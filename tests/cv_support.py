"""Synthetic DS1-like beats and folds for the CV tests. No record is read."""

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import N_FOLDS, SCORED_CLASSES, WINDOW_SAMPLES
from heartbeat.data.folds import Folds
from heartbeat.data.loader import BeatTable

CLASS_P = (0.7, 0.1, 0.15, 0.05)


def synthetic_beats(
    n_subjects: int = 10, per_subject: int = 160, seed: int = 0
) -> BeatTable:
    """Beats whose RR features carry some, not all, of the class (not separable)."""
    rng = np.random.default_rng(seed)
    n = n_subjects * per_subject
    subject = np.repeat([f"s{k:02d}" for k in range(n_subjects)], per_subject)
    labels = np.array(SCORED_CLASSES)[rng.choice(4, size=n, p=CLASS_P)]
    # Every subject has every class at least twice.
    for k in range(n_subjects):
        labels[k * per_subject : k * per_subject + 8] = np.repeat(SCORED_CLASSES, 2)
    shift_pre = {"N": 0.0, "S": -0.25, "V": -0.2, "F": -0.05}
    shift_post = {"N": 0.0, "S": 0.05, "V": 0.3, "F": 0.1}
    local = rng.uniform(0.7, 1.0, n)
    long = local * rng.uniform(0.95, 1.05, n)
    pre = local + np.array([shift_pre[c] for c in labels]) + rng.normal(0, 0.12, n)
    post = local + np.array([shift_post[c] for c in labels]) + rng.normal(0, 0.12, n)
    pre = np.clip(pre, 0.25, None)
    post = np.clip(post, 0.25, None)
    rr_s = np.column_stack([pre, post, local, long, pre / local, post / pre])
    return BeatTable(
        record_id=subject.copy(),
        subject_id=subject,
        sample=np.tile(np.arange(per_subject, dtype=np.int64) * 300, n_subjects),
        beat_class=labels,
        window_adu=np.zeros((n, WINDOW_SAMPLES), dtype=np.int16),
        rr_s=rr_s,
    )


def synthetic_folds(beats: BeatTable) -> Folds:
    """Subject k in fold k mod 5."""
    subjects = sorted(set(beats.subject_id.tolist()))
    subject_fold = {s: k % N_FOLDS for k, s in enumerate(subjects)}
    counts: dict[str, dict[str, int]] = {}
    for fold in range(N_FOLDS):
        mine = np.isin(
            beats.subject_id, [s for s, f in subject_fold.items() if f == fold]
        )
        counts[str(fold)] = {
            c: int((beats.beat_class[mine] == c).sum()) for c in SCORED_CLASSES
        }
    return Folds(
        seed=1,
        sklearn_version="test",
        manifest_sha256={},
        subject_fold=subject_fold,
        class_counts=counts,
    )


def subset_rows(beats: BeatTable, index: NDArray[np.int64]) -> BeatTable:
    """The beats at `index`."""
    return BeatTable(
        record_id=beats.record_id[index],
        subject_id=beats.subject_id[index],
        sample=beats.sample[index],
        beat_class=beats.beat_class[index],
        window_adu=beats.window_adu[index],
        rr_s=beats.rr_s[index],
    )
