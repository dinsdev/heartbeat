"""MODEL-05, CONVENTIONS section 3: every stream derives from one master seed."""

import dataclasses

import numpy as np
import pytest

from heartbeat.constants import CNN_SEEDS, N_FOLDS, SHIPPED_SEED
from heartbeat.train.seeds import FINAL_FOLD, STREAMS, derive_seeds, torch_seed


def _states(seeds: object) -> dict[str, list[int]]:
    return {
        f.name: getattr(seeds, f.name).generate_state(4).tolist()
        for f in dataclasses.fields(seeds)  # type: ignore[arg-type]
    }


def test_the_c6_seeds() -> None:
    assert CNN_SEEDS == (0, 1, 2)
    assert SHIPPED_SEED == 0


def test_the_streams() -> None:
    assert STREAMS == ("weight_init", "shuffle", "shift", "noise", "dropout")
    assert FINAL_FOLD == N_FOLDS


def test_same_master_and_fold_give_the_same_seeds() -> None:
    assert _states(derive_seeds(1, 3)) == _states(derive_seeds(1, 3))


def test_every_stream_of_every_fold_and_master_differs() -> None:
    seen: dict[tuple[int, ...], tuple[int, int, str]] = {}
    for master in CNN_SEEDS:
        for fold in range(N_FOLDS + 1):
            for name, state in _states(derive_seeds(master, fold)).items():
                key = tuple(state)
                assert key not in seen, (master, fold, name, seen.get(key))
                seen[key] = (master, fold, name)
    assert len(seen) == len(CNN_SEEDS) * (N_FOLDS + 1) * len(STREAMS)


def test_derivation_goes_through_seed_sequence_spawn() -> None:
    master, fold = 2, 4
    children = np.random.SeedSequence(master).spawn(fold + 1)[fold].spawn(len(STREAMS))
    seeds = derive_seeds(master, fold)
    for name, child in zip(STREAMS, children, strict=True):
        assert (
            getattr(seeds, name).generate_state(4).tolist()
            == child.generate_state(4).tolist()
        )


@pytest.mark.parametrize("fold", [-1, N_FOLDS + 1])
def test_a_fold_outside_the_range_raises(fold: int) -> None:
    with pytest.raises(ValueError, match="fold"):
        derive_seeds(0, fold)


def test_torch_seed_is_a_stable_non_negative_int() -> None:
    seeds = derive_seeds(0, 0)
    value = torch_seed(seeds.dropout)
    assert isinstance(value, int)
    assert 0 <= value < 2**63
    assert value == torch_seed(derive_seeds(0, 0).dropout)
    assert value != torch_seed(seeds.weight_init)
