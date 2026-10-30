"""Fill and check the MIT-BIH cache against the pinned checksums (B5; DATA-01, DATA-02).

Files are written to a temporary name in the cache folder and moved into place
only after their hash matches, so an interrupted run never leaves a partial
file under a real name (PLAN section 7, review focus 1).
"""

import hashlib
import logging
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

log = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 60
_TEMP_SUFFIX = ".part"
_CHUNK_BYTES = 1 << 20


class ChecksumMismatchError(RuntimeError):
    """A cached or downloaded file does not match its pinned SHA256 (R1)."""


class DownloadError(RuntimeError):
    """No source could serve a file."""


@dataclass(frozen=True)
class CacheStatus:
    """Result of checking the cache.

    Attributes:
        ok: True when every pinned file is present and matches.
        missing: Pinned files not in the cache, sorted.
    """

    ok: bool
    missing: tuple[str, ...]


@dataclass(frozen=True)
class DownloadReport:
    """What `download` did.

    Attributes:
        fetched: Files downloaded this run, sorted.
        skipped: Files already cached with a matching hash, sorted.
        source_used: Fetched file to the source URL that served it.
    """

    fetched: tuple[str, ...]
    skipped: tuple[str, ...]
    source_used: Mapping[str, str]


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_url(url: str) -> bytes:
    """Fetch a URL's body with a 60 s timeout."""
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_S) as response:
        body: bytes = response.read()
    return body


def _mismatch(path: Path) -> ChecksumMismatchError:
    return ChecksumMismatchError(
        f"{path}: SHA256 does not match manifests/mitdb-1.0.0.sha256; "
        "delete the file and run `uv run heartbeat download` again"
    )


def check_cache(raw_dir: Path, checksums: Mapping[str, str]) -> CacheStatus:
    """Check every pinned file that is present, and list the missing ones (R2).

    Raises:
        ChecksumMismatchError: On the first present file whose hash differs. The
            file is left in place; the run stops (DATA-02).
    """
    missing: list[str] = []
    for name in sorted(checksums):
        path = raw_dir / name
        if not path.is_file():
            missing.append(name)
        elif sha256_file(path) != checksums[name]:
            raise _mismatch(path)
    return CacheStatus(ok=not missing, missing=tuple(missing))


def _remove_stale_temporaries(raw_dir: Path) -> None:
    for stale in raw_dir.glob(f".*{_TEMP_SUFFIX}"):
        log.info("removing %s from an interrupted run", stale)
        stale.unlink()


def _write_atomically(path: Path, data: bytes, expected: str) -> None:
    temp = path.with_name(f".{path.name}{_TEMP_SUFFIX}")
    try:
        temp.write_bytes(data)
        if sha256_file(temp) != expected:
            raise _mismatch(temp)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def download(
    raw_dir: Path,
    checksums: Mapping[str, str],
    sources: Sequence[str],
    fetch: Callable[[str], bytes] = fetch_url,
) -> DownloadReport:
    """Download every pinned file that is not cached yet (DATA-01).

    Args:
        raw_dir: The cache folder; created if absent.
        checksums: File name to pinned SHA256.
        sources: Base URLs, tried in order for each file.
        fetch: Returns a URL's body; injected so tests need no network.

    Returns:
        What was fetched, what was skipped, and which source served each file.

    Raises:
        ChecksumMismatchError: If a cached file's hash differs, or no source
            served a file whose hash matches.
        DownloadError: If every source failed to serve a file.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_temporaries(raw_dir)
    status = check_cache(raw_dir, checksums)
    skipped = tuple(sorted(set(checksums) - set(status.missing)))
    source_used: dict[str, str] = {}
    for name in status.missing:
        expected = checksums[name]
        problems: list[str] = []
        hash_mismatch = False
        for source in sources:
            url = source + name
            try:
                data = fetch(url)
            except OSError as error:
                problems.append(f"{url}: {error}")
                log.warning("fetch failed, trying the next source: %s: %s", url, error)
                continue
            if hashlib.sha256(data).hexdigest() != expected:
                hash_mismatch = True
                problems.append(f"{url}: SHA256 does not match the manifest")
                log.warning("hash mismatch, trying the next source: %s", url)
                continue
            _write_atomically(raw_dir / name, data, expected)
            source_used[name] = source
            break
        else:
            detail = "; ".join(problems)
            if hash_mismatch:
                raise ChecksumMismatchError(f"{name}: no source matched ({detail})")
            raise DownloadError(f"{name}: every source failed ({detail})")
    return DownloadReport(
        fetched=tuple(sorted(source_used)),
        skipped=skipped,
        source_used=MappingProxyType(source_used),
    )
