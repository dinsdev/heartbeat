"""Phase 5 settling 5: age and sex from all 44 headers, with no signal read."""

import builtins
import io
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from run_support import make_repo

from heartbeat.config import Settings
from heartbeat.data.describe import COUNT_CLASSES, aami_counts
from heartbeat.data.loader import load_ds1
from heartbeat.data.manifests import (
    Splits,
    downloaded_records,
    load_beat_counts,
    load_checksums,
)
from heartbeat.data.prepare import PrepareReport
from heartbeat.data.records import read_header_demographics
from heartbeat.paths import BEAT_COUNTS_MANIFEST, CHECKSUM_MANIFEST
from heartbeat.stages import run_describe_data


def test_all_44_headers_parse_and_no_signal_or_annotation_is_opened(
    raw_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = downloaded_records(load_checksums(CHECKSUM_MANIFEST))
    assert len(records) == 44
    opened: list[str] = []
    real_open: Callable[..., Any] = builtins.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    found = {r: read_header_demographics(raw_dir, r) for r in records}
    assert opened
    assert all(name.endswith(".hea") for name in opened), opened
    assert all(d.sex in {"M", "F"} for d in found.values())
    # Ages that do not parse render "unknown" and are listed in the ledger.
    assert sum(d.age is not None for d in found.values()) >= 40


def test_the_describe_data_stage_on_the_real_cache(
    tmp_path: Path,
    settings: Settings,
    splits: Splits,
    subjects: dict[str, str],
    prepared_ds1: tuple[Path, PrepareReport],
) -> None:
    folder, _ = prepared_ds1
    local = replace(settings, data=replace(settings.data, prepared_dir=folder))
    repo = make_repo(tmp_path)
    run, payload = run_describe_data(local, root=repo / "runs", repo=repo)
    assert (run.path / "data_summary.json").is_file()
    kept = load_ds1(folder, splits, subjects, include_q=True)
    ds1, ds2 = payload["sets"]["DS1"], payload["sets"]["DS2"]
    assert sum(ds1["kept"].values()) == kept.sample.size == payload["n_kept_ds1"]
    assert ds2["kept"] is None
    counts = load_beat_counts(BEAT_COUNTS_MANIFEST)
    for name, records in (("DS1", splits.ds1), ("DS2", splits.ds2)):
        expected = dict.fromkeys(COUNT_CLASSES, 0)
        for record in records:
            for c, n in aami_counts(counts[record]).items():
                expected[c] += n
        assert payload["sets"][name]["annotated"] == expected
        assert payload["demographics"][name]["patients"] == len(records)
    # Two beats per record are dropped (DATA-08), so kept is at most annotated.
    for row in payload["records"]:
        if row["set"] == "DS1":
            assert all(row["kept"][c] <= row["annotated"][c] for c in COUNT_CLASSES)
    assert [r["record"] for r in payload["records"]] == [*splits.ds1, *splits.ds2]
