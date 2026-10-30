"""Scoring the committed models (Phase 5 settlings 1 and 2; EVAL-05).

The sealed run scores only committed files: the three CNN seeds through
Python ONNX Runtime on CPU, and the baseline's `baseline.json` through NumPy.
Both take the same inputs as training (the RR model inputs from
`heartbeat.models.inputs`, the z-scored windows from `heartbeat.signal`), so
the scoring path is the pipeline's own.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import RR_FEATURE_NAMES, SCORED_CLASSES
from heartbeat.models.inputs import RRScaler, apply_rr_scaler, rr_model_inputs


@dataclass(frozen=True)
class BaselineParams:
    """The frozen baseline as `baseline.json` stores it.

    Attributes:
        coefficients: `(4, 6)`, rows in `SCORED_CLASSES` order.
        intercepts: `(4,)`.
        scaler_mean: RR scaler mean, `(6,)`.
        scaler_std: RR scaler standard deviation, `(6,)`.
        log_class_weights: Log of the training class weights, `(4,)`.
        temperature: Its DS1 out-of-fold temperature.
    """

    coefficients: NDArray[np.float64]
    intercepts: NDArray[np.float64]
    scaler_mean: NDArray[np.float64]
    scaler_std: NDArray[np.float64]
    log_class_weights: NDArray[np.float64]
    temperature: float

    def __post_init__(self) -> None:
        """Check the shapes against the class and feature counts."""
        n_classes, n_features = len(SCORED_CLASSES), len(RR_FEATURE_NAMES)
        assert self.coefficients.shape == (n_classes, n_features)
        assert self.intercepts.shape == (n_classes,)
        assert self.scaler_mean.shape == (n_features,)
        assert self.scaler_std.shape == (n_features,)
        assert self.log_class_weights.shape == (n_classes,)


def baseline_logits(
    params: BaselineParams, rr_s: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Raw logits `(n, 4)` in `SCORED_CLASSES` order from RR features `(n, 6)`.

    The same arithmetic as scikit-learn's `decision_function`: the scaled RR
    inputs times the coefficients, plus the intercepts.
    """
    scaler = RRScaler(mean=params.scaler_mean, std=params.scaler_std)
    x = apply_rr_scaler(scaler, rr_model_inputs(rr_s))
    logits: NDArray[np.float64] = x @ params.coefficients.T + params.intercepts
    return logits
