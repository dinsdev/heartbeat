"""E4, OPS-01 (partial): the stage framework, fingerprints and `--from`."""

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from heartbeat import cli
from heartbeat.cli import main, rebuild_context
from heartbeat.config import DataSettings, FoldSettings, Settings, TrainSettings
from heartbeat.paths import (
    FOLDS_JSON,
    FOLDS_PIN,
    RESULTS_DIR,
    SPLITS_MANIFEST,
    SUBJECTS_MANIFEST,
)
from heartbeat.stages import (
    PIPELINE,
    PLANNED,
    Context,
    Stage,
    StageResult,
    UnknownStageError,
    fingerprint,
    run_pipeline,
)


class Counting:
    """Builds three chained stages whose runs are counted."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.runs: Counter[str] = Counter()
        self.fail: set[str] = set()
        (root / "pkg" / "a").mkdir(parents=True)
        (root / "pkg" / "b").mkdir()
        (root / "pkg" / "a" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (root / "pkg" / "b" / "mod.py").write_text("y = 1\n", encoding="utf-8")
        (root / "pkg" / "shared.py").write_text("z = 1\n", encoding="utf-8")
        (root / "input.txt").write_text("first input\n", encoding="utf-8")
        (root / "uv.lock").write_text("lock\n", encoding="utf-8")
        (root / "out").mkdir()

    def context(self, seed: int = 1) -> Context:
        settings = Settings(
            data=DataSettings(
                raw_dir=self.root / "raw",
                prepared_dir=self.root / "prepared",
                sources=("https://a.example/",),
            ),
            folds=FoldSettings(seed=seed),
            train=TrainSettings(cv_device="cpu"),
        )
        return Context(
            settings=settings,
            package_dir=self.root / "pkg",
            state_dir=self.root / "stages",
            uv_lock=self.root / "uv.lock",
        )

    def _run(self, name: str) -> Callable[[Context], None]:
        def run(context: Context) -> None:
            if name in self.fail:
                raise RuntimeError(f"{name} failed")
            self.runs[name] += 1
            (self.root / "out" / f"{name}.txt").write_text(
                f"{self.runs[name]}\n", encoding="utf-8"
            )

        return run

    def _out(self, name: str) -> Callable[[Context], Sequence[Path]]:
        return lambda context: (self.root / "out" / f"{name}.txt",)

    def stages(self) -> tuple[Stage, ...]:
        return (
            Stage(
                name="first",
                settings_keys=("data.sources",),
                upstream=(),
                code=("a", "shared.py"),
                inputs=lambda context: (self.root / "input.txt",),
                run=self._run("first"),
                outputs=self._out("first"),
            ),
            Stage(
                name="second",
                settings_keys=("folds.seed",),
                upstream=("first",),
                code=("b", "shared.py"),
                inputs=lambda context: (),
                run=self._run("second"),
                outputs=self._out("second"),
            ),
            Stage(
                name="third",
                settings_keys=(),
                upstream=("second",),
                code=("b",),
                inputs=lambda context: (),
                run=self._run("third"),
                outputs=self._out("third"),
            ),
        )

    def run(self, seed: int = 1, from_stage: str | None = None) -> list[StageResult]:
        return run_pipeline(self.stages(), self.context(seed), from_stage=from_stage)


def _ran(results: list[StageResult]) -> list[str]:
    return [r.name for r in results if r.ran]


@pytest.fixture
def counting(tmp_path: Path) -> Counting:
    return Counting(tmp_path)


def test_first_run_runs_everything_and_records_state(counting: Counting) -> None:
    assert _ran(counting.run()) == ["first", "second", "third"]
    state = json.loads((counting.root / "stages" / "first.json").read_text("utf-8"))
    assert state["name"] == "first"
    assert len(state["fingerprint"]) == 64


def test_second_run_skips_every_stage(counting: Counting) -> None:
    counting.run()
    results = counting.run()
    assert _ran(results) == []
    assert all(r.reason == "unchanged" for r in results)
    assert counting.runs == Counter(first=1, second=1, third=1)


def test_changed_setting_reruns_that_stage_and_after(counting: Counting) -> None:
    counting.run()
    assert _ran(counting.run(seed=2)) == ["second", "third"]


def test_changed_input_file_reruns_that_stage_and_after(counting: Counting) -> None:
    counting.run()
    (counting.root / "input.txt").write_text("second input\n", encoding="utf-8")
    assert _ran(counting.run()) == ["first", "second", "third"]


def test_changed_code_file_reruns_that_stage_and_after(counting: Counting) -> None:
    counting.run()
    (counting.root / "pkg" / "b" / "mod.py").write_text("y = 2\n", encoding="utf-8")
    assert _ran(counting.run()) == ["second", "third"]


def test_new_code_file_in_a_declared_folder_reruns(counting: Counting) -> None:
    counting.run()
    (counting.root / "pkg" / "a" / "new.py").write_text("w = 0\n", encoding="utf-8")
    assert _ran(counting.run()) == ["first", "second", "third"]


def test_code_outside_the_declared_folders_does_not_rerun(counting: Counting) -> None:
    counting.run()
    (counting.root / "pkg" / "other.py").write_text("v = 0\n", encoding="utf-8")
    assert _ran(counting.run()) == []


def test_changed_lockfile_reruns_everything(counting: Counting) -> None:
    counting.run()
    (counting.root / "uv.lock").write_text("lock 2\n", encoding="utf-8")
    assert _ran(counting.run()) == ["first", "second", "third"]


def test_changed_upstream_fingerprint_reruns_downstream(counting: Counting) -> None:
    counting.run()
    (counting.root / "pkg" / "a" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    # Only `first` declares folder a; second and third rerun through the chain.
    assert _ran(counting.run()) == ["first", "second", "third"]


def test_deleting_an_output_reruns_its_stage(counting: Counting) -> None:
    counting.run()
    (counting.root / "out" / "second.txt").unlink()
    results = counting.run()
    assert _ran(results) == ["second"]
    assert next(r for r in results if r.name == "second").reason == "output missing"


def test_from_reruns_that_stage_and_everything_after(counting: Counting) -> None:
    counting.run()
    assert _ran(counting.run(from_stage="second")) == ["second", "third"]


def test_unknown_from_raises(counting: Counting) -> None:
    with pytest.raises(UnknownStageError, match="nope"):
        counting.run(from_stage="nope")
    assert counting.runs == Counter()


def test_always_run_stage_runs_every_time(counting: Counting) -> None:
    stages = (
        *counting.stages(),
        Stage(
            name="check",
            settings_keys=(),
            upstream=(),
            code=(),
            inputs=lambda context: (),
            run=counting._run("check"),
            outputs=lambda context: (),
            always_run=True,
        ),
    )
    run_pipeline(stages, counting.context())
    results = run_pipeline(stages, counting.context())
    assert _ran(results) == ["check"]
    assert counting.runs["check"] == 2


def test_failed_stage_leaves_its_old_state_untouched(counting: Counting) -> None:
    counting.run()
    state = counting.root / "stages" / "second.json"
    before = state.read_text(encoding="utf-8")
    counting.fail.add("second")
    with pytest.raises(RuntimeError, match="second failed"):
        counting.run(seed=2)
    assert state.read_text(encoding="utf-8") == before
    # The failed stage and everything after it rerun next time.
    counting.fail.clear()
    assert _ran(counting.run(seed=2)) == ["second", "third"]


def test_fingerprint_is_stable_and_sensitive(counting: Counting) -> None:
    first = counting.stages()[0]
    context = counting.context()
    assert fingerprint(first, context, {}) == fingerprint(first, context, {})
    second = counting.stages()[1]
    assert fingerprint(second, context, {"first": "a" * 64}) != fingerprint(
        second, context, {"first": "b" * 64}
    )


def test_missing_input_file_has_its_own_fingerprint(counting: Counting) -> None:
    first = counting.stages()[0]
    context = counting.context()
    present = fingerprint(first, context, {})
    (counting.root / "input.txt").unlink()
    assert fingerprint(first, context, {}) != present


# The real pipeline


def test_pipeline_has_the_eight_built_stages_in_order() -> None:
    # Phase 4 design call 8: four stages after the baseline's cross-validate.
    assert [s.name for s in PIPELINE] == [
        "download",
        "prepare",
        "check-folds",
        "cross-validate",
        "cross-validate-cnn",
        "select",
        "exhibit",
        "train-final",
    ]
    by_name = {s.name: s for s in PIPELINE}
    assert by_name["check-folds"].always_run
    assert by_name["prepare"].upstream == ("download",)
    assert by_name["cross-validate"].upstream == ("prepare", "check-folds")
    assert by_name["cross-validate-cnn"].upstream == ("prepare", "check-folds")
    assert by_name["select"].upstream == ("cross-validate", "cross-validate-cnn")
    assert by_name["exhibit"].upstream == ("select",)
    assert by_name["train-final"].upstream == ("select",)
    assert not any(s.always_run for s in PIPELINE if s.name != "check-folds")
    assert by_name["cross-validate-cnn"].settings_keys == (
        "data.prepared_dir",
        "train.cv_device",
    )


def test_pipeline_code_folders_match_the_plan() -> None:
    shared = {"constants.py", "config.py", "paths.py"}
    training = {
        "data",
        "signal",
        "models",
        "train",
        "evaluate",
        "runs.py",
        "results.py",
        *shared,
    }
    by_name = {s.name: set(s.code) for s in PIPELINE}
    assert by_name == {
        "download": {"data", *shared},
        "prepare": {"data", "signal", *shared},
        "check-folds": {"data", *shared},
        "cross-validate": training,
        "cross-validate-cnn": training,
        "select": training,
        "exhibit": training,
        "train-final": training,
    }


def test_cross_validate_reads_the_folds_its_pin_and_the_manifests() -> None:
    stage = {s.name: s for s in PIPELINE}["cross-validate"]
    context = rebuild_context()
    assert set(stage.inputs(context)) == {
        FOLDS_JSON,
        FOLDS_PIN,
        SPLITS_MANIFEST,
        SUBJECTS_MANIFEST,
    }
    assert list(stage.outputs(context)) == [RESULTS_DIR / "cv_baseline.json"]


def test_cross_validate_reruns_when_its_code_or_inputs_change(
    tmp_path: Path,
) -> None:
    # The real stage's declarations over a copied package and copied inputs.
    stage = {s.name: s for s in PIPELINE}["cross-validate"]
    package = tmp_path / "pkg"
    for entry in (*stage.code, "cli.py"):
        target = package / entry
        if entry.endswith(".py"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {entry}\n", encoding="utf-8")
        else:
            target.mkdir(parents=True)
            (target / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock\n", encoding="utf-8")
    inputs = [tmp_path / f"input{k}" for k in range(2)]
    for path in inputs:
        path.write_text("v1\n", encoding="utf-8")
    runs: list[int] = []
    local = replace(
        stage,
        upstream=(),
        inputs=lambda context: inputs,
        run=lambda context: runs.append(1),
        outputs=lambda context: (),
    )
    context = Context(
        settings=rebuild_context().settings,
        package_dir=package,
        state_dir=tmp_path / "stages",
        uv_lock=tmp_path / "uv.lock",
    )

    def ran() -> bool:
        before = len(runs)
        run_pipeline((local,), context)
        return len(runs) > before

    assert ran()
    assert not ran()
    for folder in ("models", "train", "evaluate"):
        (package / folder / "mod.py").write_text(f"x = '{folder}'\n", "utf-8")
        assert ran(), folder
        assert not ran()
    (package / "results.py").write_text("# changed\n", encoding="utf-8")
    assert ran()
    inputs[0].write_text("v2\n", encoding="utf-8")
    assert ran()
    (package / "cli.py").write_text("# not declared\n", encoding="utf-8")
    assert not ran()


FOLD_INPUTS = {FOLDS_JSON, FOLDS_PIN, SPLITS_MANIFEST, SUBJECTS_MANIFEST}


@pytest.mark.parametrize(
    ("name", "results_in", "results_out"),
    [
        ("cross-validate-cnn", set(), ["cv_cnn_curves"]),
        ("select", {"cv_cnn_curves", "cv_baseline"}, ["selection", "cv_cnn"]),
        ("exhibit", {"selection", "cv_cnn_curves", "cv_baseline"}, ["exhibit"]),
        ("train-final", {"selection"}, ["train_final"]),
    ],
)
def test_the_cnn_stages_read_the_folds_and_write_their_results(
    name: str, results_in: set[str], results_out: list[str]
) -> None:
    stage = {s.name: s for s in PIPELINE}[name]
    context = rebuild_context()
    assert set(stage.inputs(context)) == FOLD_INPUTS | {
        RESULTS_DIR / f"{r}.json" for r in results_in
    }
    assert list(stage.outputs(context)) == [
        RESULTS_DIR / f"{r}.json" for r in results_out
    ]


@pytest.mark.parametrize(
    "name", ["cross-validate-cnn", "select", "exhibit", "train-final"]
)
def test_the_cnn_stages_rerun_when_code_inputs_or_the_device_change(
    name: str, tmp_path: Path
) -> None:
    stage = {s.name: s for s in PIPELINE}[name]
    package = tmp_path / "pkg"
    for entry in (*stage.code, "cli.py"):
        target = package / entry
        if entry.endswith(".py"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {entry}\n", encoding="utf-8")
        else:
            target.mkdir(parents=True)
            (target / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock\n", encoding="utf-8")
    inputs = [tmp_path / "input0"]
    inputs[0].write_text("v1\n", encoding="utf-8")
    runs: list[int] = []
    local = replace(
        stage,
        upstream=(),
        inputs=lambda context: inputs,
        run=lambda context: runs.append(1),
        outputs=lambda context: (),
    )
    base = rebuild_context().settings

    def ran(device: str = "mps") -> bool:
        context = Context(
            settings=replace(base, train=TrainSettings(cv_device=device)),
            package_dir=package,
            state_dir=tmp_path / "stages",
            uv_lock=tmp_path / "uv.lock",
        )
        before = len(runs)
        run_pipeline((local,), context)
        return len(runs) > before

    assert ran()
    assert not ran()
    (package / "train" / "mod.py").write_text("x = 'train'\n", "utf-8")
    assert ran()
    inputs[0].write_text("v2\n", encoding="utf-8")
    assert ran()
    (package / "cli.py").write_text("# not declared\n", encoding="utf-8")
    assert not ran()
    if "train.cv_device" in stage.settings_keys:
        assert ran("cpu")


@pytest.mark.parametrize(
    ("name", "function", "results"),
    [
        ("cross-validate-cnn", "run_cnn_cv_all", ["cv_cnn_curves"]),
        ("select", "run_select_all", ["selection", "cv_cnn"]),
        ("exhibit", "run_exhibit_all", ["exhibit"]),
        ("train-final", "run_final_all", ["train_final"]),
    ],
)
def test_each_cnn_stage_writes_its_results_from_its_run(
    name: str,
    function: str,
    results: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from heartbeat import stages as stages_module

    run = object()
    payloads = [{"which": r} for r in results]
    monkeypatch.setattr(stages_module, function, lambda settings: (run, *payloads))
    written: list[tuple[str, object, object]] = []

    def spy(result: str, payload: object, source: object) -> Path:
        written.append((result, payload, source))
        return Path(result)

    monkeypatch.setattr(stages_module, "write_result", spy)
    stage = {s.name: s for s in PIPELINE}[name]
    stage.run(rebuild_context())
    assert written == [(r, p, run) for r, p in zip(results, payloads, strict=True)]


def test_planned_stages_follow_with_their_phases() -> None:
    assert list(PLANNED) == [
        ("export", 5),
        ("reproduce-test", 5),
        ("build-demo-data", 6),
    ]


# rebuild through the CLI


def _patch_rebuild(counting: Counting, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "PIPELINE", counting.stages())
    monkeypatch.setattr(cli, "rebuild_context", lambda: counting.context())


def test_rebuild_stops_after_the_last_built_stage_and_names_the_next(
    counting: Counting,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_rebuild(counting, monkeypatch)
    assert main(["rebuild"]) == 0
    out = capsys.readouterr().out
    assert "first: ran" in out
    assert "next stage export (Phase 5)" in out
    assert main(["rebuild"]) == 0
    assert "first: skipped (unchanged)" in capsys.readouterr().out


def test_rebuild_from_and_exact_parse(
    counting: Counting,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_rebuild(counting, monkeypatch)
    main(["rebuild"])
    capsys.readouterr()
    assert main(["rebuild", "--from", "second", "--exact"]) == 0
    out = capsys.readouterr().out
    assert "first: skipped" in out
    assert "second: ran (--from second)" in out


def test_rebuild_unknown_from_exits_nonzero(
    counting: Counting,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_rebuild(counting, monkeypatch)
    assert main(["rebuild", "--from", "nope"]) == 2
    assert "nope" in capsys.readouterr().err


def test_rebuild_from_a_planned_stage_says_it_is_not_built(
    counting: Counting,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_rebuild(counting, monkeypatch)
    assert main(["rebuild", "--from", "export"]) == 2
    assert "Phase 5" in capsys.readouterr().err


def test_rebuild_exits_1_when_a_stage_fails(
    counting: Counting,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_rebuild(counting, monkeypatch)
    counting.fail.add("third")
    assert main(["rebuild"]) == 1
    assert "third failed" in capsys.readouterr().err


def test_context_replace_keeps_paths(counting: Counting) -> None:
    context = counting.context()
    assert replace(context, state_dir=counting.root / "x").uv_lock == context.uv_lock
