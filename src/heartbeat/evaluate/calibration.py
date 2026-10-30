"""Labels, logit adjustment, temperature and calibration metrics (C4; EVAL-11, 12, R20).

Labels are the argmax of the raw logits of the class-weighted model, and
`predict_labels` takes nothing else, so calibration can never change a label.
Probabilities come from logits adjusted by subtracting the log of the class
weights the model was trained with (each fold's own), then divided by one
fitted temperature. The calibrated argmax may differ from the label; that is
allowed, and the label is what every classification metric scores.
"""

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax, softmax

from heartbeat.constants import ECE_BINS, SCORED_CLASSES, TEMPERATURE_BOUNDS
from heartbeat.evaluate.metrics import N_CLASSES, class_indices

# Phase 3 task plan, stop condition 5: an optimum this close to a bound stops.
_BOUND_MARGIN = 0.01


class TemperatureAtBoundError(RuntimeError):
    """The fitted temperature is within 1% of a search bound."""


def predict_labels(logits: NDArray[np.float64]) -> NDArray[np.str_]:
    """Argmax of the raw logits, `(n, 4)` in, class strings `(n,)` out (C4)."""
    assert logits.shape[1:] == (N_CLASSES,), logits.shape
    labels: NDArray[np.str_] = np.array(SCORED_CLASSES)[np.argmax(logits, axis=1)]
    return labels


def adjust_logits(
    logits: NDArray[np.float64],
    class_weights: Mapping[str, float] | NDArray[np.float64],
) -> NDArray[np.float64]:
    """Subtract the log of the training class weights from the logits.

    Args:
        logits: Raw logits, `(n, 4)`.
        class_weights: One weight per class, or each row's own weights `(n, 4)`
            in `SCORED_CLASSES` order (each fold's training weights).

    Returns:
        A new array; the input is not changed.

    Raises:
        ValueError: If a per-row weight array has the wrong shape.
    """
    if isinstance(class_weights, Mapping):
        w = np.array([class_weights[c] for c in SCORED_CLASSES], dtype=np.float64)
    else:
        w = np.asarray(class_weights, dtype=np.float64)
        if w.shape != logits.shape:
            raise ValueError(
                f"per-row weights have shape {w.shape}, logits {logits.shape}"
            )
    adjusted: NDArray[np.float64] = logits - np.log(w)
    return adjusted


def calibrated_probs(
    adjusted: NDArray[np.float64], temperature: float
) -> NDArray[np.float64]:
    """Softmax of the adjusted logits divided by the temperature, `(n, 4)`."""
    probs: NDArray[np.float64] = softmax(adjusted / temperature, axis=1)
    return probs


def log_loss_from_logits(
    adjusted: NDArray[np.float64], temperature: float, y_true: NDArray[np.str_]
) -> float:
    """Mean negative log probability of the true class, in nats per beat."""
    log_probs = log_softmax(adjusted / temperature, axis=1)
    picked = log_probs[np.arange(y_true.size), class_indices(y_true)]
    return float(-picked.mean())


def fit_temperature(adjusted: NDArray[np.float64], y_true: NDArray[np.str_]) -> float:
    """Fit one temperature by minimizing mean log loss over log T (EVAL-11).

    Raises:
        TemperatureAtBoundError: If the optimum is within 1% of a bound.
    """
    true_index = class_indices(y_true)
    rows = np.arange(y_true.size)

    def loss(log_t: float) -> float:
        log_probs = log_softmax(adjusted * math.exp(-log_t), axis=1)
        return float(-log_probs[rows, true_index].mean())

    low, high = TEMPERATURE_BOUNDS
    result = minimize_scalar(
        loss, bounds=(math.log(low), math.log(high)), method="bounded"
    )
    temperature = math.exp(float(result.x))
    side = None
    if temperature < low * (1 + _BOUND_MARGIN):
        side = "lower"
    elif temperature > high * (1 - _BOUND_MARGIN):
        side = "upper"
    if side is not None:
        raise TemperatureAtBoundError(
            f"temperature {temperature:.4g} is within 1% of the {side} bound of "
            f"{TEMPERATURE_BOUNDS}; stop and ask Din (Phase 3 plan, stop 5)"
        )
    return temperature


def _bins(
    prob_k: NDArray[np.float64], is_k: NDArray[np.bool_], n_bins: int
) -> list[tuple[NDArray[np.float64], NDArray[np.bool_]]]:
    # Stable sort, so ties keep the original order; array_split makes sizes
    # differ by at most one beat (equal mass).
    order = np.argsort(prob_k, kind="stable")
    return [(prob_k[part], is_k[part]) for part in np.array_split(order, n_bins)]


def ece_equal_mass(
    prob_k: NDArray[np.float64], is_k: NDArray[np.bool_], n_bins: int = ECE_BINS
) -> float:
    """Classwise ECE with equal-mass bins (EVAL-12).

    Args:
        prob_k: Calibrated probability of class k per beat, `(n,)`.
        is_k: Whether each beat's true class is k, `(n,)`.
        n_bins: Number of bins.

    Returns:
        Sum over bins of n_b / N * |mean probability - observed rate|.
    """
    n = prob_k.size
    total = 0.0
    for p, y in _bins(prob_k, is_k, n_bins):
        if p.size:
            total += p.size / n * abs(float(p.mean()) - float(y.mean()))
    return total


def reliability_data(
    prob_k: NDArray[np.float64], is_k: NDArray[np.bool_], n_bins: int = ECE_BINS
) -> list[dict[str, Any]]:
    """Per equal-mass bin: count, mean probability, observed rate, range."""
    return [
        {
            "count": int(p.size),
            "mean_probability": float(p.mean()),
            "observed_rate": float(y.mean()),
            "lowest": float(p.min()),
            "highest": float(p.max()),
        }
        for p, y in _bins(prob_k, is_k, n_bins)
        if p.size
    ]


def brier(probs: NDArray[np.float64], y_true: NDArray[np.str_]) -> float:
    """Mean over beats of the squared distance to the one-hot label (4 classes)."""
    one_hot = np.zeros_like(probs)
    one_hot[np.arange(y_true.size), class_indices(y_true)] = 1.0
    return float(((probs - one_hot) ** 2).sum(axis=1).mean())
