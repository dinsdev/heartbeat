"""The split-enforcing loader: DS1 only (C1; EVAL-04, R15).

Before the sealed run no DS2-derived file exists (Phase 2 settling 4), and this
loader has no DS2 path: asking for any record outside DS1 raises before a file
is opened, and a stray non-DS1 file in the prepared folder fails the load.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import RR_FEATURE_NAMES, SCORED_CLASSES, WINDOW_SAMPLES
from heartbeat.data.manifests import Splits
from heartbeat.data.npz import PreparedRecord, load_prepared
from heartbeat.signal.windows import extract_windows


class SealedRecordError(PermissionError):
    """A record outside DS1 was asked for (rule 1)."""


@dataclass(frozen=True)
class BeatTable:
    """Beats from one or more DS1 records, one row per beat.

    Attributes:
        record_id: Each beat's record, `(n,)`.
        subject_id: Each beat's subject, `(n,)`.
        sample: Annotation sample within its record, int64, `(n,)`.
        beat_class: AAMI class, `(n,)`.
        window_adu: The beat's window, int16, `(n, 256)`.
        rr_s: RR features in `RR_FEATURE_NAMES` order, float64, `(n, 6)`.
    """

    record_id: NDArray[np.str_]
    subject_id: NDArray[np.str_]
    sample: NDArray[np.int64]
    beat_class: NDArray[np.str_]
    window_adu: NDArray[np.int16]
    rr_s: NDArray[np.float64]

    def __post_init__(self) -> None:
        """Check that every column has one row per beat."""
        n = self.sample.shape[0]
        assert self.sample.dtype == np.int64, self.sample.dtype
        assert self.record_id.shape == (n,), self.record_id.shape
        assert self.subject_id.shape == (n,), self.subject_id.shape
        assert self.beat_class.shape == (n,), self.beat_class.shape
        assert self.window_adu.dtype == np.int16, self.window_adu.dtype
        assert self.window_adu.shape == (n, WINDOW_SAMPLES), self.window_adu.shape
        assert self.rr_s.shape == (n, len(RR_FEATURE_NAMES)), self.rr_s.shape


def require_ds1(record_ids: Sequence[str], splits: Splits) -> None:
    """Raise unless every record is in DS1.

    Raises:
        SealedRecordError: Naming the first record that is DS2, excluded or unknown.
    """
    for record in record_ids:
        if record in splits.ds1:
            continue
        if record in splits.ds2:
            reason = "is DS2, the sealed test set (rule 1)"
        elif record in splits.excluded:
            reason = f"is excluded: {splits.excluded[record]}"
        else:
            reason = "is not in DS1"
        raise SealedRecordError(f"record {record} {reason}; only DS1 can be loaded")


def _ds1_records(
    prepared_dir: Path,
    splits: Splits,
    subjects: Mapping[str, str],
    records: Sequence[str] | None,
) -> Iterator[tuple[str, PreparedRecord]]:
    """Each asked-for DS1 record's prepared file, checked against the manifests."""
    wanted = tuple(splits.ds1 if records is None else records)
    require_ds1(wanted, splits)
    for path in sorted(prepared_dir.glob("*.npz")):
        if path.stem not in splits.ds1:
            raise SealedRecordError(
                f"{path}: a prepared file for a record outside DS1; delete it"
            )
    for record in wanted:
        path = prepared_dir / f"{record}.npz"
        if not path.is_file():
            raise FileNotFoundError(f"{path} missing; run `uv run heartbeat prepare`")
        prepared = load_prepared(path)
        require_ds1([prepared.record_id], splits)
        if prepared.subject_id != subjects[record]:
            raise ValueError(
                f"record {record}: subject {prepared.subject_id} in {path}, "
                f"{subjects[record]} in the manifest"
            )
        yield record, prepared


def load_ds1(
    prepared_dir: Path,
    splits: Splits,
    subjects: Mapping[str, str],
    records: Sequence[str] | None = None,
    include_q: bool = False,
) -> BeatTable:
    """Load the kept beats of DS1 records from the prepared folder.

    Args:
        prepared_dir: Folder written by `heartbeat prepare`.
        splits: The split manifest.
        subjects: Record to subject, from the subjects manifest.
        records: DS1 records to load; all of DS1 by default.
        include_q: Keep Q beats too (they are never scored, DATA-10).

    Returns:
        The beats, records in the order asked for.

    Raises:
        SealedRecordError: For a record outside DS1, or a non-DS1 file in the folder.
        FileNotFoundError: If a DS1 record has not been prepared.
        ValueError: If a file's record or subject disagrees with the manifests.
    """
    allowed = set(SCORED_CLASSES) | ({"Q"} if include_q else set())

    parts: list[BeatTable] = []
    for record, prepared in _ds1_records(prepared_dir, splits, subjects, records):
        kept_class = prepared.beat_class[prepared.kept]
        chosen = np.isin(kept_class, sorted(allowed))
        sample = prepared.beat_sample[prepared.kept][chosen]
        n = sample.size
        parts.append(
            BeatTable(
                record_id=np.full(n, record),
                subject_id=np.full(n, prepared.subject_id),
                sample=sample,
                beat_class=kept_class[chosen],
                window_adu=extract_windows(prepared.trace_adu, sample),
                rr_s=prepared.rr_s[chosen],
            )
        )
    return BeatTable(
        record_id=np.concatenate([p.record_id for p in parts]),
        subject_id=np.concatenate([p.subject_id for p in parts]),
        sample=np.concatenate([p.sample for p in parts]),
        beat_class=np.concatenate([p.beat_class for p in parts]),
        window_adu=np.concatenate([p.window_adu for p in parts]),
        rr_s=np.concatenate([p.rr_s for p in parts]),
    )


def load_ds1_traces(
    prepared_dir: Path,
    splits: Splits,
    subjects: Mapping[str, str],
    records: Sequence[str] | None = None,
) -> dict[str, NDArray[np.int16]]:
    """Load the canonical int16 trace of DS1 records, for augmentation.

    The same checks as `load_ds1` (R15; Phase 4 task plan, design call 2): a
    record outside DS1 raises before a file is opened, and a stray non-DS1
    file in the folder fails the load.

    Returns:
        Record to trace, `(n_samples,)` each, records in the order asked for.

    Raises:
        SealedRecordError: For a record outside DS1, or a non-DS1 file in the folder.
        FileNotFoundError: If a DS1 record has not been prepared.
        ValueError: If a file's record or subject disagrees with the manifests.
    """
    return {
        record: prepared.trace_adu
        for record, prepared in _ds1_records(prepared_dir, splits, subjects, records)
    }
