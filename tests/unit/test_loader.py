"""EVAL-04: training and CV code cannot load DS2 (R15), checked without data."""

import ast
from pathlib import Path

import numpy as np
import pytest

from heartbeat.constants import FS_HZ, WINDOW_SAMPLES
from heartbeat.data.loader import SealedRecordError, load_ds1, require_ds1
from heartbeat.data.manifests import Splits, load_splits
from heartbeat.data.prepare import prepare_record, save_prepared
from heartbeat.data.records import RawRecord
from heartbeat.paths import PACKAGE_DIR, SPLITS_MANIFEST

REAL_SPLITS = load_splits(SPLITS_MANIFEST)
NOT_DS1 = [*REAL_SPLITS.ds2, "202", "102", "104", "107", "217", "999"]

SPLITS = Splits(
    ds1=("101", "106"),
    ds2=("100",),
    excluded={"202": "same subject as 201", "102": "paced"},
    lead="MLII",
)
SUBJECTS = {"100": "s100", "101": "s101", "102": "s102", "106": "s106", "202": "s201"}


def _raw(record_id: str) -> RawRecord:
    rng = np.random.default_rng(int(record_id))
    n = 20 * FS_HZ
    t_s = np.arange(n) / FS_HZ
    return RawRecord(
        record_id=record_id,
        mlii_mv=np.sin(2 * np.pi * 1.1 * t_s) + 0.1 * rng.standard_normal(n),
        ann_sample=np.array([400, 700, 1000, 1300, 1600, 1900], dtype=np.int64),
        ann_symbol=("N", "A", "Q", "V", "F", "N"),
    )


def _prepared_folder(tmp_path: Path, records: list[str]) -> Path:
    folder = tmp_path / "prepared"
    folder.mkdir()
    for record in records:
        save_prepared(
            prepare_record(_raw(record), SUBJECTS[record]), folder / f"{record}.npz"
        )
    return folder


@pytest.mark.rule("R15")
@pytest.mark.parametrize("record", NOT_DS1)
def test_require_ds1_refuses_every_non_ds1_record(record: str) -> None:
    with pytest.raises(SealedRecordError, match=record):
        require_ds1(["101", record], REAL_SPLITS)


@pytest.mark.rule("R15")
@pytest.mark.parametrize("record", ["100", "202", "102", "999"])
def test_load_ds1_refuses_a_non_ds1_record_even_with_its_file_present(
    tmp_path: Path, record: str
) -> None:
    folder = _prepared_folder(tmp_path, ["101", "106"])
    # A matching file under the record's own name, as if someone made one.
    other = SUBJECTS.get(record, "s999")
    raw = _raw("101")
    planted = RawRecord(record, raw.mlii_mv, raw.ann_sample, raw.ann_symbol)
    save_prepared(prepare_record(planted, other), folder / f"{record}.npz")
    with pytest.raises(SealedRecordError, match=record):
        load_ds1(folder, SPLITS, SUBJECTS, records=[record])


@pytest.mark.rule("R15")
def test_load_ds1_fails_on_a_stray_ds2_file_in_the_folder(tmp_path: Path) -> None:
    folder = _prepared_folder(tmp_path, ["101", "106"])
    raw = _raw("101")
    stray = RawRecord("100", raw.mlii_mv, raw.ann_sample, raw.ann_symbol)
    save_prepared(prepare_record(stray, "s100"), folder / "100.npz")
    with pytest.raises(SealedRecordError, match=r"100\.npz"):
        load_ds1(folder, SPLITS, SUBJECTS)


@pytest.mark.rule("R15")
def test_load_ds1_fails_on_a_ds2_file_renamed_to_a_ds1_name(tmp_path: Path) -> None:
    folder = _prepared_folder(tmp_path, ["106"])
    raw = _raw("101")
    renamed = RawRecord("100", raw.mlii_mv, raw.ann_sample, raw.ann_symbol)
    save_prepared(prepare_record(renamed, "s100"), folder / "101.npz")
    with pytest.raises((SealedRecordError, ValueError), match="100"):
        load_ds1(folder, SPLITS, SUBJECTS)


def test_load_ds1_fails_on_a_wrong_subject(tmp_path: Path) -> None:
    folder = tmp_path / "prepared"
    folder.mkdir()
    save_prepared(prepare_record(_raw("101"), "s999"), folder / "101.npz")
    with pytest.raises(ValueError, match=r"101.*s999"):
        load_ds1(folder, SPLITS, SUBJECTS, records=["101"])


def test_load_ds1_returns_kept_scored_beats_with_windows(tmp_path: Path) -> None:
    folder = _prepared_folder(tmp_path, ["101", "106"])
    beats = load_ds1(folder, SPLITS, SUBJECTS)
    # Six beats per record, first and last dropped, Q left out: A, V, F.
    assert beats.record_id.tolist() == ["101"] * 3 + ["106"] * 3
    assert beats.subject_id.tolist() == ["s101"] * 3 + ["s106"] * 3
    assert beats.beat_class.tolist() == ["S", "V", "F"] * 2
    assert beats.sample.tolist() == [700, 1300, 1600] * 2
    assert beats.sample.dtype == np.int64
    assert beats.window_adu.shape == (6, WINDOW_SAMPLES)
    assert beats.window_adu.dtype == np.int16
    assert beats.rr_s.shape == (6, 6)
    assert beats.rr_s.dtype == np.float64


def test_include_q_keeps_q_beats(tmp_path: Path) -> None:
    folder = _prepared_folder(tmp_path, ["101"])
    beats = load_ds1(folder, SPLITS, SUBJECTS, records=["101"], include_q=True)
    assert beats.beat_class.tolist() == ["S", "Q", "V", "F"]


def test_missing_prepared_file_names_the_command(tmp_path: Path) -> None:
    folder = _prepared_folder(tmp_path, ["101"])
    with pytest.raises(FileNotFoundError, match="heartbeat prepare"):
        load_ds1(folder, SPLITS, SUBJECTS)


def _imports_of(path: Path) -> list[str]:
    """Names a module pulls in from heartbeat.data.records, or the module itself."""
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.module == "heartbeat.data.records":
                found.extend(a.name for a in node.names if a.name == "read_record")
            elif node.module == "heartbeat.data":
                found.extend(
                    f"module {alias.name}"
                    for alias in node.names
                    if alias.name == "records"
                )
        elif isinstance(node, ast.Import):
            found.extend(
                f"module {alias.name}"
                for alias in node.names
                if alias.name == "heartbeat.data.records"
            )
        elif isinstance(node, ast.Attribute) and node.attr == "read_record":
            found.append("attribute read_record")
    return found


@pytest.mark.rule("R15")
def test_read_record_is_imported_only_by_prepare() -> None:
    importers = {}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        names = _imports_of(path)
        if names:
            importers[path.relative_to(PACKAGE_DIR).as_posix()] = names
    assert importers == {"data/prepare.py": ["read_record"]}
