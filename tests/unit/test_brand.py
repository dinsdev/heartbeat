"""The vendored brand files and their drift check (D2, OPS-10; design call 14)."""

import hashlib
import json
from pathlib import Path

import pytest

from heartbeat.checks.brand import (
    BRAND_FILES,
    SOURCE_NAME,
    check_brand,
    main,
    vendor_brand,
)
from heartbeat.paths import REPO_ROOT

VENDOR = REPO_ROOT / "web" / "vendor" / "brand"


def _source_tree(root: Path) -> Path:
    """A fake dins.dev checkout holding every brand file, in a git repo."""
    import subprocess

    for relative in BRAND_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{relative}\n".encode())
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "commit",
            "-qm",
            "brand",
        ],
        cwd=root,
        check=True,
    )
    return root


def test_vendoring_copies_each_file_and_records_commit_path_and_hash(
    tmp_path: Path,
) -> None:
    source = _source_tree(tmp_path / "site")
    dest = tmp_path / "vendor"
    vendor_brand(source, dest)
    record = json.loads((dest / SOURCE_NAME).read_text("utf-8"))
    assert len(record["commit"]) == 40
    assert sorted(f["path"] for f in record["files"]) == sorted(BRAND_FILES)
    for entry in record["files"]:
        data = (dest / Path(entry["path"]).name).read_bytes()
        assert data == (source / entry["path"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert check_brand(source, dest) == []


def test_a_file_edited_in_place_is_drift(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "site")
    dest = tmp_path / "vendor"
    vendor_brand(source, dest)
    (dest / "tokens.css").write_text("/* edited here */\n", encoding="utf-8")
    problems = check_brand(source, dest)
    assert any("tokens.css" in p and "edited" in p for p in problems)


def test_a_changed_source_file_is_drift(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "site")
    dest = tmp_path / "vendor"
    vendor_brand(source, dest)
    (source / "brand/fonts/Fraunces-VF.ttf").write_bytes(b"new font")
    problems = check_brand(source, dest)
    assert any("Fraunces-VF.ttf" in p and "dins.dev" in p for p in problems)


def test_a_missing_or_unlisted_vendored_file_is_drift(tmp_path: Path) -> None:
    source = _source_tree(tmp_path / "site")
    dest = tmp_path / "vendor"
    vendor_brand(source, dest)
    (dest / "OFL.txt").unlink()
    (dest / "extra.css").write_text("x\n", encoding="utf-8")
    problems = check_brand(source, dest)
    assert any("OFL.txt" in p for p in problems)
    assert any("extra.css" in p for p in problems)


def test_main_exits_1_on_drift_and_0_when_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _source_tree(tmp_path / "site")
    dest = tmp_path / "vendor"
    vendor_brand(source, dest)
    assert main(["--source", str(source), "--vendor", str(dest)]) == 0
    (dest / "lockup-light.svg").write_text("<svg/>\n", encoding="utf-8")
    assert main(["--source", str(source), "--vendor", str(dest)]) == 1
    assert "lockup-light.svg" in capsys.readouterr().out


def test_the_committed_vendored_files_match_their_source_record() -> None:
    # Without the site checkout (CI): the vendored bytes equal SOURCE.json.
    record = json.loads((VENDOR / SOURCE_NAME).read_text("utf-8"))
    assert sorted(f["path"] for f in record["files"]) == sorted(BRAND_FILES)
    for entry in record["files"]:
        data = (VENDOR / Path(entry["path"]).name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
