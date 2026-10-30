"""Subject-grouped folds on DS1, made once and checked ever after (C1; EVAL-02, 03).

Phase 2 settling 5: `make_folds` runs once, by Din. `check_folds` verifies the
committed file against its pinned SHA256 and the manifests, and never calls
the splitter, so `rebuild` cannot regenerate folds (R14).
"""

import hashlib
import json
import re
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import sklearn
from sklearn.model_selection import StratifiedGroupKFold

from heartbeat.constants import N_FOLDS, SCORED_CLASSES
from heartbeat.data.loader import BeatTable
from heartbeat.data.manifests import Splits
from heartbeat.paths import SPLITS_MANIFEST, SUBJECTS_MANIFEST

DEFAULT_MANIFESTS = (SPLITS_MANIFEST, SUBJECTS_MANIFEST)
_KEYS = {"seed", "sklearn_version", "manifest_sha256", "subject_fold", "class_counts"}
_PIN_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)\n?$")


class FoldCheckError(ValueError):
    """The fold file is missing, malformed, unpinned or leaks a subject."""


@dataclass(frozen=True)
class Folds:
    """The content of `config/folds.json`.

    Attributes:
        seed: The `random_state` the folds were made with.
        sklearn_version: scikit-learn's version at the time.
        manifest_sha256: Manifest file name to its SHA256 when the folds were made.
        subject_fold: DS1 subject to its fold, 0 to 4.
        class_counts: Fold (as a string) to scored class to beat count.
    """

    seed: int
    sklearn_version: str
    manifest_sha256: Mapping[str, str]
    subject_fold: Mapping[str, int]
    class_counts: Mapping[str, Mapping[str, int]]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {path.name: _sha256(path) for path in paths}


def make_folds(
    beats: BeatTable, seed: int, manifest_paths: Sequence[Path] = DEFAULT_MANIFESTS
) -> Folds:
    """Assign each DS1 subject to one of five folds, stratified by class.

    Args:
        beats: DS1 beats; only the scored classes are used.
        seed: The fold seed from settings.
        manifest_paths: The manifests whose hashes the fold file records.

    Returns:
        The folds.
    """
    scored = np.isin(beats.beat_class, SCORED_CLASSES)
    y = beats.beat_class[scored]
    groups = beats.subject_id[scored]
    splitter = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    subject_fold: dict[str, int] = {}
    class_counts: dict[str, dict[str, int]] = {}
    for fold, (_, test_index) in enumerate(
        splitter.split(np.zeros((y.size, 1)), y, groups)
    ):
        for subject in np.unique(groups[test_index]).tolist():
            subject_fold[str(subject)] = fold
        counts = Counter(y[test_index].tolist())
        class_counts[str(fold)] = {cls: int(counts[cls]) for cls in SCORED_CLASSES}
    return Folds(
        seed=seed,
        sklearn_version=sklearn.__version__,
        manifest_sha256=_manifest_hashes(manifest_paths),
        subject_fold=dict(sorted(subject_fold.items())),
        class_counts=class_counts,
    )


def _to_json(folds: Folds) -> str:
    payload = {
        "seed": folds.seed,
        "sklearn_version": folds.sklearn_version,
        "manifest_sha256": dict(folds.manifest_sha256),
        "subject_fold": dict(folds.subject_fold),
        "class_counts": {k: dict(v) for k, v in folds.class_counts.items()},
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_folds(folds: Folds, path: Path) -> None:
    """Write canonical JSON atomically; never overwrite an existing file.

    Raises:
        FileExistsError: If `path` exists (C1: folds are made once).
    """
    if path.exists():
        raise FileExistsError(f"{path} exists; folds are made once (C1)")
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
        f.write(_to_json(folds))
    try:
        # A hard link fails if the target exists, so this cannot overwrite.
        path.hardlink_to(temp)
    finally:
        temp.unlink()


class _DuplicateKeyError(ValueError):
    pass


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKeyError(key)
        seen[key] = value
    return seen


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read_folds(path: Path) -> Folds:
    """Read and schema-check a fold file.

    Raises:
        FoldCheckError: On a missing file, a repeated key or a schema error.
    """
    if not path.is_file():
        raise FoldCheckError(
            f"{path} missing; Din makes it once with `uv run heartbeat make-folds`"
        )
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates
        )
    except _DuplicateKeyError as error:
        raise FoldCheckError(
            f"{path}: key {error} appears twice (one subject in two folds is a leak)"
        ) from error
    except json.JSONDecodeError as error:
        raise FoldCheckError(f"{path}: not JSON: {error}") from error
    if not isinstance(raw, dict) or set(raw) != _KEYS:
        keys = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        raise FoldCheckError(f"{path}: keys {keys}, expected {sorted(_KEYS)}")
    if not _is_int(raw["seed"]):
        raise FoldCheckError(f"{path}: seed must be an integer")
    if not isinstance(raw["sklearn_version"], str):
        raise FoldCheckError(f"{path}: sklearn_version must be a string")
    hashes = raw["manifest_sha256"]
    if not isinstance(hashes, dict) or not all(
        isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in hashes.values()
    ):
        raise FoldCheckError(f"{path}: manifest_sha256 must map names to SHA256 hex")
    subject_fold = raw["subject_fold"]
    if not isinstance(subject_fold, dict):
        raise FoldCheckError(f"{path}: subject_fold must be an object")
    for subject, fold in subject_fold.items():
        if not _is_int(fold) or not 0 <= fold < N_FOLDS:
            raise FoldCheckError(
                f"{path}: subject {subject} in fold {fold}, expected 0 to {N_FOLDS - 1}"
            )
    counts = raw["class_counts"]
    folds = [str(k) for k in range(N_FOLDS)]
    if (
        not isinstance(counts, dict)
        or sorted(counts) != folds
        or not all(
            isinstance(c, dict)
            and set(c) == set(SCORED_CLASSES)
            and all(_is_int(n) and n >= 0 for n in c.values())
            for c in counts.values()
        )
    ):
        raise FoldCheckError(
            f"{path}: class_counts must give N, S, V and F counts for folds 0 to 4"
        )
    return Folds(
        seed=raw["seed"],
        sklearn_version=raw["sklearn_version"],
        manifest_sha256=hashes,
        subject_fold=subject_fold,
        class_counts=counts,
    )


def _check_pin(folds_path: Path, pin_path: Path) -> None:
    if not pin_path.is_file():
        raise FoldCheckError(f"{pin_path} missing: the fold file has no pin")
    match = _PIN_LINE.match(pin_path.read_text(encoding="utf-8"))
    if match is None:
        raise FoldCheckError(f"{pin_path}: malformed pin, expected `<sha256>  <path>`")
    if not folds_path.is_file():
        raise FoldCheckError(
            f"{folds_path} missing; Din makes it once with "
            "`uv run heartbeat make-folds`"
        )
    actual = _sha256(folds_path)
    if actual != match.group(1):
        raise FoldCheckError(
            f"{folds_path}: SHA256 {actual} differs from the pin in {pin_path}; "
            "folds are never regenerated (C1)"
        )


def check_folds(
    folds_path: Path,
    pin_path: Path,
    splits: Splits,
    subjects: Mapping[str, str],
    manifest_paths: Sequence[Path] = DEFAULT_MANIFESTS,
) -> Folds:
    """Verify the committed folds without regenerating them (R13, R14).

    Checks, in order: the pinned SHA256, the schema, the manifest hashes the
    file records, and that the subjects are exactly DS1's, each in one fold.

    Returns:
        The folds.

    Raises:
        FoldCheckError: Naming the first failed check.
    """
    _check_pin(folds_path, pin_path)
    folds = read_folds(folds_path)

    current = _manifest_hashes(manifest_paths)
    if dict(folds.manifest_sha256) != current:
        changed = sorted(
            name
            for name in set(current) | set(folds.manifest_sha256)
            if current.get(name) != folds.manifest_sha256.get(name)
        )
        raise FoldCheckError(
            f"{folds_path}: made from other manifests than today's "
            f"({', '.join(changed)})"
        )

    ds1 = {subjects[r] for r in splits.ds1}
    ds2 = {subjects[r] for r in splits.ds2}
    excluded = {subjects[r] for r in splits.excluded if r in subjects} - ds1
    for subject in sorted(folds.subject_fold):
        if subject in ds1:
            continue
        if subject in ds2:
            reason = "a DS2 subject (rule 1)"
        elif subject in excluded:
            reason = "an excluded record's subject"
        else:
            reason = "not a DS1 subject in the manifest"
        raise FoldCheckError(f"{folds_path}: subject {subject} is {reason}")
    missing = sorted(ds1 - set(folds.subject_fold))
    if missing:
        raise FoldCheckError(f"{folds_path}: DS1 subjects {missing} missing")
    empty = sorted(set(range(N_FOLDS)) - set(folds.subject_fold.values()))
    if empty:
        raise FoldCheckError(f"{folds_path}: folds with no subject: {empty}")
    return folds
