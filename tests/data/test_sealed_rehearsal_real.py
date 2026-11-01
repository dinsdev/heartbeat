"""Phase 5 settling 3: `run_sealed`'s whole success path, rehearsed on DS1.

DS1 records stand in for DS2, a planted freeze record sits in a temporary git
repo with copies of the committed model files, and every output goes under the
test's temporary folder. The numbers are in-sample DS1 scores: nothing here
asserts their values and none is quoted anywhere (rule 2). Red until `rebuild`
has exported the models (Phase 5, Task 10).
"""

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from run_support import git

from heartbeat.config import Settings
from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import prepare_in_memory
from heartbeat.export.bundle import bundle_files
from heartbeat.export.freeze import FROZEN_INPUTS, FreezeError, write_freeze
from heartbeat.paths import MODELS_DIR, REPO_ROOT
from heartbeat.sealed import run as run_module
from heartbeat.sealed.log import ENTRY_KEYS, check_log, read_log
from heartbeat.sealed.run import comparable, run_sealed

LABEL = "DS1 rehearsal, in-sample (never quoted)"


def _frozen_repo(tmp_path: Path) -> Path:
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


def _run(
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


def _intervals(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        if {"point", "low", "high", "skipped", "draws"} <= set(node):
            return [node]
        return [i for v in node.values() for i in _intervals(v)]
    if isinstance(node, list):
        return [i for v in node for i in _intervals(v)]
    return []


@pytest.mark.rule("R42")
def test_the_sealed_path_runs_end_to_end_on_ds1(
    tmp_path: Path,
    settings: Settings,
    splits: Splits,
    subjects: dict[str, str],
    raw_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared: list[str] = []

    def spy(raw: Path, record: str, lead: str, subject: str) -> Any:
        prepared.append(record)
        return prepare_in_memory(raw, record, lead, subject)

    monkeypatch.setattr(run_module, "prepare_in_memory", spy)
    repo = _frozen_repo(tmp_path)
    out = tmp_path / "out"
    entry = _run(repo, out, settings, splits, subjects)
    assert prepared == list(splits.ds1)
    assert not set(prepared) & set(splits.ds2)

    log_path = out / "results" / "test_runs.jsonl"
    assert sorted(entry) == list(ENTRY_KEYS)
    assert entry["id"] == 1
    assert entry["type"] == "sealed"
    assert entry["commit"] == git(repo, "rev-parse", "HEAD")
    report = json.loads((out / entry["report"]).read_text("utf-8"))
    for key in (
        "headline",
        "comparison",
        "fpr",
        "s_without_excluded",
        "per_patient",
        "confusion",
        "n_and_f",
        "seed_range",
        "calibration",
    ):
        assert key in report, key
    assert report["data"] == LABEL
    assert report["bootstrap"]["draws"] == 10_000
    assert report["freeze_commit"] == git(repo, "rev-parse", "HEAD~1")
    scored = report["beats"]["scored"]
    assert sum(report["beats"]["by_class"].values()) == scored
    for name, matrix in report["confusion"]["matrices"].items():
        assert int(np.sum(matrix)) == scored, name
    assert report["s_without_excluded"]["present"] is False
    assert len(report["patients"]) == len(splits.ds1)
    intervals = _intervals(report)
    assert intervals
    for interval in intervals:
        assert interval["draws"] == 10_000
        assert 0 <= interval["skipped"] <= interval["draws"]
        if interval["low"] is not None:
            assert interval["low"] <= interval["high"]

    # R42: a second run appends and rewrites nothing; its numbers repeat.
    before = log_path.read_bytes()
    second = _run(repo, out, settings, splits, subjects)
    assert second["id"] == 2
    assert log_path.read_bytes().startswith(before)
    assert [e["id"] for e in read_log(log_path)] == [1, 2]
    check_log(log_path, out)
    again = json.loads((out / second["report"]).read_text("utf-8"))
    assert comparable(again) == comparable(report)


def test_the_gate_refuses_before_any_record_is_read(
    tmp_path: Path,
    settings: Settings,
    splits: Splits,
    subjects: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared: list[str] = []
    monkeypatch.setattr(
        run_module, "prepare_in_memory", lambda *a: prepared.append(a[1])
    )
    repo = _frozen_repo(tmp_path)
    (repo / "notes.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(FreezeError, match="dirty"):
        _run(repo, tmp_path / "out", settings, splits, subjects)
    assert prepared == []
    assert not (tmp_path / "out").exists()
