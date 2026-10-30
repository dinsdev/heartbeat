"""The `heartbeat` command: every E4 subcommand exists as a stub until its phase."""

import hashlib
from pathlib import Path

import pytest

from heartbeat import cli
from heartbeat.cli import SUBCOMMANDS, main
from heartbeat.config import DataSettings, FoldSettings, Settings
from heartbeat.data import download as download_module

EXPECTED_PHASES = {
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


def test_subcommands_match_the_plan() -> None:
    assert dict(SUBCOMMANDS) == EXPECTED_PHASES


def test_help_lists_every_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for name in SUBCOMMANDS:
        assert name in out


# Subcommands built so far in Phase 2; each has its own tests.
BUILT = {"download"}


@pytest.mark.parametrize(
    ("name", "phase"),
    sorted((n, p) for n, p in EXPECTED_PHASES.items() if n not in BUILT),
)
def test_stub_exits_2_and_says_when_it_arrives(
    name: str, phase: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([name]) == 2
    captured = capsys.readouterr()
    assert captured.err.strip() == f"heartbeat {name}: not built yet (Phase {phase})"
    assert captured.out == ""


def test_unknown_subcommand_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["no-such-command"])
    assert exit_info.value.code != 0


def test_no_subcommand_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code != 0


def test_rebuild_accepts_from_and_exact(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rebuild", "--from", "prepare", "--exact"]) == 2
    assert "heartbeat rebuild: not built yet (Phase 2)" in capsys.readouterr().err


def test_rebuild_from_needs_a_stage() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["rebuild", "--from"])
    assert exit_info.value.code != 0


def _tmp_settings(tmp_path: Path) -> Settings:
    return Settings(
        data=DataSettings(
            raw_dir=tmp_path / "raw",
            prepared_dir=tmp_path / "prepared",
            sources=("https://a.example/", "https://b.example/"),
        ),
        folds=FoldSettings(seed=1),
    )


def test_download_fetches_and_reports_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = {"100.atr": b"a", "100.dat": b"d", "100.hea": b"h"}
    monkeypatch.setattr(cli, "load_settings", lambda _: _tmp_settings(tmp_path))
    monkeypatch.setattr(
        cli,
        "load_checksums",
        lambda _: {n: hashlib.sha256(d).hexdigest() for n, d in files.items()},
    )
    monkeypatch.setattr(
        download_module,
        "fetch_url",
        lambda url: files[url.removeprefix("https://a.example/")],
    )
    assert main(["download"]) == 0
    assert "fetched 3, skipped 0, of 3 files" in capsys.readouterr().out
    assert main(["download"]) == 0
    assert "fetched 0, skipped 3, of 3 files" in capsys.readouterr().out


def test_download_exits_1_naming_the_file_on_a_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda _: _tmp_settings(tmp_path))
    monkeypatch.setattr(cli, "load_checksums", lambda _: {"100.hea": "0" * 64})
    monkeypatch.setattr(download_module, "fetch_url", lambda url: b"wrong")
    assert main(["download"]) == 1
    assert "100.hea" in capsys.readouterr().err
