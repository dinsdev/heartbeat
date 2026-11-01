"""`run_sealed`: from a freeze record to a logged report (EVAL-05, EVAL-06).

`evaluate-test` binds exactly one set of arguments: the DS2 records, the cache,
`models/heartbeat-v1/`, `results/test_runs.jsonl` and `results/test_runs/`
(Phase 5 settling 3). The rehearsal test runs this same function with DS1
records in DS2's place and every output in a temporary folder, so the sealed
run is not this code's first run. Records are prepared in memory and never
written (Phase 2 settling 4); only committed files are scored (settling 2).
"""

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import BOOTSTRAP_DRAWS, CNN_SEEDS
from heartbeat.data.prepare import prepare_in_memory
from heartbeat.export.bundle import seed_folder
from heartbeat.export.freeze import check_gate
from heartbeat.models.augment import model_windows
from heartbeat.models.inputs import RRScaler, apply_rr_scaler, rr_model_inputs
from heartbeat.sealed.log import append_entry, read_log
from heartbeat.sealed.report import BASELINE, ModelScores, sealed_report
from heartbeat.sealed.score import (
    baseline_logits,
    load_baseline,
    load_calibration,
    load_scaler,
    onnx_logits,
    onnx_session,
)
from heartbeat.signal.windows import extract_windows

SEALED_DATA_LABEL = "DS2 test, CPU (committed ONNX models and baseline.json)"

# Rows per ONNX Runtime call, to bound memory. Fixed, so a reproduction scores
# in the same batches as the sealed run.
SCORE_BATCH_SIZE = 4096

# Report keys that name the run rather than its numbers.
_RUN_KEYS = ("run", "commit", "dirty", "entry_type", "freeze_sha256")


class ReproductionMismatchError(RuntimeError):
    """A reproduction's report differs from the last sealed one (OPS-03)."""


@dataclass(frozen=True)
class SealedBeats:
    """Every kept beat of the given records, Q included.

    Attributes:
        record_id: Each beat's record, `(n,)`.
        subject_id: Each beat's patient, `(n,)`.
        beat_class: AAMI class, `(n,)`.
        window_adu: The int16 window, `(n, 256)`.
        rr_s: RR features, `(n, 6)`.
    """

    record_id: NDArray[np.str_]
    subject_id: NDArray[np.str_]
    beat_class: NDArray[np.str_]
    window_adu: NDArray[np.int16]
    rr_s: NDArray[np.float64]


def load_records(
    records: Sequence[str], raw_dir: Path, lead: str, subjects: Mapping[str, str]
) -> SealedBeats:
    """Prepare each record in memory with the training pipeline's own function."""
    parts = []
    for record in records:
        prepared = prepare_in_memory(raw_dir, record, lead, subjects[record])
        samples = prepared.beat_sample[prepared.kept]
        n = samples.size
        parts.append(
            SealedBeats(
                record_id=np.full(n, record),
                subject_id=np.full(n, prepared.subject_id),
                beat_class=prepared.beat_class[prepared.kept],
                window_adu=extract_windows(prepared.trace_adu, samples),
                rr_s=prepared.rr_s,
            )
        )
    return SealedBeats(
        record_id=np.concatenate([p.record_id for p in parts]),
        subject_id=np.concatenate([p.subject_id for p in parts]),
        beat_class=np.concatenate([p.beat_class for p in parts]),
        window_adu=np.concatenate([p.window_adu for p in parts]),
        rr_s=np.concatenate([p.rr_s for p in parts]),
    )


def score_models(beats: SealedBeats, models_dir: Path) -> dict[str, ModelScores]:
    """Raw logits of the three seeds (ONNX Runtime) and the baseline (NumPy)."""
    scaler = load_scaler(models_dir / "scaler.json")
    rr = apply_rr_scaler(
        RRScaler(mean=scaler.mean, std=scaler.std), rr_model_inputs(beats.rr_s)
    ).astype(np.float32)
    windows = model_windows(beats.window_adu)
    scores: dict[str, ModelScores] = {}
    for seed in CNN_SEEDS:
        folder = models_dir / seed_folder(seed)
        session = onnx_session(folder / "model.onnx")
        parts = [
            onnx_logits(
                session,
                windows[start : start + SCORE_BATCH_SIZE],
                rr[start : start + SCORE_BATCH_SIZE],
            )
            for start in range(0, windows.shape[0], SCORE_BATCH_SIZE)
        ]
        calibration = load_calibration(folder / "calibration.json")
        scores[f"cnn-seed-{seed}"] = ModelScores(
            logits=np.concatenate(parts).astype(np.float64),
            log_class_weights=calibration.log_class_weights,
            temperature=calibration.temperature,
        )
    baseline = load_baseline(models_dir / "baseline.json")
    scores[BASELINE] = ModelScores(
        logits=baseline_logits(baseline, beats.rr_s),
        log_class_weights=baseline.log_class_weights,
        temperature=baseline.temperature,
    )
    return scores


def comparable(report: Mapping[str, Any]) -> dict[str, Any]:
    """The report without the keys that name the run (OPS-03's comparison)."""
    return {k: v for k, v in report.items() if k not in _RUN_KEYS}


def run_sealed(
    records: Sequence[str],
    raw_dir: Path,
    models_dir: Path,
    log_path: Path,
    reports_dir: Path,
    entry_type: str,
    *,
    repo: Path,
    log_root: Path,
    lead: str,
    subjects: Mapping[str, str],
    data_label: str,
    require_remote: bool = True,
    today: date | None = None,
    n_draws: int = BOOTSTRAP_DRAWS,
) -> dict[str, Any]:
    """Gate, prepare in memory, score, report, then append to the log.

    Args:
        records: The records to evaluate (DS2 from `evaluate-test`).
        raw_dir: The download cache.
        models_dir: The frozen bundle with its freeze record.
        log_path: The append-only log.
        reports_dir: Where the full report goes.
        entry_type: "sealed" or "reproduction".
        repo: The git checkout the gate checks.
        log_root: The folder report paths in the log are relative to.
        lead: The lead to read, from the split manifest.
        subjects: Record to patient.
        data_label: What the records are, for the report.
        require_remote: R47's `origin/main` check.
        today: The log date; today in UTC by default.
        n_draws: Bootstrap draws.

    Returns:
        The log entry.

    Raises:
        FreezeError: From the gate, before any record is read (R41).
        ReproductionMismatchError: After logging a reproduction whose report
            differs from the last sealed one.
    """
    gate = check_gate(repo, models_dir, require_remote=require_remote)
    beats = load_records(records, raw_dir, lead, subjects)
    scores = score_models(beats, models_dir)
    report = sealed_report(
        beats.beat_class,
        beats.subject_id,
        beats.record_id,
        scores,
        data_label=data_label,
        n_draws=n_draws,
    )
    entries = read_log(log_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    report = {
        **report,
        "records": list(records),
        "freeze_commit": gate["record"]["commit"],
        "run": f"{len(entries) + 1}-{entry_type}",
        "entry_type": entry_type,
        "commit": head,
        "dirty": False,
        "freeze_sha256": gate["sha256"],
    }
    entry = append_entry(
        log_path,
        reports_dir,
        entry_type,
        report,
        commit=head,
        freeze_sha256=gate["sha256"],
        today=today or datetime.now(UTC).date(),
        repo=log_root,
    )
    if entry_type == "reproduction":
        sealed = [e for e in entries if e["type"] == "sealed"]
        if not sealed:
            raise ReproductionMismatchError("no sealed entry to reproduce")
        last = json.loads((log_root / sealed[-1]["report"]).read_text("utf-8"))
        if comparable(last) != comparable(report):
            raise ReproductionMismatchError(
                f"report {entry['report']} differs from {sealed[-1]['report']}"
            )
    return entry
