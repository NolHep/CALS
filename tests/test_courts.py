import pytest

from cals.courts import (
    COURT_STATE,
    STATE_CIRCUIT_COURT,
    STATE_DISTRICT_COURTS,
    courts_for_state,
    supported_states,
)


def test_there_are_94_federal_district_courts():
    every = [c for courts in STATE_DISTRICT_COURTS.values() for c in courts]
    assert len(every) == 94
    assert len(set(every)) == 94, "court ids must not be shared between states"


def test_every_state_has_a_circuit():
    assert not set(STATE_DISTRICT_COURTS) - set(STATE_CIRCUIT_COURT)


@pytest.mark.parametrize(
    "state,expected",
    [
        ("CA", {"cand", "cacd", "caed", "casd"}),
        ("WY", {"wyd"}),
        ("MP", {"nmid"}),
        ("PR", {"prd"}),
    ],
)
def test_courts_for_state(state, expected):
    assert set(courts_for_state(state)) == expected


def test_courts_for_state_is_case_insensitive():
    assert courts_for_state("ca") == courts_for_state("CA")


def test_include_appeals_adds_the_circuit():
    assert "ca9" in courts_for_state("CA", include_appeals=True)
    assert "cadc" in courts_for_state("DC", include_appeals=True)
    assert "ca9" not in courts_for_state("CA")


def test_unknown_state_raises():
    with pytest.raises(KeyError):
        courts_for_state("ZZ")


def test_court_state_reverse_lookup():
    assert COURT_STATE["cand"] == "CA"
    assert COURT_STATE["nysd"] == "NY"
    assert COURT_STATE["nmid"] == "MP"


def test_supported_states_sorted_by_name():
    names = [s["name"] for s in supported_states()]
    assert names == sorted(names)
    assert len(names) == len(STATE_DISTRICT_COURTS)
