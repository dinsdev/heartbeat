"""Metrics from 4 by 4 confusion matrices (C4; EVAL-08, R16).

Rows are the expert label, columns the model label, both in `SCORED_CLASSES`
order. Every metric is a function of the matrix, so pooled, per-fold,
per-patient and bootstrap numbers share one code path. Batched functions take
`(..., 4, 4)` arrays. An undefined metric (zero denominator) is NaN, never 0
(Phase 3 settling 2); `summarize` writes it as `None`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import HEADLINE_CLASSES, SCORED_CLASSES

N_CLASSES = len(SCORED_CLASSES)
CLASS_INDEX = {cls: k for k, cls in enumerate(SCORED_CLASSES)}
RATE_NAMES = ("recall", "precision", "f1", "fpr")
EC57_CLASSES = ("S", "V")
EC57_NAMES = ("se", "ppv", "fpr")


@dataclass(frozen=True)
class ClassMetrics:
    """One-vs-rest metrics for one class; NaN when undefined."""

    recall: float
    precision: float
    f1: float
    fpr: float


@dataclass(frozen=True)
class EC57Metrics:
    """AAMI EC57 statistics for S or V (Phase 3 settling 5); NaN when undefined."""

    se: float
    ppv: float
    fpr: float


def class_indices(labels: NDArray[np.str_]) -> NDArray[np.int64]:
    """Map class strings to their index in `SCORED_CLASSES`.

    Raises:
        ValueError: For any label outside the scored classes (Q included).
    """
    labels = np.asarray(labels)
    match = labels[..., np.newaxis] == np.array(SCORED_CLASSES)
    valid = match.any(axis=-1)
    if not np.all(valid):
        bad = sorted(set(labels[~valid].tolist()))
        raise ValueError(f"labels {bad} are not scored classes {SCORED_CLASSES}")
    result: NDArray[np.int64] = match.argmax(axis=-1).astype(np.int64)
    return result


def confusion_matrix(
    y_true: NDArray[np.str_], y_pred: NDArray[np.str_]
) -> NDArray[np.int64]:
    """Count beats by expert label (rows) and model label (columns), `(4, 4)`.

    Raises:
        ValueError: On different lengths or a label outside the scored classes.
    """
    if y_true.shape != y_pred.shape:
        raise ValueError(
            f"y_true and y_pred differ in length: {y_true.shape} and {y_pred.shape}"
        )
    true_index = class_indices(y_true)
    pred_index = class_indices(y_pred)
    flat = np.bincount(
        true_index * N_CLASSES + pred_index, minlength=N_CLASSES * N_CLASSES
    )
    return flat.reshape(N_CLASSES, N_CLASSES).astype(np.int64)


def _ratio(
    numerator: NDArray[np.float64], denominator: NDArray[np.float64]
) -> NDArray[np.float64]:
    out = np.full(np.broadcast_shapes(numerator.shape, denominator.shape), np.nan)
    np.divide(numerator, denominator, out=out, where=denominator != 0)
    return out


def class_rates(cms: NDArray[np.int64]) -> dict[str, NDArray[np.float64]]:
    """One-vs-rest recall, precision, F1 and FPR for each class.

    Args:
        cms: Confusion matrices, `(..., 4, 4)`.

    Returns:
        Metric name to values, `(..., 4)` in `SCORED_CLASSES` order. F1 is
        2TP / (2TP + FP + FN), undefined only when the class is absent from
        both labels and predictions (Phase 3 settling 2).
    """
    counts = np.asarray(cms, dtype=np.float64)
    assert counts.shape[-2:] == (N_CLASSES, N_CLASSES), counts.shape
    tp = np.diagonal(counts, axis1=-2, axis2=-1)
    true_sum = counts.sum(axis=-1)
    pred_sum = counts.sum(axis=-2)
    total = counts.sum(axis=(-2, -1))[..., np.newaxis]
    fn = true_sum - tp
    fp = pred_sum - tp
    tn = total - tp - fn - fp
    return {
        "recall": _ratio(tp, tp + fn),
        "precision": _ratio(tp, tp + fp),
        "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        "fpr": _ratio(fp, fp + tn),
    }


def _macro_f1_batched(
    cms: NDArray[np.int64], classes: Sequence[str]
) -> NDArray[np.float64]:
    f1 = class_rates(cms)["f1"][..., [CLASS_INDEX[c] for c in classes]]
    # A plain mean: one undefined class makes the macro undefined (settling 2).
    result: NDArray[np.float64] = f1.mean(axis=-1)
    return result


def _ec57_batched(cms: NDArray[np.int64]) -> dict[str, NDArray[np.float64]]:
    """EC57 Se, +P and FPR for S and V from de Chazal's Table V counts.

    Returns:
        Names `ec57_<class>_<metric>` to values, `(...)`.
    """
    counts = np.asarray(cms, dtype=np.float64)
    n, s, v, f = (CLASS_INDEX[c] for c in SCORED_CLASSES)
    out: dict[str, NDArray[np.float64]] = {}
    # V: Fv counts in none of TP, FN, FP, TN.
    tp = counts[..., v, v]
    fn = counts[..., v, n] + counts[..., v, s] + counts[..., v, f]
    fp = counts[..., n, v] + counts[..., s, v]
    tn = counts[..., [n, s, f], :][..., :, [n, s, f]].sum(axis=(-2, -1))
    out["ec57_V_se"] = _ratio(tp, tp + fn)
    out["ec57_V_ppv"] = _ratio(tp, tp + fp)
    out["ec57_V_fpr"] = _ratio(fp, tn + fp)
    # S: one-vs-rest.
    tp = counts[..., s, s]
    fn = counts[..., s, n] + counts[..., s, v] + counts[..., s, f]
    fp = counts[..., n, s] + counts[..., v, s] + counts[..., f, s]
    tn = counts[..., [n, v, f], :][..., :, [n, v, f]].sum(axis=(-2, -1))
    out["ec57_S_se"] = _ratio(tp, tp + fn)
    out["ec57_S_ppv"] = _ratio(tp, tp + fp)
    out["ec57_S_fpr"] = _ratio(fp, tn + fp)
    return out


def metric_values(cms: NDArray[np.int64]) -> dict[str, NDArray[np.float64]]:
    """Every scalar metric the report needs, by flat name, `(...)` each.

    Names: `<class>_<recall|precision|f1|fpr>`, `macro_f1_nsv` (the headline
    and selection metric), `macro_f1_all` (four-class, beside it) and
    `ec57_<S|V>_<se|ppv|fpr>`.
    """
    rates = class_rates(cms)
    values: dict[str, NDArray[np.float64]] = {}
    for k, cls in enumerate(SCORED_CLASSES):
        for name in RATE_NAMES:
            values[f"{cls}_{name}"] = rates[name][..., k]
    values["macro_f1_nsv"] = _macro_f1_batched(cms, HEADLINE_CLASSES)
    values["macro_f1_all"] = _macro_f1_batched(cms, SCORED_CLASSES)
    values.update(_ec57_batched(cms))
    return values


def class_metrics(cm: NDArray[np.int64]) -> dict[str, ClassMetrics]:
    """One-vs-rest metrics per class for one `(4, 4)` matrix."""
    rates = class_rates(cm)
    return {
        cls: ClassMetrics(*(float(rates[name][k]) for name in RATE_NAMES))
        for k, cls in enumerate(SCORED_CLASSES)
    }


def macro_f1(cm: NDArray[np.int64], classes: Sequence[str]) -> float:
    """Mean F1 over `classes`; NaN if any of them is undefined."""
    return float(_macro_f1_batched(cm, classes))


def ec57_metrics(cm: NDArray[np.int64]) -> dict[str, EC57Metrics]:
    """EC57 Se, +P and FPR for S and V (Phase 3 settling 5)."""
    values = _ec57_batched(cm)
    return {
        cls: EC57Metrics(*(float(values[f"ec57_{cls}_{n}"]) for n in EC57_NAMES))
        for cls in EC57_CLASSES
    }


def selection_score(cm: NDArray[np.int64]) -> float:
    """The selection metric: pooled macro F1 over N, S and V (Phase 3 settling 1)."""
    return macro_f1(cm, HEADLINE_CLASSES)


def json_float(value: float) -> float | None:
    """Return `value`, or `None` when it is NaN ("undefined", never 0)."""
    return None if np.isnan(value) else float(value)


def summarize(cm: NDArray[np.int64]) -> dict[str, Any]:
    """Every metric of one matrix as a JSON-ready dict, NaN written as `None`."""
    metrics = class_metrics(cm)
    ec57 = ec57_metrics(cm)
    return {
        "classes": list(SCORED_CLASSES),
        "confusion": np.asarray(cm).tolist(),
        "n_beats": int(np.asarray(cm).sum()),
        "per_class": {
            cls: {name: json_float(getattr(m, name)) for name in RATE_NAMES}
            for cls, m in metrics.items()
        },
        "macro_f1_nsv": json_float(macro_f1(cm, HEADLINE_CLASSES)),
        "macro_f1_all": json_float(macro_f1(cm, SCORED_CLASSES)),
        "ec57": {
            cls: {name: json_float(getattr(m, name)) for name in EC57_NAMES}
            for cls, m in ec57.items()
        },
    }
