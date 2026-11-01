"""Phase 5 settling 4: two checkouts' outputs compared exactly (C6, E4; OPS-03).

`results/*.json` must be equal once the volatile keys are removed: run names,
commits, run-folder paths and wall times, the one list in `VOLATILE_KEYS`.
A volatile key whose value holds a number anywhere inside (a list of runs with
their confusion matrices, say) is not dropped: it is opened, so every number
in it still compares. `models/heartbeat-v1/`, `fixtures/parity/` and the two
cards must be byte-identical. Checkpoint SHA256s sit in
`results/train_final.json` under non-volatile keys, so they compare too.

Run as `python -m heartbeat.checks.reproduction --other DIR [--root DIR]`.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from heartbeat.paths import REPO_ROOT

# Names and times, never numbers that a run computed (a test checks no metric
# name is here).
VOLATILE_KEYS = frozenset(
    {"run", "runs", "commit", "curves_run", "baseline_run", "path", "wall_s"}
)

# Compared byte for byte.
BYTE_FOLDERS = ("models/heartbeat-v1", "fixtures/parity")
BYTE_FILES = ("docs/MODEL_CARD.md", "docs/DATA_CARD.md")


def _only_text(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_only_text(v) for v in value.values())
    if isinstance(value, list):
        return all(_only_text(v) for v in value)
    return not isinstance(value, (int, float)) or isinstance(value, bool)


def strip_volatile(value: Any) -> Any:
    """`value` without volatile keys; one holding numbers inside is opened."""
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if key in VOLATILE_KEYS and (_only_text(item) or key == "wall_s"):
                continue
            out[key] = strip_volatile(item)
        return out
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def _files(root: Path) -> set[str]:
    found = {p.relative_to(root).as_posix() for p in (root / "results").glob("*.json")}
    for folder in BYTE_FOLDERS:
        base = root / folder
        if base.is_dir():
            found |= {
                p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file()
            }
    found |= {name for name in BYTE_FILES if (root / name).is_file()}
    return found


def compare_checkouts(root: Path, other: Path) -> list[str]:
    """Every compared file that differs or exists on one side only."""
    problems: list[str] = []
    mine, theirs = _files(root), _files(other)
    for name in sorted(mine | theirs):
        if name not in theirs:
            problems.append(f"{name} missing in {other.name}")
            continue
        if name not in mine:
            problems.append(f"{name} missing in {root.name}")
            continue
        a, b = (root / name).read_bytes(), (other / name).read_bytes()
        if name.startswith("results/"):
            same = strip_volatile(json.loads(a)) == strip_volatile(json.loads(b))
        else:
            same = a == b
        if not same:
            problems.append(f"{name} differs")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Compare this checkout (or `--root`) with `--other`; exit 1 on a difference."""
    parser = argparse.ArgumentParser(prog="python -m heartbeat.checks.reproduction")
    parser.add_argument("--other", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    problems = compare_checkouts(args.root, args.other)
    for problem in problems:
        sys.stdout.write(f"{problem}\n")
    compared = len(_files(args.root))
    sys.stdout.write(
        f"reproduction: {compared} files compared, {len(problems)} differ\n"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
