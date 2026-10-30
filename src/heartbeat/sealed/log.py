"""The append-only sealed-run log (C6, E4; EVAL-06, R42).

`results/test_runs.jsonl` holds one JSON line per run of `evaluate-test` (type
"sealed") or of the post-freeze reproduction (type "reproduction", OPS-03):
a sequential id, the type, the commit, the freeze record's SHA256, the
report's path and SHA256, and the date. The full EVAL-08 report goes to
`results/test_runs/<id>-<type>.json`, never overwritten. The writer only ever
opens the log in append mode; `check_log` and `check_log_history` (used by
`heartbeat verify`) catch a rewritten line, a changed report, or a committed
version that does not extend the one before it.
"""

import hashlib
import itertools
import json
import subprocess
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from heartbeat.runs import canonical_json

ENTRY_TYPES = ("sealed", "reproduction")
ENTRY_KEYS = (
    "commit",
    "date",
    "freeze_sha256",
    "id",
    "report",
    "report_sha256",
    "type",
)


class LogError(RuntimeError):
    """The log or a report breaks the append-only rule (R42)."""


def read_log(log_path: Path) -> list[dict[str, Any]]:
    """Every entry, in order; an absent log is empty.

    Raises:
        LogError: On a line that is not a JSON object with the entry keys.
    """
    if not log_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for number, line in enumerate(log_path.read_text("utf-8").splitlines(), 1):
        try:
            entry = json.loads(line)
        except ValueError as error:
            raise LogError(f"{log_path} line {number}: not JSON") from error
        if not isinstance(entry, dict) or sorted(entry) != list(ENTRY_KEYS):
            raise LogError(f"{log_path} line {number}: keys are not {ENTRY_KEYS}")
        entries.append(entry)
    return entries


def _line(entry: Mapping[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), allow_nan=False)


def append_entry(
    log_path: Path,
    reports_dir: Path,
    entry_type: str,
    report: Mapping[str, Any],
    commit: str,
    freeze_sha256: str,
    today: date,
    repo: Path,
) -> dict[str, Any]:
    """Write the report, then append its entry to the log.

    Raises:
        LogError: On an unknown type, a log that fails `check_log`, or a
            report file that already exists.
    """
    if entry_type not in ENTRY_TYPES:
        raise LogError(f"entry type {entry_type!r} is not one of {ENTRY_TYPES}")
    check_log(log_path, repo)
    entries = read_log(log_path)
    number = len(entries) + 1
    report_path = reports_dir / f"{number}-{entry_type}.json"
    text = canonical_json(report)
    reports_dir.mkdir(parents=True, exist_ok=True)
    try:
        # "x": refuse an existing report rather than overwrite it.
        with report_path.open("x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError as error:
        raise LogError(
            f"{report_path} exists; reports are never overwritten"
        ) from error
    entry = {
        "id": number,
        "type": entry_type,
        "commit": commit,
        "freeze_sha256": freeze_sha256,
        "report": report_path.relative_to(repo).as_posix(),
        "report_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "date": today.isoformat(),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(_line(entry) + "\n")
    return entry


def check_log(log_path: Path, repo: Path) -> None:
    """Check ids run 1, 2, ... and every report matches its recorded SHA256.

    Raises:
        LogError: Naming the first problem.
    """
    for number, entry in enumerate(read_log(log_path), 1):
        if entry["id"] != number:
            raise LogError(f"{log_path}: line {number} has id {entry['id']}")
        if entry["type"] not in ENTRY_TYPES:
            raise LogError(f"{log_path}: line {number} has type {entry['type']}")
        expected = f"{number}-{entry['type']}.json"
        if Path(entry["report"]).name != expected:
            raise LogError(f"{log_path}: line {number} names {entry['report']}")
        report = repo / entry["report"]
        if not report.is_file():
            raise LogError(f"{entry['report']} is missing")
        digest = hashlib.sha256(report.read_bytes()).hexdigest()
        if digest != entry["report_sha256"]:
            raise LogError(f"{entry['report']} differs from its logged SHA256")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


def check_log_history(log_path: Path, repo: Path) -> None:
    """Check every committed version of the log extends the one before it.

    The working copy must extend the last committed version too.

    Raises:
        LogError: If a version drops or changes an earlier line.
    """
    relative = log_path.relative_to(repo).as_posix()
    listed = _git(repo, "log", "--format=%H", "--reverse", "--", relative)
    versions = [
        _git(repo, "show", f"{commit}:{relative}").stdout
        for commit in listed.stdout.split()
    ]
    if log_path.is_file():
        versions.append(log_path.read_text("utf-8"))
    for before, after in itertools.pairwise(versions):
        if not after.startswith(before):
            raise LogError(f"{relative}: a version does not extend the one before it")
