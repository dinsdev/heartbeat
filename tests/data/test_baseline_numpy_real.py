"""Phase 5 settling 1: NumPy scoring of the frozen baseline on real DS1 rows."""

import json
from pathlib import Path

import numpy as np
from run_support import make_repo

from heartbeat.config import Settings
from heartbeat.constants import PARITY_TOLERANCE, SCORED_CLASSES
from heartbeat.data.loader import load_ds1
from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import PrepareReport
from heartbeat.evaluate.calibration import predict_labels
from heartbeat.models.baseline import BASELINE
from heartbeat.models.inputs import apply_rr_scaler, fit_rr_scaler, rr_model_inputs
from heartbeat.paths import RESULTS_DIR
from heartbeat.sealed.score import BaselineParams, baseline_logits
from heartbeat.train.final import train_final_baseline


def test_numpy_logits_match_scikit_learn_on_every_ds1_row(
    tmp_path: Path,
    settings: Settings,
    splits: Splits,
    subjects: dict[str, str],
    prepared_ds1: tuple[Path, PrepareReport],
) -> None:
    folder, _ = prepared_ds1
    beats = load_ds1(folder, splits, subjects)
    cv = json.loads((RESULTS_DIR / "cv_baseline.json").read_text("utf-8"))
    repo = make_repo(tmp_path)
    fitted = train_final_baseline(
        settings,
        beats,
        c=float(cv["chosen_c"]),
        temperature=float(cv["calibration"]["temperature"]),
        root=repo / "runs",
        repo=repo,
    )
    params = BaselineParams(
        coefficients=fitted.coefficients,
        intercepts=fitted.intercepts,
        scaler_mean=fitted.scaler_mean,
        scaler_std=fitted.scaler_std,
        log_class_weights=np.log([fitted.class_weights[c] for c in SCORED_CLASSES]),
        temperature=fitted.temperature,
    )
    rr = rr_model_inputs(beats.rr_s)
    scaled = apply_rr_scaler(fit_rr_scaler(rr), rr)
    expected = BASELINE.logits(fitted.fitted, scaled)
    got = baseline_logits(params, beats.rr_s)
    np.testing.assert_allclose(got, expected, rtol=0, atol=PARITY_TOLERANCE)
    np.testing.assert_array_equal(predict_labels(got), predict_labels(expected))
    assert fitted.n_rows == beats.sample.size
