"""`heartbeat verify`: the quick integrity check (E4; OPS-04).

Checks, without training: the manifests and, when the cache exists, its
checksums (R2); the fold file against its pin (R14); the model files against
`results/export.json` and the size gate (R25); `NOTICE` (R52); ONNX parity on
the committed fixtures (R26); the card blocks against what `heartbeat cards`
renders (R50); and the sealed-run log and its history (R42). Each check
returns its problems; an empty list is a pass.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from heartbeat.cards.blocks import TEST_PENDING, CardSources, card_specs, render_blocks
from heartbeat.cards.render import CardError, pending_after_sealed, stale_blocks
from heartbeat.constants import MODEL_SIZE_LIMIT_BYTES
from heartbeat.data.download import ChecksumMismatchError, check_cache
from heartbeat.data.folds import FoldCheckError, check_folds
from heartbeat.data.manifests import (
    ManifestError,
    load_beat_counts,
    load_checksums,
    load_splits,
    load_subjects,
)
from heartbeat.export.bundle import NOTICE_NAME, NOTICE_TEXT, bundle_files, file_facts
from heartbeat.export.fixtures import FIXTURES_NAME, fixture_parity
from heartbeat.export.onnx import ParityError
from heartbeat.paths import (
    BEAT_COUNTS_MANIFEST,
    CHECKSUM_MANIFEST,
    FOLDS_JSON,
    FOLDS_PIN,
    SPLITS_MANIFEST,
    SUBJECTS_MANIFEST,
)
from heartbeat.sealed.log import LogError, check_log, check_log_history

Renderers = Mapping[str, Callable[[CardSources], str]]


@dataclass(frozen=True)
class VerifyPaths:
    """What `verify` checks.

    Attributes:
        repo: The checkout; bundle and report paths are relative to it.
        results_dir: `results/`.
        models_dir: `models/heartbeat-v1/`.
        fixtures_dir: `fixtures/parity/`.
        model_card: `docs/MODEL_CARD.md`.
        data_card: `docs/DATA_CARD.md`.
        log_path: `results/test_runs.jsonl`.
        raw_dir: The download cache.
    """

    repo: Path
    results_dir: Path
    models_dir: Path
    fixtures_dir: Path
    model_card: Path
    data_card: Path
    log_path: Path
    raw_dir: Path

    def sources(self) -> CardSources:
        """The card sources these paths give."""
        return CardSources(self.results_dir, self.models_dir, self.log_path, self.repo)


def check_inputs(paths: VerifyPaths) -> list[str]:
    """Manifests parse, the folds match their pin, the cache its checksums."""
    try:
        splits = load_splits(SPLITS_MANIFEST)
        subjects = load_subjects(SUBJECTS_MANIFEST)
        checksums = load_checksums(CHECKSUM_MANIFEST)
        load_beat_counts(BEAT_COUNTS_MANIFEST)
        check_folds(FOLDS_JSON, FOLDS_PIN, splits, subjects)
    except (ManifestError, FoldCheckError) as error:
        return [str(error)]
    if not paths.raw_dir.is_dir():
        return []
    try:
        status = check_cache(paths.raw_dir, checksums)
    except ChecksumMismatchError as error:
        return [str(error)]
    if status.missing:
        return [
            f"{len(status.missing)} cached files missing (first {status.missing[0]})"
        ]
    return []


def check_models(paths: VerifyPaths) -> list[str]:
    """Bundle and fixtures equal `results/export.json`; each model under 1 MB."""
    record = json.loads((paths.results_dir / "export.json").read_text("utf-8"))
    problems = []
    files = bundle_files(paths.models_dir, paths.repo)
    if files != record["files"]:
        recorded = {f["path"]: f for f in record["files"]}
        found = {f["path"]: f for f in files}
        for name in sorted(set(recorded) | set(found)):
            if recorded.get(name) != found.get(name):
                problems.append(f"{name} differs from results/export.json")
    for facts in files:
        if facts["path"].endswith(".onnx") and facts["bytes"] >= MODEL_SIZE_LIMIT_BYTES:
            problems.append(f"{facts['path']} is {facts['bytes']} bytes (R25)")
    fixtures = paths.fixtures_dir / FIXTURES_NAME
    expected = {k: record["fixtures"][k] for k in ("path", "bytes", "sha256")}
    if not fixtures.is_file() or file_facts(fixtures, paths.repo) != expected:
        problems.append(f"{expected['path']} differs from results/export.json")
    return problems


def check_notice(paths: VerifyPaths) -> list[str]:
    """`NOTICE` exists with the MIT line and the ODC-By 1.0 notice (R52)."""
    path = paths.models_dir / NOTICE_NAME
    if not path.is_file():
        return [f"{path} is missing (R52)"]
    if path.read_text(encoding="utf-8") != NOTICE_TEXT:
        return [f"{path} differs from the notice export writes (R52)"]
    return []


def check_parity(paths: VerifyPaths) -> list[str]:
    """The committed models reproduce the fixtures' logits (R26)."""
    payload = json.loads((paths.fixtures_dir / FIXTURES_NAME).read_text("utf-8"))
    try:
        fixture_parity(paths.models_dir, payload)
    except ParityError as error:
        return [str(error)]
    return []


def check_cards(
    paths: VerifyPaths,
    specs: Sequence[tuple[Path, Renderers]] | None = None,
) -> list[str]:
    """Every block equals what `heartbeat cards` renders; none pending late (R50)."""
    sources = paths.sources()
    sealed = sources.sealed_report() is not None
    problems = []
    for card, renderers in specs or card_specs(paths.model_card, paths.data_card):
        text = card.read_text(encoding="utf-8")
        try:
            stale = stale_blocks(text, render_blocks(renderers, sources))
        except (CardError, FileNotFoundError, KeyError) as error:
            problems.append(f"{card.name}: {error}")
            continue
        problems += [f"{card.name}: block {name} is stale" for name in stale]
        if sealed:
            problems += [
                f"{card.name}: block {name} is pending after the sealed run"
                for name in pending_after_sealed(text, TEST_PENDING)
            ]
    return problems


def check_test_log(paths: VerifyPaths) -> list[str]:
    """Ids, reports and history of the sealed-run log (R42)."""
    try:
        check_log(paths.log_path, paths.repo)
        check_log_history(paths.log_path, paths.repo)
    except LogError as error:
        return [str(error)]
    return []


CHECKS: Sequence[tuple[str, Callable[[VerifyPaths], list[str]]]] = (
    ("manifests, folds and cache (R2, R14)", check_inputs),
    ("model files against results/export.json (R25)", check_models),
    ("NOTICE (R52)", check_notice),
    ("ONNX parity on the fixtures (R26)", check_parity),
    ("card blocks (R50)", check_cards),
    ("sealed-run log (R42)", check_test_log),
)


def verify(paths: VerifyPaths) -> list[tuple[str, list[str]]]:
    """Run every check; a check that raises reports the error as its problem."""
    results = []
    for name, check in CHECKS:
        try:
            problems = check(paths)
        except (OSError, ValueError, KeyError) as error:
            problems = [f"{type(error).__name__}: {error}"]
        results.append((name, problems))
    return results
