"""The freeze record and the sealed-run gate (C1, C6; EVAL-05, R41, R47).

`write_freeze` (`heartbeat export --freeze`, Din's, Phase 7) records the
commit, the hashes of the config, the fold pin and the lockfile, the hash of
every model file, and the date. It refuses on a dirty tree, when a record
exists, or when a model file differs from `results/export.json`.

`check_gate` is what `evaluate-test` and `reproduce-test` run before they read
anything: a clean tree; a record that parses; every recorded hash matching the
files; and (R47) the recorded commit on `origin/main`. Since the recorded
commit, a sealed run allows nothing to change but the record itself; a
reproduction allows anything outside `FROZEN_PATHS`, so the sealed log, its
report, the cards and docs may land first (Phase 7 settling 1).
"""

import hashlib
import json
import subprocess
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Literal, get_args

from heartbeat.export.bundle import FREEZE_NAME, bundle_files
from heartbeat.runs import canonical_json, write_text_atomic

# Design call 5: the inputs a frozen model depends on besides its own files.
FROZEN_INPUTS = ("config/default.toml", "manifests/folds.sha256", "uv.lock")
REMOTE_REF = "origin/main"

# Phase 7 settling 1, design call 1: what a reproduction requires unchanged
# since the freeze commit (the record aside). A trailing slash is a folder.
FROZEN_PATHS = (
    "src/",
    "config/",
    "manifests/",
    "models/heartbeat-v1/",
    "pyproject.toml",
    "uv.lock",
)

GateMode = Literal["sealed", "reproduction"]

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


def is_frozen(path: str) -> bool:
    """Whether a repo-relative POSIX path is under `FROZEN_PATHS`."""
    return any(
        path.startswith(frozen) if frozen.endswith("/") else path == frozen
        for frozen in FROZEN_PATHS
    )


def _changed_since(repo: Path, commit: str) -> list[str]:
    """Every path changed from `commit` to HEAD, both sides of a rename."""
    diff = _git(repo, "diff", "--name-only", "--no-renames", "-z", commit, "HEAD")
    if diff.returncode != 0:
        raise FreezeError(f"git diff from {commit[:12]} failed: {diff.stderr.strip()}")
    return sorted(name for name in diff.stdout.split("\0") if name)


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
    repo: Path, models_dir: Path, mode: GateMode, require_remote: bool = True
) -> dict[str, Any]:
    """Refuse unless the tree matches the freeze record for this mode.

    Args:
        repo: The git checkout.
        models_dir: The bundle holding the record.
        mode: "sealed" allows only the record to change since the freeze
            commit; "reproduction" allows changes outside `FROZEN_PATHS`.
        require_remote: R47's `origin/main` check.

    Returns:
        `{"record": <the record>, "sha256": <the record file's SHA256>}`.

    Raises:
        FreezeError: Naming the first cause found.
    """
    if mode not in get_args(GateMode):
        raise FreezeError(f"unknown gate mode {mode!r}")
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
    record_path = _record_path(repo, models_dir)
    changed = _changed_since(repo, commit)
    if record_path not in changed:
        raise FreezeError(
            f"the record is not committed after the freeze commit {commit[:12]}"
        )
    others = [c for c in changed if c != record_path]
    if mode == "reproduction":
        others = [c for c in others if is_frozen(c)]
    if others:
        allowed = "besides the record" if mode == "sealed" else "under a frozen path"
        raise FreezeError(
            f"changed since the freeze commit {commit[:12]} {allowed} ({mode}): "
            f"{others}"
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
