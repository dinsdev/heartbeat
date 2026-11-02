"""Phase 7 settling 4, design call 4: the DS2 demo labels equal the sealed report.

The report comes from `sealed_report` on synthetic beats and scores; the demo
side is the seed-0 labels of the same beats, split by record. No record is read.
"""

import copy
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray
from sealed_support import synthetic_scores

from heartbeat.demo.sealed_check import SealedMismatchError, check_against_sealed
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.sealed.report import CNN, sealed_report

Split = tuple[dict[str, NDArray[np.str_]], dict[str, NDArray[np.str_]]]


@pytest.fixture(scope="module")
def sealed() -> tuple[dict[str, Any], Split, dict[str, str]]:
    y, record, scores = synthetic_scores()
    report = sealed_report(
        y, record, record, scores, data_label="synthetic", n_draws=20
    )
    report = {**report, "records": sorted(set(record.tolist()))}
    labels = predict_labels(scores[CNN].logits)
    by_record = sorted(set(record.tolist()))
    labels_by_record = {r: labels[record == r] for r in by_record}
    classes_by_record = {r: y[record == r] for r in by_record}
    subjects = {r: r for r in by_record}
    return report, (labels_by_record, classes_by_record), subjects


def test_equal_counts_pass(
    sealed: tuple[dict[str, Any], Split, dict[str, str]],
) -> None:
    report, (labels, classes), subjects = sealed
    check_against_sealed(labels, classes, report, subjects)


def test_a_pooled_cell_off_by_one_raises_naming_it(
    sealed: tuple[dict[str, Any], Split, dict[str, str]],
) -> None:
    report, (labels, classes), subjects = sealed
    planted = copy.deepcopy(report)
    planted["confusion"]["matrices"][CNN][2][0] += 1
    with pytest.raises(SealedMismatchError, match=r"pooled.*true V labeled N"):
        check_against_sealed(labels, classes, planted, subjects)


@pytest.mark.parametrize(
    ("cls", "kind", "field"),
    [
        ("S", "recall", "numerator"),
        ("S", "precision", "denominator"),
        ("V", "recall", "denominator"),
        ("V", "precision", "numerator"),
    ],
)
def test_one_per_patient_cell_off_by_one_raises_naming_it(
    sealed: tuple[dict[str, Any], Split, dict[str, str]],
    cls: str,
    kind: str,
    field: str,
) -> None:
    report, (labels, classes), subjects = sealed
    planted = copy.deepcopy(report)
    row = planted["per_patient"][CNN][2]
    row[cls][kind][field] += 1
    with pytest.raises(
        SealedMismatchError, match=f"patient {row['patient']} {cls} {kind}"
    ):
        check_against_sealed(labels, classes, planted, subjects)


def test_one_changed_label_raises(
    sealed: tuple[dict[str, Any], Split, dict[str, str]],
) -> None:
    report, (labels, classes), subjects = sealed
    changed = {r: v.copy() for r, v in labels.items()}
    first = sorted(changed)[0]
    scored = np.flatnonzero(classes[first] != "Q")[0]
    changed[first][scored] = "F" if changed[first][scored] != "F" else "N"
    with pytest.raises(SealedMismatchError, match="pooled"):
        check_against_sealed(changed, classes, report, subjects)


def test_q_beats_are_not_scored(
    sealed: tuple[dict[str, Any], Split, dict[str, str]],
) -> None:
    """A Q beat's label counts nowhere, as in the sealed report (DATA-10)."""
    report, (labels, classes), subjects = sealed
    changed = {r: v.copy() for r, v in labels.items()}
    for record, cls in classes.items():
        changed[record][cls == "Q"] = "S"
    check_against_sealed(changed, classes, report, subjects)


def test_a_missing_or_extra_record_raises(
    sealed: tuple[dict[str, Any], Split, dict[str, str]],
) -> None:
    report, (labels, classes), subjects = sealed
    first = sorted(labels)[0]
    fewer = {r: v for r, v in labels.items() if r != first}
    fewer_classes = {r: v for r, v in classes.items() if r != first}
    with pytest.raises(SealedMismatchError, match="records"):
        check_against_sealed(fewer, fewer_classes, report, subjects)


def test_labels_and_classes_of_different_lengths_raise(
    sealed: tuple[dict[str, Any], Split, dict[str, str]],
) -> None:
    report, (labels, classes), subjects = sealed
    first = sorted(labels)[0]
    short = {**labels, first: labels[first][:-1]}
    with pytest.raises(SealedMismatchError, match=first):
        check_against_sealed(short, classes, report, subjects)
