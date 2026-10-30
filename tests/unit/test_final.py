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
from numpy.typing import NDArray
from run_support import make_repo, settings

from heartbeat.data.loader import BeatTable
from heartbeat.models.inputs import fit_rr_scaler, rr_model_inputs
from heartbeat.models.spec import ModelSpec
from heartbeat.train import final as final_module
from heartbeat.train.final import FINAL_DEVICE, final_payload, train_final
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
    payload = final_payload([model], width=WIDTH, epochs=EPOCHS, repo=repo)
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
