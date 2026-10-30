"""Storage of one prepared record as an `.npz` file (DATA-08).

Kept apart from `prepare.py` so the loader can read prepared files without
importing the module that reads signals (rule 1, R15).
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import RR_FEATURE_NAMES


@dataclass(frozen=True)
class PreparedRecord:
    """One record after `prepare_record`.

    Attributes:
        record_id: The record.
        subject_id: Its subject from `manifests/subjects.toml`.
        trace_adu: The canonical MLII trace, int16 at 200 units per mV,
            shape `(n_samples,)`.
        beat_sample: Samples of every annotated beat, int64, `(n_beats,)`.
        beat_symbol: Each beat's annotation symbol, `(n_beats,)`.
        beat_class: Each beat's AAMI class (N, S, V, F or Q), `(n_beats,)`.
        kept: False for the first and last beat (DATA-08), `(n_beats,)`.
        rr_s: RR features of the kept beats in `RR_FEATURE_NAMES` order,
            float64, `(n_kept, 6)`.
    """

    record_id: str
    subject_id: str
    trace_adu: NDArray[np.int16]
    beat_sample: NDArray[np.int64]
    beat_symbol: NDArray[np.str_]
    beat_class: NDArray[np.str_]
    kept: NDArray[np.bool_]
    rr_s: NDArray[np.float64]

    def __post_init__(self) -> None:
        """Check dtypes and shapes where data crosses a module boundary."""
        n_beats = self.beat_sample.shape[0]
        assert self.trace_adu.dtype == np.int16, self.trace_adu.dtype
        assert self.trace_adu.ndim == 1, self.trace_adu.shape
        assert self.beat_sample.dtype == np.int64, self.beat_sample.dtype
        assert self.beat_symbol.shape == (n_beats,), self.beat_symbol.shape
        assert self.beat_class.shape == (n_beats,), self.beat_class.shape
        assert self.kept.dtype == np.bool_, self.kept.dtype
        assert self.kept.shape == (n_beats,), self.kept.shape
        assert self.rr_s.dtype == np.float64, self.rr_s.dtype
        assert self.rr_s.shape == (int(self.kept.sum()), len(RR_FEATURE_NAMES))


def save_prepared(record: PreparedRecord, path: Path) -> None:
    """Write a prepared record atomically, without pickled objects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".part", delete=False
    ) as f:
        temp = Path(f.name)
        try:
            np.savez(
                f,
                record_id=np.array(record.record_id),
                subject_id=np.array(record.subject_id),
                trace_adu=record.trace_adu,
                beat_sample=record.beat_sample,
                beat_symbol=record.beat_symbol,
                beat_class=record.beat_class,
                kept=record.kept,
                rr_s=record.rr_s,
            )
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    temp.replace(path)


def load_prepared(path: Path) -> PreparedRecord:
    """Read a prepared record written by `save_prepared`.

    Raises:
        ValueError: If the record inside differs from the file's name.
    """
    with np.load(path, allow_pickle=False) as data:
        record = PreparedRecord(
            record_id=str(data["record_id"]),
            subject_id=str(data["subject_id"]),
            trace_adu=data["trace_adu"],
            beat_sample=data["beat_sample"],
            beat_symbol=data["beat_symbol"],
            beat_class=data["beat_class"],
            kept=data["kept"],
            rr_s=data["rr_s"],
        )
    if record.record_id != path.stem:
        raise ValueError(
            f"{path}: file named for record {path.stem} holds record {record.record_id}"
        )
    return record
