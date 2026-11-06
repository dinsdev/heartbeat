"""The case study renders from a template and every number comes from a file.

Phase 8 settling 11, design calls 3, 4 and 6; PUB-01, PUB-02, PUB-03, PUB-05 and
rigor rule 2. Each check is a function, and
`test_each_check_fails_on_a_planted_bad_draft` plants the fault it looks for.
"""

import copy
import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from heartbeat.cards.blocks import _test_per_patient, interval, num
from heartbeat.checks.wording import check_dashes, check_published
from heartbeat.paths import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "render_case_study.py"
FOLDER = REPO_ROOT / "docs" / "case-study"
TEMPLATE = FOLDER / "heartbeat.template.mdx"
RENDERED = FOLDER / "heartbeat.mdx"
OTTIE = FOLDER / "ottie"
OUTLINE = REPO_ROOT / "docs" / "CASE_STUDY_OUTLINE.md"
SEALED = REPO_ROOT / "results" / "test_runs" / "1-sealed.json"

# `PUBLISHED_PATHS` lives under src/, which is frozen (Phase 8 settling 2), and it
# does not name these files. So their text is passed to the lint's two checks
# under a path that is published and ends in .md, which turns on every rule.
LINT_AS = Path("docs/MODEL_CARD.md")

# Every digit allowed in the template or an Ottie draft outside a slot, with why.
# Longest first when applied, so a citation is removed before a shorter match.
ALLOWED_DIGITS = {
    "record 200": "a record's name, not a result",
    "record 202": "a record's name, not a result",
    "Records 201 and 202": "records' names, not results",
    "Record 232": "a record's name, not a result",
    "record 232": "a record's name, not a result",
    "201 and 202": "records' names, not results",
    "seed 0": "the pre-registered headline model's name (EVAL-08)",
    "DS1": "the training set's name",
    "DS2": "the test set's name",
    "F1": "a metric's name",
    "1D": "the kind of convolution",
    "EC57": "the standard's name",
    "(2001)": "a citation's year",
    "(2004)": "a citation's year",
    "(2005)": "a citation's year",
    "(2026)": "a citation's year",
    "20(3):45-50": "a citation's volume and pages",
    "51(7):1196-1206": "a citation's volume and pages",
    "SCR_007345": "a citation's identifier",
    "11446209": "a citation's identifier",
    "10.13026/C2F305": "a citation's DOI",
    "10.1038/s44360-026-00096-z": "a citation's DOI",
    "version 1.0.0": "the database's version",
    "all 22 DS2 records": "de Chazal's test set, in PUB-03's words; not a result here",
    "25 of the recordings": "PhysioNet's page, how records were chosen; not a result",
}
SLOT = re.compile(r"\{\{[^{}]*\}\}")
# Numbers spelled out would pass the digit check. "one", "two" and "zero" are
# ordinary English here ("one lead", "two people", "above zero").
NUMBER_WORDS = re.compile(
    r"\b(?:three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen"
    r"|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty"
    r"|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|percent"
    r"|dozen|half|quarter|third)\b",
    re.I,
)
# Design call 3 and the plan's A4: seed 0 is the headline, and no other seed is
# singled out, on the page or in the template's slots.
OTHER_SEED = re.compile(r"seed[ -]?[12]\b|seed_range\.points", re.I)

# The outline's field table (from dins.dev's zod schema, read only).
KINDS = {"ml", "data-engineering", "data-science", "research"}
REQUIRED_FIELDS = {
    "title",
    "kind",
    "summary",
    "role",
    "stack",
    "results",
    "capture",
    "captureAlt",
    "status",
}
OPTIONAL_FIELDS = {"featured", "demo", "repo"}

# The outline's sections 4 to 12, in order; the site renders 1 to 3 from fields.
SECTIONS = [
    "The question",
    "The trap, shown",
    "The test",
    "The CNN against the baseline",
    "Patient by patient",
    "The 201 and 202 leak",
    "Limits",
    "How to check it",
    "Credits",
]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_case_study", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return load_script()


@pytest.fixture(scope="module")
def template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered() -> str:
    return RENDERED.read_text(encoding="utf-8")


def sealed_report() -> dict[str, Any]:
    report: dict[str, Any] = json.loads(SEALED.read_text(encoding="utf-8"))
    return report


def split_front_matter(text: str) -> tuple[str, str]:
    """The text between the first two `---` lines, and everything after them."""
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert match is not None, "no front matter"
    return match.group(1), match.group(2)


def parse_fields(front: str) -> dict[str, Any]:
    """The template's front matter: `key: <JSON>` lines, which are valid YAML.

    `results:` holds `  - <JSON>` lines. Comment lines are skipped. The repo has
    no YAML dependency and this needs none (Phase 8 global constraints).
    """
    fields: dict[str, Any] = {}
    current: str | None = None
    for line in front.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line.startswith("  - "):
            assert current is not None
            fields[current].append(json.loads(line[4:]))
            continue
        key, _, value = line.partition(":")
        if value.strip():
            fields[key] = json.loads(value.strip())
            current = None
        else:
            fields[key] = []
            current = key
    return fields


def without_code(text: str) -> str:
    """Text with fenced blocks and code spans removed."""
    text = re.sub(r"^```.*?^```$", "", text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", text)


# The checks. Each returns its problems as strings, empty when the text is sound.


def digit_problems(text: str) -> list[str]:
    """Digits outside a slot and outside the allowlist, on any line."""
    stripped = SLOT.sub("", text)
    problems = []
    for line in stripped.splitlines():
        rest = line
        for allowed in sorted(ALLOWED_DIGITS, key=len, reverse=True):
            rest = rest.replace(allowed, "")
        if re.search(r"\d", rest):
            problems.append(f"digit outside a slot: {line.strip()[:100]}")
    return problems


def number_word_problems(text: str) -> list[str]:
    """Numbers spelled out, which the digit check cannot see."""
    return [
        f"number spelled out: {m.group(0)}"
        for m in NUMBER_WORDS.finditer(SLOT.sub("", text))
    ]


def other_seed_problems(text: str) -> list[str]:
    """Any seed but the headline's named on its own."""
    return [
        f"another seed singled out: {m.group(0)}" for m in OTHER_SEED.finditer(text)
    ]


def label_problems(template_text: str) -> list[str]:
    """Each paragraph with a result slot says which set, and CPU or MPS.

    A table belongs to the paragraph before it, and a list item stands alone.
    """
    problems = []
    front, body = split_front_matter(template_text)
    blocks = [line for line in front.splitlines() if "{{" in line and "label" in line]
    for chunk in re.split(r"\n\s*\n", body):
        blocks.append(chunk)
    previous = ""
    for block in blocks:
        check = block
        if block.lstrip().startswith("|") or SLOT.fullmatch(block.strip()):
            check = previous + "\n" + block
        previous = block
        if "{{sealed:" in check and not ("DS2 test" in check and "CPU" in check):
            problems.append(f"sealed slot without 'DS2 test' and CPU: {block[:80]}")
        if "{{exhibit:" in check and not (
            "DS1" in check and "out-of-fold" in check and "MPS" in check
        ):
            problems.append(f"exhibit slot without DS1 out-of-fold, MPS: {block[:80]}")
        if "{{selection:" in check and not ("DS1" in check and "out-of-fold" in check):
            problems.append(f"selection slot without DS1 out-of-fold: {block[:80]}")
    return problems


def wording_problems(text: str) -> list[str]:
    """D7's list, the buzzwords and the dash rules (PUB-05)."""
    return [
        str(finding)
        for finding in [*check_published(LINT_AS, text), *check_dashes(LINT_AS, text)]
    ]


def mdx_problems(rendered_text: str) -> list[str]:
    """MDX reads `{`, `}` and `<` as syntax, so the rendered body has none."""
    _, body = split_front_matter(rendered_text)
    return [
        f"MDX syntax character {ch!r} in the body"
        for ch in "{}<"
        if ch in without_code(body)
    ]


def field_problems(rendered_text: str) -> list[str]:
    """The front matter fits the outline's field table, as a draft."""
    problems = []
    fields = parse_fields(split_front_matter(rendered_text)[0])
    missing = REQUIRED_FIELDS - fields.keys()
    extra = fields.keys() - REQUIRED_FIELDS - OPTIONAL_FIELDS
    if missing:
        problems.append(f"missing fields: {sorted(missing)}")
    if extra:
        problems.append(f"unknown fields: {sorted(extra)}")
    for name, limit in (("title", 80), ("summary", 200), ("role", 300)):
        if not 1 <= len(str(fields.get(name, ""))) <= limit:
            problems.append(f"{name} is not 1 to {limit} characters")
    if fields.get("kind") not in KINDS:
        problems.append("kind is not one of the site's kinds")
    if fields.get("status") != "draft":
        problems.append("status is not draft")
    if not fields.get("stack"):
        problems.append("stack is empty")
    results = fields.get("results") or []
    if len(results) != 3 or any(set(r) != {"value", "label"} for r in results):
        problems.append("results are not three value and label pairs")
    if fields.get("demo") != {"type": "live", "src": "https://heartbeat.dins.dev/"}:
        problems.append("demo is not the live Heartbeat origin")
    if not str(fields.get("repo", "")).startswith("https://"):
        problems.append("repo is not an https link")
    if fields.get("capture") != "./capture.jpg" or not fields.get("captureAlt"):
        problems.append("capture or captureAlt is wrong")
    return problems


def limits_problems(rendered_text: str, report: dict[str, Any]) -> list[str]:
    """PUB-02's list in the limits section, and PUB-03's credit on the page."""
    without = report["s_without_excluded"]["intervals"]["cnn"]
    body = split_front_matter(rendered_text)[1]
    match = re.search(r"^## Limits$(.*?)^## ", body, re.S | re.M)
    limits = match.group(1) if match else ""
    in_limits = {
        "annotations": "these numbers assume every beat has already been found",
        "F": "one patient on each side",
        "record 232": "232 drives the S result",
        "the without-232 line": interval(without["S_recall"]),
        "calibration": "fragile across patients",
        "the lag": "one beat late",
        "the lead": "one lead",
        "the test size": f"tested on {len(report['patients'])} patients",
        "prevalence": "prevalence",
    }
    on_page = {
        "Table VI": "Table VI",
        "PUB-03's comparison": "two-lead classifier tested on all 22 DS2 records",
    }
    return [
        *(f"limits lack {n}: {x}" for n, x in in_limits.items() if x not in limits),
        *(f"page lacks {n}: {x}" for n, x in on_page.items() if x not in body),
    ]


def section_problems(rendered_text: str) -> list[str]:
    """The outline's sections, in its order."""
    headings = re.findall(r"^## (.+)$", split_front_matter(rendered_text)[1], re.M)
    return [] if headings == SECTIONS else [f"sections are {headings}"]


def headline_sentence(report: dict[str, Any]) -> str:
    """The verdict's sentence from the outline, filled here without the script."""
    comparison = report["comparison"]["metrics"]["macro_f1_nsv"]
    outline = OUTLINE.read_text(encoding="utf-8")
    match = re.search(rf"^\*\*{comparison['verdict']}\.\*\* (.+)$", outline, re.M)
    assert match is not None
    sentence = match.group(1)
    values = {
        "n": str(len(report["patients"])),
        "point": num(comparison["point"]),
        "low": num(comparison["low"]),
        "high": num(comparison["high"]),
    }
    for key, value in values.items():
        sentence = sentence.replace(f"`{{{{{key}}}}}`", value)
    return sentence


def headline_problems(rendered_text: str, report: dict[str, Any]) -> list[str]:
    """The verdict's pre-written sentence appears word for word, the others not."""
    problems = []
    sentence = headline_sentence(report)
    if "{{" in sentence:
        problems.append(f"a slot is left in the sentence: {sentence}")
    if sentence not in rendered_text:
        problems.append("the verdict's sentence is not on the page word for word")
    for other in (
        "the CNN beat the logistic-regression baseline",
        "the logistic-regression baseline beat the CNN",
    ):
        if other in rendered_text:
            problems.append(f"another verdict's sentence is on the page: {other}")
    return problems


def test_no_scratch_left_in_the_template(template: str) -> None:
    assert "TODO" not in template
    assert "{{ " not in template


def test_the_template_has_no_digit_outside_a_slot(template: str) -> None:
    assert digit_problems(template) == []


def test_the_template_spells_out_no_number(template: str) -> None:
    assert number_word_problems(template) == []


def test_no_other_seed_is_singled_out(template: str) -> None:
    assert other_seed_problems(template) == []


def test_every_result_slot_has_its_label(template: str) -> None:
    assert label_problems(template) == []


@pytest.mark.parametrize("name", ["template", "rendered"])
def test_the_published_wording_rules_pass(
    name: str, template: str, rendered: str
) -> None:
    assert wording_problems({"template": template, "rendered": rendered}[name]) == []


def test_the_rendered_body_is_safe_for_mdx(rendered: str) -> None:
    assert mdx_problems(rendered) == []


def test_the_front_matter_fits_the_outline(rendered: str) -> None:
    assert field_problems(rendered) == []


def test_the_limits_and_credit_are_present(rendered: str) -> None:
    assert limits_problems(rendered, sealed_report()) == []


def test_the_sections_follow_the_outline(rendered: str) -> None:
    assert section_problems(rendered) == []


def test_the_headline_is_the_pre_written_sentence(rendered: str) -> None:
    assert headline_problems(rendered, sealed_report()) == []


def test_the_page_shows_the_cards_rounding(script: ModuleType) -> None:
    # Design call 3: the page shows the cards' rounding, through one constant.
    entry = {"point": 0.123456, "low": -0.5, "high": 0.75}
    assert script.number(0.123456) == num(0.123456)
    assert script.number(None) == num(None)
    assert script.span(entry) == interval(entry)
    assert script.span({"point": 0.5, "low": None, "high": None}) == interval(
        {"point": 0.5, "low": None, "high": None}
    )


def test_the_per_patient_table_matches_the_model_card(script: ModuleType) -> None:
    report = sealed_report()
    text = _test_per_patient("x", report)
    assert text.endswith(script.per_patient_table(report))


def test_the_rendered_file_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_refuses_a_stale_page(tmp_path: Path) -> None:
    stale = tmp_path / "page.mdx"
    stale.write_text("old", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(stale)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 1
    assert "stale" in result.stdout


def real_sources(script: ModuleType) -> Any:
    return script.load_sources(REPO_ROOT)


@pytest.mark.parametrize(
    "slot",
    [
        "{{sealed: no.such.key}}",
        "{{sealed: headline.intervals.cnn.no_such_metric}}",
        "{{nowhere: patients}}",
        "{{exhibit: rows[side=nobody, model=cnn].accuracy.point}}",
        "{{exhibit: rows[3].no_such_field}}",
        "{{sealed: confusion.matrices.baseline[9][0]}}",
        "{{sealed: patients}}",
        "{{sealed: headline}}",
        "{{sealed: dirty}}",
        "{{freeze: commit.length}}",
        "{{selection: score.whole}}",
        "{{sealed: bare words}}",
    ],
)
def test_an_unresolved_slot_is_an_error(script: ModuleType, slot: str) -> None:
    with pytest.raises(script.SlotError):
        script.fill(slot, real_sources(script))


def test_a_leftover_slot_shape_is_an_error(script: ModuleType) -> None:
    with pytest.raises(script.SlotError):
        script.fill("{{ not a slot", real_sources(script))
    with pytest.raises(script.SlotError):
        script.fill("{{n}}", real_sources(script))


def test_slots_resolve_to_what_the_files_say(script: ModuleType) -> None:
    sources = real_sources(script)
    report = sealed_report()
    head = report["headline"]["intervals"]["cnn"]["macro_f1_nsv"]
    cases = {
        "{{sealed: patients.length}}": str(len(report["patients"])),
        "{{sealed: beats.scored}}": str(report["beats"]["scored"]),
        "{{sealed: headline.intervals.cnn.macro_f1_nsv}}": interval(head),
        "{{sealed: headline.intervals.cnn.macro_f1_nsv.point}}": num(head["point"]),
        "{{sealed: bootstrap.percentiles}}": "2.5 and 97.5",
        "{{sealed: confusion.matrices.cnn-seed-0[3][0]}}": str(
            report["confusion"]["matrices"]["cnn-seed-0"][3][0]
        ),
        "{{sealed: per_patient.cnn-seed-0[patient=s232].S.recall.denominator}}": str(
            next(
                row
                for row in report["per_patient"]["cnn-seed-0"]
                if row["patient"] == "s232"
            )["S"]["recall"]["denominator"]
        ),
        "{{selection: width.whole}}": "1",
    }
    span = report["seed_range"]["range"]["macro_f1_nsv"]
    cases["{{sealed: seed_range.range.macro_f1_nsv}}"] = (
        f"{num(span['min'])} to {num(span['max'])}"
    )
    for slot, want in cases.items():
        assert script.fill(slot, sources) == want, slot


@pytest.mark.parametrize(
    ("verdict", "words"),
    [
        ("CNN better than baseline", "the CNN beat the logistic-regression baseline"),
        ("no clear difference", "show no clear difference"),
        ("baseline better than CNN", "the logistic-regression baseline beat the CNN"),
    ],
)
def test_the_verdict_picks_the_sentence(
    script: ModuleType, verdict: str, words: str
) -> None:
    sources = real_sources(script)
    report = copy.deepcopy(sources.sealed)
    report["comparison"]["metrics"]["macro_f1_nsv"]["verdict"] = verdict
    sentence = script.fill("{{headline}}", script.replace_sealed(sources, report))
    assert words in sentence
    assert "{{" not in sentence
    assert "`" not in sentence


def test_an_unknown_verdict_is_an_error(script: ModuleType) -> None:
    sources = real_sources(script)
    report = copy.deepcopy(sources.sealed)
    report["comparison"]["metrics"]["macro_f1_nsv"]["verdict"] = "a tie"
    with pytest.raises(script.SlotError):
        script.fill("{{headline}}", script.replace_sealed(sources, report))


def test_the_body_reports_sealed_numbers_only_from_the_sealed_entry(
    script: ModuleType,
) -> None:
    # The `sealed` source is never a reproduction report, even when one is logged
    # after it (the outline's Slots table).
    sources = real_sources(script)
    assert sources.sealed["entry_type"] == "sealed"
    assert sources.log["type"] == "sealed"


def plant(text: str, old: str, new: str) -> str:
    assert old in text, old
    return text.replace(old, new)


def planted_drafts(
    template: str, rendered: str
) -> Iterator[tuple[str, Callable[[], list[str]]]]:
    report = sealed_report()
    yield "a typed number", lambda: digit_problems(template + "\nIt scored 0.63.\n")
    yield (
        "a number spelled out",
        lambda: number_word_problems(template + "\nTwenty-one patients.\n"),
    )
    yield (
        "another seed",
        lambda: other_seed_problems(template + "\nSeed 2 did better.\n"),
    )
    yield (
        "another seed's slot",
        lambda: other_seed_problems(template + "\n{{sealed: seed_range.points}}\n"),
    )
    yield (
        "a test number with no label",
        lambda: label_problems(template + "\nIt scored {{sealed: beats.scored}}.\n"),
    )
    yield (
        "an exhibit number with no label",
        lambda: label_problems(template + "\nIt was {{exhibit: n_beats}}.\n"),
    )
    yield (
        "a selection number with no label",
        lambda: label_problems(template + "\nWidth {{selection: epoch}}.\n"),
    )
    yield "D7's list", lambda: wording_problems(template + "\nIt can diagnose.\n")
    yield (
        "an em dash",
        lambda: wording_problems(template + "\nA pause" + chr(0x2014) + "here.\n"),
    )
    yield "a spaced hyphen", lambda: wording_problems(template + "\nA pause - here.\n")
    yield "a brace", lambda: mdx_problems(rendered + "\nA {brace}.\n")
    yield "an angle bracket", lambda: mdx_problems(rendered + "\nUnder <10 beats.\n")
    yield (
        "a long summary",
        lambda: field_problems(
            re.sub(r'^summary: ".*"$', f'summary: "{"x" * 201}"', rendered, flags=re.M)
        ),
    )
    yield (
        "a published status",
        lambda: field_problems(
            plant(rendered, 'status: "draft"', 'status: "published"')
        ),
    )
    yield (
        "a missing field",
        lambda: field_problems(re.sub(r"^role: .*\n", "", rendered, flags=re.M)),
    )
    yield (
        "a lost limit",
        lambda: limits_problems(
            plant(rendered, "one patient on each side", "a few patients"), report
        ),
    )
    yield (
        "no Table VI credit",
        lambda: limits_problems(plant(rendered, "Table VI", "a table"), report),
    )
    yield (
        "a section out of order",
        lambda: section_problems(plant(rendered, "## Limits", "## Caveats")),
    )
    sentence = headline_sentence(report)
    yield (
        "an edited headline",
        lambda: headline_problems(plant(rendered, sentence, "It went fine."), report),
    )
    yield (
        "a second verdict",
        lambda: headline_problems(
            rendered + "\nthe CNN beat the logistic-regression baseline\n", report
        ),
    )


def test_each_check_fails_on_a_planted_bad_draft(template: str, rendered: str) -> None:
    for name, problems in planted_drafts(template, rendered):
        assert problems() != [], f"the check missed {name}"


def result_values() -> set[str]:
    """Every headline number in the sealed report, as the cards print it."""
    report = sealed_report()
    values = set()
    for model in report["headline"]["intervals"].values():
        for entry in model.values():
            values.add(num(entry["point"]))
    return values


def test_readme_and_card_prose_quote_no_test_number() -> None:
    # Design call 9 and the review focus: numbers live in blocks and slots.
    block = re.compile(r"<!-- card:begin .*?<!-- card:end [a-z_0-9]+ -->", re.S)
    values = result_values()
    for path in ("README.md", "docs/MODEL_CARD.md", "docs/DATA_CARD.md"):
        text = block.sub("", (REPO_ROOT / path).read_text(encoding="utf-8"))
        assert not re.findall(r"\b0\.\d{3,}\b", text), path
        assert not [v for v in values if v in text], path


def ottie_files() -> list[Path]:
    return sorted(OTTIE.glob("*.md"))


def test_there_are_three_to_five_ottie_drafts() -> None:
    assert 3 <= len(ottie_files()) <= 5


@pytest.mark.parametrize("path", ottie_files(), ids=lambda p: p.name)
def test_each_ottie_draft_is_an_unapproved_clean_entry(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    front, body = split_front_matter(text)
    # Design call 6, from dins.dev's library schema (read only).
    lines = dict(line.split(": ", 1) for line in front.splitlines() if ": " in line)
    assert lines["project"] == "heartbeat"
    assert lines["language"] == "en"
    assert lines["approved_on"] == "null"
    assert lines["topic"]
    audience = lines["audience"].strip("[]").split(", ")
    assert audience
    assert set(audience) <= {"admissions", "recruiters", "visitors"}
    assert 'sources: [{label: "' in front
    assert body.strip()
    assert digit_problems(text) == []
    assert number_word_problems(text) == []
    assert other_seed_problems(text) == []
    assert wording_problems(text) == []
    assert mdx_problems(text) == []
