#!/usr/bin/env bash
# Lint and unit tests for both toolchains, under 2 minutes. Run before every
# commit. CI runs these plus the web build and Playwright.
set -euo pipefail

cd "$(dirname "$0")/.."

# --locked fails on a stale uv.lock instead of quietly re-locking.
uv run --locked ruff check
uv run --locked ruff format --check
uv run --locked mypy
# Includes the guard hook tests, the wording lint, rule coverage, R45 and R46.
uv run --locked pytest -q -m "not realdata"

pnpm -C web run lint
pnpm -C web run format:check
pnpm -C web run check
pnpm -C web run test
