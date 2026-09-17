"""CanLII source for Canadian class actions.

CanLII is the Canadian Legal Information Institute's free archive of
decisions from every Canadian court. It is the only sanctioned programmatic
source for Canadian court data: the CBA's class action database disallows
automated access in robots.txt, and the Quebec registry is behind a bot
challenge.

Two consequences shape this adapter, and both are visible to the user:

1. CanLII indexes *decisions*, not filings. Canada has no PACER, so a newly
   filed class action appears here only once a judge writes something about
   it - typically a certification or authorization ruling. This finds active
   class proceedings, not brand-new complaints.

2. The API has no full-text search. It browses a court's decisions by date
   and returns titles, then exposes editorial ``keywords`` one case at a
   time. So the strategy is: list a date window cheaply, then spend a
   bounded budget of metadata lookups to read keywords, newest first.
   Results are therefore a bounded scan, not an exhaustive one.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

import httpx

from ..cache import Cache
from ..classify import (
    class_action_confidence_ca,
    is_unlikely_class_action_ca,
    topics_for_ca,
)
from ..courts_ca import COURT_PROVINCE, court_name
from ..models import Case, SearchResult
from .base import SearchQuery

log = logging.getLogger(__name__)

# Metadata lookups cost one request each, so the scan is capped. Cached
# lookups do not count against it, so repeat searches reach further back.
DEFAULT_METADATA_BUDGET = 120

# How many decisions to list per court before filtering.
LIST_PAGE_SIZE = 100


class CanLIIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CanLIISource:
    name = "canlii"

    def __init__(
        self,
        cache: Cache,
        api_key: str | None = None,
        base_url: str = "https://api.canlii.org/v1",
        language: str = "en",
        timeout: int = 30,
        metadata_budget: int = DEFAULT_METADATA_BUDGET,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache = cache
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.language = language
        self.timeout = timeout
        self.metadata_budget = metadata_budget
        self._client = client

    # -- request plumbing -------------------------------------------------

    def _request(self, path: str, params: dict[str, str] | None = None) -> dict:
        if not self.api_key:
            raise CanLIIError(
                "A CanLII API key is required to search Canadian courts. "
                "Request a free key at https://developer.canlii.org/ and set "
                "CANLII_API_KEY.",
                status_code=401,
            )

        query = dict(params or {})
        query["api_key"] = self.api_key
        url = f"{self.base_url}{path}"

        # The key is an credential, so it must never become part of the
        # cache key that gets written to disk.
        cache_key = "canlii:" + hashlib.sha256(
            json.dumps([url, params], sort_keys=True).encode()
        ).hexdigest()
        cached = self.cache.get(cache_key)
        if cached is not None:
            cached["_cached"] = True
            return cached

        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.get(
                url, params=query, headers={"Accept": "application/json"}
            )
        except httpx.HTTPError as exc:
            raise CanLIIError(f"could not reach CanLII: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if response.status_code in (401, 403):
            raise CanLIIError(
                "CanLII rejected the API key. Check CANLII_API_KEY.",
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise CanLIIError(
                "CanLII rate limit reached. Try again shortly.", status_code=429
            )
        if response.status_code >= 400:
            raise CanLIIError(
                f"CanLII returned HTTP {response.status_code}.",
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise CanLIIError("CanLII returned a non-JSON response.") from exc

        self.cache.set(cache_key, payload)
        payload["_cached"] = False
        return payload

    def _list_decisions(
        self, court_id: str, after: str | None, before: str | None
    ) -> dict:
        params: dict[str, str] = {
            "offset": "0",
            "resultCount": str(LIST_PAGE_SIZE),
        }
        if after:
            params["decisionDateAfter"] = after
        if before:
            params["decisionDateBefore"] = before
        return self._request(
            f"/caseBrowse/{self.language}/{court_id}/", params
        )

    def _case_metadata(self, court_id: str, case_id: str) -> dict:
        return self._request(
            f"/caseBrowse/{self.language}/{court_id}/{case_id}/"
        )

    # -- normalization ----------------------------------------------------

    @staticmethod
    def _case_id_of(entry: dict) -> str | None:
        """Pull the case id out of a list entry.

        The list endpoint returns caseId as a language-keyed object, e.g.
        {"en": "2024onsc1234"}, but a bare string turns up too.
        """
        raw = entry.get("caseId")
        if isinstance(raw, str):
            return raw or None
        if isinstance(raw, dict):
            for key in (raw.get("en"), raw.get("fr")):
                if key:
                    return str(key)
            for value in raw.values():
                if value:
                    return str(value)
        return None

    def _to_case(self, court_id: str, entry: dict, metadata: dict | None) -> Case:
        merged = dict(entry)
        if metadata:
            merged.update({k: v for k, v in metadata.items() if v not in (None, "")})

        confidence, reasons = class_action_confidence_ca(merged)
        case_id = self._case_id_of(entry) or ""
        province = COURT_PROVINCE.get(court_id, "")

        url = merged.get("url")
        if not url and case_id:
            url = (
                f"https://www.canlii.org/{self.language}/"
                f"{_jurisdiction_path(court_id, province)}/{court_id}/doc/{case_id}.html"
            )

        return Case(
            id=f"canlii-{court_id}-{case_id}",
            source=self.name,
            case_name=str(merged.get("title") or "Untitled decision"),
            court_id=court_id,
            court=court_name(court_id),
            state=province or ("CA" if court_id in ("fct", "fca") else ""),
            docket_number=merged.get("docketNumber"),
            date_filed=merged.get("decisionDate"),
            nature_of_suit=None,
            cause=merged.get("citation"),
            url=url,
            latest_filing=merged.get("citation"),
            snippet=_keywords_snippet(merged.get("keywords")),
            confidence=round(confidence, 2),
            confidence_reasons=reasons[:4],
            topics=topics_for_ca(merged),
        )

    # -- public API -------------------------------------------------------

    def search(self, query: SearchQuery) -> SearchResult:
        after = _to_iso(query.filed_after)
        before = _to_iso(query.filed_before)

        notes: list[str] = []
        cases: list[Case] = []
        seen: set[str] = set()
        cached_all = True
        budget = self.metadata_budget
        budget_hit = False

        for court_id in query.courts:
            listing = self._list_decisions(court_id, after, before)
            cached_all = cached_all and bool(listing.get("_cached"))
            entries = listing.get("cases") or []

            for entry in entries:
                case_id = self._case_id_of(entry)
                if not case_id:
                    continue
                # CanLII case ids embed year and court ("2026onsc1234"), so
                # they are unique across databases. Deduplicating on the id
                # alone stops one decision appearing twice when a court is
                # reachable by more than one route.
                if case_id in seen:
                    continue
                seen.add(case_id)

                # A criminal style of cause is never a class proceeding, so
                # rule it out from the title and keep the lookup budget for
                # decisions that might actually qualify.
                if is_unlikely_class_action_ca(entry):
                    continue

                # The title alone sometimes settles it; otherwise spend a
                # metadata lookup to read CanLII's editorial keywords.
                title_only = self._to_case(court_id, entry, None)
                metadata = None
                if title_only.confidence < query.min_confidence:
                    if budget <= 0:
                        budget_hit = True
                        continue
                    budget -= 1
                    try:
                        metadata = self._case_metadata(court_id, case_id)
                    except CanLIIError as exc:
                        notes.append(f"Stopped reading case details: {exc}")
                        budget = 0
                        continue
                    cached_all = cached_all and bool(metadata.get("_cached"))

                case = (
                    self._to_case(court_id, entry, metadata)
                    if metadata
                    else title_only
                )
                if case.confidence < query.min_confidence:
                    continue
                if query.topics and not set(case.topics) & set(query.topics):
                    continue
                cases.append(case)

        if budget_hit:
            notes.append(
                f"Checked the {self.metadata_budget} most recent decisions per "
                "search. Narrow the date range to look further back."
            )

        cases.sort(key=lambda c: (c.date_filed or "", c.confidence), reverse=True)

        return SearchResult(
            cases=cases[: query.limit],
            total_available=len(cases),
            cached=cached_all and bool(cases),
            source=self.name,
            notes=notes,
        )


def _jurisdiction_path(court_id: str, province: str) -> str:
    if court_id in ("fct", "fca"):
        return "ca"
    return province.lower() if province else "ca"


def _to_iso(value: str | None) -> str | None:
    """Accept MM/DD/YYYY (the CourtListener style) or ISO, return ISO."""
    if not value:
        return None
    text = str(value).strip()
    if "/" in text:
        try:
            month, day, year = (int(p) for p in text.split("/"))
            return date(year, month, day).isoformat()
        except (ValueError, TypeError):
            return None
    return text


def _keywords_snippet(keywords: object) -> str | None:
    """CanLII keywords arrive as a '—'-separated string; tidy it for display."""
    if not keywords:
        return None
    text = str(keywords)
    parts = [p.strip() for p in text.replace("—", "—").split("—")]
    parts = [p for p in parts if p]
    return "; ".join(parts)[:400] or None
