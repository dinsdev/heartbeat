"""Phase 4 design calls 3 and 4: CNN CV run folders, their reader and the curves."""

import json
from pathlib import Path

import numpy as np
import pytest
from cnn_support import beats_with_traces, epoch_spec
from cv_support import synthetic_beats, synthetic_folds
from run_support import make_repo, settings

from heartbeat.constants import SCORED_CLASSES
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.evaluate.metrics import confusion_matrix
from heartbeat.runs import create_run
from heartbeat.train.cnn_cv import (
    MissingRunError,
    curves_payload,
    data_label,
    epoch_confusions,
    load_epoch_run,
    run_cnn_cv,
    run_name,
    write_epoch_run,
)
from heartbeat.train.cv import cross_validate_epochs, patient_splitter


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def test_run_names_carry_width_and_seed() -> None:
    assert run_name(1.0, 0) == "cv-cnn-w1-s0"
    assert run_name(0.5, 2) == "cv-cnn-w0.5-s2"
    assert run_name(2.0, 1) == "cv-cnn-w2-s1"


def test_the_data_label_names_the_device() -> None:
    assert data_label("mps") == "DS1 out-of-fold, MPS"
    assert data_label("cpu") == "DS1 out-of-fold, CPU"


def test_epoch_confusions_score_each_epochs_argmax() -> None:
    rng = np.random.default_rng(0)
    logits = rng.normal(size=(3, 50, 4)).astype(np.float32)
    y = np.array(SCORED_CLASSES)[rng.integers(0, 4, 50)]
    cms = epoch_confusions(logits, y)
    assert cms.shape == (3, 4, 4)
    for e in range(3):
        np.testing.assert_array_equal(
            cms[e], confusion_matrix(y, predict_labels(logits[e].astype(np.float64)))
        )


def test_a_written_run_reads_back_exactly(repo: Path) -> None:
    beats = synthetic_beats()
    folds = synthetic_folds(beats)
    result = cross_validate_epochs(
        epoch_spec(), beats, patient_splitter(folds), {"seed": 1}, 3
    )
    with create_run(
        "cv-cnn-w1-s1", settings(repo.parent), {}, repo / "runs", repo
    ) as run:
        write_epoch_run(run, result, beats, width=1.0, seed=1)
    loaded = load_epoch_run(run.path)
    assert loaded.width == 1.0
    assert loaded.seed == 1
    assert loaded.logits.dtype == np.float32
    np.testing.assert_array_equal(loaded.logits, result.logits)
    np.testing.assert_array_equal(loaded.fold, result.fold)
    np.testing.assert_array_equal(loaded.record, beats.record_id)
    np.testing.assert_array_equal(loaded.sample, beats.sample)
    np.testing.assert_array_equal(loaded.true_class, beats.beat_class)
    assert loaded.class_weights == tuple(dict(w) for w in result.class_weights)
    assert loaded.run == run.name
    metrics = json.loads((run.path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["width"] == 1.0
    assert metrics["seed"] == 1
    np.testing.assert_array_equal(
        np.array(metrics["confusion"]),
        epoch_confusions(result.logits, beats.beat_class),
    )


def test_a_missing_run_names_the_rebuild_command(tmp_path: Path) -> None:
    with pytest.raises(MissingRunError, match="rebuild --from cross-validate-cnn"):
        load_epoch_run(tmp_path / "runs" / "gone-cv-cnn-w1-s0")


def test_a_partial_run_is_refused_for_selection(repo: Path) -> None:
    beats = synthetic_beats()
    folds = synthetic_folds(beats)
    result = cross_validate_epochs(
        epoch_spec(), beats, patient_splitter(folds), {}, 2, only_folds=[0]
    )
    with create_run("partial", settings(repo.parent), {}, repo / "runs", repo) as run:
        write_epoch_run(run, result, beats, width=1.0, seed=0)
    with pytest.raises(MissingRunError, match="folds"):
        load_epoch_run(run.path)


def test_the_curves_payload_holds_confusions_and_run_names_only() -> None:
    cms = np.zeros((4, 4, 4), dtype=np.int64)
    cms[:, 0, 0] = 5
    entries = [
        {"width": 0.5, "seed": 0, "run": "a", "confusion": cms},
        {"width": 0.5, "seed": 1, "run": "b", "confusion": cms + 1},
    ]
    payload = curves_payload(entries, "mps", "ab" * 32)
    json.dumps(payload, allow_nan=False)
    assert payload["data"] == "DS1 out-of-fold, MPS"
    assert payload["classes"] == list(SCORED_CLASSES)
    assert payload["n_epochs"] == 4
    assert payload["folds_sha256"] == "ab" * 32
    assert [(r["width"], r["seed"], r["run"]) for r in payload["runs"]] == [
        (0.5, 0, "a"),
        (0.5, 1, "b"),
    ]
    assert payload["runs"][1]["confusion"] == (cms + 1).tolist()
    assert set(payload["runs"][0]) == {"width", "seed", "run", "confusion"}


def test_run_cnn_cv_writes_a_run_folder_on_cpu(repo: Path) -> None:
    beats, traces = beats_with_traces(n_subjects=10, per_subject=140)
    folds = synthetic_folds(beats)
    run, entry = run_cnn_cv(
        settings(repo.parent),
        beats,
        traces,
        folds,
        "ab" * 32,
        width=0.5,
        seed=0,
        device="cpu",
        root=repo / "runs",
        repo=repo,
        n_epochs=2,
    )
    assert run.name.endswith("-cv-cnn-w0.5-s0")
    assert {p.name for p in run.path.iterdir()} == {
        "config.json",
        "provenance.json",
        "log.txt",
        "metrics.json",
        "oof.npz",
        "weights.npz",
    }
    config = json.loads((run.path / "config.json").read_text(encoding="utf-8"))
    assert config["extra"]["resolved"]["model"] == "cnn"
    assert config["extra"]["resolved"]["params"] == {"width": 0.5, "seed": 0}
    assert config["extra"]["resolved"]["splitter"]["name"] == "patient"
    assert config["extra"]["folds_sha256"] == "ab" * 32
    provenance = json.loads((run.path / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["device"] == "cpu"
    assert provenance["deterministic"] is True
    assert provenance["torch_threads"] == 4
    assert entry["run"] == run.name
    assert np.asarray(entry["confusion"]).shape == (2, 4, 4)
    with np.load(run.path / "weights.npz", allow_pickle=False) as weights:
        assert any(k.startswith("fold0.") for k in weights.files)
        assert any(k.startswith("fold4.") for k in weights.files)


def test_two_same_seed_cpu_runs_write_identical_weights_and_logits(
    repo: Path,
) -> None:
    beats, traces = beats_with_traces(n_subjects=10, per_subject=140)
    folds = synthetic_folds(beats)
    paths = []
    for i in range(2):
        run, _ = run_cnn_cv(
            settings(repo.parent),
            beats,
            traces,
            folds,
            "ab" * 32,
            width=0.5,
            seed=1,
            device="cpu",
            # One folder each: two runs of one name in one second would clash.
            root=repo / "runs" / str(i),
            repo=repo,
            n_epochs=1,
            only_folds=[2],
        )
        paths.append(run.path)
    for name in ("weights.npz", "oof.npz"):
        with (
            np.load(paths[0] / name, allow_pickle=False) as a,
            np.load(paths[1] / name, allow_pickle=False) as b,
        ):
            assert a.files == b.files
            for key in a.files:
                np.testing.assert_array_equal(a[key], b[key])
