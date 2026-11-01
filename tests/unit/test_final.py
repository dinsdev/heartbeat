"""MODEL-05, MODEL-06: final models on all DS1 rows, on CPU, for exactly the epochs."""

import hashlib
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from cnn_support import beats_with_traces
from cv_support import synthetic_beats
from numpy.typing import NDArray
from run_support import make_repo, settings
from sklearn.exceptions import ConvergenceWarning

from heartbeat.constants import SCORED_CLASSES
from heartbeat.data.loader import BeatTable
from heartbeat.models import baseline as baseline_module
from heartbeat.models.inputs import apply_rr_scaler, fit_rr_scaler, rr_model_inputs
from heartbeat.models.spec import ModelSpec
from heartbeat.train import final as final_module
from heartbeat.train.final import (
    FINAL_DEVICE,
    FinalBaseline,
    final_payload,
    train_final,
    train_final_baseline,
)
from heartbeat.train.loop import cnn_spec
from heartbeat.train.seeds import FINAL_FOLD
from heartbeat.train.weights import balanced_class_weights

WIDTH = 0.5
EPOCHS = 2


@pytest.fixture
def data() -> tuple[BeatTable, dict[str, NDArray[np.int16]]]:
    return beats_with_traces(n_subjects=4, per_subject=160)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def _train(
    repo: Path,
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
    seed: int = 0,
    root: Path | None = None,
) -> final_module.FinalModel:
    beats, traces = data
    return train_final(
        settings(repo.parent),
        beats,
        traces,
        width=WIDTH,
        epochs=EPOCHS,
        seed=seed,
        temperature=1.25 + seed,
        root=root or repo / "runs",
        repo=repo,
    )


def test_the_final_device_is_cpu_whatever_cv_device_says(
    repo: Path,
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert FINAL_DEVICE == "cpu"
    devices: list[str] = []

    def spy(traces: Mapping[str, NDArray[np.int16]], device: str) -> ModelSpec:
        devices.append(device)
        return cnn_spec(traces, device)

    monkeypatch.setattr(final_module, "cnn_spec", spy)
    model = _train(repo, data)
    assert devices == ["cpu"]
    assert model.device == "cpu"
    provenance = json.loads(
        (repo / "runs" / model.run / "provenance.json").read_text("utf-8")
    )
    assert provenance["device"] == "cpu"
    assert provenance["deterministic"] is True


def test_training_uses_every_row_for_exactly_the_selected_epochs(
    repo: Path,
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beats, _ = data
    seen: list[dict[str, Any]] = []

    def spy(traces: Mapping[str, NDArray[np.int16]], device: str) -> ModelSpec:
        real = cnn_spec(traces, device)
        assert real.fit_epochs is not None
        real_epochs = real.fit_epochs

        def fit_epochs(
            x: Any,
            y: NDArray[np.str_],
            w: Mapping[str, float],
            params: Mapping[str, Any],
            fold: int,
            n_epochs: int,
        ) -> Iterator[Any]:
            record = {"x": x, "y": y, "w": dict(w), "fold": fold, "epochs": 0}
            seen.append(record)
            for model in real_epochs(x, y, w, params, fold, n_epochs):
                record["epochs"] += 1
                yield model

        return ModelSpec(
            real.name, real.inputs, real.fit, real.logits, fit_epochs, real.config
        )

    monkeypatch.setattr(final_module, "cnn_spec", spy)
    model = _train(repo, data)
    (call,) = seen
    np.testing.assert_array_equal(call["y"], beats.beat_class)
    np.testing.assert_array_equal(call["x"].sample, beats.sample)
    np.testing.assert_array_equal(call["x"].record, beats.record_id)
    assert call["fold"] == FINAL_FOLD
    assert call["epochs"] == EPOCHS == model.epochs
    assert call["w"] == balanced_class_weights(beats.beat_class) == model.class_weights
    scaler = fit_rr_scaler(rr_model_inputs(beats.rr_s))
    np.testing.assert_array_equal(model.scaler_mean, scaler.mean)
    np.testing.assert_array_equal(model.scaler_std, scaler.std)


def test_the_temperature_is_that_seeds_and_the_checksum_matches_the_file(
    repo: Path, data: tuple[BeatTable, dict[str, NDArray[np.int16]]]
) -> None:
    model = _train(repo, data, seed=1)
    assert model.temperature == 2.25
    assert model.seed == 1
    assert model.width == WIDTH
    path = repo / "runs" / model.run / "model.pt"
    assert model.checkpoint == path
    assert model.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    state = torch.load(path, weights_only=True)
    assert "head.3.weight" in state
    assert model.run.endswith("-train-final-s1")


def test_two_runs_with_one_seed_write_byte_identical_checkpoints(
    repo: Path, data: tuple[BeatTable, dict[str, NDArray[np.int16]]]
) -> None:
    first = _train(repo, data, seed=2, root=repo / "runs" / "a")
    second = _train(repo, data, seed=2, root=repo / "runs" / "b")
    assert first.checkpoint.read_bytes() == second.checkpoint.read_bytes()
    assert first.sha256 == second.sha256
    other = _train(repo, data, seed=0, root=repo / "runs" / "c")
    assert other.sha256 != first.sha256


def test_the_payload_records_each_model(
    repo: Path, data: tuple[BeatTable, dict[str, NDArray[np.int16]]]
) -> None:
    model = _train(repo, data)
    baseline = _fit_baseline(repo, data[0])
    payload = final_payload(
        [model], width=WIDTH, epochs=EPOCHS, repo=repo, baseline=baseline
    )
    json.dumps(payload, allow_nan=False)
    assert payload["width"] == WIDTH
    assert payload["epochs"] == EPOCHS
    assert payload["shipped_seed"] == 0
    (entry,) = payload["models"]
    assert entry["seed"] == 0
    assert entry["run"] == model.run
    assert entry["path"] == f"runs/{model.run}/model.pt"
    assert entry["sha256"] == model.sha256
    assert entry["temperature"] == model.temperature
    assert entry["device"] == "cpu"
    assert entry["torch_threads"] == 4
    assert entry["deterministic"] is True
    assert entry["class_weights"] == model.class_weights
    assert entry["scaler"]["mean"] == model.scaler_mean.tolist()
    assert entry["wall_s"] > 0
    assert sorted(entry) == [
        "class_weights",
        "deterministic",
        "device",
        "epochs",
        "path",
        "run",
        "scaler",
        "seed",
        "sha256",
        "temperature",
        "torch_threads",
        "wall_s",
        "width",
    ]


# Phase 5 settling 1: the frozen baseline on every DS1 row.
CHOSEN_C = 0.1
BASELINE_TEMPERATURE = 1.17


def _fit_baseline(
    repo: Path, beats: BeatTable, root: Path | None = None
) -> FinalBaseline:
    return train_final_baseline(
        settings(repo.parent),
        beats,
        c=CHOSEN_C,
        temperature=BASELINE_TEMPERATURE,
        root=root or repo / "runs",
        repo=repo,
    )


def test_the_baseline_fits_every_row_at_the_chosen_c(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beats = synthetic_beats(n_subjects=4)
    seen: list[dict[str, Any]] = []
    real_fit = baseline_module.BASELINE.fit

    def spy(
        x: NDArray[np.float64],
        y: NDArray[np.str_],
        w: Mapping[str, float],
        params: Mapping[str, Any],
    ) -> Any:
        seen.append({"x": x, "y": y, "w": dict(w), "params": dict(params)})
        return real_fit(x, y, w, params)

    monkeypatch.setattr(
        final_module,
        "BASELINE",
        ModelSpec(
            "baseline",
            baseline_module.BASELINE.inputs,
            spy,
            baseline_module.BASELINE.logits,
            config=baseline_module.BASELINE.config,
        ),
    )
    fitted = _fit_baseline(repo, beats)
    (call,) = seen
    np.testing.assert_array_equal(call["y"], beats.beat_class)
    scaler = fit_rr_scaler(rr_model_inputs(beats.rr_s))
    np.testing.assert_array_equal(
        call["x"], apply_rr_scaler(scaler, rr_model_inputs(beats.rr_s))
    )
    assert call["params"] == {"C": CHOSEN_C}
    assert call["w"] == balanced_class_weights(beats.beat_class)
    assert fitted.class_weights == call["w"]
    assert fitted.c == CHOSEN_C
    assert fitted.temperature == BASELINE_TEMPERATURE
    assert fitted.n_rows == beats.sample.size
    np.testing.assert_array_equal(fitted.scaler_mean, scaler.mean)
    np.testing.assert_array_equal(fitted.scaler_std, scaler.std)
    assert fitted.coefficients.shape == (4, 6)
    assert fitted.intercepts.shape == (4,)
    assert fitted.run.endswith("-train-final-baseline")
    with np.load(repo / "runs" / fitted.run / "baseline.npz") as saved:
        np.testing.assert_array_equal(saved["coef"], fitted.coefficients)
        np.testing.assert_array_equal(saved["intercept"], fitted.intercepts)
        assert saved["classes"].tolist() == list(SCORED_CLASSES)


def test_the_baseline_coefficients_follow_scored_class_order(repo: Path) -> None:
    beats = synthetic_beats(n_subjects=4)
    fitted = _fit_baseline(repo, beats)
    x = apply_rr_scaler(
        fit_rr_scaler(rr_model_inputs(beats.rr_s)), rr_model_inputs(beats.rr_s)
    )
    expected = baseline_module.BASELINE.logits(fitted.fitted, x)
    np.testing.assert_allclose(
        x @ fitted.coefficients.T + fitted.intercepts, expected, rtol=0, atol=1e-12
    )


def test_two_baseline_fits_give_equal_coefficients(repo: Path) -> None:
    beats = synthetic_beats(n_subjects=4)
    first = _fit_baseline(repo, beats, root=repo / "runs" / "a")
    second = _fit_baseline(repo, beats, root=repo / "runs" / "b")
    np.testing.assert_array_equal(first.coefficients, second.coefficients)
    np.testing.assert_array_equal(first.intercepts, second.intercepts)


def test_a_baseline_convergence_warning_raises(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(baseline_module, "BASELINE_MAX_ITER", 1)
    with pytest.raises(ConvergenceWarning):
        _fit_baseline(repo, synthetic_beats(n_subjects=4))


def test_the_payload_has_a_baseline_block(
    repo: Path, data: tuple[BeatTable, dict[str, NDArray[np.int16]]]
) -> None:
    model = _train(repo, data)
    baseline = _fit_baseline(repo, data[0])
    payload = final_payload(
        [model], width=WIDTH, epochs=EPOCHS, repo=repo, baseline=baseline
    )
    json.dumps(payload, allow_nan=False)
    block = payload["baseline"]
    assert block["run"] == baseline.run
    assert block["C"] == CHOSEN_C
    assert block["temperature"] == BASELINE_TEMPERATURE
    assert block["classes"] == list(SCORED_CLASSES)
    assert block["coefficients"] == baseline.coefficients.tolist()
    assert block["intercepts"] == baseline.intercepts.tolist()
    assert block["scaler"] == {
        "mean": baseline.scaler_mean.tolist(),
        "std": baseline.scaler_std.tolist(),
    }
    assert block["class_weights"] == baseline.class_weights
    assert block["n_rows"] == data[0].sample.size
    assert block["solver"] == "lbfgs"
