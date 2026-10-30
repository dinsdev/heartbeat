"""DATA-04: the MLII lead is picked by name in any channel order (R4)."""

import pytest

from heartbeat.data.records import LeadNotFoundError, select_lead


@pytest.mark.rule("R4")
def test_mlii_second_as_in_record_114() -> None:
    assert select_lead(["V5", "MLII"], "MLII") == 1


@pytest.mark.rule("R4")
def test_mlii_first() -> None:
    assert select_lead(["MLII", "V1"], "MLII") == 0


@pytest.mark.rule("R4")
def test_missing_lead_raises() -> None:
    with pytest.raises(LeadNotFoundError, match=r"MLII.*V1.*V5"):
        select_lead(["V1", "V5"], "MLII")


@pytest.mark.rule("R4")
def test_duplicate_lead_raises() -> None:
    with pytest.raises(LeadNotFoundError, match="twice"):
        select_lead(["MLII", "MLII"], "MLII")
