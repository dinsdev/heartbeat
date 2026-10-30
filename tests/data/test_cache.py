"""DATA-02 on the real cache: all 132 pinned files present and matching (R2)."""

from pathlib import Path

import pytest

from heartbeat.data.download import CacheStatus, check_cache
from heartbeat.data.manifests import load_checksums
from heartbeat.paths import CHECKSUM_MANIFEST


@pytest.mark.rule("R2")
def test_cache_matches_the_132_pinned_checksums(raw_dir: Path) -> None:
    checksums = load_checksums(CHECKSUM_MANIFEST)
    assert len(checksums) == 132
    assert check_cache(raw_dir, checksums) == CacheStatus(ok=True, missing=())
