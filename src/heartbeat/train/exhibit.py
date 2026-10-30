"""The leakage exhibit, inside DS1 only (C5; EXHIBIT-01 to 03).

The honest side is the patient-grouped C1 folds; the leaky side is beat-level
stratified 5-fold over the same 22 patients and beats. Both sides use the
configuration chosen on the honest folds, with no retuning: the CNN at the
selected width, trained the full epoch cap and read at the selected epoch,
for seeds 0 to 2; the baseline at its chosen C. The honest CNN is read from
its CV run folders; everything else runs through the shared driver, and each
leaky run's resolved config must differ from its honest twin in the splitter
alone (R24), checked here at run time as well as in the tests.

Each row reports the headline metrics with patient-bootstrap intervals (one
set of draws for every row), seeds 1 and 2 as a range for the CNN, and
accuracy. Accuracy is computed in this module only (design call 10).
"""

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.config import Settings
from heartbeat.constants import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CNN_SEEDS,
    INTERVAL_PERCENTILES,
    MAX_EPOCHS,
    SHIPPED_SEED,
)
from heartbeat.data.folds import Folds
from heartbeat.data.loader import BeatTable
from heartbeat.evaluate.bootstrap import (
    Interval,
    bootstrap,
    draw_confusions,
    draw_counts,
    patient_confusions,
    percentile_interval,
)
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.evaluate.metrics import confusion_matrix, json_float, metric_values
from heartbeat.models.baseline import BASELINE
from heartbeat.models.spec import ModelSpec
from heartbeat.paths import REPO_ROOT, RUNS_DIR
from heartbeat.runs import RunFolder, create_run
from heartbeat.train.cnn_cv import data_label, load_epoch_run, write_epoch_run
from heartbeat.train.cv import (
    BASELINE_DATA_LABEL,
    HEADLINE_METRICS,
    beat_splitter,
    cross_validate,
    cross_validate_epochs,
    fold_assignment_sha256,
    patient_splitter,
)
from heartbeat.train.torch_setup import configure_torch, torch_provenance

log = logging.getLogger(__name__)

# EXHIBIT-03: accuracy appears only here, labeled.
ACCURACY_LABEL = (
    "accuracy: the number papers often lead with; shown only in this exhibit "
    "(EXHIBIT-03)"
)
EXHIBIT_LABEL = (
    "inside DS1 only: patient-grouped folds (honest) against beat-level "
    "stratified folds (leaky), same configuration, code and seeds (C5)"
)


def accuracy(cms: NDArray[np.int64]) -> NDArray[np.float64]:
    """Share of beats on the diagonal, per matrix, `(k, 4, 4)` in, `(k,)` out."""
    total = cms.sum(axis=(1, 2)).astype(np.float64)
    hits = np.trace(cms, axis1=1, axis2=2).astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        values: NDArray[np.float64] = hits / total
    return values


def _accuracy_interval(
    confusions: NDArray[np.int64], counts: NDArray[np.int64]
) -> Interval:
    point = float(accuracy(confusions.sum(axis=0)[np.newaxis])[0])
    drawn = accuracy(draw_confusions(confusions, counts))
    bounds = percentile_interval(drawn)
    return Interval(
        point=point,
        low=None if bounds is None else bounds[0],
        high=None if bounds is None else bounds[1],
        skipped=int(np.isnan(drawn).sum()),
        draws=int(drawn.size),
    )


def _point_metrics(y: NDArray[np.str_], labels: NDArray[np.str_]) -> dict[str, Any]:
    cm = confusion_matrix(y, labels)[np.newaxis]
    values = metric_values(cm)
    points: dict[str, Any] = {
        m: json_float(float(values[m][0])) for m in HEADLINE_METRICS
    }
    points["accuracy"] = json_float(float(accuracy(cm)[0]))
    return points


def _check_one_key(honest: Mapping[str, Any], leaky: Mapping[str, Any]) -> None:
    # R24 at run time: the leaky run is the honest one with another splitter.
    keys = set(honest) | set(leaky)
    differ = sorted(k for k in keys if honest.get(k) != leaky.get(k))
    if differ != ["splitter"]:
        raise ValueError(
            f"leaky and honest configs differ in {differ}, not the splitter alone"
        )


def _row(
    side: str,
    model: str,
    data: str,
    labels_by_seed: Mapping[int, NDArray[np.str_]],
    beats: BeatTable,
    patients: list[str],
    counts: NDArray[np.int64],
    runs: list[str],
) -> dict[str, Any]:
    y = beats.beat_class
    head_seed = SHIPPED_SEED if SHIPPED_SEED in labels_by_seed else 0
    confusions = patient_confusions(
        y, labels_by_seed[head_seed], beats.subject_id, patients
    )
    boot = bootstrap({model: confusions}, counts=counts)
    row: dict[str, Any] = {
        "side": side,
        "model": model,
        "data": data,
        "seed": head_seed,
        "runs": runs,
        "metrics": {m: boot.intervals[model][m].as_dict() for m in HEADLINE_METRICS},
        "accuracy": _accuracy_interval(confusions, counts).as_dict(),
    }
    others = [s for s in labels_by_seed if s != head_seed]
    if others:
        pooled = [{"seed": s, **_point_metrics(y, labels_by_seed[s])} for s in others]
        value_range: dict[str, dict[str, float] | None] = {}
        for m in (*HEADLINE_METRICS, "accuracy"):
            defined = [v for p in pooled if (v := p[m]) is not None]
            value_range[m] = (
                {"min": min(defined), "max": max(defined)} if defined else None
            )
        row["other_seeds"] = {"seeds": others, "pooled": pooled, "range": value_range}
    return row


def run_exhibit(
    settings: Settings,
    width: float,
    epoch: int,
    chosen_c: float,
    beats: BeatTable,
    folds: Folds,
    folds_sha256: str,
    cv_runs: Mapping[int, Path],
    cnn: ModelSpec,
    device: str,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
    n_epochs: int = MAX_EPOCHS,
    n_draws: int = BOOTSTRAP_DRAWS,
) -> tuple[RunFolder, dict[str, Any]]:
    """Run the leaky side and report both sides for both models.

    Args:
        settings: Run settings.
        width: The honest selection's width.
        epoch: The honest selection's epoch count.
        chosen_c: The baseline's C chosen on the honest folds.
        beats: DS1 beats.
        folds: The C1 folds.
        folds_sha256: SHA256 of the fold file.
        cv_runs: Seed to its honest CV run folder at `width`.
        cnn: The CNN spec (the same one the honest runs used).
        device: The CV device.
        root: Parent of run folders.
        repo: The checkout the provenance records.
        n_epochs: Epochs each leaky run trains (the honest runs' cap).
        n_draws: Bootstrap draws.

    Returns:
        The exhibit's run folder and the `results/exhibit.json` payload.

    Raises:
        ValueError: If a leaky config differs from its honest twin in more
            than the splitter, or a run was made at another width or from
            other beats.
    """
    y = beats.beat_class
    patients = sorted(set(beats.subject_id.tolist()))
    counts = draw_counts(len(patients), n_draws, BOOTSTRAP_SEED)
    leaky_splitter = beat_splitter()
    torch_device = configure_torch(device)
    extra = {
        "width": width,
        "epoch": epoch,
        "chosen_c": chosen_c,
        "n_epochs": n_epochs,
        "cv_runs": {str(s): p.name for s, p in cv_runs.items()},
        "leaky_split": dict(leaky_splitter.config),
        "folds_sha256": folds_sha256,
    }
    rows: list[dict[str, Any]] = []
    with create_run(
        "exhibit",
        settings,
        extra,
        root=root,
        repo=repo,
        torch_info=torch_provenance(torch_device),
    ) as umbrella:
        # Honest CNN: read from the CV run folders.
        honest_cnn: dict[int, NDArray[np.str_]] = {}
        honest_configs: dict[int, Mapping[str, Any]] = {}
        for s in CNN_SEEDS:
            cv = load_epoch_run(cv_runs[s])
            if cv.width != width or cv.seed != s:
                raise ValueError(f"run {cv.run} is width {cv.width:g} seed {cv.seed}")
            if not (
                np.array_equal(cv.sample, beats.sample)
                and np.array_equal(cv.record, beats.record_id)
            ):
                raise ValueError(f"run {cv.run} was made from other beats")
            honest_cnn[s] = predict_labels(cv.logits[epoch - 1].astype(np.float64))
            config = json.loads((cv_runs[s] / "config.json").read_text("utf-8"))
            honest_configs[s] = config["extra"]["resolved"]
        rows.append(
            _row(
                "patient",
                cnn.name,
                data_label(device),
                honest_cnn,
                beats,
                patients,
                counts,
                [cv_runs[s].name for s in CNN_SEEDS],
            )
        )
        # Honest baseline: the Phase 3 driver at the chosen C.
        honest_base = cross_validate(
            BASELINE, beats, patient_splitter(folds), {"C": chosen_c}
        )
        rows.append(
            _row(
                "patient",
                BASELINE.name,
                BASELINE_DATA_LABEL,
                {0: predict_labels(honest_base.logits)},
                beats,
                patients,
                counts,
                [],
            )
        )
        # Leaky CNN: the same spec, width and seeds, all epochs, read at `epoch`.
        leaky_cnn: dict[int, NDArray[np.str_]] = {}
        leaky_runs: list[str] = []
        assignment: str | None = None
        for s in CNN_SEEDS:
            params = {"width": width, "seed": s}
            with create_run(
                f"exhibit-cnn-w{width:g}-s{s}",
                settings,
                {"leaky_split": dict(leaky_splitter.config)},
                root=root,
                repo=repo,
                torch_info=torch_provenance(torch_device),
            ) as run:
                result = cross_validate_epochs(
                    cnn, beats, leaky_splitter, params, n_epochs
                )
                _check_one_key(honest_configs[s], result.config)
                write_epoch_run(run, result, beats, width, s)
            leaky_cnn[s] = predict_labels(result.logits[epoch - 1].astype(np.float64))
            leaky_runs.append(run.name)
            assignment = fold_assignment_sha256(result.fold)
            log.info("exhibit leaky CNN seed %d: %s", s, run.name)
        rows.append(
            _row(
                "beat",
                cnn.name,
                data_label(device),
                leaky_cnn,
                beats,
                patients,
                counts,
                leaky_runs,
            )
        )
        # Leaky baseline at the honest C.
        leaky_base = cross_validate(BASELINE, beats, leaky_splitter, {"C": chosen_c})
        _check_one_key(honest_base.config, leaky_base.config)
        rows.append(
            _row(
                "beat",
                BASELINE.name,
                BASELINE_DATA_LABEL,
                {0: predict_labels(leaky_base.logits)},
                beats,
                patients,
                counts,
                [],
            )
        )
        if assignment != fold_assignment_sha256(leaky_base.fold):
            raise ValueError("the leaky CNN and baseline runs used different folds")
        payload: dict[str, Any] = {
            "label": EXHIBIT_LABEL,
            "accuracy_label": ACCURACY_LABEL,
            "selection": {"width": width, "epoch": epoch, "C": chosen_c},
            "leaky_split": {
                **dict(leaky_splitter.config),
                "assignment_sha256": assignment,
            },
            "folds_sha256": folds_sha256,
            "n_beats": int(y.size),
            "patients": patients,
            "bootstrap": {
                "draws": n_draws,
                "seed": BOOTSTRAP_SEED,
                "percentiles": list(INTERVAL_PERCENTILES),
                "unit": "patient",
                "shared": "one set of draws for every row",
            },
            "rows": rows,
        }
        umbrella.write_json("metrics", payload)
    return umbrella, payload
