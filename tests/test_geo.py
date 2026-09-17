import pytest

from cals.geo import UnknownLocation, resolve_location, state_for_zip


@pytest.mark.parametrize(
    "zip_code,expected",
    [
        ("94110", "CA"), ("10001", "NY"), ("02139", "MA"), ("78701", "TX"),
        ("99501", "AK"), ("00901", "PR"), ("96910", "GU"), ("60614", "IL"),
        ("33139", "FL"), ("20500", "DC"), ("20147", "VA"), ("21201", "MD"),
        ("75502", "AR"), ("75501", "TX"), ("88510", "TX"), ("89101", "NV"),
        ("06390", "NY"), ("00501", "NY"), ("96950", "MP"), ("98101", "WA"),
        ("94110-1234", "CA"),
    ],
)
def test_zip_maps_to_state(zip_code, expected):
    assert state_for_zip(zip_code) == expected


@pytest.mark.parametrize("bad", ["", "abc", "1234", "notazip", None])
def test_bad_zip_returns_none(bad):
    assert state_for_zip(bad) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("94110", "CA"), ("CA", "CA"), ("ca", "CA"), ("california", "CA"),
        ("New York", "NY"), ("Washington, D.C.", "DC"), ("D.C.", "DC"),
        ("  texas  ", "TX"), ("U.S. Virgin Islands", "VI"),
    ],
)
def test_resolve_location(value, expected):
    assert resolve_location(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "banana", "ZZ", "Ontario"])
def test_unresolvable_location_raises(value):
    with pytest.raises(UnknownLocation):
        resolve_location(value)


def test_american_samoa_is_rejected_with_a_useful_message():
    # AS has a ZIP but no federal district court of its own.
    with pytest.raises(UnknownLocation, match="no federal district court"):
        resolve_location("96799")
