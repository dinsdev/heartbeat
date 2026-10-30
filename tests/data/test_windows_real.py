"""DATA-06, DATA-08 on real DS1: every kept beat has a full window (R7)."""

from pathlib import Path

import numpy as np
import pytest

from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import PrepareReport, load_prepared
from heartbeat.signal.windows import window_bounds


@pytest.mark.rule("R7")
def test_every_kept_ds1_beat_has_a_full_window(
    prepared_ds1: tuple[Path, PrepareReport], splits: Splits
) -> None:
    folder, report = prepared_ds1
    assert report.records == splits.ds1
    for record in splits.ds1:
        prepared = load_prepared(folder / f"{record}.npz")
        n_samples = prepared.trace_adu.size
        for sample in prepared.beat_sample[prepared.kept].tolist():
            start, stop = window_bounds(sample)
            assert start >= 0, (record, sample)
            assert stop <= n_samples, (record, sample)


def test_floor_hits_are_within_the_limit(
    prepared_ds1: tuple[Path, PrepareReport],
) -> None:
    _, report = prepared_ds1
    assert report.total_hits <= 5
    assert set(report.floor_hits) == set(report.records)
    assert all(np.isfinite(h.min_std_adu) for h in report.floor_hits.values())
