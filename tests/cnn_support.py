"""Synthetic traces for the CNN tests: windows cut from them, no record read."""

from collections.abc import Iterator, Mapping
from typing import Any

import numpy as np
from cv_support import synthetic_beats
from numpy.typing import NDArray

from heartbeat.constants import WINDOW_AFTER_SAMPLES
from heartbeat.data.loader import BeatTable
from heartbeat.models.spec import ModelSpec, epochs_only
from heartbeat.signal.windows import extract_windows

MARGIN_SAMPLES = 200
CLASS_BUMP = {"N": 0, "S": 40, "V": -60, "F": 20}


def beats_with_traces(
    n_subjects: int = 10, per_subject: int = 160, seed: int = 0
) -> tuple[BeatTable, dict[str, NDArray[np.int16]]]:
    """`synthetic_beats` with one int16 trace per record and its real windows.

    Each beat's class leaves a small bump in its window, so a CNN has
    something to learn; the noise keeps it from being separable.
    """
    base = synthetic_beats(n_subjects, per_subject, seed)
    # Move every beat clear of the trace start, shift included.
    beats = BeatTable(
        base.record_id,
        base.subject_id,
        base.sample + MARGIN_SAMPLES,
        base.beat_class,
        base.window_adu,
        base.rr_s,
    )
    rng = np.random.default_rng(seed + 1)
    length = int(beats.sample.max()) + WINDOW_AFTER_SAMPLES + 50
    traces: dict[str, NDArray[np.int16]] = {}
    for record in sorted(set(beats.record_id.tolist())):
        trace = rng.normal(0.0, 30.0, length)
        rows = np.flatnonzero(beats.record_id == record)
        for row in rows.tolist():
            s = int(beats.sample[row])
            trace[s - 5 : s + 5] += 200 + CLASS_BUMP[str(beats.beat_class[row])]
        traces[record] = np.round(trace).astype(np.int16)
    windows = np.concatenate(
        [
            extract_windows(traces[r], beats.sample[beats.record_id == r])
            for r in dict.fromkeys(beats.record_id.tolist())
        ]
    )
    return (
        BeatTable(
            beats.record_id,
            beats.subject_id,
            beats.sample,
            beats.beat_class,
            windows,
            beats.rr_s,
        ),
        traces,
    )


def epoch_spec(calls: list[dict[str, Any]] | None = None) -> ModelSpec:
    """A fast model that trains in epochs, for driver and selection tests.

    Logits are the RR inputs times the epoch, plus the fold; a nonzero
    `params["seed"]` adds a seed-dependent term so seeds differ.
    """

    def inputs(
        b: BeatTable, rows: NDArray[np.int64], rr: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        return rr

    def fit_epochs(
        x: NDArray[np.float64],
        y: NDArray[np.str_],
        w: Mapping[str, float],
        params: Mapping[str, Any],
        fold: int,
        n_epochs: int,
    ) -> Iterator[Any]:
        if calls is not None:
            calls.append({"n": y.size, "weights": dict(w), "fold": fold})
        for epoch in range(1, n_epochs + 1):
            yield {"epoch": epoch, "fold": fold, "seed": params.get("seed", 0)}

    def logits(model: Any, x: NDArray[np.float64]) -> NDArray[np.float64]:
        out: NDArray[np.float64] = (
            x[:, :4] * model["epoch"] + model["fold"] + model["seed"] * x[:, 2:6]
        )
        return out

    return ModelSpec(
        name="epochs",
        inputs=inputs,
        fit=epochs_only,
        logits=logits,
        fit_epochs=fit_epochs,
    )
