"""R44: the two-tier wording lint (Phase 1 settling, 2 of 4).

Planted dashes are written as escapes so this file passes its own check.
"""

import subprocess
from pathlib import Path

import pytest

from heartbeat.checks.wording import (
    PUBLISHED_PATHS,
    Finding,
    check_dashes,
    check_published,
    main,
    scan,
)
from heartbeat.paths import REPO_ROOT

EM = "\u2014"
EN = "\u2013"
ENTITIES = ("&mdash;", "&ndash;", "&#8212;", "&#8211;", "&#x2014;", "&#X2013;")

pytestmark = pytest.mark.rule("R44")


def rules(findings: list[Finding]) -> list[str]:
    return [f.rule for f in findings]


# Dash tier: failures


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("notes.md", f"A pause{EM}then more.\n"),
        ("notes.md", f"Run `a{EM}b` here.\n"),
        ("notes.md", f"Intro.\n\n```text\nx {EM} y\n```\n"),
        ("module.py", f"x = 1  # one{EM}two\n"),
        ("page.svelte", f"<p>a{EM}b</p>\n"),
    ],
)
def test_em_dash_fails_anywhere(name: str, text: str) -> None:
    assert "em-dash" in rules(check_dashes(Path(name), text))


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("notes.md", f"Pages 1{EN}5.\n"),
        ("notes.md", f"```\n1{EN}5\n```\n"),
        ("trace.ts", f"// 1{EN}5\n"),
        ("config.toml", f'range = "1{EN}5"\n'),
    ],
)
def test_en_dash_fails_anywhere(name: str, text: str) -> None:
    assert "en-dash" in rules(check_dashes(Path(name), text))


@pytest.mark.parametrize(
    "line",
    [
        "The filter - zero phase - runs first.",
        "  - A list item - with a dash inside.",
        "> Quoted - with a dash.",
        "| cell - with a dash | other |",
    ],
)
def test_spaced_hyphen_in_markdown_prose_fails(line: str) -> None:
    assert "spaced-hyphen" in rules(check_dashes(Path("notes.md"), line + "\n"))


def test_spaced_double_hyphen_in_markdown_prose_fails() -> None:
    findings = check_dashes(Path("notes.md"), "The filter -- zero phase.\n")
    assert "double-hyphen" in rules(findings)


@pytest.mark.parametrize("entity", ENTITIES)
def test_dash_entity_in_markdown_prose_fails(entity: str) -> None:
    findings = check_dashes(Path("notes.md"), f"A pause{entity}then more.\n")
    assert "dash-entity" in rules(findings)


@pytest.mark.parametrize("entity", ENTITIES)
@pytest.mark.parametrize("name", ["index.html", "App.svelte"])
def test_dash_entity_anywhere_in_html_and_svelte_fails(name: str, entity: str) -> None:
    text = f"<script>\n  const s = '{entity}';\n</script>\n<code>{entity}</code>\n"
    findings = check_dashes(Path(name), text)
    assert rules(findings).count("dash-entity") == 2


def test_finding_carries_path_line_and_excerpt() -> None:
    findings = check_dashes(Path("docs/notes.md"), f"Fine.\n\nBad{EM}line.\n")
    assert findings == [
        Finding(Path("docs/notes.md"), 3, "em-dash", f"Bad{EM}line."),
    ]


# Dash tier: passes


@pytest.mark.parametrize(
    "text",
    [
        "- item\n",
        "  - nested item\n",
        "- [ ] task\n",
        "- [x] done task\n",
        "* star item\n",
        "1. numbered item\n",
        "> - quoted item\n",
        "| --- | --- |\n",
        "| :--- | ---: |\n",
        "|  |  |\n",
        "---\ntitle: Heartbeat\n---\n\nBody.\n",
        "Text.\n\n---\n\nMore.\n",
        "A zero-phase, 0.5 to 40 Hz, 1-indexed filter.\n",
        "A value of -5 and x = -1.\n",
        "Pages 433-438.\n",
        "Run `x - y` and `a -- b` and `&mdash;`.\n",
        "Intro.\n\n```python\nz = (x - mean) / std  # &mdash; a -- b\n```\n",
        "Intro.\n\n~~~\nx - y\n~~~\n",
        "Ends with a hyphen -\n",
        "",
    ],
)
def test_ordinary_markdown_passes(text: str) -> None:
    assert check_dashes(Path("notes.md"), text) == []


@pytest.mark.parametrize(
    "path",
    [
        "uv.lock",
        "web/pnpm-lock.yaml",
        "web/vendor/brand/tokens.css",
        "web/vendor/brand/README.md",
    ],
)
def test_lockfiles_and_vendored_brand_are_exempt(path: str) -> None:
    text = f"a{EM}b{EN}c - d &mdash; e\n"
    assert check_dashes(Path(path), text) == []


@pytest.mark.parametrize("name", ["module.py", "trace.ts", "index.html"])
def test_spaced_hyphen_outside_markdown_passes(name: str) -> None:
    assert check_dashes(Path(name), "x = a - b -- c\n") == []


def test_entity_in_python_passes() -> None:
    assert check_dashes(Path("module.py"), 'ENTITY = "&mdash;"\n') == []


# Published tier: failures


@pytest.mark.parametrize(
    "text",
    [
        "This tool can diagnose heart problems.",
        "Not for diagnosis.",
        "A diagnostic aid.",
        "It was diagnosed early.",
        "DIAGNOSE nothing.",
        "The model detects arrhythmia.",
        "It can detect arrhythmias.",
        "It detects heart disease.",
        "A clinical-grade model.",
        "A clinical grade model.",
        "Your AI doctor.",
        "Ai Doctor in a box.",
        "Elevate your workflow.",
        "A seamless demo.",
        "Unleash the model.",
        "Our journey so far.",
        "A tapestry of beats.",
    ],
)
def test_published_text_avoid_list_fails(text: str) -> None:
    assert check_published(Path("README.md"), text + "\n") != []


@pytest.mark.parametrize(
    "text",
    [
        "# An accurate model\n",
        "### Accurate beats\n",
        "<h1>Accurate</h1>\n",
        '<h3 class="x">Very accurate</h3>\n',
        "<title>Accurate demo</title>\n",
        "Accurate labels\n===============\n",
    ],
)
def test_accurate_in_a_heading_fails(text: str) -> None:
    assert "accurate-heading" in rules(check_published(Path("README.md"), text))


@pytest.mark.parametrize("path", PUBLISHED_PATHS)
def test_every_published_path_is_checked(path: str) -> None:
    assert check_published(Path(path), "We diagnose nothing.\n") != []


# Published tier: passes


@pytest.mark.parametrize(
    "text",
    [
        "The labels are accurate on DS1 only after a run says so.\n",
        "# Accuracy on the leaky split\n",
        "Accuracy appears only in the exhibit.\n",
        "It labels heartbeats on patients it never saw.\n",
        "A research demo, not medical advice.\n",
    ],
)
def test_ordinary_published_text_passes(text: str) -> None:
    assert check_published(Path("README.md"), text) == []


@pytest.mark.parametrize(
    "path", ["docs/PRD.md", "AGENTS.md", "tests/unit/test_x.py", "docs/PLAN.md"]
)
def test_avoid_list_outside_published_paths_passes(path: str) -> None:
    text = "# Accurate\nWe diagnose, a seamless journey, an AI doctor.\n"
    assert check_published(Path(path), text) == []


# Command line (Phase 1 exit criterion)


def test_main_fails_on_a_readme_with_a_planted_em_dash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text(f"# Heartbeat\n\nA pause{EM}here.\n")
    assert main(["--root", str(tmp_path), "README.md"]) == 1
    assert capsys.readouterr().out.startswith("README.md:3: em-dash: ")


def test_main_fails_on_a_readme_with_a_planted_diagnose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text("# Heartbeat\n\nIt can diagnose you.\n")
    assert main(["--root", str(tmp_path), "README.md"]) == 1
    assert "README.md:3: avoid-term: " in capsys.readouterr().out


def test_main_passes_a_clean_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Heartbeat\n\nIt labels heartbeats.\n")
    assert main(["--root", str(tmp_path), "README.md"]) == 0


def test_scan_skips_binary_files(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\x00\xff" + EM.encode())
    assert scan(tmp_path, [Path("blob.bin")]) == []


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_default_scan_covers_new_files_but_not_ignored_ones(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("ignored.md\n")
    (tmp_path / "tracked.md").write_text(f"a{EM}b\n")
    git(tmp_path, "add", ".gitignore", "tracked.md")
    (tmp_path / "new.md").write_text(f"a{EM}b\n")
    (tmp_path / "ignored.md").write_text(f"a{EM}b\n")
    paths = sorted(f.path.as_posix() for f in scan(tmp_path))
    assert paths == ["new.md", "tracked.md"]


# The repo itself


def test_repo_is_clean() -> None:
    assert scan(REPO_ROOT) == []
