"""The `heartbeat` command (E4). Each subcommand is a stub until its phase builds it."""

import argparse
import sys
from collections.abc import Mapping, Sequence
from types import MappingProxyType

# PLAN.md section 8, Phase 1, Task 1: subcommand name to the phase that builds it.
SUBCOMMANDS: Mapping[str, int] = MappingProxyType(
    {
        "download": 2,
        "prepare": 2,
        "make-folds": 2,
        "check-folds": 2,
        "rebuild": 2,
        "cross-validate": 3,
        "select": 4,
        "exhibit": 4,
        "train-final": 4,
        "export": 5,
        "evaluate-test": 5,
        "verify": 5,
        "cards": 5,
        "build-demo-data": 6,
    }
)

# Exit code for a subcommand that exists in the interface but not yet in code.
NOT_BUILT_EXIT = 2


def build_parser() -> argparse.ArgumentParser:
    """Return the parser with every subcommand registered."""
    parser = argparse.ArgumentParser(
        prog="heartbeat",
        description="Build, evaluate and export the Heartbeat classifier.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True
    for name, phase in SUBCOMMANDS.items():
        sub = subparsers.add_parser(name, help=f"(arrives in Phase {phase})")
        if name == "rebuild":
            sub.add_argument(
                "--from",
                dest="from_stage",
                metavar="<stage>",
                help="rerun from this stage onward",
            )
            sub.add_argument(
                "--exact",
                action="store_true",
                help="bit-exact mode (E4, about 15 hours)",
            )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return its exit code.

    Args:
        argv: Arguments without the program name; defaults to `sys.argv[1:]`.

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(argv)
    command: str = args.command
    phase = SUBCOMMANDS[command]
    print(f"heartbeat {command}: not built yet (Phase {phase})", file=sys.stderr)
    return NOT_BUILT_EXIT
