"""E3, PARITY-01, R52: the `models/heartbeat-v1/` files and NOTICE."""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from cnn_support import annotated_beats_with_traces
from numpy.typing import NDArray
from run_support import make_repo
from run_support import settings as run_settings

from heartbeat.constants import RR_FEATURE_NAMES, SCORED_CLASSES
from heartbeat.data.loader import BeatTable
from heartbeat.data.manifests import Splits
from heartbeat.export.build import export_models
from heartbeat.export.bundle import (
    ATTRIBUTION_NOTICE,
    NOTICE_TEXT,
    SeedModel,
    bundle_files,
    write_bundle,
)
from heartbeat.export.fixtures import fixture_parity
from heartbeat.export.onnx import ExportError, ParityError
from heartbeat.runs import canonical_json
from heartbeat.sealed.score import load_baseline, load_calibration
from heartbeat.train.final import final_payload, train_final, train_final_baseline

WEIGHTS = {"N": 0.28, "S": 13.5, "V": 3.36, "F": 30.8}
MEAN = [0.78, 0.78, 0.78, 0.78, -0.01, 0.0]
STD = [0.5, 0.5, 0.23, 0.17, 0.16, 0.25]
BASELINE_BLOCK: dict[str, Any] = {
    "run": "r-baseline",
    "C": 0.001,
    "temperature": 1.17,
    "classes": list(SCORED_CLASSES),
    "coefficients": [[float(i + j) for j in range(6)] for i in range(4)],
    "intercepts": [0.1, 0.2, 0.3, 0.4],
    "scaler": {"mean": MEAN, "std": STD},
    "class_weights": WEIGHTS,
    "n_rows": 100,
    "solver": "lbfgs",
    "max_iter": 10000,
}


def _seeds() -> list[SeedModel]:
    return [
        SeedModel(
            seed=s,
            onnx_bytes=f"onnx-{s}".encode(),
            class_weights=WEIGHTS,
            temperature=1.5 + s,
        )
        for s in (0, 1, 2)
    ]


def _write(folder: Path) -> list[Path]:
    return write_bundle(folder, _seeds(), MEAN, STD, BASELINE_BLOCK)


def _listing(folder: Path) -> list[str]:
    return sorted(
        p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()
    )


def test_the_bundle_layout(tmp_path: Path) -> None:
    folder = tmp_path / "heartbeat-v1"
    written = _write(folder)
    assert _listing(folder) == [
        "NOTICE",
        "baseline.json",
        "calibration.json",
        "model.onnx",
        "scaler.json",
        "seeds/seed-1/calibration.json",
        "seeds/seed-1/model.onnx",
        "seeds/seed-2/calibration.json",
        "seeds/seed-2/model.onnx",
    ]
    assert sorted(p.relative_to(folder).as_posix() for p in written) == _listing(folder)
    assert (folder / "model.onnx").read_bytes() == b"onnx-0"
    assert (folder / "seeds" / "seed-2" / "model.onnx").read_bytes() == b"onnx-2"


@pytest.mark.rule("R52")
def test_notice_has_the_mit_line_and_the_odc_by_notice(tmp_path: Path) -> None:
    folder = tmp_path / "heartbeat-v1"
    _write(folder)
    text = (folder / "NOTICE").read_text(encoding="utf-8")
    assert text == NOTICE_TEXT
    assert "MIT License" in text
    # ODC-By 1.0 section 4.3, as worded in DATA_LICENSE.md.
    assert (
        "Contains information from the MIT-BIH Arrhythmia Database (version 1.0.0, "
        "PhysioNet), which is made available under the ODC Attribution License v1.0."
    ) in " ".join(text.split())
    assert "https://opendatacommons.org/licenses/by/1-0/" in text


def test_calibration_and_scaler_files(tmp_path: Path) -> None:
    folder = tmp_path / "heartbeat-v1"
    _write(folder)
    shipped = json.loads((folder / "calibration.json").read_text("utf-8"))
    assert shipped["seed"] == 0
    assert shipped["classes"] == list(SCORED_CLASSES)
    assert shipped["temperature"] == 1.5
    assert shipped["log_class_weights"] == [
        math.log(WEIGHTS[c]) for c in SCORED_CLASSES
    ]
    seed_2 = load_calibration(folder / "seeds" / "seed-2" / "calibration.json")
    assert seed_2.temperature == 3.5
    np.testing.assert_array_equal(
        seed_2.log_class_weights, np.log([WEIGHTS[c] for c in SCORED_CLASSES])
    )
    scaler = json.loads((folder / "scaler.json").read_text("utf-8"))
    assert scaler["features"] == list(RR_FEATURE_NAMES)
    assert scaler["log_features"] == ["pre_over_local", "post_over_pre"]
    assert scaler["mean"] == MEAN
    assert scaler["std"] == STD
    for name in ("calibration.json", "scaler.json", "baseline.json"):
        text = (folder / name).read_text("utf-8")
        assert text == canonical_json(json.loads(text))


def test_baseline_json_round_trips_to_numpy_params(tmp_path: Path) -> None:
    folder = tmp_path / "heartbeat-v1"
    _write(folder)
    payload = json.loads((folder / "baseline.json").read_text("utf-8"))
    assert payload["model"] == "baseline"
    assert payload["C"] == 0.001
    assert "run" not in payload
    params = load_baseline(folder / "baseline.json")
    np.testing.assert_array_equal(params.coefficients, BASELINE_BLOCK["coefficients"])
    np.testing.assert_array_equal(params.intercepts, BASELINE_BLOCK["intercepts"])
    np.testing.assert_array_equal(params.scaler_mean, MEAN)
    np.testing.assert_array_equal(params.scaler_std, STD)
    np.testing.assert_array_equal(
        params.log_class_weights, np.log([WEIGHTS[c] for c in SCORED_CLASSES])
    )
    assert params.temperature == 1.17


def test_a_rewrite_is_byte_identical_and_keeps_a_freeze_record(tmp_path: Path) -> None:
    folder = tmp_path / "heartbeat-v1"
    _write(folder)
    first = {p: (folder / p).read_bytes() for p in _listing(folder)}
    (folder / "freeze.json").write_text("{}\n", encoding="utf-8")
    _write(folder)
    assert {
        p: (folder / p).read_bytes() for p in _listing(folder) if p != "freeze.json"
    } == first
    assert (folder / "freeze.json").read_text("utf-8") == "{}\n"


def test_a_stray_file_in_the_bundle_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "heartbeat-v1"
    _write(folder)
    (folder / "seeds" / "seed-3").mkdir()
    (folder / "seeds" / "seed-3" / "model.onnx").write_bytes(b"x")
    with pytest.raises(FileExistsError, match="seed-3"):
        _write(folder)


def test_bundle_files_lists_size_and_sha256_without_the_freeze_record(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "models" / "heartbeat-v1"
    _write(folder)
    (folder / "freeze.json").write_text("{}\n", encoding="utf-8")
    files = bundle_files(folder, tmp_path)
    assert [f["path"] for f in files] == [
        f"models/heartbeat-v1/{p}" for p in _listing(folder) if p != "freeze.json"
    ]
    model = next(f for f in files if f["path"].endswith("/model.onnx"))
    assert model["bytes"] == len(b"onnx-0")
    assert len(model["sha256"]) == 64


def test_seeds_must_include_the_shipped_seed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="seed 0"):
        write_bundle(tmp_path, _seeds()[1:], MEAN, STD, BASELINE_BLOCK)


# export_models: checkpoints from train-final to the bundle and its record.


Trained = tuple[Path, BeatTable, dict[str, Any], dict[str, NDArray[np.int64]]]
SPLITS = Splits(
    ds1=tuple(f"s{k:02d}" for k in range(10)), ds2=("100",), excluded={}, lead="MLII"
)


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> Trained:
    repo = make_repo(tmp_path_factory.mktemp("export"))
    beats, traces, annotated = annotated_beats_with_traces()
    models = [
        train_final(
            run_settings(repo.parent),
            beats,
            traces,
            width=0.5,
            epochs=1,
            seed=seed,
            temperature=1.5 + seed,
            root=repo / "runs",
            repo=repo,
        )
        for seed in (0, 1, 2)
    ]
    baseline = train_final_baseline(
        run_settings(repo.parent),
        beats,
        c=0.1,
        temperature=1.2,
        root=repo / "runs",
        repo=repo,
    )
    payload = final_payload(models, width=0.5, epochs=1, baseline=baseline, repo=repo)
    return repo, beats, payload, annotated


def _export(trained: Trained, final: dict[str, Any], name: str) -> dict[str, Any]:
    repo, beats, _, annotated = trained
    return export_models(
        final,
        beats,
        annotated,
        SPLITS,
        repo / name / "models" / "heartbeat-v1",
        repo / name / "fixtures" / "parity",
        repo,
    )


def test_export_models_writes_the_bundle_and_its_record(trained: Trained) -> None:
    repo, beats, final, _ = trained
    folder = repo / "main" / "models" / "heartbeat-v1"
    record = _export(trained, final, "main")
    json.dumps(record, allow_nan=False)
    assert record["opset"] == 20
    assert record["size_limit_bytes"] == 1_000_000
    assert record["parity"]["tolerance"] == 1e-5
    assert record["parity"]["beats"] == beats.sample.size
    assert {"torch", "onnx", "onnxruntime"} <= set(record["versions"])
    assert record["parameters"] > 0
    assert record["files"] == bundle_files(folder, repo)
    by_seed = {m["seed"]: m for m in record["models"]}
    assert sorted(by_seed) == [0, 1, 2]
    for entry in final["models"]:
        mine = by_seed[entry["seed"]]
        assert mine["checkpoint_sha256"] == entry["sha256"]
        assert mine["temperature"] == entry["temperature"]
        assert mine["parity_max_abs_diff"] <= 1e-5
        facts = next(f for f in record["files"] if f["path"] == mine["path"])
        assert facts["bytes"] < 1_000_000
    assert by_seed[0]["path"] == "main/models/heartbeat-v1/model.onnx"
    assert by_seed[2]["path"] == "main/models/heartbeat-v1/seeds/seed-2/model.onnx"
    assert record["baseline"]["path"] == "main/models/heartbeat-v1/baseline.json"
    fixtures = repo / "main" / "fixtures" / "parity" / "fixtures.json"
    assert record["fixtures"]["path"] == "main/fixtures/parity/fixtures.json"
    assert record["fixtures"]["bytes"] == fixtures.stat().st_size
    assert record["fixtures"]["beats"] == 50
    stored = json.loads(fixtures.read_text("utf-8"))
    assert stored["notice"] == ATTRIBUTION_NOTICE
    assert ATTRIBUTION_NOTICE in " ".join(NOTICE_TEXT.split())
    assert record["baseline"]["C"] == 0.1
    for name in ("run", "commit", "dirty"):
        assert name not in record


@pytest.mark.rule("R26")
def test_the_committed_files_reproduce_the_fixture_logits(trained: Trained) -> None:
    repo = trained[0]
    _export(trained, trained[2], "parity")
    models = repo / "parity" / "models" / "heartbeat-v1"
    path = repo / "parity" / "fixtures" / "parity" / "fixtures.json"
    payload = json.loads(path.read_text("utf-8"))
    diffs = fixture_parity(models, payload)
    assert sorted(diffs) == ["baseline", "seed-0", "seed-1", "seed-2"]
    assert all(d <= 1e-5 for d in diffs.values())
    payload["beats"][3]["seeds"]["1"]["logits"][2] += 2e-5
    with pytest.raises(ParityError, match="seed-1"):
        fixture_parity(models, payload)
    payload["beats"][3]["seeds"]["1"]["logits"][2] -= 2e-5
    payload["beats"][0]["baseline"]["logits"][0] += 1.0
    with pytest.raises(ParityError, match="baseline"):
        fixture_parity(models, payload)


def test_export_models_twice_gives_the_same_bytes(trained: Trained) -> None:
    final = trained[2]
    first = _export(trained, final, "a")
    second = _export(trained, final, "b")
    assert [f["sha256"] for f in first["files"]] == [
        f["sha256"] for f in second["files"]
    ]
    assert first["fixtures"]["sha256"] == second["fixtures"]["sha256"]


def test_export_models_refuses_a_changed_checkpoint(trained: Trained) -> None:
    changed = json.loads(json.dumps(trained[2]))
    changed["models"][1]["sha256"] = "0" * 64
    with pytest.raises(ExportError, match="seed-1"):
        _export(trained, changed, "c")


def test_export_models_refuses_seeds_with_different_scalers(trained: Trained) -> None:
    changed = json.loads(json.dumps(trained[2]))
    changed["models"][2]["scaler"]["mean"][0] += 1.0
    with pytest.raises(ExportError, match="scaler"):
        _export(trained, changed, "d")
