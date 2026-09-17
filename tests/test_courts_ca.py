import pytest

from cals.courts_ca import (
    COURT_NAMES,
    COURT_PROVINCE,
    FEDERAL_COURTS,
    PROVINCE_COURTS,
    PROVINCE_NAMES,
    courts_for_province,
    court_name,
    supported_provinces,
)


def test_all_thirteen_provinces_and_territories_are_covered():
    assert len(PROVINCE_COURTS) == 13
    assert set(PROVINCE_COURTS) == set(PROVINCE_NAMES)


def test_every_court_has_a_name():
    every = {c for courts in PROVINCE_COURTS.values() for c in courts}
    every |= set(FEDERAL_COURTS)
    assert not every - set(COURT_NAMES)


def test_court_ids_are_not_shared_between_provinces():
    every = [c for courts in PROVINCE_COURTS.values() for c in courts]
    assert len(every) == len(set(every))


@pytest.mark.parametrize(
    "province,superior",
    [
        ("ON", "onsc"), ("QC", "qccs"), ("BC", "bcsc"), ("AB", "abkb"),
        ("SK", "skkb"), ("MB", "mbkb"), ("NS", "nssc"), ("NB", "nbkb"),
        ("NL", "nlsc"), ("PE", "pesctd"), ("YT", "yksc"), ("NT", "ntsc"),
        ("NU", "nucj"),
    ],
)
def test_superior_court_is_first(province, superior):
    """The superior court is where a class proceeding is started."""
    assert courts_for_province(province, include_federal=False)[0] == superior


def test_federal_court_is_included_by_default():
    """The Federal Court hears class actions against the federal Crown."""
    assert "fct" in courts_for_province("ON")
    assert "fct" not in courts_for_province("ON", include_federal=False)


def test_appeals_are_opt_in():
    with_appeals = courts_for_province("BC", include_appeals=True)
    assert "bcca" in with_appeals
    assert "fca" in with_appeals
    assert "bcca" not in courts_for_province("BC")


def test_province_lookup_is_case_insensitive():
    assert courts_for_province("on") == courts_for_province("ON")


def test_unknown_province_raises():
    with pytest.raises(KeyError):
        courts_for_province("XX")


def test_reverse_lookup_and_names():
    assert COURT_PROVINCE["onsc"] == "ON"
    assert COURT_PROVINCE["qccs"] == "QC"
    assert court_name("onsc") == "Ontario Superior Court of Justice"
    assert court_name("unknown") == "unknown"


def test_supported_provinces_sorted_by_name():
    names = [p["name"] for p in supported_provinces()]
    assert names == sorted(names)
    assert len(names) == 13
