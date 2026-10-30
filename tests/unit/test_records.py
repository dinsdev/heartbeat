"""DATA-04: the MLII lead is picked by name in any channel order (R4)."""

from pathlib import Path

import pytest

from heartbeat.data.records import (
    Demographics,
    LeadNotFoundError,
    parse_demographics,
    read_header_demographics,
    select_lead,
)


@pytest.mark.rule("R4")
def test_mlii_second_as_in_record_114() -> None:
    assert select_lead(["V5", "MLII"], "MLII") == 1


@pytest.mark.rule("R4")
def test_mlii_first() -> None:
    assert select_lead(["MLII", "V1"], "MLII") == 0


@pytest.mark.rule("R4")
def test_missing_lead_raises() -> None:
    with pytest.raises(LeadNotFoundError, match=r"MLII.*V1.*V5"):
        select_lead(["V1", "V5"], "MLII")


@pytest.mark.rule("R4")
def test_duplicate_lead_raises() -> None:
    with pytest.raises(LeadNotFoundError, match="twice"):
        select_lead(["MLII", "MLII"], "MLII")


# Phase 5 settling 5: age and sex from the record headers.

HEADER = """101 2 360 650000
101.dat 212 200 11 1024 955 29832 0 MLII
101.dat 212 200 11 1024 992 19589 0 V1
# 75 F 1011 654 x1
# Diapres
"""


def test_age_and_sex_parse_from_the_first_comment_line() -> None:
    assert parse_demographics(HEADER) == Demographics(age=75, sex="F")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("# -1 M 978 654 x1", Demographics(age=None, sex="M")),
        ("# 23 F 2546 N/A x1", Demographics(age=23, sex="F")),
        ("# ? ? x1", Demographics(age=None, sex=None)),
        ("# 64 X 1953 3655 x1", Demographics(age=64, sex=None)),
        ("# 68", Demographics(age=68, sex=None)),
        ("#", Demographics(age=None, sex=None)),
    ],
)
def test_a_missing_or_unparseable_value_gives_none(
    line: str, expected: Demographics
) -> None:
    text = HEADER.replace("# 75 F 1011 654 x1", line)
    assert parse_demographics(text) == expected


def test_a_header_without_comments_gives_none() -> None:
    text = "".join(HEADER.splitlines(keepends=True)[:3])
    assert parse_demographics(text) == Demographics(age=None, sex=None)


def test_read_header_demographics_reads_the_hea_file_only(tmp_path: Path) -> None:
    (tmp_path / "101.hea").write_text(HEADER, encoding="utf-8")
    assert read_header_demographics(tmp_path, "101") == Demographics(75, "F")
