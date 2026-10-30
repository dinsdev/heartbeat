"""C1, C2, C3, EVAL-07: the model-agnostic CV driver and the baseline's C selection.

R21: the baseline and the CNN use the same folds, class weights and selection
metric, because the driver owns all three and a model supplies only its
inputs, `fit` and `logits`. Phase 4 adds the CNN spec to these tests.
"""

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from cv_support import subset_rows, synthetic_beats, synthetic_folds
from numpy.typing import NDArray
from scipy.special import log_softmax, softmax

from heartbeat.constants import BASELINE_C_GRID, SCORED_CLASSES
from heartbeat.data.folds import Folds
from heartbeat.data.loader import BeatTable
from heartbeat.evaluate.calibration import (
    adjust_logits,
    ece_equal_mass,
    fit_temperature,
)
from heartbeat.evaluate.metrics import class_indices
from heartbeat.models.baseline import BASELINE
from heartbeat.models.inputs import fit_rr_scaler, rr_model_inputs
from heartbeat.models.spec import ModelSpec
from heartbeat.paths import PACKAGE_DIR
from heartbeat.train import cv as cv_module
from heartbeat.train.cv import (
    CALIBRATION_LABEL,
    CROSS_FIT_LABEL,
    cross_validate,
    cv_summary,
    fold_indices,
    select_baseline_c,
)
from heartbeat.train.weights import balanced_class_weights

SMALL_GRID = (0.1, 1.0)


@pytest.fixture(scope="module")
def beats() -> BeatTable:
    return synthetic_beats()


@pytest.fixture(scope="module")
def folds(beats: BeatTable) -> Folds:
    return synthetic_folds(beats)


def test_fold_indices_follow_the_fold_file(beats: BeatTable, folds: Folds) -> None:
    pairs = fold_indices(beats, folds)
    assert len(pairs) == 5
    seen = np.concatenate([val for _, val in pairs])
    assert sorted(seen.tolist()) == list(range(beats.sample.size))
    for k, (train, val) in enumerate(pairs):
        fold_of = np.array([folds.subject_fold[s] for s in beats.subject_id])
        np.testing.assert_array_equal(val, np.flatnonzero(fold_of == k))
        np.testing.assert_array_equal(train, np.flatnonzero(fold_of != k))


def test_fold_indices_raise_on_a_subject_missing_from_the_folds(
    beats: BeatTable, folds: Folds
) -> None:
    partial = dict(folds.subject_fold)
    del partial["s03"]
    broken = Folds(
        folds.seed,
        folds.sklearn_version,
        folds.manifest_sha256,
        partial,
        folds.class_counts,
    )
    with pytest.raises(ValueError, match="s03"):
        fold_indices(beats, broken)


@pytest.mark.rule("R21")
def test_every_beat_gets_one_out_of_fold_prediction_from_its_subjects_fold(
    beats: BeatTable, folds: Folds
) -> None:
    result = cross_validate(BASELINE, beats, folds, {"C": 1.0})
    assert result.logits.shape == (beats.sample.size, 4)
    assert np.all(np.isfinite(result.logits))
    expected = np.array([folds.subject_fold[s] for s in beats.subject_id])
    np.testing.assert_array_equal(result.fold, expected)
    # Each fold's validation logits come from the model fitted without it.
    for k, (train, val) in enumerate(fold_indices(beats, folds)):
        rr = rr_model_inputs(beats.rr_s)
        scaler = fit_rr_scaler(rr[train])
        x_val = (rr[val] - scaler.mean) / scaler.std
        np.testing.assert_allclose(
            result.logits[val], BASELINE.logits(result.fitted[k], x_val), atol=1e-12
        )


@pytest.mark.rule("R21")
def test_folds_come_only_through_fold_indices(
    beats: BeatTable, folds: Folds, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A planted split (by beat parity within subjects is not a real fold; it
    # only shows the driver uses whatever fold_indices returns).
    n = beats.sample.size
    planted = [
        (np.flatnonzero(np.arange(n) % 5 != k), np.flatnonzero(np.arange(n) % 5 == k))
        for k in range(5)
    ]
    calls: list[int] = []

    def spy(
        b: BeatTable, f: Folds
    ) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
        calls.append(1)
        return planted

    monkeypatch.setattr(cv_module, "fold_indices", spy)
    result = cross_validate(BASELINE, beats, folds, {"C": 1.0})
    assert calls == [1]
    np.testing.assert_array_equal(result.fold, np.arange(n) % 5)


@pytest.mark.rule("R21")
def test_weights_come_only_through_balanced_class_weights(
    beats: BeatTable, folds: Folds, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[NDArray[np.str_]] = []
    received: list[Mapping[str, float]] = []

    def weights_spy(y_train: NDArray[np.str_]) -> dict[str, float]:
        seen.append(y_train)
        return {"N": 0.1 * len(seen), "S": 2.0, "V": 3.0, "F": 4.0}

    real_fit = BASELINE.fit

    def fit_spy(
        x: Any, y: NDArray[np.str_], w: Mapping[str, float], params: Mapping[str, Any]
    ) -> Any:
        received.append(dict(w))
        return real_fit(x, y, w, params)

    spec = ModelSpec(
        name="spy", inputs=BASELINE.inputs, fit=fit_spy, logits=BASELINE.logits
    )
    monkeypatch.setattr(cv_module, "balanced_class_weights", weights_spy)
    result = cross_validate(spec, beats, folds, {"C": 1.0})
    assert len(seen) == 5
    for k, (train, _) in enumerate(fold_indices(beats, folds)):
        np.testing.assert_array_equal(seen[k], beats.beat_class[train])
    assert received == [dict(w) for w in result.class_weights]
    assert [w["N"] for w in result.class_weights] == pytest.approx(
        [0.1, 0.2, 0.3, 0.4, 0.5]
    )


@pytest.mark.rule("R21")
def test_selection_comes_only_through_selection_score_and_cross_validate(
    beats: BeatTable, folds: Folds, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs: list[str] = []
    real_cv = cv_module.cross_validate

    def cv_spy(
        spec: ModelSpec, b: BeatTable, f: Folds, params: Mapping[str, Any]
    ) -> cv_module.CVResult:
        specs.append(spec.name)
        return real_cv(spec, b, f, params)

    scores = iter([0.2, 0.9])
    monkeypatch.setattr(cv_module, "cross_validate", cv_spy)
    monkeypatch.setattr(cv_module, "selection_score", lambda cm: next(scores))
    chosen = select_baseline_c(beats, folds, grid=SMALL_GRID)
    assert specs == [BASELINE.name, BASELINE.name]
    assert chosen.chosen_c == 1.0
    assert chosen.scores == {0.1: 0.2, 1.0: 0.9}


@pytest.mark.rule("R21")
def test_a_c_tie_keeps_the_smaller_c(
    beats: BeatTable, folds: Folds, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cv_module, "selection_score", lambda cm: 0.5)
    assert select_baseline_c(beats, folds, grid=(1.0, 0.1)).chosen_c == 0.1


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


@pytest.mark.rule("R21")
def test_models_never_read_folds_or_compute_weights() -> None:
    for path in sorted((PACKAGE_DIR / "models").rglob("*.py")):
        imports = _imports(path)
        text = path.read_text(encoding="utf-8")
        assert not any(i.startswith("heartbeat.data.folds") for i in imports), path
        assert not any(i.startswith("heartbeat.train") for i in imports), path
        assert "compute_class_weight" not in text, path
        assert '"balanced"' not in text, path
        assert "selection_score" not in text, path


@pytest.mark.rule("R21")
def test_the_driver_reads_folds_weights_and_selection_from_one_place() -> None:
    imports = _imports(PACKAGE_DIR / "train" / "cv.py")
    assert "heartbeat.train.weights.balanced_class_weights" in imports
    assert "heartbeat.evaluate.metrics.selection_score" in imports
    assert "heartbeat.data.folds.Folds" in imports


def test_scaler_is_fitted_on_training_rows_only(folds: Folds) -> None:
    beats = synthetic_beats()
    _, val0 = fold_indices(beats, folds)[0]
    rr_s = beats.rr_s.copy()
    rr_s[val0[0], 0] = 50.0  # a validation-only outlier in fold 0
    planted = BeatTable(
        beats.record_id,
        beats.subject_id,
        beats.sample,
        beats.beat_class,
        beats.window_adu,
        rr_s,
    )
    before = cross_validate(BASELINE, beats, folds, {"C": 1.0})
    after = cross_validate(BASELINE, planted, folds, {"C": 1.0})
    np.testing.assert_array_equal(after.scalers[0].mean, before.scalers[0].mean)
    np.testing.assert_array_equal(after.scalers[0].std, before.scalers[0].std)
    assert not np.array_equal(after.scalers[1].mean, before.scalers[1].mean)


def test_each_row_is_adjusted_with_its_own_folds_weights(
    beats: BeatTable, folds: Folds
) -> None:
    # Drop most F beats from fold 2's subjects, so fold weights differ.
    fold_of = np.array([folds.subject_fold[s] for s in beats.subject_id])
    is_f = beats.beat_class == "F"
    drop = np.flatnonzero((fold_of != 2) & is_f)[::2]
    keep = np.setdiff1d(np.arange(beats.sample.size), drop)
    uneven = subset_rows(beats, keep)
    chosen = select_baseline_c(uneven, folds, grid=SMALL_GRID)
    weights = chosen.result.class_weights
    assert weights[0]["F"] != weights[2]["F"]
    per_row = np.array(
        [[weights[k][c] for c in SCORED_CLASSES] for k in chosen.result.fold]
    )
    np.testing.assert_allclose(
        chosen.adjusted, adjust_logits(chosen.result.logits, per_row), atol=0
    )
    np.testing.assert_array_equal(
        chosen.labels,
        np.array(SCORED_CLASSES)[chosen.result.logits.argmax(axis=1)],
    )
    assert weights[0] == balanced_class_weights(uneven.beat_class[fold_of[keep] != 0])


def test_summary_has_no_nan_and_carries_the_calibration_label(
    beats: BeatTable, folds: Folds
) -> None:
    chosen = select_baseline_c(beats, folds, grid=SMALL_GRID)
    summary = cv_summary(chosen, beats, folds_sha256="ab" * 32, n_draws=200)
    json.dumps(summary, allow_nan=False)
    assert summary["model"] == "baseline"
    assert summary["chosen_c"] == chosen.chosen_c
    assert [row["C"] for row in summary["grid"]] == list(SMALL_GRID)
    assert summary["calibration"]["label"] == CALIBRATION_LABEL
    assert CALIBRATION_LABEL == "temperature fitted on these predictions"
    assert summary["calibration"]["temperature"] == chosen.temperature
    assert set(summary["calibration"]["ece"]) == {"S", "V"}
    assert len(summary["per_fold"]) == 5
    assert summary["patients"] == sorted(set(beats.subject_id.tolist()))
    assert summary["bootstrap"]["settings"]["draws"] == 200
    assert summary["bootstrap"]["intervals"]["macro_f1_nsv"]["draws"] == 200
    assert summary["folds_sha256"] == "ab" * 32
    spread = summary["fold_spread"]["macro_f1_nsv"]
    per_fold = [f["macro_f1_nsv"] for f in summary["per_fold"]]
    assert spread["min"] == min(per_fold)
    assert spread["max"] == max(per_fold)
    pooled = summary["pooled"]
    assert pooled["n_beats"] == beats.sample.size
    assert (
        summary["grid"][SMALL_GRID.index(chosen.chosen_c)]["macro_f1_nsv"]
        == (pooled["macro_f1_nsv"])
    )


def test_default_grid_is_the_locked_one() -> None:
    assert BASELINE_C_GRID == (0.01, 0.1, 1.0, 10.0, 100.0)


def test_summary_reports_a_cross_fitted_calibration_block(
    beats: BeatTable, folds: Folds
) -> None:
    # Settling 4 as amended (Din, option 2): per-fold temperatures beside the
    # in-sample one, which stays the shipped temperature.
    chosen = select_baseline_c(beats, folds, grid=SMALL_GRID)
    summary = cv_summary(chosen, beats, folds_sha256="ab" * 32, n_draws=50)
    calibration = summary["calibration"]
    assert calibration["temperature"] == chosen.temperature
    block = calibration["cross_fitted"]
    assert block["label"] == CROSS_FIT_LABEL
    assert CROSS_FIT_LABEL == "per-fold temperatures fitted on the other four folds"
    y = chosen.y_true
    fold = chosen.result.fold
    expected_t = [
        fit_temperature(chosen.adjusted[fold != k], y[fold != k]) for k in range(5)
    ]
    assert block["temperatures"] == expected_t
    scaled = chosen.adjusted / np.array(expected_t)[fold][:, np.newaxis]
    rows = np.arange(y.size)
    nll = -log_softmax(scaled, axis=1)[rows, class_indices(y)]
    assert block["log_loss"] == pytest.approx(float(nll.mean()), rel=1e-12)
    probs = softmax(scaled, axis=1)
    for cls in ("S", "V"):
        k = SCORED_CLASSES.index(cls)
        assert block["ece"][cls] == pytest.approx(
            ece_equal_mass(probs[:, k], y == cls), rel=1e-12
        )
    json.dumps(summary, allow_nan=False)
