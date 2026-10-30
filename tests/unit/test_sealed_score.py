"""Phase 5 settling 1: the frozen baseline scored with NumPy matches scikit-learn."""

from pathlib import Path

import numpy as np
from cv_support import synthetic_beats
from run_support import make_repo, settings

from heartbeat.constants import PARITY_TOLERANCE, SCORED_CLASSES
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.models.baseline import BASELINE
from heartbeat.models.inputs import apply_rr_scaler, fit_rr_scaler, rr_model_inputs
from heartbeat.sealed.score import BaselineParams, baseline_logits
from heartbeat.train.final import train_final_baseline


def test_numpy_baseline_logits_match_scikit_learn(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    train = synthetic_beats(n_subjects=4, seed=0)
    fitted = train_final_baseline(
        settings(tmp_path), train, c=0.1, temperature=1.2, root=repo / "runs", repo=repo
    )
    params = BaselineParams(
        coefficients=fitted.coefficients,
        intercepts=fitted.intercepts,
        scaler_mean=fitted.scaler_mean,
        scaler_std=fitted.scaler_std,
        log_class_weights=np.log([fitted.class_weights[c] for c in SCORED_CLASSES]),
        temperature=fitted.temperature,
    )
    other = synthetic_beats(n_subjects=3, seed=5)
    rr = rr_model_inputs(other.rr_s)
    scaler = fit_rr_scaler(rr_model_inputs(train.rr_s))
    expected = BASELINE.logits(fitted.fitted, apply_rr_scaler(scaler, rr))
    got = baseline_logits(params, other.rr_s)
    assert got.dtype == np.float64
    np.testing.assert_allclose(got, expected, rtol=0, atol=PARITY_TOLERANCE)
    np.testing.assert_array_equal(predict_labels(got), predict_labels(expected))
