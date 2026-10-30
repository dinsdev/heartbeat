"""Rule 5: `results/` has one canonical, atomic writer, called only by stages."""

import ast
import json
from pathlib import Path

import pytest
from run_support import make_repo, settings

from heartbeat.paths import PACKAGE_DIR
from heartbeat.results import write_result
from heartbeat.runs import RunFolder, create_run


def _run(tmp_path: Path) -> RunFolder:
    repo = make_repo(tmp_path)
    return create_run("t", settings(tmp_path), {}, root=repo / "runs", repo=repo)


def test_write_result_copies_run_commit_and_dirty(tmp_path: Path) -> None:
    with _run(tmp_path) as run:
        path = write_result("cv_baseline", {"x": 1}, run, results_dir=tmp_path / "r")
    assert path == tmp_path / "r" / "cv_baseline.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "x": 1,
        "run": run.name,
        "commit": run.provenance["commit"],
        "dirty": False,
    }


def test_output_is_byte_stable_and_canonical(tmp_path: Path) -> None:
    results = tmp_path / "r"
    with _run(tmp_path) as run:
        first = write_result(
            "a", {"b": [1, 2], "a": {"z": 0.5, "y": None}}, run, results
        )
        before = first.read_bytes()
        write_result("a", {"a": {"y": None, "z": 0.5}, "b": [1, 2]}, run, results)
    after = first.read_bytes()
    assert before == after
    text = after.decode("utf-8")
    assert text.endswith("}\n")
    assert not text.endswith("\n\n")
    assert '  "a": {' in text


def test_nan_raises_and_leaves_the_old_file(tmp_path: Path) -> None:
    results = tmp_path / "r"
    with _run(tmp_path) as run:
        path = write_result("a", {"x": 1.0}, run, results)
        before = path.read_bytes()
        with pytest.raises(ValueError, match="JSON"):
            write_result("a", {"x": float("nan")}, run, results)
    assert path.read_bytes() == before
    assert sorted(p.name for p in results.iterdir()) == ["a.json"]


def test_payload_may_not_set_provenance_keys(tmp_path: Path) -> None:
    with _run(tmp_path) as run, pytest.raises(ValueError, match="dirty"):
        write_result("a", {"dirty": False}, run, tmp_path / "r")


def _imports_write_result(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = {a.name for a in node.names}
            if node.module == "heartbeat.results" and names & {"write_result", "*"}:
                return True
            if node.module == "heartbeat" and "results" in names:
                return True
        if isinstance(node, ast.Import) and any(
            a.name == "heartbeat.results" for a in node.names
        ):
            return True
    return False


def test_only_stages_imports_the_results_writer() -> None:
    importers = sorted(
        path.relative_to(PACKAGE_DIR).as_posix()
        for path in PACKAGE_DIR.rglob("*.py")
        if _imports_write_result(path)
    )
    assert importers == ["stages.py"]
