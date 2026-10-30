"""Per-record pipeline and the DS1 writer (B3, B4; DATA-04 to DATA-10).

`prepare_record` is pure, so `evaluate-test` can later run it on DS2 in memory.
`prepare_ds1` writes DS1 only (Phase 2 settling 4) and refuses any other record
before reading a file.
"""

import json
import logging
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import numpy as np

from heartbeat.config import Settings
from heartbeat.constants import FLOOR_HIT_LIMIT, ZSCORE_STD_FLOOR_ADU
from heartbeat.data.aami import classify_symbols
from heartbeat.data.loader import require_ds1
from heartbeat.data.manifests import Splits
from heartbeat.data.npz import PreparedRecord, load_prepared, save_prepared
from heartbeat.data.records import RawRecord, read_record
from heartbeat.signal.filter import bandpass_mv, to_adu
from heartbeat.signal.rr import rr_features
from heartbeat.signal.windows import WindowRangeError, extract_windows, window_std_adu

__all__ = [
    "FloorHitLimitError",
    "FloorHits",
    "PrepareReport",
    "PreparedRecord",
    "load_prepared",
    "prepare_ds1",
    "prepare_record",
    "save_prepared",
]

log = logging.getLogger(__name__)

FLOOR_HITS_FILE = "floor_hits.json"


class FloorHitLimitError(RuntimeError):
    """More DS1 windows hit the z-score floor than the plan allows (B3 amendment)."""


@dataclass(frozen=True)
class FloorHits:
    """Z-score floor hits of one record's kept windows.

    Attributes:
        hits: Windows whose standard deviation is below the floor.
        min_std_adu: The smallest window standard deviation, in int16 units.
    """

    hits: int
    min_std_adu: float


@dataclass(frozen=True)
class PrepareReport:
    """What `prepare_ds1` wrote.

    Attributes:
        records: The prepared records, in order.
        floor_hits: Record to its floor hits.
        total_hits: Sum over the records.
    """

    records: tuple[str, ...]
    floor_hits: Mapping[str, FloorHits]
    total_hits: int


def prepare_record(raw: RawRecord, subject_id: str) -> PreparedRecord:
    """Filter, round, label and featurize one record.

    Raises:
        UnknownSymbolError: On an annotation symbol outside DATA-09.
        TraceRangeError: If the filtered trace does not fit int16.
        WindowRangeError: If a kept beat's window leaves the record.
    """
    trace_adu = to_adu(bandpass_mv(raw.mlii_mv))
    is_beat, beat_class = classify_symbols(raw.record_id, raw.ann_symbol)
    beat_sample = raw.ann_sample[is_beat]
    beat_symbol = np.array(raw.ann_symbol, dtype="<U1")[is_beat]
    # DATA-08: the first and last beat have no full RR context.
    kept = np.ones(beat_sample.size, dtype=np.bool_)
    kept[[0, -1]] = False
    # DATA-07: RR runs over every annotated beat, Q included (R9).
    rr_s = rr_features(beat_sample)
    try:
        extract_windows(trace_adu, beat_sample[kept])
    except WindowRangeError as error:
        raise WindowRangeError(f"record {raw.record_id}: {error}") from error
    return PreparedRecord(
        record_id=raw.record_id,
        subject_id=subject_id,
        trace_adu=trace_adu,
        beat_sample=beat_sample,
        beat_symbol=beat_symbol,
        beat_class=beat_class,
        kept=kept,
        rr_s=rr_s,
    )


def floor_hits(record: PreparedRecord) -> FloorHits:
    """Count the kept windows whose standard deviation is below the floor."""
    std_adu = window_std_adu(
        extract_windows(record.trace_adu, record.beat_sample[record.kept])
    )
    return FloorHits(
        hits=int(np.sum(std_adu < ZSCORE_STD_FLOOR_ADU)),
        min_std_adu=float(std_adu.min()),
    )


def _write_json(path: Path, payload: object) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".part",
        delete=False,
        encoding="utf-8",
    ) as f:
        temp = Path(f.name)
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    temp.replace(path)


def prepare_ds1(
    settings: Settings,
    splits: Splits,
    subjects: Mapping[str, str],
    records: Sequence[str] | None = None,
) -> PrepareReport:
    """Prepare DS1 records into `<prepared_dir>/<record>.npz` and report floor hits.

    Args:
        settings: Run settings (cache and prepared folders).
        splits: The split manifest.
        subjects: Record to subject.
        records: Records to prepare; all of DS1 by default.

    Returns:
        The report also written to `<prepared_dir>/floor_hits.json`.

    Raises:
        SealedRecordError: For any record outside DS1, before anything is read.
        FloorHitLimitError: If more than `FLOOR_HIT_LIMIT` windows hit the floor,
            after the records and the report are written.
    """
    wanted = tuple(splits.ds1 if records is None else records)
    require_ds1(wanted, splits)
    out_dir = settings.data.prepared_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    hits: dict[str, FloorHits] = {}
    for record_id in wanted:
        raw = read_record(settings.data.raw_dir, record_id, splits.lead)
        prepared = prepare_record(raw, subjects[record_id])
        save_prepared(prepared, out_dir / f"{record_id}.npz")
        hits[record_id] = floor_hits(prepared)
        log.info("prepared %s: %d beats", record_id, prepared.beat_sample.size)
    total = sum(h.hits for h in hits.values())
    _write_json(
        out_dir / FLOOR_HITS_FILE,
        {
            "floor_adu": ZSCORE_STD_FLOOR_ADU,
            "limit": FLOOR_HIT_LIMIT,
            "total_hits": total,
            "records": {
                r: {"hits": h.hits, "min_std_adu": h.min_std_adu}
                for r, h in hits.items()
            },
        },
    )
    if total > FLOOR_HIT_LIMIT:
        raise FloorHitLimitError(
            f"{total} DS1 windows hit the z-score floor, limit {FLOOR_HIT_LIMIT}; "
            f"see {out_dir / FLOOR_HITS_FILE} and ask Din (B3 amendment)"
        )
    return PrepareReport(
        records=wanted, floor_hits=MappingProxyType(hits), total_hits=total
    )
