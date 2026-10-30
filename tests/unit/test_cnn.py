"""C3, MODEL-02: the CNN's shape, its parameter counts, and its eval mode."""

import pytest
import torch
from torch import nn

from heartbeat.constants import (
    CNN_CHANNELS,
    CNN_HIDDEN,
    CNN_WIDTHS,
    RR_FEATURE_NAMES,
    SCORED_CLASSES,
    WINDOW_SAMPLES,
)
from heartbeat.models.cnn import HeartbeatCNN


@pytest.mark.parametrize(
    ("width", "expected"), [(0.5, 14_724), (1.0, 52_036), (2.0, 196_548)]
)
def test_parameter_counts_match_c7(width: float, expected: int) -> None:
    model = HeartbeatCNN(width)
    assert sum(p.numel() for p in model.parameters()) == expected


def test_the_widths_are_the_c3_ones() -> None:
    assert CNN_WIDTHS == (0.5, 1.0, 2.0)
    assert CNN_CHANNELS == (16, 32, 64, 64)
    assert CNN_HIDDEN == 64


def test_output_is_one_logit_per_scored_class_in_float32() -> None:
    torch.manual_seed(0)
    model = HeartbeatCNN(1.0).eval()
    window = torch.randn(5, 1, WINDOW_SAMPLES)
    rr = torch.randn(5, len(RR_FEATURE_NAMES))
    out = model(window, rr)
    assert out.shape == (5, len(SCORED_CLASSES))
    assert out.dtype == torch.float32


def test_eval_mode_gives_identical_outputs_on_two_calls() -> None:
    torch.manual_seed(0)
    model = HeartbeatCNN(1.0).eval()
    window = torch.randn(8, 1, WINDOW_SAMPLES)
    rr = torch.randn(8, len(RR_FEATURE_NAMES))
    with torch.no_grad():
        first = model(window, rr)
        second = model(window, rr)
    assert torch.equal(first, second)


def test_train_mode_applies_dropout() -> None:
    torch.manual_seed(0)
    model = HeartbeatCNN(1.0).train()
    window = torch.randn(8, 1, WINDOW_SAMPLES)
    rr = torch.randn(8, len(RR_FEATURE_NAMES))
    with torch.no_grad():
        assert not torch.equal(model(window, rr), model(window, rr))


@pytest.mark.parametrize("width", CNN_WIDTHS)
def test_channels_scale_with_width_and_the_hidden_layer_stays_64(
    width: float,
) -> None:
    model = HeartbeatCNN(width)
    convs = [m for m in model.modules() if isinstance(m, nn.Conv1d)]
    assert [c.out_channels for c in convs] == [int(c * width) for c in CNN_CHANNELS]
    assert all(c.kernel_size == (7,) for c in convs)
    linears = [m for m in model.modules() if isinstance(m, nn.Linear)]
    assert [(lin.in_features, lin.out_features) for lin in linears] == [
        (int(CNN_CHANNELS[-1] * width) + len(RR_FEATURE_NAMES), CNN_HIDDEN),
        (CNN_HIDDEN, len(SCORED_CLASSES)),
    ]
    dropouts = [m for m in model.modules() if isinstance(m, nn.Dropout)]
    assert [d.p for d in dropouts] == [0.3]


def test_an_unknown_width_raises() -> None:
    with pytest.raises(ValueError, match="width"):
        HeartbeatCNN(1.5)
