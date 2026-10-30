"""C4, EVAL-08: metrics from a 4 by 4 confusion matrix agree with scikit-learn (R16)."""

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from numpy.typing import NDArray
from sklearn.metrics import confusion_matrix as sk_confusion_matrix
from sklearn.metrics import f1_score, precision_recall_fscore_support

from heartbeat.constants import HEADLINE_CLASSES, SCORED_CLASSES
from heartbeat.evaluate.metrics import (
    class_metrics,
    class_rates,
    confusion_matrix,
    ec57_metrics,
    macro_f1,
    metric_values,
    selection_score,
    summarize,
)

LABELS = list(SCORED_CLASSES)
label = st.sampled_from(SCORED_CLASSES)
pairs = st.lists(st.tuples(label, label), min_size=1, max_size=200)


def _arrays(
    pairs: list[tuple[str, str]],
) -> tuple[NDArray[np.str_], NDArray[np.str_]]:
    y_true = np.array([t for t, _ in pairs])
    y_pred = np.array([p for _, p in pairs])
    return y_true, y_pred


def _sklearn(
    y_true: NDArray[np.str_], y_pred: NDArray[np.str_]
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, zero_division=np.nan
    )
    return precision, recall, f1


# A hand case: rows are the expert label, columns the model label (N, S, V, F).
HAND = np.array(
    [
        [50, 3, 2, 1],  # N
        [4, 10, 1, 0],  # S
        [2, 1, 20, 2],  # V
        [1, 0, 3, 5],  # F: Fv = 3 is non-zero
    ],
    dtype=np.int64,
)


def _from_matrix(cm: NDArray[np.int64]) -> tuple[NDArray[np.str_], NDArray[np.str_]]:
    y_true: list[str] = []
    y_pred: list[str] = []
    for i, t in enumerate(SCORED_CLASSES):
        for j, p in enumerate(SCORED_CLASSES):
            y_true += [t] * int(cm[i, j])
            y_pred += [p] * int(cm[i, j])
    return np.array(y_true), np.array(y_pred)


@pytest.mark.rule("R16")
def test_confusion_matrix_equals_sklearn_on_the_hand_case() -> None:
    y_true, y_pred = _from_matrix(HAND)
    cm = confusion_matrix(y_true, y_pred)
    assert cm.dtype == np.int64
    assert cm.shape == (4, 4)
    np.testing.assert_array_equal(cm, HAND)
    np.testing.assert_array_equal(
        cm, sk_confusion_matrix(y_true, y_pred, labels=LABELS)
    )


@pytest.mark.rule("R16")
@pytest.mark.parametrize("bad", ["Q", "n", ""])
def test_confusion_matrix_rejects_a_label_outside_the_scored_classes(
    bad: str,
) -> None:
    with pytest.raises(ValueError, match="scored"):
        confusion_matrix(np.array(["N", bad]), np.array(["N", "N"]))
    with pytest.raises(ValueError, match="scored"):
        confusion_matrix(np.array(["N", "N"]), np.array(["N", bad]))


@pytest.mark.rule("R16")
def test_confusion_matrix_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="length"):
        confusion_matrix(np.array(["N", "S"]), np.array(["N"]))


@pytest.mark.rule("R16")
def test_hand_case_per_class_metrics_equal_sklearn() -> None:
    y_true, y_pred = _from_matrix(HAND)
    precision, recall, f1 = _sklearn(y_true, y_pred)
    metrics = class_metrics(HAND)
    for k, cls in enumerate(SCORED_CLASSES):
        assert metrics[cls].recall == pytest.approx(recall[k], abs=1e-12)
        assert metrics[cls].precision == pytest.approx(precision[k], abs=1e-12)
        assert metrics[cls].f1 == pytest.approx(f1[k], abs=1e-12)


@pytest.mark.rule("R16")
def test_hand_case_by_hand() -> None:
    metrics = class_metrics(HAND)
    # S: TP 10, FN 5, FP 3 + 1 + 0 = 4, TN 105 - 19 = 86.
    assert metrics["S"].recall == pytest.approx(10 / 15)
    assert metrics["S"].precision == pytest.approx(10 / 14)
    assert metrics["S"].f1 == pytest.approx(20 / (20 + 4 + 5))
    assert metrics["S"].fpr == pytest.approx(4 / (4 + 86))


@pytest.mark.rule("R16")
@given(pairs)
def test_per_class_metrics_equal_sklearn_on_random_labels(
    pairs: list[tuple[str, str]],
) -> None:
    y_true, y_pred = _arrays(pairs)
    precision, recall, f1 = _sklearn(y_true, y_pred)
    metrics = class_metrics(confusion_matrix(y_true, y_pred))
    ours_p = np.array([metrics[c].precision for c in SCORED_CLASSES])
    ours_r = np.array([metrics[c].recall for c in SCORED_CLASSES])
    ours_f = np.array([metrics[c].f1 for c in SCORED_CLASSES])
    np.testing.assert_allclose(ours_p, precision, atol=1e-12, equal_nan=True)
    np.testing.assert_allclose(ours_r, recall, atol=1e-12, equal_nan=True)
    np.testing.assert_allclose(ours_f, f1, atol=1e-12, equal_nan=True)


@pytest.mark.rule("R16")
@given(pairs)
def test_f1_per_class_equals_sklearn_f1_score(pairs: list[tuple[str, str]]) -> None:
    y_true, y_pred = _arrays(pairs)
    expected = f1_score(
        y_true, y_pred, labels=LABELS, average=None, zero_division=np.nan
    )
    metrics = class_metrics(confusion_matrix(y_true, y_pred))
    ours = np.array([metrics[c].f1 for c in SCORED_CLASSES])
    np.testing.assert_allclose(ours, expected, atol=1e-12, equal_nan=True)


@pytest.mark.rule("R16")
@given(pairs)
def test_four_class_macro_f1_equals_sklearn_when_every_class_is_defined(
    pairs: list[tuple[str, str]],
) -> None:
    y_true, y_pred = _arrays(pairs)
    cm = confusion_matrix(y_true, y_pred)
    ours = macro_f1(cm, SCORED_CLASSES)
    present = set(y_true.tolist()) | set(y_pred.tolist())
    if present != set(SCORED_CLASSES):
        assert math.isnan(ours)
        return
    expected = f1_score(y_true, y_pred, labels=LABELS, average="macro")
    assert ours == pytest.approx(expected, abs=1e-12)


@pytest.mark.rule("R16")
def test_macro_f1_over_headline_classes_on_the_hand_case() -> None:
    y_true, y_pred = _from_matrix(HAND)
    expected = f1_score(y_true, y_pred, labels=list(HEADLINE_CLASSES), average="macro")
    assert macro_f1(HAND, HEADLINE_CLASSES) == pytest.approx(expected, abs=1e-12)
    assert selection_score(HAND) == macro_f1(HAND, HEADLINE_CLASSES)


@pytest.mark.rule("R16")
def test_fpr_on_a_hand_case() -> None:
    metrics = class_metrics(HAND)
    # V: FP = 2 + 1 + 3 = 6; negatives are every beat not V: 105 - 25 = 80.
    assert metrics["V"].fpr == pytest.approx(6 / 80)
    # N: FP = 4 + 2 + 1 = 7; negatives 105 - 56 = 49.
    assert metrics["N"].fpr == pytest.approx(7 / 49)


@pytest.mark.rule("R16")
def test_ec57_excludes_fv_from_v_false_positives_and_true_negatives() -> None:
    ec57 = ec57_metrics(HAND)
    # V: TP = Vv 20; FN = Vn + Vs + Vf = 5; FP = Nv + Sv = 3 (Fv = 3 left out);
    # TN = Nn + Ns + Nf + Sn + Ss + Sf + Fn + Fs + Ff = 50+3+1+4+10+0+1+0+5 = 74.
    assert ec57["V"].se == pytest.approx(20 / 25)
    assert ec57["V"].ppv == pytest.approx(20 / 23)
    assert ec57["V"].fpr == pytest.approx(3 / 77)
    # The one-vs-rest V counts Fv as a false positive.
    assert class_metrics(HAND)["V"].precision == pytest.approx(20 / 26)


@pytest.mark.rule("R16")
def test_ec57_s_is_one_vs_rest() -> None:
    ec57 = ec57_metrics(HAND)
    # S: TP Ss 10; FN Sn + Sv + Sf = 5; FP Ns + Vs + Fs = 4;
    # TN Nn+Nv+Nf+Vn+Vv+Vf+Fn+Fv+Ff = 50+2+1+2+20+2+1+3+5 = 86.
    assert ec57["S"].se == pytest.approx(10 / 15)
    assert ec57["S"].ppv == pytest.approx(10 / 14)
    assert ec57["S"].fpr == pytest.approx(4 / 90)
    assert set(ec57) == {"S", "V"}


@pytest.mark.rule("R16")
def test_no_predicted_s_gives_precision_nan_and_f1_zero() -> None:
    cm = HAND.copy()
    cm[:, 0] += cm[:, 1]
    cm[:, 1] = 0
    metrics = class_metrics(cm)
    assert math.isnan(metrics["S"].precision)
    assert metrics["S"].recall == 0.0
    assert metrics["S"].f1 == 0.0
    assert math.isnan(ec57_metrics(cm)["S"].ppv)
    assert not math.isnan(selection_score(cm))


@pytest.mark.rule("R16")
def test_class_absent_from_labels_and_predictions_gives_f1_nan() -> None:
    cm = HAND.copy()
    cm[3, :] = 0
    cm[:, 3] = 0
    metrics = class_metrics(cm)
    assert math.isnan(metrics["F"].f1)
    assert math.isnan(metrics["F"].recall)
    assert math.isnan(metrics["F"].precision)
    assert math.isnan(macro_f1(cm, SCORED_CLASSES))
    assert not math.isnan(macro_f1(cm, HEADLINE_CLASSES))


@pytest.mark.rule("R16")
def test_batched_equals_looped() -> None:
    rng = np.random.default_rng(7)
    cms = rng.integers(0, 6, size=(3, 5, 4, 4)).astype(np.int64)
    cms[0, 0, :, 1] = 0  # no predicted S
    cms[1, 2, 3, :] = 0
    cms[1, 2, :, 3] = 0  # F absent
    rates = class_rates(cms)
    values = metric_values(cms)
    for index in np.ndindex(3, 5):
        one = cms[index]
        metrics = class_metrics(one)
        for k, cls in enumerate(SCORED_CLASSES):
            for name in ("recall", "precision", "f1", "fpr"):
                np.testing.assert_equal(
                    rates[name][(*index, k)], getattr(metrics[cls], name)
                )
        looped = metric_values(one)
        for name, batched in values.items():
            assert batched.shape == (3, 5)
            np.testing.assert_equal(batched[index], looped[name])


@pytest.mark.rule("R16")
def test_metric_values_names() -> None:
    values = metric_values(HAND)
    assert values["macro_f1_nsv"] == pytest.approx(selection_score(HAND))
    assert values["macro_f1_all"] == pytest.approx(macro_f1(HAND, SCORED_CLASSES))
    assert values["S_fpr"] == pytest.approx(class_metrics(HAND)["S"].fpr)
    assert values["ec57_V_ppv"] == pytest.approx(ec57_metrics(HAND)["V"].ppv)


@pytest.mark.rule("R16")
def test_summarize_writes_nan_as_none() -> None:
    cm = HAND.copy()
    cm[:, 1] = 0
    summary = summarize(cm)
    assert summary["per_class"]["S"]["precision"] is None
    assert summary["per_class"]["S"]["f1"] == 0.0
    assert summary["ec57"]["S"]["ppv"] is None
    assert summary["confusion"] == cm.tolist()
    assert summary["classes"] == list(SCORED_CLASSES)
    assert summary["n_beats"] == int(cm.sum())
    assert summary["macro_f1_nsv"] == pytest.approx(selection_score(cm))
    assert isinstance(summary["macro_f1_all"], float)
