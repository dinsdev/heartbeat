"""C2, C3: one balanced class-weight function for every model."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from sklearn.utils.class_weight import compute_class_weight

from heartbeat.constants import SCORED_CLASSES
from heartbeat.train.weights import balanced_class_weights


@given(st.lists(st.sampled_from(SCORED_CLASSES), min_size=4, max_size=300))
def test_equals_sklearn_balanced(labels: list[str]) -> None:
    y = np.array(labels)
    if set(labels) != set(SCORED_CLASSES):
        with pytest.raises(ValueError, match="no training beats"):
            balanced_class_weights(y)
        return
    expected = compute_class_weight("balanced", classes=np.array(SCORED_CLASSES), y=y)
    ours = balanced_class_weights(y)
    assert list(ours) == list(SCORED_CLASSES)
    np.testing.assert_allclose([ours[c] for c in SCORED_CLASSES], expected, rtol=1e-12)


def test_hand_case() -> None:
    y = np.array(["N"] * 6 + ["S"] * 2 + ["V"] * 3 + ["F"])
    # n / (4 * count): 12 / 24, 12 / 8, 12 / 12, 12 / 4.
    assert balanced_class_weights(y) == {"N": 0.5, "S": 1.5, "V": 1.0, "F": 3.0}


def test_q_raises() -> None:
    with pytest.raises(ValueError, match="Q"):
        balanced_class_weights(np.array(["N", "S", "V", "F", "Q"]))
