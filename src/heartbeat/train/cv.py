"""The model-agnostic CV driver and the baseline's C (C1, C2; EVAL-07, R21).

The driver owns everything that must be the same for every model: the folds
(only through a `Splitter`), the class weights (only through
`balanced_class_weights`), the RR scaler fitted on each training part, the
selection metric (only through `selection_score`) and calibration. A model
supplies its inputs, a fit and `logits` (`ModelSpec`). The baseline goes
through `cross_validate`; the CNN, which trains in epochs, through
`cross_validate_epochs`, which scores every epoch (Phase 4 settling 2).

A splitter is the driver's only source of folds: the patient folds from
`config/folds.json`, or the exhibit's beat-level folds (C5). The resolved
config of a run names its splitter, so the honest and leaky runs of one model
differ in that key alone (R24).
"""

import hashlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.model_selection import StratifiedKFold

from heartbeat.config import Settings
from heartbeat.constants import (
    BASELINE_C_GRID,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    ECE_BINS,
    INTERVAL_PERCENTILES,
    LEAKY_SPLIT_SEED,
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

# Phase 4 design call 9: the data label each results file carries.
BASELINE_DATA_LABEL = "DS1 out-of-fold, CPU"

# The driver's single sources (R21), named in every resolved config.
DRIVER_SOURCES = {
    "class_weights": "balanced_class_weights",
    "rr_scaler": "fit_rr_scaler",
    "selection_metric": "selection_score",
}

FoldPairs = list[tuple[NDArray[np.int64], NDArray[np.int64]]]

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
        config: The resolved config (R24).
    """

    model: str
    params: Mapping[str, Any]
    fold: NDArray[np.int64]
    logits: NDArray[np.float64]
    class_weights: tuple[Mapping[str, float], ...]
    scalers: tuple[RRScaler, ...]
    fitted: tuple[Any, ...]
    config: Mapping[str, Any]

    def row_weights(self) -> NDArray[np.float64]:
        """Each beat's own fold's class weights, `(n, 4)`."""
        return row_weights(self.class_weights, self.fold)


@dataclass(frozen=True)
class EpochCVResult:
    """Out-of-fold output of a model scored after every epoch.

    Attributes:
        model: The spec's name.
        params: The setting.
        fold: Each beat's validation fold, `(n,)`.
        logits: Raw out-of-fold logits after each epoch, float32,
            `(n_epochs, n, 4)` in `SCORED_CLASSES` order; index e is epoch e + 1.
        class_weights: Each fold's training class weights.
        scalers: Each fold's RR scaler.
        fitted: Each fold's model after the last epoch.
        config: The resolved config (R24).
        folds_run: The folds trained, in order; all five except in a
            development run. Weights, scalers and models follow this order.
    """

    model: str
    params: Mapping[str, Any]
    fold: NDArray[np.int64]
    logits: NDArray[np.float32]
    class_weights: tuple[Mapping[str, float], ...]
    scalers: tuple[RRScaler, ...]
    fitted: tuple[Any, ...]
    config: Mapping[str, Any]
    folds_run: tuple[int, ...] = tuple(range(N_FOLDS))


@dataclass(frozen=True)
class Splitter:
    """The driver's only source of folds.

    Attributes:
        name: "patient" (the C1 folds) or "beat" (the exhibit's leaky side).
        config: What decides the folds, for the resolved config.
        indices: Training and validation rows of each fold.
    """

    name: str
    config: Mapping[str, Any]
    indices: Callable[[BeatTable], FoldPairs]


@dataclass(frozen=True)
class OOFPredictions:
    """Calibrated out-of-fold predictions of one model (EVAL-11).

    Attributes:
        model: The model's name.
        y_true: Expert labels, `(n,)`.
        labels: Argmax of the raw logits, `(n,)`.
        fold: Each beat's validation fold, `(n,)`.
        adjusted: Logits less each row's own fold's log weights, `(n, 4)`.
        temperature: Fitted on the adjusted logits.
        probs: Calibrated probabilities, `(n, 4)`.
        class_weights: Each fold's training class weights.
    """

    model: str
    y_true: NDArray[np.str_]
    labels: NDArray[np.str_]
    fold: NDArray[np.int64]
    adjusted: NDArray[np.float64]
    temperature: float
    probs: NDArray[np.float64]
    class_weights: tuple[Mapping[str, float], ...]


def row_weights(
    class_weights: Sequence[Mapping[str, float]], fold: NDArray[np.int64]
) -> NDArray[np.float64]:
    """Each beat's own fold's class weights, `(n, 4)`."""
    table = np.array([[w[c] for c in SCORED_CLASSES] for w in class_weights])
    rows: NDArray[np.float64] = table[fold]
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


def patient_splitter(folds: Folds) -> Splitter:
    """The C1 patient folds, from the fold file only (through `fold_indices`)."""
    return Splitter(
        name="patient",
        config={
            "name": "patient",
            "subject_fold": dict(sorted(folds.subject_fold.items())),
        },
        indices=lambda beats: fold_indices(beats, folds),
    )


def beat_splitter(seed: int = LEAKY_SPLIT_SEED) -> Splitter:
    """The exhibit's leaky side: beat-level stratified 5-fold (C5; EXHIBIT-01).

    `StratifiedKFold` on the beats' classes with an integer `random_state`
    (Phase 4 task plan, design call 1), so the pinned scikit-learn makes it
    reproducible. Patients end up on both sides of every fold, which is the
    leak the exhibit shows.
    """

    def indices(beats: BeatTable) -> FoldPairs:
        y = beats.beat_class
        splitter = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        return [
            (np.asarray(train, dtype=np.int64), np.asarray(val, dtype=np.int64))
            for train, val in splitter.split(np.zeros(y.size), y)
        ]

    return Splitter(
        name="beat",
        config={
            "name": "beat",
            "method": "StratifiedKFold",
            "n_splits": N_FOLDS,
            "shuffle": True,
            "seed": seed,
        },
        indices=indices,
    )


def fold_assignment_sha256(fold: NDArray[np.int64]) -> str:
    """SHA256 of a beat-to-fold assignment, as int64 bytes in beat order."""
    return hashlib.sha256(
        np.ascontiguousarray(fold, dtype=np.int64).tobytes()
    ).hexdigest()


def resolved_config(
    spec: ModelSpec,
    splitter: Splitter,
    params: Mapping[str, Any],
    n_epochs: int | None = None,
) -> dict[str, Any]:
    """Everything a CV run's numbers depend on, as one dict (R24).

    The splitter is one key, so an honest and a leaky run of one model
    differ in that key alone.
    """
    return {
        "model": spec.name,
        "model_config": dict(spec.config),
        "params": dict(params),
        "n_epochs": n_epochs,
        "splitter": dict(splitter.config),
        "driver": dict(DRIVER_SOURCES),
    }


def _check_labels(y: NDArray[np.str_]) -> None:
    unknown = sorted(set(y.tolist()) - set(SCORED_CLASSES))
    if unknown:
        raise ValueError(f"labels {unknown} are not scored classes")


def cross_validate(
    spec: ModelSpec, beats: BeatTable, splitter: Splitter, params: Mapping[str, Any]
) -> CVResult:
    """Fit on four folds and predict the fifth, five times.

    Raises:
        ValueError: If the spec trains in epochs, on a label outside the scored
            classes, or if the folds do not give every beat exactly one
            prediction.
    """
    if spec.fit_epochs is not None:
        raise ValueError(f"model {spec.name} has fit_epochs; use cross_validate_epochs")
    y = beats.beat_class
    _check_labels(y)
    rr = rr_model_inputs(beats.rr_s)
    n = y.size
    logits = np.full((n, len(SCORED_CLASSES)), np.nan)
    fold = np.full(n, -1, dtype=np.int64)
    predicted = np.zeros(n, dtype=np.int64)
    weights: list[Mapping[str, float]] = []
    scalers: list[RRScaler] = []
    fitted: list[Any] = []
    for k, (train, val) in enumerate(splitter.indices(beats)):
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
        config=resolved_config(spec, splitter, params),
    )


def cross_validate_epochs(
    spec: ModelSpec,
    beats: BeatTable,
    splitter: Splitter,
    params: Mapping[str, Any],
    n_epochs: int,
    only_folds: Sequence[int] | None = None,
) -> EpochCVResult:
    """Train on four folds for `n_epochs`, scoring the fifth after every epoch.

    The same folds, weights and scaler as `cross_validate` (R21); every run
    trains all `n_epochs` (no early stopping, EVAL-07). `only_folds` trains
    just those folds, for development runs; the other rows stay NaN with
    fold -1, and such a run feeds no selection.

    Raises:
        ValueError: If the spec has no `fit_epochs`, on a label outside the
            scored classes, if a fit yields a number of epochs other than
            `n_epochs`, or if the folds do not give every beat exactly one
            prediction per epoch.
    """
    if spec.fit_epochs is None:
        raise ValueError(f"model {spec.name} has no fit_epochs; use cross_validate")
    y = beats.beat_class
    _check_labels(y)
    rr = rr_model_inputs(beats.rr_s)
    n = y.size
    logits = np.full((n_epochs, n, len(SCORED_CLASSES)), np.nan, dtype=np.float32)
    fold = np.full(n, -1, dtype=np.int64)
    predicted = np.zeros(n, dtype=np.int64)
    weights: list[Mapping[str, float]] = []
    scalers: list[RRScaler] = []
    fitted: list[Any] = []
    pairs = splitter.indices(beats)
    folds_run = tuple(range(len(pairs)) if only_folds is None else only_folds)
    for k in folds_run:
        train, val = pairs[k]
        class_weight = balanced_class_weights(y[train])
        scaler = fit_rr_scaler(rr[train])
        x_train = spec.inputs(beats, train, apply_rr_scaler(scaler, rr[train]))
        x_val = spec.inputs(beats, val, apply_rr_scaler(scaler, rr[val]))
        epochs = 0
        model: Any = None
        for model in spec.fit_epochs(
            x_train, y[train], class_weight, params, k, n_epochs
        ):
            logits[epochs, val] = spec.logits(model, x_val)
            epochs += 1
        if epochs != n_epochs:
            raise ValueError(f"fold {k}: {epochs} epochs trained, {n_epochs} asked")
        log.info("%s %s fold %d: %d epochs", spec.name, dict(params), k, epochs)
        fold[val] = k
        predicted[val] += 1
        weights.append(class_weight)
        scalers.append(scaler)
        fitted.append(model)
    expected = np.ones(n, dtype=np.int64)
    if only_folds is not None:
        expected = np.zeros(n, dtype=np.int64)
        for k in folds_run:
            expected[pairs[k][1]] += 1
    if np.any(predicted != expected):
        raise ValueError("the folds do not give every beat exactly one prediction")
    return EpochCVResult(
        model=spec.name,
        params=dict(params),
        fold=fold,
        logits=logits,
        class_weights=tuple(weights),
        scalers=tuple(scalers),
        fitted=tuple(fitted),
        config=resolved_config(spec, splitter, params, n_epochs),
        folds_run=folds_run,
    )


def select_baseline_c(
    beats: BeatTable, folds: Folds, grid: Sequence[float] = BASELINE_C_GRID
) -> BaselineCV:
    """Cross-validate the baseline at each C, choose one, calibrate it (MODEL-01).

    Raises:
        ValueError: If a selection score is undefined.
    """
    y = beats.beat_class
    splitter = patient_splitter(folds)
    results: dict[float, CVResult] = {}
    scores: dict[float, float] = {}
    four_class: dict[float, float] = {}
    for c in grid:
        result = cross_validate(BASELINE, beats, splitter, {"C": c})
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


def oof_predictions(
    model: str,
    logits: NDArray[np.floating[Any]],
    fold: NDArray[np.int64],
    class_weights: Sequence[Mapping[str, float]],
    y_true: NDArray[np.str_],
) -> OOFPredictions:
    """Labels and calibrated probabilities from raw out-of-fold logits (EVAL-11).

    Labels are the argmax of the raw logits; each row is adjusted with its own
    fold's weights, then one temperature is fitted on the adjusted logits.
    """
    raw = np.asarray(logits, dtype=np.float64)
    adjusted = adjust_logits(raw, row_weights(class_weights, fold))
    temperature = fit_temperature(adjusted, y_true)
    return OOFPredictions(
        model=model,
        y_true=y_true,
        labels=predict_labels(raw),
        fold=fold,
        adjusted=adjusted,
        temperature=temperature,
        probs=calibrated_probs(adjusted, temperature),
        class_weights=tuple(class_weights),
    )


def cv_summary(
    oof: OOFPredictions,
    beats: BeatTable,
    selection: Mapping[str, Any],
    data_label: str,
    folds_sha256: str,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """A DS1 out-of-fold summary of any model; no NaN (design call 9).

    Args:
        oof: The calibrated out-of-fold predictions.
        beats: The beats they belong to, for the patients.
        selection: The caller's selection block (the baseline's C grid, the
            CNN's width and epoch), merged in at the top level.
        data_label: For example "DS1 out-of-fold, MPS".
        folds_sha256: SHA256 of the fold file.
        n_draws: Bootstrap draws.
        seed: Bootstrap seed.
    """
    y = oof.y_true
    labels = oof.labels
    fold = oof.fold
    fold_cms = np.stack(
        [confusion_matrix(y[fold == k], labels[fold == k]) for k in range(N_FOLDS)]
    )
    fold_values = metric_values(fold_cms)
    patients = sorted(set(beats.subject_id.tolist()))
    boot = bootstrap(
        {oof.model: patient_confusions(y, labels, beats.subject_id, patients)},
        n_draws=n_draws,
        seed=seed,
    )
    calibration: dict[str, Any] = {
        "label": CALIBRATION_LABEL,
        "temperature": oof.temperature,
        "ece": {},
        "reliability": {},
        "log_loss": log_loss_from_logits(oof.adjusted, oof.temperature, y),
        "brier": brier(oof.probs, y),
        "bins": ECE_BINS,
    }
    for cls in ("S", "V"):
        k = SCORED_CLASSES.index(cls)
        calibration["ece"][cls] = ece_equal_mass(oof.probs[:, k], y == cls)
        calibration["reliability"][cls] = reliability_data(oof.probs[:, k], y == cls)
    calibration["cross_fitted"] = cross_fitted_calibration(oof.adjusted, y, fold)
    return {
        "model": oof.model,
        "data": data_label,
        **selection,
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
                for metric, interval in boot.intervals[oof.model].items()
            },
        },
        "calibration": calibration,
        "patients": patients,
        "class_weights": [dict(w) for w in oof.class_weights],
        "folds_sha256": folds_sha256,
    }


def baseline_oof(chosen: BaselineCV) -> OOFPredictions:
    """The chosen C's calibrated out-of-fold predictions."""
    return OOFPredictions(
        model=chosen.result.model,
        y_true=chosen.y_true,
        labels=chosen.labels,
        fold=chosen.result.fold,
        adjusted=chosen.adjusted,
        temperature=chosen.temperature,
        probs=chosen.probs,
        class_weights=chosen.result.class_weights,
    )


def baseline_summary(
    chosen: BaselineCV,
    beats: BeatTable,
    folds_sha256: str,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """The `results/cv_baseline.json` payload (DS1 out-of-fold; no NaN)."""
    selection = {
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
    }
    return cv_summary(
        baseline_oof(chosen),
        beats,
        selection,
        BASELINE_DATA_LABEL,
        folds_sha256,
        n_draws=n_draws,
        seed=seed,
    )


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
        summary = baseline_summary(chosen, beats, folds_sha256, n_draws=n_draws)
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
