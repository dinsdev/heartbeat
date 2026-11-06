#!/usr/bin/env bash
# OPS-06, Phase 8 settling 4: production refuses a commit whose CI did not pass.
# Passes only when `gh` reports a successful ci.yml run for this exact commit,
# from a push to main. A pull request's run, another workflow, a failed run and
# any failure of `gh` itself all refuse.
set -euo pipefail

if [[ -z "${GITHUB_SHA:-}" ]]; then
  echo "Refusing to deploy: GITHUB_SHA is not set." >&2
  exit 1
fi

if ! count="$(gh run list --workflow ci.yml --branch main --event push \
  --commit "$GITHUB_SHA" --status success --json databaseId --jq length)"; then
  echo "Refusing to deploy: gh could not read CI for $GITHUB_SHA." >&2
  exit 1
fi

if ! [[ "$count" =~ ^[0-9]+$ ]] || ((count == 0)); then
  echo "Refusing to deploy: no successful ci.yml push run on main for $GITHUB_SHA (gh said: '$count')." >&2
  exit 1
fi

echo "CI passed for $GITHUB_SHA ($count successful run or runs)."
