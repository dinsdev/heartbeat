"""Render the case study from its template and committed results (TASKS 8.2).

Fills the `{{source: key}}` slots of G1's outline (`docs/CASE_STUDY_OUTLINE.md`)
and `{{headline}}`, the sentence the sealed verdict picks, read from that outline
so it stays word for word. Every number on the page comes through here. An
unresolved slot is an error. `--check` compares instead of writing.
"""

import argparse
import dataclasses
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from heartbeat.cards.blocks import _cell, table
from heartbeat.sealed.log import read_log

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path("docs/case-study/heartbeat.template.mdx")
RENDERED = Path("docs/case-study/heartbeat.mdx")
OUTLINE = Path("docs/CASE_STUDY_OUTLINE.md")
LOG = Path("results/test_runs.jsonl")

# Rounding is Din's call, through this one constant (design call 3). The cards'
# `num` and `interval` are frozen at four decimals; the test pins the two equal
# while this stays 4, so a change here is a choice made on purpose.
DECIMALS = 4

SLOT = re.compile(r"\{\{([^{}]*)\}\}")
SLOT_BODY = re.compile(r"(?P<source>[a-z]+): (?P<key>.+)")
STEP = re.compile(r"(?P<name>[A-Za-z0-9_-]+)(?P<brackets>(?:\[[^\]]*\])*)")
BRACKET = re.compile(r"\[([^\]]*)\]")


class SlotError(ValueError):
    """A slot that does not resolve to something the page can show."""


@dataclass(frozen=True)
class Sources:
    """The outline's Slots table, read from committed files."""

    sealed: dict[str, Any]
    log: dict[str, Any]
    freeze: dict[str, Any]
    exhibit: dict[str, Any]
    data: dict[str, Any]
    selection: dict[str, Any]
    outline: str


def _read_json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def load_sources(root: Path) -> Sources:
    """Read every source, the sealed report by the last sealed log entry.

    Raises:
        SlotError: If the log has no sealed entry, or its report is not one.
    """
    entries = [e for e in read_log(root / LOG) if e["type"] == "sealed"]
    if not entries:
        raise SlotError("no sealed entry in the log")
    log = entries[-1]
    sealed = _read_json(root / log["report"])
    if sealed.get("entry_type") != "sealed":
        raise SlotError(f"{log['report']} is not a sealed report")
    return Sources(
        sealed=sealed,
        log=log,
        freeze=_read_json(root / "models/heartbeat-v1/freeze.json"),
        exhibit=_read_json(root / "results/exhibit.json"),
        data=_read_json(root / "results/data_summary.json"),
        selection=_read_json(root / "results/selection.json"),
        outline=(root / OUTLINE).read_text(encoding="utf-8"),
    )


def replace_sealed(sources: Sources, report: dict[str, Any]) -> Sources:
    """The same sources with another sealed report."""
    return dataclasses.replace(sources, sealed=report)


def number(value: float | None) -> str:
    """The page's rounding; "undefined" (never 0) for a metric with no value."""
    return "undefined" if value is None else f"{value:.{DECIMALS}f}"


def span(entry: Mapping[str, Any]) -> str:
    """The point and its interval, "point (low to high)"."""
    point = number(entry["point"])
    if entry["low"] is None:
        return f"{point} (no interval)"
    return f"{point} ({number(entry['low'])} to {number(entry['high'])})"


def per_patient_table(report: Mapping[str, Any]) -> str:
    """The model card's per-patient table, CNN seed 0 and baseline."""
    cnn, baseline = (report["per_patient"][n] for n in ("cnn-seed-0", "baseline"))
    rows = [
        [
            a["patient"],
            _cell(a["S"]["recall"]),
            _cell(a["S"]["precision"]),
            _cell(b["S"]["recall"]),
            _cell(b["S"]["precision"]),
            _cell(a["V"]["recall"]),
            _cell(a["V"]["precision"]),
            _cell(b["V"]["recall"]),
            _cell(b["V"]["precision"]),
        ]
        for a, b in zip(cnn, baseline, strict=True)
    ]
    return table(
        [
            "Patient",
            "CNN S recall",
            "CNN S precision",
            "Baseline S recall",
            "Baseline S precision",
            "CNN V recall",
            "CNN V precision",
            "Baseline V recall",
            "Baseline V precision",
        ],
        rows,
    )


TABLES: dict[tuple[str, str], Callable[[Mapping[str, Any]], str]] = {
    ("sealed", "per_patient"): per_patient_table,
}


def _steps(key: str) -> list[str]:
    """Split on the dots outside brackets."""
    return re.split(r"\.(?![^\[]*\])", key)


def _pick(rows: Any, inside: str, key: str) -> Any:
    if re.fullmatch(r"\d+", inside):
        try:
            return rows[int(inside)]
        except (IndexError, TypeError) as error:
            raise SlotError(f"no [{inside}] in {key}") from error
    if not isinstance(rows, list):
        raise SlotError(f"[{inside}] is not on a list in {key}")
    wanted = dict(part.split("=", 1) for part in inside.split(", ") if "=" in part)
    found = [
        row
        for row in rows
        if isinstance(row, dict)
        and wanted
        and all(str(row.get(k)) == v for k, v in wanted.items())
    ]
    if len(found) != 1:
        raise SlotError(f"[{inside}] matches {len(found)} rows in {key}")
    return found[0]


def _resolve(value: Any, key: str) -> Any:
    for step in _steps(key):
        match = STEP.fullmatch(step)
        if match is None:
            raise SlotError(f"bad key {key}")
        name = match.group("name")
        if name == "length" and isinstance(value, list):
            value = len(value)
        elif name == "whole" and isinstance(value, float) and value.is_integer():
            value = int(value)
        elif isinstance(value, dict) and name in value:
            value = value[name]
        else:
            raise SlotError(f"no {name} in {key}")
        for inside in BRACKET.findall(match.group("brackets")):
            value = _pick(value, inside, key)
    return value


def _show(value: Any, key: str) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, float):
        return number(value)
    if isinstance(value, bool):
        raise SlotError(f"{key} is a flag, not something to show")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict) and {"point", "low", "high"} <= value.keys():
        return span(value)
    if isinstance(value, dict) and {"min", "max"} <= value.keys():
        return f"{number(value['min'])} to {number(value['max'])}"
    if _is_numbers(value):
        return " and ".join(str(item) for item in value)
    raise SlotError(f"{key} is not a value (use .length for a list's length)")


def _is_numbers(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and bool(value)
        and all(isinstance(i, int | float) for i in value)
    )


def headline(sources: Sources) -> str:
    """The sentence the sealed verdict picks, from the outline, slots filled."""
    comparison = sources.sealed["comparison"]["metrics"]["macro_f1_nsv"]
    verdict = re.escape(comparison["verdict"])
    match = re.search(rf"^\*\*{verdict}\.\*\* (.+)$", sources.outline, re.M)
    if match is None:
        raise SlotError(f"no sentence in the outline for {comparison['verdict']}")
    sentence = match.group(1)
    values = {
        "n": str(len(sources.sealed["patients"])),
        "point": number(comparison["point"]),
        "low": number(comparison["low"]),
        "high": number(comparison["high"]),
    }
    for name, value in values.items():
        sentence = sentence.replace(f"`{{{{{name}}}}}`", value)
    if "{{" in sentence or "`" in sentence:
        raise SlotError(f"the outline's sentence has an unknown slot: {sentence}")
    return sentence


def _fill_one(body: str, sources: Sources) -> str:
    if body == "headline":
        return headline(sources)
    match = SLOT_BODY.fullmatch(body)
    if match is None:
        raise SlotError(f"bad slot: {{{{{body}}}}}")
    source, key = match.group("source"), match.group("key")
    if source not in {"sealed", "log", "freeze", "exhibit", "data", "selection"}:
        raise SlotError(f"unknown source: {source}")
    root = getattr(sources, source)
    render_table = TABLES.get((source, key))
    if render_table is not None:
        return render_table(root)
    return _show(_resolve(root, key), key)


def fill(text: str, sources: Sources) -> str:
    """Every slot filled.

    Raises:
        SlotError: On a slot that does not resolve, or a stray `{{` or `}}`.
    """
    filled = SLOT.sub(lambda m: _fill_one(m.group(1), sources), text)
    if "{{" in filled or "}}" in filled:
        raise SlotError("a stray {{ or }} is left after filling")
    return filled


def main(argv: Sequence[str] | None = None) -> int:
    """Write the page, or with `--check` say whether it is current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare, do not write")
    parser.add_argument("--output", type=Path, default=ROOT / RENDERED)
    args = parser.parse_args(argv)
    template = (ROOT / TEMPLATE).read_text(encoding="utf-8")
    page = fill(template, load_sources(ROOT))
    output: Path = args.output
    if args.check:
        current = output.read_text(encoding="utf-8") if output.exists() else ""
        if current != page:
            sys.stdout.write(f"{output} is stale: run scripts/render_case_study.py\n")
            return 1
        return 0
    output.write_text(page, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
