"""Deterministic mode, threads and device for every training run (MODEL-06).

Phase 4 settling 5: every run, MPS or CPU, uses
`torch.use_deterministic_algorithms(True)` and 4 threads, and its run folder
records both and the device.
"""

from typing import Any

import torch

from heartbeat.config import CV_DEVICES as DEVICES
from heartbeat.constants import TORCH_THREADS


class DeviceUnavailableError(RuntimeError):
    """The asked-for device is not available (Phase 4 plan, stop condition 7)."""


def configure_torch(device: str) -> torch.device:
    """Set deterministic mode and the thread count; return the device.

    Raises:
        ValueError: On a device other than cpu or mps.
        DeviceUnavailableError: If mps is asked for and not available.
    """
    if device not in DEVICES:
        raise ValueError(f"device {device!r} is not one of {DEVICES}")
    if device == "mps" and not torch.backends.mps.is_available():
        raise DeviceUnavailableError("mps is not available on this machine")
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(TORCH_THREADS)
    return torch.device(device)


def torch_provenance(device: torch.device) -> dict[str, Any]:
    """What a run folder records about torch (MODEL-07)."""
    return {
        "torch": torch.__version__,
        "device": device.type,
        "torch_threads": torch.get_num_threads(),
        "deterministic": torch.are_deterministic_algorithms_enabled(),
    }
