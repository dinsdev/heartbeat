"""Read MIT-BIH records with wfdb and pick MLII by name (B1; DATA-04).

Rule 1: `read_record` reads a signal. Only `data/prepare.py` imports it (an
import-graph test checks this), and `prepare` refuses DS2 before reading.
`read_annotations` reads `.atr` files only, which R11 may do for every record.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import wfdb
from numpy.typing import NDArray

from heartbeat.constants import FS_HZ
from heartbeat.data.aami import classify_symbols


class LeadNotFoundError(ValueError):
    """The requested lead is missing from a record, or present twice."""


class RecordError(ValueError):
    """A record breaks an assumption the pipeline rests on (rate, units, order)."""


@dataclass(frozen=True)
class Annotations:
    """A record's reference annotations.

    Attributes:
        record_id: The record.
        sample: Annotation samples, int64, shape `(n_annotations,)`.
        symbol: Annotation symbols, same length.
    """

    record_id: str
    sample: NDArray[np.int64]
    symbol: tuple[str, ...]


@dataclass(frozen=True)
class RawRecord:
    """One record's MLII lead and annotations, before any processing.

    Attributes:
        record_id: The record.
        mlii_mv: The MLII lead in millivolts at 360 Hz, float64, `(n_samples,)`.
        ann_sample: Every annotation's sample, int64, `(n_annotations,)`.
        ann_symbol: Every annotation's symbol, same length.
    """

    record_id: str
    mlii_mv: NDArray[np.float64]
    ann_sample: NDArray[np.int64]
    ann_symbol: tuple[str, ...]


def select_lead(sig_names: Sequence[str], lead: str) -> int:
    """Return the channel index of `lead`, found by name (R4).

    Raises:
        LeadNotFoundError: If the lead is missing or appears more than once.
    """
    matches = [i for i, name in enumerate(sig_names) if name == lead]
    if not matches:
        raise LeadNotFoundError(f"lead {lead} not in {list(sig_names)}")
    if len(matches) > 1:
        raise LeadNotFoundError(f"lead {lead} appears twice in {list(sig_names)}")
    return matches[0]


def read_annotations(raw_dir: Path, record_id: str) -> Annotations:
    """Read a record's `.atr` annotations only, never its signal."""
    ann = wfdb.rdann(str(raw_dir / record_id), "atr")
    sample = np.asarray(ann.sample, dtype=np.int64)
    symbol = tuple(str(s) for s in ann.symbol)
    if sample.shape != (len(symbol),):
        raise RecordError(f"record {record_id}: annotation samples and symbols differ")
    return Annotations(record_id=record_id, sample=sample, symbol=symbol)


def read_record(raw_dir: Path, record_id: str, lead: str) -> RawRecord:
    """Read a record's lead in millivolts and its annotations.

    Args:
        raw_dir: The download cache.
        record_id: The record.
        lead: The lead to read by name, `MLII` from the splits manifest.

    Returns:
        The raw record.

    Raises:
        LeadNotFoundError: If the lead is missing.
        RecordError: If the rate is not 360 Hz, the lead is not in mV, or beat
            samples are not strictly increasing.
        UnknownSymbolError: On an annotation symbol outside DATA-09.
    """
    header = wfdb.rdheader(str(raw_dir / record_id))
    if header.fs != FS_HZ:
        raise RecordError(f"record {record_id}: rate {header.fs} Hz, expected {FS_HZ}")
    channel = select_lead(header.sig_name, lead)
    if header.units[channel] != "mV":
        raise RecordError(
            f"record {record_id}: lead {lead} in {header.units[channel]}, expected mV"
        )
    record = wfdb.rdrecord(str(raw_dir / record_id), channels=[channel], physical=True)
    mlii_mv = np.asarray(record.p_signal[:, 0], dtype=np.float64)

    annotations = read_annotations(raw_dir, record_id)
    is_beat, _ = classify_symbols(record_id, annotations.symbol)
    beat_sample = annotations.sample[is_beat]
    steps = np.diff(beat_sample)
    if np.any(steps <= 0):
        index = int(np.argmax(steps <= 0)) + 1
        raise RecordError(
            f"record {record_id}: beat {index} at sample {beat_sample[index]} "
            "is not after the beat before it"
        )
    return RawRecord(
        record_id=record_id,
        mlii_mv=mlii_mv,
        ann_sample=annotations.sample,
        ann_symbol=annotations.symbol,
    )
