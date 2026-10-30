"""What a model supplies to the CV driver (R21).

A model gives only its inputs, a way to fit, and `logits`. Folds, class
weights, the RR scaler, the selection metric and calibration belong to the
driver in `heartbeat.train.cv`, so every model gets the same ones. A model
fitted in one call supplies `fit`; a model that trains in epochs supplies
`fit_epochs`, which yields the fitted model after each epoch so the driver
scores every epoch itself (Phase 4 task plan).
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.data.loader import BeatTable

# beats, row indices, the scaled RR inputs of those rows -> the model's input.
InputsFn = Callable[[BeatTable, NDArray[np.int64], NDArray[np.float64]], Any]
# input, labels, class weights, params -> fitted model.
FitFn = Callable[[Any, NDArray[np.str_], Mapping[str, float], Mapping[str, Any]], Any]
# input, labels, class weights, params, fold, epochs -> the model after each epoch.
# The fold names the fit's random streams (MODEL-05), never its rows.
FitEpochsFn = Callable[
    [Any, NDArray[np.str_], Mapping[str, float], Mapping[str, Any], int, int],
    Iterator[Any],
]
# fitted model, input -> raw logits (n, 4) in SCORED_CLASSES order.
LogitsFn = Callable[[Any, Any], NDArray[np.float64]]


@dataclass(frozen=True)
class ModelSpec:
    """A model as the CV driver sees it.

    Attributes:
        name: The model's name in run folders and results.
        inputs: Builds the model's input from beats and scaled RR inputs.
        fit: One-call fit; `epochs_only` for a model that trains in epochs.
        logits: Raw logits of a fitted model.
        fit_epochs: Epoch-by-epoch fit, or None.
        config: Fixed settings the model's numbers depend on, for the
            resolved config (R24).
    """

    name: str
    inputs: InputsFn
    fit: FitFn
    logits: LogitsFn
    fit_epochs: FitEpochsFn | None = None
    config: Mapping[str, Any] = field(default_factory=dict)


def epochs_only(
    x: Any, y: NDArray[np.str_], w: Mapping[str, float], params: Mapping[str, Any]
) -> Any:
    """The `fit` of a model that trains only in epochs.

    Raises:
        TypeError: Always; use `fit_epochs` through `cross_validate_epochs`.
    """
    raise TypeError("this model trains in epochs; use cross_validate_epochs")
