"""Paths resolved from the repo root (CONVENTIONS section 2)."""

from pathlib import Path

# src/heartbeat/paths.py, two levels below the root.
REPO_ROOT = Path(__file__).resolve().parents[2]

PYPROJECT = REPO_ROOT / "pyproject.toml"
PLAN_MD = REPO_ROOT / "docs" / "PLAN.md"
