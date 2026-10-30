"""The paired patient bootstrap (C4; EVAL-09, R17, R18).

A draw resamples whole patients with replacement. Each draw's confusion matrix
is the sum of its patients' matrices weighted by how often each was drawn, so
10,000 draws are one matrix product. Every model scored on one patient set
uses the same counts matrix, which is what makes differences paired.

A metric undefined in a draw (zero denominator) is skipped for that metric
only, and the skips are counted (Phase 3 settling 2). Intervals are the 2.5th
and 97.5th percentiles of the defined draws (settling 5).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, INTERVAL_PERCENTILES
from heartbeat.evaluate.metrics import (
    N_CLASSES,
    confusion_matrix,
    json_float,
    metric_values,
)


@dataclass(frozen=True)
class Interval:
    """A point estimate with its bootstrap interval.

    Attributes:
        point: The metric on every patient once; NaN when undefined.
        low: 2.5th percentile of the defined draws, or None if none is defined.
        high: 97.5th percentile of the defined draws, or None.
        skipped: Draws where the metric was undefined.
        draws: Draws in all.
    """

    point: float
    low: float | None
    high: float | None
    skipped: int
    draws: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict, NaN written as None."""
        return {
            "point": json_float(self.point),
            "low": self.low,
            "high": self.high,
            "skipped": self.skipped,
            "draws": self.draws,
        }


@dataclass(frozen=True)
class BootstrapResult:
    """Every model's metrics on one shared set of draws.

    Attributes:
        counts: How often each patient is in each draw, `(n_draws, n_patients)`.
        values: Model to metric to its value per draw, `(n_draws,)`.
        intervals: Model to metric to its interval.
    """

    counts: NDArray[np.int64]
    values: Mapping[str, Mapping[str, NDArray[np.float64]]]
    intervals: Mapping[str, Mapping[str, Interval]]


def patient_confusions(
    y_true: NDArray[np.str_],
    y_pred: NDArray[np.str_],
    subject_id: NDArray[np.str_],
    patients: Sequence[str],
) -> NDArray[np.int64]:
    """One confusion matrix per patient, `(n_patients, 4, 4)`, in `patients` order.

    Raises:
        ValueError: If a beat's subject is not in `patients`.
    """
    unknown = sorted(set(subject_id.tolist()) - set(patients))
    if unknown:
        raise ValueError(f"subjects {unknown} are not in the patient list")
    stacked = np.zeros((len(patients), N_CLASSES, N_CLASSES), dtype=np.int64)
    for k, patient in enumerate(patients):
        mine = subject_id == patient
        stacked[k] = confusion_matrix(y_true[mine], y_pred[mine])
    return stacked


def draw_counts(
    n_patients: int, n_draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED
) -> NDArray[np.int64]:
    """Draw `n_patients` patients with replacement, `n_draws` times.

    Returns:
        How often each patient is drawn per draw, `(n_draws, n_patients)`; each
        row sums to `n_patients`. Depends only on the seed and the two sizes.
    """
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    picks = rng.integers(0, n_patients, size=(n_draws, n_patients))
    counts = np.zeros((n_draws, n_patients), dtype=np.int64)
    np.add.at(counts, (np.arange(n_draws)[:, np.newaxis], picks), 1)
    return counts


def draw_confusions(
    confusions: NDArray[np.int64], counts: NDArray[np.int64]
) -> NDArray[np.int64]:
    """Each draw's confusion matrix, `(n_draws, 4, 4)`.

    Args:
        confusions: Per patient, `(n_patients, 4, 4)`.
        counts: Per draw and patient, `(n_draws, n_patients)`.
    """
    n_patients = confusions.shape[0]
    assert counts.shape[1] == n_patients, (counts.shape, confusions.shape)
    flat = counts @ confusions.reshape(n_patients, N_CLASSES * N_CLASSES)
    return flat.reshape(-1, N_CLASSES, N_CLASSES).astype(np.int64)


def percentile_interval(values: NDArray[np.float64]) -> tuple[float, float] | None:
    """The 95% percentile interval of the defined values, or None if there are none."""
    defined = values[~np.isnan(values)]
    if defined.size == 0:
        return None
    low, high = np.percentile(defined, INTERVAL_PERCENTILES)
    return float(low), float(high)


def _interval(point: float, values: NDArray[np.float64]) -> Interval:
    bounds = percentile_interval(values)
    return Interval(
        point=point,
        low=None if bounds is None else bounds[0],
        high=None if bounds is None else bounds[1],
        skipped=int(np.isnan(values).sum()),
        draws=int(values.size),
    )


def bootstrap(
    confusions_by_model: Mapping[str, NDArray[np.int64]],
    counts: NDArray[np.int64] | None = None,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> BootstrapResult:
    """Score every model on one shared set of patient draws.

    Args:
        confusions_by_model: Model name to per-patient matrices,
            `(n_patients, 4, 4)`, all in one patient order.
        counts: The draws; made once with `draw_counts` when not given.
        n_draws: Number of draws when `counts` is not given.
        seed: Seed when `counts` is not given.

    Returns:
        Values per draw and intervals for every metric of `metric_values`.

    Raises:
        ValueError: If the models were scored on different numbers of patients.
    """
    sizes = {name: c.shape[0] for name, c in confusions_by_model.items()}
    if len(set(sizes.values())) != 1:
        raise ValueError(f"models scored on different numbers of patients: {sizes}")
    if counts is None:
        counts = draw_counts(next(iter(sizes.values())), n_draws, seed)
    values: dict[str, dict[str, NDArray[np.float64]]] = {}
    intervals: dict[str, dict[str, Interval]] = {}
    for name, confusions in confusions_by_model.items():
        points = metric_values(confusions.sum(axis=0))
        values[name] = metric_values(draw_confusions(confusions, counts))
        intervals[name] = {
            metric: _interval(float(points[metric]), drawn)
            for metric, drawn in values[name].items()
        }
    return BootstrapResult(counts=counts, values=values, intervals=intervals)


def paired_difference(result: BootstrapResult, a: str, b: str, metric: str) -> Interval:
    """Model `a` minus model `b` on the shared draws (EVAL-10).

    A draw where either side is undefined is skipped and counted.
    """
    diff = result.values[a][metric] - result.values[b][metric]
    point = result.intervals[a][metric].point - result.intervals[b][metric].point
    return _interval(point, diff)
