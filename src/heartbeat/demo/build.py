"""`heartbeat build-demo-data`: the browser demo's data files (Phase 6 design call 2).

Per record, from the prepared DS1 file: `NNN.<hash8>.trace.i16` (the canonical
trace as little-endian int16 at 360 Hz, 200 units per mV) and
`NNN.<hash8>.beats.json`, columnar: every annotated beat's sample
(delta-encoded), its expert AAMI class as one string, the kept mask (DATA-08),
and for each kept beat the shipped seed-0 label and its four calibrated
probabilities as integers over `PROBABILITY_SCALE`. The labels come from
Python ONNX Runtime on the committed `model.onnx`, through the scoring path
the sealed run uses; nothing is retrained. The model files, a copy of the
model's `NOTICE` and an attribution note ship beside them with hashed names,
and `manifest.json` lists everything (DEMO-08).

Until a sealed run is logged the build is DS1 only (DEMO-17, R32): a record
outside DS1 stops it before any file is opened. Once the log holds a sealed
entry it is DS2 only (Phase 7 design call 3): each record is prepared in
memory from the raw cache as the sealed run does, never written to
`data/prepared/`; the model files must match the freeze record the report
names; and the seed-0 counts must equal the report the last sealed entry
names, checked before any file is written (settling 4, design call 4).
"""

import json
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import ADU_PER_MV, FS_HZ, SCORED_CLASSES, SHIPPED_SEED
from heartbeat.data.loader import require_ds1
from heartbeat.data.manifests import Splits
from heartbeat.data.npz import PreparedRecord, load_prepared
from heartbeat.data.prepare import prepare_in_memory
from heartbeat.demo.manifest import MANIFEST_NAME, file_entry, hashed_name
from heartbeat.demo.sealed_check import check_against_sealed
from heartbeat.evaluate.calibration import calibrated_probs, predict_labels
from heartbeat.export.bundle import ATTRIBUTION_NOTICE, FREEZE_NAME
from heartbeat.export.freeze import FreezeError
from heartbeat.models.augment import model_windows
from heartbeat.models.inputs import apply_rr_scaler, rr_model_inputs
from heartbeat.paths import REPO_ROOT
from heartbeat.runs import canonical_json
from heartbeat.sealed.log import check_log, read_log
from heartbeat.sealed.score import (
    Calibration,
    load_calibration,
    load_scaler,
    onnx_logits,
    onnx_session,
)
from heartbeat.signal.windows import extract_windows

# Design call 2: millionths, so rounding moves a probability by at most 5e-7
# (a twentieth of the 1e-5 parity tolerance). Ten-millionths were the first
# choice, but put record 215's beats file at 111,657 bytes, over the 100 KB
# gate (ledger, Phase 6 Goal A).
PROBABILITY_SCALE = 1_000_000

# D5, R39: each beats file is under 100 KB uncompressed. Kept here, not in
# constants.py, so adding it left the training stages' fingerprints alone.
BEATS_SIZE_LIMIT_BYTES = 100_000

# Every annotated class, in the order the counts list them.
DEMO_CLASSES = (*SCORED_CLASSES, "Q")

# D4's default rule: most S plus V beats among records with at least this
# many of each.
DEFAULT_MIN_EACH = 25
# Design call 5: the visible span and the unit of playback pages.
SPAN_S = 10

# Gitignored, written only by this module (design call 2). Here rather than in
# paths.py for the same fingerprint reason.
DEMO_DATA_DIR = REPO_ROOT / "web" / "public" / "data"

SPLIT_DS1 = "DS1"
SPLIT_DS2 = "DS2"
MODEL_VERSION = "heartbeat-v1"

ATTRIBUTION_TEXT = f"""Heartbeat demo data

The traces and beat annotations in this folder come from the MIT-BIH
Arrhythmia Database. The traces are the MLII lead, band-pass filtered from
0.5 to 40 Hz and stored as int16 at 200 units per mV; each beat's class is the
database's expert annotation mapped to the AAMI classes N, S, V, F and Q. The
model labels come from the heartbeat-v1 model, whose NOTICE ships beside it.

{ATTRIBUTION_NOTICE}
https://opendatacommons.org/licenses/by/1-0/

Moody G, Mark R. MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet (2005).
https://doi.org/10.13026/C2F305
"""


class DemoRecordError(PermissionError):
    """A sealed run is logged and a record outside DS2 was asked for (DEMO-17)."""


Reader = Callable[[Path], PreparedRecord]
Preparer = Callable[[Path, str, str, str], PreparedRecord]


def _sealed_entries(log_path: Path) -> list[dict[str, Any]]:
    return [entry for entry in read_log(log_path) if entry["type"] == "sealed"]


def demo_records(splits: Splits, log_path: Path) -> tuple[str, ...]:
    """Every record of the split the demo uses: DS1 until a sealed run, then DS2."""
    return splits.ds2 if _sealed_entries(log_path) else splits.ds1


def require_demo_split(records: Sequence[str], splits: Splits, log_path: Path) -> str:
    """The split the demo data may use, checked before any file is opened (R32).

    Returns:
        "DS1" while no sealed run is logged, "DS2" once one is.

    Raises:
        SealedRecordError: If no sealed run is logged and a record is outside DS1.
        DemoRecordError: If a sealed run is logged and a record is outside DS2.
    """
    if not _sealed_entries(log_path):
        require_ds1(records, splits)
        return SPLIT_DS1
    for record in records:
        if record not in splits.ds2:
            raise DemoRecordError(
                f"a sealed run is logged, so the demo data is DS2 only (Phase 7, "
                f"DEMO-17): record {record} is not in DS2"
            )
    return SPLIT_DS2


def last_sealed_report(
    log_path: Path, log_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The log's last sealed entry and the report it names, checked (R42).

    Raises:
        LogError: If the log or any report differs from what it records.
    """
    check_log(log_path, log_root)
    entry = _sealed_entries(log_path)[-1]
    report: dict[str, Any] = json.loads(
        (log_root / entry["report"]).read_text(encoding="utf-8")
    )
    return entry, report


def _require_frozen(models_dir: Path, report: Mapping[str, Any]) -> None:
    """The model files to ship are the ones the sealed report's freeze recorded.

    Raises:
        FreezeError: On a missing record, another freeze commit, or a file whose
            SHA256 differs from the record.
    """
    path = models_dir / FREEZE_NAME
    if not path.is_file():
        raise FreezeError(f"no freeze record at {path}, yet a sealed run is logged")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["commit"] != report["freeze_commit"]:
        raise FreezeError(
            f"the freeze record names {record['commit'][:12]}, the sealed report "
            f"{str(report['freeze_commit'])[:12]}"
        )
    for name in ("model.onnx", "scaler.json", "calibration.json", "NOTICE"):
        expected = record["models"].get(f"models/{MODEL_VERSION}/{name}")
        if file_entry(name, (models_dir / name).read_bytes())["sha256"] != expected:
            raise FreezeError(f"{models_dir / name} differs from the freeze record")


def kept_counts(record: PreparedRecord) -> dict[str, int]:
    """Expert class counts of the kept beats (the first and last are dropped)."""
    classes = record.beat_class[record.kept].tolist()
    return {cls: classes.count(cls) for cls in DEMO_CLASSES}


def choose_default_record(counts: Mapping[str, Mapping[str, int]]) -> str:
    """D4's rule on expert labels only: most S plus V among records with 25 of each.

    A tie goes to the lower record ID.

    Raises:
        ValueError: If no record has 25 S and 25 V beats.
    """
    qualifying = [
        (-(c["S"] + c["V"]), record)
        for record, c in counts.items()
        if c["S"] >= DEFAULT_MIN_EACH and c["V"] >= DEFAULT_MIN_EACH
    ]
    if not qualifying:
        raise ValueError(
            f"no record has at least {DEFAULT_MIN_EACH} S and "
            f"{DEFAULT_MIN_EACH} V beats"
        )
    return min(qualifying)[1]


def default_start_s(
    beat_sample: NDArray[np.int64],
    beat_class: NDArray[np.str_],
    kept: NDArray[np.bool_],
) -> int:
    """Start of the first 10-second span holding a kept S or V beat (D4).

    Spans are the 10-second pages from the start of the recording; with no
    kept S or V beat the start is 0.
    """
    irregular = kept & np.isin(beat_class, ("S", "V"))
    if not irregular.any():
        return 0
    first_s = int(beat_sample[np.argmax(irregular)]) // FS_HZ
    return first_s - first_s % SPAN_S


def label_kept_beats(
    record: PreparedRecord,
    session: Any,
    scaler: Any,
    calibration: Calibration,
) -> tuple[NDArray[np.str_], NDArray[np.float64]]:
    """The seed-0 label and calibrated probabilities of every kept beat, Q included.

    The sealed run's scoring path: z-scored windows and scaled RR inputs into
    ONNX Runtime, the label the argmax of the raw logits, the probabilities
    softmax of the adjusted logits over the temperature (EVAL-11).
    """
    windows = model_windows(
        extract_windows(record.trace_adu, record.beat_sample[record.kept])
    )
    rr = apply_rr_scaler(scaler, rr_model_inputs(record.rr_s)).astype(np.float32)
    logits = onnx_logits(session, windows, rr).astype(np.float64)
    # As the sealed report adjusts them (EVAL-11).
    adjusted = logits - calibration.log_class_weights
    probs = calibrated_probs(adjusted, calibration.temperature)
    return predict_labels(logits), probs


def _compact_json(payload: Any) -> bytes:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (text + "\n").encode("utf-8")


def encode_beats(
    record_id: str,
    beat_sample: NDArray[np.int64],
    beat_class: NDArray[np.str_],
    kept: NDArray[np.bool_],
    labels: NDArray[np.str_],
    probs: NDArray[np.float64],
) -> bytes:
    """One record's `beats.json`, compact and deterministic."""
    assert labels.shape == (int(kept.sum()),), labels.shape
    assert probs.shape == (labels.size, len(SCORED_CLASSES)), probs.shape
    scaled = np.rint(probs * PROBABILITY_SCALE).astype(np.int64)
    payload = {
        "record": record_id,
        "fs_hz": FS_HZ,
        "sample_delta": np.diff(beat_sample, prepend=0).tolist(),
        "class": "".join(beat_class.tolist()),
        "kept": "".join("1" if k else "0" for k in kept.tolist()),
        "label": "".join(labels.tolist()),
        "probability_scale": PROBABILITY_SCALE,
        "probabilities": {
            cls: scaled[:, k].tolist() for k, cls in enumerate(SCORED_CLASSES)
        },
    }
    return _compact_json(payload)


def decode_beats(data: bytes) -> dict[str, Any]:
    """Read a `beats.json` back into arrays, the inverse of `encode_beats`."""
    payload = json.loads(data)
    scale = payload["probability_scale"]
    return {
        "record": payload["record"],
        "sample": np.cumsum(np.array(payload["sample_delta"], dtype=np.int64)),
        "class": np.array(list(payload["class"])),
        "kept": np.array([c == "1" for c in payload["kept"]], dtype=np.bool_),
        "label": np.array(list(payload["label"])),
        "probabilities": np.column_stack(
            [
                np.array(payload["probabilities"][cls], dtype=np.float64) / scale
                for cls in SCORED_CLASSES
            ]
        ),
    }


def _export_sha256(export_record: Mapping[str, Any], name: str) -> str:
    for entry in export_record["files"]:
        if entry["path"] == f"models/{MODEL_VERSION}/{name}":
            sha256: str = entry["sha256"]
            return sha256
    raise ValueError(f"results/export.json lists no {name}")


def _model_files(
    models_dir: Path, export_record: Mapping[str, Any]
) -> dict[str, tuple[str, bytes]]:
    """The model files to copy, checked against `results/export.json`."""
    files = {}
    for key, name, stem, suffix in (
        ("model", "model.onnx", "model", ".onnx"),
        ("scaler", "scaler.json", "scaler", ".json"),
        ("calibration", "calibration.json", "calibration", ".json"),
        ("notice", "NOTICE", "NOTICE", ".txt"),
    ):
        data = (models_dir / name).read_bytes()
        if file_entry(name, data)["sha256"] != _export_sha256(export_record, name):
            raise ValueError(
                f"{models_dir / name} differs from its SHA256 in results/export.json"
            )
        files[key] = (hashed_name(stem, suffix, data), data)
    return files


def _replace_folder(built: Path, out_dir: Path) -> None:
    if out_dir.exists():
        old = Path(tempfile.mkdtemp(dir=out_dir.parent, prefix=f".{out_dir.name}.old-"))
        out_dir.replace(old / out_dir.name)
        built.replace(out_dir)
        shutil.rmtree(old)
    else:
        built.replace(out_dir)


def build_demo_data(
    records: Sequence[str],
    prepared_dir: Path,
    models_dir: Path,
    export_record: Mapping[str, Any],
    log_path: Path,
    out_dir: Path,
    splits: Splits,
    read: Reader = load_prepared,
    *,
    raw_dir: Path | None = None,
    subjects: Mapping[str, str] | None = None,
    log_root: Path = REPO_ROOT,
    prepare: Preparer = prepare_in_memory,
) -> dict[str, Any]:
    """Write the demo data folder and return its manifest.

    Args:
        records: Records to ship, in picker order.
        prepared_dir: Folder written by `heartbeat prepare` (DS1 only).
        models_dir: `models/heartbeat-v1/`.
        export_record: `results/export.json`, whose SHA256 the copied model
            files must match.
        log_path: The sealed-run log, read for the split rule (R32).
        out_dir: The folder to replace, `web/public/data/`.
        splits: The split manifest.
        read: Reads one prepared DS1 file; tests spy on it.
        raw_dir: The download cache, read for DS2 after a sealed run.
        subjects: Record to patient, needed for DS2.
        log_root: The folder the log's report paths are relative to.
        prepare: Prepares one DS2 record in memory; tests spy on it.

    Raises:
        SealedRecordError: If no sealed run is logged and a record is outside
            DS1, before anything is read.
        DemoRecordError: If a sealed run is logged and a record is outside DS2,
            before anything is read.
        LogError: If the log or a report differs from what it records.
        FreezeError: If a model file differs from the freeze record.
        SealedMismatchError: If the seed-0 counts differ from the sealed report,
            before any file is written.
        ValueError: If a model file differs from `results/export.json`.
    """
    split = require_demo_split(records, splits, log_path)
    sealed: tuple[dict[str, Any], dict[str, Any]] | None = None
    if split == SPLIT_DS2:
        if raw_dir is None or subjects is None:
            raise ValueError("a DS2 build needs the raw cache and the subjects")
        sealed = last_sealed_report(log_path, log_root)
        _require_frozen(models_dir, sealed[1])
    model_files = _model_files(models_dir, export_record)
    session = onnx_session(models_dir / "model.onnx")
    scaler = load_scaler(models_dir / "scaler.json")
    calibration = load_calibration(models_dir / "calibration.json")

    files: dict[str, bytes] = dict(model_files.values())
    attribution = ATTRIBUTION_TEXT.encode("utf-8")
    attribution_name = hashed_name("ATTRIBUTION", ".txt", attribution)
    files[attribution_name] = attribution
    entries: list[dict[str, Any]] = []
    starts: dict[str, int] = {}
    labels_by_record: dict[str, NDArray[np.str_]] = {}
    classes_by_record: dict[str, NDArray[np.str_]] = {}
    for record_id in records:
        if sealed is None:
            record = read(prepared_dir / f"{record_id}.npz")
            require_ds1([record.record_id], splits)
        else:
            assert raw_dir is not None
            assert subjects is not None
            # Design call 3: in memory, as the sealed run reads DS2.
            record = prepare(raw_dir, record_id, splits.lead, subjects[record_id])
        labels, probs = label_kept_beats(record, session, scaler, calibration)
        labels_by_record[record_id] = labels
        classes_by_record[record_id] = record.beat_class[record.kept]
        trace = record.trace_adu.astype("<i2").tobytes()
        beats = encode_beats(
            record_id,
            record.beat_sample,
            record.beat_class,
            record.kept,
            labels,
            probs,
        )
        trace_name = hashed_name(record_id, ".trace.i16", trace)
        beats_name = hashed_name(record_id, ".beats.json", beats)
        files[trace_name] = trace
        files[beats_name] = beats
        starts[record_id] = default_start_s(
            record.beat_sample, record.beat_class, record.kept
        )
        entries.append(
            {
                "record": record_id,
                "counts": kept_counts(record),
                "duration_s": record.trace_adu.size / FS_HZ,
                "trace": file_entry(trace_name, trace),
                "beats": file_entry(beats_name, beats),
            }
        )
    sealed_run: dict[str, Any] = {}
    if sealed is not None:
        assert subjects is not None
        entry, report = sealed
        # Settling 4: before any file is written.
        check_against_sealed(labels_by_record, classes_by_record, report, subjects)
        sealed_run = {"sealed_run": {"id": entry["id"], "report": entry["report"]}}
    default = choose_default_record({e["record"]: e["counts"] for e in entries})
    manifest = {
        "label": (
            "Heartbeat demo data: expert annotations and the shipped seed-0 "
            "model's Python labels per kept beat (DEMO-08)"
        ),
        "split": split,
        "fs_hz": FS_HZ,
        "adu_per_mv": ADU_PER_MV,
        "probability_scale": PROBABILITY_SCALE,
        "classes": list(SCORED_CLASSES),
        "default": {"record": default, "start_s": starts[default]},
        "attribution": ATTRIBUTION_NOTICE,
        "attribution_file": file_entry(attribution_name, attribution),
        "model": {
            "version": MODEL_VERSION,
            "seed": SHIPPED_SEED,
            "sha256": _export_sha256(export_record, "model.onnx"),
            **{
                key: file_entry(name, data) for key, (name, data) in model_files.items()
            },
        },
        "records": entries,
        **sealed_run,
    }
    files[MANIFEST_NAME] = canonical_json(manifest).encode("utf-8")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    built = Path(tempfile.mkdtemp(dir=out_dir.parent, prefix=f".{out_dir.name}.new-"))
    try:
        for name, data in sorted(files.items()):
            (built / name).write_bytes(data)
        _replace_folder(built, out_dir)
    except BaseException:
        shutil.rmtree(built, ignore_errors=True)
        raise
    return manifest
