"""Final models: all of DS1, exactly the selected epochs, on CPU (MODEL-05, MODEL-06).

C1: no early stopping; each final model retrains on every DS1 row for the
epoch count chosen on the folds, with the class weights and RR scaler fitted
on all of those rows. C6, C7: frozen models train on CPU in deterministic
mode, whatever the CV device is. Each seed's checkpoint stays in its run
folder with its SHA256 (design call 4); Phase 5's export reads it from there.

Phase 5 settling 1 (MODEL-01): the baseline is refit the same way, on every
DS1 row at the C chosen on the folds, with its DS1 out-of-fold temperature.
It is one deterministic CPU fit with no seed.
"""

import hashlib
import logging
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray

from heartbeat.config import Settings
from heartbeat.constants import (
    BASELINE_MAX_ITER,
    SCORED_CLASSES,
    SHIPPED_SEED,
    TORCH_THREADS,
)
from heartbeat.data.loader import BeatTable
from heartbeat.models.baseline import BASELINE, FittedBaseline, coefficients
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


@dataclass(frozen=True)
class FinalBaseline:
    """The frozen baseline and what `baseline.json` needs (settling 1).

    Attributes:
        run: Its run folder's name.
        c: The C chosen on the folds (`results/cv_baseline.json`).
        temperature: Its DS1 out-of-fold temperature from the same file.
        coefficients: `(4, 6)`, rows in `SCORED_CLASSES` order.
        intercepts: `(4,)`, in `SCORED_CLASSES` order.
        scaler_mean: RR scaler mean, `(6,)`, fitted on all DS1 rows.
        scaler_std: RR scaler standard deviation, `(6,)`.
        class_weights: Balanced weights over all DS1 rows.
        n_rows: DS1 rows it was fitted on.
        fitted: The scikit-learn fit, for checks; never serialized.
    """

    run: str
    c: float
    temperature: float
    coefficients: NDArray[np.float64]
    intercepts: NDArray[np.float64]
    scaler_mean: NDArray[np.float64]
    scaler_std: NDArray[np.float64]
    class_weights: dict[str, float]
    n_rows: int
    fitted: FittedBaseline = field(repr=False, compare=False)


def train_final_baseline(
    settings: Settings,
    beats: BeatTable,
    c: float,
    temperature: float,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
) -> FinalBaseline:
    """Fit the baseline on every DS1 row into a new run `train-final-baseline`.

    Raises:
        ConvergenceWarning: If lbfgs does not converge (stop condition 5).
    """
    y = beats.beat_class
    class_weight = balanced_class_weights(y)
    rr = rr_model_inputs(beats.rr_s)
    scaler = fit_rr_scaler(rr)
    rows = np.arange(y.size, dtype=np.int64)
    x = BASELINE.inputs(beats, rows, apply_rr_scaler(scaler, rr))
    extra = {
        "model": BASELINE.name,
        "model_config": dict(BASELINE.config),
        "C": c,
        "temperature": temperature,
    }
    with create_run(
        "train-final-baseline", settings, extra, root=root, repo=repo
    ) as run:
        log.info("final baseline: C %g on %d DS1 rows", c, y.size)
        fitted = BASELINE.fit(x, y, class_weight, {"C": c})
        coef, intercept = coefficients(fitted)
        run.write_arrays(
            "baseline",
            coef=coef,
            intercept=intercept,
            scaler_mean=scaler.mean,
            scaler_std=scaler.std,
            class_weights=np.array([class_weight[k] for k in SCORED_CLASSES]),
            classes=np.array(SCORED_CLASSES),
            c=np.array(c),
        )
    return FinalBaseline(
        run=run.name,
        c=c,
        temperature=temperature,
        coefficients=coef,
        intercepts=intercept,
        scaler_mean=scaler.mean,
        scaler_std=scaler.std,
        class_weights=class_weight,
        n_rows=int(y.size),
        fitted=fitted,
    )


def final_payload(
    models: Sequence[FinalModel],
    width: float,
    epochs: int,
    baseline: FinalBaseline,
    repo: Path = REPO_ROOT,
) -> dict[str, Any]:
    """The `results/train_final.json` payload (design call 4, settling 1)."""

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
        "baseline": {
            "label": (
                "baseline on every DS1 row at the chosen C, CPU; temperature from "
                "its DS1 out-of-fold predictions (Phase 5 settling 1)"
            ),
            "run": baseline.run,
            "C": baseline.c,
            "temperature": baseline.temperature,
            "classes": list(SCORED_CLASSES),
            "coefficients": baseline.coefficients.tolist(),
            "intercepts": baseline.intercepts.tolist(),
            "scaler": {
                "mean": baseline.scaler_mean.tolist(),
                "std": baseline.scaler_std.tolist(),
            },
            "class_weights": dict(baseline.class_weights),
            "n_rows": baseline.n_rows,
            "solver": "lbfgs",
            "max_iter": BASELINE_MAX_ITER,
        },
    }
