"""`build-demo-data` on the real DS1 records (Phase 6 Task A2; R31, R32, DEMO-09).

Builds every DS1 record into a temporary folder from the committed model and
checks the stored seed-0 values against the parity fixtures, which the Python
pipeline computed through PyTorch (Phase 5): labels exact, probabilities
within 1e-5. The build reads an empty log in the temporary folder, as before
the sealed run: once `results/test_runs.jsonl` holds a sealed entry the real
log builds DS2 only (R32), which `test_demo_ds2_real.py` checks.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from heartbeat.constants import PARITY_TOLERANCE
from heartbeat.data.manifests import Splits
from heartbeat.data.prepare import PrepareReport
from heartbeat.demo.build import BEATS_SIZE_LIMIT_BYTES, build_demo_data, decode_beats
from heartbeat.demo.manifest import check_manifest
from heartbeat.export.fixtures import FIXTURES_NAME
from heartbeat.paths import FIXTURES_DIR, MODELS_DIR, RESULTS_DIR


@pytest.fixture(scope="module")
def demo(
    tmp_path_factory: pytest.TempPathFactory,
    prepared_ds1: tuple[Path, PrepareReport],
    splits: Splits,
) -> tuple[Path, dict[str, Any]]:
    folder, _ = prepared_ds1
    out = tmp_path_factory.mktemp("demo") / "data"
    no_sealed_run = tmp_path_factory.mktemp("log") / "test_runs.jsonl"
    export_record = json.loads((RESULTS_DIR / "export.json").read_text("utf-8"))
    manifest = build_demo_data(
        splits.ds1, folder, MODELS_DIR, export_record, no_sealed_run, out, splits
    )
    return out, manifest


def _beats(out: Path, manifest: dict[str, Any], record: str) -> dict[str, Any]:
    entry = next(r for r in manifest["records"] if r["record"] == record)
    return decode_beats((out / entry["beats"]["name"]).read_bytes())


@pytest.mark.rule("R32")
def test_ships_every_ds1_record_and_nothing_else(
    demo: tuple[Path, dict[str, Any]], splits: Splits
) -> None:
    _, manifest = demo
    assert manifest["split"] == "DS1"
    assert [r["record"] for r in manifest["records"]] == list(splits.ds1)


@pytest.mark.rule("R31")
def test_the_real_manifest_matches_its_files(
    demo: tuple[Path, dict[str, Any]],
) -> None:
    out, _ = demo
    assert check_manifest(out) == []


def test_default_record_is_223_by_d4s_rule_on_the_prepared_beats(
    demo: tuple[Path, dict[str, Any]],
) -> None:
    _, manifest = demo
    assert manifest["default"]["record"] == "223"
    counts = next(r["counts"] for r in manifest["records"] if r["record"] == "223")
    # Settling 6 counted the whole record (S 73, V 473); the dropped first and
    # last beats may only lower these.
    assert counts["S"] <= 73
    assert counts["V"] <= 473


def test_stored_python_values_equal_the_parity_fixtures(
    demo: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = demo
    fixtures = json.loads((FIXTURES_DIR / FIXTURES_NAME).read_text("utf-8"))
    largest = 0.0
    for beat in fixtures["beats"]:
        decoded = _beats(out, manifest, beat["record"])
        kept_samples = decoded["sample"][decoded["kept"]]
        (row,) = np.flatnonzero(kept_samples == beat["sample"])
        expected = beat["seeds"]["0"]
        assert decoded["label"][row] == expected["label"]
        diff = np.abs(decoded["probabilities"][row] - expected["probabilities"])
        largest = max(largest, float(diff.max()))
    assert largest <= PARITY_TOLERANCE


def test_every_beats_file_is_under_the_size_gate(
    demo: tuple[Path, dict[str, Any]],
) -> None:
    _, manifest = demo
    sizes = {r["record"]: r["beats"]["bytes"] for r in manifest["records"]}
    assert max(sizes.values()) < BEATS_SIZE_LIMIT_BYTES, sizes
