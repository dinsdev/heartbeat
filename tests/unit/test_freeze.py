"""EVAL-05, R41, R47: the freeze record and the gate's two modes.

A sealed run allows nothing but the record since the freeze commit; a
reproduction allows anything outside the frozen paths (Phase 7 settling 1).
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from run_support import git

from heartbeat.export.bundle import bundle_files
from heartbeat.export.freeze import (
    FROZEN_PATHS,
    FreezeError,
    GateMode,
    check_gate,
    write_freeze,
)

TODAY = date(2027, 1, 15)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for name, text in {
        "config/default.toml": "[train]\n",
        "manifests/folds.sha256": "abc  config/folds.json\n",
        "uv.lock": "lock\n",
        "src/code.py": "x = 1\n",
        "models/heartbeat-v1/model.onnx": "onnx-0",
        "models/heartbeat-v1/NOTICE": "notice\n",
        "models/heartbeat-v1/seeds/seed-1/model.onnx": "onnx-1",
    }.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    _write_export(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "export")
    return repo


def _write_export(repo: Path) -> None:
    files = bundle_files(repo / "models" / "heartbeat-v1", repo)
    (repo / "results").mkdir(exist_ok=True)
    (repo / "results" / "export.json").write_text(
        json.dumps({"files": files}), encoding="utf-8"
    )


def _export(repo: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (repo / "results" / "export.json").read_text("utf-8")
    )
    return payload


def _freeze(repo: Path) -> Path:
    path = write_freeze(repo, repo / "models" / "heartbeat-v1", _export(repo), TODAY)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "freeze")
    return path


def _gate(
    repo: Path, remote: bool = False, mode: GateMode = "sealed"
) -> dict[str, Any]:
    return check_gate(
        repo, repo / "models" / "heartbeat-v1", mode, require_remote=remote
    )


def test_the_record_holds_the_commit_inputs_models_and_date(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    path = _freeze(repo)
    record = json.loads(path.read_text("utf-8"))
    assert record["commit"] == head
    assert record["date"] == "2027-01-15"
    assert sorted(record["inputs"]) == [
        "config/default.toml",
        "manifests/folds.sha256",
        "uv.lock",
    ]
    assert sorted(record["models"]) == [
        "models/heartbeat-v1/NOTICE",
        "models/heartbeat-v1/model.onnx",
        "models/heartbeat-v1/seeds/seed-1/model.onnx",
    ]


@pytest.mark.rule("R41")
def test_a_matching_record_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    gate = _gate(repo)
    assert gate["record"]["commit"] == git(repo, "rev-parse", "HEAD~1")
    assert len(gate["sha256"]) == 64


@pytest.mark.rule("R41")
def test_no_record_refuses(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(FreezeError, match="no freeze record"):
        _gate(repo)


def _tamper(repo: Path, section: str, key: str) -> None:
    path = repo / "models" / "heartbeat-v1" / "freeze.json"
    record = json.loads(path.read_text("utf-8"))
    record[section][key] = "0" * 64
    path.write_text(json.dumps(record), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "tamper")


@pytest.mark.rule("R41")
def test_a_wrong_model_hash_refuses(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    _tamper(repo, "models", "models/heartbeat-v1/model.onnx")
    with pytest.raises(FreezeError, match=r"model\.onnx"):
        _gate(repo)


@pytest.mark.rule("R41")
def test_a_wrong_config_hash_refuses(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    _tamper(repo, "inputs", "config/default.toml")
    with pytest.raises(FreezeError, match=r"config/default\.toml"):
        _gate(repo)


@pytest.mark.rule("R41")
@pytest.mark.parametrize(
    "changed", ["src/code.py", "models/heartbeat-v1/model.onnx", "results/new.json"]
)
def test_any_change_besides_the_record_since_the_freeze_commit_refuses(
    tmp_path: Path, changed: str
) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    path = repo / changed
    path.write_text("changed\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "after the freeze")
    with pytest.raises(FreezeError, match=changed.replace(".", r"\.")):
        _gate(repo)


@pytest.mark.rule("R41")
@pytest.mark.parametrize("kind", ["edit", "untracked"])
def test_a_dirty_tree_refuses(tmp_path: Path, kind: str) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    if kind == "edit":
        (repo / "src" / "code.py").write_text("x = 2\n", encoding="utf-8")
    else:
        (repo / "notes.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(FreezeError, match="dirty"):
        _gate(repo)


@pytest.mark.rule("R41")
def test_an_unparseable_record_refuses(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    path = repo / "models" / "heartbeat-v1" / "freeze.json"
    path.write_text("{not json", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "broken")
    with pytest.raises(FreezeError, match="parse"):
        _gate(repo)


def test_freeze_refuses_a_dirty_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "src" / "code.py").write_text("x = 2\n", encoding="utf-8")
    with pytest.raises(FreezeError, match="dirty"):
        write_freeze(repo, repo / "models" / "heartbeat-v1", _export(repo), TODAY)
    assert not (repo / "models" / "heartbeat-v1" / "freeze.json").exists()


def test_freeze_refuses_model_files_that_differ_from_the_export(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "models" / "heartbeat-v1" / "model.onnx").write_text("other", "utf-8")
    git(repo, "commit", "-q", "-am", "swap the model")
    with pytest.raises(FreezeError, match=r"results/export\.json"):
        write_freeze(repo, repo / "models" / "heartbeat-v1", _export(repo), TODAY)


def test_freeze_refuses_when_a_record_exists(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    with pytest.raises(FreezeError, match="exists"):
        write_freeze(repo, repo / "models" / "heartbeat-v1", _export(repo), TODAY)


@pytest.mark.rule("R47")
def test_the_freeze_commit_must_be_on_origin_main(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    _freeze(repo)
    with pytest.raises(FreezeError, match="origin/main"):
        _gate(repo, remote=True)
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    assert _gate(repo, remote=True)["record"]["date"] == "2027-01-15"


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


# What lands on main after the sealed run (runbook step 5, then Goal B).
AFTER_THE_SEAL = {
    "results/test_runs.jsonl": '{"type": "sealed"}\n',
    "results/test_runs/1-sealed.json": "{}\n",
    "docs/MODEL_CARD.md": "rendered\n",
    "docs/src/notes.md": "a doc under a folder named src\n",
    "web/src/App.svelte": "<p>DS2</p>\n",
}


def test_frozen_paths_name_the_code_config_manifests_model_and_lock() -> None:
    assert FROZEN_PATHS == (
        "src/",
        "config/",
        "manifests/",
        "models/heartbeat-v1/",
        "pyproject.toml",
        "uv.lock",
    )


@pytest.mark.rule("R41")
def test_after_the_seal_a_reproduction_passes_and_a_sealed_run_refuses(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    _commit(repo, AFTER_THE_SEAL, "the sealed log, report and cards")
    assert _gate(repo, mode="reproduction")["record"]["date"] == "2027-01-15"
    with pytest.raises(FreezeError) as refused:
        _gate(repo, mode="sealed")
    for name in AFTER_THE_SEAL:
        assert name in str(refused.value)


@pytest.mark.rule("R41")
@pytest.mark.parametrize(
    "changed",
    [
        "src/code.py",
        "src/heartbeat/new.py",
        "config/default.toml",
        "config/folds.json",
        "manifests/splits.toml",
        "models/heartbeat-v1/model.onnx",
        "models/heartbeat-v1/scaler.json",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_a_change_under_a_frozen_path_refuses_a_reproduction(
    tmp_path: Path, changed: str
) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    _commit(repo, {**AFTER_THE_SEAL, changed: "changed after the freeze\n"}, "x")
    with pytest.raises(FreezeError, match=changed.replace(".", r"\.")):
        _gate(repo, mode="reproduction")


@pytest.mark.rule("R41")
@pytest.mark.parametrize("mode", ["sealed", "reproduction"])
def test_a_branch_merged_after_the_freeze_refuses_naming_its_code(
    tmp_path: Path, mode: GateMode
) -> None:
    """Phase 7 review focus 1: a merge commit, from a branch cut before the freeze."""
    repo = _repo(tmp_path)
    _freeze(repo)
    git(repo, "switch", "-q", "-c", "fix", "HEAD~1")
    _commit(repo, {"src/code.py": "x = 2\n"}, "fix")
    git(repo, "switch", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge fix", "fix")
    with pytest.raises(FreezeError, match=r"src/code\.py"):
        _gate(repo, mode=mode)


@pytest.mark.rule("R41")
def test_moving_a_file_out_of_a_frozen_path_refuses_a_reproduction(
    tmp_path: Path,
) -> None:
    """Both sides of a rename count, so a move out of `src/` is seen."""
    repo = _repo(tmp_path)
    _freeze(repo)
    (repo / "docs").mkdir()
    git(repo, "mv", "src/code.py", "docs/code.py")
    git(repo, "commit", "-q", "-m", "move")
    with pytest.raises(FreezeError, match=r"src/code\.py"):
        _gate(repo, mode="reproduction")


@pytest.mark.rule("R41")
@pytest.mark.parametrize("mode", ["sealed", "reproduction"])
def test_a_dirty_tree_refuses_both_modes(tmp_path: Path, mode: GateMode) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    _commit(repo, AFTER_THE_SEAL, "the sealed log")
    (repo / "docs" / "MODEL_CARD.md").write_text("edited\n", encoding="utf-8")
    with pytest.raises(FreezeError, match="dirty"):
        _gate(repo, mode=mode)


@pytest.mark.rule("R41")
def test_a_reproduction_still_checks_the_recorded_hashes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    _commit(repo, AFTER_THE_SEAL, "the sealed log")
    _tamper(repo, "models", "models/heartbeat-v1/model.onnx")
    with pytest.raises(FreezeError, match=r"model\.onnx"):
        _gate(repo, mode="reproduction")


def test_an_unknown_mode_refuses(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _freeze(repo)
    with pytest.raises(FreezeError, match="mode"):
        _gate(repo, mode="rehearsal")  # type: ignore[arg-type]
