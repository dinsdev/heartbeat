"""MODEL-04, Phase 4 settlings 2 and 3: width and epoch, then the CNN summary.

Hand-built curves and synthetic run folders; no record is read.
"""

import ast
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from cv_support import synthetic_beats, synthetic_folds
from numpy.typing import NDArray
from run_support import make_repo, settings

from heartbeat.constants import (
    BOOTSTRAP_SEED,
    CNN_SEEDS,
    CNN_WIDTHS,
    EPOCH_EDGE_FIRST,
    MAX_EPOCHS,
    SCORED_CLASSES,
)
from heartbeat.data.loader import BeatTable
from heartbeat.evaluate import bootstrap as bootstrap_module
from heartbeat.evaluate.bootstrap import (
    draw_counts,
    paired_difference,
    patient_confusions,
)
from heartbeat.evaluate.calibration import adjust_logits, fit_temperature
from heartbeat.evaluate.metrics import class_indices, macro_f1, selection_score
from heartbeat.models.spec import ModelSpec, epochs_only
from heartbeat.paths import PACKAGE_DIR
from heartbeat.runs import create_run
from heartbeat.train import select as select_module
from heartbeat.train.cnn_cv import MissingRunError, write_epoch_run
from heartbeat.train.cv import (
    OOFPredictions,
    cross_validate_epochs,
    oof_predictions,
    patient_splitter,
    row_weights,
)
from heartbeat.train.select import (
    Curves,
    EpochEdgeError,
    UndefinedScoreError,
    cnn_summary,
    epoch_curves,
    select_config,
)


def test_the_settled_cap_and_edge() -> None:
    assert MAX_EPOCHS == 40
    assert EPOCH_EDGE_FIRST == 36


def _curves(nsv: NDArray[np.float64]) -> Curves:
    return Curves(
        widths=CNN_WIDTHS,
        seeds=CNN_SEEDS,
        nsv=nsv,
        four_class=nsv - 0.1,
        runs={(w, s): f"run-w{w:g}-s{s}" for w in CNN_WIDTHS for s in CNN_SEEDS},
    )


def _base(seed: int = 0) -> NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    return rng.uniform(0.3, 0.5, size=(3, 3, MAX_EPOCHS))


def test_the_joint_argmax_over_width_and_epoch() -> None:
    nsv = _base()
    nsv[1, :, 11] = 0.9  # width 1, epoch 12
    selection = select_config(_curves(nsv))
    assert selection.width == 1.0
    assert selection.epoch == 12
    assert selection.score == pytest.approx(0.9)


def test_a_width_tie_goes_to_the_smaller_width() -> None:
    nsv = _base()
    nsv[2, :, 4] = 0.9  # width 2, epoch 5
    nsv[0, :, 19] = 0.9  # width 0.5, epoch 20
    selection = select_config(_curves(nsv))
    assert (selection.width, selection.epoch) == (0.5, 20)


def test_an_epoch_tie_goes_to_fewer_epochs() -> None:
    nsv = _base()
    nsv[1, :, 6] = 0.9
    nsv[1, :, 2] = 0.9
    selection = select_config(_curves(nsv))
    assert (selection.width, selection.epoch) == (1.0, 3)


def test_epoch_36_stops_and_35_does_not() -> None:
    nsv = _base()
    nsv[0, :, 35] = 0.9  # epoch 36
    with pytest.raises(EpochEdgeError, match="36"):
        select_config(_curves(nsv))
    nsv = _base()
    nsv[0, :, 34] = 0.9  # epoch 35
    assert select_config(_curves(nsv)).epoch == 35


def test_the_seed_mean_is_a_plain_mean_of_the_three_pooled_scores() -> None:
    nsv = _base()
    nsv[2, :, 9] = [0.6, 0.99, 0.6]  # mean 0.73
    nsv[1, :, 9] = [0.72, 0.72, 0.72]
    selection = select_config(_curves(nsv))
    np.testing.assert_array_equal(selection.seed_mean, nsv.mean(axis=1))
    assert (selection.width, selection.epoch) == (2.0, 10)


def test_an_undefined_score_raises() -> None:
    nsv = _base()
    nsv[0, 1, 3] = np.nan
    with pytest.raises(UndefinedScoreError, match=r"width 0\.5.*seed 1.*epoch 4"):
        select_config(_curves(nsv))


def test_the_selection_payload_has_every_curve_and_the_best_point_per_width() -> None:
    nsv = _base()
    nsv[1, :, 11] = 0.9
    payload = select_config(_curves(nsv)).payload()
    json.dumps(payload, allow_nan=False)
    assert payload["width"] == 1.0
    assert payload["epoch"] == 12
    assert payload["candidates"] == 120
    assert [c["width"] for c in payload["curves"]] == list(CNN_WIDTHS)
    one = payload["curves"][1]
    assert one["seed_mean"] == nsv[1].mean(axis=0).tolist()
    assert one["seed_mean_four_class"] == (nsv[1] - 0.1).mean(axis=0).tolist()
    assert [s["seed"] for s in one["per_seed"]] == list(CNN_SEEDS)
    assert one["per_seed"][2]["macro_f1_nsv"] == nsv[1, 2].tolist()
    assert one["per_seed"][2]["run"] == "run-w1-s2"
    best = {b["width"]: b for b in payload["best_per_width"]}
    assert best[1.0]["epoch"] == 12
    assert best[0.5]["epoch"] == int(np.argmax(nsv[0].mean(axis=0))) + 1


def test_epoch_curves_score_the_confusions_with_the_selection_metric() -> None:
    rng = np.random.default_rng(1)
    runs = []
    for w in CNN_WIDTHS:
        for s in CNN_SEEDS:
            cms = rng.integers(1, 50, size=(MAX_EPOCHS, 4, 4))
            runs.append(
                {"width": w, "seed": s, "run": f"r{w}{s}", "confusion": cms.tolist()}
            )
    curves = epoch_curves({"runs": runs, "n_epochs": MAX_EPOCHS})
    for entry in runs:
        wi = CNN_WIDTHS.index(entry["width"])
        si = CNN_SEEDS.index(entry["seed"])
        cms = np.asarray(entry["confusion"])
        assert curves.nsv[wi, si].tolist() == [selection_score(cm) for cm in cms]
        assert curves.four_class[wi, si].tolist() == [
            macro_f1(cm, SCORED_CLASSES) for cm in cms
        ]
        assert curves.runs[(entry["width"], entry["seed"])] == entry["run"]


def test_epoch_curves_need_every_width_and_seed() -> None:
    cms = np.ones((MAX_EPOCHS, 4, 4), dtype=np.int64).tolist()
    runs = [{"width": 1.0, "seed": 0, "run": "a", "confusion": cms}]
    with pytest.raises(ValueError, match="width"):
        epoch_curves({"runs": runs, "n_epochs": MAX_EPOCHS})


@pytest.mark.rule("R21")
def test_selection_imports_the_selection_metric_and_no_loader() -> None:
    tree = ast.parse((PACKAGE_DIR / "train" / "select.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    assert "heartbeat.evaluate.metrics.selection_score" in imported
    loaders = {
        "heartbeat.data.loader.load_ds1",
        "heartbeat.data.loader.load_ds1_traces",
        "heartbeat.data.npz.load_prepared",
        "heartbeat.data.records.read_record",
    }
    assert not imported & loaders


# The CNN summary on synthetic run folders.

WIDTH = 1.0
EPOCH = 2


def _informative_spec() -> ModelSpec:
    """Logits that lean toward the true class, with seed- and epoch-dependent noise.

    Informative logits keep the fitted temperatures inside their bounds.
    """

    def inputs(
        b: BeatTable, rows: NDArray[np.int64], rr: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        onehot = class_indices(b.beat_class[rows])[:, np.newaxis] == np.arange(4)
        return np.hstack([onehot.astype(np.float64), rr])

    def fit_epochs(
        x: NDArray[np.float64],
        y: NDArray[np.str_],
        w: Mapping[str, float],
        params: Mapping[str, Any],
        fold: int,
        n_epochs: int,
    ) -> Iterator[Any]:
        for epoch in range(1, n_epochs + 1):
            yield {"epoch": epoch, "seed": params["seed"]}

    def logits(model: Any, x: NDArray[np.float64]) -> NDArray[np.float64]:
        noise = x[:, 4:8] * (0.8 + 0.3 * model["seed"]) + 0.1 * model["epoch"]
        out: NDArray[np.float64] = 2.0 * x[:, :4] + noise
        return out

    return ModelSpec(
        name="cnn",
        inputs=inputs,
        fit=epochs_only,
        logits=logits,
        fit_epochs=fit_epochs,
    )


@pytest.fixture
def summary_inputs(
    tmp_path: Path,
) -> tuple[BeatTable, dict[int, Path], OOFPredictions, Any]:
    repo = make_repo(tmp_path)
    beats = synthetic_beats()
    folds = synthetic_folds(beats)
    paths: dict[int, Path] = {}
    for seed in CNN_SEEDS:
        result = cross_validate_epochs(
            _informative_spec(), beats, patient_splitter(folds), {"seed": seed}, 3
        )
        name = f"cv-cnn-w1-s{seed}"
        with create_run(name, settings(tmp_path), {}, repo / "runs", repo) as run:
            write_epoch_run(run, result, beats, width=WIDTH, seed=seed)
        paths[seed] = run.path
    # A baseline whose labels differ from the CNN's, still informative.
    rng = np.random.default_rng(5)
    onehot = class_indices(beats.beat_class)[:, np.newaxis] == np.arange(4)
    base_logits = 1.5 * onehot + rng.normal(size=(beats.sample.size, 4))
    fold = np.array([folds.subject_fold[s] for s in beats.subject_id])
    weights = tuple(dict.fromkeys(SCORED_CLASSES, 1.0) for _ in range(5))
    baseline = oof_predictions("baseline", base_logits, fold, weights, beats.beat_class)
    nsv = _base()
    nsv[1, :, EPOCH - 1] = 0.9
    selection = select_config(_curves(nsv))
    return beats, paths, baseline, selection


def test_the_headline_is_seed_0_through_the_shared_summary(
    summary_inputs: tuple[BeatTable, dict[int, Path], OOFPredictions, Any],
) -> None:
    beats, paths, baseline, selection = summary_inputs
    payload = cnn_summary(selection, paths, beats, baseline, "ab" * 32, "mps", 50)
    json.dumps(payload, allow_nan=False)
    assert payload["model"] == "cnn"
    assert payload["data"] == "DS1 out-of-fold, MPS"
    assert payload["width"] == WIDTH
    assert payload["epoch"] == EPOCH
    assert payload["seed"] == 0
    assert payload["label"] == "at the selected width and epoch"
    assert payload["calibration"]["cross_fitted"]["label"]
    assert payload["runs"] == {str(s): paths[s].name for s in CNN_SEEDS}


def test_each_seed_has_its_own_temperature(
    summary_inputs: tuple[BeatTable, dict[int, Path], OOFPredictions, Any],
) -> None:
    beats, paths, baseline, selection = summary_inputs
    payload = cnn_summary(selection, paths, beats, baseline, "ab" * 32, "mps", 50)
    temps = {t["seed"]: t["temperature"] for t in payload["temperatures"]}
    for seed in CNN_SEEDS:
        with np.load(paths[seed] / "oof.npz", allow_pickle=False) as data:
            logits = data["logits"][EPOCH - 1].astype(np.float64)
            fold = data["fold"]
            table = data["class_weights"]
        weights = [
            dict(zip(SCORED_CLASSES, row.tolist(), strict=True)) for row in table
        ]
        adjusted = adjust_logits(logits, row_weights(weights, fold))
        assert temps[seed] == fit_temperature(adjusted, beats.beat_class)
    assert len(set(temps.values())) == 3
    assert payload["calibration"]["temperature"] == temps[0]


def test_seeds_1_and_2_are_a_range_without_intervals(
    summary_inputs: tuple[BeatTable, dict[int, Path], OOFPredictions, Any],
) -> None:
    beats, paths, baseline, selection = summary_inputs
    payload = cnn_summary(selection, paths, beats, baseline, "ab" * 32, "mps", 50)
    other = payload["other_seeds"]
    assert other["seeds"] == [1, 2]
    values = [p["macro_f1_nsv"] for p in other["pooled"]]
    assert other["range"]["macro_f1_nsv"] == {"min": min(values), "max": max(values)}
    assert "intervals" not in json.dumps(other)


def test_the_paired_difference_uses_one_set_of_draws_for_both_models(
    summary_inputs: tuple[BeatTable, dict[int, Path], OOFPredictions, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beats, paths, baseline, selection = summary_inputs
    calls: list[Mapping[str, Any]] = []
    real = bootstrap_module.bootstrap

    def spy(confusions: Mapping[str, Any], *args: Any, **kwargs: Any) -> Any:
        calls.append(confusions)
        return real(confusions, *args, **kwargs)

    monkeypatch.setattr(select_module, "bootstrap", spy)
    payload = cnn_summary(selection, paths, beats, baseline, "ab" * 32, "mps", 60)
    assert [set(c) for c in calls] == [{"cnn", "baseline"}]
    diff = payload["paired_difference"]
    assert diff["label"] == "DS1 out-of-fold"
    assert diff["a"] == "cnn seed 0"
    assert diff["b"] == "baseline"
    # Recomputed by hand on the same draws.
    patients = sorted(set(beats.subject_id.tolist()))
    with np.load(paths[0] / "oof.npz", allow_pickle=False) as data:
        cnn_labels = np.array(SCORED_CLASSES)[data["logits"][EPOCH - 1].argmax(axis=1)]
    counts = draw_counts(len(patients), 60, BOOTSTRAP_SEED)
    result = real(
        {
            "cnn": patient_confusions(
                beats.beat_class, cnn_labels, beats.subject_id, patients
            ),
            "baseline": patient_confusions(
                beats.beat_class, baseline.labels, beats.subject_id, patients
            ),
        },
        counts=counts,
    )
    expected = paired_difference(result, "cnn", "baseline", "macro_f1_nsv").as_dict()
    assert diff["metrics"]["macro_f1_nsv"] == expected


def test_a_missing_seed_run_raises(
    summary_inputs: tuple[BeatTable, dict[int, Path], OOFPredictions, Any],
) -> None:
    beats, paths, baseline, selection = summary_inputs
    gone = dict(paths)
    gone[2] = paths[2].parent / "deleted"
    with pytest.raises(MissingRunError):
        cnn_summary(selection, gone, beats, baseline, "ab" * 32, "mps", 20)


def test_a_run_for_other_beats_raises(
    summary_inputs: tuple[BeatTable, dict[int, Path], OOFPredictions, Any],
) -> None:
    beats, paths, baseline, selection = summary_inputs
    other = BeatTable(
        beats.record_id,
        beats.subject_id,
        beats.sample + 1,
        beats.beat_class,
        beats.window_adu,
        beats.rr_s,
    )
    with pytest.raises(ValueError, match="beats"):
        cnn_summary(selection, paths, other, baseline, "ab" * 32, "mps", 20)
