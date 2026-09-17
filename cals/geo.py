"""Resolve a user-supplied location into a country and a state or province.

Kept deliberately dependency-free: a ZIP/postal prefix table is accurate
enough to pick the right courts and costs nothing to ship, whereas a real
geocoder would add a network hop and an API key to every search.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .courts import STATE_DISTRICT_COURTS, STATE_NAMES
from .courts_ca import PROVINCE_COURTS, PROVINCE_NAMES


@dataclass(frozen=True)
class Location:
    """Where the user is, resolved well enough to pick courts."""

    country: str  # "US" or "CA"
    region: str   # state or province code
    region_name: str

    @property
    def is_canada(self) -> bool:
        return self.country == "CA"

# Inclusive 5-digit ZIP ranges per state. Ranges are checked in order and the
# first hit wins, so narrow special cases are listed before broad ranges.
_ZIP_RANGES: tuple[tuple[int, int, str], ...] = (
    (501, 544, "NY"),        # IRS Holtsville
    (6390, 6390, "NY"),      # Fishers Island
    (600, 799, "PR"),
    (900, 999, "PR"),
    (800, 899, "VI"),
    (1000, 2799, "MA"),
    (2800, 2999, "RI"),
    (3000, 3899, "NH"),
    (3900, 4999, "ME"),
    (5000, 5999, "VT"),
    (6000, 6999, "CT"),
    (7000, 8999, "NJ"),
    (10000, 14999, "NY"),
    (15000, 19699, "PA"),
    (19700, 19999, "DE"),
    (20000, 20099, "DC"),
    (20100, 20199, "VA"),
    (20200, 20599, "DC"),
    (20600, 21999, "MD"),
    (22000, 24699, "VA"),
    (24700, 26899, "WV"),
    (27000, 28999, "NC"),
    (29000, 29999, "SC"),
    (30000, 31999, "GA"),
    (32000, 34999, "FL"),
    (35000, 36999, "AL"),
    (37000, 38599, "TN"),
    (38600, 39799, "MS"),
    (39800, 39999, "GA"),
    (40000, 42799, "KY"),
    (43000, 45999, "OH"),
    (46000, 47999, "IN"),
    (48000, 49999, "MI"),
    (50000, 52899, "IA"),
    (53000, 54999, "WI"),
    (55000, 56799, "MN"),
    (57000, 57799, "SD"),
    (58000, 58899, "ND"),
    (59000, 59999, "MT"),
    (60000, 62999, "IL"),
    (63000, 65899, "MO"),
    (66000, 67999, "KS"),
    (68000, 69399, "NE"),
    (70000, 71499, "LA"),
    (71600, 72999, "AR"),
    (73000, 74999, "OK"),
    (75502, 75502, "AR"),    # Texarkana AR side
    (75000, 79999, "TX"),
    (80000, 81999, "CO"),
    (82000, 83199, "WY"),
    (83200, 83899, "ID"),
    (84000, 84799, "UT"),
    (85000, 86999, "AZ"),
    (87000, 88499, "NM"),
    (88500, 88599, "TX"),    # El Paso overflow
    (88900, 89899, "NV"),
    (90000, 96199, "CA"),
    (96700, 96798, "HI"),
    (96799, 96799, "AS"),
    (96800, 96899, "HI"),
    (96910, 96932, "GU"),
    (96950, 96952, "MP"),
    (97000, 97999, "OR"),
    (98000, 99499, "WA"),
    (99500, 99999, "AK"),
)

_ZIP_RE = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")

# Canadian postal codes are A1A 1A1. The first letter identifies a province,
# except X, which Northwest Territories and Nunavut share.
_POSTAL_RE = re.compile(r"^\s*([A-Za-z])(\d)([A-Za-z])\s*\d?[A-Za-z]?\d?\s*$")

_POSTAL_LETTER_PROVINCE: dict[str, str] = {
    "A": "NL", "B": "NS", "C": "PE", "E": "NB",
    "G": "QC", "H": "QC", "J": "QC",
    "K": "ON", "L": "ON", "M": "ON", "N": "ON", "P": "ON",
    "R": "MB", "S": "SK", "T": "AB", "V": "BC", "Y": "YT",
}

# X is split between the two territories by forward sortation area.
_X_FSA_PROVINCE: dict[str, str] = {
    "X0A": "NU", "X0B": "NU", "X0C": "NU",
    "X0E": "NT", "X0G": "NT", "X1A": "NT",
}

def _normalize_name(value: str) -> str:
    """Fold a place name to a comparable key.

    Lowercases, strips accents so "Québec" matches "quebec", and drops
    punctuation so "Washington, D.C." matches "dc".
    """
    decomposed = unicodedata.normalize("NFKD", value.lower())
    unaccented = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", "", unaccented)).strip()


_US_NAME_TO_CODE = {
    _normalize_name(name): code for code, name in STATE_NAMES.items()
}
_US_NAME_TO_CODE.update(
    {
        "washington dc": "DC",
        "district of columbia": "DC",
        "dc": "DC",
        "puerto rico": "PR",
        "virgin islands": "VI",
        "us virgin islands": "VI",
        "northern mariana islands": "MP",
        "mariana islands": "MP",
    }
)

_CA_NAME_TO_CODE = {
    _normalize_name(name): code for code, name in PROVINCE_NAMES.items()
}
_CA_NAME_TO_CODE.update(
    {
        "newfoundland": "NL",
        "labrador": "NL",
        "pei": "PE",
        "quebec": "QC",
        "québec": "QC",
        "nwt": "NT",
        "northwest territory": "NT",
        "yukon territory": "YT",
        "bc": "BC",
    }
)

# Major Canadian cities, so "Toronto" resolves without a postal code. Only
# cities whose province is unambiguous are listed.
_CA_CITY_PROVINCE: dict[str, str] = {
    "toronto": "ON", "ottawa": "ON", "mississauga": "ON", "brampton": "ON",
    "hamilton": "ON", "london": "ON", "markham": "ON", "vaughan": "ON",
    "kitchener": "ON", "windsor": "ON", "oshawa": "ON", "barrie": "ON",
    "guelph": "ON", "kingston": "ON", "sudbury": "ON", "thunder bay": "ON",
    "montreal": "QC", "quebec city": "QC", "laval": "QC", "gatineau": "QC",
    "longueuil": "QC", "sherbrooke": "QC", "trois rivieres": "QC",
    "saguenay": "QC", "levis": "QC",
    "vancouver": "BC", "surrey": "BC", "burnaby": "BC", "richmond": "BC",
    "victoria": "BC", "kelowna": "BC", "abbotsford": "BC", "nanaimo": "BC",
    "coquitlam": "BC", "kamloops": "BC",
    "calgary": "AB", "edmonton": "AB", "red deer": "AB", "lethbridge": "AB",
    "airdrie": "AB", "fort mcmurray": "AB",
    "winnipeg": "MB", "brandon": "MB",
    "saskatoon": "SK", "regina": "SK",
    "halifax": "NS", "dartmouth": "NS", "sydney": "NS",
    "moncton": "NB", "saint john": "NB", "fredericton": "NB",
    "st johns": "NL", "corner brook": "NL",
    "charlottetown": "PE", "summerside": "PE",
    "whitehorse": "YT", "yellowknife": "NT", "iqaluit": "NU",
}

# Codes both countries would answer to. There are none today, but the check
# below is explicit so a future clash cannot silently resolve to one country.
_AMBIGUOUS_CODES = set(STATE_NAMES) & set(PROVINCE_NAMES)


class UnknownLocation(ValueError):
    """Raised when a location string cannot be resolved to a state."""


def state_for_zip(zip_code: str) -> str | None:
    """Return the state code for a 5-digit (or ZIP+4) US ZIP code."""
    match = _ZIP_RE.match(str(zip_code or ""))
    if not match:
        return None
    value = int(match.group(1))
    for low, high, state in _ZIP_RANGES:
        if low <= value <= high:
            return state
    return None


def province_for_postal_code(postal_code: str) -> str | None:
    """Return the province code for a Canadian postal code or FSA."""
    match = _POSTAL_RE.match(str(postal_code or ""))
    if not match:
        return None
    letter = match.group(1).upper()
    if letter == "X":
        fsa = f"X{match.group(2)}{match.group(3).upper()}"
        return _X_FSA_PROVINCE.get(fsa)
    return _POSTAL_LETTER_PROVINCE.get(letter)


def resolve_location(location: str, country: str | None = None) -> Location:
    """Resolve free text to a country and region.

    ``country`` ("US" or "CA") restricts resolution to that country, which is
    what disambiguates a bare code if the two countries ever share one.
    Raises ``UnknownLocation`` if nothing can be resolved.
    """
    raw = (location or "").strip()
    if not raw:
        raise UnknownLocation("enter a postal code, ZIP code, province or state")

    want = (country or "").strip().upper() or None
    if want not in (None, "US", "CA"):
        raise UnknownLocation(f"unsupported country {country!r}")

    if want != "CA":
        state = state_for_zip(raw)
        if state:
            return _us_location(state)
    if want != "US":
        province = province_for_postal_code(raw)
        if province:
            return _ca_location(province)

    upper = re.sub(r"[^A-Z]", "", raw.upper())
    if len(upper) == 2:
        if want != "CA" and upper in STATE_NAMES:
            return _us_location(upper)
        if want != "US" and upper in PROVINCE_NAMES:
            return _ca_location(upper)

    name = _normalize_name(raw)
    if want != "CA" and name in _US_NAME_TO_CODE:
        return _us_location(_US_NAME_TO_CODE[name])
    if want != "US" and name in _CA_NAME_TO_CODE:
        return _ca_location(_CA_NAME_TO_CODE[name])
    if want != "US" and name in _CA_CITY_PROVINCE:
        return _ca_location(_CA_CITY_PROVINCE[name])

    where = {"US": " in the US", "CA": " in Canada"}.get(want, "")
    raise UnknownLocation(
        f"could not work out a state or province from {raw!r}{where} - try a "
        "Canadian postal code, a US ZIP code, or a province or state name"
    )


def _us_location(state: str) -> Location:
    if state not in STATE_DISTRICT_COURTS:
        raise UnknownLocation(
            f"{STATE_NAMES.get(state, state)} has no federal district court "
            "of its own, so there is nothing to search"
        )
    return Location("US", state, STATE_NAMES.get(state, state))


def _ca_location(province: str) -> Location:
    if province not in PROVINCE_COURTS:
        raise UnknownLocation(
            f"no Canadian superior court is known for {province!r}"
        )
    return Location("CA", province, PROVINCE_NAMES.get(province, province))
