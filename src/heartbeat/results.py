"""The `results/` writer (rule 5; Phase 3 task plan, design calls 6 and 7).

`results/` holds committed summaries. Only the rebuild stages call
`write_result` (a test checks the import graph), and each file records the
run folder, commit and dirty flag it came from, so a committed result can be
checked against history.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from heartbeat.paths import RESULTS_DIR
from heartbeat.runs import RunFolder, canonical_json, write_text_atomic

PROVENANCE_KEYS = ("run", "commit", "dirty")


def write_result(
    name: str,
    payload: Mapping[str, Any],
    run: RunFolder,
    results_dir: Path = RESULTS_DIR,
) -> Path:
    """Write `results/<name>.json` as canonical JSON, atomically.

    Args:
        name: File name without `.json`.
        payload: The summary; NaN must already be None.
        run: The run it came from; its folder name, commit and dirty flag are
            copied in.
        results_dir: The results folder.

    Raises:
        ValueError: On NaN or infinity, or if the payload sets a provenance key.
    """
    clash = sorted(set(payload) & set(PROVENANCE_KEYS))
    if clash:
        raise ValueError(f"payload sets {clash}; the writer copies those from the run")
    content = {
        **payload,
        "run": run.name,
        "commit": run.provenance["commit"],
        "dirty": run.provenance["dirty"],
    }
    path = results_dir / f"{name}.json"
    # canonical_json raises before anything is written.
    write_text_atomic(path, canonical_json(content))
    return path
