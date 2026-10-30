"""Real-data fixtures (layer L2). Every test here needs the cached download.

A missing cache fails with the command that fills it; real-data tests never
skip (Phase 2 plan, approach).
"""

from pathlib import Path

import pytest

from heartbeat.config import Settings, load_settings
from heartbeat.data.manifests import Splits, load_checksums, load_splits
from heartbeat.paths import CHECKSUM_MANIFEST, DEFAULT_CONFIG, SPLITS_MANIFEST

HERE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if HERE in Path(item.path).parents:
            item.add_marker(pytest.mark.realdata)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return load_settings(DEFAULT_CONFIG)


@pytest.fixture(scope="session")
def splits() -> Splits:
    return load_splits(SPLITS_MANIFEST)


@pytest.fixture(scope="session")
def raw_dir(settings: Settings) -> Path:
    raw = settings.data.raw_dir
    missing = [
        name for name in load_checksums(CHECKSUM_MANIFEST) if not (raw / name).is_file()
    ]
    if missing:
        pytest.fail(
            f"{len(missing)} cached MIT-BIH files missing (first: {missing[0]}); "
            "run `uv run heartbeat download`",
            pytrace=False,
        )
    return raw
