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
from cnn_support import beats_with_traces, epoch_spec
from cv_support import subset_rows, synthetic_beats, synthetic_folds
from numpy.typing import NDArray
from scipy.special import log_softmax, softmax
from sklearn.model_selection import StratifiedKFold

from heartbeat.constants import BASELINE_C_GRID, LEAKY_SPLIT_SEED, SCORED_CLASSES
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
from heartbeat.signal.windows import zscore_windows
from heartbeat.train import cv as cv_module
from heartbeat.train.cv import (
    CALIBRATION_LABEL,
    CROSS_FIT_LABEL,
    Splitter,
    baseline_summary,
    beat_splitter,
    cross_validate,
    cross_validate_epochs,
    cv_summary,
    fold_indices,
    oof_predictions,
    patient_splitter,
    resolved_config,
    select_baseline_c,
)
from heartbeat.train.loop import cnn_spec
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
    result = cross_validate(BASELINE, beats, patient_splitter(folds), {"C": 1.0})
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
    result = cross_validate(BASELINE, beats, patient_splitter(folds), {"C": 1.0})
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
    result = cross_validate(spec, beats, patient_splitter(folds), {"C": 1.0})
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
        spec: ModelSpec, b: BeatTable, f: Splitter, params: Mapping[str, Any]
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
    before = cross_validate(BASELINE, beats, patient_splitter(folds), {"C": 1.0})
    after = cross_validate(BASELINE, planted, patient_splitter(folds), {"C": 1.0})
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
    summary = baseline_summary(chosen, beats, folds_sha256="ab" * 32, n_draws=200)
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
    # Phase 4 settling 1: seven values, widened once and never again.
    assert BASELINE_C_GRID == (0.0001, 0.001, 0.01, 0.1, 1.0, 10.0, 100.0)


def test_summary_reports_a_cross_fitted_calibration_block(
    beats: BeatTable, folds: Folds
) -> None:
    # Settling 4 as amended (Din, option 2): per-fold temperatures beside the
    # in-sample one, which stays the shipped temperature.
    chosen = select_baseline_c(beats, folds, grid=SMALL_GRID)
    summary = baseline_summary(chosen, beats, folds_sha256="ab" * 32, n_draws=50)
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


# Phase 4, Task 4: splitters, the epoch driver and the CNN in the same driver.


def test_cross_validate_epochs_gives_every_beat_one_prediction_per_epoch(
    beats: BeatTable, folds: Folds
) -> None:
    result = cross_validate_epochs(
        epoch_spec(), beats, patient_splitter(folds), {}, n_epochs=3
    )
    n = beats.sample.size
    assert result.logits.shape == (3, n, 4)
    assert result.logits.dtype == np.float32
    assert np.all(np.isfinite(result.logits))
    expected_fold = np.array([folds.subject_fold[s] for s in beats.subject_id])
    np.testing.assert_array_equal(result.fold, expected_fold)
    # Epoch e's logits for fold k come from fold k's model after epoch e.
    rr = rr_model_inputs(beats.rr_s)
    for k, (train, val) in enumerate(fold_indices(beats, folds)):
        scaler = fit_rr_scaler(rr[train])
        x_val = (rr[val] - scaler.mean) / scaler.std
        for e in range(3):
            np.testing.assert_array_equal(
                result.logits[e, val], (x_val[:, :4] * (e + 1) + k).astype(np.float32)
            )


@pytest.mark.rule("R21")
def test_the_epoch_driver_takes_folds_only_from_the_splitter(
    beats: BeatTable, folds: Folds
) -> None:
    n = beats.sample.size
    planted = [
        (np.flatnonzero(np.arange(n) % 5 != k), np.flatnonzero(np.arange(n) % 5 == k))
        for k in range(5)
    ]
    calls: list[int] = []

    def indices(b: BeatTable) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
        calls.append(1)
        return planted

    splitter = Splitter(name="planted", config={"name": "planted"}, indices=indices)
    result = cross_validate_epochs(epoch_spec(), beats, splitter, {}, n_epochs=1)
    assert calls == [1]
    np.testing.assert_array_equal(result.fold, np.arange(n) % 5)


@pytest.mark.rule("R21")
def test_the_epoch_driver_takes_weights_only_from_balanced_class_weights(
    beats: BeatTable, folds: Folds, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[NDArray[np.str_]] = []

    def weights_spy(y_train: NDArray[np.str_]) -> dict[str, float]:
        seen.append(y_train)
        return {"N": 0.1 * len(seen), "S": 2.0, "V": 3.0, "F": 4.0}

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(cv_module, "balanced_class_weights", weights_spy)
    result = cross_validate_epochs(
        epoch_spec(calls), beats, patient_splitter(folds), {}, n_epochs=1
    )
    assert len(seen) == 5
    for k, (train, _) in enumerate(fold_indices(beats, folds)):
        np.testing.assert_array_equal(seen[k], beats.beat_class[train])
    assert [c["weights"] for c in calls] == [dict(w) for w in result.class_weights]
    assert [c["fold"] for c in calls] == [0, 1, 2, 3, 4]


def test_the_epoch_driver_fits_the_scaler_on_training_rows_only(
    folds: Folds,
) -> None:
    beats = synthetic_beats()
    _, val0 = fold_indices(beats, folds)[0]
    rr_s = beats.rr_s.copy()
    rr_s[val0[0], 0] = 50.0
    planted = BeatTable(
        beats.record_id,
        beats.subject_id,
        beats.sample,
        beats.beat_class,
        beats.window_adu,
        rr_s,
    )
    spec = epoch_spec()
    before = cross_validate_epochs(spec, beats, patient_splitter(folds), {}, 1)
    after = cross_validate_epochs(spec, planted, patient_splitter(folds), {}, 1)
    np.testing.assert_array_equal(after.scalers[0].mean, before.scalers[0].mean)
    assert not np.array_equal(after.scalers[1].mean, before.scalers[1].mean)


def test_cross_validate_needs_fit_and_the_epoch_driver_needs_fit_epochs(
    beats: BeatTable, folds: Folds
) -> None:
    with pytest.raises(ValueError, match="fit"):
        cross_validate(epoch_spec(), beats, patient_splitter(folds), {})
    no_epochs = ModelSpec(
        name="b", inputs=BASELINE.inputs, fit=BASELINE.fit, logits=BASELINE.logits
    )
    with pytest.raises(ValueError, match="fit_epochs"):
        cross_validate_epochs(no_epochs, beats, patient_splitter(folds), {}, 1)


def test_the_beat_splitter_puts_every_beat_in_exactly_one_validation_fold(
    beats: BeatTable,
) -> None:
    pairs = beat_splitter().indices(beats)
    assert len(pairs) == 5
    seen = np.concatenate([val for _, val in pairs])
    assert sorted(seen.tolist()) == list(range(beats.sample.size))
    for train, val in pairs:
        assert not set(train.tolist()) & set(val.tolist())
        assert len(train) + len(val) == beats.sample.size


def test_the_beat_splitter_is_stratified_k_fold_with_the_exhibit_seed(
    beats: BeatTable,
) -> None:
    assert LEAKY_SPLIT_SEED == 20261030
    splitter = beat_splitter()
    assert splitter.config == {
        "name": "beat",
        "method": "StratifiedKFold",
        "n_splits": 5,
        "shuffle": True,
        "seed": LEAKY_SPLIT_SEED,
    }
    ours = splitter.indices(beats)
    own = StratifiedKFold(n_splits=5, shuffle=True, random_state=LEAKY_SPLIT_SEED)
    y = beats.beat_class
    for (train, val), (t2, v2) in zip(
        ours, own.split(np.zeros(y.size), y), strict=True
    ):
        np.testing.assert_array_equal(val, v2)
        np.testing.assert_array_equal(train, t2)
    # Class proportions per fold are within one beat of a fifth of each class.
    for _, val in ours:
        for cls in SCORED_CLASSES:
            total = int((y == cls).sum())
            assert abs(int((y[val] == cls).sum()) - total / 5) < 1


def test_the_beat_splitter_is_identical_across_calls_and_mixes_patients(
    beats: BeatTable,
) -> None:
    first = beat_splitter().indices(beats)
    second = beat_splitter().indices(beats)
    for (a, b), (c, d) in zip(first, second, strict=True):
        np.testing.assert_array_equal(a, c)
        np.testing.assert_array_equal(b, d)
    # The leak the exhibit shows: a patient's beats on both sides of a fold.
    train, val = first[0]
    assert set(beats.subject_id[train].tolist()) & set(beats.subject_id[val].tolist())


def test_the_patient_splitter_names_the_fold_file(folds: Folds) -> None:
    splitter = patient_splitter(folds)
    assert splitter.name == "patient"
    assert splitter.config["name"] == "patient"
    assert splitter.config["subject_fold"] == dict(sorted(folds.subject_fold.items()))


@pytest.mark.rule("R24")
@pytest.mark.parametrize("model", ["cnn", "baseline"])
def test_honest_and_leaky_configs_differ_only_in_the_splitter(
    model: str, folds: Folds
) -> None:
    if model == "cnn":
        spec = cnn_spec({}, "mps")
        params: dict[str, Any] = {"width": 1.0, "seed": 0}
        n_epochs: int | None = 40
    else:
        spec = BASELINE
        params = {"C": 0.001}
        n_epochs = None
    honest = resolved_config(spec, patient_splitter(folds), params, n_epochs)
    leaky = resolved_config(spec, beat_splitter(), params, n_epochs)
    assert {k for k in honest if honest[k] != leaky.get(k)} == {"splitter"}
    assert set(honest) == set(leaky)
    assert honest["splitter"]["name"] == "patient"
    assert leaky["splitter"]["name"] == "beat"
    json.dumps(honest, allow_nan=False)


def test_resolved_config_carries_everything_the_cnn_run_depends_on(
    folds: Folds,
) -> None:
    config = resolved_config(
        cnn_spec({}, "cpu"), patient_splitter(folds), {"width": 0.5, "seed": 2}, 40
    )
    assert config["model"] == "cnn"
    assert config["params"] == {"width": 0.5, "seed": 2}
    assert config["n_epochs"] == 40
    assert config["model_config"]["device"] == "cpu"
    for key, value in {
        "batch_size": 256,
        "learning_rate": 1e-3,
        "weight_decay": 1e-4,
        "shift_max_samples": 5,
        "noise_std_z": 0.05,
        "torch_threads": 4,
        "deterministic": True,
    }.items():
        assert config["model_config"][key] == value
    assert config["driver"] == {
        "class_weights": "balanced_class_weights",
        "rr_scaler": "fit_rr_scaler",
        "selection_metric": "selection_score",
    }


def test_a_tiny_cnn_runs_end_to_end_through_the_driver_on_cpu() -> None:
    small, traces = beats_with_traces(n_subjects=10, per_subject=140)
    small_folds = synthetic_folds(small)
    spec = cnn_spec(traces, "cpu")
    result = cross_validate_epochs(
        spec, small, patient_splitter(small_folds), {"width": 0.5, "seed": 0}, 2
    )
    assert result.logits.shape == (2, small.sample.size, 4)
    assert np.all(np.isfinite(result.logits))
    assert not np.array_equal(result.logits[0], result.logits[1])
    assert len(result.fitted) == 5
    assert result.config["splitter"]["name"] == "patient"


def test_cnn_inputs_are_unaugmented_float32_windows_and_rr(
    beats: BeatTable,
) -> None:
    small, traces = beats_with_traces(n_subjects=2, per_subject=20)
    rows = np.arange(5, 15)
    rr = np.ones((rows.size, 6))
    x = cnn_spec(traces, "cpu").inputs(small, rows, rr)
    np.testing.assert_array_equal(
        x.windows[:, 0, :], zscore_windows(small.window_adu[rows]).astype(np.float32)
    )
    assert x.rr.dtype == np.float32
    np.testing.assert_array_equal(x.record, small.record_id[rows])
    np.testing.assert_array_equal(x.sample, small.sample[rows])


def test_the_models_ast_check_covers_the_cnn_files() -> None:
    names = {p.name for p in (PACKAGE_DIR / "models").rglob("*.py")}
    assert {"cnn.py", "augment.py", "spec.py", "baseline.py"} <= names


def test_cv_summary_is_model_agnostic(beats: BeatTable, folds: Folds) -> None:
    chosen = select_baseline_c(beats, folds, grid=SMALL_GRID)
    oof = oof_predictions(
        "cnn",
        chosen.result.logits,
        chosen.result.fold,
        chosen.result.class_weights,
        chosen.y_true,
    )
    selection = {"width": 1.0, "epoch": 12}
    summary = cv_summary(
        oof, beats, selection, "DS1 out-of-fold, MPS", "ab" * 32, n_draws=50
    )
    assert summary["model"] == "cnn"
    assert summary["data"] == "DS1 out-of-fold, MPS"
    assert summary["width"] == 1.0
    assert summary["epoch"] == 12
    assert "chosen_c" not in summary
    assert set(summary["bootstrap"]["intervals"]) >= {"macro_f1_nsv", "S_recall"}
    json.dumps(summary, allow_nan=False)


def test_oof_predictions_calibrate_with_each_rows_fold_weights(
    beats: BeatTable, folds: Folds
) -> None:
    chosen = select_baseline_c(beats, folds, grid=SMALL_GRID)
    oof = oof_predictions(
        "baseline",
        chosen.result.logits,
        chosen.result.fold,
        chosen.result.class_weights,
        chosen.y_true,
    )
    np.testing.assert_array_equal(oof.adjusted, chosen.adjusted)
    assert oof.temperature == chosen.temperature
    np.testing.assert_array_equal(oof.labels, chosen.labels)
    np.testing.assert_array_equal(oof.probs, chosen.probs)


def test_only_folds_trains_the_named_folds_and_leaves_the_rest_unscored(
    beats: BeatTable, folds: Folds
) -> None:
    # Development runs (`cross-validate --model cnn --fold 0`, Task 9).
    calls: list[dict[str, Any]] = []
    result = cross_validate_epochs(
        epoch_spec(calls), beats, patient_splitter(folds), {}, 2, only_folds=[0]
    )
    expected = np.array([folds.subject_fold[s] for s in beats.subject_id])
    assert [c["fold"] for c in calls] == [0]
    assert np.all(np.isfinite(result.logits[:, expected == 0]))
    assert np.all(np.isnan(result.logits[:, expected != 0]))
    np.testing.assert_array_equal(result.fold[expected == 0], 0)
    np.testing.assert_array_equal(result.fold[expected != 0], -1)
    assert result.folds_run == (0,)
    assert len(result.class_weights) == len(result.fitted) == 1
