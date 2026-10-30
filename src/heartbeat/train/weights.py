"""Balanced class weights, one function for every model (C2, C3; R21)."""

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import SCORED_CLASSES


def balanced_class_weights(y_train: NDArray[np.str_]) -> dict[str, float]:
    """Return `n_beats / (4 * count_c)` per class over the training beats.

    The same math as scikit-learn's `class_weight="balanced"` (Phase 3 task
    plan, design call 3), as an explicit dict in `SCORED_CLASSES` order.

    Raises:
        ValueError: On a label outside the scored classes, or a class with no
            training beats.
    """
    unknown = sorted(set(y_train.tolist()) - set(SCORED_CLASSES))
    if unknown:
        raise ValueError(f"labels {unknown} are not scored classes")
    n = y_train.size
    weights: dict[str, float] = {}
    for cls in SCORED_CLASSES:
        count = int((y_train == cls).sum())
        if count == 0:
            raise ValueError(f"class {cls} has no training beats")
        weights[cls] = n / (len(SCORED_CLASSES) * count)
    return weights
