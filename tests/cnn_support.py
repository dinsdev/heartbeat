"""Synthetic traces for the CNN tests: windows cut from them, no record read."""

import numpy as np
from cv_support import synthetic_beats
from numpy.typing import NDArray

from heartbeat.constants import WINDOW_AFTER_SAMPLES
from heartbeat.data.loader import BeatTable
from heartbeat.signal.windows import extract_windows

MARGIN_SAMPLES = 200
CLASS_BUMP = {"N": 0, "S": 40, "V": -60, "F": 20}


def beats_with_traces(
    n_subjects: int = 10, per_subject: int = 160, seed: int = 0
) -> tuple[BeatTable, dict[str, NDArray[np.int16]]]:
    """`synthetic_beats` with one int16 trace per record and its real windows.

    Each beat's class leaves a small bump in its window, so a CNN has
    something to learn; the noise keeps it from being separable.
    """
    base = synthetic_beats(n_subjects, per_subject, seed)
    # Move every beat clear of the trace start, shift included.
    beats = BeatTable(
        base.record_id,
        base.subject_id,
        base.sample + MARGIN_SAMPLES,
        base.beat_class,
        base.window_adu,
        base.rr_s,
    )
    rng = np.random.default_rng(seed + 1)
    length = int(beats.sample.max()) + WINDOW_AFTER_SAMPLES + 50
    traces: dict[str, NDArray[np.int16]] = {}
    for record in sorted(set(beats.record_id.tolist())):
        trace = rng.normal(0.0, 30.0, length)
        rows = np.flatnonzero(beats.record_id == record)
        for row in rows.tolist():
            s = int(beats.sample[row])
            trace[s - 5 : s + 5] += 200 + CLASS_BUMP[str(beats.beat_class[row])]
        traces[record] = np.round(trace).astype(np.int16)
    windows = np.concatenate(
        [
            extract_windows(traces[r], beats.sample[beats.record_id == r])
            for r in dict.fromkeys(beats.record_id.tolist())
        ]
    )
    return (
        BeatTable(
            beats.record_id,
            beats.subject_id,
            beats.sample,
            beats.beat_class,
            windows,
            beats.rr_s,
        ),
        traces,
    )
