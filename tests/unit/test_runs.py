"""C6, MODEL-07: run folders with resolved config and provenance."""

import json
import logging
import re
from pathlib import Path

import numpy as np
import pytest
from run_support import git, make_repo, settings

from heartbeat.runs import RunFolder, canonical_json, create_run


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def _run(repo: Path, name: str = "test") -> RunFolder:
    return create_run(
        name,
        settings(repo.parent),
        {"model": "baseline", "grid": [0.1, 1.0]},
        root=repo / "runs",
        repo=repo,
    )


def test_run_folder_name_has_utc_time_short_commit_and_name(repo: Path) -> None:
    with _run(repo, "cv-baseline") as run:
        short = git(repo, "rev-parse", "--short", "HEAD")
        assert re.fullmatch(rf"\d{{8}}T\d{{6}}Z-{short}-cv-baseline", run.path.name)
        assert run.path.parent == repo / "runs"
        assert run.name == run.path.name


def test_config_has_resolved_settings_and_extra_config(repo: Path) -> None:
    with _run(repo) as run:
        config = json.loads((run.path / "config.json").read_text(encoding="utf-8"))
    assert config["settings"]["folds"]["seed"] == 7
    assert config["settings"]["data"]["sources"] == ["https://a.example/"]
    assert config["settings"]["data"]["raw_dir"] == str(repo.parent / "raw")
    assert config["extra"] == {"model": "baseline", "grid": [0.1, 1.0]}


def test_provenance_fields_on_a_clean_tree(repo: Path) -> None:
    with _run(repo) as run:
        provenance = json.loads(
            (run.path / "provenance.json").read_text(encoding="utf-8")
        )
    assert run.provenance == provenance
    assert provenance["commit"] == git(repo, "rev-parse", "HEAD")
    assert provenance["dirty"] is False
    assert len(provenance["diff_sha256"]) == 64
    assert provenance["python"].count(".") == 2
    assert set(provenance["packages"]) == {"numpy", "scipy", "scikit-learn", "wfdb"}
    assert provenance["packages"]["numpy"] == np.__version__
    assert len(provenance["uv_lock_sha256"]) == 64
    assert len(provenance["folds_sha256"]) == 64
    assert provenance["device"] == "cpu"
    assert isinstance(provenance["cpu_count"], int)
    assert isinstance(provenance["threads"], dict)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", provenance["created_utc"])


def test_dirty_flag_and_diff_hash_after_an_uncommitted_edit(repo: Path) -> None:
    with _run(repo, "clean") as clean:
        pass
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
    with _run(repo, "dirty") as dirty:
        pass
    assert clean.provenance["dirty"] is False
    assert dirty.provenance["dirty"] is True
    assert dirty.provenance["diff_sha256"] != clean.provenance["diff_sha256"]


def test_an_untracked_file_makes_the_tree_dirty(repo: Path) -> None:
    (repo / "new.py").write_text("y = 1\n", encoding="utf-8")
    with _run(repo) as run:
        assert run.provenance["dirty"] is True


def test_results_written_earlier_in_a_rebuild_leave_the_tree_clean(
    repo: Path,
) -> None:
    (repo / "results").mkdir()
    (repo / "results" / "cv_baseline.json").write_text("{}\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "results")
    with _run(repo, "clean") as clean:
        pass
    (repo / "results" / "cv_baseline.json").write_text('{"a": 1}\n', encoding="utf-8")
    (repo / "results" / "selection.json").write_text("{}\n", encoding="utf-8")
    with _run(repo, "after") as after:
        pass
    assert after.provenance["dirty"] is False
    assert after.provenance["diff_sha256"] == clean.provenance["diff_sha256"]
    (repo / "docs" / "results").mkdir(parents=True)
    (repo / "docs" / "results" / "notes.md").write_text("x\n", encoding="utf-8")
    with _run(repo, "nested") as nested:
        assert nested.provenance["dirty"] is True


def test_thread_variables_are_recorded(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    with _run(repo) as run:
        assert run.provenance["threads"]["OMP_NUM_THREADS"] == "3"


def test_log_txt_receives_package_log_records(repo: Path) -> None:
    with _run(repo) as run:
        logging.getLogger("heartbeat.train").warning("fold 3 done")
    logging.getLogger("heartbeat.train").warning("after close")
    text = (run.path / "log.txt").read_text(encoding="utf-8")
    assert "fold 3 done" in text
    assert "after close" not in text


def test_write_json_is_canonical(repo: Path) -> None:
    with _run(repo) as run:
        path = run.write_json("metrics", {"b": 1, "a": [1.5, None]})
    assert path == run.path / "metrics.json"
    text = path.read_text(encoding="utf-8")
    assert text == canonical_json({"a": [1.5, None], "b": 1})
    assert text.endswith("}\n")
    assert text.index('"a"') < text.index('"b"')


def test_write_json_rejects_nan(repo: Path) -> None:
    with _run(repo) as run, pytest.raises(ValueError, match="JSON"):
        run.write_json("metrics", {"x": float("nan")})


def test_write_arrays_round_trips_without_pickle(repo: Path) -> None:
    with _run(repo) as run:
        path = run.write_arrays(
            "oof", logits=np.ones((3, 4)), record=np.array(["101", "106", "108"])
        )
    assert path == run.path / "oof.npz"
    with np.load(path, allow_pickle=False) as data:
        np.testing.assert_array_equal(data["logits"], np.ones((3, 4)))
        assert data["record"].tolist() == ["101", "106", "108"]


def test_two_runs_with_one_name_in_one_second_do_not_share_a_folder(
    repo: Path,
) -> None:
    with _run(repo, "same") as first, pytest.raises(FileExistsError):
        create_run(
            "same",
            settings(repo.parent),
            {},
            root=repo / "runs",
            repo=repo,
            now=first.created,
        )


def test_a_torch_run_records_torch_device_threads_and_the_flag(repo: Path) -> None:
    # Phase 4 design call 7: provenance adds the torch version, device, thread
    # count and the deterministic flag.
    info = {
        "torch": "2.14.1",
        "device": "mps",
        "torch_threads": 4,
        "deterministic": True,
    }
    with create_run(
        "cv-cnn-w1-s0",
        settings(repo.parent),
        {},
        root=repo / "runs",
        repo=repo,
        torch_info=info,
    ) as run:
        provenance = json.loads(
            (run.path / "provenance.json").read_text(encoding="utf-8")
        )
    for key, value in info.items():
        assert provenance[key] == value
