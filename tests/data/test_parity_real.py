"""R26, R27, PARITY-02, PARITY-03 (Python half): the committed fixtures and models.

Red until `rebuild` has exported the models (Phase 5, Task 10).
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from heartbeat.constants import PARITY_FIXTURE_QUOTA, PARITY_TOLERANCE, SCORED_CLASSES
from heartbeat.data.manifests import Splits
from heartbeat.data.npz import load_prepared
from heartbeat.data.prepare import PrepareReport
from heartbeat.evaluate.calibration import adjust_logits, calibrated_probs
from heartbeat.export.fixtures import FIXTURES_NAME, fixture_parity, rr_context
from heartbeat.models.inputs import RRScaler, apply_rr_scaler, rr_model_inputs
from heartbeat.paths import FIXTURES_DIR, MODELS_DIR
from heartbeat.sealed.score import load_calibration
from heartbeat.signal.rr import rr_features
from heartbeat.signal.windows import extract_windows, zscore_windows


@pytest.fixture(scope="module")
def fixtures() -> dict[str, Any]:
    path = FIXTURES_DIR / FIXTURES_NAME
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


@pytest.mark.rule("R27")
def test_every_fixture_beat_comes_from_ds1(
    fixtures: dict[str, Any], splits: Splits
) -> None:
    records = {b["record"] for b in fixtures["beats"]}
    assert records <= set(splits.ds1)
    assert not records & set(splits.ds2)
    assert not records & set(splits.excluded)
    classes = [b["class"] for b in fixtures["beats"]]
    assert {c: classes.count(c) for c in SCORED_CLASSES} == dict(PARITY_FIXTURE_QUOTA)


@pytest.mark.rule("R26")
def test_onnx_runtime_on_the_committed_models_matches_the_fixtures(
    fixtures: dict[str, Any],
) -> None:
    diffs = fixture_parity(MODELS_DIR, fixtures)
    assert sorted(diffs) == ["baseline", "seed-0", "seed-1", "seed-2"]
    assert max(diffs.values()) <= PARITY_TOLERANCE


def test_each_stored_step_matches_the_pipeline_on_the_cache(
    fixtures: dict[str, Any], prepared_ds1: tuple[Path, PrepareReport]
) -> None:
    folder, _ = prepared_ds1
    scaler_file = json.loads((MODELS_DIR / "scaler.json").read_text("utf-8"))
    scaler = RRScaler(
        mean=np.array(scaler_file["mean"]), std=np.array(scaler_file["std"])
    )
    assert fixtures["scaler"] == {
        "mean": scaler_file["mean"],
        "std": scaler_file["std"],
    }
    calibrations = {
        "0": load_calibration(MODELS_DIR / "calibration.json"),
        "1": load_calibration(MODELS_DIR / "seeds" / "seed-1" / "calibration.json"),
        "2": load_calibration(MODELS_DIR / "seeds" / "seed-2" / "calibration.json"),
    }
    prepared = {}
    for beat in fixtures["beats"]:
        record = beat["record"]
        if record not in prepared:
            prepared[record] = load_prepared(folder / f"{record}.npz")
        rec = prepared[record]
        index = int(np.searchsorted(rec.beat_sample, beat["sample"]))
        assert rec.beat_sample[index] == beat["sample"]
        assert rec.kept[index]
        assert rec.beat_class[index] == beat["class"]
        window = extract_windows(rec.trace_adu, rec.beat_sample[[index]])
        assert beat["window_adu"] == window[0].tolist()
        assert beat["window_z"] == zscore_windows(window)[0].tolist()
        context, position = rr_context(rec.beat_sample, index)
        assert beat["rr_beat_samples"] == context.tolist()
        assert beat["rr_beat_index"] == position
        # rr_s rows are the kept beats, which are every beat but the first and last.
        row = int(np.sum(rec.kept[:index]))
        assert beat["rr_s"] == rec.rr_s[row].tolist()
        assert beat["rr_s"] == rr_features(context)[position - 1].tolist()
        # The log ratios can round one step apart across platforms (macOS arm64
        # wrote the fixtures, CI runs Linux x86), so float steps after a log
        # compare at 1e-12 like the logits below.
        inputs = rr_model_inputs(rec.rr_s[[row]])
        np.testing.assert_allclose(beat["rr_inputs"], inputs[0], rtol=0, atol=1e-12)
        np.testing.assert_allclose(
            beat["rr_scaled"], apply_rr_scaler(scaler, inputs)[0], rtol=0, atol=1e-12
        )
        for seed, calibration in calibrations.items():
            out = beat["seeds"][seed]
            logits = np.array([out["logits"]])
            weights = dict(
                zip(SCORED_CLASSES, np.exp(calibration.log_class_weights), strict=True)
            )
            adjusted = adjust_logits(logits, weights)
            np.testing.assert_allclose(out["adjusted"], adjusted[0], rtol=0, atol=1e-12)
            probs = calibrated_probs(adjusted, calibration.temperature)
            np.testing.assert_allclose(
                out["probabilities"], probs[0], rtol=0, atol=1e-12
            )
            assert out["label"] == SCORED_CLASSES[int(np.argmax(logits[0]))]
