"""EVAL-08 to EVAL-12: the pre-registered report, on synthetic beats."""

import json
from typing import Any

import numpy as np
import pytest
from sealed_support import PATIENTS, synthetic_scores

from heartbeat.sealed.report import ModelScores, sealed_report


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    y, rec, scores = synthetic_scores()
    return sealed_report(y, rec, rec, scores, data_label="synthetic", n_draws=400)


def test_every_eval_08_item_is_present(report: dict[str, Any]) -> None:
    json.dumps(report, allow_nan=False)
    for key in (
        "headline",
        "comparison",
        "fpr",
        "s_without_excluded",
        "per_patient",
        "confusion",
        "n_and_f",
        "seed_range",
        "calibration",
    ):
        assert key in report, key
    assert report["data"] == "synthetic"
    assert report["patients"] == list(PATIENTS)
    headline = report["headline"]
    assert headline["models"] == {"cnn": "cnn-seed-0", "baseline": "baseline"}
    for model in ("cnn", "baseline"):
        for metric in (
            "S_recall",
            "S_precision",
            "V_recall",
            "V_precision",
            "macro_f1_nsv",
            "macro_f1_all",
        ):
            interval = headline["intervals"][model][metric]
            assert interval["low"] <= interval["high"]
            assert interval["draws"] == 400
            assert "skipped" in interval
    assert report["bootstrap"]["unit"] == "patient"


def test_the_comparison_sentence_follows_the_rule(report: dict[str, Any]) -> None:
    comparison = report["comparison"]
    for metric, row in comparison["metrics"].items():
        low, high = row["low"], row["high"]
        if low is not None and low > 0:
            assert row["verdict"] == "CNN better than baseline", metric
        elif high is not None and high < 0:
            assert row["verdict"] == "baseline better than CNN", metric
        else:
            assert row["verdict"] == "no clear difference", metric
    assert "EVAL-10" in comparison["wording"]


def test_q_beats_are_not_scored_and_are_counted(report: dict[str, Any]) -> None:
    assert report["beats"]["q_not_scored"] == 2 * len(PATIENTS)
    scored = report["beats"]["scored"]
    for model in ("cnn-seed-0", "baseline"):
        cm = np.array(report["confusion"]["matrices"][model])
        assert cm.shape == (4, 4)
        assert int(cm.sum()) == scored
    assert "Q" in report["confusion"]["note"]
    assert report["fpr"]["ec57"]["q_not_scored"] == 2 * len(PATIENTS)


def test_per_class_counts_sum_to_the_beat_count(report: dict[str, Any]) -> None:
    for model, pooled in report["models"].items():
        assert (
            sum(sum(row) for row in pooled["pooled"]["confusion"])
            == report["beats"]["scored"]
        ), model


def test_s_without_232_uses_the_other_patients(report: dict[str, Any]) -> None:
    block = report["s_without_excluded"]
    assert block["record"] == "232"
    assert block["present"] is True
    assert block["patients"] == ["200", "210", "233"]
    for model in ("cnn", "baseline"):
        assert sorted(block["intervals"][model]) == ["S_precision", "S_recall"]


def test_per_patient_cells_and_confusion_matrices(report: dict[str, Any]) -> None:
    rows = report["per_patient"]["cnn-seed-0"]
    assert [r["patient"] for r in rows] == list(PATIENTS)
    small = next(r for r in rows if r["patient"] == "200")
    # 3 true S beats: counts only, no percentage (R19).
    assert small["S"]["recall"]["denominator"] == 3
    assert small["S"]["recall"]["percent"] is None
    assert sorted(report["per_patient"]) == ["baseline", "cnn-seed-0"]


def test_seed_range_and_calibration(report: dict[str, Any]) -> None:
    ranges = report["seed_range"]
    assert ranges["seeds"] == ["cnn-seed-1", "cnn-seed-2"]
    for metric, span in ranges["range"].items():
        assert span is None or span["min"] <= span["max"], metric
    for model in ("cnn-seed-0", "cnn-seed-1", "cnn-seed-2", "baseline"):
        block = report["calibration"][model]
        assert block["temperature"] == 1.5
        assert block["bins"] == 10
        assert sorted(block["ece"]) == ["S", "V"]
        assert sorted(block["reliability"]) == ["S", "V"]
        assert block["log_loss"] > 0
        assert 0 <= block["brier"] <= 2
    n_f = report["n_and_f"]["cnn"]
    assert sorted(n_f) == ["F_precision", "F_recall", "N_precision", "N_recall"]


def test_a_draw_with_no_predicted_s_is_skipped_and_counted() -> None:
    y, rec, scores = synthetic_scores(no_predicted_s_outside_232=True)
    report = sealed_report(y, rec, rec, scores, data_label="synthetic", n_draws=400)
    precision = report["headline"]["intervals"]["baseline"]["S_precision"]
    # Draws without patient 232 have no predicted S for the baseline.
    assert precision["skipped"] > 0
    assert precision["draws"] == 400
    without = report["s_without_excluded"]["intervals"]["baseline"]["S_precision"]
    # Without 232 nothing is predicted S at all: the point is undefined.
    assert without["point"] is None
    assert without["low"] is None
    assert without["skipped"] == 400


def test_a_set_without_the_excluded_record_says_so() -> None:
    y, rec, scores = synthetic_scores()
    keep = rec != "232"
    trimmed = {
        name: ModelScores(s.logits[keep], s.log_class_weights, s.temperature)
        for name, s in scores.items()
    }
    report = sealed_report(
        y[keep], rec[keep], rec[keep], trimmed, data_label="synthetic", n_draws=50
    )
    block = report["s_without_excluded"]
    assert block["present"] is False
    assert block["patients"] == ["200", "210", "233"]
