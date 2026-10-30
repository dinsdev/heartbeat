"""C4, EVAL-11, EVAL-12: labels, logit adjustment, temperature and calibration metrics.

R20: calibration never changes a label; logit adjustment; equal-mass ECE.
"""

import inspect

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays
from numpy.typing import NDArray
from sklearn.metrics import brier_score_loss, log_loss

from heartbeat.constants import SCORED_CLASSES, TEMPERATURE_BOUNDS
from heartbeat.evaluate.calibration import (
    TemperatureAtBoundError,
    adjust_logits,
    brier,
    calibrated_probs,
    ece_equal_mass,
    fit_temperature,
    log_loss_from_logits,
    predict_labels,
    reliability_data,
)

# scikit-learn reads probability columns in sorted label order (F, N, S, V).
SORTED = np.argsort(np.array(SCORED_CLASSES))

finite = st.floats(min_value=-20, max_value=20, allow_nan=False)
logit_arrays = st.integers(1, 30).flatmap(
    lambda n: arrays(np.float64, (n, 4), elements=finite)
)
weights = st.lists(st.floats(min_value=0.05, max_value=50), min_size=4, max_size=4)
temperatures = st.floats(min_value=0.05, max_value=20)


@pytest.mark.rule("R20")
def test_predict_labels_is_the_argmax_of_the_raw_logits() -> None:
    logits = np.array([[3.0, 1.0, 0.0, -1.0], [0.0, 0.5, 2.0, 1.0], [0, 0, 0, 9.0]])
    np.testing.assert_array_equal(predict_labels(logits), ["N", "V", "F"])


@pytest.mark.rule("R20")
def test_predict_labels_takes_only_the_logits() -> None:
    # Nothing else goes in, so no temperature or adjustment can reach a label.
    assert list(inspect.signature(predict_labels).parameters) == ["logits"]


@pytest.mark.rule("R20")
@given(logit_arrays, weights, temperatures)
def test_calibration_never_changes_a_label(
    logits: NDArray[np.float64], w: list[float], temperature: float
) -> None:
    before = predict_labels(logits)
    raw = logits.copy()
    adjusted = adjust_logits(logits, dict(zip(SCORED_CLASSES, w, strict=True)))
    probs = calibrated_probs(adjusted, temperature)
    np.testing.assert_array_equal(logits, raw)
    np.testing.assert_array_equal(predict_labels(logits), before)
    # Probabilities may rank classes differently from the label (next test);
    # they are still a distribution.
    assert np.all(np.isfinite(probs))
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-12)


@pytest.mark.rule("R20")
def test_calibrated_argmax_may_differ_from_the_label() -> None:
    # A heavily weighted S pushed the raw S logit up; the adjustment removes it.
    logits = np.array([[1.0, 1.5, 0.0, 0.0]])
    adjusted = adjust_logits(logits, {"N": 0.25, "S": 10.0, "V": 1.0, "F": 1.0})
    assert predict_labels(logits).tolist() == ["S"]
    assert SCORED_CLASSES[int(np.argmax(calibrated_probs(adjusted, 1.0)))] == "N"


@pytest.mark.rule("R20")
def test_logit_adjustment_subtracts_log_weights() -> None:
    logits = np.array([[1.0, 2.0, 3.0, 4.0], [0.0, 0.0, 0.0, 0.0]])
    w = {"N": 0.5, "S": 2.0, "V": 4.0, "F": 1.0}
    expected = logits - np.log([0.5, 2.0, 4.0, 1.0])
    np.testing.assert_allclose(adjust_logits(logits, w), expected, rtol=0, atol=1e-15)


@pytest.mark.rule("R20")
def test_logit_adjustment_uses_each_rows_own_weights() -> None:
    # Two folds with different training weights: each row uses its own.
    logits = np.ones((3, 4))
    per_row = np.array(
        [[0.5, 2.0, 4.0, 1.0], [0.5, 2.0, 4.0, 1.0], [1.0, 8.0, 3.0, 20.0]]
    )
    np.testing.assert_allclose(
        adjust_logits(logits, per_row), logits - np.log(per_row), atol=1e-15
    )
    with pytest.raises(ValueError, match="shape"):
        adjust_logits(logits, per_row[:2])


def _exact_set(true_temperature: float) -> tuple[NDArray[np.float64], NDArray[np.str_]]:
    """Logits whose labels follow softmax(logits / T) exactly, in whole beats."""
    patterns = [
        ([0.5, 0.25, 0.125, 0.125], [4, 2, 1, 1]),
        ([0.125, 0.625, 0.125, 0.125], [1, 5, 1, 1]),
        ([0.25, 0.25, 0.375, 0.125], [2, 2, 3, 1]),
        ([0.375, 0.125, 0.125, 0.375], [3, 1, 1, 3]),
    ]
    rows: list[NDArray[np.float64]] = []
    labels: list[str] = []
    for probs, counts in patterns:
        z = np.log(np.array(probs)) * true_temperature
        for cls, n in zip(SCORED_CLASSES, counts, strict=True):
            rows += [z] * n
            labels += [cls] * n
    return np.array(rows), np.array(labels)


@pytest.mark.rule("R20")
@pytest.mark.parametrize("true_temperature", [0.4, 1.0, 2.5, 7.0])
def test_fit_temperature_recovers_a_known_temperature(true_temperature: float) -> None:
    logits, y_true = _exact_set(true_temperature)
    assert fit_temperature(logits, y_true) == pytest.approx(true_temperature, abs=1e-3)


@pytest.mark.rule("R20")
@pytest.mark.parametrize(
    ("margin", "bound"),
    [
        # Always right by a small margin: log loss falls as T falls, all the
        # way to the lower bound (a small margin keeps the loss above float
        # rounding there).
        (0.1, "lower"),
        # Always wrong: log loss falls toward log 4 as T grows.
        (-1.0, "upper"),
    ],
)
def test_fit_temperature_at_a_bound_raises(margin: float, bound: str) -> None:
    logits = margin * np.eye(4)
    y_true = np.array(list(SCORED_CLASSES))
    with pytest.raises(TemperatureAtBoundError, match=f"{bound} bound"):
        fit_temperature(logits, y_true)
    assert TEMPERATURE_BOUNDS == (0.05, 20.0)


@pytest.mark.rule("R20")
@pytest.mark.parametrize("n", [10, 11, 19, 95, 1003])
def test_equal_mass_bins_differ_by_at_most_one_beat(n: int) -> None:
    rng = np.random.default_rng(n)
    prob = rng.random(n)
    is_k = rng.random(n) < prob
    bins = reliability_data(prob, is_k)
    sizes = [b["count"] for b in bins]
    assert len(sizes) == 10
    assert sum(sizes) == n
    assert max(sizes) - min(sizes) <= 1


@pytest.mark.rule("R20")
def test_ece_on_a_hand_case() -> None:
    # Two bins of two beats: probabilities (0.1, 0.2) with outcomes (0, 1),
    # then (0.8, 0.9) with outcomes (1, 1).
    prob = np.array([0.9, 0.1, 0.8, 0.2])
    is_k = np.array([True, False, True, True])
    # Bin 1: |0.15 - 0.5| = 0.35; bin 2: |0.85 - 1.0| = 0.15; ECE = 0.25.
    assert ece_equal_mass(prob, is_k, n_bins=2) == pytest.approx(0.25)
    bins = reliability_data(prob, is_k, n_bins=2)
    assert bins[0] == {
        "count": 2,
        "mean_probability": pytest.approx(0.15),
        "observed_rate": 0.5,
        "lowest": 0.1,
        "highest": 0.2,
    }


@pytest.mark.rule("R20")
def test_ties_split_by_original_order() -> None:
    prob = np.full(4, 0.5)
    is_k = np.array([True, True, False, False])
    # Stable sort keeps the order: bin 1 is beats 0 and 1 (rate 1), bin 2 is
    # beats 2 and 3 (rate 0). ECE = 0.5 * 0.5 + 0.5 * 0.5 = 0.5.
    assert ece_equal_mass(prob, is_k, n_bins=2) == pytest.approx(0.5)
    bins = reliability_data(prob, is_k, n_bins=2)
    assert [b["observed_rate"] for b in bins] == [1.0, 0.0]


@pytest.mark.rule("R20")
def test_ece_is_zero_when_rates_match_in_every_bin() -> None:
    prob = np.array([0.0, 0.0, 1.0, 1.0])
    is_k = np.array([False, False, True, True])
    assert ece_equal_mass(prob, is_k, n_bins=2) == 0.0


def _random_set(seed: int) -> tuple[NDArray[np.float64], NDArray[np.str_]]:
    rng = np.random.default_rng(seed)
    logits = rng.normal(0, 2, size=(300, 4))
    y_true = np.array(SCORED_CLASSES)[rng.integers(0, 4, size=300)]
    return logits, y_true


@pytest.mark.parametrize("temperature", [0.5, 1.0, 3.0])
def test_log_loss_equals_sklearn(temperature: float) -> None:
    logits, y_true = _random_set(1)
    probs = calibrated_probs(logits, temperature)
    expected = log_loss(y_true, probs[:, SORTED], labels=sorted(SCORED_CLASSES))
    ours = log_loss_from_logits(logits, temperature, y_true)
    assert ours == pytest.approx(expected, rel=1e-9)


def test_brier_on_a_hand_case() -> None:
    probs = np.array([[0.7, 0.1, 0.1, 0.1], [0.25, 0.25, 0.25, 0.25]])
    y_true = np.array(["N", "S"])
    # Beat 1: 0.09 + 0.01 * 3 = 0.12; beat 2: 0.5625 + 3 * 0.0625 = 0.75.
    assert brier(probs, y_true) == pytest.approx((0.12 + 0.75) / 2)


def test_brier_equals_sklearn() -> None:
    logits, y_true = _random_set(2)
    probs = calibrated_probs(logits, 1.3)
    expected = brier_score_loss(
        y_true, probs[:, SORTED], labels=sorted(SCORED_CLASSES), scale_by_half=False
    )
    assert brier(probs, y_true) == pytest.approx(expected, rel=1e-12)


def test_calibrated_probs_rows_sum_to_one() -> None:
    logits, _ = _random_set(3)
    probs = calibrated_probs(logits, 0.7)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-12)
    assert probs.min() > 0
