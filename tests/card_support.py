"""Results, a bundle and a sealed report for the card and verify tests (synthetic).

The DS1 results files are copies of the committed ones; `export.json` and
`data_summary.json` are built here; the sealed report comes from synthetic
beats. No record is read.
"""

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from cv_support import synthetic_beats
from sealed_support import synthetic_scores

from heartbeat.cards.blocks import CardSources
from heartbeat.data.describe import describe_data
from heartbeat.data.loader import BeatTable
from heartbeat.data.manifests import Splits
from heartbeat.data.records import Demographics
from heartbeat.paths import RESULTS_DIR
from heartbeat.sealed.log import append_entry
from heartbeat.sealed.report import sealed_report

DS1_RESULTS = ("cv_baseline", "cv_cnn", "cv_cnn_curves", "exhibit", "selection")


def export_record() -> dict[str, Any]:
    models = []
    files = []
    for seed in (0, 1, 2):
        name = "model.onnx" if seed == 0 else f"seeds/seed-{seed}/model.onnx"
        models.append({"seed": seed, "path": f"models/heartbeat-v1/{name}"})
        files.append(
            {
                "path": f"models/heartbeat-v1/{name}",
                "bytes": 235466,
                "sha256": f"{seed}" * 64,
            }
        )
    files.append(
        {"path": "models/heartbeat-v1/baseline.json", "bytes": 1758, "sha256": "b" * 64}
    )
    return {
        "parameters": 52036,
        "opset": 20,
        "size_limit_bytes": 1_000_000,
        "shipped_seed": 0,
        "models": models,
        "files": files,
    }


def data_summary() -> dict[str, Any]:
    splits = Splits(ds1=("101",), ds2=("103",), excluded={}, lead="MLII")

    base = synthetic_beats(n_subjects=1, per_subject=20)
    kept = BeatTable(
        np.full(20, "101"),
        np.full(20, "101"),
        base.sample,
        base.beat_class,
        base.window_adu,
        base.rr_s,
    )
    return describe_data(
        splits,
        {"101": "101", "103": "103"},
        {"101": {"N": 1860, "A": 3, "Q": 2}, "103": {"N": 2082, "A": 2}},
        {"101": Demographics(75, "F"), "103": Demographics(None, "M")},
        kept,
    )


def results_dir(root: Path) -> Path:
    folder = root / "results"
    folder.mkdir(parents=True)
    for name in DS1_RESULTS:
        shutil.copyfile(RESULTS_DIR / f"{name}.json", folder / f"{name}.json")
    (folder / "export.json").write_text(json.dumps(export_record()), "utf-8")
    (folder / "data_summary.json").write_text(json.dumps(data_summary()), "utf-8")
    return folder


def sources(root: Path) -> CardSources:
    folder = results_dir(root)
    models = root / "models" / "heartbeat-v1"
    models.mkdir(parents=True)
    return CardSources(folder, models, folder / "test_runs.jsonl", root)


def log_sealed_run(sources: CardSources) -> None:
    y, record, scores = synthetic_scores()
    report = sealed_report(
        y, record, record, scores, data_label="synthetic", n_draws=50
    )
    append_entry(
        sources.log_path,
        sources.results_dir / "test_runs",
        "sealed",
        report,
        commit="c" * 40,
        freeze_sha256="f" * 64,
        today=date(2027, 1, 16),
        repo=sources.log_root,
    )
