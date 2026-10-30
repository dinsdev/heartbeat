"""RR model inputs and the fold-fitted RR scaler (C2, C3; CONVENTIONS section 3).

The scaler has a fit step and an apply step: it is fitted on the training part
of each fold only. The standard deviation is the population one, as the
TypeScript parity code computes it (Phase 3 task plan, design call 2).
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import RR_FEATURE_NAMES

_RATIO_COLUMNS = (
    RR_FEATURE_NAMES.index("pre_over_local"),
    RR_FEATURE_NAMES.index("post_over_pre"),
)


# A column whose standard deviation is at most this times max(1, |mean|) is
# constant up to float rounding; scaling by it would blow the inputs up.
CONSTANT_RELATIVE_STD = 1e-12


@dataclass(frozen=True)
class RRScaler:
    """Per-column mean and population standard deviation, `(6,)` each."""

    mean: NDArray[np.float64]
    std: NDArray[np.float64]


def rr_model_inputs(rr_s: NDArray[np.float64]) -> NDArray[np.float64]:
    """The six RR inputs: four intervals in seconds, then the log of each ratio.

    Args:
        rr_s: RR features in `RR_FEATURE_NAMES` order, `(n, 6)`.

    Returns:
        A new float64 array, `(n, 6)`.

    Raises:
        ValueError: If a ratio is zero or negative (no log exists).
    """
    assert rr_s.shape[1:] == (len(RR_FEATURE_NAMES),), rr_s.shape
    x = np.array(rr_s, dtype=np.float64)
    for column in _RATIO_COLUMNS:
        bad = np.flatnonzero(x[:, column] <= 0)
        if bad.size:
            raise ValueError(
                f"ratio {RR_FEATURE_NAMES[column]} is not positive at row {bad[0]}"
            )
        x[:, column] = np.log(x[:, column])
    return x


def fit_rr_scaler(x_train: NDArray[np.float64]) -> RRScaler:
    """Fit the scaler on training rows, `(n, 6)`.

    Raises:
        ValueError: If a column's standard deviation is zero up to rounding.
    """
    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    flat = np.flatnonzero(std <= CONSTANT_RELATIVE_STD * np.maximum(1.0, np.abs(mean)))
    if flat.size:
        raise ValueError(f"column {int(flat[0])} has zero standard deviation")
    return RRScaler(mean=mean, std=std)


def apply_rr_scaler(scaler: RRScaler, x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Standardize rows with an already fitted scaler."""
    scaled: NDArray[np.float64] = (x - scaler.mean) / scaler.std
    return scaled
