"""`heartbeat build-demo-data` on synthetic DS1 records (Phase 6 Task A2)."""

from dataclasses import replace
from pathlib import Path

import pytest
from demo_support import write_prepared

from heartbeat import cli
from heartbeat.cli import main
from heartbeat.config import load_settings
from heartbeat.demo.manifest import MANIFEST_NAME, check_manifest
from heartbeat.paths import DEFAULT_CONFIG


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    prepared = write_prepared(tmp_path / "prepared")
    settings = load_settings(DEFAULT_CONFIG)
    settings = replace(settings, data=replace(settings.data, prepared_dir=prepared))
    monkeypatch.setattr(cli, "load_settings", lambda path: settings)
    monkeypatch.setattr(cli, "DEMO_RECORDS", ("101", "223"))
    monkeypatch.setattr(cli, "TEST_LOG", tmp_path / "test_runs.jsonl")
    monkeypatch.setattr(cli, "DEMO_DATA_DIR", tmp_path / "data")
    return tmp_path / "data"


def test_build_demo_data_writes_the_folder_and_reports_it(
    local: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["build-demo-data"]) == 0
    assert (local / MANIFEST_NAME).is_file()
    assert check_manifest(local) == []
    out = capsys.readouterr().out
    assert "2 DS1 records" in out
    assert "default record 223 from 20 s" in out
    assert "largest beats file" in out


@pytest.mark.rule("R32")
def test_build_demo_data_refuses_a_ds2_record_with_exit_1(
    local: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "DEMO_RECORDS", ("101", "100"))
    assert main(["build-demo-data"]) == 1
    assert "record 100 is DS2" in capsys.readouterr().err
    assert not local.exists()
