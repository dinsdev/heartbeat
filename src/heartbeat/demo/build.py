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
outside DS1 stops it before any file is opened. DS2 demo data is Phase 7 work.
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
from heartbeat.demo.manifest import MANIFEST_NAME, file_entry, hashed_name
from heartbeat.evaluate.calibration import calibrated_probs, predict_labels
from heartbeat.export.bundle import ATTRIBUTION_NOTICE
from heartbeat.models.augment import model_windows
from heartbeat.models.inputs import apply_rr_scaler, rr_model_inputs
from heartbeat.paths import REPO_ROOT
from heartbeat.runs import canonical_json
from heartbeat.sealed.log import read_log
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


class DemoSplitError(RuntimeError):
    """A sealed run is logged, and DS2 demo data is not built yet (Phase 7)."""


Reader = Callable[[Path], PreparedRecord]


def require_demo_split(records: Sequence[str], splits: Splits, log_path: Path) -> str:
    """The split the demo data may use, checked before any file is opened (R32).

    Returns:
        "DS1" while no sealed run is logged.

    Raises:
        SealedRecordError: If a record is outside DS1.
        DemoSplitError: If a sealed run is logged.
    """
    if any(entry["type"] == "sealed" for entry in read_log(log_path)):
        raise DemoSplitError(
            "a sealed run is logged: the demo moves to DS2 with the frozen model, "
            "which `build-demo-data` builds from Phase 7 on"
        )
    require_ds1(records, splits)
    return SPLIT_DS1


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
) -> dict[str, Any]:
    """Write the demo data folder and return its manifest.

    Args:
        records: Records to ship, in picker order.
        prepared_dir: Folder written by `heartbeat prepare`.
        models_dir: `models/heartbeat-v1/`.
        export_record: `results/export.json`, whose SHA256 the copied model
            files must match.
        log_path: The sealed-run log, read for the split rule (R32).
        out_dir: The folder to replace, `web/public/data/`.
        splits: The split manifest.
        read: Reads one prepared file; tests spy on it.

    Raises:
        SealedRecordError: If a record is outside DS1, before anything is read.
        DemoSplitError: If a sealed run is logged.
        ValueError: If a model file differs from `results/export.json`.
    """
    split = require_demo_split(records, splits, log_path)
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
    for record_id in records:
        record = read(prepared_dir / f"{record_id}.npz")
        require_ds1([record.record_id], splits)
        labels, probs = label_kept_beats(record, session, scaler, calibration)
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
