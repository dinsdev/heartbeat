"""Tests for guard.py. Run: uv run pytest .claude/hooks.

Each case runs the hook as Claude Code does: JSON on stdin, exit 2 blocks.
GUARD_PYTHON picks the interpreter that runs the hook, so the same cases
check the macOS `/usr/bin/python3` (3.9). Skip markers are built by
concatenation so this file never trips the guard.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).with_name("guard.py")
REPO = GUARD.parents[2]
PYTHON = os.environ.get("GUARD_PYTHON", sys.executable)


def run_guard(stdin: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO)}
    return subprocess.run(
        [PYTHON, str(GUARD)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def run(
    tool_name: str, tool_input: dict[str, object], cwd: Path = REPO
) -> subprocess.CompletedProcess[str]:
    event = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
    }
    return run_guard(json.dumps(event))


BLOCKED = [
    # evaluate-test in any spelling (rule 1)
    "uv run heartbeat evaluate-test",
    "uv run --frozen heartbeat evaluate-test --seeds 0,1,2",
    "cd src && uv run python -m heartbeat evaluate-test",
    ".venv/bin/heartbeat evaluate-test",
    "sh -c 'uv run heartbeat evaluate-test'",
    "echo $(uv run heartbeat evaluate-test)",
    # pushes, in every spelling
    "git push",
    "git push origin main",
    "cd web && git push",
    "timeout 60 git push",
    "git -C . push origin main",
    "git -c push.default=current push",
    "/usr/bin/git push",
    "bash -c 'git push origin main'",
    "env GIT_TRACE=1 git push",
    "xargs git push < /dev/null",
    "echo $(git push)",
    "uv run git push",
    # the rest of Din's list
    "git remote add origin git@github.com:dinsdev/heartbeat.git",
    "gh repo create dinsdev/heartbeat --public",
    "gh pr create --fill",
    "gh -R dinsdev/heartbeat pr merge 3 --merge",
    "gh secret set CLOUDFLARE_API_TOKEN",
    "gh workflow run deploy.yml",
    "pnpm -C web exec wrangler deploy",
    "npx wrangler versions upload",
    "wrangler preview --name pr-3",
    "pnpm -C web exec wrangler preview delete --name pr-3",
    "npx wrangler rollback",
    "wrangler delete --name heartbeat",
    "pnpm -C web run deploy",
    "uv run heartbeat make-folds",
    "uv run heartbeat rebuild --exact",
    # discarding uncommitted work
    "git clean -fdx",
    "git reset --hard HEAD",
    "git checkout -- src/heartbeat/cli.py",
    "git restore src/heartbeat/cli.py",
    "git stash drop",
    # shell writes to protected paths (rules 4 and 5)
    "echo '{}' >> results/test_runs.jsonl",
    "cat > config/folds.json <<'EOF'\n{\"folds\": []}\nEOF",
    "printf x | tee results/metrics.json",
    "rm -rf results/",
    "mv manifests/splits.toml /tmp/",
    "cp /tmp/x.toml manifests/splits.toml",
    "sed -i '' 's/100/101/' manifests/splits.toml",
    "python3 -c \"open('results/test_runs.jsonl', 'w')\"",
    "git checkout HEAD~1 -- config/folds.json",
    "git restore results/test_runs.jsonl",
    "find results -name '*.json' -delete",
    "truncate -s 0 results/test_runs.jsonl",
    "touch models/heartbeat-v1/freeze.json",
    "echo x > .claude/settings.json",
    f"echo x > {REPO}/results/test_runs.jsonl",
    "cd results && rm test_runs.jsonl",
]

ALLOWED = [
    "git status && git log --oneline -5",
    "git switch -c phase-1-skeleton",
    "git checkout -b phase-1-skeleton",
    "git restore --staged src/heartbeat/cli.py",
    "git stash && git stash pop",
    "git reset HEAD~1",
    "git merge --no-ff phase-1-skeleton",
    "gh pr view 3",
    "gh run list",
    "git commit -m 'Update results/ docs'",
    "git add results/ manifests/ && git commit -m wip",
    "git diff config/folds.json",
    "cat results/test_runs.jsonl",
    "wc -l results/test_runs.jsonl 2>/dev/null",
    "cp results/metrics.json /tmp/metrics.json",
    "grep -rn evaluate-test docs/",
    "uv run pytest tests/unit -k evaluate_test",
    "uv run heartbeat rebuild",
    "uv run heartbeat rebuild --from cross-validate",
    "uv run heartbeat verify",
    "pnpm -C web build",
    "wrangler whoami",
    "pnpm -C web exec wrangler types",
    "ls -la .claude",
    "git commit -F - <<'EOF'\nLock F5: Din's settings\n\nrm results/ in a message\nEOF",
    "echo 'it'\\''s fine' > /tmp/x",
    "git log --grep push",
    "python3 -c \"import json; json.load(open('.claude/settings.json'))\"",
    "uv run python -c \"print(open('results/metrics.json').read())\"",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_bash_blocked(command: str) -> None:
    result = run("Bash", {"command": command})
    assert result.returncode == 2, result.stderr
    assert "Blocked" in result.stderr


@pytest.mark.parametrize("command", ALLOWED)
def test_bash_allowed(command: str) -> None:
    result = run("Bash", {"command": command})
    assert result.returncode == 0, result.stderr


def test_cwd_inside_protected_dir() -> None:
    result = run("Bash", {"command": "rm test_runs.jsonl"}, cwd=REPO / "results")
    assert result.returncode == 2, result.stderr


SKIP = "pytest.mark." + "skip"
XFAIL = "pytest.mark." + "xfail"


@pytest.mark.parametrize(
    "marker", [f"@{SKIP}\n", f"@{XFAIL}(strict=True)\n", "pytest." + "skip('later')"]
)
def test_edit_adding_a_python_skip_is_blocked(marker: str) -> None:
    result = run(
        "Edit",
        {
            "file_path": f"{REPO}/tests/unit/test_split.py",
            "old_string": "def test_a():",
            "new_string": f"{marker}def test_a():",
        },
    )
    assert result.returncode == 2, result.stderr


@pytest.mark.parametrize(
    "marker", ["it." + "skip", "test." + "only", "test.describe." + "skip"]
)
def test_edit_adding_a_ts_skip_or_only_is_blocked(marker: str) -> None:
    result = run(
        "Edit",
        {
            "file_path": f"{REPO}/web/src/trace.test.ts",
            "old_string": "it('R29: x'",
            "new_string": f"{marker}('R29: x'",
        },
    )
    assert result.returncode == 2, result.stderr


def test_write_new_test_file_with_skip_is_blocked() -> None:
    result = run(
        "Write",
        {
            "file_path": f"{REPO}/tests/unit/test_new.py",
            "content": f"import pytest\n@{SKIP}\ndef test_x(): ...",
        },
    )
    assert result.returncode == 2, result.stderr


def test_write_keeping_an_existing_marker_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "tests" / "test_old.py"
    path.parent.mkdir()
    path.write_text(f"@{SKIP}\ndef test_x(): ...\n")
    result = run(
        "Write",
        {
            "file_path": str(path),
            "content": f"@{SKIP}\ndef test_x(): ...\ndef test_y(): ...\n",
        },
    )
    assert result.returncode == 0, result.stderr


def test_ordinary_test_edit_is_allowed() -> None:
    result = run(
        "Edit",
        {
            "file_path": f"{REPO}/tests/unit/test_split.py",
            "old_string": "assert a",
            "new_string": "assert a == b\n@pytest.mark.rule('R12')",
        },
    )
    assert result.returncode == 0, result.stderr


def test_non_test_file_is_ignored() -> None:
    result = run(
        "Edit",
        {
            "file_path": f"{REPO}/docs/CONVENTIONS.md",
            "old_string": "a",
            "new_string": f"never use {SKIP}",
        },
    )
    assert result.returncode == 0, result.stderr


def test_bad_input_blocks() -> None:
    result = run_guard("not json")
    assert result.returncode == 2
    assert "failed" in result.stderr


def test_other_tools_pass() -> None:
    result = run("Read", {"file_path": f"{REPO}/results/test_runs.jsonl"})
    assert result.returncode == 0, result.stderr
