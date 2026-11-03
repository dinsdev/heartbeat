"""`build-demo-data` on the real DS2 records, after the sealed run (Phase 7 Task B2).

Builds every DS2 record into a temporary folder through the stage behind
`heartbeat build-demo-data`, from the committed model and the real log, so the
exact check against the sealed report runs before anything is written (Phase 7
settling 4). It asserts structure and D4's default only, never a DS2 metric
(rule 2). Run only once a sealed entry is logged and pushed (rule 1).
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from heartbeat.config import Settings
from heartbeat.data.manifests import Splits
from heartbeat.demo.build import BEATS_SIZE_LIMIT_BYTES, decode_beats
from heartbeat.demo.manifest import check_manifest
from heartbeat.paths import TEST_LOG
from heartbeat.sealed.log import read_log
from heartbeat.stages import run_build_demo_data


@pytest.fixture(scope="module")
def demo(
    tmp_path_factory: pytest.TempPathFactory, settings: Settings
) -> tuple[Path, dict[str, Any]]:
    out = tmp_path_factory.mktemp("demo-ds2") / "data"
    return out, run_build_demo_data(settings, out_dir=out)


def _beats_payload(
    out: Path, manifest: dict[str, Any], record: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = next(r for r in manifest["records"] if r["record"] == record)
    data = (out / entry["beats"]["name"]).read_bytes()
    return json.loads(data), decode_beats(data)


@pytest.mark.rule("R32")
def test_ships_every_ds2_record_and_names_the_sealed_run(
    demo: tuple[Path, dict[str, Any]], splits: Splits
) -> None:
    _, manifest = demo
    sealed = [entry for entry in read_log(TEST_LOG) if entry["type"] == "sealed"]
    assert sealed, "no sealed entry in results/test_runs.jsonl"
    assert manifest["split"] == "DS2"
    assert [r["record"] for r in manifest["records"]] == list(splits.ds2)
    assert manifest["sealed_run"] == {
        "id": sealed[-1]["id"],
        "report": sealed[-1]["report"],
    }


@pytest.mark.rule("R31")
def test_the_real_ds2_manifest_matches_its_files(
    demo: tuple[Path, dict[str, Any]],
) -> None:
    out, _ = demo
    assert check_manifest(out) == []


@pytest.mark.rule("R43")
def test_default_is_200_from_its_first_10_second_span_with_an_s_or_v_beat(
    demo: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = demo
    assert manifest["default"]["record"] == "200"
    payload, beats = _beats_payload(out, manifest, "200")
    irregular = beats["kept"] & np.isin(beats["class"], ("S", "V"))
    assert irregular.any()
    # Worked out here from the shipped beats file, not by the build's helper.
    first_seconds = int(beats["sample"][irregular][0]) / payload["fs_hz"]
    assert manifest["default"]["start_s"] == 10 * int(first_seconds // 10)


def test_every_ds2_beats_file_is_under_the_size_gate(
    demo: tuple[Path, dict[str, Any]],
) -> None:
    _, manifest = demo
    sizes = {r["record"]: r["beats"]["bytes"] for r in manifest["records"]}
    assert max(sizes.values()) < BEATS_SIZE_LIMIT_BYTES, sizes
