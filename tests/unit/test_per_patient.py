"""C4, EVAL-08 item 4: the per-patient S and V table and its count rule (R19).

Each cell is gated on its own denominator (Phase 3 settling 3). Synthetic
patients only.
"""

import numpy as np
import pytest
from numpy.typing import NDArray

from heartbeat.evaluate.per_patient import Cell, per_patient_table

N, S, V, F = range(4)


def _patient(cells: dict[tuple[int, int], int]) -> NDArray[np.int64]:
    cm = np.zeros((4, 4), dtype=np.int64)
    for (i, j), n in cells.items():
        cm[i, j] = n
    return cm


def _table(*patients: NDArray[np.int64]) -> list[Cell]:
    rows = per_patient_table(
        np.stack(patients), [f"p{k}" for k in range(len(patients))]
    )
    return [cell for row in rows for cell in (row.s_recall, row.s_precision)]


@pytest.mark.rule("R19")
def test_nine_true_s_beats_show_counts_and_no_percent() -> None:
    rows = per_patient_table(np.stack([_patient({(S, S): 6, (S, N): 3})]), ["p"])
    cell = rows[0].s_recall
    assert (cell.numerator, cell.denominator) == (6, 9)
    assert cell.percent is None
    assert cell.note is None


@pytest.mark.rule("R19")
def test_ten_true_s_beats_show_a_percent() -> None:
    rows = per_patient_table(np.stack([_patient({(S, S): 7, (S, N): 3})]), ["p"])
    cell = rows[0].s_recall
    assert (cell.numerator, cell.denominator) == (7, 10)
    assert cell.percent == pytest.approx(70.0)


@pytest.mark.rule("R19")
def test_precision_on_two_flagged_beats_shows_no_percent() -> None:
    # Settling 3: 50 true S beats, 2 flagged, 1 of them right.
    cm = _patient({(S, S): 1, (S, N): 49, (N, S): 1, (N, N): 100})
    row = per_patient_table(np.stack([cm]), ["p"])[0]
    assert (row.s_precision.numerator, row.s_precision.denominator) == (1, 2)
    assert row.s_precision.percent is None
    assert row.s_recall.percent == pytest.approx(2.0)


@pytest.mark.rule("R19")
def test_twelve_flagged_beats_show_a_percent() -> None:
    cm = _patient({(S, S): 9, (N, S): 3, (S, N): 41})
    row = per_patient_table(np.stack([cm]), ["p"])[0]
    assert (row.s_precision.numerator, row.s_precision.denominator) == (9, 12)
    assert row.s_precision.percent == pytest.approx(75.0)


@pytest.mark.rule("R19")
def test_zero_flagged_beats_says_none_flagged() -> None:
    cm = _patient({(S, N): 12, (N, N): 50, (V, V): 11, (N, V): 2})
    row = per_patient_table(np.stack([cm]), ["p"])[0]
    assert row.s_precision == Cell(0, 0, None, "none flagged")
    assert row.s_recall == Cell(0, 12, 0.0, None)
    assert (row.v_precision.numerator, row.v_precision.denominator) == (11, 13)
    assert row.v_precision.percent == pytest.approx(100 * 11 / 13)


@pytest.mark.rule("R19")
def test_zero_true_beats_says_none_present() -> None:
    cm = _patient({(N, N): 50, (N, V): 2})
    row = per_patient_table(np.stack([cm]), ["p"])[0]
    assert row.v_recall == Cell(0, 0, None, "none present")
    assert row.v_precision == Cell(0, 2, None, None)
    assert row.s_recall.note == "none present"
    assert row.s_precision.note == "none flagged"


@pytest.mark.rule("R19")
def test_counts_are_always_present() -> None:
    rng = np.random.default_rng(5)
    patients = rng.integers(0, 15, size=(8, 4, 4)).astype(np.int64)
    rows = per_patient_table(patients, [f"p{k}" for k in range(8)])
    assert [r.patient for r in rows] == [f"p{k}" for k in range(8)]
    for row, cm in zip(rows, patients, strict=True):
        for cls, k in (("s", S), ("v", V)):
            recall = getattr(row, f"{cls}_recall")
            precision = getattr(row, f"{cls}_precision")
            assert recall.numerator == cm[k, k]
            assert recall.denominator == cm[k].sum()
            assert precision.numerator == cm[k, k]
            assert precision.denominator == cm[:, k].sum()
            for cell in (recall, precision):
                assert (cell.percent is None) == (cell.denominator < 10)


def test_cell_as_dict() -> None:
    assert Cell(7, 10, 70.0, None).as_dict() == {
        "numerator": 7,
        "denominator": 10,
        "percent": 70.0,
        "note": None,
    }


def test_patient_count_must_match() -> None:
    with pytest.raises(ValueError, match="patients"):
        per_patient_table(np.zeros((2, 4, 4), dtype=np.int64), ["p"])
    assert _table(_patient({(N, N): 1}))[0].note == "none present"
