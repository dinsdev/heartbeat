"""DATA-07: the six RR features (R8, R9 and the settled definitions)."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from numpy.typing import NDArray

from heartbeat.constants import FS_HZ, RR_FEATURE_NAMES, RR_LONG_WINDOW_SAMPLES
from heartbeat.signal.rr import rr_features

PRE, POST, LOCAL, LONG, PRE_OVER_LOCAL, POST_OVER_PRE = range(6)


def _samples(intervals: list[int], start: int = 500) -> NDArray[np.int64]:
    return np.cumsum([start, *intervals]).astype(np.int64)


intervals_strategy = st.lists(st.integers(60, 2000), min_size=3, max_size=40)


def test_feature_names_match_the_columns() -> None:
    assert RR_FEATURE_NAMES == (
        "pre_rr_s",
        "post_rr_s",
        "local_avg_rr_s",
        "long_avg_rr_s",
        "pre_over_local",
        "post_over_pre",
    )


def test_shape_is_one_row_per_kept_beat() -> None:
    features = rr_features(_samples([300, 310, 320, 330]))
    assert features.shape == (3, 6)
    assert features.dtype == np.float64


@pytest.mark.parametrize("samples", [[100], [100, 400]])
def test_fewer_than_three_beats_raise(samples: list[int]) -> None:
    with pytest.raises(ValueError, match="3 beats"):
        rr_features(np.array(samples, dtype=np.int64))


@pytest.mark.parametrize("samples", [[100, 400, 400, 700], [100, 400, 300, 700]])
def test_non_increasing_samples_raise(samples: list[int]) -> None:
    with pytest.raises(ValueError, match="increasing"):
        rr_features(np.array(samples, dtype=np.int64))


@pytest.mark.rule("R8")
@given(intervals=intervals_strategy, data=st.data())
def test_moving_a_beat_two_or_more_ahead_never_changes_a_row(
    intervals: list[int], data: st.DataObject
) -> None:
    samples = _samples(intervals)
    n = samples.size
    j = data.draw(st.integers(3, n - 1), label="moved beat")
    upper = samples[j + 1] - 1 if j + 1 < n else samples[j] + 5000
    new = data.draw(
        st.integers(int(samples[j - 1]) + 1, int(upper)).filter(
            lambda s: s != samples[j]
        ),
        label="new sample",
    )
    moved = samples.copy()
    moved[j] = new
    before, after = rr_features(samples), rr_features(moved)
    # Row r holds beat r + 1; beats up to j - 2 sit two or more behind beat j.
    for beat in range(1, j - 1):
        np.testing.assert_array_equal(before[beat - 1], after[beat - 1])


@pytest.mark.rule("R8")
@given(intervals=intervals_strategy, data=st.data())
def test_moving_the_next_beat_changes_only_post_rr_and_its_ratio(
    intervals: list[int], data: st.DataObject
) -> None:
    samples = _samples(intervals)
    n = samples.size
    i = data.draw(st.integers(1, n - 2), label="kept beat")
    j = i + 1
    upper = samples[j + 1] - 1 if j + 1 < n else samples[j] + 5000
    new = data.draw(
        st.integers(int(samples[i]) + 1, int(upper)).filter(lambda s: s != samples[j]),
        label="new sample",
    )
    moved = samples.copy()
    moved[j] = new
    row_before, row_after = rr_features(samples)[i - 1], rr_features(moved)[i - 1]
    for column in (PRE, LOCAL, LONG, PRE_OVER_LOCAL):
        assert row_before[column] == row_after[column]
    assert row_before[POST] != row_after[POST]
    assert row_before[POST_OVER_PRE] != row_after[POST_OVER_PRE]


@pytest.mark.rule("R9")
def test_a_q_beat_is_an_rr_endpoint() -> None:
    # N at 0, Q at 300, N at 600, N at 900: every annotated beat is passed in,
    # so the N after the Q has a pre-RR of 300 samples, not 600.
    features = rr_features(np.array([0, 300, 600, 900], dtype=np.int64))
    assert features[1, PRE] == 300 / FS_HZ
    assert features[0, POST] == 300 / FS_HZ


def test_pre_and_post_rr_are_the_neighbouring_intervals() -> None:
    features = rr_features(_samples([360, 180, 540]))
    assert features[:, PRE].tolist() == [1.0, 0.5]
    assert features[:, POST].tolist() == [0.5, 1.5]
    assert features[:, POST_OVER_PRE].tolist() == [0.5, 3.0]


def test_first_kept_beat_averages_equal_its_pre_rr() -> None:
    features = rr_features(_samples([400, 300, 200]))
    assert features[0, LOCAL] == features[0, PRE] == 400 / FS_HZ
    assert features[0, LONG] == features[0, PRE]
    assert features[0, PRE_OVER_LOCAL] == 1.0


def test_local_average_uses_the_last_ten_intervals_including_its_own() -> None:
    intervals = [100 + 10 * k for k in range(15)]  # RR_1 to RR_15
    features = rr_features(_samples(intervals))
    rr = np.array(intervals, dtype=np.float64) / FS_HZ
    # Beat 12: RR_3 to RR_12, that is intervals[2:12].
    assert features[11, LOCAL] == pytest.approx(rr[2:12].mean(), rel=1e-15)
    # Beat 3, near the start: RR_1 to RR_3.
    assert features[2, LOCAL] == pytest.approx(rr[0:3].mean(), rel=1e-15)
    assert features[11, PRE_OVER_LOCAL] == pytest.approx(
        rr[11] / rr[2:12].mean(), rel=1e-15
    )


def test_long_average_includes_an_interval_ending_exactly_5_minutes_before() -> None:
    # Beat 2 sits exactly 108,000 samples after beat 1, so RR_1 is in.
    samples = np.array(
        [0, 1000, 1000 + RR_LONG_WINDOW_SAMPLES, 110_000], dtype=np.int64
    )
    features = rr_features(samples)
    expected = (1000 + RR_LONG_WINDOW_SAMPLES) / 2 / FS_HZ
    assert features[1, LONG] == pytest.approx(expected, rel=1e-15)


def test_long_average_excludes_an_interval_ending_one_sample_earlier() -> None:
    samples = np.array(
        [0, 1000, 1001 + RR_LONG_WINDOW_SAMPLES, 110_000], dtype=np.int64
    )
    features = rr_features(samples)
    # RR_1 ends 108,001 samples before beat 2, so only RR_2 (108,001) is in.
    assert features[1, LONG] == (RR_LONG_WINDOW_SAMPLES + 1) / FS_HZ


def test_long_average_over_a_long_record_matches_a_direct_sum() -> None:
    rng = np.random.default_rng(7)
    intervals = rng.integers(200, 500, size=2000).tolist()
    samples = _samples(intervals)
    features = rr_features(samples)
    rr = np.diff(samples) / FS_HZ
    for i in (1, 50, 400, 1500, samples.size - 2):
        ks = [k for k in range(1, i + 1) if samples[i] - samples[k] <= 108_000]
        expected = rr[np.array(ks) - 1].mean()
        assert features[i - 1, LONG] == pytest.approx(expected, rel=1e-12)
