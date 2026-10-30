"""DATA-05 to DATA-10 per record: prepare_record, the .npz round trip, prepare_ds1."""

import json
from pathlib import Path

import numpy as np
import pytest

from heartbeat.config import DataSettings, FoldSettings, Settings
from heartbeat.constants import ADU_PER_MV, FS_HZ, WINDOW_SAMPLES
from heartbeat.data import prepare as prepare_module
from heartbeat.data.loader import SealedRecordError
from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import (
    FloorHitLimitError,
    PreparedRecord,
    load_prepared,
    prepare_ds1,
    prepare_record,
    save_prepared,
)
from heartbeat.data.records import RawRecord
from heartbeat.signal.filter import bandpass_mv, to_adu
from heartbeat.signal.rr import rr_features

N_SAMPLES = 20 * FS_HZ
# Seven annotations: five beats (one Q), a rhythm marker and a noise marker.
ANN_SAMPLE = np.array([400, 700, 700, 1000, 1300, 1500, 1900], dtype=np.int64)
ANN_SYMBOL = ("N", "+", "A", "Q", "~", "V", "N")
BEAT_SAMPLE = np.array([400, 700, 1000, 1500, 1900], dtype=np.int64)


def _signal_mv(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t_s = np.arange(N_SAMPLES) / FS_HZ
    return np.sin(2 * np.pi * 1.2 * t_s) + 0.1 * rng.standard_normal(N_SAMPLES)


def _raw(record_id: str = "101", seed: int = 0) -> RawRecord:
    return RawRecord(
        record_id=record_id,
        mlii_mv=_signal_mv(seed),
        ann_sample=ANN_SAMPLE,
        ann_symbol=ANN_SYMBOL,
    )


def test_non_beats_are_dropped_and_beats_keep_their_symbols() -> None:
    prepared = prepare_record(_raw(), "s101")
    assert prepared.beat_sample.tolist() == BEAT_SAMPLE.tolist()
    assert prepared.beat_symbol.tolist() == ["N", "A", "Q", "V", "N"]
    assert prepared.beat_class.tolist() == ["N", "S", "Q", "V", "N"]


def test_first_and_last_beat_are_not_kept() -> None:
    prepared = prepare_record(_raw(), "s101")
    assert prepared.kept.tolist() == [False, True, True, True, False]


def test_q_beat_is_kept_for_rr_with_class_q() -> None:
    prepared = prepare_record(_raw(), "s101")
    q = prepared.beat_symbol.tolist().index("Q")
    assert prepared.kept[q]
    assert prepared.beat_class[q] == "Q"


@pytest.mark.rule("R9")
def test_rr_uses_the_q_beat_as_an_endpoint_and_ignores_non_beats() -> None:
    prepared = prepare_record(_raw(), "s101")
    # Kept beats: A at 700, Q at 1000, V at 1500. The V's pre-RR runs from the
    # Q, and the rhythm marker at 700 and noise marker at 1300 change nothing.
    np.testing.assert_array_equal(prepared.rr_s, rr_features(BEAT_SAMPLE))
    assert prepared.rr_s[2, 0] == 500 / FS_HZ
    assert prepared.rr_s[0, 0] == 300 / FS_HZ


def test_rr_rows_line_up_with_kept_beats() -> None:
    prepared = prepare_record(_raw(), "s101")
    assert prepared.rr_s.shape == (int(prepared.kept.sum()), 6)


def test_trace_is_the_filtered_lead_in_int16_units() -> None:
    raw = _raw()
    prepared = prepare_record(raw, "s101")
    assert prepared.trace_adu.dtype == np.int16
    np.testing.assert_array_equal(prepared.trace_adu, to_adu(bandpass_mv(raw.mlii_mv)))
    assert abs(prepared.trace_adu.max() / ADU_PER_MV) < 2


def test_record_and_subject_are_carried() -> None:
    prepared = prepare_record(_raw("203"), "s203")
    assert prepared.record_id == "203"
    assert prepared.subject_id == "s203"


def test_kept_beat_whose_window_leaves_the_record_raises() -> None:
    from heartbeat.signal.windows import WindowRangeError

    raw = RawRecord(
        record_id="101",
        mlii_mv=_signal_mv(),
        ann_sample=np.array([10, 50, 400, 800], dtype=np.int64),
        ann_symbol=("N", "N", "N", "N"),
    )
    with pytest.raises(WindowRangeError, match="101"):
        prepare_record(raw, "s101")


def test_round_trip_is_exact(tmp_path: Path) -> None:
    prepared = prepare_record(_raw(), "s101")
    path = tmp_path / "101.npz"
    save_prepared(prepared, path)
    loaded = load_prepared(path)
    assert loaded.record_id == prepared.record_id
    assert loaded.subject_id == prepared.subject_id
    for field in (
        "trace_adu",
        "beat_sample",
        "beat_symbol",
        "beat_class",
        "kept",
        "rr_s",
    ):
        a, b = getattr(loaded, field), getattr(prepared, field)
        assert a.dtype == b.dtype, field
        np.testing.assert_array_equal(a, b, err_msg=field)


def test_save_is_atomic_and_leaves_no_temporary(tmp_path: Path) -> None:
    save_prepared(prepare_record(_raw(), "s101"), tmp_path / "101.npz")
    assert [p.name for p in tmp_path.iterdir()] == ["101.npz"]


def test_load_rejects_a_file_named_for_another_record(tmp_path: Path) -> None:
    save_prepared(prepare_record(_raw("101"), "s101"), tmp_path / "106.npz")
    with pytest.raises(ValueError, match=r"106.*101"):
        load_prepared(tmp_path / "106.npz")


# prepare_ds1

SPLITS = Splits(
    ds1=("101", "106"),
    ds2=("100", "103"),
    excluded={"102": "paced", "202": "same subject as 201"},
    lead="MLII",
)
SUBJECTS = {"100": "s100", "101": "s101", "102": "s102", "103": "s103", "106": "s106"}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data=DataSettings(
            raw_dir=tmp_path / "raw",
            prepared_dir=tmp_path / "prepared",
            sources=("https://a.example/",),
        ),
        folds=FoldSettings(seed=1),
    )


def _fake_reader(calls: list[str]) -> object:
    def read(raw_dir: Path, record_id: str, lead: str) -> RawRecord:
        calls.append(record_id)
        assert lead == "MLII"
        return _raw(record_id, seed=int(record_id))

    return read


@pytest.mark.rule("R15")
@pytest.mark.parametrize("record", ["100", "103", "102", "202", "999"])
def test_prepare_ds1_refuses_a_non_ds1_record_before_reading_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: str
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(prepare_module, "read_record", _fake_reader(calls))
    with pytest.raises(SealedRecordError, match=record):
        prepare_ds1(_settings(tmp_path), SPLITS, SUBJECTS, records=["101", record])
    assert calls == []
    assert not (tmp_path / "prepared").exists()


def test_prepare_ds1_writes_every_ds1_record_and_the_floor_hit_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(prepare_module, "read_record", _fake_reader(calls))
    report = prepare_ds1(_settings(tmp_path), SPLITS, SUBJECTS)
    assert calls == ["101", "106"]
    prepared = tmp_path / "prepared"
    assert sorted(p.name for p in prepared.iterdir()) == [
        "101.npz",
        "106.npz",
        "floor_hits.json",
    ]
    assert load_prepared(prepared / "106.npz").subject_id == "s106"
    floor = json.loads((prepared / "floor_hits.json").read_text(encoding="utf-8"))
    assert set(floor["records"]) == {"101", "106"}
    assert floor["total_hits"] == 0 == report.total_hits
    assert floor["limit"] == 5
    assert floor["records"]["101"]["hits"] == 0
    assert floor["records"]["101"]["min_std_adu"] > 2.0


def test_floor_hits_are_counted_and_more_than_five_stop_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A flat lead: every kept window is constant, so all hit the floor.
    flat_samples = np.array([400 + 300 * k for k in range(9)], dtype=np.int64)

    def read(raw_dir: Path, record_id: str, lead: str) -> RawRecord:
        return RawRecord(
            record_id=record_id,
            mlii_mv=np.zeros(N_SAMPLES),
            ann_sample=flat_samples,
            ann_symbol=("N",) * flat_samples.size,
        )

    monkeypatch.setattr(prepare_module, "read_record", read)
    with pytest.raises(FloorHitLimitError, match=r"14 .*limit 5"):
        prepare_ds1(_settings(tmp_path), SPLITS, SUBJECTS)
    floor = json.loads(
        (tmp_path / "prepared" / "floor_hits.json").read_text(encoding="utf-8")
    )
    assert floor["records"]["101"] == {"hits": 7, "min_std_adu": 0.0}
    assert floor["total_hits"] == 14


def test_windows_are_256_samples_for_every_kept_beat() -> None:
    from heartbeat.signal.windows import extract_windows

    prepared: PreparedRecord = prepare_record(_raw(), "s101")
    windows = extract_windows(prepared.trace_adu, prepared.beat_sample[prepared.kept])
    assert windows.shape == (3, WINDOW_SAMPLES)
