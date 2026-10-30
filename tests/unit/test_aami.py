"""DATA-09, DATA-10: strict annotation symbol to AAMI class mapping (R10)."""

import numpy as np
import pytest

from heartbeat.constants import AAMI_CLASS
from heartbeat.data.aami import NON_BEAT_SYMBOLS, UnknownSymbolError, classify_symbols

# DATA-09, written out here rather than read from the code under test.
DATA_09 = {
    "N": "NLRej",
    "S": "AaJS",
    "V": "VE",
    "F": "F",
    "Q": "/fQ",
}


@pytest.mark.rule("R10")
def test_unknown_symbol_raises_naming_record_index_and_symbol() -> None:
    with pytest.raises(UnknownSymbolError, match=r"record 101.*annotation 2.*'\?'"):
        classify_symbols("101", ["N", "+", "?", "N"])


@pytest.mark.rule("R10")
@pytest.mark.parametrize("symbol", ["P", "p", "t", "u", "s", "T", "*", "D", "=", "^"])
def test_symbols_outside_data_09_raise(symbol: str) -> None:
    with pytest.raises(UnknownSymbolError):
        classify_symbols("101", ["N", symbol])


@pytest.mark.rule("R10")
def test_mapping_covers_exactly_the_data_09_symbols() -> None:
    expected = {s: cls for cls, symbols in DATA_09.items() for s in symbols}
    assert dict(AAMI_CLASS) == expected


@pytest.mark.rule("R10")
@pytest.mark.parametrize(
    ("symbol", "aami"),
    [(s, cls) for cls, symbols in DATA_09.items() for s in symbols],
)
def test_every_data_09_symbol_maps_to_its_class(symbol: str, aami: str) -> None:
    is_beat, classes = classify_symbols("101", [symbol])
    assert is_beat.tolist() == [True]
    assert classes.tolist() == [aami]


@pytest.mark.rule("R10")
def test_flutter_waves_and_non_conducted_p_waves_are_not_beats() -> None:
    assert "!" in NON_BEAT_SYMBOLS
    assert "x" in NON_BEAT_SYMBOLS
    is_beat, classes = classify_symbols("207", ["N", "!", "x", "V"])
    assert is_beat.tolist() == [True, False, False, True]
    assert classes.tolist() == ["N", "V"]


def test_beat_and_non_beat_symbols_do_not_overlap() -> None:
    assert not set(AAMI_CLASS) & NON_BEAT_SYMBOLS
    assert frozenset('+~|!x[]"') == NON_BEAT_SYMBOLS


def test_classes_come_back_as_a_string_array() -> None:
    is_beat, classes = classify_symbols("101", ["N", "+", "A", "~", "Q"])
    assert is_beat.dtype == np.bool_
    assert classes.dtype.kind == "U"
    assert classes.tolist() == ["N", "S", "Q"]
