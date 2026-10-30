"""The CNN's fixed augmentation (C3; MODEL-03, Phase 4 settling 4).

Training batches only: re-cut each window from the int16 trace at the beat
sample plus a uniform integer offset in [-5, 5], z-score it with the same
function and floor as inference, then add Gaussian noise of standard deviation
0.05 in z-units. Validation and every evaluation use `validation_windows`.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import NOISE_STD_Z, SHIFT_MAX_SAMPLES, WINDOW_SAMPLES
from heartbeat.data.loader import BeatTable
from heartbeat.signal.windows import extract_windows, zscore_windows


def draw_offsets(rng: np.random.Generator, n: int) -> NDArray[np.int64]:
    """Uniform integer offsets in [-5, 5], `(n,)`."""
    offsets: NDArray[np.int64] = rng.integers(
        -SHIFT_MAX_SAMPLES, SHIFT_MAX_SAMPLES + 1, size=n, dtype=np.int64
    )
    return offsets


def shifted_windows(
    traces: Mapping[str, NDArray[np.int16]],
    record: NDArray[np.str_],
    sample: NDArray[np.int64],
    offsets: NDArray[np.int64],
) -> NDArray[np.int16]:
    """Windows cut at `sample + offsets` from each beat's own trace, `(b, 256)`.

    Raises:
        WindowRangeError: If a shifted window leaves its record (settling 4:
            no clamping or padding).
    """
    windows = np.empty((sample.size, WINDOW_SAMPLES), dtype=np.int16)
    for name in np.unique(record).tolist():
        rows = np.flatnonzero(record == name)
        windows[rows] = extract_windows(traces[name], sample[rows] + offsets[rows])
    return windows


def augment_batch(
    traces: Mapping[str, NDArray[np.int16]],
    record: NDArray[np.str_],
    sample: NDArray[np.int64],
    rng_shift: np.random.Generator,
    rng_noise: np.random.Generator,
) -> NDArray[np.float32]:
    """One augmented training batch, `(b, 1, 256)` float32.

    Args:
        traces: Record to its canonical int16 trace.
        record: Each beat's record, `(b,)`.
        sample: Each beat's annotation sample, `(b,)`.
        rng_shift: The run's shift stream.
        rng_noise: The run's noise stream; fresh noise on every call.
    """
    offsets = draw_offsets(rng_shift, sample.size)
    z = zscore_windows(shifted_windows(traces, record, sample, offsets))
    noisy = z + rng_noise.normal(0.0, NOISE_STD_Z, size=z.shape)
    return noisy.astype(np.float32)[:, np.newaxis, :]


def validation_windows(beats: BeatTable) -> NDArray[np.float32]:
    """Unaugmented model windows, `(n, 1, 256)` float32 (the inference path)."""
    return zscore_windows(beats.window_adu).astype(np.float32)[:, np.newaxis, :]
