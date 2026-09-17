#!/usr/bin/env python3
"""Check cals/courts_ca.py against CanLII's live database list.

The Canadian court table is hand-maintained and was written without a CanLII
API key, so it has never been checked against the source. Run this with a key
to verify it:

    CANLII_API_KEY=... python3 scripts/verify_canlii_courts.py
"""

from __future__ import annotations

import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cals.courts_ca import COURT_NAMES, COURT_PROVINCE, FEDERAL_COURTS  # noqa: E402

BASE = "https://api.canlii.org/v1/caseBrowse"


def fetch_databases(api_key: str, language: str = "en") -> dict[str, str]:
    response = httpx.get(
        f"{BASE}/{language}/",
        params={"api_key": api_key},
        timeout=45,
        headers={"Accept": "application/json"},
    )
    if response.status_code in (401, 403):
        raise SystemExit("CanLII rejected the key. Check CANLII_API_KEY.")
    response.raise_for_status()
    payload = response.json()
    return {
        db["databaseId"]: db.get("name", "")
        for db in payload.get("caseDatabases", [])
    }


def main() -> int:
    api_key = os.environ.get("CANLII_API_KEY")
    if not api_key:
        raise SystemExit(
            "Set CANLII_API_KEY. Request a free key at "
            "https://developer.canlii.org/"
        )

    upstream = fetch_databases(api_key)
    if not upstream:
        print("CanLII returned no databases.")
        return 1

    ours = set(COURT_PROVINCE) | set(FEDERAL_COURTS)
    missing = sorted(ours - set(upstream))

    print(f"CanLII case databases: {len(upstream)}")
    print(f"courts in cals/courts_ca.py: {len(ours)}")

    if missing:
        print("\nNOT FOUND upstream - these ids are wrong:")
        for court in missing:
            print(f"  {court}  ({COURT_NAMES.get(court, '?')})")
        return 1

    print("\nAll court ids exist upstream:")
    for court in sorted(ours):
        print(f"  {court:8s} {upstream[court]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
