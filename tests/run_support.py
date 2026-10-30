"""Temporary git repos and settings for the run-folder and results tests."""

import subprocess
from pathlib import Path

from heartbeat.config import DataSettings, FoldSettings, Settings


def git(repo: Path, *args: str) -> str:
    """Run git in `repo` with a throwaway identity and return its output."""
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    """A one-commit repo with `uv.lock`, `config/folds.json` and ignored runs."""
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / ".gitignore").write_text("/runs/\n", encoding="utf-8")
    (repo / "uv.lock").write_text("lock\n", encoding="utf-8")
    (repo / "config" / "folds.json").write_text("{}\n", encoding="utf-8")
    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    return repo


def settings(tmp_path: Path) -> Settings:
    """Settings with data folders under `tmp_path`."""
    return Settings(
        data=DataSettings(
            raw_dir=tmp_path / "raw",
            prepared_dir=tmp_path / "prepared",
            sources=("https://a.example/",),
        ),
        folds=FoldSettings(seed=7),
    )
