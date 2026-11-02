"""R28, OPS-02, E4: without a freeze record `rebuild` stops before DS2.

Every stage but reproduce-test is replaced by a recorder; reproduce-test runs
for real against a bundle with no freeze record. Spies on every way to read a
record's signal or annotations show no DS2 record is touched.
"""

import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import wfdb

from heartbeat import cli
from heartbeat import stages as stages_module
from heartbeat.cli import main
from heartbeat.data import prepare as prepare_module
from heartbeat.data import records as records_module
from heartbeat.data.manifests import Splits
from heartbeat.sealed import run as sealed_run_module
from heartbeat.stages import NO_FREEZE_MESSAGE, PIPELINE, Context


@pytest.mark.rule("R28")
def test_rebuild_without_a_freeze_record_reads_no_ds2_record(
    tmp_path: Path,
    splits: Splits,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    touched: list[str] = []

    def spy(name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> Any:
            touched.append(f"{name}: {args[:2]}")
            raise AssertionError(f"{name} called during the stop")

        return record

    for module, name in (
        (wfdb, "rdrecord"),
        (wfdb, "rdann"),
        (wfdb, "rdsamp"),
        (records_module, "read_record"),
        (records_module, "read_annotations"),
        (prepare_module, "read_record"),
        (prepare_module, "prepare_record"),
        (sealed_run_module, "prepare_in_memory"),
        (stages_module, "run_sealed"),
    ):
        monkeypatch.setattr(module, name, spy(name))
    ran: list[str] = []

    def recorder(name: str) -> Callable[[Context], None]:
        def run(context: Context) -> None:
            ran.append(name)

        return run

    stages = tuple(
        stage
        if stage.name == "reproduce-test"
        else replace(stage, run=recorder(stage.name))
        for stage in PIPELINE
    )
    models = tmp_path / "models" / "heartbeat-v1"
    models.mkdir(parents=True)
    monkeypatch.setattr(stages_module, "MODELS_DIR", models)
    monkeypatch.setattr(stages_module, "TEST_LOG", tmp_path / "test_runs.jsonl")
    monkeypatch.setattr(stages_module, "TEST_REPORTS_DIR", tmp_path / "test_runs")
    base = cli.rebuild_context()
    monkeypatch.setattr(cli, "PIPELINE", stages)
    monkeypatch.setattr(
        cli,
        "rebuild_context",
        lambda exact=False: Context(
            settings=base.settings,
            package_dir=base.package_dir,
            state_dir=tmp_path / "stages",
            uv_lock=base.uv_lock,
        ),
    )
    with caplog.at_level(logging.INFO, logger="heartbeat"):
        assert main(["rebuild"]) == 0
    assert touched == []
    assert NO_FREEZE_MESSAGE in caplog.text
    assert ran == [s.name for s in PIPELINE if s.name != "reproduce-test"]
    out = capsys.readouterr().out
    # Phase 7 A3: no longer always_run, and the state folder is fresh.
    assert "reproduce-test: ran (no earlier run)" in out
    assert f"stopped after {PIPELINE[-1].name}" in out
    assert not (tmp_path / "test_runs.jsonl").exists()
    assert set(splits.ds2)
