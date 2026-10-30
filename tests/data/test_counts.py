"""DATA-11: per-record counts from the real `.atr` files match PhysioNet's table (R11).

This reads annotations only, for all 44 downloaded records; DS2 annotations
may be read for class counts (rule 1). No signal is read here.
"""

from collections import Counter
from pathlib import Path

import pytest

from heartbeat.constants import AAMI_CLASS
from heartbeat.data.aami import classify_symbols
from heartbeat.data.manifests import (
    Splits,
    downloaded_records,
    load_beat_counts,
    load_checksums,
)
from heartbeat.data.records import read_annotations
from heartbeat.paths import BEAT_COUNTS_MANIFEST, CHECKSUM_MANIFEST

RECORDS = downloaded_records(load_checksums(CHECKSUM_MANIFEST))
EXPECTED = load_beat_counts(BEAT_COUNTS_MANIFEST)
# The beat table counts beats plus flutter waves and non-conducted P waves.
TABLE_SYMBOLS = {*AAMI_CLASS, "!", "x"}

# PRD Appendix C, written out rather than computed from the manifest.
APPENDIX_C = {
    "ds1": {"N": 45866, "S": 944, "V": 3788, "F": 415, "Q": 8},
    "ds2": {"N": 42198, "S": 1782, "V": 3202, "F": 387, "Q": 7},
}


def _table_counts(raw_dir: Path, record: str) -> Counter[str]:
    symbols = read_annotations(raw_dir, record).symbol
    return Counter(s for s in symbols if s in TABLE_SYMBOLS)


def test_44_records() -> None:
    assert len(RECORDS) == 44


@pytest.mark.rule("R11")
@pytest.mark.parametrize("record", RECORDS)
def test_symbol_counts_match_the_beat_table(raw_dir: Path, record: str) -> None:
    assert dict(_table_counts(raw_dir, record)) == dict(EXPECTED[record])


@pytest.mark.rule("R10")
@pytest.mark.parametrize("record", RECORDS)
def test_every_annotation_symbol_is_known(raw_dir: Path, record: str) -> None:
    classify_symbols(record, read_annotations(raw_dir, record).symbol)


@pytest.mark.rule("R11")
@pytest.mark.parametrize("side", ["ds1", "ds2"])
def test_aami_class_totals_match_appendix_c(
    raw_dir: Path, splits: Splits, side: str
) -> None:
    totals: Counter[str] = Counter()
    for record in getattr(splits, side):
        symbols = read_annotations(raw_dir, record).symbol
        _, classes = classify_symbols(record, symbols)
        totals.update(classes.tolist())
    assert dict(totals) == APPENDIX_C[side]
