"""C2, C3: the RR model inputs and the fold-fitted scaler."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays
from numpy.typing import NDArray
from sklearn.preprocessing import StandardScaler

from heartbeat.models.inputs import (
    RRScaler,
    apply_rr_scaler,
    fit_rr_scaler,
    rr_model_inputs,
)


def _rr(n: int, seed: int) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    pre = rng.uniform(0.4, 1.4, n)
    post = rng.uniform(0.4, 1.4, n)
    local = rng.uniform(0.6, 1.1, n)
    long = rng.uniform(0.7, 1.0, n)
    return np.column_stack([pre, post, local, long, pre / local, post / pre])


def test_inputs_keep_the_intervals_and_log_the_two_ratios() -> None:
    rr_s = _rr(50, 1)
    x = rr_model_inputs(rr_s)
    assert x.shape == (50, 6)
    assert x.dtype == np.float64
    np.testing.assert_array_equal(x[:, :4], rr_s[:, :4])
    np.testing.assert_allclose(x[:, 4], np.log(rr_s[:, 4]), rtol=0, atol=1e-15)
    np.testing.assert_allclose(x[:, 5], np.log(rr_s[:, 5]), rtol=0, atol=1e-15)


@pytest.mark.parametrize("column", [4, 5])
@pytest.mark.parametrize("bad", [0.0, -0.5])
def test_a_non_positive_ratio_raises(column: int, bad: float) -> None:
    rr_s = _rr(5, 2)
    rr_s[3, column] = bad
    with pytest.raises(ValueError, match="ratio"):
        rr_model_inputs(rr_s)


@given(
    st.integers(2, 40).flatmap(
        lambda n: arrays(
            np.float64,
            (n, 6),
            elements=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False),
        )
    )
)
def test_scaler_equals_standard_scaler(x: NDArray[np.float64]) -> None:
    if np.any(x.std(axis=0) <= 1e-12 * np.maximum(1.0, np.abs(x.mean(axis=0)))):
        with pytest.raises(ValueError, match="standard deviation"):
            fit_rr_scaler(x)
        return
    scaler = fit_rr_scaler(x)
    reference = StandardScaler().fit(x)
    np.testing.assert_allclose(scaler.mean, reference.mean_, rtol=1e-12, atol=1e-9)
    np.testing.assert_allclose(scaler.std, reference.scale_, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(
        apply_rr_scaler(scaler, x), reference.transform(x), rtol=1e-9, atol=1e-9
    )


def test_scaler_uses_the_population_standard_deviation() -> None:
    x = np.array([[1.0] * 6, [3.0] * 6])
    scaler = fit_rr_scaler(x)
    np.testing.assert_array_equal(scaler.std, np.ones(6))
    np.testing.assert_array_equal(scaler.mean, np.full(6, 2.0))


def test_a_constant_column_raises() -> None:
    x = _rr(10, 3)
    x[:, 2] = 0.8
    with pytest.raises(ValueError, match="standard deviation"):
        fit_rr_scaler(x)


def test_a_column_constant_up_to_rounding_raises() -> None:
    # 16.1999439 repeated: the float mean is off by rounding, so std is about
    # 1e-15, not 0.
    x = _rr(12, 6)
    x[:, 1] = 16.1999439
    with pytest.raises(ValueError, match="standard deviation"):
        fit_rr_scaler(x)


def test_apply_does_not_refit() -> None:
    train = _rr(30, 4)
    scaler = fit_rr_scaler(train)
    validation = _rr(5, 5) * 100
    applied = apply_rr_scaler(scaler, validation)
    np.testing.assert_allclose(applied, (validation - scaler.mean) / scaler.std)
    assert isinstance(scaler, RRScaler)
