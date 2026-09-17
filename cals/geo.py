"""Resolve a user-supplied location into a US state code.

Kept deliberately dependency-free: a ZIP prefix table is accurate enough to
pick the right federal district courts and costs nothing to ship, whereas a
real geocoder would add a network hop and an API key to every search.
"""

from __future__ import annotations

import re

from .courts import STATE_DISTRICT_COURTS, STATE_NAMES

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

def _normalize_name(value: str) -> str:
    """Lowercase and drop punctuation so "Washington, D.C." matches "dc"."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", "", value.lower())).strip()


_NAME_TO_CODE = {
    _normalize_name(name): code for code, name in STATE_NAMES.items()
}
_NAME_TO_CODE.update(
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


def resolve_location(location: str) -> str:
    """Resolve a ZIP code, state code, or state name to a state code.

    Raises ``UnknownLocation`` if it cannot be resolved, or resolves to a
    place with no federal district court of its own (American Samoa).
    """
    raw = (location or "").strip()
    if not raw:
        raise UnknownLocation("enter a ZIP code or state")

    state = state_for_zip(raw)
    if state is None:
        upper = raw.upper()
        if len(upper) == 2 and upper in STATE_NAMES:
            state = upper
        else:
            state = _NAME_TO_CODE.get(_normalize_name(raw))

    if state is None:
        raise UnknownLocation(
            f"could not work out a US state from {raw!r} - "
            "try a 5-digit ZIP code or a state name"
        )
    if state not in STATE_DISTRICT_COURTS:
        raise UnknownLocation(
            f"{STATE_NAMES.get(state, state)} has no federal district court "
            "of its own, so there is nothing to search"
        )
    return state
