"""Rule 5, design call 7: committed results came from a clean tree on this history."""

import json
import subprocess
from pathlib import Path

from run_support import git, make_repo

from heartbeat.paths import REPO_ROOT

# The sealed-run log is append-only and has its own checks (R42, Phase 5).
NOT_SUMMARIES = {"results/test_runs.jsonl"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


def problems(repo: Path) -> list[str]:
    """Every way a results file committed at HEAD breaks the rule."""
    listed = _git(repo, "ls-tree", "-r", "--name-only", "HEAD", "results").stdout
    found: list[str] = []
    for path in sorted(listed.split()):
        if not path.endswith(".json") or path in NOT_SUMMARIES:
            continue
        payload = json.loads(_git(repo, "show", f"HEAD:{path}").stdout)
        if payload.get("dirty") is not False:
            found.append(f"{path}: written from a dirty tree")
        commit = str(payload.get("commit"))
        if _git(repo, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
            found.append(f"{path}: commit {commit} not in this clone (shallow?)")
        elif _git(repo, "merge-base", "--is-ancestor", commit, "HEAD").returncode:
            found.append(f"{path}: commit {commit} is not an ancestor of HEAD")
        if not payload.get("run"):
            found.append(f"{path}: no run folder named")
    return found


def test_every_committed_result_is_clean_and_on_head_history() -> None:
    assert problems(REPO_ROOT) == []


def _commit_result(repo: Path, payload: dict[str, object]) -> None:
    (repo / "results").mkdir(exist_ok=True)
    (repo / "results" / "cv.json").write_text(json.dumps(payload), encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "result")


def test_a_clean_result_on_history_passes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    _commit_result(repo, {"dirty": False, "commit": head, "run": "r1"})
    assert problems(repo) == []


def test_a_dirty_result_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    _commit_result(repo, {"dirty": True, "commit": head, "run": "r1"})
    assert problems(repo) == ["results/cv.json: written from a dirty tree"]


def test_a_result_from_another_history_fails(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    git(repo, "switch", "-q", "-c", "side")
    (repo / "side.py").write_text("s = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "side")
    side = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-q", "main")
    _commit_result(repo, {"dirty": False, "commit": side, "run": "r1"})
    assert problems(repo) == [
        f"results/cv.json: commit {side} is not an ancestor of HEAD"
    ]
    _commit_result(repo, {"dirty": False, "commit": "0" * 40, "run": "r1"})
    assert "not in this clone" in problems(repo)[0]
