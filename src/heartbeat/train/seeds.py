"""Seeds derived from one master seed per run (MODEL-05; CONVENTIONS section 3).

`SeedSequence(master)` is spawned once per fold, and each fold's child once
per stream (Phase 4 task plan, design call 5). Folds 0 to 4 are the CV folds
(the exhibit's leaky side uses the same numbering, so both sides run on the
same seeds, C5); `FINAL_FOLD` is the final model trained on all of DS1.
"""

from dataclasses import dataclass

import numpy as np

from heartbeat.constants import N_FOLDS

STREAMS = ("weight_init", "shuffle", "shift", "noise", "dropout")
# The child for train-final, after the five CV folds.
FINAL_FOLD = N_FOLDS


@dataclass(frozen=True)
class RunSeeds:
    """One stream per source of randomness in a fit."""

    weight_init: np.random.SeedSequence
    shuffle: np.random.SeedSequence
    shift: np.random.SeedSequence
    noise: np.random.SeedSequence
    dropout: np.random.SeedSequence


def derive_seeds(master: int, fold: int) -> RunSeeds:
    """The streams of one fit: fold 0 to 4 in CV, `FINAL_FOLD` for train-final.

    Raises:
        ValueError: On a fold outside 0 to `FINAL_FOLD`.
    """
    if not 0 <= fold <= FINAL_FOLD:
        raise ValueError(f"fold {fold} is outside 0 to {FINAL_FOLD}")
    fold_seq = np.random.SeedSequence(master).spawn(fold + 1)[fold]
    return RunSeeds(*fold_seq.spawn(len(STREAMS)))


def torch_seed(seq: np.random.SeedSequence) -> int:
    """A non-negative 63-bit integer for `torch.manual_seed` or a torch generator."""
    return int(seq.generate_state(1, dtype=np.uint64)[0] >> np.uint64(1))
