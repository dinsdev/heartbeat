"""DATA-04 on real records: MLII by name in both channel orders (R4).

Record 114 is DS1 and is read in full. Record 100 is DS2, so only its header
(lead names and rate) is read, never its signal (rule 1).
"""

from pathlib import Path

import numpy as np
import pytest
import wfdb

from heartbeat.constants import FS_HZ
from heartbeat.data.manifests import Splits
from heartbeat.data.records import read_record, select_lead


@pytest.mark.rule("R4")
def test_record_114_has_mlii_second_and_reads_it(raw_dir: Path, splits: Splits) -> None:
    assert "114" in splits.ds1
    header = wfdb.rdheader(str(raw_dir / "114"))
    assert header.fs == FS_HZ
    assert select_lead(header.sig_name, splits.lead) == 1
    raw = read_record(raw_dir, "114", splits.lead)
    assert raw.mlii_mv.dtype == np.float64
    assert raw.mlii_mv.shape == (header.sig_len,)
    record = wfdb.rdrecord(str(raw_dir / "114"), physical=True)
    np.testing.assert_array_equal(raw.mlii_mv, record.p_signal[:, 1])


@pytest.mark.rule("R4")
def test_record_100_header_has_mlii_first(raw_dir: Path, splits: Splits) -> None:
    header = wfdb.rdheader(str(raw_dir / "100"))
    assert header.fs == FS_HZ
    assert select_lead(header.sig_name, splits.lead) == 0
