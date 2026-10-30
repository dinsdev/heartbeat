"""EVAL-02, EVAL-03 on the committed fold file and its pin (R13, R14).

`config/folds.json` came from Din's one `make-folds` run (C1). These tests read
it and never call the splitter.
"""

import hashlib
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from heartbeat.constants import N_FOLDS, SCORED_CLASSES
from heartbeat.data.folds import check_folds, read_folds
from heartbeat.data.loader import load_ds1
from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import PrepareReport
from heartbeat.paths import FOLDS_JSON, FOLDS_PIN, SPLITS_MANIFEST, SUBJECTS_MANIFEST

FOLD_MANIFESTS = (SPLITS_MANIFEST, SUBJECTS_MANIFEST)


@pytest.mark.rule("R13")
def test_committed_folds_hold_every_ds1_subject_once(
    splits: Splits, subjects: dict[str, str]
) -> None:
    folds = read_folds(FOLDS_JSON)  # rejects a subject key that appears twice
    ds1 = {subjects[r] for r in splits.ds1}
    assert sorted(folds.subject_fold) == sorted(ds1)
    assert len(folds.subject_fold) == 22
    assert set(folds.subject_fold.values()) == set(range(N_FOLDS))


@pytest.mark.rule("R13")
def test_committed_folds_hold_no_ds2_or_excluded_subject(
    splits: Splits, subjects: dict[str, str]
) -> None:
    folds = read_folds(FOLDS_JSON)
    ds1 = {subjects[r] for r in splits.ds1}
    sealed = {subjects[r] for r in (*splits.ds2, *splits.excluded)} - ds1
    assert not sealed & set(folds.subject_fold)


@pytest.mark.rule("R13")
def test_201_and_202_share_one_valid_fold(subjects: dict[str, str]) -> None:
    folds = read_folds(FOLDS_JSON)
    assert subjects["201"] == subjects["202"]
    assert 0 <= folds.subject_fold[subjects["201"]] < N_FOLDS


@pytest.mark.rule("R13")
def test_committed_folds_were_made_from_todays_manifests() -> None:
    folds = read_folds(FOLDS_JSON)
    assert dict(folds.manifest_sha256) == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in FOLD_MANIFESTS
    }


@pytest.mark.rule("R13")
def test_committed_class_counts_match_the_prepared_ds1(
    prepared_ds1: tuple[Path, PrepareReport],
    splits: Splits,
    subjects: dict[str, str],
) -> None:
    folder, _ = prepared_ds1
    beats = load_ds1(folder, splits, subjects)
    folds = read_folds(FOLDS_JSON)
    fold_of_beat = np.array([folds.subject_fold[s] for s in beats.subject_id])
    for fold in range(N_FOLDS):
        counts = Counter(beats.beat_class[fold_of_beat == fold].tolist())
        expected = {cls: counts[cls] for cls in SCORED_CLASSES}
        assert dict(folds.class_counts[str(fold)]) == expected


@pytest.mark.rule("R14")
def test_committed_folds_pass_check_folds_against_the_pin(
    splits: Splits, subjects: dict[str, str]
) -> None:
    folds = check_folds(
        FOLDS_JSON, FOLDS_PIN, splits, subjects, manifest_paths=FOLD_MANIFESTS
    )
    assert folds.seed == 20261026
    assert FOLDS_PIN.read_text(encoding="utf-8").endswith("  config/folds.json\n")
