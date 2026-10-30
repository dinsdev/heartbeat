"""EVAL-04 on real DS1: the loader returns DS1's scored beats and refuses DS2 (R15)."""

from pathlib import Path

import numpy as np
import pytest

from heartbeat.constants import RR_FEATURE_NAMES, WINDOW_SAMPLES
from heartbeat.data.loader import SealedRecordError, load_ds1
from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import PrepareReport


@pytest.mark.rule("R15")
def test_load_ds1_returns_22_records_of_scored_beats(
    prepared_ds1: tuple[Path, PrepareReport],
    splits: Splits,
    subjects: dict[str, str],
) -> None:
    folder, _ = prepared_ds1
    beats = load_ds1(folder, splits, subjects)
    assert sorted(set(beats.record_id.tolist())) == sorted(splits.ds1)
    assert len(set(beats.subject_id.tolist())) == 22
    assert set(beats.beat_class.tolist()) == {"N", "S", "V", "F"}
    n = beats.sample.size
    assert beats.sample.dtype == np.int64
    assert beats.window_adu.dtype == np.int16
    assert beats.window_adu.shape == (n, WINDOW_SAMPLES)
    assert beats.rr_s.dtype == np.float64
    assert beats.rr_s.shape == (n, len(RR_FEATURE_NAMES))
    assert np.all(np.isfinite(beats.rr_s))
    assert np.all(beats.rr_s[:, :4] > 0)


@pytest.mark.rule("R15")
def test_load_ds1_refuses_record_100(
    prepared_ds1: tuple[Path, PrepareReport],
    splits: Splits,
    subjects: dict[str, str],
) -> None:
    folder, _ = prepared_ds1
    with pytest.raises(SealedRecordError, match="100"):
        load_ds1(folder, splits, subjects, records=["100"])
