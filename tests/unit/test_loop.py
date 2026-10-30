"""MODEL-03, MODEL-06, R22: the epoch loop on small synthetic data, on CPU."""

from collections.abc import Iterator, Mapping
from typing import Any

import numpy as np
import pytest
import torch
from cnn_support import beats_with_traces
from numpy.typing import NDArray

from heartbeat.constants import BATCH_SIZE, SCORED_CLASSES
from heartbeat.data.loader import BeatTable
from heartbeat.models.augment import augment_batch, validation_windows
from heartbeat.models.cnn import HeartbeatCNN
from heartbeat.train import loop as loop_module
from heartbeat.train.loop import (
    NonFiniteLossError,
    TrainData,
    cnn_logits,
    init_model,
    train_epochs,
)
from heartbeat.train.seeds import derive_seeds
from heartbeat.train.torch_setup import configure_torch
from heartbeat.train.weights import balanced_class_weights

WIDTH = 0.5


@pytest.fixture(scope="module")
def data() -> tuple[BeatTable, dict[str, NDArray[np.int16]]]:
    # 4 x 160 = 640 beats: two full batches of 256 per epoch.
    return beats_with_traces(n_subjects=4, per_subject=160)


def _train_data(beats: BeatTable, traces: Mapping[str, NDArray[np.int16]]) -> TrainData:
    rr = beats.rr_s.astype(np.float32)
    rr = (rr - rr.mean(axis=0)) / rr.std(axis=0)
    return TrainData(traces=traces, record=beats.record_id, sample=beats.sample, rr=rr)


def _run(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
    master: int,
    n_epochs: int,
    score: bool = True,
) -> tuple[HeartbeatCNN, list[NDArray[np.float32]]]:
    beats, traces = data
    device = configure_torch("cpu")
    seeds = derive_seeds(master, 0)
    model = init_model(WIDTH, seeds)
    train = _train_data(beats, traces)
    weights = balanced_class_weights(beats.beat_class)
    logits: list[NDArray[np.float32]] = []
    windows = validation_windows(beats)
    for fitted in train_epochs(
        model, train, beats.beat_class, weights, seeds, n_epochs, device
    ):
        assert not fitted.training
        if score:
            logits.append(cnn_logits(fitted, windows, train.rr, device))
    return model, logits


def _same_weights(a: torch.nn.Module, b: torch.nn.Module) -> bool:
    sa, sb = a.state_dict(), b.state_dict()
    return sa.keys() == sb.keys() and all(torch.equal(sa[k], sb[k]) for k in sa)


@pytest.mark.rule("R22")
def test_same_seed_on_cpu_gives_identical_weights(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
) -> None:
    first, logits_a = _run(data, master=0, n_epochs=2)
    second, logits_b = _run(data, master=0, n_epochs=2)
    assert _same_weights(first, second)
    for a, b in zip(logits_a, logits_b, strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.rule("R22")
def test_a_different_seed_gives_different_weights(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
) -> None:
    first, _ = _run(data, master=0, n_epochs=2)
    other, _ = _run(data, master=1, n_epochs=2)
    assert not _same_weights(first, other)


def test_epoch_two_of_a_three_epoch_run_equals_a_two_epoch_run(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
) -> None:
    # The prefix property: train-final trains exactly the selected epochs.
    _, three = _run(data, master=2, n_epochs=3)
    _, two = _run(data, master=2, n_epochs=2)
    assert len(three) == 3
    np.testing.assert_array_equal(three[0], two[0])
    np.testing.assert_array_equal(three[1], two[1])
    assert not np.array_equal(three[2], two[1])


def test_scoring_between_epochs_consumes_no_training_stream(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
) -> None:
    scored, _ = _run(data, master=0, n_epochs=3, score=True)
    unscored, _ = _run(data, master=0, n_epochs=3, score=False)
    assert _same_weights(scored, unscored)


def test_augmentation_runs_on_training_batches_and_never_on_validation(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beats, traces = data
    real = augment_batch
    calls: list[set[tuple[str, int]]] = []

    def spy(*args: Any, **kwargs: Any) -> NDArray[np.float32]:
        record, sample = args[1], args[2]
        calls.append(set(zip(record.tolist(), sample.tolist(), strict=True)))
        return real(*args, **kwargs)

    monkeypatch.setattr(loop_module, "augment_batch", spy)
    # Train on the first 512 beats; the other 128 (record s03) are held out.
    train_rows = np.arange(512)
    held = np.arange(512, beats.sample.size)
    device = configure_torch("cpu")
    seeds = derive_seeds(0, 1)
    train = _train_data(beats, traces)
    sub = TrainData(
        traces=traces,
        record=beats.record_id[train_rows],
        sample=beats.sample[train_rows],
        rr=train.rr[train_rows],
    )
    y = beats.beat_class[train_rows]
    gen: Iterator[HeartbeatCNN] = train_epochs(
        init_model(WIDTH, seeds),
        sub,
        y,
        balanced_class_weights(y),
        seeds,
        2,
        device,
    )
    windows = validation_windows(beats)
    for fitted in gen:
        before = len(calls)
        cnn_logits(fitted, windows[held], train.rr[held], device)
        assert len(calls) == before
    # Two epochs of 512 // 256 = 2 full batches each.
    assert len(calls) == 2 * (512 // BATCH_SIZE)
    assert all(len(c) == BATCH_SIZE for c in calls)
    train_keys = set(
        zip(
            beats.record_id[train_rows].tolist(),
            beats.sample[train_rows].tolist(),
            strict=True,
        )
    )
    held_keys = set(
        zip(beats.record_id[held].tolist(), beats.sample[held].tolist(), strict=True)
    )
    augmented = set().union(*calls)
    assert augmented <= train_keys
    assert not augmented & held_keys
    # Each epoch augments every training beat once (drop_last leaves none here).
    assert calls[0] | calls[1] == train_keys
    assert calls[2] | calls[3] == train_keys


def test_a_non_finite_loss_raises_with_the_epoch_and_batch(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
) -> None:
    beats, traces = data
    device = configure_torch("cpu")
    seeds = derive_seeds(0, 0)
    train = _train_data(beats, traces)
    rr = train.rr.copy()
    rr[:, 0] = np.nan
    broken = TrainData(traces=traces, record=train.record, sample=train.sample, rr=rr)
    gen = train_epochs(
        init_model(WIDTH, seeds),
        broken,
        beats.beat_class,
        balanced_class_weights(beats.beat_class),
        seeds,
        1,
        device,
    )
    with pytest.raises(NonFiniteLossError, match=r"epoch 1, batch 0"):
        next(gen)


def test_logits_are_float32_in_scored_class_order(
    data: tuple[BeatTable, dict[str, NDArray[np.int16]]],
) -> None:
    beats, _ = data
    _, logits = _run(data, master=0, n_epochs=1)
    assert logits[0].dtype == np.float32
    assert logits[0].shape == (beats.sample.size, len(SCORED_CLASSES))
    assert np.all(np.isfinite(logits[0]))
