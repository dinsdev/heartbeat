"""The CNN (C3; MODEL-02).

The 256-sample window goes through four blocks of Conv1d (kernel 7), batch
norm, ReLU and max-pool by 2, then global average pooling; the result is
concatenated with the six standardized RR inputs and goes through a 64-unit
layer with dropout 0.3 to four logits in `SCORED_CLASSES` order. The width
scales the conv channels only. Float32 throughout (CONVENTIONS section 2).
"""

import itertools

import torch
from torch import nn

from heartbeat.constants import (
    CNN_CHANNELS,
    CNN_DROPOUT,
    CNN_HIDDEN,
    CNN_KERNEL,
    CNN_WIDTHS,
    RR_FEATURE_NAMES,
    SCORED_CLASSES,
    WINDOW_SAMPLES,
)


def _block(in_channels: int, out_channels: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv1d(in_channels, out_channels, CNN_KERNEL, padding=CNN_KERNEL // 2),
        nn.BatchNorm1d(out_channels),
        nn.ReLU(),
        nn.MaxPool1d(2),
    )


class HeartbeatCNN(nn.Module):
    """The C3 network at one of the three widths.

    Raises:
        ValueError: On a width outside `CNN_WIDTHS`.
    """

    def __init__(self, width: float) -> None:
        """Build the layers; weights come from torch's global generator."""
        super().__init__()
        if width not in CNN_WIDTHS:
            raise ValueError(f"width {width} is not one of {CNN_WIDTHS}")
        self.width = width
        channels = [1, *(int(c * width) for c in CNN_CHANNELS)]
        self.features = nn.Sequential(
            *(_block(a, b) for a, b in itertools.pairwise(channels))
        )
        self.head = nn.Sequential(
            nn.Linear(channels[-1] + len(RR_FEATURE_NAMES), CNN_HIDDEN),
            nn.ReLU(),
            nn.Dropout(CNN_DROPOUT),
            nn.Linear(CNN_HIDDEN, len(SCORED_CLASSES)),
        )

    def forward(self, window: torch.Tensor, rr: torch.Tensor) -> torch.Tensor:
        """Logits `(b, 4)` from windows `(b, 1, 256)` and RR inputs `(b, 6)`."""
        assert window.shape[1:] == (1, WINDOW_SAMPLES), window.shape
        assert rr.shape[1:] == (len(RR_FEATURE_NAMES),), rr.shape
        # Global average pooling as a plain mean over time.
        pooled = self.features(window).mean(dim=2)
        logits: torch.Tensor = self.head(torch.cat([pooled, rr], dim=1))
        return logits
