"""The pre-registered test report (A3, C4; EVAL-08 to EVAL-12).

Built from the existing `heartbeat.evaluate` functions, so the sealed numbers
are computed exactly as the DS1 out-of-fold ones were. Q beats are left out of
every metric and counted. All four models (the three CNN seeds and the
baseline) are scored on one shared set of patient draws; the headline and the
comparison use seed 0 and the baseline (EVAL-08 item 6, EVAL-10).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CNN_SEEDS,
    ECE_BINS,
    INTERVAL_PERCENTILES,
    SCORED_CLASSES,
    SHIPPED_SEED,
)
from heartbeat.evaluate.bootstrap import (
    Interval,
    bootstrap,
    draw_counts,
    paired_difference,
    patient_confusions,
)
from heartbeat.evaluate.calibration import (
    brier,
    calibrated_probs,
    ece_equal_mass,
    log_loss_from_logits,
    predict_labels,
    reliability_data,
)
from heartbeat.evaluate.metrics import confusion_matrix, summarize
from heartbeat.evaluate.per_patient import per_patient_table
from heartbeat.train.cv import HEADLINE_METRICS
from heartbeat.train.select import PAIRED_WORDING

CNN = f"cnn-seed-{SHIPPED_SEED}"
BASELINE = "baseline"
MODEL_NAMES = (*(f"cnn-seed-{s}" for s in CNN_SEEDS), BASELINE)

# EVAL-08 item 3: S is repeated without this record, which holds most of
# DS2's S beats.
S_EXCLUDED_RECORD = "232"

# EVAL-10: differences where a larger value is better; FPRs are reported, not
# compared.
COMPARED_METRICS = (
    "macro_f1_nsv",
    "macro_f1_all",
    "S_recall",
    "S_precision",
    "V_recall",
    "V_precision",
)
EC57_METRICS = (
    "ec57_S_se",
    "ec57_S_ppv",
    "ec57_S_fpr",
    "ec57_V_se",
    "ec57_V_ppv",
    "ec57_V_fpr",
)
N_F_METRICS = ("N_recall", "N_precision", "F_recall", "F_precision")

Q_NOTE = "Q beats are not scored (DATA-10); they are left out and counted"
F_CAVEAT = (
    "F beats come almost entirely from one patient on each side, so the F "
    "numbers describe two people, not a class"
)
EC57_LABEL = (
    "AAMI EC57 definitions as printed in de Chazal's Table V: a V false "
    "positive is an N or S beat labeled V, an S false positive an N, V or F "
    "beat labeled S"
)


@dataclass(frozen=True)
class ModelScores:
    """One model's raw output on every beat, and its calibration.

    Attributes:
        logits: Raw logits `(n, 4)` in `SCORED_CLASSES` order, Q beats included.
        log_class_weights: Log of its training class weights, `(4,)`.
        temperature: Its DS1 out-of-fold temperature.
    """

    logits: NDArray[np.float64]
    log_class_weights: NDArray[np.float64]
    temperature: float


def _verdict(interval: Interval) -> str:
    if interval.low is not None and interval.low > 0:
        return "CNN better than baseline"
    if interval.high is not None and interval.high < 0:
        return "baseline better than CNN"
    return "no clear difference"


def _intervals(
    intervals: Mapping[str, Interval], names: Sequence[str]
) -> dict[str, Any]:
    return {m: intervals[m].as_dict() for m in names}


def _calibration(
    scores: ModelScores, y: NDArray[np.str_], scored: NDArray[np.bool_]
) -> dict[str, Any]:
    adjusted = scores.logits[scored] - scores.log_class_weights
    probs = calibrated_probs(adjusted, scores.temperature)
    block: dict[str, Any] = {
        "temperature": scores.temperature,
        "bins": ECE_BINS,
        "ece": {},
        "reliability": {},
        "log_loss": log_loss_from_logits(adjusted, scores.temperature, y),
        "brier": brier(probs, y),
    }
    for cls in ("S", "V"):
        k = SCORED_CLASSES.index(cls)
        block["ece"][cls] = ece_equal_mass(probs[:, k], y == cls)
        block["reliability"][cls] = reliability_data(probs[:, k], y == cls)
    return block


def sealed_report(
    y_true: NDArray[np.str_],
    subject_id: NDArray[np.str_],
    record_id: NDArray[np.str_],
    scores: Mapping[str, ModelScores],
    data_label: str,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
    excluded_record: str = S_EXCLUDED_RECORD,
) -> dict[str, Any]:
    """The EVAL-08 report as a JSON-ready dict (no NaN; undefined is None).

    Args:
        y_true: Every kept beat's class, Q included, `(n,)`.
        subject_id: Each beat's patient, `(n,)`.
        record_id: Each beat's record, `(n,)`.
        scores: Model name (`MODEL_NAMES`) to its scores on the same beats.
        data_label: What the beats are, for example "DS2 test, CPU".
        n_draws: Bootstrap draws (10,000 in every real run).
        seed: Bootstrap seed.
        excluded_record: The record EVAL-08 item 3 leaves out.

    Raises:
        ValueError: If a model is missing or extra.
    """
    if sorted(scores) != sorted(MODEL_NAMES):
        raise ValueError(f"models {sorted(scores)}, expected {sorted(MODEL_NAMES)}")
    scored = y_true != "Q"
    y = y_true[scored]
    subjects = subject_id[scored]
    records = record_id[scored]
    patients = sorted(set(subjects.tolist()))
    labels = {name: predict_labels(scores[name].logits[scored]) for name in MODEL_NAMES}
    confusions = {
        name: patient_confusions(y, labels[name], subjects, patients)
        for name in MODEL_NAMES
    }
    boot = bootstrap(confusions, counts=draw_counts(len(patients), n_draws, seed))
    all_metrics = list(boot.intervals[CNN])

    keep = records != excluded_record
    others = sorted(set(subjects[keep].tolist()))
    without = bootstrap(
        {
            name: patient_confusions(
                y[keep], labels[name][keep], subjects[keep], others
            )
            for name in (CNN, BASELINE)
        },
        counts=draw_counts(len(others), n_draws, seed),
    )

    comparison = {}
    for metric in COMPARED_METRICS:
        diff = paired_difference(boot, CNN, BASELINE, metric)
        comparison[metric] = {**diff.as_dict(), "verdict": _verdict(diff)}

    seed_names = [n for n in MODEL_NAMES if n not in (CNN, BASELINE)]
    points = {
        n: {m: boot.intervals[n][m].as_dict()["point"] for m in HEADLINE_METRICS}
        for n in seed_names
    }
    ranges: dict[str, dict[str, float] | None] = {}
    for metric in HEADLINE_METRICS:
        defined = [v for p in points.values() if (v := p[metric]) is not None]
        ranges[metric] = {"min": min(defined), "max": max(defined)} if defined else None

    n_q = int((~scored).sum())
    return {
        "data": data_label,
        "patients": patients,
        "beats": {
            "scored": int(scored.sum()),
            "q_not_scored": n_q,
            "by_class": {c: int((y == c).sum()) for c in SCORED_CLASSES},
        },
        "bootstrap": {
            "draws": n_draws,
            "seed": seed,
            "percentiles": list(INTERVAL_PERCENTILES),
            "unit": "patient",
            "shared": list(MODEL_NAMES),
        },
        "models": {
            name: {
                "pooled": summarize(confusion_matrix(y, labels[name])),
                "temperature": scores[name].temperature,
            }
            for name in MODEL_NAMES
        },
        "headline": {
            "models": {"cnn": CNN, "baseline": BASELINE},
            "metrics": list(HEADLINE_METRICS),
            "intervals": {
                "cnn": _intervals(boot.intervals[CNN], all_metrics),
                "baseline": _intervals(boot.intervals[BASELINE], all_metrics),
            },
        },
        "comparison": {
            "a": CNN,
            "b": BASELINE,
            "difference": "a minus b, on the shared draws",
            "wording": PAIRED_WORDING,
            "headline_metric": "macro_f1_nsv",
            "metrics": comparison,
        },
        "fpr": {
            "one_vs_rest": {
                key: _intervals(boot.intervals[name], ("S_fpr", "V_fpr"))
                for key, name in (("cnn", CNN), ("baseline", BASELINE))
            },
            "ec57": {
                "label": EC57_LABEL,
                "q_not_scored": n_q,
                **{
                    key: _intervals(boot.intervals[name], EC57_METRICS)
                    for key, name in (("cnn", CNN), ("baseline", BASELINE))
                },
            },
        },
        "s_without_excluded": {
            "record": excluded_record,
            "present": bool((~keep).any()),
            "patients": others,
            "intervals": {
                key: _intervals(without.intervals[name], ("S_recall", "S_precision"))
                for key, name in (("cnn", CNN), ("baseline", BASELINE))
            },
        },
        "per_patient": {
            name: [
                row.as_dict() for row in per_patient_table(confusions[name], patients)
            ]
            for name in (CNN, BASELINE)
        },
        "confusion": {
            "classes": list(SCORED_CLASSES),
            "rows": "true class",
            "columns": "label",
            "note": Q_NOTE,
            "q_not_scored": n_q,
            "matrices": {
                name: confusion_matrix(y, labels[name]).tolist() for name in MODEL_NAMES
            },
        },
        "n_and_f": {
            "caveat": F_CAVEAT,
            **{
                key: _intervals(boot.intervals[name], N_F_METRICS)
                for key, name in (("cnn", CNN), ("baseline", BASELINE))
            },
        },
        "seed_range": {
            "seeds": seed_names,
            "label": "point metrics of the other two final models, min to max",
            "points": points,
            "range": ranges,
        },
        "calibration": {
            name: _calibration(scores[name], y, scored) for name in MODEL_NAMES
        },
    }
