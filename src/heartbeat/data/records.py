"""Read MIT-BIH records with wfdb and pick MLII by name (B1; DATA-04).

Rule 1: `read_record` reads a signal. Only `data/prepare.py` imports it (an
import-graph test checks this), and `prepare` refuses DS2 before reading.
`read_annotations` reads `.atr` files only, which R11 may do for every record.
`read_header_demographics` reads the `.hea` text only, for the data card's age
and sex rows (Phase 5 settling 5), which may be done for every record.
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
class Demographics:
    """Age and sex from a record header's first comment line.

    Attributes:
        age: Age in years, or None when the header gives none (for example -1).
        sex: "M" or "F", or None when the header gives neither.
    """

    age: int | None
    sex: str | None


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


def parse_demographics(header_text: str) -> Demographics:
    """Age and sex from the first `#` line of a header, as `# <age> <sex> ...`.

    A value that is missing or does not parse gives None, never an error: the
    card renders it "unknown" and the ledger lists it (Phase 5 plan, stop 9).
    """
    comments = [line for line in header_text.splitlines() if line.startswith("#")]
    fields = comments[0].lstrip("#").split() if comments else []
    age: int | None = None
    if fields and fields[0].isdigit():
        age = int(fields[0])
    sex = fields[1] if len(fields) > 1 and fields[1] in ("M", "F") else None
    return Demographics(age=age, sex=sex)


def read_header_demographics(raw_dir: Path, record_id: str) -> Demographics:
    """Read a record's age and sex from its `.hea` file, opening nothing else."""
    text = (raw_dir / f"{record_id}.hea").read_text(encoding="utf-8")
    return parse_demographics(text)
