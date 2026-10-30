"""The `heartbeat` command (E4). Each subcommand is a stub until its phase builds it."""

import argparse
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType

from heartbeat.config import load_settings
from heartbeat.constants import FLOOR_HIT_LIMIT
from heartbeat.data import download as download_module
from heartbeat.data.download import ChecksumMismatchError, DownloadError, check_cache
from heartbeat.data.manifests import load_checksums, load_splits, load_subjects
from heartbeat.data.prepare import FloorHitLimitError, prepare_ds1
from heartbeat.paths import (
    CHECKSUM_MANIFEST,
    DEFAULT_CONFIG,
    SPLITS_MANIFEST,
    SUBJECTS_MANIFEST,
)

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


def _download(args: argparse.Namespace) -> int:
    settings = load_settings(DEFAULT_CONFIG)
    checksums = load_checksums(CHECKSUM_MANIFEST)
    try:
        report = download_module.download(
            settings.data.raw_dir,
            checksums,
            settings.data.sources,
            fetch=download_module.fetch_url,
        )
    except (ChecksumMismatchError, DownloadError) as error:
        print(f"heartbeat download: {error}", file=sys.stderr)
        return 1
    print(
        f"heartbeat download: fetched {len(report.fetched)}, "
        f"skipped {len(report.skipped)}, of {len(checksums)} files "
        f"in {settings.data.raw_dir}"
    )
    return 0


def _prepare(args: argparse.Namespace) -> int:
    settings = load_settings(DEFAULT_CONFIG)
    # DATA-02: every run checks the cache before using it.
    try:
        status = check_cache(settings.data.raw_dir, load_checksums(CHECKSUM_MANIFEST))
    except ChecksumMismatchError as error:
        print(f"heartbeat prepare: {error}", file=sys.stderr)
        return 1
    if not status.ok:
        print(
            f"heartbeat prepare: {len(status.missing)} cached files missing; "
            "run `uv run heartbeat download`",
            file=sys.stderr,
        )
        return 1
    try:
        report = prepare_ds1(
            settings, load_splits(SPLITS_MANIFEST), load_subjects(SUBJECTS_MANIFEST)
        )
    except FloorHitLimitError as error:
        print(f"heartbeat prepare: {error}", file=sys.stderr)
        return 1
    print(
        f"heartbeat prepare: prepared {len(report.records)} DS1 records into "
        f"{settings.data.prepared_dir}; floor hits {report.total_hits} "
        f"(limit {FLOOR_HIT_LIMIT})"
    )
    return 0


HANDLERS: Mapping[str, Callable[[argparse.Namespace], int]] = MappingProxyType(
    {"download": _download, "prepare": _prepare}
)


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
    handler = HANDLERS.get(command)
    if handler is not None:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
        return handler(args)
    phase = SUBCOMMANDS[command]
    print(f"heartbeat {command}: not built yet (Phase {phase})", file=sys.stderr)
    return NOT_BUILT_EXIT
