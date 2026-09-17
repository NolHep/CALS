"""CourtListener / RECAP source.

CourtListener is the Free Law Project's archive of PACER records. It exposes
federal dockets, which is where class actions live, and its search endpoint
takes the same GET parameters as the website's front end.
"""

from __future__ import annotations

import hashlib
import json
import logging

import httpx

from ..cache import Cache
from ..classify import (
    TOPICS_BY_KEY,
    class_action_confidence,
    is_unlikely_class_action,
    topics_for,
)
from ..courts import COURT_STATE, state_name
from ..models import Case, SearchResult
from .base import SearchQuery

log = logging.getLogger(__name__)

# Phrases that make the upstream query select class-action-shaped dockets
# rather than every case in the district.
_CLASS_ACTION_QUERY = (
    '("class action" OR "similarly situated" OR "class certification")'
)

# Every result comes back because class-action language matched somewhere in
# the docket's full text, which is far more than the snippet we get to see.
# That match is real evidence, so it sets the floor; the locally visible
# signals in classify.py only add to it. Without this floor a genuine class
# action whose snippet happens to be the caption page would score 0 and be
# dropped.
_UPSTREAM_MATCH_CONFIDENCE = 0.35
_UPSTREAM_MATCH_REASON = "full-text search matched class action language"

# The API returns 20 results per page. Following a couple of pages fills a
# typical result list without burning the request budget.
_MAX_PAGES = 3


class CourtListenerError(RuntimeError):
    """Raised when the upstream API cannot serve a search."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CourtListenerSource:
    name = "courtlistener"

    def __init__(
        self,
        cache: Cache,
        token: str | None = None,
        base_url: str = "https://www.courtlistener.com/api/rest/v4",
        timeout: int = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.cache = cache
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    # -- request plumbing -------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "CALS/0.1"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def _fetch(self, params: dict[str, str]) -> dict:
        """Fetch the first page of a search."""
        return self._request(f"{self.base_url}/search/", params)

    def _fetch_url(self, url: str) -> dict:
        """Fetch a follow-on page from a cursor URL returned by the API."""
        return self._request(url, None)

    def _request(self, url: str, params: dict[str, str] | None) -> dict:
        key = "cl:" + hashlib.sha256(
            json.dumps([url, params], sort_keys=True).encode()
        ).hexdigest()

        cached = self.cache.get(key)
        if cached is not None:
            cached["_cached"] = True
            return cached

        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.get(url, params=params, headers=self._headers())
        except httpx.HTTPError as exc:
            raise CourtListenerError(
                f"could not reach CourtListener: {exc}"
            ) from exc
        finally:
            if self._client is None:
                client.close()

        if response.status_code == 429:
            raise CourtListenerError(
                "CourtListener rate limit reached. Anonymous use is capped at "
                "125 requests/day - set COURTLISTENER_TOKEN for 5,000/hour.",
                status_code=429,
            )
        if response.status_code in (401, 403):
            raise CourtListenerError(
                "CourtListener rejected the API token.",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise CourtListenerError(
                f"CourtListener returned HTTP {response.status_code}.",
                status_code=response.status_code,
            )

        payload = response.json()
        self.cache.set(key, payload)
        payload["_cached"] = False
        return payload

    # -- query building ---------------------------------------------------

    def _build_query_string(self, query: SearchQuery) -> str:
        clauses = [_CLASS_ACTION_QUERY]

        topic_terms: list[str] = []
        for key in query.topics:
            topic = TOPICS_BY_KEY.get(key)
            if topic:
                topic_terms.extend(f'"{term}"' for term in topic.query_terms)
        if topic_terms:
            clauses.append("(" + " OR ".join(topic_terms) + ")")

        keywords = query.keywords.strip()
        if keywords:
            clauses.append(f"({keywords})")

        return " AND ".join(clauses)

    def _build_params(self, query: SearchQuery) -> dict[str, str]:
        params = {
            "type": "r",
            "q": self._build_query_string(query),
            "order_by": "dateFiled desc",
            "court": " ".join(query.courts),
        }
        if query.filed_after:
            params["filed_after"] = query.filed_after
        if query.filed_before:
            params["filed_before"] = query.filed_before
        return params

    # -- normalization ----------------------------------------------------

    def _to_case(self, raw: dict, fallback_state: str) -> Case:
        court_id = str(raw.get("court_id") or "")
        confidence, reasons = class_action_confidence(raw)
        if confidence < _UPSTREAM_MATCH_CONFIDENCE and not is_unlikely_class_action(raw):
            confidence = _UPSTREAM_MATCH_CONFIDENCE
            reasons = [_UPSTREAM_MATCH_REASON, *reasons]

        documents = raw.get("recap_documents") or []
        latest = documents[0] if documents else {}

        absolute_url = raw.get("docket_absolute_url") or raw.get("absolute_url")
        url = (
            f"https://www.courtlistener.com{absolute_url}"
            if absolute_url and absolute_url.startswith("/")
            else absolute_url
        )

        docket_id = raw.get("docket_id") or raw.get("id")

        return Case(
            id=f"cl-{docket_id}",
            source=self.name,
            case_name=str(raw.get("caseName") or raw.get("case_name_full") or "Unnamed docket"),
            court_id=court_id,
            court=str(raw.get("court") or court_id),
            state=COURT_STATE.get(court_id, fallback_state),
            docket_number=raw.get("docketNumber"),
            date_filed=raw.get("dateFiled"),
            date_terminated=raw.get("dateTerminated"),
            nature_of_suit=raw.get("suitNature"),
            cause=raw.get("cause"),
            judge=raw.get("assignedTo"),
            url=url,
            parties=[str(p) for p in (raw.get("party") or [])][:8],
            firms=[str(f) for f in (raw.get("firm") or [])][:6],
            latest_filing=(
                latest.get("short_description") or latest.get("description") or None
            ),
            snippet=_clean_snippet(latest.get("snippet")),
            confidence=round(confidence, 2),
            confidence_reasons=reasons[:4],
            topics=topics_for(raw),
        )

    # -- public API -------------------------------------------------------

    def search(self, query: SearchQuery) -> SearchResult:
        params = self._build_params(query)
        payload = self._fetch(params)
        total_available = int(payload.get("count") or 0)
        cached = bool(payload.get("_cached"))

        raw_results = payload.get("results") or []
        notes: list[str] = []
        seen: set[str] = set()
        cases: list[Case] = []
        dropped = 0

        def absorb(results: list[dict]) -> None:
            nonlocal dropped
            for raw in results:
                case = self._to_case(raw, query.state)
                if case.id in seen:
                    continue
                seen.add(case.id)
                if case.confidence < query.min_confidence:
                    dropped += 1
                    continue
                # Topics were ANDed into the upstream query, so the archive
                # has already confirmed them against each docket's full text -
                # far more than the snippet topics_for() can see. Re-filtering
                # here would throw away real matches, so the topics a docket
                # carries stay as the ones actually visible in its text.
                cases.append(case)

        absorb(raw_results)

        # Follow the cursor until the caller's limit is satisfied.
        pages = 1
        next_url = payload.get("next")
        while len(cases) < query.limit and next_url and pages < _MAX_PAGES:
            try:
                payload = self._fetch_url(next_url)
            except CourtListenerError as exc:
                notes.append(f"Stopped paging early: {exc}")
                break
            absorb(payload.get("results") or [])
            cached = cached and bool(payload.get("_cached"))
            next_url = payload.get("next")
            pages += 1

        if dropped > 0:
            notes.append(
                f"{dropped} docket(s) did not meet the confidence threshold "
                "and were left out."
            )

        cases.sort(key=lambda c: (c.date_filed or "", c.confidence), reverse=True)

        return SearchResult(
            cases=cases[: query.limit],
            total_available=total_available,
            cached=cached,
            source=self.name,
            notes=notes,
        )


def _clean_snippet(snippet: str | None) -> str | None:
    """Strip the <mark> highlighting CourtListener adds to snippets."""
    if not snippet:
        return None
    text = str(snippet).replace("<mark>", "").replace("</mark>", "")
    text = " ".join(text.split())
    return text[:400] or None
