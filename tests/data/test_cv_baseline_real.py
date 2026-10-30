"""EVAL-07 on real DS1: the baseline CV over the committed folds (R21, layer L2).

DS1 only: the prepared folder holds DS1 alone and the loader refuses DS2.
"""

from pathlib import Path

import numpy as np

from heartbeat.data.folds import check_folds
from heartbeat.data.loader import load_ds1
from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import PrepareReport
from heartbeat.models.baseline import BASELINE
from heartbeat.paths import FOLDS_JSON, FOLDS_PIN
from heartbeat.train.cv import cross_validate


def test_baseline_cv_on_real_ds1_at_one_c(
    prepared_ds1: tuple[Path, PrepareReport],
    splits: Splits,
    subjects: dict[str, str],
) -> None:
    folder, _ = prepared_ds1
    beats = load_ds1(folder, splits, subjects)
    folds = check_folds(FOLDS_JSON, FOLDS_PIN, splits, subjects)
    result = cross_validate(BASELINE, beats, folds, {"C": 1.0})
    assert result.logits.shape == (beats.sample.size, 4)
    assert np.all(np.isfinite(result.logits))
    assert set(beats.beat_class.tolist()) == {"N", "S", "V", "F"}
    expected = np.array([folds.subject_fold[s] for s in beats.subject_id.tolist()])
    np.testing.assert_array_equal(result.fold, expected)
    assert set(beats.record_id.tolist()) <= set(splits.ds1)
    assert not set(beats.record_id.tolist()) & set(splits.ds2)
    # Each fold's class counts equal the fold file's.
    for k in range(5):
        mine = beats.beat_class[result.fold == k]
        counts = {c: int((mine == c).sum()) for c in ("N", "S", "V", "F")}
        assert counts == dict(folds.class_counts[str(k)])
