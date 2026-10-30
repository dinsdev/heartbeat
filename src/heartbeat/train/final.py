"""Final models: all of DS1, exactly the selected epochs, on CPU (MODEL-05, MODEL-06).

C1: no early stopping; each final model retrains on every DS1 row for the
epoch count chosen on the folds, with the class weights and RR scaler fitted
on all of those rows. C6, C7: frozen models train on CPU in deterministic
mode, whatever the CV device is. Each seed's checkpoint stays in its run
folder with its SHA256 (design call 4); Phase 5's export reads it from there.
"""

import hashlib
import logging
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray

from heartbeat.config import Settings
from heartbeat.constants import SCORED_CLASSES, SHIPPED_SEED, TORCH_THREADS
from heartbeat.data.loader import BeatTable
from heartbeat.models.inputs import apply_rr_scaler, fit_rr_scaler, rr_model_inputs
from heartbeat.paths import REPO_ROOT, RUNS_DIR
from heartbeat.runs import create_run
from heartbeat.train.loop import cnn_spec
from heartbeat.train.seeds import FINAL_FOLD
from heartbeat.train.torch_setup import configure_torch, torch_provenance
from heartbeat.train.weights import balanced_class_weights

log = logging.getLogger(__name__)

# C6, MODEL-06: frozen models train on CPU, never on the CV device.
FINAL_DEVICE = "cpu"
CHECKPOINT_NAME = "model.pt"


@dataclass(frozen=True)
class FinalModel:
    """One final model and what the export needs to rebuild its pipeline.

    Attributes:
        seed: The master seed.
        run: Its run folder's name.
        checkpoint: The state dict file.
        sha256: The checkpoint's SHA256.
        width: The network width.
        epochs: Epochs trained.
        temperature: This seed's temperature from the selection (EVAL-11).
        scaler_mean: RR scaler mean, `(6,)`, fitted on all DS1 rows.
        scaler_std: RR scaler standard deviation, `(6,)`.
        class_weights: Balanced weights over all DS1 rows.
        device: Always "cpu".
        wall_s: Training wall-clock time in seconds.
    """

    seed: int
    run: str
    checkpoint: Path
    sha256: str
    width: float
    epochs: int
    temperature: float
    scaler_mean: NDArray[np.float64]
    scaler_std: NDArray[np.float64]
    class_weights: dict[str, float]
    device: str
    wall_s: float


def _save_state(state: Mapping[str, torch.Tensor], path: Path) -> str:
    # Atomic write (CONVENTIONS section 2); the checksum is of the bytes written.
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".part", delete=False
    ) as f:
        temp = Path(f.name)
        torch.save(dict(state), f)
    digest = hashlib.sha256(temp.read_bytes()).hexdigest()
    temp.replace(path)
    return digest


def train_final(
    settings: Settings,
    beats: BeatTable,
    traces: Mapping[str, NDArray[np.int16]],
    width: float,
    epochs: int,
    seed: int,
    temperature: float,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
) -> FinalModel:
    """Train one final model into a new run folder `train-final-s<seed>`."""
    spec = cnn_spec(traces, FINAL_DEVICE)
    assert spec.fit_epochs is not None
    y = beats.beat_class
    rows = np.arange(y.size, dtype=np.int64)
    class_weight = balanced_class_weights(y)
    rr = rr_model_inputs(beats.rr_s)
    scaler = fit_rr_scaler(rr)
    x = spec.inputs(beats, rows, apply_rr_scaler(scaler, rr))
    params = {"width": width, "seed": seed}
    torch_device = configure_torch(FINAL_DEVICE)
    extra = {
        "model": spec.name,
        "model_config": dict(spec.config),
        "params": params,
        "epochs": epochs,
        "temperature": temperature,
        "stream_fold": FINAL_FOLD,
    }
    with create_run(
        f"train-final-s{seed}",
        settings,
        extra,
        root=root,
        repo=repo,
        torch_info=torch_provenance(torch_device),
    ) as run:
        log.info("final model seed %d: width %g, %d epochs on CPU", seed, width, epochs)
        start = time.perf_counter()
        trained = 0
        final: Any = None
        for model in spec.fit_epochs(x, y, class_weight, params, FINAL_FOLD, epochs):
            final = model
            trained += 1
            log.info("final model seed %d: epoch %d of %d", seed, trained, epochs)
        wall_s = time.perf_counter() - start
        if trained != epochs:
            raise ValueError(f"{trained} epochs trained, {epochs} asked")
        checkpoint = run.path / CHECKPOINT_NAME
        sha256 = _save_state(final.state_dict(), checkpoint)
        run.write_arrays(
            "pipeline",
            scaler_mean=scaler.mean,
            scaler_std=scaler.std,
            class_weights=np.array([class_weight[c] for c in SCORED_CLASSES]),
            classes=np.array(SCORED_CLASSES),
        )
        log.info("wrote %s (sha256 %s) in %.1f s", checkpoint, sha256, wall_s)
    return FinalModel(
        seed=seed,
        run=run.name,
        checkpoint=checkpoint,
        sha256=sha256,
        width=width,
        epochs=epochs,
        temperature=temperature,
        scaler_mean=scaler.mean,
        scaler_std=scaler.std,
        class_weights=class_weight,
        device=FINAL_DEVICE,
        wall_s=wall_s,
    )


def final_payload(
    models: Sequence[FinalModel], width: float, epochs: int, repo: Path = REPO_ROOT
) -> dict[str, Any]:
    """The `results/train_final.json` payload (design call 4)."""

    def path_text(path: Path) -> str:
        try:
            return path.relative_to(repo).as_posix()
        except ValueError:
            return str(path)

    return {
        "label": "final models on every DS1 row, CPU, deterministic mode (MODEL-06)",
        "width": width,
        "epochs": epochs,
        "shipped_seed": SHIPPED_SEED,
        "torch": torch.__version__,
        "models": [
            {
                "seed": m.seed,
                "run": m.run,
                "path": path_text(m.checkpoint),
                "sha256": m.sha256,
                "width": m.width,
                "epochs": m.epochs,
                "temperature": m.temperature,
                "scaler": {
                    "mean": m.scaler_mean.tolist(),
                    "std": m.scaler_std.tolist(),
                },
                "class_weights": dict(m.class_weights),
                "device": m.device,
                "torch_threads": TORCH_THREADS,
                "deterministic": True,
                "wall_s": m.wall_s,
            }
            for m in models
        ],
    }
