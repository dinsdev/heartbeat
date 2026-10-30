"""The data summary behind the data card (F6; Phase 5 settling 5).

Class counts per record and set come from the expected-count manifest
(PhysioNet's published table, R11's oracle), DS1 kept-beat counts from the
prepared DS1 files, and age and sex from the record headers. No DS2 signal or
annotation is read: DS2 rows use the published counts and the headers only.
"""

import statistics
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from heartbeat.constants import AAMI_CLASS
from heartbeat.data.loader import BeatTable
from heartbeat.data.manifests import Splits
from heartbeat.data.records import Demographics

# The data card's class columns: the four scored classes, then Q (B4).
COUNT_CLASSES = ("N", "S", "V", "F", "Q")

DATA_SUMMARY_LABEL = (
    "annotated beats: PhysioNet's published per-record table "
    "(manifests/mitdb-beat-counts.toml); kept beats: DS1 prepared files, first "
    "and last beat of each record dropped; age and sex: record headers"
)


def aami_counts(symbol_counts: Mapping[str, int]) -> dict[str, int]:
    """Counts by AAMI class from counts by annotation symbol; non-beats skipped."""
    out = dict.fromkeys(COUNT_CLASSES, 0)
    for symbol, n in symbol_counts.items():
        if symbol in AAMI_CLASS:
            out[AAMI_CLASS[symbol]] += n
    return out


def _kept_counts(kept: BeatTable, record: str) -> dict[str, int]:
    classes = kept.beat_class[kept.record_id == record].tolist()
    return {c: classes.count(c) for c in COUNT_CLASSES}


def _sum(rows: Sequence[Mapping[str, int]]) -> dict[str, int]:
    return {c: sum(r[c] for r in rows) for c in COUNT_CLASSES}


def _demographics(people: Sequence[Demographics]) -> dict[str, Any]:
    ages = sorted(p.age for p in people if p.age is not None)
    return {
        "patients": len(people),
        "men": sum(p.sex == "M" for p in people),
        "women": sum(p.sex == "F" for p in people),
        "sex_unknown": sum(p.sex is None for p in people),
        "age_min": ages[0] if ages else None,
        "age_max": ages[-1] if ages else None,
        "age_median": float(statistics.median(ages)) if ages else None,
        "age_unknown": len(people) - len(ages),
    }


def describe_data(
    splits: Splits,
    subjects: Mapping[str, str],
    beat_counts: Mapping[str, Mapping[str, int]],
    demographics: Mapping[str, Demographics],
    kept: BeatTable,
) -> dict[str, Any]:
    """The `results/data_summary.json` payload.

    Args:
        splits: The split manifest; DS1 then DS2, in manifest order.
        subjects: Record to subject.
        beat_counts: Expected counts by symbol per record (the manifest).
        demographics: Record to its header's age and sex.
        kept: DS1's kept beats, Q included (`load_ds1(include_q=True)`).

    Raises:
        KeyError: If a DS1 or DS2 record has no counts or no header entry.
    """
    if not set(kept.record_id.tolist()) <= set(splits.ds1):
        raise ValueError("kept beats must come from DS1 records only")
    records: list[dict[str, Any]] = []
    sets: dict[str, Any] = {}
    people: dict[str, list[Demographics]] = {}
    unparsed: list[dict[str, str]] = []
    for name, members in (("DS1", splits.ds1), ("DS2", splits.ds2)):
        rows: list[dict[str, Any]] = []
        annotated: list[dict[str, int]] = []
        kept_rows: list[dict[str, int]] = []
        for record in members:
            if record not in beat_counts:
                raise KeyError(f"record {record} has no expected counts")
            if record not in demographics:
                raise KeyError(f"record {record} has no header demographics")
            person = demographics[record]
            for field, value in (("age", person.age), ("sex", person.sex)):
                if value is None:
                    unparsed.append({"record": record, "field": field})
            annotated.append(aami_counts(beat_counts[record]))
            if name == "DS1":
                kept_rows.append(_kept_counts(kept, record))
            rows.append(
                {
                    "record": record,
                    "set": name,
                    "subject": subjects[record],
                    "annotated": annotated[-1],
                    "kept": kept_rows[-1] if name == "DS1" else None,
                    "age": person.age,
                    "sex": person.sex,
                }
            )
        records.extend(rows)
        sets[name] = {
            "records": list(members),
            "patients": len({subjects[r] for r in members}),
            "annotated": _sum(annotated),
            "kept": _sum(kept_rows) if name == "DS1" else None,
        }
        people[name] = [demographics[r] for r in members]
    return {
        "label": DATA_SUMMARY_LABEL,
        "classes": list(COUNT_CLASSES),
        "sets": sets,
        "records": records,
        "demographics": {name: _demographics(p) for name, p in people.items()},
        "unparsed": unparsed,
        "n_kept_ds1": int(np.asarray(kept.sample).size),
    }
