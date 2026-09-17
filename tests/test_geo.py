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
def test_resolve_us_location(value, expected):
    place = resolve_location(value)
    assert place.country == "US"
    assert place.region == expected


@pytest.mark.parametrize("value", ["", "   ", "banana", "ZZ", "Mexico City"])
def test_unresolvable_location_raises(value):
    with pytest.raises(UnknownLocation):
        resolve_location(value)


def test_american_samoa_is_rejected_with_a_useful_message():
    # AS has a ZIP but no federal district court of its own.
    with pytest.raises(UnknownLocation, match="no federal district court"):
        resolve_location("96799")


def test_country_can_be_forced():
    assert resolve_location("CA", "US").region == "CA"       # California
    assert resolve_location("ON", "CA").region == "ON"       # Ontario
    with pytest.raises(UnknownLocation):
        resolve_location("94110", "CA")
    with pytest.raises(UnknownLocation):
        resolve_location("M5V 3A8", "US")


def test_unsupported_country_is_rejected():
    with pytest.raises(UnknownLocation, match="unsupported country"):
        resolve_location("Toronto", "MX")



# ---------------------------------------------------------------- Canada ---


@pytest.mark.parametrize(
    "postal,expected",
    [
        ("M5V 3A8", "ON"), ("m5v3a8", "ON"), ("K1A 0B1", "ON"), ("N2L", "ON"),
        ("H3Z 2Y7", "QC"), ("G1R", "QC"), ("J4B", "QC"),
        ("V6B 1A1", "BC"), ("T2P 2M5", "AB"), ("S7K", "SK"), ("R3C", "MB"),
        ("B3H", "NS"), ("E3B", "NB"), ("A1C", "NL"), ("C1A", "PE"),
        ("Y1A 2C6", "YT"),
    ],
)
def test_postal_code_maps_to_province(postal, expected):
    from cals.geo import province_for_postal_code

    assert province_for_postal_code(postal) == expected


@pytest.mark.parametrize(
    "postal,expected",
    [
        ("X0A 0H0", "NU"), ("X0B 1K0", "NU"), ("X0C 0A0", "NU"),
        ("X1A 2L9", "NT"), ("X0E 1H0", "NT"), ("X0G 0A0", "NT"),
    ],
)
def test_the_shared_x_postal_prefix_splits_the_territories(postal, expected):
    """NT and NU both use X, so the FSA has to decide."""
    from cals.geo import province_for_postal_code

    assert province_for_postal_code(postal) == expected


@pytest.mark.parametrize("bad", ["", "M5V3A8X9Z", "12345", "abc", None])
def test_bad_postal_code_returns_none(bad):
    from cals.geo import province_for_postal_code

    assert province_for_postal_code(bad) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("M5V 3A8", "ON"), ("Ontario", "ON"), ("ON", "ON"),
        ("British Columbia", "BC"), ("BC", "BC"),
        ("Quebec", "QC"), ("Qu\u00e9bec", "QC"), ("QU\u00c9BEC", "QC"),
        ("Toronto", "ON"), ("Montr\u00e9al", "QC"), ("montreal", "QC"),
        ("Vancouver", "BC"), ("Calgary", "AB"), ("Iqaluit", "NU"),
        ("Newfoundland and Labrador", "NL"), ("PEI", "PE"),
    ],
)
def test_resolve_canadian_location(value, expected):
    place = resolve_location(value)
    assert place.country == "CA"
    assert place.region == expected
    assert place.is_canada


def test_accents_are_folded_not_stripped():
    """Naive punctuation stripping turns "qu\u00e9bec" into "qubec" and loses it."""
    assert resolve_location("Qu\u00e9bec").region == "QC"
    assert resolve_location("quebec").region == "QC"


def test_us_location_is_not_canada():
    assert resolve_location("94110").is_canada is False
