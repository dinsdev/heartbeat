"""C4, EVAL-09: the paired patient bootstrap (R17) and its skip counts (R18).

Synthetic patients only; no record is read.
"""

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from heartbeat.constants import BOOTSTRAP_SEED, SCORED_CLASSES
from heartbeat.evaluate import bootstrap as bootstrap_module
from heartbeat.evaluate.bootstrap import (
    Interval,
    bootstrap,
    draw_confusions,
    draw_counts,
    paired_difference,
    patient_confusions,
    percentile_interval,
)
from heartbeat.evaluate.metrics import confusion_matrix, metric_values

N, S, V, F = range(4)


def _matrix(cells: dict[tuple[int, int], int]) -> NDArray[np.int64]:
    cm = np.zeros((4, 4), dtype=np.int64)
    for (i, j), n in cells.items():
        cm[i, j] = n
    return cm


def _beats(
    confusions: dict[str, NDArray[np.int64]],
) -> tuple[NDArray[np.str_], NDArray[np.str_], NDArray[np.str_]]:
    y_true: list[str] = []
    y_pred: list[str] = []
    subject: list[str] = []
    for patient, cm in confusions.items():
        for i, t in enumerate(SCORED_CLASSES):
            for j, p in enumerate(SCORED_CLASSES):
                n = int(cm[i, j])
                y_true += [t] * n
                y_pred += [p] * n
                subject += [patient] * n
    return np.array(y_true), np.array(y_pred), np.array(subject)


def test_patient_confusions_follow_the_patient_order() -> None:
    a = _matrix({(N, N): 5, (S, S): 2})
    b = _matrix({(V, N): 3})
    y_true, y_pred, subject = _beats({"b": b, "a": a})
    stacked = patient_confusions(y_true, y_pred, subject, ["a", "b", "c"])
    assert stacked.shape == (3, 4, 4)
    np.testing.assert_array_equal(stacked[0], a)
    np.testing.assert_array_equal(stacked[1], b)
    np.testing.assert_array_equal(stacked[2], np.zeros((4, 4)))


def test_patient_confusions_rejects_a_subject_outside_the_patient_list() -> None:
    y_true, y_pred, subject = _beats({"x": _matrix({(N, N): 1})})
    with pytest.raises(ValueError, match="x"):
        patient_confusions(y_true, y_pred, subject, ["a"])


@pytest.mark.rule("R17")
def test_draw_counts_resample_whole_patients_with_replacement() -> None:
    counts = draw_counts(7, n_draws=500, seed=3)
    assert counts.shape == (500, 7)
    assert counts.dtype == np.int64
    np.testing.assert_array_equal(counts.sum(axis=1), np.full(500, 7))
    assert counts.min() >= 0
    # With replacement: some draw repeats a patient.
    assert counts.max() > 1


@pytest.mark.rule("R17")
def test_same_seed_gives_the_same_counts_and_another_seed_differs() -> None:
    np.testing.assert_array_equal(draw_counts(9, 200, 5), draw_counts(9, 200, 5))
    assert not np.array_equal(draw_counts(9, 200, 5), draw_counts(9, 200, 6))


@pytest.mark.rule("R17")
def test_draw_counts_default_to_the_fixed_seed() -> None:
    np.testing.assert_array_equal(
        draw_counts(4, n_draws=50), draw_counts(4, n_draws=50, seed=BOOTSTRAP_SEED)
    )


@pytest.mark.rule("R17")
def test_a_planted_patient_contributes_all_or_none_of_its_beats_per_copy() -> None:
    rng = np.random.default_rng(11)
    confusions = rng.integers(0, 20, size=(6, 4, 4)).astype(np.int64)
    # Only patient 4 has F beats labeled S, seven of them.
    confusions[:, F, S] = 0
    confusions[4, F, S] = 7
    counts = draw_counts(6, n_draws=300, seed=1)
    drawn = draw_confusions(confusions, counts)
    np.testing.assert_array_equal(drawn[:, F, S], 7 * counts[:, 4])


@pytest.mark.rule("R17")
def test_draw_sum_equals_the_matrix_of_the_resampled_beats() -> None:
    patients = ["p0", "p1", "p2"]
    by_patient = {
        "p0": _matrix({(N, N): 4, (S, N): 1}),
        "p1": _matrix({(V, V): 2, (N, S): 1}),
        "p2": _matrix({(F, V): 1, (S, S): 3}),
    }
    y_true, y_pred, subject = _beats(by_patient)
    counts = np.array([[2, 0, 1], [0, 3, 0], [1, 1, 1]], dtype=np.int64)
    drawn = draw_confusions(
        patient_confusions(y_true, y_pred, subject, patients), counts
    )
    for d, row in enumerate(counts):
        index = np.concatenate(
            [
                np.tile(np.flatnonzero(subject == p), int(c))
                for p, c in zip(patients, row, strict=True)
            ]
        )
        np.testing.assert_array_equal(
            drawn[d], confusion_matrix(y_true[index], y_pred[index])
        )


@pytest.mark.rule("R17")
def test_two_models_in_one_call_share_one_counts_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int]] = []
    real = bootstrap_module.draw_counts

    def spy(
        n_patients: int, n_draws: int = 10_000, seed: int = BOOTSTRAP_SEED
    ) -> NDArray[np.int64]:
        calls.append((n_patients, n_draws, seed))
        return real(n_patients, n_draws, seed)

    monkeypatch.setattr(bootstrap_module, "draw_counts", spy)
    rng = np.random.default_rng(2)
    cnn = rng.integers(1, 30, size=(5, 4, 4)).astype(np.int64)
    result = bootstrap({"cnn": cnn, "baseline": cnn.copy()}, n_draws=400)
    assert len(calls) == 1
    assert result.counts.shape == (400, 5)
    # Same matrices on the same draws: the paired difference is exactly 0.
    diff = paired_difference(result, "cnn", "baseline", "macro_f1_nsv")
    assert diff.low == 0.0
    assert diff.high == 0.0


@pytest.mark.rule("R17")
def test_models_with_different_patient_counts_raise() -> None:
    with pytest.raises(ValueError, match="patients"):
        bootstrap(
            {
                "a": np.zeros((3, 4, 4), dtype=np.int64),
                "b": np.zeros((4, 4, 4), dtype=np.int64),
            },
            n_draws=10,
        )


@pytest.mark.rule("R17")
def test_point_estimate_is_the_metric_on_all_patients() -> None:
    rng = np.random.default_rng(4)
    confusions = rng.integers(1, 30, size=(5, 4, 4)).astype(np.int64)
    result = bootstrap({"m": confusions}, n_draws=100)
    pooled = metric_values(confusions.sum(axis=0))
    for name, value in pooled.items():
        assert result.intervals["m"][name].point == pytest.approx(float(value))


# R18: a patient set built so the skips are known exactly.
# A: predicts S. B and C: true S beats, none predicted S.
PATIENT_A = _matrix({(N, N): 20, (S, S): 4, (N, S): 1, (V, V): 3})
PATIENT_B = _matrix({(N, N): 30, (S, N): 2, (V, V): 2})
PATIENT_C = _matrix({(N, N): 25, (S, N): 3, (V, N): 1, (V, V): 1})
SKIP_COUNTS = np.array(
    [[1, 1, 1], [0, 3, 0], [0, 0, 3], [0, 2, 1], [3, 0, 0], [2, 1, 0]],
    dtype=np.int64,
)
# Draws 1, 2 and 3 hold no copy of A, so no beat is predicted S.
NO_PREDICTED_S = 3


@pytest.mark.rule("R18")
def test_no_predicted_s_skips_s_precision_only_and_counts_it() -> None:
    confusions = np.stack([PATIENT_A, PATIENT_B, PATIENT_C])
    result = bootstrap({"m": confusions}, counts=SKIP_COUNTS)
    intervals = result.intervals["m"]
    assert intervals["S_precision"].skipped == NO_PREDICTED_S
    assert intervals["ec57_S_ppv"].skipped == NO_PREDICTED_S
    assert intervals["S_recall"].skipped == 0
    assert intervals["S_f1"].skipped == 0
    assert intervals["macro_f1_nsv"].skipped == 0
    assert intervals["V_precision"].skipped == 0
    assert intervals["S_precision"].draws == len(SKIP_COUNTS)


@pytest.mark.rule("R18")
def test_skipped_draws_are_left_out_of_the_interval_not_counted_as_zero() -> None:
    confusions = np.stack([PATIENT_A, PATIENT_B, PATIENT_C])
    result = bootstrap({"m": confusions}, counts=SKIP_COUNTS)
    drawn = draw_confusions(confusions, SKIP_COUNTS)
    precision = metric_values(drawn)["S_precision"]
    defined = precision[[0, 4, 5]]
    expected = np.percentile(defined, [2.5, 97.5])
    interval = result.intervals["m"]["S_precision"]
    assert interval.low == pytest.approx(expected[0])
    assert interval.high == pytest.approx(expected[1])
    assert interval.low is not None
    assert interval.low > 0
    # S recall uses every draw, including those with no predicted S (recall 0).
    recall = result.intervals["m"]["S_recall"]
    assert recall.low == pytest.approx(
        np.percentile(metric_values(drawn)["S_recall"], 2.5)
    )


@pytest.mark.rule("R18")
def test_paired_difference_skips_draws_where_either_side_is_undefined() -> None:
    model_a = np.stack([PATIENT_A, PATIENT_B, PATIENT_C])
    # Model b predicts S only for patient B.
    b_patient_b = _matrix({(N, N): 30, (S, S): 2, (V, V): 2})
    model_b = np.stack(
        [_matrix({(N, N): 21, (S, N): 4, (V, V): 3}), b_patient_b, PATIENT_C]
    )
    result = bootstrap({"a": model_a, "b": model_b}, counts=SKIP_COUNTS)
    assert result.intervals["a"]["S_precision"].skipped == 3  # draws 1, 2, 3
    assert result.intervals["b"]["S_precision"].skipped == 2  # draws 2, 4
    diff = paired_difference(result, "a", "b", "S_precision")
    # Draws 1, 2, 3 (no A) or 2, 4 (no B): 1, 2, 3, 4 are skipped.
    assert diff.skipped == 4
    assert diff.draws == len(SKIP_COUNTS)
    point_a = result.intervals["a"]["S_precision"].point
    point_b = result.intervals["b"]["S_precision"].point
    assert diff.point == pytest.approx(point_a - point_b)


@pytest.mark.rule("R18")
def test_a_metric_undefined_in_every_draw_gives_no_interval() -> None:
    confusions = np.stack([PATIENT_B, PATIENT_C])
    result = bootstrap({"m": confusions}, n_draws=50)
    interval = result.intervals["m"]["S_precision"]
    assert interval.low is None
    assert interval.high is None
    assert interval.skipped == 50
    assert math.isnan(interval.point)


def test_percentile_interval_on_a_known_vector() -> None:
    values = np.arange(101, dtype=np.float64)
    assert percentile_interval(values) == (2.5, 97.5)
    with_nan = np.concatenate([values, [np.nan, np.nan]])
    assert percentile_interval(with_nan) == (2.5, 97.5)
    assert percentile_interval(np.array([np.nan])) is None


def test_interval_as_dict_writes_nan_as_none() -> None:
    interval = Interval(point=math.nan, low=None, high=None, skipped=4, draws=4)
    assert interval.as_dict() == {
        "point": None,
        "low": None,
        "high": None,
        "skipped": 4,
        "draws": 4,
    }
