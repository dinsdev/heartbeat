"""Task 1.7: the rule-coverage check (CONVENTIONS section 5).

Every row of PLAN.md section 6 whose phase is at or below `[tool.heartbeat]
current-phase` must have at least one test carrying its ID, in any layer (Phase 1
settling, 1 of 4). Rows whose only layer is MAN are never required. Later rows
are listed as pending.

Run as `python -m heartbeat.checks.rule_coverage [--root DIR]`.
"""

import argparse
import ast
import re
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from heartbeat.paths import REPO_ROOT

SECTION_HEADING = re.compile(r"^## 6\. Rule-to-test table\s*$", re.M)
NEXT_SECTION = re.compile(r"^## ", re.M)
RULE_ID = re.compile(r"R\d+")
PHASE_NUMBER = re.compile(r"\d+")
MANUAL_LAYER = "MAN"

# Vitest and Playwright: a test or suite whose title starts with the rule ID.
WEB_TITLE = re.compile(
    r"(?<![\w.$])(?:test\.describe|test|it|describe)\s*\(\s*[\"'`](R\d+):"
)
SKIPPED_DIRS = frozenset({"node_modules", "dist", ".venv"})


@dataclass(frozen=True)
class Row:
    """One row of the rule-to-test table."""

    rule_id: str
    layers: tuple[str, ...]
    phase: int


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_rule_table(plan_md: str) -> list[Row]:
    """Return the rows of PLAN.md section 6.

    The phase is the first integer in the Phase cell, so "1 onward" is 1.

    Raises:
        ValueError: The section is missing or a row is malformed; the message
            carries the row text.
    """
    heading = SECTION_HEADING.search(plan_md)
    if heading is None:
        raise ValueError("PLAN.md has no '## 6. Rule-to-test table' section")
    rest = plan_md[heading.end() :]
    following = NEXT_SECTION.search(rest)
    section = rest[: following.start()] if following else rest
    table = [line for line in section.splitlines() if line.lstrip().startswith("|")]
    if len(table) < 2:
        raise ValueError("the Rule-to-test table section has no table")
    header = _cells(table[0])
    try:
        id_col, layer_col, phase_col = (
            header.index("#"),
            header.index("Layer"),
            header.index("Phase"),
        )
    except ValueError as error:
        raise ValueError(f"unexpected table header: {table[0]}") from error
    rows: list[Row] = []
    for line in table[2:]:
        cells = _cells(line)
        if len(cells) != len(header):
            raise ValueError(f"expected {len(header)} cells: {line}")
        phase = PHASE_NUMBER.search(cells[phase_col])
        if not RULE_ID.fullmatch(cells[id_col]) or phase is None:
            raise ValueError(f"malformed rule row: {line}")
        layers = tuple(layer.strip() for layer in cells[layer_col].split(","))
        rows.append(Row(cells[id_col], layers, int(phase.group())))
    return rows


def _walk(root: Path, pattern: str) -> Iterable[Path]:
    for path in sorted(root.glob(pattern)):
        if path.is_file() and not SKIPPED_DIRS.intersection(path.parts):
            yield path


def _python_rule_ids(source: str) -> set[str]:
    """Return IDs from `pytest.mark.rule("Rn")` calls, not strings or comments."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_rule_mark = (
            isinstance(func, ast.Attribute)
            and func.attr == "rule"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "mark"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "pytest"
        )
        first = node.args[0]
        if (
            is_rule_mark
            and isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and RULE_ID.fullmatch(first.value)
        ):
            found.add(first.value)
    return found


def collect_rule_ids(root: Path) -> set[str]:
    """Return every rule ID carried by a test under `root`.

    Python: `pytest.mark.rule("Rn")` in `tests/**/*.py`. Web: titles starting
    `Rn:` in `web/**/*.test.ts` and `web/e2e/**/*.ts`.
    """
    found: set[str] = set()
    for path in _walk(root, "tests/**/*.py"):
        found |= _python_rule_ids(path.read_text(encoding="utf-8"))
    web_files = {*_walk(root, "web/**/*.test.ts"), *_walk(root, "web/e2e/**/*.ts")}
    for path in sorted(web_files):
        found |= set(WEB_TITLE.findall(path.read_text(encoding="utf-8")))
    return found


def current_phase(pyproject: Path) -> int:
    """Return `[tool.heartbeat] current-phase` from `pyproject.toml`.

    Raises:
        ValueError: The value is missing or not an integer.
    """
    with pyproject.open("rb") as handle:
        config = tomllib.load(handle)
    value = config.get("tool", {}).get("heartbeat", {}).get("current-phase")
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{pyproject} needs an integer [tool.heartbeat] current-phase")
    return value


def _needs_a_test(row: Row) -> bool:
    return any(layer != MANUAL_LAYER for layer in row.layers)


def uncovered(rows: Sequence[Row], ids: set[str], phase: int) -> list[Row]:
    """Return rows due by `phase` that no test covers (MAN-only rows skipped)."""
    return [
        row
        for row in rows
        if _needs_a_test(row) and row.phase <= phase and row.rule_id not in ids
    ]


def pending(rows: Sequence[Row], ids: set[str], phase: int) -> list[Row]:
    """Return rows due after `phase` that no test covers yet (MAN-only skipped)."""
    return [
        row
        for row in rows
        if _needs_a_test(row) and row.phase > phase and row.rule_id not in ids
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Print uncovered and pending rows; return 1 if any row is uncovered."""
    parser = argparse.ArgumentParser(
        prog="python -m heartbeat.checks.rule_coverage", description=__doc__
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    root: Path = args.root
    rows = parse_rule_table((root / "docs" / "PLAN.md").read_text(encoding="utf-8"))
    ids = collect_rule_ids(root)
    phase = current_phase(root / "pyproject.toml")
    missing = uncovered(rows, ids, phase)
    for row in missing:
        sys.stdout.write(f"uncovered: {row.rule_id} (phase {row.phase})\n")
    for row in pending(rows, ids, phase):
        sys.stdout.write(f"pending: {row.rule_id} (phase {row.phase})\n")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
