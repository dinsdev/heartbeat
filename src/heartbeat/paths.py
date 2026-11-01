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

# Gitignored: one folder per run (C6, MODEL-07).
RUNS_DIR = REPO_ROOT / "runs"
# Committed summaries, written only by the rebuild stages (rule 5).
RESULTS_DIR = REPO_ROOT / "results"

# E3: the frozen model, written only by `heartbeat export` (and its freeze
# record only by `heartbeat export --freeze`, Din's, Phase 7).
MODELS_DIR = REPO_ROOT / "models" / "heartbeat-v1"
FREEZE_RECORD = MODELS_DIR / "freeze.json"
# E5, PARITY-02: DS1 parity fixtures, written only by `heartbeat export`.
FIXTURES_DIR = REPO_ROOT / "fixtures" / "parity"
# C6, EVAL-06: the append-only sealed-run log and its reports (R42).
TEST_LOG = RESULTS_DIR / "test_runs.jsonl"
TEST_REPORTS_DIR = RESULTS_DIR / "test_runs"

# F6: the cards whose generated blocks `heartbeat cards` renders (R50).
MODEL_CARD = REPO_ROOT / "docs" / "MODEL_CARD.md"
DATA_CARD = REPO_ROOT / "docs" / "DATA_CARD.md"
