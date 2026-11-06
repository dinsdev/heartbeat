"""Production refuses a commit whose CI did not pass (OPS-06, design call 7)."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from heartbeat.paths import REPO_ROOT

GATE = REPO_ROOT / "scripts" / "require_ci_passed.sh"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
WRANGLER = REPO_ROOT / "web" / "wrangler.jsonc"
SHA = "0123456789abcdef0123456789abcdef01234567"
EXPECTED_ARGS = (
    "run list --workflow ci.yml --branch main --event push "
    f"--commit {SHA} --status success --json databaseId --jq length"
)


def run_gate(
    tmp_path: Path, gh_body: str, *, sha: str = SHA
) -> subprocess.CompletedProcess[str]:
    """The gate with a fake `gh` first on PATH, which logs its arguments."""
    fake = tmp_path / "gh"
    fake.write_text(
        f'#!/bin/sh\necho "$*" > "{tmp_path}/args"\n{gh_body}\n', encoding="utf-8"
    )
    fake.chmod(0o755)
    env = {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "GITHUB_SHA": sha}
    return subprocess.run(
        [str(GATE)], capture_output=True, text=True, check=False, env=env
    )


def test_a_successful_run_passes(tmp_path: Path) -> None:
    result = run_gate(tmp_path, "echo 1")
    assert result.returncode == 0, result.stderr
    assert SHA in result.stdout


def test_the_gate_asks_only_about_this_commits_push_run_on_main(tmp_path: Path) -> None:
    # Another workflow, a pull request's run or a failed attempt never counts,
    # because the query itself rules them out.
    run_gate(tmp_path, "echo 1")
    assert (tmp_path / "args").read_text(encoding="utf-8").strip() == EXPECTED_ARGS


@pytest.mark.parametrize(
    ("name", "gh_body"),
    [
        ("no run", "echo 0"),
        ("gh fails", "echo 'HTTP 403' >&2; exit 1"),
        ("gh fails after printing a count", "echo 1; exit 1"),
        ("gh prints nothing", "exit 0"),
        ("gh prints something else", "echo '[]'"),
        ("gh prints a negative", "echo -1"),
    ],
)
def test_anything_else_refuses(tmp_path: Path, name: str, gh_body: str) -> None:
    result = run_gate(tmp_path, gh_body)
    assert result.returncode != 0, name
    assert "Refusing to deploy" in result.stderr, name


def test_no_commit_refuses_before_asking(tmp_path: Path) -> None:
    result = run_gate(tmp_path, "echo 1", sha="")
    assert result.returncode != 0
    assert not (tmp_path / "args").exists()


def production_job() -> str:
    text = DEPLOY.read_text(encoding="utf-8")
    match = re.search(r"^  production:\n((?:    .*\n|\n)+)", text, re.M)
    assert match is not None
    return match.group(1)


def test_the_gate_is_the_first_step_after_checkout() -> None:
    job = production_job()
    steps = re.findall(r"^      - (.+)$", job, re.M)
    assert steps[0].startswith("uses: actions/checkout@")
    assert steps[1] == "name: Refuse a commit whose CI did not pass"
    assert job.index("run: scripts/require_ci_passed.sh") < job.index("wrangler deploy")


def test_the_job_can_read_actions_and_nothing_more() -> None:
    job = production_job()
    match = re.search(r"^    permissions:\n((?:      .*\n)+)", job, re.M)
    assert match is not None
    assert match.group(1).split() == ["contents:", "read", "actions:", "read"]
    assert "GH_TOKEN: ${{ github.token }}" in job


def test_the_gate_is_executable() -> None:
    assert os.access(GATE, os.X_OK)


def test_wrangler_keeps_no_route() -> None:
    # Phase 8 settling 9: the domain is attached in the dashboard.
    text = re.sub(r"//.*", "", WRANGLER.read_text(encoding="utf-8"))
    assert not re.search(r'"routes?"\s*:', text)
