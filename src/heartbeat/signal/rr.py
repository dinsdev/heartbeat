"""The six RR features per beat (B3; DATA-07 as settled on 2026-10-29).

With every annotated beat k (Q included) at sample s_k and RR_k the interval in
seconds ending at beat k, beat i (1 <= i <= n - 2) has pre-RR RR_i, post-RR
RR_(i+1), a local average over RR_(i-9) to RR_i, and a long average over every
RR_k (k <= i) whose ending beat lies at most 108,000 samples before beat i.
Only post-RR looks ahead (R8).
"""

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import (
    FS_HZ,
    RR_FEATURE_NAMES,
    RR_LOCAL_INTERVALS,
    RR_LONG_WINDOW_SAMPLES,
)


def rr_features(beat_sample: NDArray[np.int64]) -> NDArray[np.float64]:
    """Compute the RR features of beats 1 to n - 2.

    Args:
        beat_sample: Samples of every annotated beat in a record, strictly
            increasing, shape `(n_beats,)`.

    Returns:
        Shape `(n_beats - 2, 6)`, columns in `RR_FEATURE_NAMES` order; row r
        is beat r + 1.

    Raises:
        ValueError: For fewer than 3 beats or samples that are not increasing.
    """
    assert beat_sample.ndim == 1, beat_sample.shape
    n = beat_sample.size
    if n < 3:
        raise ValueError(f"RR features need at least 3 beats, got {n}")
    steps = np.diff(beat_sample)
    if np.any(steps <= 0):
        first = int(np.argmax(steps <= 0)) + 1
        raise ValueError(f"beat samples must be strictly increasing (beat {first})")

    # rr_s[k - 1] is RR_k, the interval ending at beat k.
    rr_s = steps.astype(np.float64) / FS_HZ
    out = np.empty((n - 2, len(RR_FEATURE_NAMES)), dtype=np.float64)
    for i in range(1, n - 1):
        pre_s = rr_s[i - 1]
        post_s = rr_s[i]
        first_local = max(1, i - RR_LOCAL_INTERVALS + 1)
        local_s = rr_s[first_local - 1 : i].mean()
        # First k >= 1 with s_i - s_k <= 108,000, so s_k >= s_i - 108,000.
        first_long = max(
            1,
            int(
                np.searchsorted(
                    beat_sample, beat_sample[i] - RR_LONG_WINDOW_SAMPLES, side="left"
                )
            ),
        )
        long_s = rr_s[first_long - 1 : i].mean()
        out[i - 1] = (pre_s, post_s, local_s, long_s, pre_s / local_s, post_s / pre_s)
    return out
