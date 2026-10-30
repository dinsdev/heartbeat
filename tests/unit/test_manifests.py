"""Task 2.1: the committed manifests and settings parse and validate."""

import textwrap
from pathlib import Path

import pytest

from heartbeat.config import SettingsError, load_settings
from heartbeat.data.manifests import (
    ManifestError,
    downloaded_records,
    load_beat_counts,
    load_checksums,
    load_splits,
    load_subjects,
)
from heartbeat.paths import (
    BEAT_COUNTS_MANIFEST,
    CHECKSUM_MANIFEST,
    DEFAULT_CONFIG,
    REPO_ROOT,
    SPLITS_MANIFEST,
    SUBJECTS_MANIFEST,
)

# de Chazal, O'Dwyer and Reilly (2004), written out here so the test does not
# read the lists it checks from the file under test.
DE_CHAZAL_DS1 = [
    "101", "106", "108", "109", "112", "114", "115", "116", "118", "119", "122",
    "124", "201", "203", "205", "207", "208", "209", "215", "220", "223", "230",
]  # fmt: skip
DE_CHAZAL_DS2_WITH_202 = [
    "100", "103", "105", "111", "113", "117", "121", "123", "200", "202", "210",
    "212", "213", "214", "219", "221", "222", "228", "231", "232", "233", "234",
]  # fmt: skip
PACED = ("102", "104", "107", "217")


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# The split lists, for R3


@pytest.mark.rule("R3")
def test_ds1_is_de_chazals_training_list() -> None:
    splits = load_splits(SPLITS_MANIFEST)
    assert list(splits.ds1) == DE_CHAZAL_DS1
    assert len(splits.ds1) == 22


@pytest.mark.rule("R3")
def test_ds2_is_de_chazals_test_list_without_202() -> None:
    splits = load_splits(SPLITS_MANIFEST)
    assert list(splits.ds2) == [r for r in DE_CHAZAL_DS2_WITH_202 if r != "202"]
    assert len(splits.ds2) == 21


@pytest.mark.rule("R3")
def test_paced_records_and_202_are_excluded_from_both_sets() -> None:
    splits = load_splits(SPLITS_MANIFEST)
    assert set(splits.excluded) == {*PACED, "202"}
    for record in splits.excluded:
        assert record not in splits.ds1
        assert record not in splits.ds2
    assert not set(splits.ds1) & set(splits.ds2)


@pytest.mark.rule("R3")
def test_splits_name_the_lead() -> None:
    assert load_splits(SPLITS_MANIFEST).lead == "MLII"


# Subject IDs, for R12


@pytest.mark.rule("R12")
def test_no_subject_on_both_sides_of_ds1_and_ds2() -> None:
    splits = load_splits(SPLITS_MANIFEST)
    subjects = load_subjects(SUBJECTS_MANIFEST)
    ds1_subjects = {subjects[r] for r in splits.ds1}
    ds2_subjects = {subjects[r] for r in splits.ds2}
    assert not ds1_subjects & ds2_subjects
    assert len(ds1_subjects) == 22
    assert len(ds2_subjects) == 21


@pytest.mark.rule("R12")
def test_201_and_202_are_one_subject() -> None:
    subjects = load_subjects(SUBJECTS_MANIFEST)
    assert subjects["201"] == subjects["202"]


@pytest.mark.rule("R12")
def test_48_records_map_to_47_subjects() -> None:
    subjects = load_subjects(SUBJECTS_MANIFEST)
    assert len(subjects) == 48
    assert len(set(subjects.values())) == 47


def test_every_split_record_has_a_subject() -> None:
    splits = load_splits(SPLITS_MANIFEST)
    subjects = load_subjects(SUBJECTS_MANIFEST)
    for record in (*splits.ds1, *splits.ds2, *splits.excluded):
        assert record in subjects


# Checksums and beat counts


def test_checksums_name_exactly_the_files_of_the_44_non_paced_records() -> None:
    checksums = load_checksums(CHECKSUM_MANIFEST)
    records = sorted({*DE_CHAZAL_DS1, *DE_CHAZAL_DS2_WITH_202})
    expected = {f"{r}.{ext}" for r in records for ext in ("hea", "dat", "atr")}
    assert set(checksums) == expected
    assert len(checksums) == 132
    for digest in checksums.values():
        assert len(digest) == 64
        assert digest == digest.lower()


def test_downloaded_records_are_the_44_non_paced_records() -> None:
    checksums = load_checksums(CHECKSUM_MANIFEST)
    expected = sorted({*DE_CHAZAL_DS1, *DE_CHAZAL_DS2_WITH_202})
    assert list(downloaded_records(checksums)) == expected


def test_beat_counts_cover_the_44_downloaded_records() -> None:
    counts = load_beat_counts(BEAT_COUNTS_MANIFEST)
    assert sorted(counts) == sorted({*DE_CHAZAL_DS1, *DE_CHAZAL_DS2_WITH_202})
    assert counts["208"]["F"] == 373


# Malformed manifests raise ManifestError naming the file and the line


def test_malformed_checksum_line_names_file_and_line(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad.sha256",
        f"""\
        {"a" * 64} 100.atr
        not-a-checksum 100.dat
        """,
    )
    with pytest.raises(ManifestError, match=r"bad\.sha256:2"):
        load_checksums(path)


def test_short_checksum_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.sha256", "abc123 100.atr\n")
    with pytest.raises(ManifestError, match=r"bad\.sha256:1"):
        load_checksums(path)


def test_duplicate_checksum_file_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "dup.sha256",
        f"""\
        {"a" * 64} 100.atr
        {"b" * 64} 100.atr
        """,
    )
    with pytest.raises(ManifestError, match=r"dup\.sha256:2.*100\.atr"):
        load_checksums(path)


def test_checksum_for_a_record_missing_one_of_its_files_raises(
    tmp_path: Path,
) -> None:
    checksums = {"100.atr": "a" * 64, "100.dat": "b" * 64}
    with pytest.raises(ManifestError, match=r"100.*hea"):
        downloaded_records(checksums)


SPLITS_OK = """\
    database = "mitdb"
    version = "1.0.0"
    lead = "MLII"
    ds1 = ["101", "106"]
    ds2 = ["100", "103"]

    [excluded]
    "102" = "paced"
    """


def test_small_valid_splits_parse(tmp_path: Path) -> None:
    splits = load_splits(_write(tmp_path, "splits.toml", SPLITS_OK))
    assert splits.ds1 == ("101", "106")
    assert splits.ds2 == ("100", "103")
    assert dict(splits.excluded) == {"102": "paced"}


def test_duplicate_record_in_a_split_raises(tmp_path: Path) -> None:
    text = SPLITS_OK.replace('ds1 = ["101", "106"]', 'ds1 = ["101", "106", "101"]')
    path = _write(tmp_path, "splits.toml", text)
    with pytest.raises(ManifestError, match=r"splits\.toml:4.*101"):
        load_splits(path)


def test_record_in_both_sets_raises(tmp_path: Path) -> None:
    text = SPLITS_OK.replace('ds2 = ["100", "103"]', 'ds2 = ["100", "106"]')
    path = _write(tmp_path, "splits.toml", text)
    with pytest.raises(ManifestError, match=r"splits\.toml:5.*106"):
        load_splits(path)


def test_excluded_record_in_a_set_raises(tmp_path: Path) -> None:
    text = SPLITS_OK.replace('ds2 = ["100", "103"]', 'ds2 = ["100", "102"]')
    path = _write(tmp_path, "splits.toml", text)
    with pytest.raises(ManifestError, match=r"splits\.toml:5.*102"):
        load_splits(path)


def test_unknown_key_in_splits_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "splits.toml", '    ds3 = ["999"]\n' + SPLITS_OK)
    with pytest.raises(ManifestError, match=r"splits\.toml:1.*ds3"):
        load_splits(path)


def test_missing_key_in_splits_raises(tmp_path: Path) -> None:
    text = SPLITS_OK.replace('lead = "MLII"\n', "")
    path = _write(tmp_path, "splits.toml", text)
    with pytest.raises(ManifestError, match=r"splits\.toml.*lead"):
        load_splits(path)


def test_toml_syntax_error_names_file_and_line(tmp_path: Path) -> None:
    path = _write(tmp_path, "splits.toml", SPLITS_OK + "ds3 = [\n")
    with pytest.raises(ManifestError, match=r"splits\.toml:\d+"):
        load_splits(path)


def test_unknown_key_in_subjects_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "subjects.toml",
        """\
        [subjects]
        "100" = "s100"

        [extra]
        "x" = "y"
        """,
    )
    with pytest.raises(ManifestError, match=r"subjects\.toml:4.*extra"):
        load_subjects(path)


def test_non_string_subject_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "subjects.toml",
        """\
        [subjects]
        "100" = "s100"
        "101" = 101
        """,
    )
    with pytest.raises(ManifestError, match=r"subjects\.toml:3.*101"):
        load_subjects(path)


def test_negative_beat_count_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "counts.toml",
        """\
        [records]
        "100" = { N = 10 }
        "101" = { N = -1 }
        """,
    )
    with pytest.raises(ManifestError, match=r"counts\.toml:3.*101"):
        load_beat_counts(path)


# Settings


def test_fold_seed_is_the_c1_lock_date() -> None:
    assert load_settings(DEFAULT_CONFIG).folds.seed == 20261026


def test_data_folders_resolve_under_the_repo() -> None:
    settings = load_settings(DEFAULT_CONFIG)
    assert settings.data.raw_dir == REPO_ROOT / "data" / "raw" / "mitdb" / "1.0.0"
    assert settings.data.prepared_dir == REPO_ROOT / "data" / "prepared"


def test_sources_try_the_s3_mirror_first() -> None:
    sources = load_settings(DEFAULT_CONFIG).data.sources
    assert sources[0].startswith("https://physionet-open.s3.amazonaws.com/")
    assert sources[1].startswith("https://physionet.org/")
    assert all(s.endswith("/") for s in sources)


def test_unknown_key_in_settings_raises(tmp_path: Path) -> None:
    text = DEFAULT_CONFIG.read_text(encoding="utf-8") + "\n[extra]\nx = 1\n"
    path = _write(tmp_path, "config.toml", text)
    with pytest.raises(SettingsError, match="extra"):
        load_settings(path)


def test_unknown_key_inside_a_settings_table_raises(tmp_path: Path) -> None:
    text = DEFAULT_CONFIG.read_text(encoding="utf-8").replace(
        "seed = 20261026", "seed = 20261026\nshuffle = true"
    )
    path = _write(tmp_path, "config.toml", text)
    with pytest.raises(SettingsError, match="shuffle"):
        load_settings(path)


def test_settings_type_errors_raise(tmp_path: Path) -> None:
    text = DEFAULT_CONFIG.read_text(encoding="utf-8").replace(
        "seed = 20261026", 'seed = "20261026"'
    )
    path = _write(tmp_path, "config.toml", text)
    with pytest.raises(SettingsError, match="seed"):
        load_settings(path)


def test_the_cv_device_is_mps() -> None:
    # Phase 4 design call 7: a run setting; final training is CPU by constant.
    assert load_settings(DEFAULT_CONFIG).train.cv_device == "mps"


def test_an_unknown_cv_device_raises(tmp_path: Path) -> None:
    text = DEFAULT_CONFIG.read_text(encoding="utf-8").replace(
        'cv_device = "mps"', 'cv_device = "cuda"'
    )
    path = _write(tmp_path, "config.toml", text)
    with pytest.raises(SettingsError, match="cv_device"):
        load_settings(path)
