"""C2, MODEL-01: the multinomial logistic regression baseline as a ModelSpec."""

import warnings

import numpy as np
import pytest
from numpy.typing import NDArray
from sklearn.exceptions import ConvergenceWarning

from heartbeat.constants import SCORED_CLASSES
from heartbeat.models import baseline as baseline_module
from heartbeat.models.baseline import BASELINE

WEIGHTS = {"N": 1.0, "S": 1.0, "V": 1.0, "F": 1.0}


def _separable(seed: int) -> tuple[NDArray[np.float64], NDArray[np.str_]]:
    rng = np.random.default_rng(seed)
    y = np.array(SCORED_CLASSES)[rng.integers(0, 4, size=400)]
    centers = {"N": 0.0, "S": 4.0, "V": 8.0, "F": 12.0}
    x = rng.normal(0, 0.3, size=(400, 6))
    x[:, 0] += np.array([centers[c] for c in y])
    return x, y


def test_fit_and_logits_shapes() -> None:
    x, y = _separable(1)
    fitted = BASELINE.fit(x, y, WEIGHTS, {"C": 1.0})
    logits = BASELINE.logits(fitted, x)
    assert logits.shape == (400, 4)
    assert logits.dtype == np.float64
    assert np.mean(np.array(SCORED_CLASSES)[logits.argmax(axis=1)] == y) > 0.95


def test_logit_columns_follow_scored_classes() -> None:
    # Only S is separable (feature 0); N, V and F are noise. sklearn sorts its
    # classes (F, N, S, V), so a missing reorder would put S in column 2.
    rng = np.random.default_rng(2)
    y = np.array(SCORED_CLASSES)[rng.integers(0, 4, size=800)]
    x = rng.normal(0, 1, size=(800, 6))
    x[y == "S", 0] += 6.0
    fitted = BASELINE.fit(x, y, WEIGHTS, {"C": 1.0})
    logits = BASELINE.logits(fitted, x)
    s_column = SCORED_CLASSES.index("S")
    assert np.mean(logits[y == "S"].argmax(axis=1) == s_column) > 0.95
    assert np.mean(logits[y != "S"].argmax(axis=1) == s_column) < 0.05


def test_class_weights_reach_the_estimator() -> None:
    x, y = _separable(3)
    weights = {"N": 0.5, "S": 2.0, "V": 1.5, "F": 3.0}
    fitted = BASELINE.fit(x, y, weights, {"C": 1.0})
    assert baseline_module.estimator(fitted).class_weight == weights


def test_coefficients_follow_scored_classes() -> None:
    x, y = _separable(4)
    fitted = BASELINE.fit(x, y, WEIGHTS, {"C": 1.0})
    coef, intercept = baseline_module.coefficients(fitted)
    assert coef.shape == (4, 6)
    assert intercept.shape == (4,)
    np.testing.assert_allclose(
        x @ coef.T + intercept, BASELINE.logits(fitted, x), rtol=1e-10, atol=1e-10
    )


def test_a_convergence_warning_raises_even_when_warnings_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(baseline_module, "BASELINE_MAX_ITER", 1)
    x, y = _separable(5)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ConvergenceWarning):
            BASELINE.fit(x, y, WEIGHTS, {"C": 100.0})


def test_a_missing_class_raises() -> None:
    x, y = _separable(6)
    keep = y != "F"
    with pytest.raises(ValueError, match="F"):
        BASELINE.fit(x[keep], y[keep], WEIGHTS, {"C": 1.0})
