"""Strict annotation symbol to AAMI class mapping (B4; DATA-09, DATA-10)."""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from heartbeat.constants import AAMI_CLASS, NON_BEAT_SYMBOLS

__all__ = ["NON_BEAT_SYMBOLS", "UnknownSymbolError", "classify_symbols"]


class UnknownSymbolError(ValueError):
    """An annotation symbol is neither a DATA-09 beat nor a known non-beat (R10)."""


def classify_symbols(
    record_id: str, symbols: Sequence[str]
) -> tuple[NDArray[np.bool_], NDArray[np.str_]]:
    """Split a record's annotations into beats and non-beats, and class the beats.

    Args:
        record_id: The record, for error messages.
        symbols: Every annotation symbol of the record, in order.

    Returns:
        A mask of shape `(n_annotations,)` that is true for beats, and the AAMI
        class of each beat, shape `(n_beats,)`.

    Raises:
        UnknownSymbolError: Naming the record, the annotation index and the symbol.
    """
    is_beat = np.zeros(len(symbols), dtype=np.bool_)
    classes: list[str] = []
    for index, symbol in enumerate(symbols):
        if symbol in AAMI_CLASS:
            is_beat[index] = True
            classes.append(AAMI_CLASS[symbol])
        elif symbol not in NON_BEAT_SYMBOLS:
            raise UnknownSymbolError(
                f"record {record_id}, annotation {index}: unknown symbol {symbol!r}"
            )
    return is_beat, np.array(classes, dtype="<U1")
