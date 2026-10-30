"""The freeze record and the sealed-run gate (C1, C6; EVAL-05, R41, R47).

`write_freeze` (`heartbeat export --freeze`, Din's, Phase 7) records the
commit, the hashes of the config, the fold pin and the lockfile, the hash of
every model file, and the date. It refuses on a dirty tree, when a record
exists, or when a model file differs from `results/export.json`.

`check_gate` is what `evaluate-test` runs before it reads anything: a clean
tree; a record that parses; nothing changed since the recorded commit except
the record itself; every recorded hash matching the files; and (R47) the
recorded commit on `origin/main`.
"""

import hashlib
import json
import subprocess
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from heartbeat.export.bundle import FREEZE_NAME, bundle_files
from heartbeat.runs import canonical_json, write_text_atomic

# Design call 5: the inputs a frozen model depends on besides its own files.
FROZEN_INPUTS = ("config/default.toml", "manifests/folds.sha256", "uv.lock")
REMOTE_REF = "origin/main"

FREEZE_LABEL = (
    "freeze record: written by `heartbeat export --freeze` before the sealed "
    "run; evaluate-test refuses unless the tree matches it (EVAL-05)"
)


class FreezeError(RuntimeError):
    """The freeze record is missing, stale, or the tree does not match it."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_clean(repo: Path) -> None:
    status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if status.returncode != 0:
        raise FreezeError(f"git status failed: {status.stderr.strip()}")
    if status.stdout.strip():
        changed = [line[3:] for line in status.stdout.splitlines()]
        raise FreezeError(f"the tree is dirty: {changed}; commit or stash first")


def _record_path(repo: Path, models_dir: Path) -> str:
    return (models_dir / FREEZE_NAME).relative_to(repo).as_posix()


def write_freeze(
    repo: Path, models_dir: Path, export_record: Mapping[str, Any], today: date
) -> Path:
    """Write `<models_dir>/freeze.json` for the current HEAD.

    Raises:
        FreezeError: On a dirty tree, an existing record, or model files that
            differ from `results/export.json`.
    """
    _require_clean(repo)
    path = models_dir / FREEZE_NAME
    if path.exists():
        raise FreezeError(f"{path} exists; a model is frozen once")
    files = bundle_files(models_dir, repo)
    if files != list(export_record["files"]):
        raise FreezeError(
            "the model files differ from results/export.json; rerun "
            "`uv run heartbeat rebuild` and commit its outputs first"
        )
    record = {
        "label": FREEZE_LABEL,
        "commit": _git(repo, "rev-parse", "HEAD").stdout.strip(),
        "date": today.isoformat(),
        "inputs": {name: _sha256(repo / name) for name in FROZEN_INPUTS},
        "models": {f["path"]: f["sha256"] for f in files},
    }
    write_text_atomic(path, canonical_json(record))
    return path


def check_gate(
    repo: Path, models_dir: Path, require_remote: bool = True
) -> dict[str, Any]:
    """Refuse unless the tree is exactly the frozen one plus its record.

    Returns:
        `{"record": <the record>, "sha256": <the record file's SHA256>}`.

    Raises:
        FreezeError: Naming the first cause found.
    """
    _require_clean(repo)
    path = models_dir / FREEZE_NAME
    if not path.is_file():
        raise FreezeError(
            f"no freeze record at {path}; Din writes it with "
            "`uv run heartbeat export --freeze` (Phase 7)"
        )
    try:
        record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        commit = str(record["commit"])
        inputs = dict(record["inputs"])
        models = dict(record["models"])
    except (ValueError, KeyError, TypeError) as error:
        raise FreezeError(f"cannot parse {path}: {error}") from error
    if _git(repo, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        raise FreezeError(f"freeze commit {commit} is not in this repository")
    diff = _git(repo, "diff", "--name-only", commit, "HEAD")
    changed = sorted(diff.stdout.split())
    if diff.returncode != 0 or changed != [_record_path(repo, models_dir)]:
        others = [c for c in changed if c != _record_path(repo, models_dir)]
        raise FreezeError(
            f"changed since the freeze commit {commit[:12]} besides the record: "
            f"{others or changed}"
        )
    if sorted(inputs) != sorted(FROZEN_INPUTS):
        raise FreezeError(f"the record's inputs are {sorted(inputs)}")
    for name, expected in sorted(inputs.items()):
        if _sha256(repo / name) != expected:
            raise FreezeError(f"{name} differs from the freeze record")
    files = {f["path"]: f["sha256"] for f in bundle_files(models_dir, repo)}
    if sorted(files) != sorted(models):
        raise FreezeError(
            f"model files {sorted(files)} differ from the record's {sorted(models)}"
        )
    for name, expected in sorted(models.items()):
        if files[name] != expected:
            raise FreezeError(f"{name} differs from the freeze record")
    if require_remote:
        # R47: pushed before the sealed run (Din fetches first).
        on_remote = _git(repo, "merge-base", "--is-ancestor", commit, REMOTE_REF)
        if on_remote.returncode != 0:
            raise FreezeError(
                f"freeze commit {commit[:12]} is not on {REMOTE_REF}; push and "
                "fetch it before the sealed run (R47)"
            )
    return {"record": record, "sha256": _sha256(path)}
