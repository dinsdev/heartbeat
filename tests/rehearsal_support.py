"""The DS1 rehearsal of the sealed run, shared by the real-data rehearsals.

DS1 records stand in for DS2, a planted freeze record sits in a temporary git
repo with copies of the committed model files, and every output goes under the
test's temporary folder (Phase 5 settling 3, Phase 7 settling 4).
"""

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from run_support import git

from heartbeat.config import Settings
from heartbeat.data.manifests import Splits
from heartbeat.export.bundle import bundle_files
from heartbeat.export.freeze import FROZEN_INPUTS, write_freeze
from heartbeat.paths import MODELS_DIR, REPO_ROOT
from heartbeat.sealed.run import run_sealed

LABEL = "DS1 rehearsal, in-sample (never quoted)"


def frozen_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(MODELS_DIR, repo / "models" / "heartbeat-v1")
    for name in FROZEN_INPUTS:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, repo / name)
    models = repo / "models" / "heartbeat-v1"
    export = {"files": bundle_files(models, repo)}
    (repo / "results").mkdir()
    (repo / "results" / "export.json").write_text(json.dumps(export), "utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "export")
    write_freeze(repo, models, export, date(2027, 1, 15))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "freeze")
    return repo


def run_on_ds1(
    repo: Path,
    out: Path,
    settings: Settings,
    splits: Splits,
    subjects: dict[str, str],
) -> dict[str, Any]:
    return run_sealed(
        splits.ds1,
        settings.data.raw_dir,
        repo / "models" / "heartbeat-v1",
        out / "results" / "test_runs.jsonl",
        out / "results" / "test_runs",
        "sealed",
        repo=repo,
        log_root=out,
        lead=splits.lead,
        subjects=subjects,
        data_label=LABEL,
        require_remote=False,
        today=date(2027, 1, 16),
    )
