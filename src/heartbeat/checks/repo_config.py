"""R45 (the 14-day rule), R46 (actions pinned to commits) and the deploy checks.

The deploy checks cover OPS-06 and Phase 6 design call 19. Each check returns a
list of problems; an empty list is a pass. The YAML files are read with a few
line patterns rather than a YAML library: the workflow and `pnpm-workspace.yaml`
shapes are ours, and a pattern that finds nothing fails.

Run as `python -m heartbeat.checks.repo_config [--root DIR]`.
"""

import argparse
import json
import re
import shlex
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path

from heartbeat.paths import REPO_ROOT

# E2 as amended 2026-10-29 (Phase 1 settling, 3 of 4).
UV_SPAN = "14 days"
UV_LOCK_SPAN = "P14D"
PNPM_MINUTES = 20160
RENOVATE_AGE = "14 days"
ALLOWED_BUILDS = frozenset({"esbuild", "workerd"})

WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")
ACTION_GLOBS = (".github/actions/**/action.yml", ".github/actions/**/action.yaml")

TOP_LEVEL = re.compile(r"^([A-Za-z][\w-]*):\s*(.*?)\s*$")
CHILD = re.compile(r"^\s+([\w@./-]+):\s*(.*?)\s*$")
RUN_KEY = re.compile(r"^(\s*)(?:-\s+)?run:\s*(.*?)\s*$")
USES_KEY = re.compile(r"^\s*(?:-\s+)?uses:\s*(.+?)\s*$")
SHELL_SPLIT = re.compile(r"&&|\|\||[;|]")

COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
VERSION_COMMENT = re.compile(r"^#\s*v?\d+\.\d+\.\d+\S*$")
DOCKER_DIGEST = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-f]{64}$")
REMOTE_REF = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@(\S+)$")
# pnpm options that take a value before the subcommand.
PNPM_VALUE_OPTIONS = frozenset({"-C", "--dir", "-F", "--filter", "-w"})

DEPLOY_WORKFLOW = ".github/workflows/deploy.yml"
WRANGLER_CONFIG = "web/wrangler.jsonc"
JOB_KEY = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$")
JOB_FIELD = re.compile(r"^    ([\w-]+):\s*(.*?)\s*$")
PERMISSIONS_KEY = re.compile(r"^(\s*)permissions:\s*(.*?)\s*$")
PERMISSION_LEVELS = frozenset({"read", "none"})
# Triggers that run with the repo's secrets on a fork's code.
UNSAFE_TRIGGERS = frozenset({"pull_request_target", "workflow_run"})
DEPLOY_TRIGGERS = frozenset({"workflow_call", "workflow_dispatch"})
PREVIEW_IF = "github.event_name == 'pull_request'"
SAME_REPO_IF = "github.event.pull_request.head.repo.full_name == github.repository"
PRODUCTION_IF = (
    "github.event_name == 'workflow_dispatch'",
    "github.ref == 'refs/heads/main'",
)


def _strip_comment(value: str) -> str:
    return re.sub(r"\s+#.*$", "", value).strip().strip("\"'")


def _yaml_top_level(text: str) -> dict[str, str]:
    """Return top-level `key: value` pairs (values unquoted, comments dropped)."""
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        match = TOP_LEVEL.match(line)
        if match:
            pairs[match.group(1)] = _strip_comment(match.group(2))
    return pairs


def _yaml_block(text: str, key: str) -> dict[str, str] | None:
    """Return the `child: value` pairs under a top-level `key:`, or None."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.rstrip() == f"{key}:":
            block: dict[str, str] = {}
            for child in lines[index + 1 :]:
                if child.strip() == "" or child.lstrip().startswith("#"):
                    continue
                match = CHILD.match(child)
                if not match:
                    break
                block[match.group(1)] = _strip_comment(match.group(2))
            return block
    return None


def _read(root: Path, name: str, problems: list[str]) -> str | None:
    path = root / name
    if not path.is_file():
        problems.append(f"{name}: missing")
        return None
    return path.read_text(encoding="utf-8")


def _check_uv(root: Path, problems: list[str]) -> None:
    text = _read(root, "pyproject.toml", problems)
    if text is not None:
        span = tomllib.loads(text).get("tool", {}).get("uv", {}).get("exclude-newer")
        if span != UV_SPAN:
            problems.append(
                f'pyproject.toml: [tool.uv] exclude-newer must be "{UV_SPAN}"'
            )
    lock = _read(root, "uv.lock", problems)
    if lock is not None:
        options = tomllib.loads(lock).get("options", {})
        if options.get("exclude-newer-span") != UV_LOCK_SPAN:
            problems.append(
                f'uv.lock: [options] exclude-newer-span must be "{UV_LOCK_SPAN}"'
                " (run uv lock)"
            )


def _check_pnpm(root: Path, problems: list[str]) -> None:
    name = "web/pnpm-workspace.yaml"
    text = _read(root, name, problems)
    if text is None:
        return
    top = _yaml_top_level(text)
    if top.get("minimumReleaseAge") != str(PNPM_MINUTES):
        problems.append(f"{name}: minimumReleaseAge must be {PNPM_MINUTES}")
    if top.get("minimumReleaseAgeIgnoreMissingTime") != "false":
        problems.append(f"{name}: minimumReleaseAgeIgnoreMissingTime must be false")
    if top.get("dangerouslyAllowAllBuilds", "false") != "false":
        problems.append(f"{name}: dangerouslyAllowAllBuilds must not be set")
    builds = _yaml_block(text, "allowBuilds")
    if builds is None:
        problems.append(f"{name}: allowBuilds is missing")
        return
    allowed = {package for package, value in builds.items() if value != "false"}
    extra = sorted(allowed - ALLOWED_BUILDS)
    if extra:
        problems.append(
            f"{name}: allowBuilds may allow only esbuild and workerd, not "
            + ", ".join(extra)
        )


def _walk_settings(node: object) -> Iterator[dict[str, object]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_settings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_settings(item)


def _check_renovate(root: Path, problems: list[str]) -> None:
    text = _read(root, "renovate.json", problems)
    if text is None:
        return
    config = json.loads(text)
    required = {
        "minimumReleaseAge": RENOVATE_AGE,
        "internalChecksFilter": "strict",
        "minimumReleaseAgeBehaviour": "timestamp-required",
    }
    for key, value in required.items():
        if config.get(key) != value:
            problems.append(f'renovate.json: {key} must be "{value}"')
    for settings in _walk_settings(config):
        if settings.get("automerge") is True:
            problems.append("renovate.json: automerge must not be enabled")
    for rule in config.get("packageRules", []):
        if "minimumReleaseAge" in rule and rule["minimumReleaseAge"] != RENOVATE_AGE:
            problems.append(
                "renovate.json: a packageRule changes minimumReleaseAge from "
                f'"{RENOVATE_AGE}"'
            )


def _workflow_files(root: Path, globs: Sequence[str]) -> list[Path]:
    return sorted({path for pattern in globs for path in root.glob(pattern)})


def run_commands(text: str) -> list[str]:
    """Return each `run:` step's command lines from a workflow's text."""
    lines = text.splitlines()
    commands: list[str] = []
    for index, line in enumerate(lines):
        match = RUN_KEY.match(line)
        if not match:
            continue
        indent, value = len(match.group(1)), match.group(2)
        if value and value[0] not in "|>":
            commands.append(value.strip("\"'"))
            continue
        for body in lines[index + 1 :]:
            if body.strip() and len(body) - len(body.lstrip()) <= indent:
                break
            if body.strip():
                commands.append(body.strip())
    return commands


def _command_words(command: str) -> Iterator[list[str]]:
    for segment in SHELL_SPLIT.split(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if words:
            yield words


def _subcommand(words: list[str]) -> tuple[str, list[str]]:
    """Return the subcommand after options (skipping option values) and the rest."""
    index = 1
    while index < len(words) and words[index].startswith("-"):
        index += 2 if words[index] in PNPM_VALUE_OPTIONS else 1
    if index >= len(words):
        return "", []
    return words[index], words[index + 1 :]


def _check_ci(root: Path, problems: list[str]) -> None:
    files = _workflow_files(root, WORKFLOW_GLOBS)
    if not files:
        problems.append(".github/workflows: no workflow")
        return
    frozen_uv = frozen_pnpm = False
    for path in files:
        name = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        uses_uv_run = uses_pnpm = synced_uv = installed_pnpm = False
        for command in run_commands(text):
            for words in _command_words(command):
                sub, rest = _subcommand(words)
                if words[0] == "uv" and sub == "sync":
                    if "--frozen" in rest:
                        frozen_uv = synced_uv = True
                    else:
                        problems.append(f"{name}: `{command}` needs --frozen")
                if words[0] == "uv" and sub == "run":
                    uses_uv_run = True
                if words[0] == "pnpm":
                    uses_pnpm = True
                if words[0] == "pnpm" and sub in {"install", "i"}:
                    if "--frozen-lockfile" in rest:
                        frozen_pnpm = installed_pnpm = True
                    else:
                        problems.append(f"{name}: `{command}` needs --frozen-lockfile")
                if words[0] == "pnpm" and sub == "add":
                    problems.append(f"{name}: `{command}` changes the lockfile in CI")
        # Each workflow installs what it runs from the lockfile itself.
        if uses_uv_run and not synced_uv:
            problems.append(
                f"{name}: runs `uv run` but no step runs `uv sync --frozen`"
            )
        if uses_pnpm and not installed_pnpm:
            problems.append(
                f"{name}: runs pnpm but no step runs `pnpm install --frozen-lockfile`"
            )
        env = _yaml_block(text, "env") or {}
        if uses_uv_run and env.get("UV_FROZEN") not in {"1", "true"}:
            problems.append(
                f'{name}: runs `uv run`, so the workflow env needs UV_FROZEN: "1"'
            )
    if not frozen_uv:
        problems.append(".github/workflows: no step runs `uv sync --frozen`")
    if not frozen_pnpm:
        problems.append(
            ".github/workflows: no step runs `pnpm install --frozen-lockfile`"
        )


def check_release_age(root: Path) -> list[str]:
    """R45: the 14-day rule holds in uv, pnpm, Renovate and CI installs.

    Args:
        root: The repo root to check.

    Returns:
        One message per problem; empty means pass.
    """
    problems: list[str] = []
    _check_uv(root, problems)
    _check_pnpm(root, problems)
    _check_renovate(root, problems)
    _check_ci(root, problems)
    return problems


def _pin_problem(value: str) -> str | None:
    """Return why a `uses:` value is not pinned to a commit, or None if it is."""
    quoted = re.match(r"^([\"'])(.*?)\1\s*(.*)$", value)
    if quoted:
        ref, comment = quoted.group(2), quoted.group(3)
    else:
        ref, _, comment = value.partition(" #")
        comment = "#" + comment if comment else ""
    ref, comment = ref.strip(), comment.strip()
    if ref.startswith("./"):
        return None
    if ref.startswith("docker://"):
        return None if DOCKER_DIGEST.match(ref) else "Docker image needs @sha256:"
    remote = REMOTE_REF.match(ref)
    if not remote:
        return "needs @<40-character commit hash>"
    if not COMMIT_SHA.fullmatch(remote.group(1)):
        return "needs a full 40-character lowercase commit hash, not a tag or branch"
    if not VERSION_COMMENT.match(comment):
        return "needs the release version in a comment, for example # v1.2.3"
    return None


def check_action_pins(root: Path) -> list[str]:
    """R46: every third-party action and reusable workflow is pinned to a commit.

    Args:
        root: The repo root to check.

    Returns:
        One message per unpinned `uses:`; empty means pass.
    """
    problems: list[str] = []
    for path in _workflow_files(root, WORKFLOW_GLOBS + ACTION_GLOBS):
        name = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, start=1):
            match = USES_KEY.match(line)
            if match:
                problem = _pin_problem(match.group(1))
                if problem:
                    problems.append(f"{name}:{line_no}: {match.group(1)}: {problem}")
    return problems


def _jobs(text: str) -> dict[str, list[str]]:
    """Return each job's lines under the top-level `jobs:`, by job id."""
    lines = text.splitlines()
    if "jobs:" not in lines:
        return {}
    jobs: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines[lines.index("jobs:") + 1 :]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        match = JOB_KEY.match(line)
        if match:
            current = jobs.setdefault(match.group(1), [])
        elif current is not None:
            current.append(line)
    return jobs


def _job_field(lines: list[str], key: str) -> str:
    for line in lines:
        match = JOB_FIELD.match(line)
        if match and match.group(1) == key:
            return re.sub(r"\s+#.*$", "", match.group(2)).strip()
    return ""


def _triggers(text: str) -> set[str]:
    top = _yaml_top_level(text)
    inline = top.get("on", "")
    if inline:
        return {word.strip() for word in inline.strip("[]").split(",")}
    block = text.splitlines()
    names: set[str] = set()
    if "on:" in block:
        for line in block[block.index("on:") + 1 :]:
            if line and not line[0].isspace():
                break
            match = re.match(r"^  ([\w-]+):", line)
            if match:
                names.add(match.group(1))
    return names


def _permission_problems(name: str, text: str) -> list[str]:
    problems: list[str] = []
    if "permissions" not in _yaml_top_level(text):
        problems.append(f"{name}: needs a top-level permissions block")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = PERMISSIONS_KEY.match(line)
        if not match:
            continue
        indent, value = len(match.group(1)), _strip_comment(match.group(2))
        if value:
            if value != "{}":
                problems.append(f"{name}:{index + 1}: permissions: {value}")
            continue
        for child in lines[index + 1 :]:
            if child.strip() and len(child) - len(child.lstrip()) <= indent:
                break
            scope = CHILD.match(child)
            if scope and _strip_comment(scope.group(2)) not in PERMISSION_LEVELS:
                problems.append(
                    f"{name}: permission {scope.group(1)} must be read or none,"
                    f" not {scope.group(2)}"
                )
    return problems


def _wrangler_subcommands(lines: list[str]) -> list[list[str]]:
    """Return the words after `wrangler` in each command of a job."""
    found: list[list[str]] = []
    for command in run_commands("\n".join(lines)):
        for words in _command_words(command):
            if "wrangler" in words:
                rest = words[words.index("wrangler") + 1 :]
                found.append([word for word in rest if not word.startswith("-")])
    return found


def _check_deploy_jobs(
    name: str, jobs: dict[str, list[str]], problems: list[str]
) -> None:
    for job, lines in jobs.items():
        condition = _job_field(lines, "if")
        for words in _wrangler_subcommands(lines):
            if words[:1] == ["deploy"]:
                if not all(part in condition for part in PRODUCTION_IF):
                    problems.append(
                        f"{name}: job {job} runs wrangler deploy, so its if: needs "
                        + " and ".join(PRODUCTION_IF)
                    )
            elif words[:2] == ["versions", "upload"]:
                if PREVIEW_IF not in condition:
                    problems.append(
                        f"{name}: job {job} uploads a preview, so its if: needs"
                        f" {PREVIEW_IF}"
                    )
            else:
                problems.append(
                    f"{name}: job {job} runs wrangler {' '.join(words[:2])};"
                    " only deploy and versions upload belong in CI"
                )


def _check_wrangler_config(root: Path, problems: list[str]) -> None:
    text = _read(root, WRANGLER_CONFIG, problems)
    if text is None:
        return
    # JSONC as Prettier writes it: whole-line comments and trailing commas.
    body = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )
    try:
        config = json.loads(re.sub(r",(\s*[}\]])", r"\1", body))
    except json.JSONDecodeError as error:
        problems.append(f"{WRANGLER_CONFIG}: not JSONC ({error})")
        return
    expected: dict[str, object] = {
        "name": "heartbeat",
        "workers_dev": False,
        "preview_urls": True,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            problems.append(f"{WRANGLER_CONFIG}: {key} must be {json.dumps(value)}")
    if config.get("assets", {}).get("directory") != "./dist":
        problems.append(f'{WRANGLER_CONFIG}: assets.directory must be "./dist"')
    if "main" in config:
        problems.append(f"{WRANGLER_CONFIG}: an assets-only Worker has no main")


def check_deploy(root: Path) -> list[str]:
    """OPS-06: deploys run only where design call 19 says, with read-only tokens.

    Every workflow declares read-only permissions and avoids the triggers that
    run a fork's code with secrets. `deploy.yml` is only called or started by
    hand; it uploads previews only on pull requests and deploys production only
    when started on main, and no other workflow runs wrangler. CI calls it only
    after the python and web jobs, and only for this repo's pull requests. The
    wrangler config is an assets-only Worker off workers.dev with previews on.

    Args:
        root: The repo root to check.

    Returns:
        One message per problem; empty means pass.
    """
    problems: list[str] = []
    if not (root / DEPLOY_WORKFLOW).is_file():
        problems.append(f"{DEPLOY_WORKFLOW}: missing")
    callers = 0
    for path in _workflow_files(root, WORKFLOW_GLOBS):
        name = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        problems.extend(_permission_problems(name, text))
        triggers = _triggers(text)
        for trigger in sorted(triggers & UNSAFE_TRIGGERS):
            problems.append(f"{name}: the {trigger} trigger runs forks with secrets")
        jobs = _jobs(text)
        if name == DEPLOY_WORKFLOW:
            if triggers != DEPLOY_TRIGGERS:
                problems.append(
                    f"{name}: triggers must be exactly workflow_call and"
                    f" workflow_dispatch, not {', '.join(sorted(triggers))}"
                )
            _check_deploy_jobs(name, jobs, problems)
            continue
        for job, lines in jobs.items():
            if _wrangler_subcommands(lines):
                problems.append(f"{name}: job {job} runs wrangler outside deploy.yml")
            if _job_field(lines, "uses") != f"./{DEPLOY_WORKFLOW}":
                continue
            callers += 1
            needs = {
                n.strip() for n in _job_field(lines, "needs").strip("[]").split(",")
            }
            if not {"python", "web"} <= needs:
                problems.append(f"{name}: job {job} must need the python and web jobs")
            condition = _job_field(lines, "if")
            if PREVIEW_IF not in condition or SAME_REPO_IF not in condition:
                problems.append(
                    f"{name}: job {job} needs if: {PREVIEW_IF} && {SAME_REPO_IF}"
                )
    if callers == 0:
        problems.append(f"no workflow calls {DEPLOY_WORKFLOW} for previews")
    _check_wrangler_config(root, problems)
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Print every problem; return 1 if there are any, else 0."""
    parser = argparse.ArgumentParser(
        prog="python -m heartbeat.checks.repo_config", description=__doc__
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    problems = (
        check_release_age(args.root)
        + check_action_pins(args.root)
        + check_deploy(args.root)
    )
    for problem in problems:
        sys.stdout.write(f"{problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
