"""C5, EXHIBIT-01 to 03: the leakage exhibit for the CNN and the baseline.

A fast stand-in for the CNN and synthetic beats; no record is read.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from cnn_support import epoch_spec
from cv_support import synthetic_beats, synthetic_folds
from run_support import make_repo, settings

from heartbeat.constants import CNN_SEEDS
from heartbeat.data.folds import Folds
from heartbeat.data.loader import BeatTable
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.evaluate.metrics import confusion_matrix, selection_score
from heartbeat.models.spec import ModelSpec
from heartbeat.paths import PACKAGE_DIR
from heartbeat.runs import create_run
from heartbeat.train import exhibit as exhibit_module
from heartbeat.train.cnn_cv import write_epoch_run
from heartbeat.train.cv import (
    CVResult,
    EpochCVResult,
    Splitter,
    baseline_summary,
    beat_splitter,
    cross_validate,
    cross_validate_epochs,
    fold_assignment_sha256,
    patient_splitter,
    select_baseline_c,
)
from heartbeat.train.exhibit import ACCURACY_LABEL, run_exhibit

WIDTH = 1.0
EPOCH = 2
N_EPOCHS = 3
CHOSEN_C = 0.1


@pytest.fixture
def setup(
    tmp_path: Path,
) -> tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]]:
    repo = make_repo(tmp_path)
    beats = synthetic_beats()
    folds = synthetic_folds(beats)
    spec = epoch_spec()
    cv_runs: dict[int, Path] = {}
    for seed in CNN_SEEDS:
        params = {"width": WIDTH, "seed": seed}
        result = cross_validate_epochs(
            spec, beats, patient_splitter(folds), params, N_EPOCHS
        )
        with create_run(
            f"cv-cnn-w1-s{seed}",
            settings(tmp_path),
            {"resolved": result.config},
            repo / "runs",
            repo,
        ) as run:
            write_epoch_run(run, result, beats, width=WIDTH, seed=seed)
        cv_runs[seed] = run.path
    return repo, beats, folds, spec, cv_runs


def _run(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
) -> tuple[Any, dict[str, Any]]:
    repo, beats, folds, spec, cv_runs = setup
    return run_exhibit(
        settings(repo.parent),
        width=WIDTH,
        epoch=EPOCH,
        chosen_c=CHOSEN_C,
        beats=beats,
        folds=folds,
        folds_sha256="ab" * 32,
        cv_runs=cv_runs,
        cnn=spec,
        device="cpu",
        root=repo / "runs",
        repo=repo,
        n_epochs=N_EPOCHS,
        n_draws=40,
    )


def _row(payload: Mapping[str, Any], side: str, model: str) -> Mapping[str, Any]:
    rows: list[Mapping[str, Any]] = [
        r for r in payload["rows"] if (r["side"], r["model"]) == (side, model)
    ]
    (row,) = rows
    return row


def test_both_models_on_both_sides(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
) -> None:
    _, payload = _run(setup)
    json.dumps(payload, allow_nan=False)
    assert sorted((r["side"], r["model"]) for r in payload["rows"]) == [
        ("beat", "baseline"),
        ("beat", "epochs"),
        ("patient", "baseline"),
        ("patient", "epochs"),
    ]
    for row in payload["rows"]:
        assert set(row["metrics"]) >= {"macro_f1_nsv", "S_recall", "V_fpr"}
        assert row["metrics"]["macro_f1_nsv"]["draws"] == 40
    assert _row(payload, "beat", "epochs")["data"] == "DS1 out-of-fold, CPU"
    assert _row(payload, "beat", "baseline")["data"] == "DS1 out-of-fold, CPU"


@pytest.mark.rule("R24")
def test_the_leaky_side_reuses_the_honest_choices_and_differs_only_in_the_splitter(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cv_runs = setup[4]
    epoch_calls: list[tuple[Splitter, Mapping[str, Any], int, EpochCVResult]] = []
    calls: list[tuple[Splitter, Mapping[str, Any], CVResult]] = []

    def epochs_spy(
        s: ModelSpec, b: BeatTable, splitter: Splitter, p: Mapping[str, Any], n: int
    ) -> EpochCVResult:
        result = cross_validate_epochs(s, b, splitter, p, n)
        epoch_calls.append((splitter, p, n, result))
        return result

    def cv_spy(
        s: ModelSpec, b: BeatTable, splitter: Splitter, p: Mapping[str, Any]
    ) -> CVResult:
        result = cross_validate(s, b, splitter, p)
        calls.append((splitter, p, result))
        return result

    monkeypatch.setattr(exhibit_module, "cross_validate_epochs", epochs_spy)
    monkeypatch.setattr(exhibit_module, "cross_validate", cv_spy)
    _run(setup)
    # The honest CNN is read from its CV run folders, never retrained.
    assert [c[0].name for c in epoch_calls] == ["beat"] * 3
    assert [dict(c[1]) for c in epoch_calls] == [
        {"width": WIDTH, "seed": s} for s in CNN_SEEDS
    ]
    assert {c[2] for c in epoch_calls} == {N_EPOCHS}
    for seed, (_, _, _, leaky) in zip(CNN_SEEDS, epoch_calls, strict=True):
        config = json.loads((cv_runs[seed] / "config.json").read_text("utf-8"))
        honest = config["extra"]["resolved"]
        assert {k for k in honest if honest[k] != leaky.config[k]} == {"splitter"}
    # The baseline at the honest side's chosen C, on both sides.
    assert [(c[0].name, dict(c[1])) for c in calls] == [
        ("patient", {"C": CHOSEN_C}),
        ("beat", {"C": CHOSEN_C}),
    ]
    honest_b, leaky_b = calls[0][2].config, calls[1][2].config
    assert {k for k in honest_b if honest_b[k] != leaky_b[k]} == {"splitter"}


def test_the_cnn_rows_read_the_selected_epoch(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
) -> None:
    repo, beats, _, _, cv_runs = setup
    _, payload = _run(setup)
    honest = _row(payload, "patient", "epochs")
    with np.load(cv_runs[0] / "oof.npz", allow_pickle=False) as data:
        labels = predict_labels(data["logits"][EPOCH - 1].astype(np.float64))
    cm = confusion_matrix(beats.beat_class, labels)
    assert honest["metrics"]["macro_f1_nsv"]["point"] == selection_score(cm)
    assert honest["runs"] == [cv_runs[s].name for s in CNN_SEEDS]
    leaky = _row(payload, "beat", "epochs")
    (leaky_dir,) = [
        p for p in (repo / "runs").iterdir() if p.name.endswith("exhibit-cnn-w1-s0")
    ]
    assert leaky["runs"][0] == leaky_dir.name
    with np.load(leaky_dir / "oof.npz", allow_pickle=False) as data:
        leaky_labels = predict_labels(data["logits"][EPOCH - 1].astype(np.float64))
        assert data["logits"].shape[0] == N_EPOCHS
    leaky_cm = confusion_matrix(beats.beat_class, leaky_labels)
    assert leaky["metrics"]["macro_f1_nsv"]["point"] == selection_score(leaky_cm)
    assert leaky["accuracy"]["point"] == np.trace(leaky_cm) / leaky_cm.sum()


def test_seeds_1_and_2_are_a_range_for_the_cnn_rows(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
) -> None:
    _, payload = _run(setup)
    for side in ("patient", "beat"):
        other = _row(payload, side, "epochs")["other_seeds"]
        assert other["seeds"] == [1, 2]
        values = [p["macro_f1_nsv"] for p in other["pooled"]]
        assert other["range"]["macro_f1_nsv"] == {
            "min": min(values),
            "max": max(values),
        }
        assert all("accuracy" in p for p in other["pooled"])
    assert "other_seeds" not in _row(payload, "patient", "baseline")


def test_accuracy_is_shown_with_its_label(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
) -> None:
    _, payload = _run(setup)
    assert payload["accuracy_label"] == ACCURACY_LABEL
    assert "papers often lead with" in ACCURACY_LABEL
    for row in payload["rows"]:
        acc = row["accuracy"]
        assert 0.0 <= acc["low"] <= acc["point"] <= acc["high"] <= 1.0
        assert acc["draws"] == 40


def test_the_payload_records_the_leaky_assignment(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
) -> None:
    _, beats, _, _, _ = setup
    _, payload = _run(setup)
    fold = np.full(beats.sample.size, -1, dtype=np.int64)
    for k, (_, val) in enumerate(beat_splitter().indices(beats)):
        fold[val] = k
    leaky = payload["leaky_split"]
    assert leaky["assignment_sha256"] == fold_assignment_sha256(fold)
    assert leaky["name"] == "beat"
    assert leaky["seed"] == 20261030
    assert payload["selection"] == {"width": WIDTH, "epoch": EPOCH, "C": CHOSEN_C}


def test_accuracy_is_computed_only_in_the_exhibit() -> None:
    # Design call 10: no other module, so no other results payload, has it.
    hits = sorted(
        path.relative_to(PACKAGE_DIR).as_posix()
        for path in PACKAGE_DIR.rglob("*.py")
        if "accuracy" in path.read_text(encoding="utf-8").lower()
    )
    assert hits == ["train/exhibit.py"]


def _keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return set(value) | set().union(*(_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value))
    return set()


def test_the_baseline_summary_has_no_accuracy() -> None:
    beats = synthetic_beats()
    folds = synthetic_folds(beats)
    chosen = select_baseline_c(beats, folds, grid=(0.1, 1.0))
    payload = baseline_summary(chosen, beats, folds_sha256="ab" * 32, n_draws=20)
    assert not any("accuracy" in k.lower() for k in _keys(payload))


def test_a_leaky_config_that_differs_in_another_key_raises(
    setup: tuple[Path, BeatTable, Folds, ModelSpec, dict[int, Path]],
) -> None:
    cv_runs = setup[4]
    path = cv_runs[1] / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["extra"]["resolved"]["n_epochs"] = 99
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="n_epochs"):
        _run(setup)
