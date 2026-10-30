"""DATA-05: the bandpass (R5) and the int16 rounding (R6)."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays
from numpy.typing import NDArray

from heartbeat.constants import ADU_PER_MV, FS_HZ
from heartbeat.signal.filter import TraceRangeError, bandpass_mv, to_adu

DURATION_S = 60
EDGE_S = 10


def _sine(freq_hz: float, phase_rad: float = 0.0) -> NDArray[np.float64]:
    t_s = np.arange(DURATION_S * FS_HZ) / FS_HZ
    return np.sin(2 * np.pi * freq_hz * t_s + phase_rad)


def _gain_db(freq_hz: float) -> float:
    """Gain of the filter at one frequency, measured away from the edges."""
    x = _sine(freq_hz)
    y = bandpass_mv(x)
    middle = slice(EDGE_S * FS_HZ, (DURATION_S - EDGE_S) * FS_HZ)
    rms_in = np.sqrt(np.mean(x[middle] ** 2))
    rms_out = np.sqrt(np.mean(y[middle] ** 2))
    return float(20 * np.log10(rms_out / rms_in))


@pytest.mark.rule("R5")
@pytest.mark.parametrize("freq_hz", [2.0, 5.0, 10.0, 15.0, 20.0, 25.0])
def test_passband_is_flat_from_2_to_25_hz(freq_hz: float) -> None:
    assert abs(_gain_db(freq_hz)) <= 0.2


@pytest.mark.rule("R5")
@pytest.mark.parametrize("freq_hz", [0.5, 40.0])
def test_band_edges_are_at_minus_6_db(freq_hz: float) -> None:
    # Zero-phase filtering squares the magnitude, so -3 dB becomes -6 dB.
    assert abs(_gain_db(freq_hz) - -6.0) <= 0.2


@pytest.mark.rule("R5")
def test_mains_at_60_hz_is_down_30_db() -> None:
    assert _gain_db(60.0) <= -30.0


@pytest.mark.rule("R5")
def test_baseline_wander_at_0_1_hz_is_down_40_db() -> None:
    assert _gain_db(0.1) <= -40.0


@pytest.mark.rule("R5")
def test_filter_is_zero_phase() -> None:
    x = _sine(10.0)
    y = bandpass_mv(x)
    middle = slice(EDGE_S * FS_HZ, (DURATION_S - EDGE_S) * FS_HZ)
    xm, ym = x[middle], y[middle]
    max_lag = 20
    lags = range(-max_lag, max_lag + 1)
    corr = [float(np.dot(xm, np.roll(ym, lag))) for lag in lags]
    assert list(lags)[int(np.argmax(corr))] == 0
    # Phase of the 10 Hz component in input and output, from a single-bin DFT.
    n = xm.size
    basis = np.exp(-2j * np.pi * 10.0 * np.arange(n) / FS_HZ)
    phase_diff = np.angle(np.dot(ym, basis)) - np.angle(np.dot(xm, basis))
    assert abs(phase_diff) < 1e-3


def test_bandpass_keeps_shape_and_dtype() -> None:
    x = _sine(10.0)
    y = bandpass_mv(x)
    assert y.shape == x.shape
    assert y.dtype == np.float64


@pytest.mark.rule("R6")
@given(
    arrays(
        np.float64,
        st.integers(1, 200),
        elements=st.floats(-150.0, 150.0, allow_nan=False, allow_infinity=False),
    )
)
def test_int16_rounding_error_is_at_most_a_quarter_hundredth_mv(
    x_mv: NDArray[np.float64],
) -> None:
    adu = to_adu(x_mv)
    assert adu.dtype == np.int16
    assert np.all(np.abs(adu / ADU_PER_MV - x_mv) <= 0.0025)


@pytest.mark.rule("R6")
@pytest.mark.parametrize("value_mv", [163.84, -163.845, 1000.0, -1000.0])
def test_values_outside_int16_raise(value_mv: float) -> None:
    with pytest.raises(TraceRangeError):
        to_adu(np.array([0.0, value_mv]))


@pytest.mark.rule("R6")
def test_int16_extremes_are_kept() -> None:
    adu = to_adu(np.array([32767 / ADU_PER_MV, -32768 / ADU_PER_MV]))
    assert adu.tolist() == [32767, -32768]


@pytest.mark.rule("R6")
def test_exact_halves_round_to_even() -> None:
    # 0.0025 mV is 0.5 units, 0.0075 mV is 1.5 units, and so on.
    x_mv = np.array([0.5, 1.5, 2.5, -0.5, -1.5, -2.5]) / ADU_PER_MV
    assert to_adu(x_mv).tolist() == [0, 2, 2, 0, -2, -2]


def test_non_finite_values_raise() -> None:
    with pytest.raises(TraceRangeError):
        to_adu(np.array([0.0, np.nan]))
