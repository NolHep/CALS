"""Mapping between US locations and the federal courts that serve them.

Class actions are overwhelmingly filed in (or removed to) federal district
court, so "lawsuits in my area" is modelled here as "dockets in the federal
district courts whose territory covers my state".

Court identifiers are CourtListener court IDs (the same short slugs used by
the RECAP archive, e.g. ``cand`` for N.D. Cal.).
"""

from __future__ import annotations

# state/territory -> federal district court ids serving it
STATE_DISTRICT_COURTS: dict[str, tuple[str, ...]] = {
    "AL": ("alnd", "almd", "alsd"),
    "AK": ("akd",),
    "AZ": ("azd",),
    "AR": ("ared", "arwd"),
    "CA": ("cand", "cacd", "caed", "casd"),
    "CO": ("cod",),
    "CT": ("ctd",),
    "DE": ("ded",),
    "DC": ("dcd",),
    "FL": ("flsd", "flmd", "flnd"),
    "GA": ("gand", "gamd", "gasd"),
    "HI": ("hid",),
    "ID": ("idd",),
    "IL": ("ilnd", "ilcd", "ilsd"),
    "IN": ("innd", "insd"),
    "IA": ("iand", "iasd"),
    "KS": ("ksd",),
    "KY": ("kyed", "kywd"),
    "LA": ("laed", "lamd", "lawd"),
    "ME": ("med",),
    "MD": ("mdd",),
    "MA": ("mad",),
    "MI": ("mied", "miwd"),
    "MN": ("mnd",),
    "MS": ("msnd", "mssd"),
    "MO": ("moed", "mowd"),
    "MT": ("mtd",),
    "NE": ("ned",),
    "NV": ("nvd",),
    "NH": ("nhd",),
    "NJ": ("njd",),
    "NM": ("nmd",),
    "NY": ("nysd", "nyed", "nynd", "nywd"),
    "NC": ("nced", "ncmd", "ncwd"),
    "ND": ("ndd",),
    "OH": ("ohnd", "ohsd"),
    "OK": ("okwd", "oknd", "oked"),
    "OR": ("ord",),
    "PA": ("paed", "pamd", "pawd"),
    "RI": ("rid",),
    "SC": ("scd",),
    "SD": ("sdd",),
    "TN": ("tned", "tnmd", "tnwd"),
    "TX": ("txsd", "txnd", "txed", "txwd"),
    "UT": ("utd",),
    "VT": ("vtd",),
    "VA": ("vaed", "vawd"),
    "WA": ("wawd", "waed"),
    "WV": ("wvnd", "wvsd"),
    "WI": ("wied", "wiwd"),
    "WY": ("wyd",),
    "PR": ("prd",),
    "VI": ("vid",),
    "GU": ("gud",),
    "MP": ("nmid",),
}

# state/territory -> federal circuit court of appeals id
STATE_CIRCUIT_COURT: dict[str, str] = {}
_CIRCUITS: dict[str, tuple[str, ...]] = {
    "ca1": ("ME", "MA", "NH", "RI", "PR"),
    "ca2": ("CT", "NY", "VT"),
    "ca3": ("DE", "NJ", "PA", "VI"),
    "ca4": ("MD", "NC", "SC", "VA", "WV"),
    "ca5": ("LA", "MS", "TX"),
    "ca6": ("KY", "MI", "OH", "TN"),
    "ca7": ("IL", "IN", "WI"),
    "ca8": ("AR", "IA", "MN", "MO", "NE", "ND", "SD"),
    "ca9": ("AK", "AZ", "CA", "HI", "ID", "MT", "NV", "OR", "WA", "GU", "MP"),
    "ca10": ("CO", "KS", "NM", "OK", "UT", "WY"),
    "ca11": ("AL", "FL", "GA"),
    "cadc": ("DC",),
}
for _circuit, _states in _CIRCUITS.items():
    for _state in _states:
        STATE_CIRCUIT_COURT[_state] = _circuit

STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida",
    "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
    "VI": "U.S. Virgin Islands", "GU": "Guam",
    "MP": "Northern Mariana Islands",
}

# court id -> the state it sits in, derived from the table above
COURT_STATE: dict[str, str] = {
    court: state
    for state, courts in STATE_DISTRICT_COURTS.items()
    for court in courts
}


def courts_for_state(state: str, include_appeals: bool = False) -> list[str]:
    """Return the court ids covering ``state``.

    Raises ``KeyError`` if the state is not a US state or territory with a
    federal district court.
    """
    key = (state or "").strip().upper()
    if key not in STATE_DISTRICT_COURTS:
        raise KeyError(f"no federal district court known for {state!r}")
    courts = list(STATE_DISTRICT_COURTS[key])
    if include_appeals:
        circuit = STATE_CIRCUIT_COURT.get(key)
        if circuit:
            courts.append(circuit)
    return courts


def state_name(state: str) -> str:
    return STATE_NAMES.get((state or "").strip().upper(), state)


def supported_states() -> list[dict[str, str]]:
    """States/territories offered in the UI, alphabetical by name."""
    return sorted(
        (
            {"code": code, "name": STATE_NAMES.get(code, code)}
            for code in STATE_DISTRICT_COURTS
        ),
        key=lambda item: item["name"],
    )
