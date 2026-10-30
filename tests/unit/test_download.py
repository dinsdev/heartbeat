"""DATA-01, DATA-02: the checksum-pinned downloader (R1, review focus 1)."""

import hashlib
import urllib.error
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from heartbeat.data.download import (
    CacheStatus,
    ChecksumMismatchError,
    DownloadError,
    check_cache,
    download,
    sha256_file,
)

S3 = "https://s3.example/mitdb/"
PHYSIONET = "https://physionet.example/mitdb/"
SOURCES = (S3, PHYSIONET)

GOOD = {"100.atr": b"annotations", "100.dat": b"signal bytes", "100.hea": b"header"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


CHECKSUMS = {name: _digest(data) for name, data in GOOD.items()}


class FakeFetch:
    """Serves bytes per URL and records every call."""

    def __init__(self, responses: Mapping[str, bytes | Exception]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def _serve(source: str, files: Mapping[str, bytes]) -> dict[str, bytes | Exception]:
    return {source + name: data for name, data in files.items()}


def _final_names(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir()}


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"heartbeat")
    assert sha256_file(path) == _digest(b"heartbeat")


def test_empty_cache_downloads_every_file_from_the_first_source(
    tmp_path: Path,
) -> None:
    fetch = FakeFetch(_serve(S3, GOOD))
    report = download(tmp_path, CHECKSUMS, SOURCES, fetch=fetch)
    assert set(report.fetched) == set(GOOD)
    assert report.skipped == ()
    assert set(report.source_used.values()) == {S3}
    for name, data in GOOD.items():
        assert (tmp_path / name).read_bytes() == data
    assert check_cache(tmp_path, CHECKSUMS) == CacheStatus(ok=True, missing=())


@pytest.mark.rule("R1")
def test_wrong_hash_from_every_source_raises_and_leaves_no_file(
    tmp_path: Path,
) -> None:
    bad = dict(GOOD, **{"100.dat": b"tampered"})
    fetch = FakeFetch({**_serve(S3, bad), **_serve(PHYSIONET, bad)})
    with pytest.raises(ChecksumMismatchError, match=r"100\.dat"):
        download(tmp_path, CHECKSUMS, SOURCES, fetch=fetch)
    assert not (tmp_path / "100.dat").exists()
    assert not any(p.name.startswith(".") for p in tmp_path.iterdir())


@pytest.mark.rule("R1")
def test_wrong_hash_from_the_first_source_falls_back_to_the_second(
    tmp_path: Path,
) -> None:
    bad = dict(GOOD, **{"100.dat": b"tampered"})
    fetch = FakeFetch({**_serve(S3, bad), **_serve(PHYSIONET, GOOD)})
    report = download(tmp_path, CHECKSUMS, SOURCES, fetch=fetch)
    assert report.source_used["100.dat"] == PHYSIONET
    assert report.source_used["100.atr"] == S3
    assert (tmp_path / "100.dat").read_bytes() == GOOD["100.dat"]


def test_network_error_on_the_first_source_falls_back(tmp_path: Path) -> None:
    responses: dict[str, bytes | Exception] = {
        **_serve(PHYSIONET, GOOD),
        **{S3 + name: urllib.error.URLError("unreachable") for name in GOOD},
    }
    fetch = FakeFetch(responses)
    report = download(tmp_path, CHECKSUMS, SOURCES, fetch=fetch)
    assert set(report.source_used.values()) == {PHYSIONET}
    assert check_cache(tmp_path, CHECKSUMS).ok


def test_both_sources_unreachable_raises_download_error(tmp_path: Path) -> None:
    error = TimeoutError("timed out")
    responses: dict[str, bytes | Exception] = {
        source + name: error for source in SOURCES for name in GOOD
    }
    with pytest.raises(DownloadError, match=r"100\.atr"):
        download(tmp_path, CHECKSUMS, SOURCES, fetch=FakeFetch(responses))
    assert _final_names(tmp_path) == set()


def test_matching_cached_files_are_skipped_without_fetching(tmp_path: Path) -> None:
    for name, data in GOOD.items():
        (tmp_path / name).write_bytes(data)
    fetch = FakeFetch({})
    report = download(tmp_path, CHECKSUMS, SOURCES, fetch=fetch)
    assert fetch.calls == []
    assert set(report.skipped) == set(GOOD)
    assert report.fetched == ()


@pytest.mark.rule("R1")
def test_cached_file_with_the_wrong_hash_stops_the_run(tmp_path: Path) -> None:
    (tmp_path / "100.atr").write_bytes(b"corrupted after download")
    fetch = FakeFetch(_serve(S3, GOOD))
    with pytest.raises(ChecksumMismatchError, match=r"100\.atr.*delete"):
        download(tmp_path, CHECKSUMS, SOURCES, fetch=fetch)
    # Never downloaded over the bad file.
    assert (tmp_path / "100.atr").read_bytes() == b"corrupted after download"


@pytest.mark.rule("R1")
def test_check_cache_raises_on_a_corrupted_file(tmp_path: Path) -> None:
    for name, data in GOOD.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "100.hea").write_bytes(b"flipped")
    with pytest.raises(ChecksumMismatchError, match=r"100\.hea"):
        check_cache(tmp_path, CHECKSUMS)


def test_check_cache_lists_missing_files(tmp_path: Path) -> None:
    (tmp_path / "100.hea").write_bytes(GOOD["100.hea"])
    status = check_cache(tmp_path, CHECKSUMS)
    assert status == CacheStatus(ok=False, missing=("100.atr", "100.dat"))


def test_missing_cache_folder_lists_every_file(tmp_path: Path) -> None:
    status = check_cache(tmp_path / "absent", CHECKSUMS)
    assert not status.ok
    assert status.missing == tuple(sorted(GOOD))


def _failing_write(monkeypatch: pytest.MonkeyPatch) -> None:
    original: Callable[[Path, bytes], int] = Path.write_bytes

    def write_half_then_fail(self: Path, data: bytes) -> int:
        original(self, data[: len(data) // 2])
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", write_half_then_fail)


def test_exception_while_writing_leaves_no_file_under_the_final_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _failing_write(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        download(tmp_path, CHECKSUMS, SOURCES, fetch=FakeFetch(_serve(S3, GOOD)))
    assert not set(GOOD) & _final_names(tmp_path)


def test_stale_temporary_files_are_removed_at_the_start(tmp_path: Path) -> None:
    stale = tmp_path / ".100.dat.part"
    stale.write_bytes(b"half a file from an interrupted run")
    download(tmp_path, CHECKSUMS, SOURCES, fetch=FakeFetch(_serve(S3, GOOD)))
    assert not stale.exists()
    assert _final_names(tmp_path) == set(GOOD)


def test_writes_go_to_a_temporary_name_then_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    seen: list[tuple[str, str]] = []
    original = os.replace

    def spy(src: str | Path, dst: str | Path) -> None:
        src_path, dst_path = Path(src), Path(dst)
        assert src_path.parent == dst_path.parent == tmp_path
        assert sha256_file(src_path) == CHECKSUMS[dst_path.name]
        seen.append((src_path.name, dst_path.name))
        original(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    download(tmp_path, CHECKSUMS, SOURCES, fetch=FakeFetch(_serve(S3, GOOD)))
    assert sorted(dst for _, dst in seen) == sorted(GOOD)
    assert all(src != dst for src, dst in seen)
