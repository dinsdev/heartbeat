"""The baseline: multinomial logistic regression on the six RR inputs (C2; MODEL-01).

Runs in float64 (it never ships; design call 4). A `ConvergenceWarning` is an
error wherever this runs, not only under pytest (design call 5).
"""

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from heartbeat.constants import BASELINE_MAX_ITER, SCORED_CLASSES
from heartbeat.data.loader import BeatTable
from heartbeat.models.spec import ModelSpec


@dataclass(frozen=True)
class FittedBaseline:
    """A fitted estimator and the column order that maps it to `SCORED_CLASSES`."""

    model: Any
    order: tuple[int, ...]


def _inputs(
    beats: BeatTable, index: NDArray[np.int64], rr_scaled: NDArray[np.float64]
) -> NDArray[np.float64]:
    # The baseline sees the scaled RR inputs only (C2).
    return rr_scaled


def _fit(
    x: NDArray[np.float64],
    y: NDArray[np.str_],
    class_weight: Mapping[str, float],
    params: Mapping[str, Any],
) -> FittedBaseline:
    missing = sorted(set(SCORED_CLASSES) - set(y.tolist()))
    if missing:
        raise ValueError(f"classes {missing} have no training beats")
    model = LogisticRegression(
        solver="lbfgs",
        C=float(params["C"]),
        class_weight=dict(class_weight),
        max_iter=BASELINE_MAX_ITER,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(x, y)
    classes = [str(c) for c in model.classes_]
    return FittedBaseline(model, tuple(classes.index(c) for c in SCORED_CLASSES))


def _logits(fitted: FittedBaseline, x: NDArray[np.float64]) -> NDArray[np.float64]:
    # scikit-learn orders columns by its sorted classes_ (F, N, S, V).
    scores = np.asarray(fitted.model.decision_function(x), dtype=np.float64)
    return scores[:, list(fitted.order)]


def estimator(fitted: FittedBaseline) -> Any:
    """The fitted scikit-learn estimator."""
    return fitted.model


def coefficients(
    fitted: FittedBaseline,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Coefficients `(4, 6)` and intercepts `(4,)` in `SCORED_CLASSES` order."""
    order = list(fitted.order)
    coef = np.asarray(fitted.model.coef_, dtype=np.float64)[order]
    intercept = np.asarray(fitted.model.intercept_, dtype=np.float64)[order]
    return coef, intercept


BASELINE = ModelSpec(
    name="baseline",
    inputs=_inputs,
    fit=_fit,
    logits=_logits,
    config={"solver": "lbfgs", "max_iter": BASELINE_MAX_ITER, "dtype": "float64"},
)
