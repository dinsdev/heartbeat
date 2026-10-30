"""C3, MODEL-03, Phase 4 settling 4: shift by re-cut, then z-score, then noise."""

import numpy as np
import pytest
from cv_support import synthetic_beats

from heartbeat.constants import (
    NOISE_STD_Z,
    SHIFT_MAX_SAMPLES,
    WINDOW_BEFORE_SAMPLES,
    WINDOW_SAMPLES,
)
from heartbeat.models.augment import (
    augment_batch,
    draw_offsets,
    shifted_windows,
    validation_windows,
)
from heartbeat.signal.windows import WindowRangeError, zscore_windows

N_SAMPLES = 3_000


def _traces() -> dict[str, np.ndarray]:
    ramp = (np.arange(N_SAMPLES) % 20_000).astype(np.int16)
    # Record "b": a flat stretch, so its windows hit the z-score floor.
    flat = np.full(N_SAMPLES, 7, dtype=np.int16)
    flat[1_500:] = (np.arange(N_SAMPLES - 1_500) * 3).astype(np.int16)
    return {"a": ramp, "b": flat}


def test_the_settled_values() -> None:
    assert SHIFT_MAX_SAMPLES == 5
    assert NOISE_STD_Z == 0.05


def test_a_shifted_window_is_the_trace_cut_at_the_beat_plus_the_offset() -> None:
    traces = _traces()
    record = np.array(["a", "a", "b", "a"])
    sample = np.array([500, 900, 700, 1_200], dtype=np.int64)
    offsets = np.array([-5, 0, 3, 5], dtype=np.int64)
    windows = shifted_windows(traces, record, sample, offsets)
    assert windows.dtype == np.int16
    assert windows.shape == (4, WINDOW_SAMPLES)
    for row in range(4):
        start = int(sample[row] + offsets[row]) - WINDOW_BEFORE_SAMPLES
        np.testing.assert_array_equal(
            windows[row], traces[record[row]][start : start + WINDOW_SAMPLES]
        )


def test_offsets_cover_minus_five_to_five_and_nothing_else() -> None:
    offsets = draw_offsets(np.random.default_rng(0), 20_000)
    assert offsets.dtype == np.int64
    assert set(offsets.tolist()) == set(range(-5, 6))


def test_a_shift_that_leaves_the_record_raises() -> None:
    traces = _traces()
    edge = np.array([WINDOW_BEFORE_SAMPLES + 2], dtype=np.int64)
    with pytest.raises(WindowRangeError):
        shifted_windows(traces, np.array(["a"]), edge, np.array([-3]))


def test_augment_is_zscore_of_the_recut_window_plus_noise() -> None:
    traces = _traces()
    record = np.array(["a", "b", "b", "a"])
    sample = np.array([500, 300, 1_400, 2_000], dtype=np.int64)
    out = augment_batch(
        traces,
        record,
        sample,
        np.random.default_rng(1),
        np.random.default_rng(2),
    )
    assert out.dtype == np.float32
    assert out.shape == (4, 1, WINDOW_SAMPLES)
    shift_rng, noise_rng = np.random.default_rng(1), np.random.default_rng(2)
    offsets = draw_offsets(shift_rng, 4)
    z = zscore_windows(shifted_windows(traces, record, sample, offsets))
    expected = (z + noise_rng.normal(0.0, NOISE_STD_Z, size=z.shape)).astype(np.float32)
    np.testing.assert_array_equal(out[:, 0, :], expected)


def test_flat_windows_use_the_zscore_floor() -> None:
    traces = _traces()
    # Record b's flat stretch: a constant window z-scores to zeros, so only
    # the noise is left.
    out = augment_batch(
        traces,
        np.array(["b"] * 64),
        np.full(64, 400, dtype=np.int64),
        np.random.default_rng(3),
        np.random.default_rng(4),
    )
    noise = np.random.default_rng(4).normal(0.0, NOISE_STD_Z, size=(64, 256))
    np.testing.assert_array_equal(out[:, 0, :], noise.astype(np.float32))


def test_noise_has_standard_deviation_0_05() -> None:
    traces = _traces()
    n = 64
    record = np.array(["a"] * n)
    sample = np.full(n, 1_000, dtype=np.int64)
    out = augment_batch(
        traces, record, sample, np.random.default_rng(5), np.random.default_rng(6)
    )
    offsets = draw_offsets(np.random.default_rng(5), n)
    clean = zscore_windows(shifted_windows(traces, record, sample, offsets))
    residual = out[:, 0, :].astype(np.float64) - clean
    # 16,384 draws: the sample standard deviation's own standard error is
    # about 0.05 / sqrt(2 * 16,384), roughly 0.0003; the bound is about 7 of them.
    assert residual.std() == pytest.approx(NOISE_STD_Z, abs=0.002)
    assert abs(residual.mean()) < 0.002


def test_fresh_noise_on_every_call_with_one_generator() -> None:
    traces = _traces()
    record = np.array(["a"] * 4)
    sample = np.full(4, 1_000, dtype=np.int64)
    shift_rng, noise_rng = np.random.default_rng(7), np.random.default_rng(8)
    first = augment_batch(traces, record, sample, shift_rng, noise_rng)
    second = augment_batch(traces, record, sample, shift_rng, noise_rng)
    assert not np.array_equal(first, second)


def test_validation_windows_are_the_unaugmented_zscore_in_float32() -> None:
    beats = synthetic_beats(n_subjects=2, per_subject=20)
    rng = np.random.default_rng(9)
    windows = rng.integers(-500, 500, size=beats.window_adu.shape).astype(np.int16)
    windows[0] = 3  # a flat window, at the floor
    beats = type(beats)(
        beats.record_id,
        beats.subject_id,
        beats.sample,
        beats.beat_class,
        windows,
        beats.rr_s,
    )
    out = validation_windows(beats)
    assert out.dtype == np.float32
    assert out.shape == (beats.sample.size, 1, WINDOW_SAMPLES)
    np.testing.assert_array_equal(
        out[:, 0, :], zscore_windows(windows).astype(np.float32)
    )
    np.testing.assert_array_equal(out[0], 0.0)
