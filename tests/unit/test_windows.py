"""DATA-06: window cutting (R7) and the floored z-score (R51)."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays
from numpy.typing import NDArray

from heartbeat.constants import WINDOW_SAMPLES
from heartbeat.signal.windows import (
    WindowRangeError,
    extract_windows,
    window_bounds,
    window_std_adu,
    zscore_windows,
)


def _ramp(n: int) -> NDArray[np.int16]:
    return (np.arange(n) % 30000).astype(np.int16)


@pytest.mark.rule("R7")
def test_window_bounds_are_96_before_and_160_after() -> None:
    assert window_bounds(1000) == (904, 1160)


@pytest.mark.rule("R7")
def test_annotation_sample_sits_at_index_96() -> None:
    trace = _ramp(5000)
    beats = np.array([500, 1000, 4000], dtype=np.int64)
    windows = extract_windows(trace, beats)
    assert windows.shape == (3, WINDOW_SAMPLES)
    assert windows.dtype == np.int16
    for row, s in zip(windows, beats, strict=True):
        assert row[96] == trace[s]
        assert row[0] == trace[s - 96]
        assert row[-1] == trace[s + 159]


@pytest.mark.rule("R7")
def test_first_and_last_possible_beats_are_accepted() -> None:
    trace = _ramp(1000)
    windows = extract_windows(trace, np.array([96, 1000 - 160], dtype=np.int64))
    assert windows.shape == (2, WINDOW_SAMPLES)


@pytest.mark.rule("R7")
@pytest.mark.parametrize("sample", [95, 0, 1000 - 159, 999])
def test_window_outside_the_record_raises_naming_the_beat(sample: int) -> None:
    trace = _ramp(1000)
    beats = np.array([500, sample], dtype=np.int64)
    with pytest.raises(WindowRangeError, match=rf"beat 1 .*sample {sample}"):
        extract_windows(trace, beats)


@pytest.mark.rule("R51")
def test_constant_window_gives_zeros() -> None:
    windows = np.full((2, WINDOW_SAMPLES), 123, dtype=np.int16)
    z = zscore_windows(windows)
    assert z.dtype == np.float64
    assert np.array_equal(z, np.zeros((2, WINDOW_SAMPLES)))


@pytest.mark.rule("R51")
@given(arrays(np.int16, (3, WINDOW_SAMPLES)))
def test_any_int16_window_gives_finite_values(windows: NDArray[np.int16]) -> None:
    assert np.all(np.isfinite(zscore_windows(windows)))


@pytest.mark.rule("R51")
@given(arrays(np.int16, (1, WINDOW_SAMPLES), elements=st.integers(-2000, 2000)))
def test_window_above_the_floor_is_a_plain_z_score(
    windows: NDArray[np.int16],
) -> None:
    x = windows.astype(np.float64)
    std = x.std(axis=1, keepdims=True)
    if std[0, 0] <= 2.0:
        return
    expected = (x - x.mean(axis=1, keepdims=True)) / std
    np.testing.assert_allclose(zscore_windows(windows), expected, rtol=0, atol=1e-12)


@pytest.mark.rule("R51")
def test_window_below_the_floor_divides_by_two() -> None:
    row = np.zeros(WINDOW_SAMPLES, dtype=np.int16)
    row[0] = 1  # std is tiny, well under 2 units
    z = zscore_windows(row[np.newaxis, :])
    x = row.astype(np.float64)
    np.testing.assert_allclose(z[0], (x - x.mean()) / 2.0, rtol=0, atol=1e-15)


def test_window_std_is_the_population_one() -> None:
    windows = np.tile(np.arange(WINDOW_SAMPLES, dtype=np.int16), (2, 1))
    expected = np.arange(WINDOW_SAMPLES, dtype=np.float64).std(ddof=0)
    np.testing.assert_allclose(window_std_adu(windows), [expected, expected])
