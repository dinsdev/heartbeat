"""Synthetic prepared DS1 records for the demo-data tests."""

from pathlib import Path

import numpy as np

from heartbeat.data.npz import PreparedRecord, save_prepared
from heartbeat.signal.rr import rr_features


def synthetic_record(record: str, classes: str, seed: int) -> PreparedRecord:
    """A record with a spike per beat every 0.8 s, V beats early and wider."""
    rng = np.random.default_rng(seed)
    n = len(classes)
    steps = np.where(np.array(list(classes)) == "V", 200, 288)
    beat_sample = (400 + np.concatenate([[0], np.cumsum(steps[1:])])).astype(np.int64)
    trace = rng.normal(0, 8, beat_sample[-1] + 400)
    for sample, cls in zip(beat_sample.tolist(), classes, strict=True):
        width = 18 if cls == "V" else 6
        span = np.arange(-3 * width, 3 * width)
        trace[sample + span] += 220 * np.exp(-((span / width) ** 2))
    kept = np.ones(n, dtype=np.bool_)
    kept[[0, -1]] = False
    return PreparedRecord(
        record_id=record,
        subject_id=record,
        trace_adu=np.round(trace).astype(np.int16),
        beat_sample=beat_sample,
        beat_symbol=np.array(list(classes)),
        beat_class=np.array(list(classes)),
        kept=kept,
        rr_s=rr_features(beat_sample),
    )


# 101: no irregular beats; 223: 26 S and 26 V from beat 30 on (past 20 s),
# enough for D4's default rule, and one Q.
CLASSES = {
    "101": "N" * 40,
    "223": "N" * 30 + "SVN" * 26 + "Q" + "N" * 5,
}


def write_prepared(folder: Path) -> Path:
    """Write the CLASSES records as prepared files into `folder`."""
    for seed, (record, classes) in enumerate(CLASSES.items()):
        save_prepared(synthetic_record(record, classes, seed), folder / f"{record}.npz")
    return folder
