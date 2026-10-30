"""Beat windows and their floored z-score (B3 and its amendment; DATA-06)."""

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import (
    WINDOW_AFTER_SAMPLES,
    WINDOW_BEFORE_SAMPLES,
    WINDOW_SAMPLES,
    ZSCORE_STD_FLOOR_ADU,
)

_OFFSETS = np.arange(-WINDOW_BEFORE_SAMPLES, WINDOW_AFTER_SAMPLES, dtype=np.int64)


class WindowRangeError(ValueError):
    """A beat's window reaches past the start or end of the trace."""


def window_bounds(sample: int) -> tuple[int, int]:
    """Return the half-open sample range `[start, stop)` of a beat's window."""
    return sample - WINDOW_BEFORE_SAMPLES, sample + WINDOW_AFTER_SAMPLES


def extract_windows(
    trace_adu: NDArray[np.int16], beat_sample: NDArray[np.int64]
) -> NDArray[np.int16]:
    """Cut one window per beat, with no realignment (R7).

    Args:
        trace_adu: The canonical trace, shape `(n_samples,)`.
        beat_sample: Annotation samples, shape `(n_beats,)`.

    Returns:
        Windows of shape `(n_beats, 256)`; the annotation sample is index 96.

    Raises:
        WindowRangeError: Naming the first beat whose window leaves the trace.
    """
    assert trace_adu.dtype == np.int16, trace_adu.dtype
    assert trace_adu.ndim == 1, trace_adu.shape
    assert beat_sample.ndim == 1, beat_sample.shape
    n_samples = trace_adu.size
    for index, sample in enumerate(beat_sample.tolist()):
        start, stop = window_bounds(sample)
        if start < 0 or stop > n_samples:
            raise WindowRangeError(
                f"beat {index} at sample {sample}: window [{start}, {stop}) "
                f"leaves the trace of {n_samples} samples"
            )
    windows: NDArray[np.int16] = trace_adu[beat_sample[:, np.newaxis] + _OFFSETS]
    assert windows.shape == (beat_sample.size, WINDOW_SAMPLES)
    return windows


def window_std_adu(windows_adu: NDArray[np.int16]) -> NDArray[np.float64]:
    """Population standard deviation of each window in int16 units, `(n_beats,)`."""
    std: NDArray[np.float64] = windows_adu.astype(np.float64).std(axis=1)
    return std


def zscore_windows(windows_adu: NDArray[np.int16]) -> NDArray[np.float64]:
    """Z-score each window as `(x - mean) / max(std, 2)` (DATA-06, R51).

    Args:
        windows_adu: Windows of shape `(n_beats, 256)`.

    Returns:
        Float64 windows of the same shape. A flat window becomes all zeros.
    """
    assert windows_adu.ndim == 2, windows_adu.shape
    assert windows_adu.shape[1] == WINDOW_SAMPLES, windows_adu.shape
    x = windows_adu.astype(np.float64)
    mean = x.mean(axis=1, keepdims=True)
    std = x.std(axis=1, keepdims=True)
    z: NDArray[np.float64] = (x - mean) / np.maximum(std, ZSCORE_STD_FLOOR_ADU)
    return z
