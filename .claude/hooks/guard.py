#!/usr/bin/env python3
"""PreToolUse guard for Claude Code in Heartbeat (F5).

Backs up the deny rules in `.claude/settings.json`. Deny rules match the
command text Claude usually writes; this hook also catches the spellings they
miss (`git -C . push`, `/usr/bin/git push`, `sh -c '...'`, `python -m
heartbeat ...`). Deny rules and this hook hold in every permission mode; ask
rules did not prompt in a desktop session in bypass mode (measured
2026-10-27, see the F5 ledger entries).

It is a tripwire, not a security boundary: the code checks in the
rule-to-test table (PLAN.md section 6) are the real guard, and Codex never
runs this file.

What it blocks (exit 2, reason on stderr):

- Bash: commands only Din runs (AGENTS.md approvals): pushes, remotes, pull
  requests, releases, deploys, secrets, `evaluate-test`, `make-folds`,
  `rebuild --exact`.
- Bash: commands that discard uncommitted work (`git clean`, `git reset
  --hard`, `git checkout -- path`, `git restore path`, `git stash drop`).
- Bash: shell writes to paths only code may write (rule 5) or only Din may
  change (rule 4), and to `.claude/` itself.
- Edit, Write, NotebookEdit: adding a skip, xfail, only or todo marker to a
  test file (rule 3).

Any error inside the guard blocks the call, so a bug fails closed. Stdlib
only, Python 3.9 or later, so it runs on whatever `python3` is on PATH.
Tests: `.claude/hooks/test_guard.py`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

# Commands only Din runs, as (program, leading words). Matched on the
# positional words after the program, so options in between don't hide them.
DIN_ONLY = (
    ("git", ("push",)),
    ("git", ("remote", "add")),
    ("git", ("remote", "set-url")),
    ("gh", ("repo", "create")),
    ("gh", ("pr", "create")),
    ("gh", ("pr", "merge")),
    ("gh", ("release",)),
    ("gh", ("workflow", "run")),
    ("gh", ("secret",)),
    ("gh", ("variable",)),
    ("gh", ("auth", "token")),
    ("wrangler", ("deploy",)),
    ("wrangler", ("versions",)),
    ("wrangler", ("secret",)),
    ("wrangler", ("login",)),
    ("wrangler", ("preview",)),
    ("wrangler", ("rollback",)),
    ("wrangler", ("delete",)),
    ("heartbeat", ("evaluate-test",)),
    ("heartbeat", ("make-folds",)),
)
DIN_ONLY_REASON = (
    "only Din runs this (AGENTS.md, Git and approvals). Stop, say what you want "
    "to run and why, and give Din the exact command."
)

# Paths only code writes (rule 5), only Din changes (rule 4), or the guard
# itself. Relative to the repo root, compared as path prefixes.
PROTECTED_PREFIXES = (
    "results/",
    "models/heartbeat-v1/",
    "config/folds.json",
    "manifests/",
    ".claude/",
)

# Programs that write, move or delete the paths they are given.
WRITE_PROGRAMS = frozenset(
    {
        "rm",
        "rmdir",
        "mv",
        "cp",
        "tee",
        "truncate",
        "dd",
        "ln",
        "touch",
        "chmod",
        "chown",
        "install",
        "rsync",
        "unlink",
        "shred",
    }
)
# For these the last argument is the destination; the others are sources.
DEST_LAST_PROGRAMS = frozenset({"cp", "install", "rsync", "ln"})
# Interpreters count only when their script shows intent to write, so a
# read-only `python3 -c "json.load(open(...))"` passes.
INTERPRETERS = frozenset({"perl", "python", "python3", "node", "ruby", "awk", "gawk"})
INTERPRETER_WRITES = re.compile(
    r"""['"][wax]b?\+?['"]|write|unlink|remove|rmtree|rename|replace|truncate"""
    r"""|dump|save|copy|move|mkdir|>|-i\b"""
)
GIT_PATH_WRITES = frozenset(
    {"checkout", "restore", "rm", "mv", "apply", "reset", "clean"}
)

# Wrappers that run the command after them.
WRAPPERS = frozenset(
    {
        "timeout",
        "time",
        "nice",
        "nohup",
        "stdbuf",
        "command",
        "builtin",
        "noglob",
        "env",
        "sudo",
        "exec",
        "xargs",
        "watch",
        "setsid",
        "flock",
        "caffeinate",
    }
)
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})
# Runners that execute their argument, and the subcommand that does it
# (empty: no subcommand).
RUNNERS = {
    "uv": {"run"},
    "pnpm": {"exec", "dlx"},
    "uvx": set(),
    "npx": set(),
    "pipx": {"run"},
}
# Options that take the next token as their value, per program.
OPTIONS_WITH_VALUE = {
    "git": {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--exec-path",
        "--config-env",
    },
    "gh": {"-R", "--repo"},
    "wrangler": {"-c", "--config", "-e", "--env", "--cwd"},
    "heartbeat": {"--config"},
    "pnpm": {"-C", "--dir", "--filter", "-F"},
    "runner": {
        "-C",
        "--dir",
        "--directory",
        "--project",
        "--filter",
        "--with",
        "--python",
        "--from",
        "--package",
        "--group",
    },
}

SEPARATORS = frozenset({"&&", "||", ";", "|", "|&", "&", ";;", "(", ")", "{", "}"})
REDIRECT = re.compile(r"[<>&|]*[<>][<>&|]*")
OUTPUT_REDIRECT = re.compile(r"\d?(?:>>?|>\||&>>?)")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
DURATION = re.compile(r"[\d.]+[smhd]?")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
COARSE_DIN_ONLY = re.compile(
    r"\b(?:git\b[^;&|\n]*\bpush"
    r"|heartbeat\b[^;&|\n]*\b(?:evaluate-test|make-folds)"
    r"|wrangler\b[^;&|\n]*\bdeploy)\b"
)

SKIP_MARKERS = re.compile(
    r"pytest\.mark\.(?:skip|skipif|xfail)\b"
    r"|pytest\.(?:skip|xfail|importorskip)\s*\("
    r"|unittest\.skip\w*"
    r"|\.skipTest\s*\("
    r"|\b(?:it|test|describe|suite|bench)\.(?:skip|skipIf|runIf|only|todo|fixme|fail)\b"
    r"|\b(?:xit|xtest|xdescribe|fit|fdescribe)\s*\("
)


class BlockedError(Exception):
    """Raised with the reason shown to Claude when a call is blocked."""


def repo_root() -> Path:
    """Return the project root Claude Code passes to hooks."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()


def is_protected(path_text: str, cwd: Path) -> str | None:
    """Return the repo-relative path if it is protected, else None.

    Args:
        path_text: A word from the command that may be a path.
        cwd: The directory the command runs in.

    Returns:
        The path relative to the repo root, or None when the word is not a
        protected path.
    """
    path_text = path_text.strip("'\"")
    if not path_text or path_text.startswith("-"):
        return None
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = cwd / path
    try:
        rel = Path(os.path.normpath(path)).relative_to(repo_root()).as_posix()
    except ValueError:
        return None
    for prefix in PROTECTED_PREFIXES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            return rel
    return None


def protected_reason(rel: str) -> str:
    """Return which rule protects the path, for the message Claude sees."""
    if rel.startswith("results/"):
        return (
            "`results/` is written only by `rebuild`, and `test_runs.jsonl` only "
            "by `evaluate-test` (rule 5)."
        )
    if rel.startswith("models/heartbeat-v1"):
        return "`models/heartbeat-v1/` is written only by `heartbeat export` (rule 5)."
    if rel.startswith("config/folds.json"):
        return "`config/folds.json` is written only by `heartbeat make-folds` (rule 4)."
    if rel.startswith("manifests"):
        return (
            "Changes to `manifests/` need Din's go and a ledger entry (rule 4). "
            "Use the Edit tool after Din's go."
        )
    return "Changes to `.claude/` need Din's go. Use the Edit tool after Din's go."


def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies: they are data, and their quotes break shlex."""
    out: list[str] = []
    terminators: list[str] = []
    for line in command.split("\n"):
        if terminators:
            if line.strip() == terminators[0]:
                terminators.pop(0)
            continue
        out.append(line)
        terminators.extend(m.group(2) for m in HEREDOC.finditer(line))
    return "\n".join(out)


def segments(command: str) -> list[list[str]]:
    """Split a command into simple commands at shell separators.

    Raises:
        ValueError: The command doesn't tokenize (unbalanced quotes).
    """
    lexer = shlex.shlex(
        command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>"
    )
    lexer.whitespace_split = True
    lexer.commenters = ""
    result: list[list[str]] = [[]]
    for token in lexer:
        if token in SEPARATORS:
            result.append([])
        else:
            result[-1].append(token)
    return [segment for segment in result if segment]


def skip_options(argv: list[str], program: str) -> list[str]:
    """Drop leading options, and the values of options that take one."""
    with_value = OPTIONS_WITH_VALUE.get(program, set())
    while argv and argv[0].startswith("-"):
        argv = argv[2:] if argv[0] in with_value else argv[1:]
    return argv


def unwrap(argv: list[str]) -> list[str]:
    """Strip assignments, wrappers and runners down to the command they run."""
    while argv:
        head = Path(argv[0]).name
        if ASSIGNMENT.match(argv[0]):
            argv = argv[1:]
        elif head in WRAPPERS:
            argv = argv[1:]
            while argv and (
                argv[0].startswith("-")
                or ASSIGNMENT.match(argv[0])
                or DURATION.fullmatch(argv[0])
            ):
                argv = argv[1:]
        elif head in RUNNERS:
            rest = skip_options(argv[1:], "runner")
            if RUNNERS[head]:
                if not rest or rest[0] not in RUNNERS[head]:
                    break
                rest = skip_options(rest[1:], "runner")
            argv = rest
        elif head in INTERPRETERS and "-m" in argv:
            # `python -m heartbeat ...` runs the module as a program.
            argv = argv[argv.index("-m") + 1 :]
        else:
            break
    return argv


def positional(argv: list[str], program: str) -> list[str]:
    """Return the words after the program that are not options or their values."""
    with_value = OPTIONS_WITH_VALUE.get(program, set())
    words: list[str] = []
    i = 1
    while i < len(argv):
        token = argv[i]
        if token in with_value:
            i += 2
            continue
        if not token.startswith("-"):
            words.append(token)
        i += 1
    return words


def check_din_only(program: str, argv: list[str]) -> None:
    """Block the commands only Din runs.

    Raises:
        BlockedError: The command is on Din's list.
    """
    words = positional(argv, program)
    for name, leading in DIN_ONLY:
        if program == name and tuple(words[: len(leading)]) == leading:
            raise BlockedError(f"`{name} {' '.join(leading)}`: {DIN_ONLY_REASON}")
    if program == "heartbeat" and words[:1] == ["rebuild"] and "--exact" in argv:
        raise BlockedError(
            f"`heartbeat rebuild --exact` takes about 15 hours: {DIN_ONLY_REASON}"
        )
    if program == "pnpm" and any(word.startswith("deploy") for word in words[:2]):
        raise BlockedError(f"`pnpm ... deploy`: {DIN_ONLY_REASON}")


def check_discard(argv: list[str]) -> None:
    """Block git commands that throw away uncommitted work.

    Raises:
        BlockedError: The command can discard uncommitted work.
    """
    words = positional(argv, "git")
    sub = words[0] if words else None
    discards = (
        sub == "clean"
        or (sub == "reset" and "--hard" in argv)
        or (sub == "checkout" and "--" in argv)
        or (sub == "restore" and "--staged" not in argv and "-S" not in argv)
        or (sub == "stash" and words[1:2] in (["drop"], ["clear"]))
    )
    if discards:
        raise BlockedError(
            f"`git {sub}` here can discard uncommitted work, which the global "
            "agreements rule out. Commit or stash first, or ask Din."
        )


def write_targets(program: str, argv: list[str]) -> list[str]:
    """Return the arguments a program may write to, or none if it only reads."""
    if (program == "find" and {"-delete", "-exec", "-execdir", "-ok"} & set(argv)) or (
        program == "sed" and any(t.startswith("-i") or t == "--in-place" for t in argv)
    ):
        return argv[1:]
    if program in DEST_LAST_PROGRAMS:
        return argv[-1:]
    if program in WRITE_PROGRAMS or (
        program in INTERPRETERS and INTERPRETER_WRITES.search(" ".join(argv[1:]))
    ):
        return argv[1:]
    return []


def check_segment(argv: list[str], cwd: Path) -> None:
    """Check one simple command: redirects, Din's list, discards, protected paths.

    Raises:
        BlockedError: The command is blocked.
    """
    kept: list[str] = []
    skip_next = False
    for i, token in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if REDIRECT.fullmatch(token) or OUTPUT_REDIRECT.fullmatch(token):
            if kept and kept[-1].isdigit():
                kept.pop()
            if ">" in token and i + 1 < len(argv):
                rel = is_protected(argv[i + 1], cwd)
                if rel:
                    raise BlockedError(f"shell write to {rel}. {protected_reason(rel)}")
            skip_next = True
        else:
            kept.append(token)

    argv = unwrap(kept)
    if not argv:
        return
    program = Path(argv[0]).name

    if program in SHELLS and "-c" in argv[1:]:
        inner = argv[argv.index("-c") + 1 :]
        if inner:
            check_command(inner[0], cwd)
        return
    if program == "eval":
        check_command(" ".join(argv[1:]), cwd)
        return

    check_din_only(program, argv)

    if program == "git":
        check_discard(argv)
        words = positional(argv, "git")
        if words and words[0] in GIT_PATH_WRITES:
            for token in words[1:]:
                rel = is_protected(token, cwd)
                if rel:
                    raise BlockedError(
                        f"`git {words[0]}` on {rel}. {protected_reason(rel)}"
                    )
        return

    for token in write_targets(program, argv):
        # A path can sit inside a script string, so look at every word.
        for word in re.split(r"[\s'\"(),=]+", token):
            rel = is_protected(word, cwd)
            if rel:
                raise BlockedError(
                    f"`{program}` touching {rel}. {protected_reason(rel)}"
                )


def check_command(command: str, cwd: Path) -> None:
    """Check a whole Bash command, following `cd` and command substitutions.

    Raises:
        BlockedError: Some part of the command is blocked.
    """
    body = strip_heredocs(command)
    for match in SUBSTITUTION.finditer(body):
        check_command(match.group(1) or match.group(2) or "", cwd)
    try:
        parsed = segments(body)
    except ValueError:
        coarse_check(body)
        return
    for argv in parsed:
        if argv[0] in {"cd", "pushd"} and len(argv) > 1:
            cwd = Path(os.path.normpath(cwd / Path(argv[1]).expanduser()))
            continue
        check_segment(argv, cwd)


def coarse_check(command: str) -> None:
    """Fall back to the raw text when the command doesn't tokenize.

    Raises:
        BlockedError: The text looks like a command only Din runs.
    """
    if COARSE_DIN_ONLY.search(command):
        raise BlockedError(
            f"couldn't parse this command and it looks like one {DIN_ONLY_REASON}"
        )


def is_test_file(path_text: str) -> bool:
    """Return whether the path is a Python or TypeScript test file."""
    path = Path(path_text)
    name = path.name
    return (
        "tests" in path.parts
        or name == "conftest.py"
        or (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
        or re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", name) is not None
    )


def check_file_tool(tool_name: str, tool_input: dict[str, object]) -> None:
    """Block file edits that add skip markers to a test file.

    Raises:
        BlockedError: The edit adds a skip, xfail, only or todo marker.
    """
    path_text = str(
        tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    )
    if not path_text or not is_test_file(path_text):
        return
    if tool_name == "Edit":
        before = str(tool_input.get("old_string", ""))
        after = str(tool_input.get("new_string", ""))
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        edit_list = edits if isinstance(edits, list) else []
        before = "\n".join(str(e.get("old_string", "")) for e in edit_list)
        after = "\n".join(str(e.get("new_string", "")) for e in edit_list)
    else:
        path = Path(path_text)
        before = (
            path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        )
        after = str(tool_input.get("content") or tool_input.get("new_source") or "")
    if len(SKIP_MARKERS.findall(after)) > len(SKIP_MARKERS.findall(before)):
        raise BlockedError(
            "this adds a skip, xfail, only or todo marker to a test. Tests are the "
            "spec (AGENTS.md rule 3): if a test looks wrong, stop and explain why "
            "to Din."
        )


def main() -> int:
    """Read the hook event from stdin and return the exit code (2 blocks)."""
    try:
        event = json.load(sys.stdin)
        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input") or {}
        cwd = Path(event.get("cwd") or Path.cwd())
        if tool_name == "Bash":
            check_command(tool_input.get("command", ""), cwd)
        elif tool_name in {"Edit", "Write", "NotebookEdit", "MultiEdit"}:
            check_file_tool(tool_name, tool_input)
    except BlockedError as reason:
        sys.stderr.write(f"Blocked by .claude/hooks/guard.py: {reason}\n")
        return 2
    except Exception as error:  # fail closed on any guard bug
        sys.stderr.write(
            f"Blocked: .claude/hooks/guard.py failed ({error!r}). Tell Din.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
