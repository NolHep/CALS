#!/usr/bin/env python3
"""Check cals/courts.py against CourtListener's live court list.

The court table is hand-maintained, so this exists to prove it still matches
upstream. Run it after editing the table:

    python3 scripts/verify_courts.py

Set COURTLISTENER_TOKEN to avoid the 125 requests/day anonymous limit.
"""

from __future__ import annotations

import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cals.courts import COURT_STATE  # noqa: E402

BASE = "https://www.courtlistener.com/api/rest/v4/courts/"


def fetch_district_courts(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "CALS/0.1"}
    if token:
        headers["Authorization"] = f"Token {token}"

    courts: dict[str, str] = {}
    url: str | None = f"{BASE}?jurisdiction=FD&fields=id,full_name"
    with httpx.Client(timeout=45, headers=headers) as client:
        while url:
            response = client.get(url)
            if response.status_code == 429:
                raise SystemExit(
                    "Rate limited. Set COURTLISTENER_TOKEN and try again."
                )
            response.raise_for_status()
            payload = response.json()
            for court in payload.get("results", []):
                courts[court["id"]] = court.get("full_name", "")
            url = payload.get("next")
    return courts


def main() -> int:
    upstream = fetch_district_courts(os.environ.get("COURTLISTENER_TOKEN"))
    if not upstream:
        print("No courts returned from upstream.")
        return 1

    unknown = sorted(set(COURT_STATE) - set(upstream))
    print(f"upstream federal district courts: {len(upstream)}")
    print(f"courts in cals/courts.py:          {len(COURT_STATE)}")

    if unknown:
        print("\nNOT FOUND upstream (check these):")
        for court in unknown:
            print(f"  {court}  -> {COURT_STATE[court]}")
        return 1

    print("\nAll court ids in cals/courts.py exist upstream.")
    for court in sorted(COURT_STATE):
        print(f"  {court:6s} {COURT_STATE[court]}  {upstream[court]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
