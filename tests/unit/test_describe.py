"""Phase 5 settling 5, F6: the data summary the data card renders from."""

import json

import numpy as np
import pytest
from cv_support import synthetic_beats

from heartbeat.data.describe import aami_counts, describe_data
from heartbeat.data.loader import BeatTable
from heartbeat.data.manifests import Splits
from heartbeat.data.records import Demographics

SPLITS = Splits(
    ds1=("101", "106"), ds2=("100", "103"), excluded={"202": "same as 201"}, lead="MLII"
)
SUBJECTS = {"101": "101", "106": "106", "100": "100", "103": "103", "202": "201"}
COUNTS = {
    "101": {"N": 10, "A": 2, "Q": 1, "x": 3},
    "106": {"N": 5, "V": 4},
    "100": {"N": 7, "A": 1, "V": 1},
    "103": {"N": 6, "a": 2, "F": 1, "/": 1, "!": 2},
    "202": {"N": 99},
}
DEMOGRAPHICS = {
    "101": Demographics(75, "F"),
    "106": Demographics(24, "F"),
    "100": Demographics(69, "M"),
    "103": Demographics(None, "M"),
}


def _kept() -> BeatTable:
    base = synthetic_beats(n_subjects=2, per_subject=8)
    record = np.array(["101"] * 8 + ["106"] * 8)
    classes = np.array(["N"] * 6 + ["S", "Q"] + ["N"] * 4 + ["V"] * 4)
    return BeatTable(record, record, base.sample, classes, base.window_adu, base.rr_s)


def test_aami_counts_map_symbols_and_skip_non_beats() -> None:
    assert aami_counts({"N": 10, "L": 2, "A": 2, "Q": 1, "x": 3, "!": 4}) == {
        "N": 12,
        "S": 2,
        "V": 0,
        "F": 0,
        "Q": 1,
    }


def test_the_summary_has_per_set_and_per_record_counts() -> None:
    summary = describe_data(SPLITS, SUBJECTS, COUNTS, DEMOGRAPHICS, _kept())
    json.dumps(summary, allow_nan=False)
    ds1, ds2 = summary["sets"]["DS1"], summary["sets"]["DS2"]
    assert ds1["records"] == ["101", "106"]
    assert ds1["annotated"] == {"N": 15, "S": 2, "V": 4, "F": 0, "Q": 1}
    assert ds1["kept"] == {"N": 10, "S": 1, "V": 4, "F": 0, "Q": 1}
    assert ds2["annotated"] == {"N": 13, "S": 3, "V": 1, "F": 1, "Q": 1}
    # DS2 beats are never loaded: only the published counts (settling 5).
    assert ds2["kept"] is None
    rows = {r["record"]: r for r in summary["records"]}
    assert list(rows) == ["101", "106", "100", "103"]
    assert "202" not in rows
    assert rows["101"]["set"] == "DS1"
    assert rows["101"]["annotated"] == {"N": 10, "S": 2, "V": 0, "F": 0, "Q": 1}
    assert rows["101"]["kept"] == {"N": 6, "S": 1, "V": 0, "F": 0, "Q": 1}
    assert rows["103"]["kept"] is None
    assert rows["103"]["age"] is None
    assert rows["103"]["sex"] == "M"


def test_demographics_per_set_and_the_unparsed_list() -> None:
    summary = describe_data(SPLITS, SUBJECTS, COUNTS, DEMOGRAPHICS, _kept())
    assert summary["demographics"]["DS1"] == {
        "patients": 2,
        "men": 0,
        "women": 2,
        "sex_unknown": 0,
        "age_min": 24,
        "age_max": 75,
        "age_median": 49.5,
        "age_unknown": 0,
    }
    ds2 = summary["demographics"]["DS2"]
    assert ds2["men"] == 2
    assert ds2["age_min"] == ds2["age_max"] == 69
    assert ds2["age_unknown"] == 1
    assert summary["unparsed"] == [{"record": "103", "field": "age"}]


def test_a_record_missing_from_the_counts_or_headers_fails() -> None:
    with pytest.raises(KeyError, match="104"):
        describe_data(
            Splits(ds1=("101", "106"), ds2=("104",), excluded={}, lead="MLII"),
            SUBJECTS,
            COUNTS,
            DEMOGRAPHICS,
            _kept(),
        )
