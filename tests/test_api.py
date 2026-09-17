import httpx
import pytest
from fastapi.testclient import TestClient

from cals.app import create_app
from cals.config import Settings
from cals.sources.courtlistener import CourtListenerError, CourtListenerSource


@pytest.fixture
def client(tmp_path, cache, recap_payload):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=recap_payload)
    )
    source = CourtListenerSource(cache=cache, client=httpx.Client(transport=transport))
    settings = Settings(cache_path=str(tmp_path / "c.sqlite3"))
    return TestClient(create_app(settings=settings, source=source))


def test_health_reports_both_countries(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["countries"]["CA"]["source"] == "canlii"
    assert body["countries"]["US"]["source"] == "courtlistener"


def test_us_regions_endpoint(client):
    states = client.get("/api/regions", params={"country": "US"}).json()["regions"]
    assert len(states) == 55
    assert {"code": "CA", "name": "California"} in states


def test_canadian_regions_endpoint(client):
    provinces = client.get("/api/regions", params={"country": "CA"}).json()["regions"]
    assert len(provinces) == 13
    assert {"code": "ON", "name": "Ontario"} in provinces


def test_regions_defaults_to_canada(client):
    assert client.get("/api/regions").json()["country"] == "CA"


def test_unsupported_country_rejected(client):
    assert client.get(
        "/api/regions", params={"country": "MX"}
    ).status_code == 400


def test_topics_endpoint(client):
    topics = client.get("/api/topics").json()["topics"]
    assert any(t["key"] == "data_privacy" for t in topics)
    assert all(t["label"] for t in topics)


def test_search_by_zip(client):
    body = client.get("/api/search", params={"location": "94110"}).json()
    assert body["query"]["country"] == "US"
    assert body["query"]["region"] == "CA"
    assert body["query"]["region_name"] == "California"
    assert set(body["query"]["courts"]) == {"cand", "cacd", "caed", "casd"}
    assert len(body["cases"]) == 2


def test_search_by_state_name(client):
    body = client.get("/api/search", params={"location": "California"}).json()
    assert body["query"]["region"] == "CA"


def test_search_includes_appeals_when_asked(client):
    body = client.get(
        "/api/search",
        params={"location": "CA", "country": "US", "include_appeals": "true"},
    ).json()
    assert "ca9" in body["query"]["courts"]


def test_search_rejects_unknown_location(client):
    response = client.get("/api/search", params={"location": "banana"})
    assert response.status_code == 400
    assert "could not work out" in response.json()["detail"]


def test_search_requires_a_location(client):
    assert client.get("/api/search").status_code == 422


def test_days_is_validated(client):
    assert client.get(
        "/api/search", params={"location": "CA", "country": "US", "days": 0}
    ).status_code == 422
    assert client.get(
        "/api/search", params={"location": "CA", "country": "US", "days": 99999}
    ).status_code == 422


def test_filed_after_is_derived_from_days(client):
    body = client.get("/api/search", params={"location": "CA", "country": "US", "days": 90}).json()
    assert body["query"]["days"] == 90
    assert body["query"]["filed_after"].count("/") == 2


def test_strict_confidence_narrows_results(client):
    body = client.get(
        "/api/search", params={"location": "CA", "country": "US", "min_confidence": 0.6}
    ).json()
    assert [c["case_name"] for c in body["cases"]] == [
        "Weatherford v. Metabase, Inc."
    ]


def test_topic_filter_passes_through(client):
    body = client.get(
        "/api/search", params={"location": "CA", "country": "US", "topics": "antitrust"}
    ).json()
    assert body["query"]["topics"] == ["antitrust"]
    assert body["cases"], "topics narrow the upstream query, not the results"


def test_multiple_topics_are_parsed(client):
    body = client.get(
        "/api/search",
        params={"location": "CA", "country": "US", "topics": "antitrust, data_privacy ,"},
    ).json()
    assert body["query"]["topics"] == ["antitrust", "data_privacy"]


def test_rate_limit_surfaces_as_429(tmp_path, cache):
    transport = httpx.MockTransport(lambda r: httpx.Response(429, json={}))
    source = CourtListenerSource(cache=cache, client=httpx.Client(transport=transport))
    app = create_app(Settings(cache_path=str(tmp_path / "c.sqlite3")), source=source)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/search", params={"location": "CA", "country": "US"}
    )
    assert response.status_code == 429
    assert "COURTLISTENER_TOKEN" in response.json()["detail"]


def test_upstream_failure_surfaces_as_502(tmp_path, cache):
    transport = httpx.MockTransport(lambda r: httpx.Response(500, json={}))
    source = CourtListenerSource(cache=cache, client=httpx.Client(transport=transport))
    app = create_app(Settings(cache_path=str(tmp_path / "c.sqlite3")), source=source)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/search", params={"location": "CA", "country": "US"}
    )
    assert response.status_code == 502


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "CALS" in response.text


# ---------------------------------------------------------------- Canada ---


@pytest.fixture
def ca_client(tmp_path, cache):
    """A client whose Canadian source is a stubbed CanLII."""
    from cals.sources.canlii import CanLIISource

    listing = {
        "cases": [
            {
                "databaseId": "onsc",
                "caseId": {"en": "2026onsc1234"},
                "title": "Smith v. Rogers Communications Inc.",
                "citation": "2026 ONSC 1234",
            }
        ]
    }
    metadata = {
        "title": "Smith v. Rogers Communications Inc.",
        "citation": "2026 ONSC 1234",
        "decisionDate": "2026-08-14",
        "docketNumber": "CV-26-001234",
        "keywords": "class proceedings — certification — privacy breach",
        "url": "https://www.canlii.org/en/on/onsc/doc/2026/2026onsc1234.html",
    }

    def handler(request):
        if request.url.path.rstrip("/").endswith(("onsc", "fct", "onca", "fca")):
            return httpx.Response(200, json=listing)
        return httpx.Response(200, json=metadata)

    source = CanLIISource(
        cache=cache,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    app = create_app(
        Settings(cache_path=str(tmp_path / "ca.sqlite3")), canada_source=source
    )
    return TestClient(app)


def test_search_by_canadian_postal_code(ca_client):
    body = ca_client.get("/api/search", params={"location": "M5V 3A8"}).json()
    assert body["query"]["country"] == "CA"
    assert body["query"]["region"] == "ON"
    assert body["query"]["region_name"] == "Ontario"
    assert body["cases"]


def test_search_by_canadian_city(ca_client):
    body = ca_client.get("/api/search", params={"location": "Toronto"}).json()
    assert body["query"]["region"] == "ON"


def test_canadian_search_includes_the_federal_court(ca_client):
    body = ca_client.get("/api/search", params={"location": "Toronto"}).json()
    assert "onsc" in body["query"]["courts"]
    assert "fct" in body["query"]["courts"]


def test_federal_court_can_be_excluded(ca_client):
    body = ca_client.get(
        "/api/search", params={"location": "Toronto", "include_federal": "false"}
    ).json()
    assert "fct" not in body["query"]["courts"]


def test_canadian_result_is_normalized(ca_client):
    case = ca_client.get(
        "/api/search", params={"location": "M5V 3A8"}
    ).json()["cases"][0]
    assert case["source"] == "canlii"
    assert case["court"] == "Ontario Superior Court of Justice"
    assert case["state"] == "ON"
    assert case["date_filed"] == "2026-08-14"
    assert "data_privacy" in case["topics"]


def test_country_parameter_forces_canada(ca_client):
    """'CA' means California by default, but Canada when the country says so."""
    body = ca_client.get(
        "/api/search", params={"location": "ON", "country": "CA"}
    ).json()
    assert body["query"]["country"] == "CA"


def test_missing_canlii_key_returns_401(tmp_path, cache):
    from cals.sources.canlii import CanLIISource

    source = CanLIISource(cache=cache, api_key=None)
    app = create_app(
        Settings(cache_path=str(tmp_path / "k.sqlite3")), canada_source=source
    )
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/search", params={"location": "Toronto"}
    )
    assert response.status_code == 401
    assert "CANLII_API_KEY" in response.json()["detail"]
