"""The `heartbeat` command: every E4 subcommand exists as a stub until its phase."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from heartbeat import cli
from heartbeat.cli import SUBCOMMANDS, main
from heartbeat.config import DataSettings, FoldSettings, Settings, TrainSettings
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


# The Phase 2 to 4 subcommands are built and have their own tests here and in
# test_folds.py and test_stages.py; the rest stay stubs until their phase.
BUILT = {n for n, p in EXPECTED_PHASES.items() if p <= 4}


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
        train=TrainSettings(cv_device="cpu"),
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


def _fake_prepare(total_hits: int) -> object:
    from heartbeat.data.prepare import FloorHitLimitError, FloorHits, PrepareReport

    def prepare(settings: Settings, splits: object, subjects: object) -> PrepareReport:
        if total_hits > 5:
            raise FloorHitLimitError(f"{total_hits} DS1 windows hit the z-score floor")
        return PrepareReport(
            records=("101", "106"),
            floor_hits={"101": FloorHits(total_hits, 1.5), "106": FloorHits(0, 30.0)},
            total_hits=total_hits,
        )

    return prepare


def _cache_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from heartbeat.data.download import CacheStatus

    monkeypatch.setattr(cli, "load_settings", lambda _: _tmp_settings(tmp_path))
    monkeypatch.setattr(cli, "check_cache", lambda *_: CacheStatus(ok=True, missing=()))


def test_prepare_prints_the_floor_hit_total(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _cache_ok(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "prepare_ds1", _fake_prepare(2))
    assert main(["prepare"]) == 0
    out = capsys.readouterr().out
    assert "prepared 2 DS1 records" in out
    assert "floor hits 2 (limit 5)" in out


def test_prepare_exits_1_over_the_floor_hit_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _cache_ok(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "prepare_ds1", _fake_prepare(9))
    assert main(["prepare"]) == 1
    assert "9 DS1 windows" in capsys.readouterr().err


def test_prepare_exits_1_on_an_incomplete_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda _: _tmp_settings(tmp_path))
    assert main(["prepare"]) == 1
    assert "heartbeat download" in capsys.readouterr().err


def _patch_cross_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    from cv_support import synthetic_beats, synthetic_folds

    beats = synthetic_beats()
    folds_json = tmp_path / "folds.json"
    folds_json.write_text("{}\n", encoding="utf-8")
    runs = tmp_path / "runs"
    monkeypatch.setattr(cli, "load_settings", lambda _: _tmp_settings(tmp_path))
    monkeypatch.setattr(cli, "check_folds", lambda *a, **k: synthetic_folds(beats))
    monkeypatch.setattr(cli, "load_ds1", lambda *a, **k: beats)
    monkeypatch.setattr(cli, "FOLDS_JSON", folds_json)
    monkeypatch.setattr(cli, "RUNS_DIR", runs)
    return runs, folds_json


def test_cross_validate_writes_a_run_folder_and_no_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runs, folds_json = _patch_cross_validate(tmp_path, monkeypatch)
    assert main(["cross-validate", "--model", "baseline"]) == 0
    out = capsys.readouterr().out
    (run,) = runs.iterdir()
    assert run.name.endswith("-cv-baseline")
    assert {p.name for p in run.iterdir()} == {
        "config.json",
        "provenance.json",
        "log.txt",
        "metrics.json",
        "oof.npz",
        "model.npz",
    }
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    assert (
        metrics["folds_sha256"] == hashlib.sha256(folds_json.read_bytes()).hexdigest()
    )
    assert f"chosen C {metrics['chosen_c']}" in out
    assert str(run) in out
    assert not (tmp_path / "results").exists()


def test_cross_validate_exits_1_on_a_fold_check_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from heartbeat.data.folds import FoldCheckError

    runs, _ = _patch_cross_validate(tmp_path, monkeypatch)

    def failing(*args: object, **kwargs: object) -> None:
        raise FoldCheckError("pin differs")

    monkeypatch.setattr(cli, "check_folds", failing)
    assert main(["cross-validate"]) == 1
    assert "pin differs" in capsys.readouterr().err
    assert not runs.exists()


def test_cross_validate_rejects_an_unknown_model() -> None:
    # The CNN arrived in Phase 4; any other model is still refused.
    with pytest.raises(SystemExit) as exit_info:
        main(["cross-validate", "--model", "svm"])
    assert exit_info.value.code != 0


# Phase 4: the CNN's development runs and the select, exhibit and train-final
# subcommands, which write run folders only (rule 5).


def test_cross_validate_cnn_runs_one_fold_into_a_run_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from cnn_support import beats_with_traces
    from cv_support import synthetic_folds

    beats, traces = beats_with_traces(n_subjects=10, per_subject=140)
    runs, _ = _patch_cross_validate(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "check_folds", lambda *a, **k: synthetic_folds(beats))
    monkeypatch.setattr(cli, "load_ds1", lambda *a, **k: beats)
    monkeypatch.setattr(cli, "load_ds1_traces", lambda *a, **k: traces)
    monkeypatch.setattr(cli, "MAX_EPOCHS", 2)
    argv = ["cross-validate", "--model", "cnn", "--width", "0.5", "--seed", "1"]
    assert main([*argv, "--fold", "3", "--device", "cpu"]) == 0
    out = capsys.readouterr().out
    (run,) = runs.iterdir()
    assert run.name.endswith("-cv-cnn-w0.5-s1")
    with np.load(run / "oof.npz", allow_pickle=False) as data:
        assert data["folds_run"].tolist() == [3]
        assert data["logits"].shape[0] == 2
    provenance = json.loads((run / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["device"] == "cpu"
    assert "fold 3" in out
    assert str(run) in out
    assert not (tmp_path / "results").exists()


def test_cross_validate_cnn_device_defaults_to_the_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake(*args: object, **kwargs: object) -> tuple[object, dict[str, object]]:
        seen.update(kwargs)
        raise SystemExit(0)

    _patch_cross_validate(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "load_ds1_traces", lambda *a, **k: {})
    monkeypatch.setattr(cli, "run_cnn_cv", fake)
    with pytest.raises(SystemExit):
        main(["cross-validate", "--model", "cnn"])
    # _tmp_settings sets cv_device = "cpu"; width 1 and seed 0 by default.
    assert seen["device"] == "cpu"
    assert seen["width"] == 1.0
    assert seen["seed"] == 0
    assert seen["only_folds"] is None


@pytest.mark.parametrize(
    ("command", "function", "n_payloads"),
    [
        ("select", "run_select_all", 2),
        ("exhibit", "run_exhibit_all", 1),
        ("train-final", "run_final_all", 1),
    ],
)
def test_the_cnn_subcommands_write_a_run_folder_and_no_results(
    command: str,
    function: str,
    n_payloads: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeRun:
        path = tmp_path / "runs" / "the-run"

    monkeypatch.setattr(cli, "load_settings", lambda _: _tmp_settings(tmp_path))
    monkeypatch.setattr(
        cli, function, lambda settings: (FakeRun(), *([{}] * n_payloads))
    )
    assert main([command]) == 0
    assert str(FakeRun.path) in capsys.readouterr().out


def test_select_exits_1_at_the_epoch_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from heartbeat.train.select import EpochEdgeError

    def edge(settings: object) -> None:
        raise EpochEdgeError("selected epoch 38", selection=None)  # type: ignore[arg-type]

    monkeypatch.setattr(cli, "load_settings", lambda _: _tmp_settings(tmp_path))
    monkeypatch.setattr(cli, "run_select_all", edge)
    assert main(["select"]) == 1
    assert "selected epoch 38" in capsys.readouterr().err
