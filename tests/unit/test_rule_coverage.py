"""Task 1.7: every rule-table row at or below the current phase has a test."""

import textwrap
from pathlib import Path

import pytest

from heartbeat.checks.rule_coverage import (
    Row,
    collect_rule_ids,
    current_phase,
    main,
    parse_rule_table,
    pending,
    uncovered,
)

TABLE = textwrap.dedent(
    """\
    # Plan

    ## 5. Verification layers

    | Layer | What |
    | --- | --- |
    | L1 | not the rule table |

    ## 6. Rule-to-test table

    | # | Rule | Source | Enforced by | Layer | Phase |
    | --- | --- | --- | --- | --- | --- |
    | R1 | A checksum mismatch stops the run | B5 | download test | L1 | 2 |
    | R4 | MLII picked by name | B1 | unit and real-data tests | L1, L2 | 2 |
    | R10 | Unknown symbol fails loudly | B4 | unit test | L1 | 2 |
    | R44 | Published text avoids D7's list | D7, F6 | wording lint | TX | 1 onward |
    | R48 | One VoiceOver pass | D6 | manual | MAN | 8 |

    ## 7. Review focus

    | R99 | not in the table | x | x | L1 | 1 |
    """
)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def write_pyproject(root: Path, phase: int) -> None:
    write(root, "pyproject.toml", f"[tool.heartbeat]\ncurrent-phase = {phase}\n")


def ids(rows: list[Row]) -> list[str]:
    return [row.rule_id for row in rows]


# Parsing the table


def test_parse_reads_only_section_6() -> None:
    rows = parse_rule_table(TABLE)
    assert rows == [
        Row("R1", ("L1",), 2),
        Row("R4", ("L1", "L2"), 2),
        Row("R10", ("L1",), 2),
        Row("R44", ("TX",), 1),
        Row("R48", ("MAN",), 8),
    ]


def test_phase_one_onward_parses_as_1() -> None:
    (row,) = [r for r in parse_rule_table(TABLE) if r.rule_id == "R44"]
    assert row.phase == 1


def test_malformed_row_raises_with_the_row_text() -> None:
    broken = TABLE.replace("| L1 | 2 |\n| R4", "| L1 |\n| R4", 1)
    with pytest.raises(ValueError, match=r"\| R1 \| A checksum mismatch"):
        parse_rule_table(broken)


def test_row_without_a_phase_number_raises() -> None:
    broken = TABLE.replace("| TX | 1 onward |", "| TX | later |")
    with pytest.raises(ValueError, match="R44"):
        parse_rule_table(broken)


def test_missing_section_raises() -> None:
    with pytest.raises(ValueError, match="Rule-to-test table"):
        parse_rule_table("# Plan\n\n## 5. Verification layers\n")


# Collecting rule IDs from tests


def test_prefix_ids_do_not_cover_each_other(tmp_path: Path) -> None:
    write(
        tmp_path,
        "tests/unit/test_a.py",
        """\
        import pytest

        @pytest.mark.rule("R44")
        def test_a() -> None: ...

        @pytest.mark.rule("R10")
        def test_b() -> None: ...
        """,
    )
    found = collect_rule_ids(tmp_path)
    assert found == {"R44", "R10"}
    rows = parse_rule_table(TABLE)
    assert "R4" in ids(uncovered(rows, found, 2))
    assert "R1" in ids(uncovered(rows, found, 2))


def test_module_level_pytestmark_counts(tmp_path: Path) -> None:
    write(
        tmp_path,
        "tests/data/test_b.py",
        """\
        import pytest

        pytestmark = [pytest.mark.realdata, pytest.mark.rule("R4")]
        """,
    )
    assert collect_rule_ids(tmp_path) == {"R4"}


def test_one_test_in_either_layer_covers_a_row(tmp_path: Path) -> None:
    write(
        tmp_path,
        "tests/data/test_c.py",
        """\
        import pytest

        @pytest.mark.rule("R4")
        def test_c() -> None: ...
        """,
    )
    rows = [Row("R4", ("L1", "L2"), 2)]
    assert uncovered(rows, collect_rule_ids(tmp_path), 2) == []


@pytest.mark.parametrize(
    ("relative", "text"),
    [
        ("web/src/lib/preprocess.test.ts", 'test("R29: parity", () => {});\n'),
        ("web/src/lib/theme.test.ts", "it('R37: origin check', () => {});\n"),
        ("web/e2e/axe.spec.ts", "test.describe(`R35: axe`, () => {});\n"),
        ("web/e2e/keyboard.ts", 'test("R36: keyboard walk", async () => {});\n'),
    ],
)
def test_web_test_titles_count(tmp_path: Path, relative: str, text: str) -> None:
    write(tmp_path, relative, text)
    assert len(collect_rule_ids(tmp_path)) == 1


@pytest.mark.parametrize(
    ("relative", "text"),
    [
        ("src/heartbeat/notes.py", "NOTE = '@pytest.mark.rule(\"R1\")'\n"),
        ("tests/unit/test_d.py", "TEXT = '@pytest.mark.rule(\"R1\")'\n"),
        ("tests/unit/test_e.py", '# @pytest.mark.rule("R1")\n'),
        ("web/src/lib/notes.ts", "const s = 'test(\"R29: parity\")';\n"),
        ("web/node_modules/x/a.test.ts", 'test("R29: parity", () => {});\n'),
        ("web/src/lib/a.test.ts", 'test("parity R29: late", () => {});\n'),
    ],
)
def test_ids_outside_real_test_markers_do_not_count(
    tmp_path: Path, relative: str, text: str
) -> None:
    write(tmp_path, relative, text)
    assert collect_rule_ids(tmp_path) == set()


# Phase gating


def test_man_only_rows_are_never_required() -> None:
    rows = [Row("R48", ("MAN",), 8)]
    assert uncovered(rows, set(), 8) == []
    assert pending(rows, set(), 1) == []


def test_later_row_is_pending_until_its_phase() -> None:
    rows = [Row("R1", ("L1",), 2)]
    assert uncovered(rows, set(), 1) == []
    assert pending(rows, set(), 1) == rows
    assert uncovered(rows, set(), 2) == rows
    assert pending(rows, set(), 2) == []


def test_covered_later_row_is_not_pending() -> None:
    rows = [Row("R1", ("L1",), 2)]
    assert pending(rows, {"R1"}, 1) == []


def test_current_phase_reads_pyproject(tmp_path: Path) -> None:
    write_pyproject(tmp_path, 3)
    assert current_phase(tmp_path / "pyproject.toml") == 3


def test_current_phase_missing_raises(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[tool.other]\nx = 1\n")
    with pytest.raises(ValueError, match="current-phase"):
        current_phase(tmp_path / "pyproject.toml")


# Command line


def make_repo(root: Path, phase: int, test_ids: list[str]) -> None:
    write(root, "docs/PLAN.md", TABLE)
    write_pyproject(root, phase)
    body = "import pytest\n" + "".join(
        f'\n@pytest.mark.rule("{rule_id}")\ndef test_{n}() -> None: ...\n'
        for n, rule_id in enumerate(test_ids)
    )
    write(root, "tests/unit/test_rules.py", body)


def test_main_passes_and_lists_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_repo(tmp_path, 1, ["R44"])
    assert main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "pending: R1 (phase 2)" in out
    assert "R48" not in out
    assert "uncovered" not in out


def test_main_fails_on_an_uncovered_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_repo(tmp_path, 2, ["R44", "R1"])
    assert main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "uncovered: R4 (phase 2)" in out
    assert "uncovered: R10 (phase 2)" in out
    assert "uncovered: R1 " not in out
