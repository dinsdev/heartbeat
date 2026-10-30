"""The `rebuild` stages, their fingerprints and `--from` (E4; OPS-01, partial).

A stage reruns when its fingerprint changes: its settings, its upstream
fingerprints, the code under the package folders it declares, its input files,
or `uv.lock`. It also reruns when an output is missing, when `--from` names it
or an earlier stage, or always if it is marked `always_run`. State lives in
`data/stages/<name>.json` and is written only after the stage succeeds.
"""

import hashlib
import json
import logging
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from heartbeat.config import Settings
from heartbeat.data.download import download
from heartbeat.data.folds import check_folds
from heartbeat.data.manifests import load_checksums, load_splits, load_subjects
from heartbeat.data.prepare import FLOOR_HITS_FILE, prepare_ds1
from heartbeat.paths import (
    CHECKSUM_MANIFEST,
    FOLDS_JSON,
    FOLDS_PIN,
    SPLITS_MANIFEST,
    SUBJECTS_MANIFEST,
)

log = logging.getLogger(__name__)


class UnknownStageError(ValueError):
    """`--from` names no built stage."""


class StageFailedError(RuntimeError):
    """A stage's run raised; its old state is left as it was."""


@dataclass(frozen=True)
class Context:
    """What stages read: settings and the folders the framework uses.

    Attributes:
        settings: Run settings.
        package_dir: Root of the Python package, for code fingerprints.
        state_dir: Where stage state files live.
        uv_lock: The lockfile, part of every fingerprint.
    """

    settings: Settings
    package_dir: Path
    state_dir: Path
    uv_lock: Path


@dataclass(frozen=True)
class Stage:
    """One step of `rebuild`.

    Attributes:
        name: The stage name, as `--from` takes it.
        settings_keys: Dotted settings names the stage depends on.
        upstream: Names of stages whose fingerprints feed this one.
        code: Folders or files under the package whose `.py` files it runs.
        inputs: Files it reads, hashed into the fingerprint.
        run: Does the work; raises on failure.
        outputs: Files it writes; a missing one reruns the stage.
        always_run: Run every time (checks such as check-folds).
    """

    name: str
    settings_keys: tuple[str, ...]
    upstream: tuple[str, ...]
    code: tuple[str, ...]
    inputs: Callable[[Context], Sequence[Path]]
    run: Callable[[Context], None]
    outputs: Callable[[Context], Sequence[Path]]
    always_run: bool = False


@dataclass(frozen=True)
class StageResult:
    """What happened to one stage in a run.

    Attributes:
        name: The stage.
        ran: Whether it ran.
        reason: Why it ran, or "unchanged".
        fingerprint: Its fingerprint in this run.
    """

    name: str
    ran: bool
    reason: str
    fingerprint: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _setting(settings: Settings, key: str) -> Any:
    value: Any = settings
    for part in key.split("."):
        value = getattr(value, part)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _code_hash(package_dir: Path, code: Sequence[str]) -> str:
    files: list[Path] = []
    for entry in code:
        path = package_dir / entry
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    digest = hashlib.sha256()
    for path in sorted(set(files)):
        digest.update(path.relative_to(package_dir).as_posix().encode())
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode() if path.is_file() else b"missing")
        digest.update(b"\0")
    return digest.hexdigest()


def fingerprint(
    stage: Stage, context: Context, upstream_fingerprints: Mapping[str, str]
) -> str:
    """Return the SHA256 over everything that should rerun the stage when changed."""
    payload = {
        "name": stage.name,
        "settings": {k: _setting(context.settings, k) for k in stage.settings_keys},
        "upstream": {k: upstream_fingerprints[k] for k in stage.upstream},
        "code": _code_hash(context.package_dir, stage.code),
        "inputs": {
            str(p): _sha256_file(p) if p.is_file() else "missing"
            for p in stage.inputs(context)
        },
        "uv_lock": _sha256_file(context.uv_lock),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _state_path(context: Context, name: str) -> Path:
    return context.state_dir / f"{name}.json"


def _read_state(context: Context, name: str) -> str | None:
    path = _state_path(context, name)
    if not path.is_file():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    value = state.get("fingerprint")
    return value if isinstance(value, str) else None


def _write_state(context: Context, name: str, value: str) -> None:
    context.state_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(context, name)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=context.state_dir,
        prefix=f".{path.name}.",
        suffix=".part",
        delete=False,
        encoding="utf-8",
    ) as f:
        temp = Path(f.name)
        json.dump({"name": name, "fingerprint": value}, f, indent=2, sort_keys=True)
        f.write("\n")
    temp.replace(path)


def run_pipeline(
    stages: Sequence[Stage], context: Context, from_stage: str | None = None
) -> list[StageResult]:
    """Run the stages in order, skipping those whose fingerprint is unchanged.

    Args:
        stages: The stages, upstream before downstream.
        context: Settings and folders.
        from_stage: Force this stage and every later one to rerun.

    Returns:
        One result per stage.

    Raises:
        UnknownStageError: If `from_stage` names no stage, before anything runs.
        StageFailedError: When a stage raises; later stages do not run.
    """
    names = [s.name for s in stages]
    if from_stage is not None and from_stage not in names:
        raise UnknownStageError(f"no stage {from_stage!r}; stages: {', '.join(names)}")
    forced_from = names.index(from_stage) if from_stage is not None else len(names)

    fingerprints: dict[str, str] = {}
    results: list[StageResult] = []
    for index, stage in enumerate(stages):
        value = fingerprint(stage, context, fingerprints)
        fingerprints[stage.name] = value
        previous = _read_state(context, stage.name)
        if index >= forced_from:
            reason = f"--from {from_stage}"
        elif stage.always_run:
            reason = "always runs"
        elif previous is None:
            reason = "no earlier run"
        elif previous != value:
            reason = "fingerprint changed"
        elif not all(p.exists() for p in stage.outputs(context)):
            reason = "output missing"
        else:
            results.append(StageResult(stage.name, False, "unchanged", value))
            continue
        log.info("running %s (%s)", stage.name, reason)
        try:
            stage.run(context)
        except Exception as error:
            raise StageFailedError(f"stage {stage.name} failed: {error}") from error
        _write_state(context, stage.name, value)
        results.append(StageResult(stage.name, True, reason, value))
    return results


# The real stages. Code folders per the Phase 2 plan, review focus 5.
_SHARED_CODE = ("constants.py", "config.py", "paths.py")


def _raw_files(context: Context) -> tuple[Path, ...]:
    raw_dir = context.settings.data.raw_dir
    return tuple(raw_dir / name for name in sorted(load_checksums(CHECKSUM_MANIFEST)))


def _run_download(context: Context) -> None:
    data = context.settings.data
    download(data.raw_dir, load_checksums(CHECKSUM_MANIFEST), data.sources)


def _prepared_files(context: Context) -> tuple[Path, ...]:
    folder = context.settings.data.prepared_dir
    ds1 = load_splits(SPLITS_MANIFEST).ds1
    return (*(folder / f"{r}.npz" for r in ds1), folder / FLOOR_HITS_FILE)


def _run_prepare(context: Context) -> None:
    prepare_ds1(
        context.settings, load_splits(SPLITS_MANIFEST), load_subjects(SUBJECTS_MANIFEST)
    )


def _run_check_folds(context: Context) -> None:
    check_folds(
        FOLDS_JSON,
        FOLDS_PIN,
        load_splits(SPLITS_MANIFEST),
        load_subjects(SUBJECTS_MANIFEST),
    )


PIPELINE: tuple[Stage, ...] = (
    Stage(
        name="download",
        settings_keys=("data.raw_dir", "data.sources"),
        upstream=(),
        code=("data", *_SHARED_CODE),
        # The cached files are inputs, so a file changed on disk reruns the
        # download stage, whose checksum check then stops the run (DATA-02).
        inputs=lambda context: (CHECKSUM_MANIFEST, *_raw_files(context)),
        run=_run_download,
        outputs=_raw_files,
    ),
    Stage(
        name="prepare",
        settings_keys=("data.raw_dir", "data.prepared_dir"),
        upstream=("download",),
        code=("data", "signal", *_SHARED_CODE),
        inputs=lambda context: (SPLITS_MANIFEST, SUBJECTS_MANIFEST),
        run=_run_prepare,
        outputs=_prepared_files,
    ),
    Stage(
        name="check-folds",
        settings_keys=(),
        upstream=(),
        code=("data", *_SHARED_CODE),
        inputs=lambda context: (
            FOLDS_JSON,
            FOLDS_PIN,
            SPLITS_MANIFEST,
            SUBJECTS_MANIFEST,
        ),
        run=_run_check_folds,
        outputs=lambda context: (),
        # C1, E4: rebuild checks the folds every time and never makes them.
        always_run=True,
    ),
)

# OPS-01's later stages with the phase that builds each.
PLANNED: tuple[tuple[str, int], ...] = (
    ("cross-validate", 3),
    ("select", 4),
    ("exhibit", 4),
    ("train-final", 4),
    ("export", 5),
    ("reproduce-test", 5),
    ("build-demo-data", 6),
)
