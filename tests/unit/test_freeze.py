"""EVAL-05, R41 (and R47, built now): the freeze record and the sealed-run gate."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from run_support import git

from heartbeat.export.bundle import bundle_files
from heartbeat.export.freeze import FreezeError, check_gate, write_freeze

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


def _gate(repo: Path, remote: bool = False) -> dict[str, Any]:
    return check_gate(repo, repo / "models" / "heartbeat-v1", require_remote=remote)


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
