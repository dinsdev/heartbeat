"""What a model supplies to the CV driver (R21).

A model gives only its inputs, `fit` and `logits`. Folds, class weights, the
RR scaler, the selection metric and calibration belong to the driver in
`heartbeat.train.cv`, so every model gets the same ones.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.data.loader import BeatTable

# beats, row indices, the scaled RR inputs of those rows -> the model's input.
InputsFn = Callable[[BeatTable, NDArray[np.int64], NDArray[np.float64]], Any]
# input, labels, class weights, params -> fitted model.
FitFn = Callable[[Any, NDArray[np.str_], Mapping[str, float], Mapping[str, Any]], Any]
# fitted model, input -> raw logits (n, 4) in SCORED_CLASSES order.
LogitsFn = Callable[[Any, Any], NDArray[np.float64]]


@dataclass(frozen=True)
class ModelSpec:
    """A model as the CV driver sees it."""

    name: str
    inputs: InputsFn
    fit: FitFn
    logits: LogitsFn
