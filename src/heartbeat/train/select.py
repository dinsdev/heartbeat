"""Width and epoch count from the curves, and the CNN's DS1 summary.

MODEL-04, Phase 4 settling 2: for each width and epoch, pool the five folds'
predictions per seed, score macro F1 over N, S and V (`selection_score`),
average over the three seeds, and take the joint argmax over width and epoch.
Ties go to the smaller width, then fewer epochs. A pick at epoch 36 to 40
stops for Din.

Settling 3: the DS1 headline is seed 0 at the selected configuration, through
the shared `cv_summary`; seeds 1 and 2 are a min to max range; each seed's
temperature is fitted on its own adjusted logits; the paired difference CNN
seed 0 minus baseline uses one set of patient draws (R17).

Selection reads confusion matrices only; the summary reads the named run
folders. Neither loads any record (rule 1).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CNN_SEEDS,
    CNN_WIDTHS,
    EPOCH_EDGE_FIRST,
    SCORED_CLASSES,
    SHIPPED_SEED,
)
from heartbeat.data.loader import BeatTable
from heartbeat.evaluate.bootstrap import (
    bootstrap,
    draw_counts,
    paired_difference,
    patient_confusions,
)
from heartbeat.evaluate.metrics import (
    confusion_matrix,
    json_float,
    macro_f1,
    metric_values,
    selection_score,
)
from heartbeat.train.cnn_cv import data_label, load_epoch_run
from heartbeat.train.cv import (
    HEADLINE_METRICS,
    OOFPredictions,
    cv_summary,
    oof_predictions,
)

# Settling 2, "Cost, stated": DS1 numbers at the chosen point carry this label.
SELECTED_LABEL = "at the selected width and epoch"
SELECTION_RULE = (
    "joint argmax over width and epoch of the seed mean of pooled out-of-fold "
    "macro F1 over N, S and V; ties to the smaller width, then fewer epochs "
    "(Phase 4 settling 2)"
)
# EVAL-10: the wording rule for any difference between the two models.
PAIRED_WORDING = (
    "CNN better than baseline only when the interval sits above zero; "
    "otherwise no clear difference (EVAL-10)"
)


class EpochEdgeError(RuntimeError):
    """The selected epoch is 36 or later (settling 2: stop and ask Din)."""

    def __init__(self, message: str, selection: Selection) -> None:
        """Keep the selection, so its curves can go in the ledger."""
        super().__init__(message)
        self.selection = selection


class UndefinedScoreError(ValueError):
    """A selection score is undefined (Phase 4 plan, stop condition 4)."""


@dataclass(frozen=True)
class Curves:
    """Pooled out-of-fold scores per width, seed and epoch.

    Attributes:
        widths: In `CNN_WIDTHS` order.
        seeds: In `CNN_SEEDS` order.
        nsv: Macro F1 over N, S and V, `(n_widths, n_seeds, n_epochs)`.
        four_class: Four-class macro F1, same shape.
        runs: (width, seed) to its CV run folder name.
    """

    widths: tuple[float, ...]
    seeds: tuple[int, ...]
    nsv: NDArray[np.float64]
    four_class: NDArray[np.float64]
    runs: Mapping[tuple[float, int], str]


@dataclass(frozen=True)
class Selection:
    """The selected width and epoch count, with the curves behind them.

    Attributes:
        width: The selected width.
        epoch: The selected number of epochs, 1-based.
        score: Its seed-mean macro F1 over N, S and V.
        seed_mean: The seed mean per width and epoch, `(n_widths, n_epochs)`.
        curves: The curves it was chosen from.
    """

    width: float
    epoch: int
    score: float
    seed_mean: NDArray[np.float64]
    curves: Curves

    def payload(self) -> dict[str, Any]:
        """The selection part of `results/selection.json` (settling 2, item 5)."""
        c = self.curves
        four_mean = c.four_class.mean(axis=1)
        curves = []
        best = []
        for wi, width in enumerate(c.widths):
            curves.append(
                {
                    "width": width,
                    "seed_mean": self.seed_mean[wi].tolist(),
                    "seed_mean_four_class": four_mean[wi].tolist(),
                    "per_seed": [
                        {
                            "seed": seed,
                            "run": c.runs[(width, seed)],
                            "macro_f1_nsv": c.nsv[wi, si].tolist(),
                            "macro_f1_all": c.four_class[wi, si].tolist(),
                        }
                        for si, seed in enumerate(c.seeds)
                    ],
                }
            )
            e = _first_max(self.seed_mean[wi])
            best.append(
                {
                    "width": width,
                    "epoch": e + 1,
                    "score": float(self.seed_mean[wi, e]),
                    "four_class": float(four_mean[wi, e]),
                }
            )
        return {
            "rule": SELECTION_RULE,
            "label": SELECTED_LABEL,
            "width": self.width,
            "epoch": self.epoch,
            "score": self.score,
            "candidates": int(self.seed_mean.size),
            "max_epochs": int(self.seed_mean.shape[1]),
            "edge_first": EPOCH_EDGE_FIRST,
            "seeds": list(c.seeds),
            "curves": curves,
            "best_per_width": best,
        }


def _first_max(values: NDArray[np.float64]) -> int:
    return int(np.flatnonzero(values == values.max())[0])


def epoch_curves(payload: Mapping[str, Any]) -> Curves:
    """Score the committed confusion matrices (`results/cv_cnn_curves.json`).

    Raises:
        ValueError: If a width and seed is missing or repeated, or a run has
            the wrong number of epochs.
    """
    n_epochs = int(payload["n_epochs"])
    shape = (len(CNN_WIDTHS), len(CNN_SEEDS), n_epochs)
    nsv = np.full(shape, np.nan)
    four = np.full(shape, np.nan)
    runs: dict[tuple[float, int], str] = {}
    for entry in payload["runs"]:
        key = (float(entry["width"]), int(entry["seed"]))
        if key in runs:
            raise ValueError(f"width {key[0]:g} seed {key[1]} appears twice")
        cms = np.asarray(entry["confusion"], dtype=np.int64)
        if cms.shape != (n_epochs, 4, 4):
            raise ValueError(f"width {key[0]:g} seed {key[1]}: shape {cms.shape}")
        wi, si = CNN_WIDTHS.index(key[0]), CNN_SEEDS.index(key[1])
        nsv[wi, si] = [selection_score(cm) for cm in cms]
        four[wi, si] = [macro_f1(cm, SCORED_CLASSES) for cm in cms]
        runs[key] = str(entry["run"])
    missing = [(w, s) for w in CNN_WIDTHS for s in CNN_SEEDS if (w, s) not in runs]
    if missing:
        names = ", ".join(f"width {w:g} seed {s}" for w, s in missing)
        raise ValueError(f"no curves for {names}")
    return Curves(CNN_WIDTHS, CNN_SEEDS, nsv, four, runs)


def select_config(curves: Curves) -> Selection:
    """The joint argmax of the seed mean over width and epoch (settling 2).

    Raises:
        UndefinedScoreError: If any per-seed score is undefined.
        EpochEdgeError: If the selected epoch is `EPOCH_EDGE_FIRST` or later.
    """
    bad = np.argwhere(np.isnan(curves.nsv))
    if bad.size:
        wi, si, e = (int(v) for v in bad[0])
        raise UndefinedScoreError(
            f"selection score undefined at width {curves.widths[wi]:g}, "
            f"seed {curves.seeds[si]}, epoch {e + 1}"
        )
    seed_mean = curves.nsv.mean(axis=1)
    best = seed_mean.max()
    # Widths in increasing order, then epochs: the first maximum wins the ties.
    order = sorted(range(len(curves.widths)), key=lambda i: curves.widths[i])
    wi, e = next(
        (i, int(np.flatnonzero(seed_mean[i] == best)[0]))
        for i in order
        if np.any(seed_mean[i] == best)
    )
    selection = Selection(
        width=curves.widths[wi],
        epoch=e + 1,
        score=float(best),
        seed_mean=seed_mean,
        curves=curves,
    )
    if selection.epoch >= EPOCH_EDGE_FIRST:
        raise EpochEdgeError(
            f"selected epoch {selection.epoch} at width {selection.width:g} "
            f"(seed-mean macro F1 over N, S, V {selection.score:.4f}) is at or "
            f"after epoch {EPOCH_EDGE_FIRST}; the curve may still be rising. "
            "Stop and ask Din (settling 2).",
            selection,
        )
    return selection


def _pooled(oof: OOFPredictions) -> dict[str, float | None]:
    values = metric_values(confusion_matrix(oof.y_true, oof.labels)[np.newaxis])
    return {m: json_float(float(values[m][0])) for m in HEADLINE_METRICS}


def cnn_summary(
    selection: Selection,
    run_paths: Mapping[int, Path],
    beats: BeatTable,
    baseline: OOFPredictions,
    folds_sha256: str,
    device: str,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """The `results/cv_cnn.json` payload (settling 3; no NaN).

    Args:
        selection: The selected width and epoch.
        run_paths: Seed to its CV run folder at the selected width.
        beats: The DS1 beats the runs were made from.
        baseline: The baseline's calibrated out-of-fold predictions.
        folds_sha256: SHA256 of the fold file.
        device: The CV device, for the data label.
        n_draws: Bootstrap draws.
        seed: Bootstrap seed.

    Raises:
        MissingRunError: If a seed's run folder is missing or partial.
        ValueError: If a run was made at another width or from other beats.
    """
    y = beats.beat_class
    if not np.array_equal(baseline.y_true, y):
        raise ValueError("the baseline's predictions are for other beats")
    oofs: dict[int, OOFPredictions] = {}
    runs: dict[str, str] = {}
    for s in CNN_SEEDS:
        run = load_epoch_run(run_paths[s])
        if run.width != selection.width or run.seed != s:
            raise ValueError(
                f"run {run.run} is width {run.width:g} seed {run.seed}; "
                f"wanted width {selection.width:g} seed {s}"
            )
        same = (
            np.array_equal(run.record, beats.record_id)
            and np.array_equal(run.sample, beats.sample)
            and np.array_equal(run.true_class, y)
        )
        if not same:
            raise ValueError(f"run {run.run} was made from other beats")
        oofs[s] = oof_predictions(
            "cnn", run.logits[selection.epoch - 1], run.fold, run.class_weights, y
        )
        runs[str(s)] = run.run
    headline = cv_summary(
        oofs[SHIPPED_SEED],
        beats,
        {
            "width": selection.width,
            "epoch": selection.epoch,
            "seed": SHIPPED_SEED,
            "label": SELECTED_LABEL,
        },
        data_label(device),
        folds_sha256,
        n_draws=n_draws,
        seed=seed,
    )
    others = [s for s in CNN_SEEDS if s != SHIPPED_SEED]
    points = {s: _pooled(oofs[s]) for s in others}
    value_range: dict[str, dict[str, float] | None] = {}
    for m in HEADLINE_METRICS:
        defined = [v for p in points.values() if (v := p[m]) is not None]
        value_range[m] = {"min": min(defined), "max": max(defined)} if defined else None
    patients = sorted(set(beats.subject_id.tolist()))
    counts = draw_counts(len(patients), n_draws, seed)
    paired = bootstrap(
        {
            "cnn": patient_confusions(
                y, oofs[SHIPPED_SEED].labels, beats.subject_id, patients
            ),
            "baseline": patient_confusions(
                y, baseline.labels, beats.subject_id, patients
            ),
        },
        counts=counts,
    )
    return {
        **headline,
        "temperatures": [
            {"seed": s, "temperature": oofs[s].temperature} for s in CNN_SEEDS
        ],
        "other_seeds": {
            "seeds": others,
            "label": "pooled point metrics as a min to max range (settling 3)",
            "pooled": [{"seed": s, **points[s]} for s in others],
            "range": value_range,
        },
        "paired_difference": {
            "label": "DS1 out-of-fold",
            "a": f"cnn seed {SHIPPED_SEED}",
            "b": "baseline",
            "wording": PAIRED_WORDING,
            "draws": n_draws,
            "seed": seed,
            "metrics": {
                m: paired_difference(paired, "cnn", "baseline", m).as_dict()
                for m in HEADLINE_METRICS
            },
        },
        "runs": runs,
    }
