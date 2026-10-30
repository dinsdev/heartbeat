"""Paths resolved from the repo root (CONVENTIONS section 2)."""

from pathlib import Path

# src/heartbeat/paths.py, two levels below the root.
REPO_ROOT = Path(__file__).resolve().parents[2]

PYPROJECT = REPO_ROOT / "pyproject.toml"
PLAN_MD = REPO_ROOT / "docs" / "PLAN.md"
UV_LOCK = REPO_ROOT / "uv.lock"
PACKAGE_DIR = REPO_ROOT / "src" / "heartbeat"

CONFIG_DIR = REPO_ROOT / "config"
DEFAULT_CONFIG = CONFIG_DIR / "default.toml"
# Written only by `heartbeat make-folds` (rule 4).
FOLDS_JSON = CONFIG_DIR / "folds.json"

MANIFESTS_DIR = REPO_ROOT / "manifests"
CHECKSUM_MANIFEST = MANIFESTS_DIR / "mitdb-1.0.0.sha256"
SPLITS_MANIFEST = MANIFESTS_DIR / "splits.toml"
SUBJECTS_MANIFEST = MANIFESTS_DIR / "subjects.toml"
BEAT_COUNTS_MANIFEST = MANIFESTS_DIR / "mitdb-beat-counts.toml"
# Phase 2 settling 5: the SHA256 of config/folds.json, pinned with Din's go.
FOLDS_PIN = MANIFESTS_DIR / "folds.sha256"

# Gitignored: rebuild stage state (E4).
STAGES_DIR = REPO_ROOT / "data" / "stages"
