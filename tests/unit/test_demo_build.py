"""`build-demo-data` on synthetic DS1 records (Phase 6 Task A2; R31, R32).

The committed `models/heartbeat-v1/` files and `results/export.json` label
the synthetic beats, so these tests need no download.
"""

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from demo_support import write_prepared

from heartbeat.constants import AAMI_CLASS, FS_HZ
from heartbeat.data.loader import SealedRecordError
from heartbeat.data.manifests import Splits, load_beat_counts, load_splits
from heartbeat.data.npz import PreparedRecord, load_prepared
from heartbeat.demo.build import (
    PROBABILITY_SCALE,
    DemoSplitError,
    build_demo_data,
    choose_default_record,
    decode_beats,
    default_start_s,
    encode_beats,
)
from heartbeat.demo.manifest import MANIFEST_NAME, check_manifest
from heartbeat.evaluate.calibration import calibrated_probs
from heartbeat.models.augment import model_windows
from heartbeat.models.inputs import apply_rr_scaler, rr_model_inputs
from heartbeat.paths import (
    BEAT_COUNTS_MANIFEST,
    MODELS_DIR,
    RESULTS_DIR,
    SPLITS_MANIFEST,
)
from heartbeat.sealed.score import (
    load_calibration,
    load_scaler,
    onnx_logits,
    onnx_session,
)
from heartbeat.signal.windows import extract_windows

EXPORT_RECORD: dict[str, Any] = json.loads(
    (RESULTS_DIR / "export.json").read_text(encoding="utf-8")
)
HASHED = re.compile(r"^(?P<stem>[^.]+)\.(?P<hash>[0-9a-f]{8})(?P<suffix>\..+)$")


@pytest.fixture(scope="module")
def splits() -> Splits:
    return load_splits(SPLITS_MANIFEST)


@pytest.fixture
def prepared_dir(tmp_path: Path) -> Path:
    return write_prepared(tmp_path / "prepared")


Reader = Callable[[Path], PreparedRecord]


def build(
    prepared_dir: Path,
    out_dir: Path,
    splits: Splits,
    records: tuple[str, ...] = ("101", "223"),
    log_path: Path | None = None,
    read: Reader = load_prepared,
) -> dict[str, Any]:
    return build_demo_data(
        records,
        prepared_dir,
        MODELS_DIR,
        EXPORT_RECORD,
        log_path if log_path is not None else out_dir.parent / "no-log.jsonl",
        out_dir,
        splits,
        read=read,
    )


def test_every_file_but_the_manifest_is_named_by_its_content(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    out = tmp_path / "data"
    build(prepared_dir, out, splits)
    names = sorted(p.name for p in out.iterdir())
    assert MANIFEST_NAME in names
    for name in names:
        if name == MANIFEST_NAME:
            continue
        match = HASHED.match(name)
        assert match, name
        digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
        assert match["hash"] == digest[:8], name
    matches = [HASHED.match(n) for n in names if n != MANIFEST_NAME]
    stems = {m["stem"] + m["suffix"] for m in matches if m}
    assert {
        "101.trace.i16",
        "101.beats.json",
        "223.trace.i16",
        "223.beats.json",
        "model.onnx",
        "scaler.json",
        "calibration.json",
        "NOTICE.txt",
        "ATTRIBUTION.txt",
    } <= stems


def test_trace_file_is_the_prepared_trace_as_little_endian_int16(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    out = tmp_path / "data"
    manifest = build(prepared_dir, out, splits)
    entry = next(r for r in manifest["records"] if r["record"] == "223")
    data = np.frombuffer((out / entry["trace"]["name"]).read_bytes(), dtype="<i2")
    expected = load_prepared(prepared_dir / "223.npz").trace_adu
    assert np.array_equal(data, expected)


def test_beats_format_round_trips() -> None:
    sample = np.array([100, 388, 676, 876, 1164], dtype=np.int64)
    classes = np.array(list("NNVQN"))
    kept = np.array([False, True, True, True, False])
    labels = np.array(list("NVN"))
    probs = np.array(
        [[0.9, 0.05, 0.03, 0.02], [1e-9, 0.25, 0.75, 0.0], [0.5, 0.5, 0.0, 0.0]]
    )
    payload = encode_beats("223", sample, classes, kept, labels, probs)
    decoded = decode_beats(payload)
    assert decoded["record"] == "223"
    assert np.array_equal(decoded["sample"], sample)
    assert "".join(decoded["class"]) == "NNVQN"
    assert np.array_equal(decoded["kept"], kept)
    assert "".join(decoded["label"]) == "NVN"
    assert np.max(np.abs(decoded["probabilities"] - probs)) <= 0.5 / PROBABILITY_SCALE
    # Compact and deterministic: no spaces, the same bytes every time.
    assert b" " not in payload
    assert encode_beats("223", sample, classes, kept, labels, probs) == payload


def test_stored_labels_and_probabilities_are_onnx_runtimes(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    out = tmp_path / "data"
    manifest = build(prepared_dir, out, splits)
    entry = next(r for r in manifest["records"] if r["record"] == "223")
    decoded = decode_beats((out / entry["beats"]["name"]).read_bytes())
    record = load_prepared(prepared_dir / "223.npz")
    scaler = load_scaler(MODELS_DIR / "scaler.json")
    calibration = load_calibration(MODELS_DIR / "calibration.json")
    logits = onnx_logits(
        onnx_session(MODELS_DIR / "model.onnx"),
        model_windows(
            extract_windows(record.trace_adu, record.beat_sample[record.kept])
        ),
        apply_rr_scaler(scaler, rr_model_inputs(record.rr_s)).astype(np.float32),
    ).astype(np.float64)
    probs = calibrated_probs(
        logits - calibration.log_class_weights,
        calibration.temperature,
    )
    labels = np.array(["N", "S", "V", "F"])[np.argmax(logits, axis=1)]
    assert "".join(decoded["label"]) == "".join(labels)
    assert np.max(np.abs(decoded["probabilities"] - probs)) <= 0.5 / PROBABILITY_SCALE


@pytest.mark.rule("R31")
def test_manifest_hashes_and_sizes_equal_the_files(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    out = tmp_path / "data"
    manifest = build(prepared_dir, out, splits)
    assert check_manifest(out) == []
    listed = [manifest["model"][k] for k in ("model", "scaler", "calibration")]
    for record in manifest["records"]:
        listed += [record["trace"], record["beats"]]
    for entry in listed:
        data = (out / entry["name"]).read_bytes()
        assert entry["bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()


@pytest.mark.rule("R31")
def test_manifest_check_catches_a_changed_missing_or_unlisted_file(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    out = tmp_path / "data"
    manifest = build(prepared_dir, out, splits)
    trace = out / manifest["records"][0]["trace"]["name"]
    data = bytearray(trace.read_bytes())
    data[10] ^= 1
    trace.write_bytes(bytes(data))
    assert any(trace.name in p for p in check_manifest(out))
    trace.unlink()
    assert any(trace.name in p for p in check_manifest(out))
    (out / "stray.bin").write_bytes(b"x")
    assert any("stray.bin" in p for p in check_manifest(out))


def test_manifest_names_the_split_model_and_default(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    manifest = build(prepared_dir, tmp_path / "data", splits)
    assert manifest["split"] == "DS1"
    model_file = next(
        f for f in EXPORT_RECORD["files"] if f["path"].endswith("v1/model.onnx")
    )
    assert manifest["model"]["sha256"] == model_file["sha256"]
    assert manifest["model"]["model"]["sha256"] == model_file["sha256"]
    assert manifest["probability_scale"] == PROBABILITY_SCALE
    assert "MIT-BIH Arrhythmia Database" in manifest["attribution"]
    assert [r["record"] for r in manifest["records"]] == ["101", "223"]
    counts = {r["record"]: r["counts"] for r in manifest["records"]}
    # Kept beats only: the first and last beat of each record are dropped.
    assert counts["101"] == {"N": 38, "S": 0, "V": 0, "F": 0, "Q": 0}
    assert counts["223"] == {"N": 59, "S": 26, "V": 26, "F": 0, "Q": 1}
    assert manifest["default"] == {"record": "223", "start_s": 20}


def test_manifest_refuses_a_model_that_differs_from_the_export_record(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    record = json.loads(json.dumps(EXPORT_RECORD))
    for entry in record["files"]:
        if entry["path"].endswith("v1/model.onnx"):
            entry["sha256"] = "0" * 64
    with pytest.raises(ValueError, match=r"model\.onnx"):
        build_demo_data(
            ("101",),
            prepared_dir,
            MODELS_DIR,
            record,
            tmp_path / "no-log.jsonl",
            tmp_path / "data",
            splits,
        )


def test_two_builds_are_byte_identical(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    build(prepared_dir, first, splits)
    build(prepared_dir, second, splits)
    names = sorted(p.name for p in first.iterdir())
    assert names == sorted(p.name for p in second.iterdir())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_a_rebuild_replaces_the_folder_and_leaves_no_stale_files(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    out = tmp_path / "data"
    build(prepared_dir, out, splits)
    (out / "101.00000000.trace.i16").write_bytes(b"old")
    build(prepared_dir, out, splits, records=("223",))
    assert check_manifest(out) == []
    assert not any(p.name.startswith("101.") for p in out.iterdir())


def _counts(s: int, v: int) -> dict[str, int]:
    return {"N": 1000, "S": s, "V": v, "F": 0, "Q": 0}


def test_default_record_is_most_s_plus_v_among_records_with_25_of_each() -> None:
    counts = {
        "101": _counts(3, 0),
        "201": _counts(30, 200),
        "207": _counts(25, 100),
        "208": _counts(2, 990),  # most V, but too few S
        "223": _counts(73, 473),
    }
    assert choose_default_record(counts) == "223"


@pytest.mark.rule("R43")
def test_the_rule_picks_200_on_ds2s_published_counts() -> None:
    """Phase 7 design call 6: D4's rule on PhysioNet's table, the counts D4 used.

    The table counts every annotation of the record; the built manifest counts
    kept beats only, which Goal B checks on the real DS2 build.
    """
    published = load_beat_counts(BEAT_COUNTS_MANIFEST)
    counts = {}
    for record in load_splits(SPLITS_MANIFEST).ds2:
        by_class = dict.fromkeys(("N", "S", "V", "F", "Q"), 0)
        for symbol, n in published[record].items():
            if symbol in AAMI_CLASS:
                by_class[AAMI_CLASS[symbol]] += n
        counts[record] = by_class
    assert choose_default_record(counts) == "200"


def test_default_record_tie_goes_to_the_lower_record_id() -> None:
    assert choose_default_record({"209": _counts(50, 50), "201": _counts(40, 60)}) == (
        "201"
    )


def test_default_record_needs_one_qualifying_record() -> None:
    with pytest.raises(ValueError, match="25"):
        choose_default_record({"101": _counts(24, 900), "208": _counts(25, 24)})


def test_default_start_is_the_first_10_second_span_with_an_s_or_v_beat() -> None:
    sample = np.array([0, 10, 20, 40, 55], dtype=np.int64) * FS_HZ
    classes = np.array(list("NNNVS"))
    kept = np.array([False, True, True, True, False])
    assert default_start_s(sample, classes, kept) == 40
    # An S or V among the dropped beats does not count.
    assert default_start_s(sample, np.array(list("VNNNS")), kept) == 0


@pytest.mark.rule("R32")
@pytest.mark.parametrize("asked", ["100", "232", "202", "999"])
def test_refuses_a_record_outside_ds1_before_opening_any_file(
    prepared_dir: Path, tmp_path: Path, splits: Splits, asked: str
) -> None:
    opened: list[Path] = []

    def spy(path: Path) -> PreparedRecord:
        opened.append(path)
        return load_prepared(path)

    with pytest.raises(SealedRecordError, match=asked):
        build(prepared_dir, tmp_path / "data", splits, ("101", asked), read=spy)
    assert opened == []
    assert not (tmp_path / "data").exists()


@pytest.mark.rule("R32")
def test_with_no_sealed_entry_the_build_is_ds1_and_opens_only_ds1_files(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    opened: list[str] = []

    def spy(path: Path) -> PreparedRecord:
        opened.append(path.stem)
        return load_prepared(path)

    manifest = build(prepared_dir, tmp_path / "data", splits, read=spy)
    assert opened == ["101", "223"]
    assert set(opened) <= set(splits.ds1)
    assert manifest["split"] == "DS1"


@pytest.mark.rule("R32")
def test_a_sealed_entry_stops_the_ds1_build(
    prepared_dir: Path, tmp_path: Path, splits: Splits
) -> None:
    log = tmp_path / "test_runs.jsonl"
    entry = {
        "commit": "0" * 40,
        "date": "2026-11-20",
        "freeze_sha256": "0" * 64,
        "id": 1,
        "report": "results/test_runs/1-sealed.json",
        "report_sha256": "0" * 64,
        "type": "sealed",
    }
    log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    with pytest.raises(DemoSplitError, match="Phase 7"):
        build(prepared_dir, tmp_path / "data", splits, log_path=log)
    assert not (tmp_path / "data").exists()
