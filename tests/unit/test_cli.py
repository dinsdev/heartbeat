"""The `heartbeat` command: every E4 subcommand exists as a stub until its phase."""

import pytest

from heartbeat.cli import SUBCOMMANDS, main

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


@pytest.mark.parametrize(("name", "phase"), sorted(EXPECTED_PHASES.items()))
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
