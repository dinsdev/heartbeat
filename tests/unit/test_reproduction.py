"""Phase 5 settling 4: reproduction is exact, apart from one list of volatile keys."""

import json
from pathlib import Path
from typing import Any

import pytest

from heartbeat.checks.reproduction import (
    VOLATILE_KEYS,
    compare_checkouts,
    main,
    strip_volatile,
)
from heartbeat.evaluate.metrics import RATE_NAMES, metric_values
from heartbeat.train.cv import HEADLINE_METRICS

RESULT: dict[str, Any] = {
    "run": "20261030T092237Z-3b1116c-select",
    "commit": "3b1116c87b015d9df38e81dc641fe03019869ae9",
    "dirty": False,
    "pooled": {"macro_f1_nsv": 0.64, "confusion": [[1, 2], [3, 4]]},
    "runs": {"0": "20261030T082322Z-3b1116c-cv-cnn-w1-s0"},
    "curves": [{"run": "a-run", "per_seed": [{"run": "b-run", "f1": [0.1, 0.2]}]}],
    "models": [{"seed": 0, "path": "runs/x/model.pt", "sha256": "ab", "wall_s": 293.6}],
    "rows": [{"runs": ["r1", "r2"], "metrics": {"S_recall": 0.5}}],
}


def test_volatile_keys_name_runs_commits_paths_and_times_only() -> None:
    assert (
        frozenset(
            {"run", "runs", "commit", "curves_run", "baseline_run", "path", "wall_s"}
        )
        == VOLATILE_KEYS
    )


def test_no_metric_name_is_volatile() -> None:
    import numpy as np

    names = set(metric_values(np.ones((4, 4), dtype=np.int64)))
    names |= set(HEADLINE_METRICS) | set(RATE_NAMES)
    names |= {"confusion", "temperature", "sha256", "score", "epoch", "width", "C"}
    names |= {"chosen_c", "coefficients", "intercepts", "bytes", "dirty", "pooled"}
    assert not names & VOLATILE_KEYS


def test_strip_removes_volatile_values_and_keeps_every_number_inside() -> None:
    stripped = strip_volatile(RESULT)
    assert "run" not in stripped
    assert "commit" not in stripped
    assert stripped["dirty"] is False
    # A volatile key holding only names goes; one holding numbers is opened.
    assert "runs" not in stripped
    assert stripped["curves"] == [{"per_seed": [{"f1": [0.1, 0.2]}]}]
    assert stripped["models"] == [{"seed": 0, "sha256": "ab"}]
    assert stripped["rows"] == [{"metrics": {"S_recall": 0.5}}]
    assert stripped["pooled"] == RESULT["pooled"]


def test_a_runs_list_holding_metrics_still_compares_them() -> None:
    a = {"runs": [{"run": "x", "confusion": [1, 2]}]}
    b = {"runs": [{"run": "y", "confusion": [1, 3]}]}
    assert strip_volatile(a) != strip_volatile(b)
    b["runs"][0]["confusion"] = [1, 2]
    assert strip_volatile(a) == strip_volatile(b)


def _checkout(root: Path, metric: float = 0.64, model: bytes = b"onnx") -> Path:
    files: dict[str, bytes] = {
        "results/cv_cnn.json": json.dumps(
            {**RESULT, "pooled": {"macro_f1_nsv": metric}}
        ).encode(),
        "results/export.json": b'{"run": "e1", "files": []}',
        "results/test_runs.jsonl": b"",
        "models/heartbeat-v1/model.onnx": model,
        "models/heartbeat-v1/NOTICE": b"notice",
        "fixtures/parity/fixtures.json": b"{}",
        "docs/MODEL_CARD.md": b"card",
        "docs/DATA_CARD.md": b"card",
    }
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def test_equal_checkouts_pass(tmp_path: Path) -> None:
    a = _checkout(tmp_path / "a")
    b = _checkout(tmp_path / "b")
    run_dir = b / "results" / "cv_cnn.json"
    other = json.loads(run_dir.read_text("utf-8"))
    other["run"] = "another-run"
    other["commit"] = "f" * 40
    run_dir.write_text(json.dumps(other), encoding="utf-8")
    assert compare_checkouts(a, b) == []


def test_a_changed_metric_fails(tmp_path: Path) -> None:
    a = _checkout(tmp_path / "a")
    b = _checkout(tmp_path / "b", metric=0.65)
    assert compare_checkouts(a, b) == ["results/cv_cnn.json differs"]


def test_a_changed_model_byte_fails(tmp_path: Path) -> None:
    a = _checkout(tmp_path / "a")
    b = _checkout(tmp_path / "b", model=b"onnY")
    assert compare_checkouts(a, b) == ["models/heartbeat-v1/model.onnx differs"]


def test_a_missing_file_fails(tmp_path: Path) -> None:
    a = _checkout(tmp_path / "a")
    b = _checkout(tmp_path / "b")
    (b / "fixtures" / "parity" / "fixtures.json").unlink()
    assert compare_checkouts(a, b) == ["fixtures/parity/fixtures.json missing in b"]


def test_the_command_exits_1_on_a_difference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _checkout(tmp_path / "a")
    b = _checkout(tmp_path / "b", metric=0.1)
    assert main(["--root", str(a), "--other", str(b)]) == 1
    assert "results/cv_cnn.json differs" in capsys.readouterr().out
    c = _checkout(tmp_path / "c")
    assert main(["--root", str(a), "--other", str(c)]) == 0
