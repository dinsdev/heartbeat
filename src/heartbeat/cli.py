"""The `heartbeat` command (E4). Each subcommand is a stub until its phase builds it."""

import argparse
import hashlib
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from sklearn.exceptions import ConvergenceWarning

from heartbeat.config import CV_DEVICES, Settings, load_settings
from heartbeat.constants import CNN_WIDTHS, FLOOR_HIT_LIMIT, MAX_EPOCHS, N_FOLDS
from heartbeat.data import download as download_module
from heartbeat.data.download import ChecksumMismatchError, DownloadError, check_cache
from heartbeat.data.folds import (
    FoldCheckError,
    Folds,
    check_folds,
    make_folds,
    write_folds,
)
from heartbeat.data.loader import BeatTable, load_ds1, load_ds1_traces
from heartbeat.data.manifests import load_checksums, load_splits, load_subjects
from heartbeat.data.prepare import FloorHitLimitError, prepare_ds1
from heartbeat.evaluate.calibration import TemperatureAtBoundError
from heartbeat.paths import (
    CHECKSUM_MANIFEST,
    DEFAULT_CONFIG,
    FOLDS_JSON,
    FOLDS_PIN,
    PACKAGE_DIR,
    RUNS_DIR,
    SPLITS_MANIFEST,
    STAGES_DIR,
    SUBJECTS_MANIFEST,
    UV_LOCK,
)
from heartbeat.stages import (
    PIPELINE,
    PLANNED,
    Context,
    StageFailedError,
    UnknownStageError,
    run_exhibit_all,
    run_final_all,
    run_pipeline,
    run_select_all,
)
from heartbeat.train.cnn_cv import MissingRunError, run_cnn_cv
from heartbeat.train.cv import run_baseline
from heartbeat.train.loop import NonFiniteLossError
from heartbeat.train.select import EpochEdgeError, UndefinedScoreError
from heartbeat.train.torch_setup import DeviceUnavailableError

# Phase 2 settling 5: the manifests whose hashes the fold file records.
FOLD_MANIFESTS = (SPLITS_MANIFEST, SUBJECTS_MANIFEST)

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


def _make_folds(args: argparse.Namespace) -> int:
    # Phase 2 settling 5: Din runs this once; F5 denies it to Claude.
    settings = load_settings(DEFAULT_CONFIG)
    splits = load_splits(SPLITS_MANIFEST)
    subjects = load_subjects(SUBJECTS_MANIFEST)
    out = Path(args.out) if args.out is not None else FOLDS_JSON
    if out.exists():
        print(
            f"heartbeat make-folds: {out} exists; folds are made once", file=sys.stderr
        )
        return 1
    beats = load_ds1(settings.data.prepared_dir, splits, subjects)
    folds = make_folds(beats, settings.folds.seed, manifest_paths=FOLD_MANIFESTS)
    try:
        write_folds(folds, out)
    except FileExistsError as error:
        print(f"heartbeat make-folds: {error}", file=sys.stderr)
        return 1
    for fold in range(N_FOLDS):
        members = sorted(s for s, f in folds.subject_fold.items() if f == fold)
        counts = ", ".join(f"{c} {n}" for c, n in folds.class_counts[str(fold)].items())
        print(f"fold {fold}: {len(members)} subjects ({' '.join(members)}); {counts}")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"heartbeat make-folds: wrote {out} (seed {folds.seed})")
    print(f"sha256 {digest}")
    return 0


def _check_folds(args: argparse.Namespace) -> int:
    try:
        folds = check_folds(
            FOLDS_JSON,
            FOLDS_PIN,
            load_splits(SPLITS_MANIFEST),
            load_subjects(SUBJECTS_MANIFEST),
            manifest_paths=FOLD_MANIFESTS,
        )
    except FoldCheckError as error:
        print(f"heartbeat check-folds: {error}", file=sys.stderr)
        return 1
    print(
        f"heartbeat check-folds: ok, {len(folds.subject_fold)} subjects in "
        f"{N_FOLDS} folds, {FOLDS_JSON} matches its pin"
    )
    return 0


def _cross_validate(args: argparse.Namespace) -> int:
    # Writes a run folder only; results/ is written by the rebuild stage (rule 5).
    settings = load_settings(DEFAULT_CONFIG)
    splits = load_splits(SPLITS_MANIFEST)
    subjects = load_subjects(SUBJECTS_MANIFEST)
    try:
        folds = check_folds(
            FOLDS_JSON, FOLDS_PIN, splits, subjects, manifest_paths=FOLD_MANIFESTS
        )
    except FoldCheckError as error:
        print(f"heartbeat cross-validate: {error}", file=sys.stderr)
        return 1
    beats = load_ds1(settings.data.prepared_dir, splits, subjects)
    folds_sha256 = hashlib.sha256(FOLDS_JSON.read_bytes()).hexdigest()
    if args.model == "cnn":
        return _cross_validate_cnn(args, settings, beats, folds, folds_sha256)
    try:
        run, summary = run_baseline(settings, beats, folds, folds_sha256, root=RUNS_DIR)
    except (ConvergenceWarning, TemperatureAtBoundError) as error:
        # Phase 3 plan, stop conditions 1 and 5.
        print(f"heartbeat cross-validate: {error}", file=sys.stderr)
        return 1
    pooled = summary["pooled"]
    print(
        f"heartbeat cross-validate: {args.model}, chosen C {summary['chosen_c']}; "
        f"DS1 out-of-fold macro F1 over N, S, V {pooled['macro_f1_nsv']:.4f}, "
        f"four-class {pooled['macro_f1_all']:.4f}; "
        f"temperature {summary['calibration']['temperature']:.4f}"
    )
    print(f"run folder {run.path}")
    return 0


def _cross_validate_cnn(
    args: argparse.Namespace,
    settings: Settings,
    beats: BeatTable,
    folds: Folds,
    folds_sha256: str,
) -> int:
    # A development run at one width and seed, all folds or one (Task 9).
    device = args.device or settings.train.cv_device
    only_folds = None if args.fold is None else [args.fold]
    traces = load_ds1_traces(
        settings.data.prepared_dir,
        load_splits(SPLITS_MANIFEST),
        load_subjects(SUBJECTS_MANIFEST),
    )
    try:
        run, _ = run_cnn_cv(
            settings,
            beats,
            traces,
            folds,
            folds_sha256,
            width=args.width,
            seed=args.seed,
            device=device,
            root=RUNS_DIR,
            n_epochs=MAX_EPOCHS,
            only_folds=only_folds,
        )
    except (DeviceUnavailableError, NonFiniteLossError) as error:
        print(f"heartbeat cross-validate: {error}", file=sys.stderr)
        return 1
    folds_text = "all folds" if only_folds is None else f"fold {args.fold}"
    print(
        f"heartbeat cross-validate: cnn width {args.width:g} seed {args.seed}, "
        f"{folds_text}, {MAX_EPOCHS} epochs on {device}"
    )
    print(f"run folder {run.path}")
    return 0


# Errors that stop a CNN subcommand with exit 1 (Phase 4 plan, stop conditions).
_CNN_STOPS = (
    EpochEdgeError,
    UndefinedScoreError,
    MissingRunError,
    NonFiniteLossError,
    DeviceUnavailableError,
    TemperatureAtBoundError,
    ConvergenceWarning,
    FileNotFoundError,
    ValueError,
)


def _select(args: argparse.Namespace) -> int:
    # Writes a run folder only; results/ is written by the rebuild stage (rule 5).
    try:
        run, selection, _ = run_select_all(load_settings(DEFAULT_CONFIG))
    except _CNN_STOPS as error:
        print(f"heartbeat select: {error}", file=sys.stderr)
        return 1
    if selection:
        print(
            f"heartbeat select: width {selection['width']:g}, "
            f"{selection['epoch']} epochs"
        )
    print(f"run folder {run.path}")
    return 0


def _exhibit(args: argparse.Namespace) -> int:
    try:
        run, _ = run_exhibit_all(load_settings(DEFAULT_CONFIG))
    except _CNN_STOPS as error:
        print(f"heartbeat exhibit: {error}", file=sys.stderr)
        return 1
    print(f"run folder {run.path}")
    return 0


def _train_final(args: argparse.Namespace) -> int:
    try:
        run, _ = run_final_all(load_settings(DEFAULT_CONFIG))
    except _CNN_STOPS as error:
        print(f"heartbeat train-final: {error}", file=sys.stderr)
        return 1
    print(f"run folder {run.path}")
    return 0


def rebuild_context() -> Context:
    """Return the context `rebuild` runs in."""
    return Context(
        settings=load_settings(DEFAULT_CONFIG),
        package_dir=PACKAGE_DIR,
        state_dir=STAGES_DIR,
        uv_lock=UV_LOCK,
    )


def _rebuild(args: argparse.Namespace) -> int:
    planned = dict(PLANNED)
    if args.from_stage in planned:
        print(
            f"heartbeat rebuild: stage {args.from_stage} is not built yet "
            f"(Phase {planned[args.from_stage]})",
            file=sys.stderr,
        )
        return 2
    if args.exact:
        # E4: --exact (every training run on CPU, checked bit for bit) is built
        # with the reproduction checks in Phase 5.
        print(
            "heartbeat rebuild: --exact is not built yet (Phase 5); "
            "running the default mode"
        )
    try:
        results = run_pipeline(PIPELINE, rebuild_context(), from_stage=args.from_stage)
    except UnknownStageError as error:
        print(f"heartbeat rebuild: {error}", file=sys.stderr)
        return 2
    except StageFailedError as error:
        print(f"heartbeat rebuild: {error}", file=sys.stderr)
        return 1
    for result in results:
        state = "ran" if result.ran else "skipped"
        print(f"{result.name}: {state} ({result.reason})")
    if PLANNED:
        name, phase = PLANNED[0]
        print(
            f"heartbeat rebuild: stopped after {results[-1].name}; "
            f"next stage {name} (Phase {phase}) is not built yet"
        )
    return 0


HANDLERS: Mapping[str, Callable[[argparse.Namespace], int]] = MappingProxyType(
    {
        "download": _download,
        "prepare": _prepare,
        "make-folds": _make_folds,
        "check-folds": _check_folds,
        "rebuild": _rebuild,
        "cross-validate": _cross_validate,
        "select": _select,
        "exhibit": _exhibit,
        "train-final": _train_final,
    }
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
        if name == "make-folds":
            sub.add_argument(
                "--out",
                metavar="PATH",
                help="where to write the folds (default config/folds.json)",
            )
        if name == "cross-validate":
            sub.add_argument(
                "--model",
                choices=("baseline", "cnn"),
                default="baseline",
                help="the model to cross-validate",
            )
            sub.add_argument(
                "--width",
                type=float,
                choices=CNN_WIDTHS,
                default=1.0,
                help="CNN width (development runs)",
            )
            sub.add_argument(
                "--seed", type=int, default=0, help="CNN master seed (default 0)"
            )
            sub.add_argument(
                "--fold",
                type=int,
                choices=range(N_FOLDS),
                help="train this fold only (development runs)",
            )
            sub.add_argument(
                "--device",
                choices=CV_DEVICES,
                help="CNN device (default: [train] cv_device)",
            )
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
