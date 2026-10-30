"""`heartbeat export`: train-final's checkpoints to the bundle and fixtures (E3, E5).

Loads each final checkpoint after checking its SHA256 against
`results/train_final.json`, exports it, checks the file (R25) and PyTorch
against ONNX Runtime on every DS1 kept beat (R26), writes `models/heartbeat-v1/`
and `fixtures/parity/fixtures.json` (R27), and returns the `results/export.json`
payload (Phase 5 task plan, design calls 3 and 4).
"""

import importlib.metadata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import (
    MODEL_SIZE_LIMIT_BYTES,
    ONNX_OPSET,
    PARITY_TOLERANCE,
    SCORED_CLASSES,
    SHIPPED_SEED,
)
from heartbeat.data.loader import BeatTable
from heartbeat.data.manifests import Splits
from heartbeat.export.bundle import (
    SeedModel,
    bundle_files,
    file_facts,
    seed_folder,
    write_bundle,
)
from heartbeat.export.fixtures import FixtureModel, build_fixtures, write_fixtures
from heartbeat.export.onnx import (
    ExportError,
    check_onnx,
    check_parity,
    export_onnx,
    load_checkpoint,
    parameter_count,
)
from heartbeat.models.augment import model_windows
from heartbeat.models.inputs import RRScaler, apply_rr_scaler, rr_model_inputs
from heartbeat.sealed.score import BaselineParams
from heartbeat.train.final import FINAL_DEVICE
from heartbeat.train.torch_setup import configure_torch

EXPORT_LABEL = (
    "frozen models from train-final, exported on CPU; parity: PyTorch against "
    "Python ONNX Runtime on every DS1 kept beat (R26)"
)


def _same_scaler(
    entries: Sequence[Mapping[str, Any]], baseline: Mapping[str, Any]
) -> tuple[list[float], list[float]]:
    # Every final model's scaler is fitted on the same DS1 rows (settling 2).
    scalers = [e["scaler"] for e in entries] + [baseline["scaler"]]
    if any(s != scalers[0] for s in scalers[1:]):
        raise ExportError("the final models' RR scalers differ; scaler.json is shared")
    return list(scalers[0]["mean"]), list(scalers[0]["std"])


def baseline_params(block: Mapping[str, Any]) -> BaselineParams:
    """The frozen baseline from `results/train_final.json`'s baseline block."""
    weights = block["class_weights"]
    return BaselineParams(
        coefficients=np.array(block["coefficients"], dtype=np.float64),
        intercepts=np.array(block["intercepts"], dtype=np.float64),
        scaler_mean=np.array(block["scaler"]["mean"], dtype=np.float64),
        scaler_std=np.array(block["scaler"]["std"], dtype=np.float64),
        log_class_weights=np.log([weights[c] for c in SCORED_CLASSES]),
        temperature=float(block["temperature"]),
    )


def export_models(
    train_final: Mapping[str, Any],
    beats: BeatTable,
    annotated: Mapping[str, NDArray[np.int64]],
    splits: Splits,
    models_dir: Path,
    fixtures_dir: Path,
    repo: Path,
) -> dict[str, Any]:
    """Export every final model and the baseline, and write the fixtures.

    Args:
        train_final: The `results/train_final.json` payload.
        beats: Every DS1 kept beat, for the parity check and the fixtures.
        annotated: DS1 record to every annotated beat sample, for the fixtures.
        splits: The split manifest (fixtures are DS1 only, R27).
        models_dir: The bundle folder (`models/heartbeat-v1/`).
        fixtures_dir: The fixtures folder (`fixtures/parity/`).
        repo: Root that checkpoint and output paths are relative to.

    Returns:
        The `results/export.json` payload (without run provenance).

    Raises:
        ExportError: On a checkpoint whose SHA256 differs from `train_final`,
            differing scalers, a file that breaks design call 3 or the size
            gate (R25), or a parity miss (R26).
    """
    configure_torch(FINAL_DEVICE)
    width = float(train_final["width"])
    entries = sorted(train_final["models"], key=lambda e: int(e["seed"]))
    mean, std = _same_scaler(entries, train_final["baseline"])
    scaler = RRScaler(mean=np.array(mean), std=np.array(std))
    windows = model_windows(beats.window_adu)
    rr = apply_rr_scaler(scaler, rr_model_inputs(beats.rr_s)).astype(np.float32)
    seeds: list[SeedModel] = []
    networks: list[FixtureModel] = []
    rows: list[dict[str, Any]] = []
    parameters = 0
    for entry in entries:
        seed = int(entry["seed"])
        try:
            model = load_checkpoint(repo / entry["path"], width, entry["sha256"])
        except ExportError as error:
            raise ExportError(f"seed-{seed}: {error}") from error
        data = export_onnx(model)
        check_onnx(data)
        diff = check_parity(model, data, windows, rr)
        parameters = parameter_count(model)
        seeds.append(
            SeedModel(seed, data, entry["class_weights"], float(entry["temperature"]))
        )
        networks.append(
            FixtureModel(
                seed, model, entry["class_weights"], float(entry["temperature"])
            )
        )
        rows.append(
            {
                "seed": seed,
                "path": (models_dir / seed_folder(seed) / "model.onnx")
                .relative_to(repo)
                .as_posix(),
                "checkpoint_sha256": entry["sha256"],
                "temperature": entry["temperature"],
                "parity_max_abs_diff": diff,
            }
        )
    baseline = train_final["baseline"]
    fixtures = build_fixtures(
        beats, annotated, splits, networks, baseline_params(baseline)
    )
    write_bundle(models_dir, seeds, mean, std, baseline)
    fixtures_path = write_fixtures(fixtures_dir, fixtures)
    return {
        "label": EXPORT_LABEL,
        "width": width,
        "epochs": train_final["epochs"],
        "shipped_seed": SHIPPED_SEED,
        "opset": ONNX_OPSET,
        "parameters": parameters,
        "size_limit_bytes": MODEL_SIZE_LIMIT_BYTES,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "onnx", "onnxscript", "onnxruntime")
        },
        "parity": {
            "tolerance": PARITY_TOLERANCE,
            "beats": int(beats.sample.size),
            "data": "every DS1 kept beat, CPU",
        },
        "models": rows,
        "baseline": {
            "path": (models_dir / "baseline.json").relative_to(repo).as_posix(),
            "C": baseline["C"],
            "temperature": baseline["temperature"],
        },
        "files": bundle_files(models_dir, repo),
        "fixtures": {
            **file_facts(fixtures_path, repo),
            "beats": len(fixtures["beats"]),
            "seed": fixtures["seed"],
        },
    }
