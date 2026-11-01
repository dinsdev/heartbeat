"""Scoring the committed models (Phase 5 settlings 1 and 2; EVAL-05).

The sealed run scores only committed files: the three CNN seeds through
Python ONNX Runtime on CPU, and the baseline's `baseline.json` through NumPy.
Both take the same inputs as training (the RR model inputs from
`heartbeat.models.inputs`, the z-scored windows from `heartbeat.signal`), so
the scoring path is the pipeline's own.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

from heartbeat.constants import RR_FEATURE_NAMES, SCORED_CLASSES
from heartbeat.models.inputs import RRScaler, apply_rr_scaler, rr_model_inputs

# Design call 3: the exported model's input and output names.
INPUT_NAMES = ("window", "rr")
OUTPUT_NAME = "logits"


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


def _read_json(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def _check_classes(path: Path, payload: dict[str, Any]) -> None:
    if payload.get("classes") != list(SCORED_CLASSES):
        raise ValueError(
            f"{path}: classes {payload.get('classes')}, expected {list(SCORED_CLASSES)}"
        )


def load_scaler(path: Path) -> RRScaler:
    """Read `scaler.json`, the RR scaler every seed shares.

    Raises:
        ValueError: If its feature order is not `RR_FEATURE_NAMES`.
    """
    payload = _read_json(path)
    if payload.get("features") != list(RR_FEATURE_NAMES):
        raise ValueError(f"{path}: features {payload.get('features')}")
    return RRScaler(
        mean=np.array(payload["mean"], dtype=np.float64),
        std=np.array(payload["std"], dtype=np.float64),
    )


def load_baseline(path: Path) -> BaselineParams:
    """Read `baseline.json` (settling 1).

    Raises:
        ValueError: If its class order is not `SCORED_CLASSES`.
    """
    payload = _read_json(path)
    _check_classes(path, payload)
    return BaselineParams(
        coefficients=np.array(payload["coefficients"], dtype=np.float64),
        intercepts=np.array(payload["intercepts"], dtype=np.float64),
        scaler_mean=np.array(payload["scaler"]["mean"], dtype=np.float64),
        scaler_std=np.array(payload["scaler"]["std"], dtype=np.float64),
        log_class_weights=np.array(payload["log_class_weights"], dtype=np.float64),
        temperature=float(payload["temperature"]),
    )


@dataclass(frozen=True)
class Calibration:
    """One CNN seed's `calibration.json`: logit adjustment and temperature.

    Attributes:
        log_class_weights: Log of the training class weights, `(4,)`.
        temperature: The seed's DS1 out-of-fold temperature.
    """

    log_class_weights: NDArray[np.float64]
    temperature: float


def load_calibration(path: Path) -> Calibration:
    """Read a seed's `calibration.json`.

    Raises:
        ValueError: If its class order is not `SCORED_CLASSES`.
    """
    payload = _read_json(path)
    _check_classes(path, payload)
    return Calibration(
        log_class_weights=np.array(payload["log_class_weights"], dtype=np.float64),
        temperature=float(payload["temperature"]),
    )


def onnx_session(model: Path | bytes) -> ort.InferenceSession:
    """An ONNX Runtime session on CPU with one thread, so runs repeat exactly."""
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    source = str(model) if isinstance(model, Path) else model
    return ort.InferenceSession(
        source, sess_options=options, providers=["CPUExecutionProvider"]
    )


def onnx_logits(
    session: ort.InferenceSession,
    windows: NDArray[np.float32],
    rr: NDArray[np.float32],
) -> NDArray[np.float32]:
    """Raw logits `(n, 4)` from z-scored windows `(n, 1, 256)`, scaled RR `(n, 6)`."""
    assert windows.dtype == np.float32, windows.dtype
    assert rr.dtype == np.float32, rr.dtype
    if windows.shape[0] == 0:
        return np.zeros((0, len(SCORED_CLASSES)), dtype=np.float32)
    (logits,) = session.run(
        [OUTPUT_NAME], {INPUT_NAMES[0]: windows, INPUT_NAMES[1]: rr}
    )
    out: NDArray[np.float32] = np.asarray(logits, dtype=np.float32)
    return out
