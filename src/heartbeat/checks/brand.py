"""The vendored brand files and their drift check (D2, OPS-10; Phase 6 design call 14).

`web/vendor/brand/` holds copies of files from the dins.dev repo, never
edited here; `SOURCE.json` records the source commit and each file's path
and SHA256. The check reports a vendored file that differs from its record
(edited in place), a source file that differs from it (changed in dins.dev
since), and a missing or unlisted file. It needs the site checkout, so it
runs locally, not in CI. `--update` copies the files again from the source.

Run as `python -m heartbeat.checks.brand --source ~/Develop/dins.dev`.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from heartbeat.paths import REPO_ROOT

SOURCE_NAME = "SOURCE.json"
VENDOR_DIR = REPO_ROOT / "web" / "vendor" / "brand"

# Design call 14: the tokens, the two variable fonts with their licenses, and
# the lockups. JetBrains Mono is not in brand/fonts; the token's fallback
# stack renders mono text.
BRAND_FILES = (
    "brand/tokens/tokens.css",
    "brand/fonts/Fraunces-VF.ttf",
    "brand/fonts/InstrumentSans-VF.ttf",
    "brand/fonts/OFL.txt",
    "brand/fonts/OFL-InstrumentSans.txt",
    "brand/logo/lockup-light.svg",
    "brand/logo/lockup-dark.svg",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit(source: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def vendor_brand(source: Path, dest: Path) -> dict[str, object]:
    """Copy the brand files from a dins.dev checkout and write `SOURCE.json`."""
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    for relative in BRAND_FILES:
        shutil.copyfile(source / relative, dest / PurePosixPath(relative).name)
        files.append({"path": relative, "sha256": _sha256(source / relative)})
    record: dict[str, object] = {
        "label": (
            "Copied from the dins.dev repo, never edited here; change them "
            "there and copy again (D2, OPS-10)"
        ),
        "repository": "dins.dev",
        "commit": _commit(source),
        "files": files,
    }
    (dest / SOURCE_NAME).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def check_brand(source: Path | None, dest: Path) -> list[str]:
    """Drift between the vendored files, `SOURCE.json` and the source checkout.

    Args:
        source: The dins.dev checkout, or None to check the vendored files
            against `SOURCE.json` alone.
        dest: `web/vendor/brand/`.
    """
    record = json.loads((dest / SOURCE_NAME).read_text(encoding="utf-8"))
    problems: list[str] = []
    listed = set()
    for entry in record["files"]:
        name = PurePosixPath(entry["path"]).name
        listed.add(name)
        vendored = dest / name
        if not vendored.is_file():
            problems.append(f"{name}: in {SOURCE_NAME} but missing")
        elif _sha256(vendored) != entry["sha256"]:
            problems.append(
                f"{name}: edited here; change it in dins.dev and copy again"
            )
        if source is not None:
            original = source / entry["path"]
            if not original.is_file():
                problems.append(f"{entry['path']}: missing from the dins.dev checkout")
            elif _sha256(original) != entry["sha256"]:
                problems.append(
                    f"{entry['path']}: changed in dins.dev since commit "
                    f"{record['commit'][:12]}; copy it again with --update"
                )
    for path in sorted(dest.iterdir()):
        if path.name != SOURCE_NAME and path.name not in listed:
            problems.append(f"{path.name}: vendored but not in {SOURCE_NAME}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Print drift and return 1 if any; with `--update`, copy the files again."""
    parser = argparse.ArgumentParser(
        prog="python -m heartbeat.checks.brand", description=__doc__
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, default=VENDOR_DIR)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args(argv)
    source: Path = args.source.expanduser()
    vendor: Path = args.vendor
    if args.update:
        record = vendor_brand(source, vendor)
        sys.stdout.write(f"copied {len(BRAND_FILES)} files at {record['commit']}\n")
    problems = check_brand(source, vendor)
    for problem in problems:
        sys.stdout.write(f"drift: {problem}\n")
    if not problems:
        sys.stdout.write(f"brand files match dins.dev ({len(BRAND_FILES)} files)\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
