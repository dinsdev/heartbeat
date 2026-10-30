"""EVAL-06, C6, R42: the append-only sealed-run log."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from run_support import git

from heartbeat.sealed.log import (
    ENTRY_TYPES,
    LogError,
    append_entry,
    check_log,
    check_log_history,
    read_log,
)

TODAY = date(2027, 1, 15)


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    results = tmp_path / "results"
    return results / "test_runs.jsonl", results / "test_runs"


def _append(tmp_path: Path, kind: str = "sealed", report: Any = None) -> Any:
    log_path, reports_dir = _paths(tmp_path)
    return append_entry(
        log_path,
        reports_dir,
        kind,
        report or {"headline": {"macro_f1_nsv": 0.5}},
        commit="c" * 40,
        freeze_sha256="f" * 64,
        today=TODAY,
        repo=tmp_path,
    )


@pytest.mark.rule("R42")
def test_entries_append_with_sequential_ids_and_both_types(tmp_path: Path) -> None:
    assert ENTRY_TYPES == ("sealed", "reproduction")
    first = _append(tmp_path)
    log_path, _ = _paths(tmp_path)
    before = log_path.read_bytes()
    second = _append(tmp_path, "reproduction")
    assert log_path.read_bytes().startswith(before)
    entries = read_log(log_path)
    assert [e["id"] for e in entries] == [1, 2]
    assert [e["type"] for e in entries] == ["sealed", "reproduction"]
    assert entries == [first, second]
    assert first["report"] == "results/test_runs/1-sealed.json"
    assert second["report"] == "results/test_runs/2-reproduction.json"
    assert sorted(first) == [
        "commit",
        "date",
        "freeze_sha256",
        "id",
        "report",
        "report_sha256",
        "type",
    ]
    assert first["date"] == "2027-01-15"
    assert len(log_path.read_text("utf-8").splitlines()) == 2
    check_log(log_path, tmp_path)


@pytest.mark.rule("R42")
def test_an_unknown_entry_type_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LogError, match="rehearsal"):
        _append(tmp_path, "rehearsal")


@pytest.mark.rule("R42")
def test_an_existing_report_file_is_never_overwritten(tmp_path: Path) -> None:
    _, reports_dir = _paths(tmp_path)
    reports_dir.mkdir(parents=True)
    (reports_dir / "1-sealed.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(LogError, match="exists"):
        _append(tmp_path)
    assert (reports_dir / "1-sealed.json").read_text("utf-8") == "{}\n"
    assert not _paths(tmp_path)[0].exists()


@pytest.mark.rule("R42")
def test_a_rewritten_earlier_line_is_detected(tmp_path: Path) -> None:
    _append(tmp_path)
    _append(tmp_path, "reproduction")
    log_path, _ = _paths(tmp_path)
    lines = log_path.read_text("utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["id"] = 3
    log_path.write_text("\n".join([json.dumps(entry), lines[1]]) + "\n", "utf-8")
    with pytest.raises(LogError, match="id"):
        check_log(log_path, tmp_path)


@pytest.mark.rule("R42")
def test_a_changed_report_is_detected(tmp_path: Path) -> None:
    _append(tmp_path)
    _, reports_dir = _paths(tmp_path)
    (reports_dir / "1-sealed.json").write_text('{"headline": 1}\n', "utf-8")
    with pytest.raises(LogError, match="1-sealed"):
        check_log(_paths(tmp_path)[0], tmp_path)


@pytest.mark.rule("R42")
def test_history_must_only_ever_append(tmp_path: Path) -> None:
    repo = tmp_path
    git(repo, "init", "-q", "-b", "main")
    _append(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "sealed run")
    _append(repo, "reproduction")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "reproduction")
    log_path, _ = _paths(repo)
    check_log_history(log_path, repo)
    lines = log_path.read_text("utf-8").splitlines()
    log_path.write_text(lines[1] + "\n" + lines[0] + "\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "reorder")
    with pytest.raises(LogError, match="does not extend"):
        check_log_history(log_path, repo)


def test_a_missing_log_reads_as_empty_and_checks_clean(tmp_path: Path) -> None:
    log_path, _ = _paths(tmp_path)
    assert read_log(log_path) == []
    check_log(log_path, tmp_path)
