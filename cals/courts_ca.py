"""Mapping between Canadian locations and the courts that hear class actions.

Canada has no federal docket system comparable to PACER. Class actions are
started in each province's superior court, or in the Federal Court when the
defendant is the federal Crown. Court identifiers here are CanLII database
ids - the same codes CanLII uses in its URLs and neutral citations
(``2024 ONSC 1234`` lives in the ``onsc`` database).

These ids are maintained by hand and have NOT been verified against a live
CanLII API, which requires a key. Run ``scripts/verify_canlii_courts.py``
with your key to check them.
"""

from __future__ import annotations

# province/territory -> (superior court, court of appeal)
# The superior court is where a class proceeding is started.
PROVINCE_COURTS: dict[str, tuple[str, ...]] = {
    "AB": ("abkb", "abca"),
    "BC": ("bcsc", "bcca"),
    "MB": ("mbkb", "mbca"),
    "NB": ("nbkb", "nbca"),
    "NL": ("nlsc", "nlca"),
    "NS": ("nssc", "nsca"),
    "NT": ("ntsc", "ntca"),
    "NU": ("nucj", "nuca"),
    "ON": ("onsc", "onca"),
    "PE": ("pesctd", "peca"),
    "QC": ("qccs", "qcca"),
    "SK": ("skkb", "skca"),
    "YT": ("yksc", "ykca"),
}

# Courts of first instance - the ones that actually certify class proceedings.
SUPERIOR_COURT: dict[str, str] = {
    province: courts[0] for province, courts in PROVINCE_COURTS.items()
}

# The Federal Court has nationwide jurisdiction and hears class actions
# against the federal Crown, so it is relevant from any province.
FEDERAL_COURTS: tuple[str, ...] = ("fct", "fca")

PROVINCE_NAMES: dict[str, str] = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}

COURT_NAMES: dict[str, str] = {
    "abkb": "Court of King's Bench of Alberta",
    "abca": "Court of Appeal of Alberta",
    "bcsc": "Supreme Court of British Columbia",
    "bcca": "Court of Appeal for British Columbia",
    "mbkb": "Court of King's Bench of Manitoba",
    "mbca": "Court of Appeal of Manitoba",
    "nbkb": "Court of King's Bench of New Brunswick",
    "nbca": "Court of Appeal of New Brunswick",
    "nlsc": "Supreme Court of Newfoundland and Labrador",
    "nlca": "Court of Appeal of Newfoundland and Labrador",
    "nssc": "Supreme Court of Nova Scotia",
    "nsca": "Nova Scotia Court of Appeal",
    "ntsc": "Supreme Court of the Northwest Territories",
    "ntca": "Court of Appeal of the Northwest Territories",
    "nucj": "Nunavut Court of Justice",
    "nuca": "Court of Appeal of Nunavut",
    "onsc": "Ontario Superior Court of Justice",
    "onca": "Court of Appeal for Ontario",
    "pesctd": "Supreme Court of Prince Edward Island",
    "peca": "Prince Edward Island Court of Appeal",
    "qccs": "Superior Court of Quebec",
    "qcca": "Quebec Court of Appeal",
    "skkb": "Court of King's Bench for Saskatchewan",
    "skca": "Court of Appeal for Saskatchewan",
    "yksc": "Supreme Court of Yukon",
    "ykca": "Court of Appeal of Yukon",
    "fct": "Federal Court",
    "fca": "Federal Court of Appeal",
}

COURT_PROVINCE: dict[str, str] = {
    court: province
    for province, courts in PROVINCE_COURTS.items()
    for court in courts
}


def courts_for_province(
    province: str,
    include_appeals: bool = False,
    include_federal: bool = True,
) -> list[str]:
    """Return the CanLII database ids covering ``province``."""
    key = (province or "").strip().upper()
    if key not in PROVINCE_COURTS:
        raise KeyError(f"no Canadian superior court known for {province!r}")

    courts = [SUPERIOR_COURT[key]]
    if include_appeals:
        courts.append(PROVINCE_COURTS[key][1])
    if include_federal:
        courts.append(FEDERAL_COURTS[0])
        if include_appeals:
            courts.append(FEDERAL_COURTS[1])
    return courts


def province_name(province: str) -> str:
    return PROVINCE_NAMES.get((province or "").strip().upper(), province)


def court_name(court_id: str) -> str:
    return COURT_NAMES.get(court_id, court_id)


def supported_provinces() -> list[dict[str, str]]:
    return sorted(
        ({"code": code, "name": name} for code, name in PROVINCE_NAMES.items()),
        key=lambda item: item["name"],
    )
