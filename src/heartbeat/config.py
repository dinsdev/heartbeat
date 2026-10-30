"""Run settings from `config/default.toml` as frozen dataclasses (CONVENTIONS 2)."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from heartbeat.paths import REPO_ROOT


class SettingsError(ValueError):
    """A settings file is malformed: unknown key, missing key or wrong type."""


@dataclass(frozen=True)
class DataSettings:
    """Where the raw and prepared data live, and where downloads come from.

    Attributes:
        raw_dir: Cache of the 132 pinned MIT-BIH files (DATA-01).
        prepared_dir: DS1 prepared records (DATA-08).
        sources: Base URLs tried in order, each ending in a slash (B5).
    """

    raw_dir: Path
    prepared_dir: Path
    sources: tuple[str, ...]


@dataclass(frozen=True)
class FoldSettings:
    """Fold generation settings (Phase 2 settling 5).

    Attributes:
        seed: `random_state` for `StratifiedGroupKFold`, read only by make-folds.
    """

    seed: int


@dataclass(frozen=True)
class Settings:
    """All run settings."""

    data: DataSettings
    folds: FoldSettings


def _table(
    raw: Mapping[str, Any], name: str, keys: set[str], path: Path
) -> Mapping[str, Any]:
    table = raw.get(name)
    if not isinstance(table, dict):
        raise SettingsError(f"{path}: missing table [{name}]")
    unknown = set(table) - keys
    if unknown:
        raise SettingsError(f"{path}: unknown key in [{name}]: {sorted(unknown)}")
    missing = keys - set(table)
    if missing:
        raise SettingsError(f"{path}: missing key in [{name}]: {sorted(missing)}")
    return table


def load_settings(path: Path, root: Path = REPO_ROOT) -> Settings:
    """Read and validate a settings file.

    Args:
        path: The TOML file, normally `config/default.toml`.
        root: Folder that relative data paths resolve against.

    Returns:
        The settings, with data folders as absolute paths.

    Raises:
        SettingsError: On an unknown or missing key, or a value of the wrong type.
    """
    with path.open("rb") as f:
        raw = tomllib.load(f)
    unknown = set(raw) - {"data", "folds"}
    if unknown:
        raise SettingsError(f"{path}: unknown table: {sorted(unknown)}")

    data = _table(raw, "data", {"raw_dir", "prepared_dir", "sources"}, path)
    for key in ("raw_dir", "prepared_dir"):
        if not isinstance(data[key], str):
            raise SettingsError(f"{path}: [data] {key} must be a string")
    sources = data["sources"]
    if (
        not isinstance(sources, list)
        or not sources
        or not all(isinstance(s, str) and s.endswith("/") for s in sources)
    ):
        raise SettingsError(
            f"{path}: [data] sources must be a non-empty list of URLs ending in /"
        )

    folds = _table(raw, "folds", {"seed"}, path)
    seed = folds["seed"]
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise SettingsError(f"{path}: [folds] seed must be an integer")

    return Settings(
        data=DataSettings(
            raw_dir=root / data["raw_dir"],
            prepared_dir=root / data["prepared_dir"],
            sources=tuple(sources),
        ),
        folds=FoldSettings(seed=seed),
    )
