"""R44: the two-tier wording lint (Phase 1 settling, 2 of 4).

Tier 1, dashes, covers every tracked text file except lockfiles and the vendored
brand files: U+2014 and U+2013 anywhere; in Markdown prose, a hyphen or double
hyphen with a space on each side, and dash entities; dash entities anywhere in
HTML and Svelte files.

Tier 2, published text (`PUBLISHED_PATHS`): D7's avoid list, Din's buzzword list,
and "accurate" in a heading.

Run as `python -m heartbeat.checks.wording [--root DIR] [paths...]`.
"""

import argparse
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from heartbeat.paths import REPO_ROOT

# D7 and F6: the published text that exists today. The built demo text and the
# case study draft join when they exist.
PUBLISHED_PATHS = ("README.md", "docs/MODEL_CARD.md", "docs/DATA_CARD.md")

LOCKFILE_NAMES = frozenset({"uv.lock", "pnpm-lock.yaml"})
VENDORED_PREFIX = ("web", "vendor", "brand")
MARKDOWN_SUFFIXES = frozenset({".md"})
HTML_SUFFIXES = frozenset({".html", ".svelte"})

EM_DASH = "\u2014"
EN_DASH = "\u2013"
DASH_ENTITY = re.compile(r"&(?:mdash|ndash);|&#0*82(?:12|11);|&#x0*201[34];", re.I)
SPACED_HYPHEN = re.compile(r"\S[ \t]+-[ \t]+\S")
SPACED_DOUBLE_HYPHEN = re.compile(r"\S[ \t]+--[ \t]+\S")

FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+).+?(?<!`)\1(?!`)")
LINE_PREFIX = re.compile(r"^\s*(?:>\s*)*(?:(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?)?")
THEMATIC_BREAK = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")

# D7's avoid list, as widened in Phase 1 settling 2 of 4 (`diagnos` on purpose).
AVOID_TERMS = re.compile(
    r"\bdiagnos\w*"
    r"|\bdetect\w*\s+arrhythmi\w*"
    r"|\bdetect\w*\s+heart\s+disease\b"
    r"|\bclinical[- ]grade\b"
    r"|\bAI\s+doctors?\b",
    re.I,
)
# Din's buzzword list, with its inflections.
BUZZWORDS = re.compile(
    r"\belevat(?:e|es|ed|ing)\b"
    r"|\bseamless(?:ly)?\b"
    r"|\bunleash(?:es|ed|ing)?\b"
    r"|\bjourneys?\b"
    r"|\btapestr(?:y|ies)\b",
    re.I,
)
ACCURATE = re.compile(r"\baccurate\b", re.I)
ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
HTML_HEADING = re.compile(r"<(h[1-6]|title)\b[^>]*>(.*?)</\1\s*>", re.I | re.S)

EXCERPT_CHARS = 120


@dataclass(frozen=True)
class Finding:
    """One wording problem, printed as `path:line: rule: excerpt`."""

    path: Path
    line: int
    rule: str
    excerpt: str

    def __str__(self) -> str:
        """Return the finding as one line of command output."""
        return f"{self.path.as_posix()}:{self.line}: {self.rule}: {self.excerpt}"


def _finding(path: Path, line_no: int, rule: str, line: str) -> Finding:
    return Finding(path, line_no, rule, line.strip()[:EXCERPT_CHARS])


def is_exempt(path: Path) -> bool:
    """Return whether the dash tier skips this path (lockfiles, vendored brand)."""
    return path.name in LOCKFILE_NAMES or path.parts[:3] == VENDORED_PREFIX


def markdown_prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (line number, prose) for Markdown lines outside code and front matter.

    Code spans are replaced by a placeholder so text around them is still checked.
    List markers, task boxes and blockquote markers are stripped from the start.
    """
    lines = text.splitlines()
    in_front_matter = bool(lines) and lines[0].strip() == "---"
    fence: str | None = None
    for index, line in enumerate(lines):
        line_no = index + 1
        if in_front_matter:
            if index > 0 and line.strip() in {"---", "..."}:
                in_front_matter = False
            continue
        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            continue
        opened = FENCE_OPEN.match(line)
        if opened:
            fence = opened.group(1)
            continue
        if THEMATIC_BREAK.match(line):
            continue
        prose = CODE_SPAN.sub("C", line)
        yield line_no, LINE_PREFIX.sub("", prose, count=1)


def check_dashes(path: Path, text: str) -> list[Finding]:
    """Return the dash tier's findings for one file.

    Args:
        path: The file's path relative to the repo root; picks the rules.
        text: The file's contents.
    """
    if is_exempt(path):
        return []
    findings: list[Finding] = []
    lines = text.splitlines()
    whole_file_entities = path.suffix in HTML_SUFFIXES
    for index, line in enumerate(lines):
        if EM_DASH in line:
            findings.append(_finding(path, index + 1, "em-dash", line))
        if EN_DASH in line:
            findings.append(_finding(path, index + 1, "en-dash", line))
        if whole_file_entities and DASH_ENTITY.search(line):
            findings.append(_finding(path, index + 1, "dash-entity", line))
    if path.suffix in MARKDOWN_SUFFIXES:
        for line_no, prose in markdown_prose_lines(text):
            original = lines[line_no - 1]
            if SPACED_HYPHEN.search(prose):
                findings.append(_finding(path, line_no, "spaced-hyphen", original))
            if SPACED_DOUBLE_HYPHEN.search(prose):
                findings.append(_finding(path, line_no, "double-hyphen", original))
            if DASH_ENTITY.search(prose):
                findings.append(_finding(path, line_no, "dash-entity", original))
    return sorted(findings, key=lambda f: f.line)


def check_published(path: Path, text: str) -> list[Finding]:
    """Return the published tier's findings, or none if the path is not published.

    Args:
        path: The file's path relative to the repo root.
        text: The file's contents.
    """
    if path.as_posix() not in PUBLISHED_PATHS:
        return []
    findings: list[Finding] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if AVOID_TERMS.search(line):
            findings.append(_finding(path, index + 1, "avoid-term", line))
        if BUZZWORDS.search(line):
            findings.append(_finding(path, index + 1, "buzzword", line))
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        is_heading = ATX_HEADING.match(line) or (
            line.strip() and SETEXT_UNDERLINE.match(next_line)
        )
        if is_heading and ACCURATE.search(line):
            findings.append(_finding(path, index + 1, "accurate-heading", line))
    for match in HTML_HEADING.finditer(text):
        if ACCURATE.search(match.group(2)):
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                _finding(path, line_no, "accurate-heading", lines[line_no - 1])
            )
    return sorted(set(findings), key=lambda f: (f.line, f.rule))


def tracked_files(root: Path) -> list[Path]:
    """Return the files git tracks or would track under `root`, relative to it.

    New files not yet added count too (ignored ones do not), so the check that
    runs before a commit sees the files about to be committed.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    names = result.stdout.decode().split("\0")
    return [Path(name) for name in names if name and (root / name).is_file()]


def read_text(path: Path) -> str | None:
    """Return a file's text, or None if it is binary or not UTF-8."""
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan(root: Path, paths: Sequence[Path] | None = None) -> list[Finding]:
    """Run both tiers over files under `root`.

    Args:
        root: The directory paths are resolved against and reported relative to.
        paths: Files to check; defaults to every file git tracks or would track.

    Returns:
        Every finding, in path then line order.
    """
    root = root.resolve()
    findings: list[Finding] = []
    for path in tracked_files(root) if paths is None else paths:
        full = (path if path.is_absolute() else root / path).resolve()
        try:
            relative = full.relative_to(root)
        except ValueError:
            relative = full
        text = read_text(full)
        if text is None:
            continue
        findings += check_dashes(relative, text)
        findings += check_published(relative, text)
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Print every finding; return 1 if there are any, else 0."""
    parser = argparse.ArgumentParser(
        prog="python -m heartbeat.checks.wording", description=__doc__
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    findings = scan(args.root, args.paths or None)
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
