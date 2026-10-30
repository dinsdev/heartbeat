"""R23: the CNN trains on real DS1 data without crashing (layer L2, CPU).

A few CPU batches through `train_epochs` with real traces; DS1 only.
"""

from pathlib import Path

import numpy as np
import pytest

from heartbeat.data import loader as loader_module
from heartbeat.data.loader import load_ds1, load_ds1_traces
from heartbeat.data.manifests import Splits
from heartbeat.data.npz import PreparedRecord, load_prepared
from heartbeat.data.prepare import PrepareReport
from heartbeat.models.augment import validation_windows
from heartbeat.models.inputs import apply_rr_scaler, fit_rr_scaler, rr_model_inputs
from heartbeat.train.loop import TrainData, cnn_logits, init_model, train_epochs
from heartbeat.train.seeds import derive_seeds
from heartbeat.train.torch_setup import configure_torch
from heartbeat.train.weights import balanced_class_weights

# Training records with all four classes between them, and one held out.
TRAIN_RECORDS = ["101", "106", "208"]
HELD_RECORD = "119"


@pytest.mark.rule("R23")
def test_a_few_cpu_batches_on_real_ds1_give_a_finite_loss_and_logits(
    prepared_ds1: tuple[Path, PrepareReport],
    splits: Splits,
    subjects: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder, _ = prepared_ds1
    read: list[str] = []
    real_load = load_prepared

    def spy(path: Path) -> PreparedRecord:
        read.append(path.stem)
        return real_load(path)

    monkeypatch.setattr(loader_module, "load_prepared", spy)
    records = [*TRAIN_RECORDS, HELD_RECORD]
    beats = load_ds1(folder, splits, subjects, records=records)
    traces = load_ds1_traces(folder, splits, subjects, records=records)
    assert set(read) <= set(splits.ds1)
    assert not set(read) & set(splits.ds2)

    # A few batches, one epoch: every non-N training beat and every 8th N beat.
    in_train = beats.record_id != HELD_RECORD
    is_n = beats.beat_class == "N"
    every_8th = np.zeros(beats.sample.size, dtype=bool)
    every_8th[::8] = True
    train = np.flatnonzero(in_train & (~is_n | every_8th))
    held = np.flatnonzero(beats.record_id == HELD_RECORD)
    y = beats.beat_class[train]
    assert set(y.tolist()) == {"N", "S", "V", "F"}
    rr = rr_model_inputs(beats.rr_s)
    scaler = fit_rr_scaler(rr[train])
    data = TrainData(
        traces=traces,
        record=beats.record_id[train],
        sample=beats.sample[train],
        rr=apply_rr_scaler(scaler, rr[train]).astype(np.float32),
    )
    device = configure_torch("cpu")
    seeds = derive_seeds(0, 0)
    (model,) = list(
        train_epochs(
            init_model(1.0, seeds),
            data,
            y,
            balanced_class_weights(y),
            seeds,
            1,
            device,
        )
    )
    windows = validation_windows(beats)[held]
    logits = cnn_logits(
        model, windows, apply_rr_scaler(scaler, rr[held]).astype(np.float32), device
    )
    assert logits.shape == (held.size, 4)
    assert np.all(np.isfinite(logits))
