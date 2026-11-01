"""DS1 parity fixtures (E5; PARITY-02, PARITY-03, R26, R27).

Fifty kept DS1 beats (20 N, 12 S, 12 V, 6 F; no Q), drawn with their own
seed (Phase 5 task plan, design call 4). For each beat the fixture holds
every step of the pipeline, each computed by the pipeline's own function: the
annotated beat samples the RR features read, the int16 window, the z-scored
window, the six RR values, the model inputs after the log ratios, the scaled
inputs, and for every seed the raw logits, adjusted logits, probabilities and
label, plus the baseline's. CI and the browser check their own steps against
these numbers without a checkpoint or the download.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray

from heartbeat.constants import (
    PARITY_FIXTURE_QUOTA,
    PARITY_FIXTURE_SEED,
    PARITY_TOLERANCE,
    RR_LOCAL_INTERVALS,
    RR_LONG_WINDOW_SAMPLES,
    SCORED_CLASSES,
)
from heartbeat.data.loader import BeatTable, require_ds1
from heartbeat.data.manifests import Splits
from heartbeat.evaluate.calibration import (
    adjust_logits,
    calibrated_probs,
    predict_labels,
)
from heartbeat.export.bundle import ATTRIBUTION_NOTICE, seed_folder
from heartbeat.export.onnx import ParityError
from heartbeat.models.cnn import HeartbeatCNN
from heartbeat.models.inputs import RRScaler, apply_rr_scaler, rr_model_inputs
from heartbeat.runs import canonical_json, write_text_atomic
from heartbeat.sealed.score import (
    BaselineParams,
    baseline_logits,
    load_baseline,
    onnx_logits,
    onnx_session,
)
from heartbeat.signal.rr import rr_features
from heartbeat.signal.windows import zscore_windows
from heartbeat.train.loop import cnn_logits

FIXTURES_NAME = "fixtures.json"


@dataclass(frozen=True)
class FixtureModel:
    """One CNN seed as the fixtures need it.

    Attributes:
        seed: The master seed.
        network: The loaded final model, eval mode, on CPU.
        class_weights: Its training class weights.
        temperature: Its DS1 out-of-fold temperature.
    """

    seed: int
    network: HeartbeatCNN
    class_weights: Mapping[str, float]
    temperature: float


def draw_fixture_rows(
    beats: BeatTable,
    quota: Mapping[str, int] = PARITY_FIXTURE_QUOTA,
    seed: int = PARITY_FIXTURE_SEED,
) -> NDArray[np.int64]:
    """Rows of `beats` to use, by class quota, without replacement, sorted.

    Raises:
        ValueError: If a class has fewer beats than its quota.
    """
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    picks: list[NDArray[np.int64]] = []
    for cls in SCORED_CLASSES:
        candidates = np.flatnonzero(beats.beat_class == cls)
        if candidates.size < quota[cls]:
            raise ValueError(
                f"class {cls}: {candidates.size} beats, quota {quota[cls]}"
            )
        picks.append(rng.choice(candidates, size=quota[cls], replace=False))
    return np.sort(np.concatenate(picks)).astype(np.int64)


def rr_context(
    beat_sample: NDArray[np.int64], index: int
) -> tuple[NDArray[np.int64], int]:
    """The annotated beats beat `index`'s RR features read, and its position.

    From the start of the earliest interval the local or long average uses
    (DATA-07) to the next beat, which post-RR reads. `rr_features` on the
    returned samples gives this beat's features at row `position - 1`.
    """
    assert 1 <= index <= beat_sample.size - 2, index
    first_long = max(
        1,
        int(
            np.searchsorted(
                beat_sample, beat_sample[index] - RR_LONG_WINDOW_SAMPLES, side="left"
            )
        ),
    )
    start = max(0, min(index - RR_LOCAL_INTERVALS, first_long - 1))
    return beat_sample[start : index + 2].copy(), index - start


def _scored(
    logits: NDArray[np.float64],
    class_weights: Mapping[str, float] | NDArray[np.float64],
    temperature: float,
) -> list[dict[str, Any]]:
    adjusted = adjust_logits(logits, class_weights)
    probs = calibrated_probs(adjusted, temperature)
    labels = predict_labels(logits)
    return [
        {
            "logits": logits[k].tolist(),
            "adjusted": adjusted[k].tolist(),
            "probabilities": probs[k].tolist(),
            "label": str(labels[k]),
        }
        for k in range(logits.shape[0])
    ]


def build_fixtures(
    beats: BeatTable,
    annotated: Mapping[str, NDArray[np.int64]],
    splits: Splits,
    models: Sequence[FixtureModel],
    baseline: BaselineParams,
) -> dict[str, Any]:
    """The `fixtures/parity/fixtures.json` payload.

    Args:
        beats: Every DS1 kept beat (`load_ds1`), whose RR scaler the models use.
        annotated: DS1 record to every annotated beat sample, Q included.
        splits: The split manifest; every fixture beat must be DS1 (R27).
        models: The three CNN seeds.
        baseline: The frozen baseline.

    Raises:
        SealedRecordError: If a drawn beat is not from DS1.
        ValueError: If a beat's RR features do not reproduce from its context.
    """
    rows = draw_fixture_rows(beats)
    require_ds1(sorted(set(beats.record_id[rows].tolist())), splits)
    scaler = RRScaler(mean=baseline.scaler_mean, std=baseline.scaler_std)
    windows_z = zscore_windows(beats.window_adu[rows])
    rr_s = beats.rr_s[rows]
    rr_inputs = rr_model_inputs(rr_s)
    rr_scaled = apply_rr_scaler(scaler, rr_inputs)
    per_seed = {
        m.seed: _scored(
            cnn_logits(
                m.network,
                windows_z.astype(np.float32)[:, np.newaxis, :],
                rr_scaled.astype(np.float32),
                torch.device("cpu"),
            ).astype(np.float64),
            m.class_weights,
            m.temperature,
        )
        for m in models
    }
    base = _scored(
        baseline_logits(baseline, rr_s),
        np.broadcast_to(np.exp(baseline.log_class_weights), (rows.size, 4)).copy(),
        baseline.temperature,
    )
    out_beats = []
    for k, row in enumerate(rows.tolist()):
        record = str(beats.record_id[row])
        sample = int(beats.sample[row])
        all_samples = annotated[record]
        index = int(np.searchsorted(all_samples, sample))
        if index >= all_samples.size or all_samples[index] != sample:
            raise ValueError(f"record {record}: beat {sample} is not annotated")
        context, position = rr_context(all_samples, index)
        again = rr_features(context)[position - 1]
        if not np.array_equal(again, rr_s[k]):
            raise ValueError(
                f"record {record}, beat {sample}: RR features do not reproduce "
                "from the annotated samples"
            )
        out_beats.append(
            {
                "record": record,
                "sample": sample,
                "class": str(beats.beat_class[row]),
                "rr_beat_samples": context.tolist(),
                "rr_beat_index": position,
                "window_adu": beats.window_adu[row].tolist(),
                "window_z": windows_z[k].tolist(),
                "rr_s": rr_s[k].tolist(),
                "rr_inputs": rr_inputs[k].tolist(),
                "rr_scaled": rr_scaled[k].tolist(),
                "seeds": {str(seed): scored[k] for seed, scored in per_seed.items()},
                "baseline": base[k],
            }
        )
    return {
        "label": (
            "parity fixtures: every preprocessing step and model output for kept "
            "DS1 beats, computed by the Python pipeline on CPU (PARITY-02)"
        ),
        "data": "DS1 only (R27)",
        "notice": ATTRIBUTION_NOTICE,
        "seed": PARITY_FIXTURE_SEED,
        "quota": dict(PARITY_FIXTURE_QUOTA),
        "classes": list(SCORED_CLASSES),
        "scaler": {"mean": scaler.mean.tolist(), "std": scaler.std.tolist()},
        "models": [
            {
                "seed": m.seed,
                "log_class_weights": np.log(
                    [m.class_weights[c] for c in SCORED_CLASSES]
                ).tolist(),
                "temperature": m.temperature,
            }
            for m in models
        ],
        "baseline_model": {
            "log_class_weights": baseline.log_class_weights.tolist(),
            "temperature": baseline.temperature,
        },
        "beats": out_beats,
    }


def write_fixtures(fixtures_dir: Path, payload: Mapping[str, Any]) -> Path:
    """Write `fixtures.json` as canonical JSON, atomically."""
    path = fixtures_dir / FIXTURES_NAME
    write_text_atomic(path, canonical_json(payload))
    return path


def fixture_parity(models_dir: Path, payload: Mapping[str, Any]) -> dict[str, float]:
    """Score the fixtures with the committed files and compare (R26).

    Every seed's ONNX file through Python ONNX Runtime on the stored model
    inputs, and `baseline.json` through NumPy on the stored RR values, against
    the stored logits: within 1e-5, labels exact. Needs no checkpoint and no
    download, so CI and `heartbeat verify` run it.

    Returns:
        Model name ("seed-<n>", "baseline") to the largest absolute difference.

    Raises:
        ParityError: On a difference above 1e-5 or a changed label.
    """
    beats = payload["beats"]
    windows = np.array([b["window_z"] for b in beats], dtype=np.float32)[
        :, np.newaxis, :
    ]
    rr = np.array([b["rr_scaled"] for b in beats], dtype=np.float32)
    rr_s = np.array([b["rr_s"] for b in beats], dtype=np.float64)
    found: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
    for model in payload["models"]:
        seed = int(model["seed"])
        path = models_dir / seed_folder(seed) / "model.onnx"
        got = onnx_logits(onnx_session(path), windows, rr).astype(np.float64)
        stored = np.array([b["seeds"][str(seed)]["logits"] for b in beats])
        found[f"seed-{seed}"] = (got, stored)
    baseline = load_baseline(models_dir / "baseline.json")
    stored = np.array([b["baseline"]["logits"] for b in beats])
    found["baseline"] = (baseline_logits(baseline, rr_s), stored)
    diffs: dict[str, float] = {}
    for name, (got, stored) in found.items():
        diff = float(np.max(np.abs(got - stored)))
        if not diff <= PARITY_TOLERANCE:
            raise ParityError(
                f"{name}: fixtures differ by {diff:.3g}, tolerance {PARITY_TOLERANCE}"
            )
        if not np.array_equal(predict_labels(got), predict_labels(stored)):
            raise ParityError(f"{name}: a fixture beat's label changed")
        diffs[name] = diff
    return diffs
