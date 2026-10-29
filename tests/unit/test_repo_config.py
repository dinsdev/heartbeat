"""R45 (the 14-day rule in config and CI) and R46 (actions pinned to commits).

Also the repo-level rule-coverage test (Task 1.7), which needs R45 and R46.
"""

import json
import shutil
import textwrap
from pathlib import Path

import pytest

from heartbeat.checks.repo_config import check_action_pins, check_release_age, main
from heartbeat.checks.rule_coverage import (
    collect_rule_ids,
    current_phase,
    parse_rule_table,
    uncovered,
)
from heartbeat.paths import PLAN_MD, PYPROJECT, REPO_ROOT

CONFIG_FILES = (
    "pyproject.toml",
    "uv.lock",
    "web/pnpm-workspace.yaml",
    "renovate.json",
    ".github/workflows/ci.yml",
)
SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A temporary copy of the real config files."""
    for name in CONFIG_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, target)
    return tmp_path


def edit(root: Path, name: str, old: str, new: str) -> None:
    path = root / name
    text = path.read_text()
    assert old in text, f"{old!r} not in {name}"
    path.write_text(text.replace(old, new))


def edit_renovate(root: Path, **changes: object) -> None:
    path = root / "renovate.json"
    config = json.loads(path.read_text())
    for key, value in changes.items():
        if value is None:
            config.pop(key, None)
        else:
            config[key] = value
    path.write_text(json.dumps(config))


# R45: the real repo passes


@pytest.mark.rule("R45")
def test_release_age_passes_on_the_repo() -> None:
    assert check_release_age(REPO_ROOT) == []


@pytest.mark.rule("R45")
def test_release_age_passes_on_an_unchanged_copy(repo: Path) -> None:
    assert check_release_age(repo) == []


# R45: each broken copy fails


@pytest.mark.rule("R45")
@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        ("pyproject.toml", 'exclude-newer = "14 days"', 'exclude-newer = "7 days"'),
        ("pyproject.toml", 'exclude-newer = "14 days"', ""),
        ("uv.lock", 'exclude-newer-span = "P14D"', 'exclude-newer-span = "P7D"'),
        ("uv.lock", 'exclude-newer-span = "P14D"', ""),
        (
            "web/pnpm-workspace.yaml",
            "minimumReleaseAge: 20160",
            "minimumReleaseAge: 1440",
        ),
        ("web/pnpm-workspace.yaml", "minimumReleaseAge: 20160", ""),
        (
            "web/pnpm-workspace.yaml",
            "minimumReleaseAgeIgnoreMissingTime: false",
            "minimumReleaseAgeIgnoreMissingTime: true",
        ),
        (
            "web/pnpm-workspace.yaml",
            "protobufjs: false",
            "protobufjs: true",
        ),
        (
            "web/pnpm-workspace.yaml",
            "  workerd: true\n",
            "  workerd: true\n  sharp: true\n",
        ),
        (
            "web/pnpm-workspace.yaml",
            "allowBuilds:",
            "dangerouslyAllowAllBuilds: true\nallowBuilds:",
        ),
        (".github/workflows/ci.yml", "uv sync --frozen", "uv sync"),
        (
            ".github/workflows/ci.yml",
            "pnpm -C web install --frozen-lockfile",
            "pnpm -C web install",
        ),
        (
            ".github/workflows/ci.yml",
            "pnpm -C web install --frozen-lockfile",
            "pnpm --dir web i",
        ),
        (".github/workflows/ci.yml", "uv sync --frozen", "echo no install"),
        (".github/workflows/ci.yml", 'UV_FROZEN: "1"', 'UV_FROZEN: "0"'),
    ],
)
def test_release_age_fails_when_broken(
    repo: Path, name: str, old: str, new: str
) -> None:
    edit(repo, name, old, new)
    assert check_release_age(repo) != []


@pytest.mark.rule("R45")
@pytest.mark.parametrize(
    "changes",
    [
        {"minimumReleaseAge": "3 days"},
        {"minimumReleaseAge": None},
        {"internalChecksFilter": "none"},
        {"minimumReleaseAgeBehaviour": "timestamp-optional"},
        {"automerge": True},
        {"packageRules": [{"matchManagers": ["npm"], "minimumReleaseAge": "1 day"}]},
        {"packageRules": [{"matchManagers": ["pep621"], "automerge": True}]},
        {"lockFileMaintenance": {"enabled": True, "automerge": True}},
    ],
)
def test_release_age_fails_on_a_broken_renovate_config(
    repo: Path, changes: dict[str, object]
) -> None:
    edit_renovate(repo, **changes)
    assert check_release_age(repo) != []


@pytest.mark.rule("R45")
def test_release_age_fails_when_a_file_is_missing(repo: Path) -> None:
    (repo / "renovate.json").unlink()
    assert any("renovate.json" in problem for problem in check_release_age(repo))


# R46: action pins


def workflow(root: Path, *uses: str) -> Path:
    steps = "".join(f"      - uses: {value}\n" for value in uses)
    path = root / ".github" / "workflows" / "x.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(
            """\
            name: x
            on: push
            jobs:
              a:
                runs-on: ubuntu-24.04
                steps:
            """
        )
        + steps
    )
    return path


@pytest.mark.rule("R46")
@pytest.mark.parametrize(
    "uses",
    [
        "actions/checkout@v5",
        '"actions/checkout@v5"',
        "'actions/checkout@v5' # v5.0.0",
        "actions/checkout@3d3c42e # v7.0.1",
        f"actions/checkout@{SHA.upper()} # v7.0.1",
        f"actions/checkout@{SHA}",
        "actions/checkout",
        "docker://alpine:3.20",
        "docker://alpine",
        "owner/repo/.github/workflows/x.yml@main",
    ],
)
def test_unpinned_action_is_rejected(tmp_path: Path, uses: str) -> None:
    workflow(tmp_path, uses)
    assert len(check_action_pins(tmp_path)) == 1


@pytest.mark.rule("R46")
@pytest.mark.parametrize(
    "uses",
    [
        f"actions/checkout@{SHA} # v7.0.1",
        f'"actions/checkout@{SHA}" # v7.0.1',
        f"owner/repo/.github/workflows/x.yml@{SHA} # v1.2.3",
        "./local-action",
        "./.github/actions/setup",
        "docker://alpine@sha256:" + "a" * 64,
    ],
)
def test_pinned_action_is_accepted(tmp_path: Path, uses: str) -> None:
    workflow(tmp_path, uses)
    assert check_action_pins(tmp_path) == []


@pytest.mark.rule("R46")
def test_job_level_reusable_workflow_is_checked(tmp_path: Path) -> None:
    path = tmp_path / ".github" / "workflows" / "x.yml"
    path.parent.mkdir(parents=True)
    path.write_text("jobs:\n  a:\n    uses: owner/repo/.github/workflows/x.yml@v1\n")
    assert len(check_action_pins(tmp_path)) == 1


@pytest.mark.rule("R46")
def test_action_pins_pass_on_the_repo() -> None:
    assert check_action_pins(REPO_ROOT) == []


@pytest.mark.rule("R46")
def test_repo_has_a_workflow_to_check() -> None:
    assert list((REPO_ROOT / ".github" / "workflows").glob("*.yml"))


# Command line


@pytest.mark.rule("R45")
def test_main_reports_problems(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo)]) == 0
    edit(repo, ".github/workflows/ci.yml", "uv sync --frozen", "uv sync")
    workflow(repo, "actions/checkout@v5")
    assert main(["--root", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "uv sync" in out
    assert "actions/checkout@v5" in out


# Task 1.7: the repo-level rule-coverage check


def test_every_row_due_by_the_current_phase_has_a_test() -> None:
    rows = parse_rule_table(PLAN_MD.read_text())
    phase = current_phase(PYPROJECT)
    assert uncovered(rows, collect_rule_ids(REPO_ROOT), phase) == []
