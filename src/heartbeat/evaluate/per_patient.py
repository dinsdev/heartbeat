"""The per-patient S and V table (C4; EVAL-08 item 4, R19).

Every cell shows its counts. A cell shows a percentage only when its own
denominator is at least `PER_PATIENT_MIN_BEATS`: true beats for recall,
flagged beats for precision (Phase 3 settling 3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import PER_PATIENT_MIN_BEATS
from heartbeat.evaluate.metrics import CLASS_INDEX


@dataclass(frozen=True)
class Cell:
    """One table cell.

    Attributes:
        numerator: Correct beats of the class.
        denominator: True beats (recall) or flagged beats (precision).
        percent: 100 * numerator / denominator, only at 10 or more beats.
        note: "none present" (no true beats) or "none flagged" (none predicted).
    """

    numerator: int
    denominator: int
    percent: float | None
    note: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict."""
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "percent": self.percent,
            "note": self.note,
        }


@dataclass(frozen=True)
class PatientRow:
    """One patient's S and V cells."""

    patient: str
    s_recall: Cell
    s_precision: Cell
    v_recall: Cell
    v_precision: Cell

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict."""
        return {
            "patient": self.patient,
            "S": {
                "recall": self.s_recall.as_dict(),
                "precision": self.s_precision.as_dict(),
            },
            "V": {
                "recall": self.v_recall.as_dict(),
                "precision": self.v_precision.as_dict(),
            },
        }


def _cell(numerator: int, denominator: int, empty_note: str) -> Cell:
    if denominator == 0:
        return Cell(numerator, denominator, None, empty_note)
    percent = (
        100.0 * numerator / denominator
        if denominator >= PER_PATIENT_MIN_BEATS
        else None
    )
    return Cell(numerator, denominator, percent, None)


def per_patient_table(
    confusions: NDArray[np.int64], patients: Sequence[str]
) -> list[PatientRow]:
    """Build the S and V cells for each patient.

    Args:
        confusions: Per-patient matrices, `(n_patients, 4, 4)`.
        patients: Patient IDs in the same order.

    Raises:
        ValueError: If the counts of matrices and patients differ.
    """
    if confusions.shape[0] != len(patients):
        raise ValueError(f"{confusions.shape[0]} matrices for {len(patients)} patients")
    rows: list[PatientRow] = []
    for patient, cm in zip(patients, confusions, strict=True):
        cells: dict[str, Cell] = {}
        for cls in ("S", "V"):
            k = CLASS_INDEX[cls]
            tp = int(cm[k, k])
            cells[f"{cls}_recall"] = _cell(tp, int(cm[k].sum()), "none present")
            cells[f"{cls}_precision"] = _cell(tp, int(cm[:, k].sum()), "none flagged")
        rows.append(
            PatientRow(
                patient=patient,
                s_recall=cells["S_recall"],
                s_precision=cells["S_precision"],
                v_recall=cells["V_recall"],
                v_precision=cells["V_precision"],
            )
        )
    return rows
