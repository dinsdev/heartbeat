"""Run folders and their provenance (C6; MODEL-07).

Every run writes `runs/<UTC time>-<short commit>-<name>/` with the resolved
config, the provenance (commit, dirty flag, diff hash, versions, input hashes,
device and threads) and a log. Nothing in a run folder is committed; the
committed summaries in `results/` name the run they came from.
"""

import dataclasses
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import numpy as np
from numpy.typing import NDArray

from heartbeat.config import Settings
from heartbeat.paths import REPO_ROOT, RUNS_DIR

# The packages whose versions decide the numbers of a Phase 3 run.
PROVENANCE_PACKAGES = ("numpy", "scipy", "scikit-learn", "wfdb")

_PACKAGE_LOGGER = "heartbeat"


def canonical_json(payload: Any) -> str:
    """Sorted keys, two-space indent, trailing newline; NaN is an error.

    Raises:
        ValueError: On NaN or infinity ("Out of range float values are not
            JSON compliant"); write undefined values as None first.
    """
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Write to a temporary file in the same folder, then rename (CONVENTIONS 2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".part",
        delete=False,
        encoding="utf-8",
    ) as f:
        temp = Path(f.name)
        f.write(text)
    temp.replace(path)


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True
    ).stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple | list):
        return [_jsonable(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def provenance(repo: Path, now: datetime) -> dict[str, Any]:
    """What a run's numbers depend on besides its config.

    The tree is dirty when `git status` shows any change, untracked files
    included (ignored files are not).
    """
    status = _git(repo, "status", "--porcelain")
    return {
        "commit": _git(repo, "rev-parse", "HEAD").decode().strip(),
        "dirty": bool(status.strip()),
        "diff_sha256": hashlib.sha256(_git(repo, "diff", "HEAD")).hexdigest(),
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name) for name in PROVENANCE_PACKAGES
        },
        "uv_lock_sha256": _sha256(repo / "uv.lock"),
        "folds_sha256": _sha256(repo / "config" / "folds.json"),
        "device": "cpu",
        "cpu_count": os.cpu_count(),
        "threads": {
            k: v for k, v in sorted(os.environ.items()) if k.endswith("_NUM_THREADS")
        },
        "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@dataclass
class RunFolder:
    """An open run folder; close it (or use `with`) to detach its log.

    Attributes:
        path: The folder.
        provenance: The content of `provenance.json`.
        created: When the run started, UTC.
    """

    path: Path
    provenance: Mapping[str, Any]
    created: datetime
    _handler: logging.Handler | None = field(default=None, repr=False)
    _previous_level: int = field(default=logging.NOTSET, repr=False)

    @property
    def name(self) -> str:
        """The folder name, which `results/` files record as `run`."""
        return self.path.name

    def write_json(self, name: str, payload: Any) -> Path:
        """Write `<name>.json` as canonical JSON, atomically."""
        path = self.path / f"{name}.json"
        write_text_atomic(path, canonical_json(payload))
        return path

    def write_arrays(self, name: str, **arrays: NDArray[Any]) -> Path:
        """Write `<name>.npz`; object arrays are refused (no pickle)."""
        path = self.path / f"{name}.npz"
        with tempfile.NamedTemporaryFile(
            dir=self.path, prefix=f".{path.name}.", suffix=".part", delete=False
        ) as f:
            temp = Path(f.name)
            np.savez(f, allow_pickle=False, **arrays)
        temp.replace(path)
        return path

    def close(self) -> None:
        """Detach the log file handler."""
        if self._handler is not None:
            logger = logging.getLogger(_PACKAGE_LOGGER)
            logger.removeHandler(self._handler)
            logger.setLevel(self._previous_level)
            self._handler.close()
            self._handler = None

    def __enter__(self) -> Self:
        """Return the run."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the run."""
        self.close()


def create_run(
    name: str,
    settings: Settings,
    extra_config: Mapping[str, Any],
    root: Path = RUNS_DIR,
    repo: Path = REPO_ROOT,
    now: datetime | None = None,
    torch_info: Mapping[str, Any] | None = None,
) -> RunFolder:
    """Make a run folder with `config.json`, `provenance.json` and `log.txt`.

    Args:
        name: Short run name, the last part of the folder name.
        settings: The resolved settings.
        extra_config: Run-specific config (model, grid, and so on).
        root: Parent of run folders.
        repo: The git checkout whose state the provenance records.
        now: Start time; the current UTC time by default.
        torch_info: For a training run, the torch version, device, thread count
            and deterministic flag (Phase 4 design call 7); they replace the
            CPU default in the provenance.

    Raises:
        FileExistsError: If the folder already exists.
    """
    created = (now or datetime.now(UTC)).replace(microsecond=0)
    prov = provenance(repo, created)
    if torch_info is not None:
        prov.update(torch_info)
    short = _git(repo, "rev-parse", "--short", "HEAD").decode().strip()
    path = root / f"{created.strftime('%Y%m%dT%H%M%SZ')}-{short}-{name}"
    path.mkdir(parents=True, exist_ok=False)
    config = {
        "settings": _jsonable(dataclasses.asdict(settings)),
        "extra": _jsonable(extra_config),
    }
    write_text_atomic(path / "config.json", canonical_json(config))
    write_text_atomic(path / "provenance.json", canonical_json(prov))
    handler = logging.FileHandler(path / "log.txt", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
    )
    logger = logging.getLogger(_PACKAGE_LOGGER)
    previous = logger.level
    logger.addHandler(handler)
    if previous == logging.NOTSET or previous > logging.INFO:
        logger.setLevel(logging.INFO)
    return RunFolder(
        path=path,
        provenance=prov,
        created=created,
        _handler=handler,
        _previous_level=previous,
    )
