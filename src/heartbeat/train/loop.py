"""The CNN's epoch loop (C3; MODEL-03, MODEL-06, R22).

AdamW at a constant rate, cross-entropy weighted by the driver's balanced
class weights, augmentation on training batches only. The loop yields the
model in eval mode after each epoch, so the caller can score every epoch
(Phase 4 settling 2), and puts it back in train mode before the next.

Randomness (design calls 5 and 6): weights from the weight-init stream,
dropout from torch's global generator seeded from the dropout stream at the
start of the fit, the batch order from a seeded `DataLoader` generator, shift
and noise from their own NumPy generators. Each is drawn per epoch in the
same way whatever the run length, so epoch e of a longer run equals epoch e
of a run that stops at e (the prefix property `train-final` relies on).
"""

import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import numpy as np
import torch
from numpy.typing import NDArray
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from heartbeat.constants import (
    BATCH_SIZE,
    LEARNING_RATE,
    RR_FEATURE_NAMES,
    SCORED_CLASSES,
    WEIGHT_DECAY,
)
from heartbeat.evaluate.metrics import class_indices
from heartbeat.models.augment import augment_batch
from heartbeat.models.cnn import HeartbeatCNN
from heartbeat.train.seeds import RunSeeds, torch_seed

log = logging.getLogger(__name__)

# Rows per forward pass when scoring; eval mode makes it independent of batches.
EVAL_BATCH_SIZE = 2048


class NonFiniteLossError(FloatingPointError):
    """A training loss went NaN or infinite (Phase 4 plan, stop condition 4)."""


@dataclass(frozen=True)
class TrainData:
    """What the loop trains on.

    Attributes:
        traces: Record to its int16 trace, for the re-cut shift.
        record: Each training beat's record, `(n,)`.
        sample: Each training beat's annotation sample, `(n,)`.
        rr: Scaled RR inputs, float32, `(n, 6)`.
    """

    traces: Mapping[str, NDArray[np.int16]]
    record: NDArray[np.str_]
    sample: NDArray[np.int64]
    rr: NDArray[np.float32]

    def __post_init__(self) -> None:
        """Check one row per beat and float32 inputs."""
        n = self.sample.shape[0]
        assert self.record.shape == (n,), self.record.shape
        assert self.rr.dtype == np.float32, self.rr.dtype
        assert self.rr.shape == (n, len(RR_FEATURE_NAMES)), self.rr.shape


def init_model(width: float, seeds: RunSeeds) -> HeartbeatCNN:
    """A new network with weights drawn from the run's weight-init stream."""
    torch.manual_seed(torch_seed(seeds.weight_init))
    return HeartbeatCNN(width)


def train_epochs(
    model: HeartbeatCNN,
    data: TrainData,
    y_train: NDArray[np.str_],
    class_weight: Mapping[str, float],
    seeds: RunSeeds,
    n_epochs: int,
    device: torch.device,
) -> Iterator[HeartbeatCNN]:
    """Train for `n_epochs`, yielding the model in eval mode after each epoch.

    Raises:
        NonFiniteLossError: Naming the first epoch and batch whose loss is not
            finite.
    """
    n = data.sample.size
    assert y_train.shape == (n,), y_train.shape
    # Dropout draws from the global generator (design call 5).
    torch.manual_seed(torch_seed(seeds.dropout))
    model.to(device).train()
    y = torch.from_numpy(class_indices(y_train).astype(np.int64))
    rr = torch.from_numpy(data.rr)
    weight = torch.tensor(
        [class_weight[c] for c in SCORED_CLASSES], dtype=torch.float32, device=device
    )
    loss_fn = nn.CrossEntropyLoss(weight=weight)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY
    )
    # drop_last: a batch of one breaks batch norm (design call 6).
    loader = DataLoader(
        TensorDataset(torch.arange(n)),
        batch_size=BATCH_SIZE,
        shuffle=True,
        generator=torch.Generator().manual_seed(torch_seed(seeds.shuffle)),
        num_workers=0,
        drop_last=True,
    )
    rng_shift = np.random.default_rng(seeds.shift)
    rng_noise = np.random.default_rng(seeds.noise)
    for epoch in range(1, n_epochs + 1):
        losses: list[torch.Tensor] = []
        for (index,) in loader:
            rows = index.numpy()
            window = augment_batch(
                data.traces, data.record[rows], data.sample[rows], rng_shift, rng_noise
            )
            optimizer.zero_grad(set_to_none=True)
            logits = model(torch.from_numpy(window).to(device), rr[index].to(device))
            loss = loss_fn(logits, y[index].to(device))
            loss.backward()
            optimizer.step()
            losses.append(loss.detach())
        # One device sync per epoch; the batch is found after the fact.
        per_batch = torch.stack(losses).cpu() if losses else torch.zeros(0)
        bad = torch.nonzero(~torch.isfinite(per_batch)).flatten()
        if bad.numel():
            batch = int(bad[0])
            raise NonFiniteLossError(
                f"epoch {epoch}, batch {batch}: loss {float(per_batch[batch])}"
            )
        log.debug("epoch %d: mean loss %.4f", epoch, float(per_batch.mean()))
        model.eval()
        yield model
        model.train()


def cnn_logits(
    model: HeartbeatCNN,
    windows: NDArray[np.float32],
    rr: NDArray[np.float32],
    device: torch.device,
) -> NDArray[np.float32]:
    """Raw logits `(n, 4)` in eval mode, unaugmented inputs, no random stream used.

    Args:
        model: The network, in eval mode.
        windows: Z-scored windows, `(n, 1, 256)`.
        rr: Scaled RR inputs, `(n, 6)`.
        device: Where the model lives.
    """
    assert not model.training, "score in eval mode"
    assert windows.dtype == np.float32, windows.dtype
    assert rr.dtype == np.float32, rr.dtype
    parts: list[NDArray[np.float32]] = []
    with torch.no_grad():
        for start in range(0, windows.shape[0], EVAL_BATCH_SIZE):
            stop = start + EVAL_BATCH_SIZE
            out = model(
                torch.from_numpy(windows[start:stop]).to(device),
                torch.from_numpy(rr[start:stop]).to(device),
            )
            parts.append(out.cpu().numpy())
    if not parts:
        return np.zeros((0, len(SCORED_CLASSES)), dtype=np.float32)
    return np.concatenate(parts)
