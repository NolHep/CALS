import httpx
import pytest

from cals.sources.base import SearchQuery
from cals.sources.canlii import CanLIIError, CanLIISource

LIST_PATH = "/caseBrowse/en/onsc/"


def make_source(cache, handler, api_key="key-123", **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return CanLIISource(cache=cache, api_key=api_key, client=client, **kwargs)


def query(**kwargs):
    defaults = dict(state="ON", courts=["onsc"], filed_after="01/01/2026")
    defaults.update(kwargs)
    return SearchQuery(**defaults)


def listing(*cases):
    return {"cases": list(cases)}


CLASS_ACTION = {
    "databaseId": "onsc",
    "caseId": {"en": "2026onsc1234"},
    "title": "Smith v. Rogers Communications Inc.",
    "citation": "2026 ONSC 1234",
}
CRIMINAL = {
    "databaseId": "onsc",
    "caseId": {"en": "2026onsc9999"},
    "title": "R. v. Smith",
    "citation": "2026 ONSC 9999",
}
METADATA = {
    "databaseId": "onsc",
    "caseId": "2026onsc1234",
    "title": "Smith v. Rogers Communications Inc.",
    "citation": "2026 ONSC 1234",
    "docketNumber": "CV-26-001234",
    "decisionDate": "2026-08-14",
    "keywords": "class proceedings — certification — privacy breach",
    "url": "https://www.canlii.org/en/on/onsc/doc/2026/2026onsc1234/2026onsc1234.html",
}


def routed(list_payload, metadata=METADATA, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(str(request.url.path))
        if request.url.path.rstrip("/").endswith(("onsc", "qccs", "fct")):
            return httpx.Response(200, json=list_payload)
        return httpx.Response(200, json=metadata)

    return handler


# -- key handling ---------------------------------------------------------


def test_missing_api_key_is_reported_clearly(cache):
    source = CanLIISource(cache=cache, api_key=None)
    with pytest.raises(CanLIIError) as excinfo:
        source.search(query())
    assert excinfo.value.status_code == 401
    assert "CANLII_API_KEY" in str(excinfo.value)
    assert "developer.canlii.org" in str(excinfo.value)


def test_api_key_is_sent_as_a_query_parameter(cache):
    seen = {}

    def handler(request):
        seen.setdefault("keys", []).append(request.url.params.get("api_key"))
        return httpx.Response(200, json=listing())

    make_source(cache, handler).search(query())
    assert seen["keys"] == ["key-123"]


def test_api_key_is_never_written_into_the_cache_key(cache):
    """Two different keys must share cache entries, and neither may leak in."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=listing(CLASS_ACTION))

    make_source(cache, handler, api_key="key-a").search(query())
    after_first = calls["n"]
    make_source(cache, handler, api_key="key-b").search(query())
    assert calls["n"] == after_first, "a different key must still hit the cache"

    stored = " ".join(
        row[0] for row in cache._conn.execute("SELECT key FROM responses")
    )
    assert "key-a" not in stored and "key-b" not in stored


# -- searching ------------------------------------------------------------


def test_finds_a_class_proceeding_from_its_keywords(cache):
    source = make_source(cache, routed(listing(CLASS_ACTION)))
    result = source.search(query())
    assert len(result.cases) == 1

    case = result.cases[0]
    assert case.case_name == "Smith v. Rogers Communications Inc."
    assert case.court == "Ontario Superior Court of Justice"
    assert case.state == "ON"
    assert case.date_filed == "2026-08-14"
    assert case.docket_number == "CV-26-001234"
    assert case.url == METADATA["url"]
    assert case.id == "canlii-onsc-2026onsc1234"
    assert "data_privacy" in case.topics
    assert case.confidence >= 0.6


def test_criminal_decisions_are_excluded_without_a_metadata_lookup(cache):
    """A criminal cause must not burn a lookup from the metadata budget."""
    calls = []
    source = make_source(cache, routed(listing(CRIMINAL), calls=calls))
    assert source.search(query()).cases == []
    # only the listing call - "R. v." is settled from the title alone
    assert len(calls) == 1


def test_quebec_french_terminology_is_recognised(cache):
    french_list = {
        "cases": [
            {
                "databaseId": "qccs",
                "caseId": {"fr": "2026qccs555"},
                "title": "Tremblay c. Banque Nationale",
                "citation": "2026 QCCS 555",
            }
        ]
    }
    french_meta = {
        "title": "Tremblay c. Banque Nationale",
        "citation": "2026 QCCS 555",
        "decisionDate": "2026-07-02",
        "keywords": "action collective — autorisation — protection du consommateur",
    }
    source = make_source(cache, routed(french_list, metadata=french_meta))
    result = source.search(query(state="QC", courts=["qccs"]))
    assert len(result.cases) == 1
    assert "consumer" in result.cases[0].topics
    assert result.cases[0].confidence >= 0.6


def test_case_id_accepts_a_bare_string(cache):
    entry = dict(CLASS_ACTION, caseId="2026onsc1234")
    source = make_source(cache, routed(listing(entry)))
    assert source.search(query()).cases[0].id == "canlii-onsc-2026onsc1234"


def test_entries_without_a_case_id_are_skipped(cache):
    source = make_source(cache, routed(listing({"title": "No id here"})))
    assert source.search(query()).cases == []


def test_several_courts_are_each_listed(cache):
    calls = []
    source = make_source(cache, routed(listing(), calls=calls))
    source.search(query(courts=["onsc", "fct"]))
    assert len([c for c in calls if c.endswith(("onsc/", "fct/"))]) == 2


def test_duplicate_cases_are_not_repeated(cache):
    source = make_source(cache, routed(listing(CLASS_ACTION, CLASS_ACTION)))
    assert len(source.search(query()).cases) == 1


def test_date_range_is_converted_to_iso(cache):
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=listing())

    make_source(cache, handler).search(query(filed_after="03/09/2026"))
    assert seen["decisionDateAfter"] == "2026-03-09"


def test_iso_dates_pass_through(cache):
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=listing())

    make_source(cache, handler).search(query(filed_after="2026-03-09"))
    assert seen["decisionDateAfter"] == "2026-03-09"


def test_topic_filter_applies(cache):
    source = make_source(cache, routed(listing(CLASS_ACTION)))
    assert source.search(query(topics=["antitrust"])).cases == []
    assert len(source.search(query(topics=["data_privacy"])).cases) == 1


def test_limit_is_respected(cache):
    second = dict(CLASS_ACTION, caseId={"en": "2026onsc4321"})
    source = make_source(cache, routed(listing(CLASS_ACTION, second)))
    assert len(source.search(query(limit=1)).cases) == 1


# -- budget ---------------------------------------------------------------


def test_metadata_budget_caps_the_scan(cache):
    entries = [
        dict(CLASS_ACTION, caseId={"en": f"2026onsc{i}"}, title=f"Case {i} v. Co")
        for i in range(10)
    ]
    calls = []
    source = make_source(
        cache, routed(listing(*entries), calls=calls), metadata_budget=3
    )
    result = source.search(query())
    metadata_calls = [c for c in calls if not c.rstrip("/").endswith("onsc")]
    assert len(metadata_calls) == 3
    assert any("most recent decisions" in n for n in result.notes)


def test_budget_is_not_spent_on_titles_that_already_decide(cache):
    """A title containing the words needs no lookup."""
    obvious = dict(
        CLASS_ACTION, title="Doe v. Acme (class proceeding certification)"
    )
    calls = []
    source = make_source(cache, routed(listing(obvious), calls=calls))
    result = source.search(query())
    assert len(result.cases) == 1
    assert len(calls) == 1, "no metadata lookup needed"


# -- errors ---------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_bad_key_is_reported(cache, status):
    source = make_source(cache, lambda r: httpx.Response(status, json={}))
    with pytest.raises(CanLIIError, match="rejected the API key"):
        source.search(query())


def test_rate_limit_is_reported(cache):
    source = make_source(cache, lambda r: httpx.Response(429, json={}))
    with pytest.raises(CanLIIError) as excinfo:
        source.search(query())
    assert excinfo.value.status_code == 429


def test_server_error_is_wrapped(cache):
    source = make_source(cache, lambda r: httpx.Response(500, json={}))
    with pytest.raises(CanLIIError, match="HTTP 500"):
        source.search(query())


def test_non_json_response_is_wrapped(cache):
    source = make_source(cache, lambda r: httpx.Response(200, text="<html>"))
    with pytest.raises(CanLIIError, match="non-JSON"):
        source.search(query())


def test_network_failure_is_wrapped(cache):
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(CanLIIError, match="could not reach CanLII"):
        make_source(cache, handler).search(query())


def test_repeat_search_is_cached(cache):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=listing(CLASS_ACTION))

    source = make_source(cache, handler)
    source.search(query())
    before = calls["n"]
    source.search(query())
    assert calls["n"] == before, "a repeat search must not hit the network"


def test_the_same_decision_is_not_listed_twice_across_courts(cache):
    """One decision reachable via two courts must appear once."""
    def handler(request):
        last = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        if last in ("onsc", "fct"):
            return httpx.Response(200, json=listing(CLASS_ACTION))
        return httpx.Response(200, json=METADATA)

    source = make_source(cache, handler)
    result = source.search(query(courts=["onsc", "fct"]))
    assert len(result.cases) == 1
    assert len({c.id for c in result.cases}) == 1
