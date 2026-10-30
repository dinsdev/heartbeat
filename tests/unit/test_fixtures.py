"""PARITY-02, E5, R27: DS1 parity fixtures that hold every preprocessing step."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from cnn_support import annotated_beats_with_traces
from numpy.typing import NDArray

from heartbeat.constants import (
    PARITY_FIXTURE_QUOTA,
    PARITY_TOLERANCE,
    RR_LOCAL_INTERVALS,
    RR_LONG_WINDOW_SAMPLES,
    SCORED_CLASSES,
)
from heartbeat.data.loader import BeatTable, SealedRecordError
from heartbeat.data.manifests import Splits
from heartbeat.evaluate.calibration import adjust_logits, calibrated_probs
from heartbeat.export.fixtures import (
    FixtureModel,
    build_fixtures,
    draw_fixture_rows,
    rr_context,
)
from heartbeat.models.cnn import HeartbeatCNN
from heartbeat.models.inputs import apply_rr_scaler, fit_rr_scaler, rr_model_inputs
from heartbeat.sealed.score import BaselineParams, baseline_logits
from heartbeat.signal.rr import rr_features
from heartbeat.signal.windows import zscore_windows
from heartbeat.train.loop import cnn_logits


def _beats() -> tuple[BeatTable, dict[str, NDArray[np.int64]]]:
    beats, _, annotated = annotated_beats_with_traces()
    return beats, annotated


SPLITS = Splits(
    ds1=tuple(f"s{k:02d}" for k in range(10)), ds2=("100",), excluded={}, lead="MLII"
)


def _models(beats: BeatTable) -> tuple[list[FixtureModel], BaselineParams]:
    models = []
    for seed in (0, 1, 2):
        torch.manual_seed(seed)
        models.append(
            FixtureModel(
                seed=seed,
                network=HeartbeatCNN(0.5).eval(),
                class_weights={"N": 0.3, "S": 9.0, "V": 3.0, "F": 30.0},
                temperature=1.5 + seed,
            )
        )
    scaler = fit_rr_scaler(rr_model_inputs(beats.rr_s))
    baseline = BaselineParams(
        coefficients=np.arange(24, dtype=np.float64).reshape(4, 6) / 10,
        intercepts=np.array([0.1, -0.2, 0.3, -0.4]),
        scaler_mean=scaler.mean,
        scaler_std=scaler.std,
        log_class_weights=np.log([0.3, 9.0, 3.0, 30.0]),
        temperature=1.2,
    )
    return models, baseline


@pytest.fixture(scope="module")
def built() -> tuple[BeatTable, dict[str, Any], BaselineParams]:
    beats, annotated = _beats()
    models, baseline = _models(beats)
    return beats, build_fixtures(beats, annotated, SPLITS, models, baseline), baseline


def test_the_draw_meets_the_quota_with_no_q_and_repeats() -> None:
    beats, _ = _beats()
    rows = draw_fixture_rows(beats)
    assert rows.tolist() == sorted(rows.tolist())
    classes = beats.beat_class[rows].tolist()
    assert {c: classes.count(c) for c in SCORED_CLASSES} == dict(PARITY_FIXTURE_QUOTA)
    assert "Q" not in classes
    assert np.array_equal(draw_fixture_rows(beats), rows)
    assert not np.array_equal(draw_fixture_rows(beats, seed=1), rows)


@pytest.mark.rule("R27")
def test_a_beat_outside_ds1_is_refused() -> None:
    beats, annotated = _beats()
    models, baseline = _models(beats)
    splits = Splits(ds1=SPLITS.ds1[1:], ds2=("s00",), excluded={}, lead="MLII")
    with pytest.raises(SealedRecordError, match="s00"):
        build_fixtures(beats, annotated, splits, models, baseline)


@pytest.mark.rule("R27")
def test_every_fixture_beat_is_ds1(
    built: tuple[BeatTable, dict[str, Any], BaselineParams],
) -> None:
    _, payload, _ = built
    assert len(payload["beats"]) == sum(PARITY_FIXTURE_QUOTA.values()) == 50
    assert {b["record"] for b in payload["beats"]} <= set(SPLITS.ds1)
    assert payload["data"] == "DS1 only (R27)"


@pytest.mark.parametrize("index", [1, 5, 10, 11, 40, 158])
def test_the_rr_context_reproduces_the_features(index: int) -> None:
    rng = np.random.default_rng(index)
    samples = np.cumsum(rng.integers(150, 600, size=160)).astype(np.int64)
    samples[100:] += RR_LONG_WINDOW_SAMPLES // 2
    context, position = rr_context(samples, index)
    assert context[position] == samples[index]
    assert context[-1] == samples[index + 1]
    assert position >= min(index, RR_LOCAL_INTERVALS)
    np.testing.assert_array_equal(
        rr_features(context)[position - 1], rr_features(samples)[index - 1]
    )


def test_each_stored_step_is_the_pipelines_own(
    built: tuple[BeatTable, dict[str, Any], BaselineParams],
) -> None:
    beats, payload, baseline = built
    models, _ = _models(beats)
    rows = draw_fixture_rows(beats)
    assert [(b["record"], b["sample"]) for b in payload["beats"]] == list(
        zip(beats.record_id[rows].tolist(), beats.sample[rows].tolist(), strict=True)
    )
    scaler = fit_rr_scaler(rr_model_inputs(beats.rr_s))
    assert payload["scaler"]["mean"] == scaler.mean.tolist()
    # The models score the fixture beats as one batch; float32 kernels can
    # differ in the last bits with the batch size, within the parity tolerance.
    batch_windows = zscore_windows(beats.window_adu[rows]).astype(np.float32)
    batch_rr = apply_rr_scaler(scaler, rr_model_inputs(beats.rr_s[rows]))
    batch_logits = {
        m.seed: cnn_logits(
            m.network,
            batch_windows[:, np.newaxis, :],
            batch_rr.astype(np.float32),
            torch.device("cpu"),
        ).astype(np.float64)
        for m in models
    }
    batch_base = baseline_logits(baseline, beats.rr_s[rows])
    for k, (beat, row) in enumerate(zip(payload["beats"], rows.tolist(), strict=True)):
        assert beat["class"] == beats.beat_class[row]
        window = beats.window_adu[row]
        assert beat["window_adu"] == window.tolist()
        z = zscore_windows(window[np.newaxis])[0]
        assert beat["window_z"] == z.tolist()
        context = np.array(beat["rr_beat_samples"], dtype=np.int64)
        position = beat["rr_beat_index"]
        assert context[position] == beat["sample"]
        assert rr_features(context)[position - 1].tolist() == beat["rr_s"]
        assert beat["rr_s"] == beats.rr_s[row].tolist()
        inputs = rr_model_inputs(beats.rr_s[row][np.newaxis])
        assert beat["rr_inputs"] == inputs[0].tolist()
        scaled = apply_rr_scaler(scaler, inputs)
        assert beat["rr_scaled"] == scaled[0].tolist()
        for model in models:
            out = beat["seeds"][str(model.seed)]
            logits = batch_logits[model.seed][k : k + 1]
            assert out["logits"] == logits[0].tolist()
            alone = cnn_logits(
                model.network,
                z.astype(np.float32)[np.newaxis, np.newaxis],
                scaled.astype(np.float32),
                torch.device("cpu"),
            )
            np.testing.assert_allclose(
                alone[0], out["logits"], rtol=0, atol=PARITY_TOLERANCE
            )
            adjusted = adjust_logits(logits, model.class_weights)
            assert out["adjusted"] == adjusted[0].tolist()
            probs = calibrated_probs(adjusted, model.temperature)
            assert out["probabilities"] == probs[0].tolist()
            assert out["label"] == SCORED_CLASSES[int(np.argmax(logits[0]))]
        assert beat["baseline"]["logits"] == batch_base[k].tolist()
    json.dumps(payload, allow_nan=False)


def test_the_payload_names_its_seeds_and_attribution(
    built: tuple[BeatTable, dict[str, Any], BaselineParams],
) -> None:
    _, payload, _ = built
    assert payload["seed"] == 20261031
    assert payload["quota"] == dict(PARITY_FIXTURE_QUOTA)
    assert payload["classes"] == list(SCORED_CLASSES)
    assert [m["seed"] for m in payload["models"]] == [0, 1, 2]
    assert payload["models"][0]["temperature"] == 1.5
    assert "MIT-BIH Arrhythmia Database" in payload["notice"]


def test_a_feature_that_does_not_reproduce_raises() -> None:
    beats, annotated = _beats()
    models, baseline = _models(beats)
    row = int(draw_fixture_rows(beats)[0])
    record = str(beats.record_id[row])
    moved = annotated[record].copy()
    moved[int(np.searchsorted(moved, beats.sample[row])) - 1] -= 5
    annotated[record] = moved
    with pytest.raises(ValueError, match="RR"):
        build_fixtures(beats, annotated, SPLITS, models, baseline)


def test_write_fixtures_is_canonical(
    tmp_path: Path, built: tuple[BeatTable, dict[str, Any], BaselineParams]
) -> None:
    from heartbeat.export.fixtures import write_fixtures
    from heartbeat.runs import canonical_json

    _, payload, _ = built
    path = write_fixtures(tmp_path / "parity", payload)
    assert path == tmp_path / "parity" / "fixtures.json"
    assert path.read_text("utf-8") == canonical_json(payload)
