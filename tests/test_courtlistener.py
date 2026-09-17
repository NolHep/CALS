import httpx
import pytest

from cals.sources.base import SearchQuery
from cals.sources.courtlistener import CourtListenerError, CourtListenerSource


def make_source(cache, handler, token=None):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return CourtListenerSource(cache=cache, token=token, client=client)


def query(**kwargs):
    defaults = dict(state="CA", courts=["cand", "cacd"], filed_after="01/01/2026")
    defaults.update(kwargs)
    return SearchQuery(**defaults)


def test_search_normalizes_results(cache, recap_payload):
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    result = source.search(query())

    assert result.total_available == 523
    assert result.cached is False
    # the criminal case is filtered out, the two class actions survive
    assert len(result.cases) == 2

    top = result.cases[0]
    assert top.case_name == "Rorke-Giorgi v. Ulta Beauty, Inc"
    assert top.state == "CA"
    assert top.url == (
        "https://www.courtlistener.com/docket/74762551/rorke-giorgi-v-ulta-beauty-inc/"
    )
    assert top.id == "cl-74762551"


def test_results_are_sorted_newest_first(cache, recap_payload):
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    dates = [c.date_filed for c in source.search(query()).cases]
    assert dates == sorted(dates, reverse=True)


def test_upstream_match_sets_a_confidence_floor(cache, recap_payload):
    """A real class action whose snippet is just the caption page is kept."""
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    ulta = next(
        c for c in source.search(query()).cases if "Ulta" in c.case_name
    )
    assert ulta.confidence == 0.35
    assert "full-text search matched" in ulta.confidence_reasons[0]


def test_visible_evidence_scores_above_the_floor(cache, recap_payload):
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    metabase = next(
        c for c in source.search(query()).cases if "Metabase" in c.case_name
    )
    assert metabase.confidence > 0.35


def test_snippet_highlighting_is_stripped(cache, recap_payload):
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    metabase = next(
        c for c in source.search(query()).cases if "Metabase" in c.case_name
    )
    assert "<mark>" not in metabase.snippet
    assert "class action" in metabase.snippet


def test_min_confidence_filters_weak_matches(cache, recap_payload):
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    result = source.search(query(min_confidence=0.6))
    assert [c.case_name for c in result.cases] == ["Weatherford v. Metabase, Inc."]
    assert result.notes, "filtering should be reported to the caller"


def test_topics_constrain_upstream_not_local_results(cache, recap_payload):
    """Topics are ANDed into the upstream query, so results are not re-filtered.

    The archive matches topic terms against each docket's full text; the
    snippet we get back is a fraction of that. Re-filtering locally would
    discard genuine matches, so requested topics are recorded instead.
    """
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    result = source.search(query(topics=["antitrust"]))
    assert len(result.cases) == 2


def test_tags_show_only_what_is_visible_in_the_docket(cache, recap_payload):
    """A requested topic is not pinned onto every result.

    The upstream query confirmed it against full text we cannot see, but
    labelling a securities case "data breach" because that was the filter
    would misrepresent it to the reader.
    """
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    metabase = next(
        c
        for c in source.search(query(topics=["antitrust"])).cases
        if "Metabase" in c.case_name
    )
    assert metabase.topics == ["data_privacy"]
    assert "antitrust" not in metabase.topics


def test_limit_is_respected(cache, recap_payload):
    source = make_source(cache, lambda r: httpx.Response(200, json=recap_payload))
    assert len(source.search(query(limit=1)).cases) == 1


def test_request_parameters(cache, recap_payload):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=recap_payload)

    source = make_source(cache, handler, token="secret")
    source.search(query(keywords="Acme", topics=["data_privacy"]))

    assert seen["params"]["type"] == "r"
    assert seen["params"]["court"] == "cand cacd"
    assert seen["params"]["filed_after"] == "01/01/2026"
    assert seen["params"]["order_by"] == "dateFiled desc"
    assert '"class action"' in seen["params"]["q"]
    assert '"data breach"' in seen["params"]["q"]
    assert "(Acme)" in seen["params"]["q"]
    assert seen["auth"] == "Token secret"


def test_no_token_means_no_auth_header(cache, recap_payload):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=recap_payload)

    make_source(cache, handler).search(query())
    assert seen["auth"] is None


def test_second_identical_search_is_served_from_cache(cache, recap_payload):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=recap_payload)

    source = make_source(cache, handler)
    assert source.search(query()).cached is False
    assert source.search(query()).cached is True
    assert calls["n"] == 1, "the second search must not hit the network"


def test_rate_limit_is_reported_clearly(cache):
    source = make_source(
        cache, lambda r: httpx.Response(429, json={"detail": "throttled"})
    )
    with pytest.raises(CourtListenerError) as excinfo:
        source.search(query())
    assert excinfo.value.status_code == 429
    assert "COURTLISTENER_TOKEN" in str(excinfo.value)


@pytest.mark.parametrize("status", [401, 403])
def test_bad_token_is_reported(cache, status):
    source = make_source(cache, lambda r: httpx.Response(status, json={}))
    with pytest.raises(CourtListenerError, match="rejected the API token"):
        source.search(query())


def test_server_error_is_wrapped(cache):
    source = make_source(cache, lambda r: httpx.Response(500, json={}))
    with pytest.raises(CourtListenerError, match="HTTP 500"):
        source.search(query())


def test_network_failure_is_wrapped(cache):
    def handler(request):
        raise httpx.ConnectError("no route to host")

    with pytest.raises(CourtListenerError, match="could not reach CourtListener"):
        make_source(cache, handler).search(query())


def test_empty_results_are_handled(cache):
    source = make_source(
        cache, lambda r: httpx.Response(200, json={"count": 0, "results": []})
    )
    result = source.search(query())
    assert result.cases == []
    assert result.total_available == 0


def test_pagination_follows_the_cursor_to_fill_the_limit(cache, recap_payload):
    """Each upstream page holds 20 results, so a bigger limit needs paging."""
    page_two = {
        "count": 523,
        "next": None,
        "results": [
            dict(recap_payload["results"][1], docket_id=555, caseName="Page Two Co.")
        ],
    }
    page_one = dict(recap_payload, next="https://example.test/next-cursor")
    pages = {"n": 0}

    def handler(request):
        pages["n"] += 1
        return httpx.Response(200, json=page_one if pages["n"] == 1 else page_two)

    source = make_source(cache, handler)
    names = [c.case_name for c in source.search(query(limit=40)).cases]
    assert "Page Two Co." in names
    assert pages["n"] == 2


def test_pagination_stops_once_the_limit_is_met(cache, recap_payload):
    pages = {"n": 0}

    def handler(request):
        pages["n"] += 1
        return httpx.Response(
            200, json=dict(recap_payload, next="https://example.test/next")
        )

    source = make_source(cache, handler)
    source.search(query(limit=2))
    assert pages["n"] == 1, "no extra request once the limit is satisfied"


def test_pagination_is_capped(cache, recap_payload):
    pages = {"n": 0}

    def handler(request):
        pages["n"] += 1
        return httpx.Response(
            200,
            json={
                "count": 999,
                "next": f"https://example.test/p{pages['n']}",
                "results": [
                    dict(recap_payload["results"][1], docket_id=1000 + pages["n"])
                ],
            },
        )

    source = make_source(cache, handler)
    source.search(query(limit=200))
    assert pages["n"] == 3, "paging must not run away"


def test_duplicate_dockets_are_not_repeated(cache, recap_payload):
    def handler(request):
        return httpx.Response(200, json=dict(recap_payload, next=None))

    source = make_source(cache, handler)
    ids = [c.id for c in source.search(query(limit=40)).cases]
    assert len(ids) == len(set(ids))


def test_cached_is_false_when_a_later_page_is_fetched_live(cache, recap_payload):
    """A cached first page plus a live second page is not a cached result."""

    def handler(request):
        if "cursor" in str(request.url):
            return httpx.Response(200, json={"count": 523, "results": []})
        return httpx.Response(
            200, json=dict(recap_payload, next="https://example.test/?cursor=x")
        )

    source = make_source(cache, handler)
    # a small limit is satisfied by page one alone, which caches only that page
    assert source.search(query(limit=2)).cached is False
    assert source.search(query(limit=2)).cached is True

    # a larger limit reuses the cached page one but fetches page two live
    assert source.search(query(limit=40)).cached is False


def test_fully_cached_paged_search_reports_cached(cache, recap_payload):
    def handler(request):
        if "cursor" in str(request.url):
            return httpx.Response(200, json={"count": 523, "results": []})
        return httpx.Response(
            200, json=dict(recap_payload, next="https://example.test/?cursor=x")
        )

    source = make_source(cache, handler)
    source.search(query(limit=40))
    assert source.search(query(limit=40)).cached is True
