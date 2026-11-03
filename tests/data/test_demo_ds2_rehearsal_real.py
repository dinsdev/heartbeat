"""Phase 7 Task A4: the DS2 demo build, rehearsed on DS1 (settling 4, R32).

The sealed run goes through `run_sealed` on DS1 records in a temporary frozen
repo (`rehearsal_support`), then `build-demo-data` runs in its post-seal mode
with a stand-in split whose DS2 is DS1, so no DS2 file is opened (rule 1). The
build prepares each record in memory, never reads `data/prepared/`, and must
match the logged report exactly; a planted per-patient cell in a later sealed
report must stop it before any file is written. The numbers are in-sample DS1
scores: nothing here asserts their values and none is quoted (rule 2).
"""

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from rehearsal_support import frozen_repo, run_on_ds1

from heartbeat.config import Settings
from heartbeat.data.manifests import Splits
from heartbeat.data.npz import PreparedRecord
from heartbeat.data.prepare import prepare_in_memory
from heartbeat.demo.build import build_demo_data, demo_records
from heartbeat.demo.manifest import MANIFEST_NAME, check_manifest
from heartbeat.demo.sealed_check import SealedMismatchError
from heartbeat.sealed.log import append_entry, read_log
from heartbeat.sealed.report import CNN


def _no_prepared_file(path: Path) -> PreparedRecord:
    raise AssertionError(f"the DS2 build opened a prepared file: {path}")


@pytest.mark.rule("R32")
def test_the_ds2_build_matches_the_sealed_report_and_stops_on_a_planted_cell(
    tmp_path: Path,
    settings: Settings,
    splits: Splits,
    subjects: dict[str, str],
    raw_dir: Path,
) -> None:
    repo = frozen_repo(tmp_path)
    out = tmp_path / "out"
    entry = run_on_ds1(repo, out, settings, splits, subjects)
    log_path = out / "results" / "test_runs.jsonl"
    stand_in = Splits(
        ds1=(), ds2=splits.ds1, excluded=splits.excluded, lead=splits.lead
    )
    records = demo_records(stand_in, log_path)
    assert records == splits.ds1

    models = repo / "models" / "heartbeat-v1"
    export = json.loads((repo / "results" / "export.json").read_text("utf-8"))
    prepared: list[str] = []

    def spy(raw: Path, record: str, lead: str, subject: str) -> PreparedRecord:
        prepared.append(record)
        return prepare_in_memory(raw, record, lead, subject)

    def build(out_dir: Path) -> dict[str, Any]:
        return build_demo_data(
            records,
            tmp_path / "no-prepared",
            models,
            export,
            log_path,
            out_dir,
            stand_in,
            read=_no_prepared_file,
            raw_dir=raw_dir,
            subjects=subjects,
            log_root=out,
            prepare=spy,
        )

    demo = tmp_path / "demo"
    manifest = build(demo)
    assert prepared == list(splits.ds1)
    assert manifest["split"] == "DS2"
    assert manifest["sealed_run"] == {"id": entry["id"], "report": entry["report"]}
    assert [r["record"] for r in manifest["records"]] == list(splits.ds1)
    assert check_manifest(demo) == []
    assert not (tmp_path / "no-prepared").exists()

    # A later sealed report with one per-patient cell changed stops the build.
    report = json.loads((out / entry["report"]).read_text("utf-8"))
    planted = copy.deepcopy(report)
    row = planted["per_patient"][CNN][0]
    row["S"]["recall"]["numerator"] += 1
    append_entry(
        log_path,
        out / "results" / "test_runs",
        "sealed",
        planted,
        commit=entry["commit"],
        freeze_sha256=entry["freeze_sha256"],
        today=date(2027, 1, 17),
        repo=out,
    )
    assert [e["id"] for e in read_log(log_path)] == [1, 2]
    with pytest.raises(SealedMismatchError, match=f"patient {row['patient']} S recall"):
        build(tmp_path / "planted")
    assert not (tmp_path / "planted").exists()
    assert json.loads((demo / MANIFEST_NAME).read_text("utf-8")) == manifest
