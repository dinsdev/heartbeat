"""The canonical trace: bandpass in millivolts, then int16 units (B3, D4; DATA-05)."""

from functools import cache

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from heartbeat.constants import (
    ADU_PER_MV,
    BANDPASS_HIGH_HZ,
    BANDPASS_LOW_HZ,
    BANDPASS_ORDER,
    FS_HZ,
)

_INT16_MIN = int(np.iinfo(np.int16).min)
_INT16_MAX = int(np.iinfo(np.int16).max)


class TraceRangeError(ValueError):
    """A filtered value does not fit int16 at 200 units per mV, or is not finite."""


@cache
def _bandpass_sos() -> NDArray[np.float64]:
    sos: NDArray[np.float64] = signal.butter(
        BANDPASS_ORDER,
        [BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ],
        btype="bandpass",
        fs=FS_HZ,
        output="sos",
    )
    return sos


def bandpass_mv(x_mv: NDArray[np.float64]) -> NDArray[np.float64]:
    """Filter one record's lead with the zero-phase bandpass (Phase 2 settling 2).

    Args:
        x_mv: The lead in millivolts at 360 Hz, shape `(n_samples,)`.

    Returns:
        The filtered lead in millivolts, float64, shape `(n_samples,)`.
    """
    assert x_mv.ndim == 1, x_mv.shape
    y_mv: NDArray[np.float64] = signal.sosfiltfilt(
        _bandpass_sos(), x_mv.astype(np.float64, copy=False)
    )
    return y_mv


def to_adu(x_mv: NDArray[np.float64]) -> NDArray[np.int16]:
    """Round millivolts to int16 units, half to even (DATA-05).

    Args:
        x_mv: Values in millivolts, any shape.

    Returns:
        The values at 200 units per mV as int16, same shape.

    Raises:
        TraceRangeError: If a value is not finite or falls outside int16. The
            trace is never clipped.
    """
    if not np.all(np.isfinite(x_mv)):
        raise TraceRangeError("trace holds a non-finite value")
    adu = np.rint(x_mv * ADU_PER_MV)
    low, high = float(adu.min()), float(adu.max())
    if low < _INT16_MIN or high > _INT16_MAX:
        raise TraceRangeError(
            f"trace spans {low:.0f} to {high:.0f} units, outside int16 "
            f"({_INT16_MIN} to {_INT16_MAX})"
        )
    return adu.astype(np.int16)
