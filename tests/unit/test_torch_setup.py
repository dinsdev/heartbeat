"""MODEL-06, Phase 4 settling 5: deterministic mode and 4 threads on every device."""

import pytest
import torch

from heartbeat.constants import TORCH_THREADS
from heartbeat.train.torch_setup import (
    DeviceUnavailableError,
    configure_torch,
    torch_provenance,
)


def test_cpu_sets_deterministic_mode_and_four_threads() -> None:
    torch.use_deterministic_algorithms(False)
    torch.set_num_threads(1)
    device = configure_torch("cpu")
    assert device == torch.device("cpu")
    assert torch.are_deterministic_algorithms_enabled()
    assert torch.get_num_threads() == TORCH_THREADS == 4


def test_mps_unavailable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    with pytest.raises(DeviceUnavailableError, match="mps"):
        configure_torch("mps")


def test_an_unknown_device_raises() -> None:
    with pytest.raises(ValueError, match="cuda"):
        configure_torch("cuda")


def test_provenance_names_torch_device_threads_and_the_flag() -> None:
    configure_torch("cpu")
    prov = torch_provenance(torch.device("cpu"))
    assert prov == {
        "torch": torch.__version__,
        "device": "cpu",
        "torch_threads": TORCH_THREADS,
        "deterministic": True,
    }
