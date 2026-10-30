"""The model-agnostic CV driver and the baseline's C (C1, C2; EVAL-07, R21).

The driver owns everything that must be the same for every model: the folds
(only through `fold_indices`), the class weights (only through
`balanced_class_weights`), the RR scaler fitted on each training part, the
selection metric (only through `selection_score`) and calibration. A model
supplies its inputs, `fit` and `logits` (`ModelSpec`). The baseline is its
first model; Phase 4 plugs the CNN into the same driver.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.config import Settings
from heartbeat.constants import (
    BASELINE_C_GRID,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    ECE_BINS,
    INTERVAL_PERCENTILES,
    N_FOLDS,
    SCORED_CLASSES,
)
from heartbeat.data.folds import Folds
from heartbeat.data.loader import BeatTable
from heartbeat.evaluate.bootstrap import bootstrap, patient_confusions
from heartbeat.evaluate.calibration import (
    adjust_logits,
    brier,
    calibrated_probs,
    ece_equal_mass,
    fit_temperature,
    log_loss_from_logits,
    predict_labels,
    reliability_data,
)
from heartbeat.evaluate.metrics import (
    confusion_matrix,
    json_float,
    macro_f1,
    metric_values,
    selection_score,
    summarize,
)
from heartbeat.models.baseline import BASELINE, coefficients
from heartbeat.models.inputs import (
    RRScaler,
    apply_rr_scaler,
    fit_rr_scaler,
    rr_model_inputs,
)
from heartbeat.models.spec import ModelSpec
from heartbeat.paths import REPO_ROOT, RUNS_DIR
from heartbeat.runs import RunFolder, create_run
from heartbeat.train.weights import balanced_class_weights

log = logging.getLogger(__name__)

# Phase 3 settling 4: every DS1 calibration number carries this label.
CALIBRATION_LABEL = "temperature fitted on these predictions"
# Settling 4 as amended (Din, option 2): reported beside the in-sample block.
CROSS_FIT_LABEL = "per-fold temperatures fitted on the other four folds"

# EVAL-07: the spread across folds, for each headline metric (EVAL-08 items 1, 2).
HEADLINE_METRICS = (
    "macro_f1_nsv",
    "macro_f1_all",
    "S_recall",
    "S_precision",
    "V_recall",
    "V_precision",
    "S_fpr",
    "V_fpr",
)


@dataclass(frozen=True)
class CVResult:
    """Out-of-fold output of one model at one setting.

    Attributes:
        model: The spec's name.
        params: The setting.
        fold: Each beat's validation fold, `(n,)`.
        logits: Raw out-of-fold logits, `(n, 4)` in `SCORED_CLASSES` order.
        class_weights: Each fold's training class weights.
        scalers: Each fold's RR scaler.
        fitted: Each fold's fitted model.
    """

    model: str
    params: Mapping[str, Any]
    fold: NDArray[np.int64]
    logits: NDArray[np.float64]
    class_weights: tuple[Mapping[str, float], ...]
    scalers: tuple[RRScaler, ...]
    fitted: tuple[Any, ...]

    def row_weights(self) -> NDArray[np.float64]:
        """Each beat's own fold's class weights, `(n, 4)`."""
        table = np.array([[w[c] for c in SCORED_CLASSES] for w in self.class_weights])
        rows: NDArray[np.float64] = table[self.fold]
        return rows


@dataclass(frozen=True)
class BaselineCV:
    """The baseline over the C grid, and the chosen C calibrated.

    Attributes:
        results: C to its out-of-fold result.
        scores: C to pooled macro F1 over N, S and V (the selection metric).
        four_class: C to pooled four-class macro F1, reported beside it.
        chosen_c: The C with the best score, ties to the smaller.
        result: The chosen C's result.
        y_true: Expert labels, `(n,)`.
        labels: Model labels: argmax of the raw logits, `(n,)`.
        adjusted: Logits less each row's own fold's log weights, `(n, 4)`.
        temperature: Fitted on the adjusted out-of-fold logits.
        probs: Calibrated probabilities, `(n, 4)`.
    """

    results: Mapping[float, CVResult]
    scores: Mapping[float, float]
    four_class: Mapping[float, float]
    chosen_c: float
    result: CVResult
    y_true: NDArray[np.str_]
    labels: NDArray[np.str_]
    adjusted: NDArray[np.float64]
    temperature: float
    probs: NDArray[np.float64]


def fold_indices(
    beats: BeatTable, folds: Folds
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """Training and validation rows for each fold, from the fold file only.

    Validation fold k is every beat whose subject is in fold k.

    Raises:
        ValueError: If a beat's subject is not in the folds.
    """
    missing = sorted(set(beats.subject_id.tolist()) - set(folds.subject_fold))
    if missing:
        raise ValueError(f"subjects {missing} are not in the fold file")
    fold_of = np.array([folds.subject_fold[s] for s in beats.subject_id.tolist()])
    return [
        (np.flatnonzero(fold_of != k), np.flatnonzero(fold_of == k))
        for k in range(N_FOLDS)
    ]


def cross_validate(
    spec: ModelSpec, beats: BeatTable, folds: Folds, params: Mapping[str, Any]
) -> CVResult:
    """Fit on four folds and predict the fifth, five times.

    Raises:
        ValueError: On a label outside the scored classes, or if the folds do
            not give every beat exactly one prediction.
    """
    y = beats.beat_class
    unknown = sorted(set(y.tolist()) - set(SCORED_CLASSES))
    if unknown:
        raise ValueError(f"labels {unknown} are not scored classes")
    rr = rr_model_inputs(beats.rr_s)
    n = y.size
    logits = np.full((n, len(SCORED_CLASSES)), np.nan)
    fold = np.full(n, -1, dtype=np.int64)
    predicted = np.zeros(n, dtype=np.int64)
    weights: list[Mapping[str, float]] = []
    scalers: list[RRScaler] = []
    fitted: list[Any] = []
    for k, (train, val) in enumerate(fold_indices(beats, folds)):
        class_weight = balanced_class_weights(y[train])
        scaler = fit_rr_scaler(rr[train])
        x_train = spec.inputs(beats, train, apply_rr_scaler(scaler, rr[train]))
        model = spec.fit(x_train, y[train], class_weight, params)
        x_val = spec.inputs(beats, val, apply_rr_scaler(scaler, rr[val]))
        logits[val] = spec.logits(model, x_val)
        fold[val] = k
        predicted[val] += 1
        weights.append(class_weight)
        scalers.append(scaler)
        fitted.append(model)
    if np.any(predicted != 1):
        raise ValueError("the folds do not give every beat exactly one prediction")
    return CVResult(
        model=spec.name,
        params=dict(params),
        fold=fold,
        logits=logits,
        class_weights=tuple(weights),
        scalers=tuple(scalers),
        fitted=tuple(fitted),
    )


def select_baseline_c(
    beats: BeatTable, folds: Folds, grid: Sequence[float] = BASELINE_C_GRID
) -> BaselineCV:
    """Cross-validate the baseline at each C, choose one, calibrate it (MODEL-01).

    Raises:
        ValueError: If a selection score is undefined.
    """
    y = beats.beat_class
    results: dict[float, CVResult] = {}
    scores: dict[float, float] = {}
    four_class: dict[float, float] = {}
    for c in grid:
        result = cross_validate(BASELINE, beats, folds, {"C": c})
        cm = confusion_matrix(y, predict_labels(result.logits))
        results[c] = result
        scores[c] = selection_score(cm)
        four_class[c] = macro_f1(cm, SCORED_CLASSES)
        if np.isnan(scores[c]):
            raise ValueError(f"selection score undefined at C = {c}")
        log.info(
            "C %s: macro F1 N, S, V %.4f; four-class %.4f", c, scores[c], four_class[c]
        )
    best = max(scores.values())
    # Ties keep the smaller C (Phase 3 task plan, design call 5).
    chosen_c = min(c for c in grid if scores[c] == best)
    result = results[chosen_c]
    adjusted = adjust_logits(result.logits, result.row_weights())
    temperature = fit_temperature(adjusted, y)
    log.info("chosen C %s; temperature %.4f", chosen_c, temperature)
    return BaselineCV(
        results=results,
        scores=scores,
        four_class=four_class,
        chosen_c=chosen_c,
        result=result,
        y_true=y,
        labels=predict_labels(result.logits),
        adjusted=adjusted,
        temperature=temperature,
        probs=calibrated_probs(adjusted, temperature),
    )


def _spread(values: NDArray[np.float64]) -> dict[str, Any]:
    defined = values[~np.isnan(values)]
    return {
        "min": float(defined.min()) if defined.size else None,
        "max": float(defined.max()) if defined.size else None,
        "undefined_folds": int(np.isnan(values).sum()),
    }


def cross_fitted_calibration(
    adjusted: NDArray[np.float64], y_true: NDArray[np.str_], fold: NDArray[np.int64]
) -> dict[str, Any]:
    """Log loss and S and V ECE with each fold's temperature fitted on the others.

    Strictly out of sample; the shipped temperature stays the pooled fit
    (EVAL-11; settling 4 as amended).
    """
    temperatures = [
        fit_temperature(adjusted[fold != k], y_true[fold != k]) for k in range(N_FOLDS)
    ]
    row_t = np.array(temperatures)[fold]
    # Per-row temperature: one temperature per row is the same as dividing the
    # row's logits by it, so the shared functions apply with T = 1.
    scaled = adjusted / row_t[:, np.newaxis]
    probs = calibrated_probs(scaled, 1.0)
    ece: dict[str, float] = {}
    for cls in ("S", "V"):
        k = SCORED_CLASSES.index(cls)
        ece[cls] = ece_equal_mass(probs[:, k], y_true == cls)
    return {
        "label": CROSS_FIT_LABEL,
        "temperatures": temperatures,
        "log_loss": log_loss_from_logits(scaled, 1.0, y_true),
        "ece": ece,
    }


def cv_summary(
    chosen: BaselineCV,
    beats: BeatTable,
    folds_sha256: str,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """The `results/cv_baseline.json` payload (DS1 out-of-fold; no NaN)."""
    y = chosen.y_true
    labels = chosen.labels
    fold = chosen.result.fold
    fold_cms = np.stack(
        [confusion_matrix(y[fold == k], labels[fold == k]) for k in range(N_FOLDS)]
    )
    fold_values = metric_values(fold_cms)
    patients = sorted(set(beats.subject_id.tolist()))
    boot = bootstrap(
        {"baseline": patient_confusions(y, labels, beats.subject_id, patients)},
        n_draws=n_draws,
        seed=seed,
    )
    calibration: dict[str, Any] = {
        "label": CALIBRATION_LABEL,
        "temperature": chosen.temperature,
        "ece": {},
        "reliability": {},
        "log_loss": log_loss_from_logits(chosen.adjusted, chosen.temperature, y),
        "brier": brier(chosen.probs, y),
        "bins": ECE_BINS,
    }
    for cls in ("S", "V"):
        k = SCORED_CLASSES.index(cls)
        calibration["ece"][cls] = ece_equal_mass(chosen.probs[:, k], y == cls)
        calibration["reliability"][cls] = reliability_data(chosen.probs[:, k], y == cls)
    calibration["cross_fitted"] = cross_fitted_calibration(chosen.adjusted, y, fold)
    return {
        "model": chosen.result.model,
        "data": "DS1 out-of-fold, CPU",
        "chosen_c": chosen.chosen_c,
        "chosen_at_grid_edge": chosen.chosen_c
        in (min(chosen.scores), max(chosen.scores)),
        "grid": [
            {
                "C": c,
                "macro_f1_nsv": json_float(chosen.scores[c]),
                "macro_f1_all": json_float(chosen.four_class[c]),
            }
            for c in chosen.scores
        ],
        "pooled": summarize(confusion_matrix(y, labels)),
        "per_fold": [{"fold": k, **summarize(fold_cms[k])} for k in range(N_FOLDS)],
        "fold_spread": {m: _spread(fold_values[m]) for m in HEADLINE_METRICS},
        "bootstrap": {
            "settings": {
                "draws": n_draws,
                "seed": seed,
                "percentiles": list(INTERVAL_PERCENTILES),
                "unit": "patient",
            },
            "intervals": {
                metric: interval.as_dict()
                for metric, interval in boot.intervals["baseline"].items()
            },
        },
        "calibration": calibration,
        "patients": patients,
        "class_weights": [dict(w) for w in chosen.result.class_weights],
        "folds_sha256": folds_sha256,
    }


def run_baseline(
    settings: Settings,
    beats: BeatTable,
    folds: Folds,
    folds_sha256: str,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
    grid: Sequence[float] = BASELINE_C_GRID,
    n_draws: int = BOOTSTRAP_DRAWS,
) -> tuple[RunFolder, dict[str, Any]]:
    """Run the baseline CV into a new run folder; return the run and the summary.

    Writes `metrics.json` (the summary), `oof.npz` and `model.npz` to the run
    folder. Never writes `results/` (rule 5; only the rebuild stage does).
    """
    extra = {
        "model": BASELINE.name,
        "grid": list(grid),
        "folds_sha256": folds_sha256,
        "bootstrap_draws": n_draws,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }
    with create_run("cv-baseline", settings, extra, root=root, repo=repo) as run:
        log.info("baseline CV on %d DS1 beats", beats.sample.size)
        chosen = select_baseline_c(beats, folds, grid)
        summary = cv_summary(chosen, beats, folds_sha256, n_draws=n_draws)
        run.write_json("metrics", summary)
        run.write_arrays(
            "oof",
            record=beats.record_id,
            subject=beats.subject_id,
            sample=beats.sample,
            true_class=chosen.y_true,
            fold=chosen.result.fold,
            raw_logits=chosen.result.logits,
            adjusted_logits=chosen.adjusted,
            calibrated_probs=chosen.probs,
            classes=np.array(SCORED_CLASSES),
        )
        coef, intercept = zip(
            *(coefficients(f) for f in chosen.result.fitted), strict=True
        )
        run.write_arrays(
            "model",
            coef=np.stack(coef),
            intercept=np.stack(intercept),
            scaler_mean=np.stack([s.mean for s in chosen.result.scalers]),
            scaler_std=np.stack([s.std for s in chosen.result.scalers]),
            class_weights=chosen.result.row_weights()[
                [
                    int(np.flatnonzero(chosen.result.fold == k)[0])
                    for k in range(N_FOLDS)
                ]
            ],
            classes=np.array(SCORED_CLASSES),
            c=np.array(chosen.chosen_c),
        )
        log.info("wrote %s", run.path)
    return run, summary
