"""OPS-04: `heartbeat verify` passes a sound checkout and fails each planted fault."""

import json
import shutil
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import torch
from cnn_support import annotated_beats_with_traces

from heartbeat.cards.blocks import SHIPPED_PENDING, TEST_PENDING, CardSources
from heartbeat.data.manifests import Splits
from heartbeat.export.build import baseline_params
from heartbeat.export.bundle import SeedModel, bundle_files, file_facts, write_bundle
from heartbeat.export.fixtures import FixtureModel, build_fixtures, write_fixtures
from heartbeat.export.onnx import export_onnx
from heartbeat.models.cnn import HeartbeatCNN
from heartbeat.models.inputs import fit_rr_scaler, rr_model_inputs
from heartbeat.sealed.log import append_entry
from heartbeat.verify import (
    CHECKS,
    VerifyPaths,
    check_cards,
    check_models,
    check_notice,
    check_parity,
    check_test_log,
    verify,
)

WEIGHTS = {"N": 0.3, "S": 9.0, "V": 3.0, "F": 30.0}
SPLITS = Splits(
    ds1=tuple(f"s{k:02d}" for k in range(10)), ds2=("100",), excluded={}, lead="MLII"
)
CARD = (
    "# Card\n\n<!-- card:begin test_headline -->\n\n{test}\n\n"
    "<!-- card:end test_headline -->\n\n<!-- card:begin shipped_data -->\n\n"
    "{shipped}\n\n<!-- card:end shipped_data -->\n"
)
Renderers = Mapping[str, Callable[[CardSources], str]]
SPECS_RENDERERS: Renderers = {
    "test_headline": lambda s: TEST_PENDING,
    "shipped_data": lambda s: SHIPPED_PENDING,
}


def _build(root: Path) -> VerifyPaths:
    beats, _, annotated = annotated_beats_with_traces()
    scaler = fit_rr_scaler(rr_model_inputs(beats.rr_s))
    block = {
        "C": 0.1,
        "temperature": 1.2,
        "classes": ["N", "S", "V", "F"],
        "coefficients": (np.arange(24).reshape(4, 6) / 10).tolist(),
        "intercepts": [0.1, -0.2, 0.3, -0.4],
        "scaler": {"mean": scaler.mean.tolist(), "std": scaler.std.tolist()},
        "class_weights": WEIGHTS,
    }
    seeds, networks = [], []
    for seed in (0, 1, 2):
        torch.manual_seed(seed)
        network = HeartbeatCNN(0.5).eval()
        seeds.append(SeedModel(seed, export_onnx(network), WEIGHTS, 1.5 + seed))
        networks.append(FixtureModel(seed, network, WEIGHTS, 1.5 + seed))
    paths = VerifyPaths(
        repo=root,
        results_dir=root / "results",
        models_dir=root / "models" / "heartbeat-v1",
        fixtures_dir=root / "fixtures" / "parity",
        model_card=root / "docs" / "MODEL_CARD.md",
        data_card=root / "docs" / "DATA_CARD.md",
        log_path=root / "results" / "test_runs.jsonl",
        raw_dir=root / "no-cache",
    )
    write_bundle(
        paths.models_dir, seeds, block["scaler"]["mean"], block["scaler"]["std"], block
    )
    payload = build_fixtures(beats, annotated, SPLITS, networks, baseline_params(block))
    fixtures = write_fixtures(paths.fixtures_dir, payload)
    paths.results_dir.mkdir(parents=True)
    record = {
        "files": bundle_files(paths.models_dir, root),
        "fixtures": {**file_facts(fixtures, root), "beats": 50},
    }
    (paths.results_dir / "export.json").write_text(json.dumps(record), "utf-8")
    paths.model_card.parent.mkdir(parents=True)
    for card in (paths.model_card, paths.data_card):
        card.write_text(
            CARD.format(test=TEST_PENDING, shipped=SHIPPED_PENDING), "utf-8"
        )
    return paths


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> VerifyPaths:
    return _build(tmp_path_factory.mktemp("verify") / "repo")


@pytest.fixture
def paths(built: VerifyPaths, tmp_path: Path) -> VerifyPaths:
    root = tmp_path / "repo"
    shutil.copytree(built.repo, root)
    return VerifyPaths(
        repo=root,
        results_dir=root / "results",
        models_dir=root / "models" / "heartbeat-v1",
        fixtures_dir=root / "fixtures" / "parity",
        model_card=root / "docs" / "MODEL_CARD.md",
        data_card=root / "docs" / "DATA_CARD.md",
        log_path=root / "results" / "test_runs.jsonl",
        raw_dir=root / "no-cache",
    )


def _specs(paths: VerifyPaths) -> list[tuple[Path, Renderers]]:
    return [(paths.model_card, SPECS_RENDERERS), (paths.data_card, SPECS_RENDERERS)]


def test_a_sound_checkout_passes_every_check(paths: VerifyPaths) -> None:
    assert check_models(paths) == []
    assert check_notice(paths) == []
    assert check_parity(paths) == []
    assert check_cards(paths, _specs(paths)) == []
    assert check_test_log(paths) == []
    names = [name for name, _ in verify(paths)]
    assert names == [name for name, _ in CHECKS]


@pytest.mark.rule("R52")
def test_a_missing_notice_fails(paths: VerifyPaths) -> None:
    (paths.models_dir / "NOTICE").unlink()
    assert "R52" in check_notice(paths)[0]


@pytest.mark.rule("R52")
def test_a_changed_notice_fails(paths: VerifyPaths) -> None:
    (paths.models_dir / "NOTICE").write_text("MIT\n", encoding="utf-8")
    assert "differs" in check_notice(paths)[0]


@pytest.mark.rule("R25")
def test_a_changed_model_byte_fails(paths: VerifyPaths) -> None:
    model = paths.models_dir / "seeds" / "seed-1" / "model.onnx"
    data = bytearray(model.read_bytes())
    data[-1] ^= 1
    model.write_bytes(bytes(data))
    assert check_models(paths) == [
        "models/heartbeat-v1/seeds/seed-1/model.onnx differs from results/export.json"
    ]


@pytest.mark.rule("R26")
def test_a_changed_fixture_logit_fails_parity(paths: VerifyPaths) -> None:
    path = paths.fixtures_dir / "fixtures.json"
    payload = json.loads(path.read_text("utf-8"))
    payload["beats"][7]["seeds"]["2"]["logits"][1] += 1e-3
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert "seed-2" in check_parity(paths)[0]
    assert "fixtures.json differs" in check_models(paths)[0]


@pytest.mark.rule("R50")
def test_a_stale_block_fails(paths: VerifyPaths) -> None:
    text = paths.data_card.read_text("utf-8")
    paths.data_card.write_text(text.replace(SHIPPED_PENDING, "edited"), "utf-8")
    assert check_cards(paths, _specs(paths)) == [
        "DATA_CARD.md: block shipped_data is stale"
    ]


@pytest.mark.rule("R42")
def test_a_rewritten_log_line_fails(paths: VerifyPaths) -> None:
    for kind in ("sealed", "reproduction"):
        append_entry(
            paths.log_path,
            paths.results_dir / "test_runs",
            kind,
            {"x": kind},
            commit="c" * 40,
            freeze_sha256="f" * 64,
            today=date(2027, 1, 16),
            repo=paths.repo,
        )
    assert check_test_log(paths) == []
    lines = paths.log_path.read_text("utf-8").splitlines()
    first = json.loads(lines[0])
    first["commit"] = "d" * 40
    first["id"] = 2
    paths.log_path.write_text(json.dumps(first) + "\n" + lines[1] + "\n", "utf-8")
    assert "id" in check_test_log(paths)[0]
