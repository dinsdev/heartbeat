"""The `models/heartbeat-v1/` files (E3; PARITY-01, PUB-07, R52).

Layout (Phase 5 task plan, design call 3): seed 0 ships as `model.onnx` with
its `calibration.json`; seeds 1 and 2 sit under `seeds/seed-<n>/` with their
own; `scaler.json` serves all three; `baseline.json` holds the frozen
baseline (settling 1); `NOTICE` gives the license of the weights and the
data's attribution notice (R52). JSON goes through `canonical_json`, so a
rerun writes the same bytes. `freeze.json` is written only by
`heartbeat export --freeze` (Phase 7) and left alone here.
"""

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from heartbeat.constants import RR_FEATURE_NAMES, SCORED_CLASSES, SHIPPED_SEED
from heartbeat.runs import canonical_json, write_text_atomic

NOTICE_NAME = "NOTICE"
FREEZE_NAME = "freeze.json"

# PUB-07, R52: ODC-By 1.0 section 4.3's notice for the training data, worded as
# in `DATA_LICENSE.md`; the fixtures carry it too.
ATTRIBUTION_NOTICE = (
    "Contains information from the MIT-BIH Arrhythmia Database (version 1.0.0, "
    "PhysioNet), which is made available under the ODC Attribution License v1.0."
)

# PUB-07, R52: MIT for the weights (as `LICENSE`), and the notice above.
NOTICE_TEXT = """heartbeat-v1 model files

The model weights in this folder are released under the MIT License, like the
code of the repository they come from (see LICENSE at the repository root):
Copyright (c) 2026 Dinesh Dawonauth.

The models were trained on data from the MIT-BIH Arrhythmia Database. Notice
under section 4.3 of the Open Data Commons Attribution License v1.0:

Contains information from the MIT-BIH Arrhythmia Database (version 1.0.0,
PhysioNet), which is made available under the ODC Attribution License v1.0.
https://opendatacommons.org/licenses/by/1-0/

Moody G, Mark R. MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet (2005).
https://doi.org/10.13026/C2F305
"""

CALIBRATION_LABEL = (
    "probabilities: softmax of (logits minus log_class_weights) divided by the "
    "temperature; the label is the argmax of the raw logits (EVAL-11)"
)


@dataclass(frozen=True)
class SeedModel:
    """One exported CNN seed.

    Attributes:
        seed: The master seed.
        onnx_bytes: The exported file.
        class_weights: The training class weights (all DS1 rows).
        temperature: The seed's DS1 out-of-fold temperature.
    """

    seed: int
    onnx_bytes: bytes
    class_weights: Mapping[str, float]
    temperature: float


def seed_folder(seed: int) -> PurePosixPath:
    """Where a seed's files sit inside the bundle: the root for the shipped seed."""
    return (
        PurePosixPath(".")
        if seed == SHIPPED_SEED
        else PurePosixPath("seeds", f"seed-{seed}")
    )


def _log_weights(class_weights: Mapping[str, float]) -> list[float]:
    return [math.log(class_weights[c]) for c in SCORED_CLASSES]


def calibration_payload(model: SeedModel) -> dict[str, Any]:
    """A seed's `calibration.json`."""
    return {
        "seed": model.seed,
        "classes": list(SCORED_CLASSES),
        "log_class_weights": _log_weights(model.class_weights),
        "temperature": model.temperature,
        "label": CALIBRATION_LABEL,
    }


def scaler_payload(mean: Sequence[float], std: Sequence[float]) -> dict[str, Any]:
    """`scaler.json`: the RR scaler fitted on every DS1 row."""
    return {
        "features": list(RR_FEATURE_NAMES),
        "log_features": ["pre_over_local", "post_over_pre"],
        "mean": [float(v) for v in mean],
        "std": [float(v) for v in std],
        "label": (
            "RR inputs: the six features in this order, the log taken of "
            "log_features, then (x - mean) / std (population std)"
        ),
    }


def baseline_payload(block: Mapping[str, Any]) -> dict[str, Any]:
    """`baseline.json` from `results/train_final.json`'s baseline block."""
    if list(block["classes"]) != list(SCORED_CLASSES):
        raise ValueError(f"baseline classes {block['classes']}")
    return {
        "model": "baseline",
        "classes": list(SCORED_CLASSES),
        "features": list(RR_FEATURE_NAMES),
        "C": block["C"],
        "coefficients": block["coefficients"],
        "intercepts": block["intercepts"],
        "scaler": dict(block["scaler"]),
        "log_class_weights": _log_weights(block["class_weights"]),
        "temperature": block["temperature"],
        "label": (
            "logits: scaled RR inputs (scaler block, as in scaler.json) times "
            "coefficients plus intercepts; probabilities as in calibration.json"
        ),
    }


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.part")
    temp.write_bytes(data)
    temp.replace(path)


def write_bundle(
    models_dir: Path,
    seeds: Sequence[SeedModel],
    scaler_mean: Sequence[float],
    scaler_std: Sequence[float],
    baseline_block: Mapping[str, Any],
) -> list[Path]:
    """Write every bundle file; return their paths.

    Raises:
        ValueError: If the shipped seed is missing or a seed appears twice.
        FileExistsError: If the folder holds a file the bundle does not write
            (other than the freeze record), so no stale file survives.
    """
    numbers = [m.seed for m in seeds]
    if SHIPPED_SEED not in numbers or len(set(numbers)) != len(numbers):
        raise ValueError(f"seeds {numbers}: need seed {SHIPPED_SEED} once each")
    texts: dict[PurePosixPath, bytes] = {}
    for model in seeds:
        folder = seed_folder(model.seed)
        texts[folder / "model.onnx"] = model.onnx_bytes
        texts[folder / "calibration.json"] = canonical_json(
            calibration_payload(model)
        ).encode()
    texts[PurePosixPath("scaler.json")] = canonical_json(
        scaler_payload(scaler_mean, scaler_std)
    ).encode()
    texts[PurePosixPath("baseline.json")] = canonical_json(
        baseline_payload(baseline_block)
    ).encode()
    texts[PurePosixPath(NOTICE_NAME)] = NOTICE_TEXT.encode()
    allowed = {p.as_posix() for p in texts} | {FREEZE_NAME}
    if models_dir.is_dir():
        stray = sorted(
            p.relative_to(models_dir).as_posix()
            for p in models_dir.rglob("*")
            if p.is_file() and p.relative_to(models_dir).as_posix() not in allowed
        )
        if stray:
            raise FileExistsError(
                f"{models_dir} holds files export does not write: {stray}"
            )
    written = []
    for relative, data in sorted(texts.items()):
        path = models_dir / relative
        if relative.suffix == ".json" or relative.name == NOTICE_NAME:
            write_text_atomic(path, data.decode())
        else:
            _write_bytes_atomic(path, data)
        written.append(path)
    return written


def file_facts(path: Path, repo: Path) -> dict[str, Any]:
    """A file's repo-relative path, size and SHA256."""
    data = path.read_bytes()
    return {
        "path": path.relative_to(repo).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def bundle_files(models_dir: Path, repo: Path) -> list[dict[str, Any]]:
    """Size and SHA256 of every bundle file except the freeze record, sorted."""
    return [
        file_facts(path, repo)
        for path in sorted(models_dir.rglob("*"))
        if path.is_file() and path.relative_to(models_dir).as_posix() != FREEZE_NAME
    ]
