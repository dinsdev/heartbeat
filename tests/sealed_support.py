"""Synthetic beats and model scores for the sealed report tests. No record is read."""

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import SCORED_CLASSES
from heartbeat.sealed.report import ModelScores

PATIENTS = ("200", "210", "232", "233")
CLASS_ROWS = {"N": 0, "S": 1, "V": 2, "F": 3}


def logits_for(labels: list[str], rng: np.random.Generator) -> NDArray[np.float64]:
    logits = rng.normal(0.0, 0.3, (len(labels), 4))
    for k, label in enumerate(labels):
        logits[k, CLASS_ROWS[label]] += 3.0
    return logits


def synthetic_scores(
    no_predicted_s_outside_232: bool = False,
) -> tuple[NDArray[np.str_], NDArray[np.str_], dict[str, ModelScores]]:
    rng = np.random.default_rng(7)
    true: list[str] = []
    record: list[str] = []
    for patient in PATIENTS:
        n_s = 30 if patient == "232" else 3
        classes = ["N"] * 60 + ["S"] * n_s + ["V"] * 12 + ["F"] * 2 + ["Q"] * 2
        true.extend(classes)
        record.extend([patient] * len(classes))
    y = np.array(true)
    rec = np.array(record)
    scores = {}
    for k, name in enumerate(("cnn-seed-0", "cnn-seed-1", "cnn-seed-2", "baseline")):
        predicted = [c if c != "Q" else "N" for c in true]
        # Some mistakes, differing by model.
        for i in rng.choice(len(predicted), size=20 + 5 * k, replace=False):
            predicted[i] = SCORED_CLASSES[int(rng.integers(4))]
        if no_predicted_s_outside_232 and name == "baseline":
            predicted = [
                "N" if (p == "S" and r != "232") else p
                for p, r in zip(predicted, record, strict=True)
            ]
        scores[name] = ModelScores(
            logits=logits_for(predicted, rng),
            log_class_weights=np.log([0.3, 13.0, 3.4, 30.0]),
            temperature=1.5,
        )
    return y, rec, scores
