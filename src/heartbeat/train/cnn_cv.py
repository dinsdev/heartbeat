"""CNN cross-validation run folders, their reader and the curves payload.

Phase 4 task plan, design calls 3 and 4: one run folder per width and seed
(`cv-cnn-w1-s0` and so on) holds every epoch's out-of-fold logits in float32,
each fold's class weights and scaler, and each fold's final weights. The
committed curves file holds only the pooled confusion matrix per width, seed
and epoch, plus the run folder names; later stages read logits from the named
run folders.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from torch import nn

from heartbeat.config import Settings
from heartbeat.constants import MAX_EPOCHS, N_FOLDS, SCORED_CLASSES
from heartbeat.data.folds import Folds
from heartbeat.data.loader import BeatTable
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.evaluate.metrics import (
    confusion_matrix,
    json_float,
    macro_f1,
    selection_score,
)
from heartbeat.paths import REPO_ROOT, RUNS_DIR
from heartbeat.runs import RunFolder, create_run
from heartbeat.train.cv import (
    EpochCVResult,
    cross_validate_epochs,
    patient_splitter,
    resolved_config,
)
from heartbeat.train.loop import cnn_spec
from heartbeat.train.torch_setup import configure_torch, torch_provenance

log = logging.getLogger(__name__)

RERUN_HINT = "rerun `uv run heartbeat rebuild --from cross-validate-cnn`"


class MissingRunError(FileNotFoundError):
    """A CNN CV run folder that a later stage reads is missing or partial."""


@dataclass(frozen=True)
class EpochRun:
    """One CNN CV run folder, read back.

    Attributes:
        run: The run folder's name.
        width: The network width.
        seed: The master seed.
        logits: Raw out-of-fold logits per epoch, float32, `(n_epochs, n, 4)`.
        fold: Each beat's validation fold, `(n,)`.
        class_weights: Each fold's training class weights, folds 0 to 4.
        record: Each beat's record, `(n,)`.
        sample: Each beat's annotation sample, `(n,)`.
        true_class: Expert labels, `(n,)`.
    """

    run: str
    width: float
    seed: int
    logits: NDArray[np.float32]
    fold: NDArray[np.int64]
    class_weights: tuple[dict[str, float], ...]
    record: NDArray[np.str_]
    sample: NDArray[np.int64]
    true_class: NDArray[np.str_]


def run_name(width: float, seed: int) -> str:
    """`cv-cnn-w1-s0` and so on (design call 4)."""
    return f"cv-cnn-w{width:g}-s{seed}"


def data_label(device: str) -> str:
    """The label every CNN number carries, for example "DS1 out-of-fold, MPS"."""
    return f"DS1 out-of-fold, {device.upper()}"


def epoch_confusions(
    logits: NDArray[np.float32], y_true: NDArray[np.str_]
) -> NDArray[np.int64]:
    """The pooled confusion matrix of each epoch's argmax, `(n_epochs, 4, 4)`."""
    return np.stack(
        [
            confusion_matrix(y_true, predict_labels(epoch.astype(np.float64)))
            for epoch in logits
        ]
    )


def write_epoch_run(
    run: RunFolder, result: EpochCVResult, beats: BeatTable, width: float, seed: int
) -> dict[str, Any]:
    """Write a CV result into its run folder; return its curves entry.

    Writes `oof.npz` (logits per epoch, folds, weights, scalers, the beats'
    identity), `weights.npz` (each fold's final state, for torch models) and
    `metrics.json` (the pooled confusion and scores per epoch).
    """
    scored = result.fold >= 0
    cms = epoch_confusions(result.logits[:, scored], beats.beat_class[scored])
    run.write_arrays(
        "oof",
        record=beats.record_id,
        subject=beats.subject_id,
        sample=beats.sample,
        true_class=beats.beat_class,
        fold=result.fold,
        logits=result.logits,
        classes=np.array(SCORED_CLASSES),
        class_weights=np.array(
            [[w[c] for c in SCORED_CLASSES] for w in result.class_weights]
        ),
        scaler_mean=np.stack([s.mean for s in result.scalers]),
        scaler_std=np.stack([s.std for s in result.scalers]),
        folds_run=np.array(result.folds_run, dtype=np.int64),
        width=np.array(width),
        seed=np.array(seed),
    )
    states: dict[str, NDArray[Any]] = {}
    for k, model in zip(result.folds_run, result.fitted, strict=True):
        if isinstance(model, nn.Module):
            for name, tensor in model.state_dict().items():
                states[f"fold{k}.{name}"] = tensor.detach().cpu().numpy()
    if states:
        run.write_arrays("weights", **states)
    run.write_json(
        "metrics",
        {
            "width": width,
            "seed": seed,
            "n_epochs": int(result.logits.shape[0]),
            "folds_run": list(result.folds_run),
            "confusion": cms.tolist(),
            "macro_f1_nsv": [json_float(selection_score(cm)) for cm in cms],
            "macro_f1_all": [json_float(macro_f1(cm, SCORED_CLASSES)) for cm in cms],
        },
    )
    return {"width": width, "seed": seed, "run": run.name, "confusion": cms}


def run_cnn_cv(
    settings: Settings,
    beats: BeatTable,
    traces: Mapping[str, NDArray[np.int16]],
    folds: Folds,
    folds_sha256: str,
    width: float,
    seed: int,
    device: str,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
    n_epochs: int = MAX_EPOCHS,
    only_folds: Sequence[int] | None = None,
) -> tuple[RunFolder, dict[str, Any]]:
    """Cross-validate the CNN at one width and seed into a new run folder.

    Never writes `results/` (rule 5; only the rebuild stages do).
    """
    spec = cnn_spec(traces, device)
    splitter = patient_splitter(folds)
    params = {"width": width, "seed": seed}
    torch_device = configure_torch(device)
    extra = {
        "resolved": resolved_config(spec, splitter, params, n_epochs),
        "folds_sha256": folds_sha256,
        "only_folds": None if only_folds is None else list(only_folds),
    }
    with create_run(
        run_name(width, seed),
        settings,
        extra,
        root=root,
        repo=repo,
        torch_info=torch_provenance(torch_device),
    ) as run:
        log.info("CNN CV width %g seed %d on %s", width, seed, device)
        result = cross_validate_epochs(
            spec, beats, splitter, params, n_epochs, only_folds=only_folds
        )
        entry = write_epoch_run(run, result, beats, width, seed)
        log.info("wrote %s", run.path)
    return run, entry


def load_epoch_run(path: Path) -> EpochRun:
    """Read a complete CNN CV run folder.

    Raises:
        MissingRunError: If the folder or its logits are missing, or it is a
            development run that trained fewer than five folds.
    """
    oof = path / "oof.npz"
    if not oof.is_file():
        raise MissingRunError(f"{path}: CNN CV run folder missing; {RERUN_HINT}")
    with np.load(oof, allow_pickle=False) as data:
        folds_run = tuple(int(k) for k in data["folds_run"])
        if folds_run != tuple(range(N_FOLDS)):
            raise MissingRunError(
                f"{path}: trained folds {list(folds_run)}, not all {N_FOLDS} folds; "
                f"{RERUN_HINT}"
            )
        table = data["class_weights"]
        return EpochRun(
            run=path.name,
            width=float(data["width"]),
            seed=int(data["seed"]),
            logits=data["logits"],
            fold=data["fold"],
            class_weights=tuple(
                dict(zip(SCORED_CLASSES, row.tolist(), strict=True)) for row in table
            ),
            record=data["record"],
            sample=data["sample"],
            true_class=data["true_class"],
        )


def curves_payload(
    entries: Sequence[Mapping[str, Any]], device: str, folds_sha256: str
) -> dict[str, Any]:
    """The `results/cv_cnn_curves.json` payload: confusions and run names only.

    Raises:
        ValueError: If the runs have different numbers of epochs.
    """
    epochs = {np.asarray(e["confusion"]).shape[0] for e in entries}
    if len(epochs) != 1:
        raise ValueError(f"runs have different numbers of epochs: {sorted(epochs)}")
    return {
        "data": data_label(device),
        "device": device,
        "classes": list(SCORED_CLASSES),
        "n_epochs": epochs.pop(),
        "folds_sha256": folds_sha256,
        "runs": [
            {
                "width": float(e["width"]),
                "seed": int(e["seed"]),
                "run": str(e["run"]),
                "confusion": np.asarray(e["confusion"]).tolist(),
            }
            for e in entries
        ],
    }
