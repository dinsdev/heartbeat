"""The DS2 demo labels against the sealed report, exactly (Phase 7 settling 4).

`build-demo-data` scores DS2 with the frozen seed-0 model through the DS1
build's scoring path, then requires the pooled seed-0 confusion matrix and
every per-patient S and V cell to equal the last sealed report (design call
4). It runs before any file is written; any difference stops the build and
goes to Din. Q beats are left out, as the report leaves them out (DATA-10).
"""

from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import SCORED_CLASSES
from heartbeat.evaluate.bootstrap import patient_confusions
from heartbeat.evaluate.metrics import confusion_matrix
from heartbeat.evaluate.per_patient import per_patient_table
from heartbeat.sealed.report import CNN


class SealedMismatchError(RuntimeError):
    """The demo's seed-0 counts differ from the sealed report (settling 4)."""


def _pooled(
    y: NDArray[np.str_], labels: NDArray[np.str_], report: Mapping[str, Any]
) -> None:
    demo = confusion_matrix(y, labels).tolist()
    sealed = report["confusion"]["matrices"][CNN]
    for i, true in enumerate(SCORED_CLASSES):
        for j, label in enumerate(SCORED_CLASSES):
            if demo[i][j] != sealed[i][j]:
                raise SealedMismatchError(
                    f"pooled seed-0 confusion, true {true} labeled {label}: demo "
                    f"{demo[i][j]}, sealed report {sealed[i][j]}"
                )


def _per_patient(
    y: NDArray[np.str_],
    labels: NDArray[np.str_],
    subject: NDArray[np.str_],
    report: Mapping[str, Any],
) -> None:
    patients = list(report["patients"])
    if sorted(set(subject.tolist())) != sorted(patients):
        raise SealedMismatchError(
            f"patients {sorted(set(subject.tolist()))} differ from the sealed "
            f"report's {sorted(patients)}"
        )
    rows = per_patient_table(patient_confusions(y, labels, subject, patients), patients)
    for demo, sealed in zip(
        (row.as_dict() for row in rows), report["per_patient"][CNN], strict=True
    ):
        for cls in ("S", "V"):
            for kind in ("recall", "precision"):
                a, b = demo[cls][kind], sealed[cls][kind]
                if (a["numerator"], a["denominator"]) != (
                    b["numerator"],
                    b["denominator"],
                ) or demo["patient"] != sealed["patient"]:
                    raise SealedMismatchError(
                        f"patient {sealed['patient']} {cls} {kind}: demo "
                        f"{a['numerator']}/{a['denominator']}, sealed report "
                        f"{b['numerator']}/{b['denominator']}"
                    )


def check_against_sealed(
    labels_by_record: Mapping[str, NDArray[np.str_]],
    beat_class_by_record: Mapping[str, NDArray[np.str_]],
    report: Mapping[str, Any],
    subjects: Mapping[str, str],
) -> None:
    """Require the demo's seed-0 counts to equal the sealed report's.

    Args:
        labels_by_record: Each record's seed-0 label per kept beat, Q included.
        beat_class_by_record: Each record's expert class per kept beat.
        report: The report the log's last sealed entry names.
        subjects: Record to patient, as the sealed run grouped them.

    Raises:
        SealedMismatchError: Naming the first difference: the record list, then
            the pooled matrix, then each patient's S and V cells.
    """
    records = sorted(labels_by_record)
    if records != sorted(beat_class_by_record) or records != sorted(report["records"]):
        raise SealedMismatchError(
            f"records {records} differ from the sealed report's "
            f"{sorted(report['records'])}"
        )
    for record in records:
        if labels_by_record[record].shape != beat_class_by_record[record].shape:
            raise SealedMismatchError(
                f"record {record}: {labels_by_record[record].size} labels for "
                f"{beat_class_by_record[record].size} kept beats"
            )
    y = np.concatenate([beat_class_by_record[r] for r in records])
    labels = np.concatenate([labels_by_record[r] for r in records])
    subject = np.concatenate(
        [np.full(beat_class_by_record[r].size, subjects[r]) for r in records]
    )
    scored = y != "Q"
    _pooled(y[scored], labels[scored], report)
    _per_patient(y[scored], labels[scored], subject[scored], report)
