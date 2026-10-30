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

import numpy as np
from numpy.typing import NDArray

from heartbeat.config import Settings
from heartbeat.constants import CNN_SEEDS, CNN_WIDTHS
from heartbeat.data.download import download
from heartbeat.data.folds import Folds, check_folds
from heartbeat.data.loader import BeatTable, load_ds1, load_ds1_traces
from heartbeat.data.manifests import load_checksums, load_splits, load_subjects
from heartbeat.data.prepare import FLOOR_HITS_FILE, prepare_ds1
from heartbeat.paths import (
    CHECKSUM_MANIFEST,
    FOLDS_JSON,
    FOLDS_PIN,
    REPO_ROOT,
    RESULTS_DIR,
    RUNS_DIR,
    SPLITS_MANIFEST,
    SUBJECTS_MANIFEST,
)
from heartbeat.results import write_result
from heartbeat.runs import RunFolder, create_run
from heartbeat.train.cnn_cv import (
    MissingRunError,
    curves_payload,
    data_label,
    run_cnn_cv,
)
from heartbeat.train.cv import oof_predictions, run_baseline
from heartbeat.train.exhibit import run_exhibit
from heartbeat.train.final import final_payload, train_final
from heartbeat.train.loop import cnn_spec
from heartbeat.train.select import (
    EpochEdgeError,
    cnn_summary,
    epoch_curves,
    select_config,
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


CV_BASELINE_RESULT = "cv_baseline"


def _run_cross_validate(context: Context) -> None:
    # Rule 5: the only writer of results/; the run folder holds everything else.
    splits = load_splits(SPLITS_MANIFEST)
    subjects = load_subjects(SUBJECTS_MANIFEST)
    folds = check_folds(FOLDS_JSON, FOLDS_PIN, splits, subjects)
    beats = load_ds1(context.settings.data.prepared_dir, splits, subjects)
    folds_sha256 = _sha256_file(FOLDS_JSON)
    run, summary = run_baseline(
        context.settings, beats, folds, folds_sha256, root=RUNS_DIR
    )
    path = write_result(CV_BASELINE_RESULT, summary, run)
    log.info("wrote %s from run %s", path, run.name)


CV_CNN_CURVES_RESULT = "cv_cnn_curves"
SELECTION_RESULT = "selection"
CV_CNN_RESULT = "cv_cnn"
EXHIBIT_RESULT = "exhibit"
TRAIN_FINAL_RESULT = "train_final"


def _ds1(settings: Settings) -> tuple[BeatTable, Folds, str]:
    splits = load_splits(SPLITS_MANIFEST)
    subjects = load_subjects(SUBJECTS_MANIFEST)
    folds = check_folds(FOLDS_JSON, FOLDS_PIN, splits, subjects)
    beats = load_ds1(settings.data.prepared_dir, splits, subjects)
    return beats, folds, _sha256_file(FOLDS_JSON)


def _traces(settings: Settings) -> dict[str, NDArray[np.int16]]:
    return load_ds1_traces(
        settings.data.prepared_dir,
        load_splits(SPLITS_MANIFEST),
        load_subjects(SUBJECTS_MANIFEST),
    )


def _result(results_dir: Path, name: str) -> dict[str, Any]:
    path = results_dir / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; run `uv run heartbeat rebuild`")
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def run_cnn_cv_all(
    settings: Settings, root: Path = RUNS_DIR, repo: Path = REPO_ROOT
) -> tuple[RunFolder, dict[str, Any]]:
    """Cross-validate the CNN at every width and seed (MODEL-04, design call 8).

    One run folder per width and seed, then one `cv-cnn` run folder holding
    the curves payload (pooled confusions per epoch and the run names).
    """
    beats, folds, folds_sha256 = _ds1(settings)
    traces = _traces(settings)
    device = settings.train.cv_device
    entries = []
    for width in CNN_WIDTHS:
        for seed in CNN_SEEDS:
            _, entry = run_cnn_cv(
                settings,
                beats,
                traces,
                folds,
                folds_sha256,
                width,
                seed,
                device,
                root=root,
                repo=repo,
            )
            entries.append(entry)
    payload = curves_payload(entries, device, folds_sha256)
    extra = {"runs": [e["run"] for e in entries], "folds_sha256": folds_sha256}
    with create_run("cv-cnn", settings, extra, root=root, repo=repo) as run:
        run.write_json("metrics", payload)
    return run, payload


def run_select_all(
    settings: Settings,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
    results_dir: Path = RESULTS_DIR,
) -> tuple[RunFolder, dict[str, Any], dict[str, Any]]:
    """Select width and epoch, and summarize the CNN (settlings 2 and 3).

    Reads the committed curves and baseline results and the run folders they
    name. Writes `selection.json` and `cv_cnn.json` into a new `select` run
    folder; on an epoch-edge stop it writes the selection there anyway, for
    the ledger, and raises.

    Raises:
        EpochEdgeError: If the pick is epoch 36 or later (settling 2).
        MissingRunError: If a named run folder is missing.
        ValueError: If the curves came from another fold file.
    """
    curves_result = _result(results_dir, CV_CNN_CURVES_RESULT)
    baseline_result = _result(results_dir, CV_BASELINE_RESULT)
    beats, _, folds_sha256 = _ds1(settings)
    for name, result in (("curves", curves_result), ("baseline", baseline_result)):
        if result["folds_sha256"] != folds_sha256:
            raise ValueError(f"the {name} results came from another fold file")
    extra = {
        "curves_run": curves_result["run"],
        "baseline_run": baseline_result["run"],
    }
    curves = epoch_curves(curves_result)
    with create_run("select", settings, extra, root=root, repo=repo) as run:
        try:
            selection = select_config(curves)
        except EpochEdgeError as error:
            run.write_json(
                "selection", {**error.selection.payload(), "stopped": str(error)}
            )
            raise
        oof_path = root / baseline_result["run"] / "oof.npz"
        if not oof_path.is_file():
            raise MissingRunError(
                f"{oof_path} missing; rerun `uv run heartbeat rebuild --from "
                "cross-validate`"
            )
        with np.load(oof_path, allow_pickle=False) as oof:
            same = np.array_equal(oof["sample"], beats.sample) and np.array_equal(
                oof["record"], beats.record_id
            )
            if not same:
                raise ValueError(f"{oof_path} was made from other beats")
            baseline = oof_predictions(
                "baseline",
                oof["raw_logits"],
                oof["fold"],
                baseline_result["class_weights"],
                beats.beat_class,
            )
        if baseline.temperature != baseline_result["calibration"]["temperature"]:
            raise ValueError("the baseline run does not reproduce its results file")
        device = str(curves_result["device"])
        run_paths = {s: root / curves.runs[(selection.width, s)] for s in CNN_SEEDS}
        summary = cnn_summary(
            selection, run_paths, beats, baseline, folds_sha256, device
        )
        selection_payload = {
            **selection.payload(),
            "data": data_label(device),
            "temperatures": summary["temperatures"],
            "curves_run": curves_result["run"],
            "baseline_run": baseline_result["run"],
            "folds_sha256": folds_sha256,
        }
        run.write_json("selection", selection_payload)
        run.write_json("cv_cnn", summary)
    return run, selection_payload, summary


def run_exhibit_all(
    settings: Settings,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
    results_dir: Path = RESULTS_DIR,
) -> tuple[RunFolder, dict[str, Any]]:
    """The exhibit at the committed selection and chosen C (C5)."""
    selection = _result(results_dir, SELECTION_RESULT)
    baseline = _result(results_dir, CV_BASELINE_RESULT)
    curves = _result(results_dir, CV_CNN_CURVES_RESULT)
    width = float(selection["width"])
    device = str(curves["device"])
    cv_runs = {
        int(e["seed"]): root / e["run"]
        for e in curves["runs"]
        if float(e["width"]) == width
    }
    beats, folds, folds_sha256 = _ds1(settings)
    traces = _traces(settings)
    return run_exhibit(
        settings,
        width=width,
        epoch=int(selection["epoch"]),
        chosen_c=float(baseline["chosen_c"]),
        beats=beats,
        folds=folds,
        folds_sha256=folds_sha256,
        cv_runs=cv_runs,
        cnn=cnn_spec(traces, device),
        device=device,
        root=root,
        repo=repo,
    )


def run_final_all(
    settings: Settings,
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
    results_dir: Path = RESULTS_DIR,
) -> tuple[RunFolder, dict[str, Any]]:
    """Train the three final models on CPU at the committed selection (C6)."""
    selection = _result(results_dir, SELECTION_RESULT)
    width = float(selection["width"])
    epochs = int(selection["epoch"])
    temperatures = {int(t["seed"]): t["temperature"] for t in selection["temperatures"]}
    beats, _, _ = _ds1(settings)
    traces = _traces(settings)
    models = [
        train_final(
            settings,
            beats,
            traces,
            width=width,
            epochs=epochs,
            seed=seed,
            temperature=float(temperatures[seed]),
            root=root,
            repo=repo,
        )
        for seed in CNN_SEEDS
    ]
    payload = final_payload(models, width=width, epochs=epochs, repo=repo)
    extra = {"runs": [m.run for m in models], "selection_run": selection["run"]}
    with create_run("train-final", settings, extra, root=root, repo=repo) as run:
        run.write_json("metrics", payload)
    return run, payload


def _run_cross_validate_cnn(context: Context) -> None:
    run, payload = run_cnn_cv_all(context.settings)
    write_result(CV_CNN_CURVES_RESULT, payload, run)


def _run_select(context: Context) -> None:
    run, selection, summary = run_select_all(context.settings)
    write_result(SELECTION_RESULT, selection, run)
    write_result(CV_CNN_RESULT, summary, run)


def _run_exhibit(context: Context) -> None:
    run, payload = run_exhibit_all(context.settings)
    write_result(EXHIBIT_RESULT, payload, run)


def _run_train_final(context: Context) -> None:
    run, payload = run_final_all(context.settings)
    write_result(TRAIN_FINAL_RESULT, payload, run)


# Code folders of every stage that trains or scores a model.
_TRAINING_CODE = (
    "data",
    "signal",
    "models",
    "train",
    "evaluate",
    "runs.py",
    "results.py",
    *_SHARED_CODE,
)


def _fold_inputs(context: Context) -> tuple[Path, ...]:
    return (FOLDS_JSON, FOLDS_PIN, SPLITS_MANIFEST, SUBJECTS_MANIFEST)


def _results(*names: str) -> Callable[[Context], tuple[Path, ...]]:
    return lambda context: tuple(RESULTS_DIR / f"{n}.json" for n in names)


def _inputs_and_results(*names: str) -> Callable[[Context], tuple[Path, ...]]:
    return lambda context: (*_fold_inputs(context), *_results(*names)(context))


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
    Stage(
        name="cross-validate",
        settings_keys=("data.prepared_dir",),
        upstream=("prepare", "check-folds"),
        code=(
            "data",
            "signal",
            "models",
            "train",
            "evaluate",
            "runs.py",
            "results.py",
            *_SHARED_CODE,
        ),
        inputs=lambda context: (
            FOLDS_JSON,
            FOLDS_PIN,
            SPLITS_MANIFEST,
            SUBJECTS_MANIFEST,
        ),
        run=_run_cross_validate,
        outputs=lambda context: (RESULTS_DIR / f"{CV_BASELINE_RESULT}.json",),
    ),
    Stage(
        name="cross-validate-cnn",
        settings_keys=("data.prepared_dir", "train.cv_device"),
        upstream=("prepare", "check-folds"),
        code=_TRAINING_CODE,
        inputs=_fold_inputs,
        run=_run_cross_validate_cnn,
        outputs=_results(CV_CNN_CURVES_RESULT),
    ),
    Stage(
        name="select",
        settings_keys=("data.prepared_dir",),
        upstream=("cross-validate", "cross-validate-cnn"),
        code=_TRAINING_CODE,
        inputs=_inputs_and_results(CV_CNN_CURVES_RESULT, CV_BASELINE_RESULT),
        run=_run_select,
        outputs=_results(SELECTION_RESULT, CV_CNN_RESULT),
    ),
    Stage(
        name="exhibit",
        settings_keys=("data.prepared_dir", "train.cv_device"),
        upstream=("select",),
        code=_TRAINING_CODE,
        inputs=_inputs_and_results(
            SELECTION_RESULT, CV_CNN_CURVES_RESULT, CV_BASELINE_RESULT
        ),
        run=_run_exhibit,
        outputs=_results(EXHIBIT_RESULT),
    ),
    Stage(
        name="train-final",
        settings_keys=("data.prepared_dir",),
        upstream=("select",),
        code=_TRAINING_CODE,
        inputs=_inputs_and_results(SELECTION_RESULT),
        run=_run_train_final,
        outputs=_results(TRAIN_FINAL_RESULT),
    ),
)

# OPS-01's later stages with the phase that builds each.
PLANNED: tuple[tuple[str, int], ...] = (
    ("export", 5),
    ("reproduce-test", 5),
    ("build-demo-data", 6),
)
