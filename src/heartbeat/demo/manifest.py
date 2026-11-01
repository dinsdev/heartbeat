"""The demo data's `manifest.json` and its check against the files (DEMO-08, R31).

Every other file in the demo data folder is named by its content
(`<stem>.<first 8 hex of its SHA256><suffix>`, design call 2), so it can be
served as immutable; the manifest is the one unhashed file and lists each
file's name, size in bytes and SHA256.
"""

import hashlib
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"
HASH_CHARS = 8


def file_entry(name: str, data: bytes) -> dict[str, Any]:
    """The manifest entry of one file: name, size and SHA256."""
    return {
        "bytes": len(data),
        "name": name,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def hashed_name(stem: str, suffix: str, data: bytes) -> str:
    """`<stem>.<hash8><suffix>`, for example `223.1a2b3c4d.trace.i16`."""
    return f"{stem}.{hashlib.sha256(data).hexdigest()[:HASH_CHARS]}{suffix}"


def listed_files(manifest: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Every file entry the manifest lists."""
    model = manifest["model"]
    yield from (model[key] for key in ("model", "scaler", "calibration", "notice"))
    yield manifest["attribution_file"]
    for record in manifest["records"]:
        yield record["trace"]
        yield record["beats"]


def check_manifest(folder: Path) -> list[str]:
    """Problems between `folder/manifest.json` and the files beside it (R31).

    A listed file that is missing, of another size or SHA256, or whose name
    does not carry its own hash, and any file in the folder the manifest does
    not list, is a problem. An empty list means they match.
    """
    path = folder / MANIFEST_NAME
    if not path.is_file():
        return [f"{path} missing"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    names: set[str] = set()
    for entry in listed_files(manifest):
        name = entry["name"]
        names.add(name)
        file = folder / name
        if not file.is_file():
            problems.append(f"{name}: listed in the manifest but missing")
            continue
        data = file.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != entry["bytes"]:
            problems.append(f"{name}: {len(data)} bytes, manifest {entry['bytes']}")
        if digest != entry["sha256"]:
            problems.append(f"{name}: SHA256 {digest}, manifest {entry['sha256']}")
        if f".{digest[:HASH_CHARS]}." not in name:
            problems.append(f"{name}: the name does not carry its hash {digest[:8]}")
    for file in sorted(folder.iterdir()):
        if file.name != MANIFEST_NAME and file.name not in names:
            problems.append(f"{file.name}: in the folder but not in the manifest")
    return problems
