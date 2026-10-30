"""Read and validate the four committed manifests (B1, B5, C1; DATA-01 to 03, 11).

Every error names the file and, where it can be found, the line, so a bad
manifest edit points at itself.
"""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

# The three files downloaded per record (DATA-01).
RECORD_EXTENSIONS = ("hea", "dat", "atr")

_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ?([^\s/]+)$")
_FILE_NAME = re.compile(r"^(\d{3})\.(hea|dat|atr)$")


class ManifestError(ValueError):
    """A manifest is malformed or inconsistent."""


@dataclass(frozen=True)
class Splits:
    """The record lists from `manifests/splits.toml`.

    Attributes:
        ds1: Training and development records, in manifest order.
        ds2: The sealed test records (rule 1), in manifest order.
        excluded: Record to the reason it is in neither set.
        lead: The signal name to read (DATA-04).
    """

    ds1: tuple[str, ...]
    ds2: tuple[str, ...]
    excluded: Mapping[str, str]
    lead: str


def _key_line(text: str, key: str) -> int | None:
    """Return the 1-based line where `key` is defined, as a key or a table."""
    escaped = re.escape(key)
    pattern = re.compile(rf'^\s*(?:"{escaped}"|{escaped})\s*=|^\s*\[{escaped}\]')
    for number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return number
    return None


def _value_line(text: str, key: str, value: str, occurrence: int = 1) -> int | None:
    """Return the line of the n-th quoted `value` at or after `key`'s line."""
    start = _key_line(text, key)
    if start is None:
        return None
    needle = f'"{value}"'
    seen = 0
    for number, line in enumerate(text.splitlines()[start - 1 :], start=start):
        seen += line.count(needle)
        if seen >= occurrence:
            return number
    return None


def _where(path: Path, line: int | None) -> str:
    return f"{path}:{line}" if line is not None else str(path)


def _load_toml(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        return text, tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(f"{path}:{error.lineno}: {error.msg}") from error


def _check_keys(
    path: Path, text: str, raw: Mapping[str, Any], required: set[str]
) -> None:
    for key in raw:
        if key not in required:
            raise ManifestError(
                f"{_where(path, _key_line(text, key))}: unknown key {key!r}"
            )
    for key in sorted(required - set(raw)):
        raise ManifestError(f"{path}: missing key {key!r}")


def _record_list(
    path: Path, text: str, raw: Mapping[str, Any], key: str
) -> tuple[str, ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(r, str) for r in value):
        raise ManifestError(
            f"{_where(path, _key_line(text, key))}: {key} must be a list of record IDs"
        )
    seen: set[str] = set()
    for record in value:
        if record in seen:
            line = _value_line(text, key, record, occurrence=2)
            raise ManifestError(
                f"{_where(path, line)}: record {record} listed twice in {key}"
            )
        seen.add(record)
    return tuple(value)


def load_splits(path: Path) -> Splits:
    """Read `splits.toml`: DS1, DS2, the exclusions and the lead (R3).

    Raises:
        ManifestError: On an unknown or missing key, a duplicate record, or a
            record in more than one of DS1, DS2 and the exclusions.
    """
    text, raw = _load_toml(path)
    _check_keys(
        path, text, raw, {"database", "version", "lead", "ds1", "ds2", "excluded"}
    )
    ds1 = _record_list(path, text, raw, "ds1")
    ds2 = _record_list(path, text, raw, "ds2")
    excluded = raw["excluded"]
    if not isinstance(excluded, dict) or not all(
        isinstance(v, str) for v in excluded.values()
    ):
        raise ManifestError(
            f"{_where(path, _key_line(text, 'excluded'))}: "
            "excluded must map record IDs to reasons"
        )
    for record in ds2:
        if record in ds1:
            line = _value_line(text, "ds2", record)
            raise ManifestError(
                f"{_where(path, line)}: record {record} in both ds1 and ds2"
            )
    for key, records in (("ds1", ds1), ("ds2", ds2)):
        for record in records:
            if record in excluded:
                line = _value_line(text, key, record)
                raise ManifestError(
                    f"{_where(path, line)}: excluded record {record} listed in {key}"
                )
    lead = raw["lead"]
    if not isinstance(lead, str):
        raise ManifestError(
            f"{_where(path, _key_line(text, 'lead'))}: lead must be a string"
        )
    return Splits(
        ds1=ds1, ds2=ds2, excluded=MappingProxyType(dict(excluded)), lead=lead
    )


def load_subjects(path: Path) -> Mapping[str, str]:
    """Read `subjects.toml`: record ID to subject ID (R12).

    Raises:
        ManifestError: On an unknown table or a subject that is not a string.
    """
    text, raw = _load_toml(path)
    _check_keys(path, text, raw, {"subjects"})
    subjects = raw["subjects"]
    if not isinstance(subjects, dict):
        raise ManifestError(
            f"{_where(path, _key_line(text, 'subjects'))}: [subjects] must be a table"
        )
    for record, subject in subjects.items():
        if not isinstance(subject, str):
            raise ManifestError(
                f"{_where(path, _key_line(text, record))}: subject of record {record} "
                "must be a string"
            )
    return MappingProxyType(dict(subjects))


def load_checksums(path: Path) -> Mapping[str, str]:
    """Read the checksum manifest: file name to lowercase SHA256 hex (R1, R2).

    The format is PhysioNet's `SHA256SUMS.txt` line (`<hex> <name>`); the
    `sha256sum` two-space form is accepted too.

    Raises:
        ManifestError: On a malformed line or a file listed twice.
    """
    checksums: dict[str, str] = {}
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        match = _CHECKSUM_LINE.match(line)
        if match is None:
            raise ManifestError(f"{path}:{number}: malformed checksum line {line!r}")
        digest, name = match.groups()
        if name in checksums:
            raise ManifestError(f"{path}:{number}: file {name} listed twice")
        checksums[name] = digest
    return MappingProxyType(checksums)


def load_beat_counts(path: Path) -> Mapping[str, Mapping[str, int]]:
    """Read the expected per-record counts by annotation symbol (DATA-11, R11).

    Raises:
        ManifestError: On an unknown table or a count that is not a positive integer.
    """
    text, raw = _load_toml(path)
    _check_keys(path, text, raw, {"records"})
    records = raw["records"]
    if not isinstance(records, dict):
        raise ManifestError(
            f"{_where(path, _key_line(text, 'records'))}: [records] must be a table"
        )
    out: dict[str, Mapping[str, int]] = {}
    for record, counts in records.items():
        if not isinstance(counts, dict) or not all(
            isinstance(n, int) and not isinstance(n, bool) and n > 0
            for n in counts.values()
        ):
            raise ManifestError(
                f"{_where(path, _key_line(text, record))}: counts of record {record} "
                "must be positive integers"
            )
        out[record] = MappingProxyType(dict(counts))
    return MappingProxyType(out)


def downloaded_records(checksums: Mapping[str, str]) -> tuple[str, ...]:
    """Return the sorted record IDs the checksum manifest covers.

    Raises:
        ManifestError: If a file name is not `<record>.<hea|dat|atr>`, or a
            record lacks one of its three files.
    """
    files: dict[str, set[str]] = {}
    for name in checksums:
        match = _FILE_NAME.match(name)
        if match is None:
            raise ManifestError(f"checksum manifest: unexpected file name {name!r}")
        record, extension = match.groups()
        files.setdefault(record, set()).add(extension)
    for record, extensions in files.items():
        missing = set(RECORD_EXTENSIONS) - extensions
        if missing:
            raise ManifestError(
                f"checksum manifest: record {record} lacks {sorted(missing)}"
            )
    return tuple(sorted(files))
