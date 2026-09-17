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


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["source"] == "courtlistener"


def test_states_endpoint(client):
    states = client.get("/api/states").json()["states"]
    assert len(states) == 55
    assert {"code": "CA", "name": "California"} in states


def test_topics_endpoint(client):
    topics = client.get("/api/topics").json()["topics"]
    assert any(t["key"] == "data_privacy" for t in topics)
    assert all(t["label"] for t in topics)


def test_search_by_zip(client):
    body = client.get("/api/search", params={"location": "94110"}).json()
    assert body["query"]["state"] == "CA"
    assert body["query"]["state_name"] == "California"
    assert set(body["query"]["courts"]) == {"cand", "cacd", "caed", "casd"}
    assert len(body["cases"]) == 2


def test_search_by_state_name(client):
    body = client.get("/api/search", params={"location": "California"}).json()
    assert body["query"]["state"] == "CA"


def test_search_includes_appeals_when_asked(client):
    body = client.get(
        "/api/search", params={"location": "CA", "include_appeals": "true"}
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
        "/api/search", params={"location": "CA", "days": 0}
    ).status_code == 422
    assert client.get(
        "/api/search", params={"location": "CA", "days": 99999}
    ).status_code == 422


def test_filed_after_is_derived_from_days(client):
    body = client.get("/api/search", params={"location": "CA", "days": 90}).json()
    assert body["query"]["days"] == 90
    assert body["query"]["filed_after"].count("/") == 2


def test_strict_confidence_narrows_results(client):
    body = client.get(
        "/api/search", params={"location": "CA", "min_confidence": 0.6}
    ).json()
    assert [c["case_name"] for c in body["cases"]] == [
        "Weatherford v. Metabase, Inc."
    ]


def test_topic_filter_passes_through(client):
    body = client.get(
        "/api/search", params={"location": "CA", "topics": "antitrust"}
    ).json()
    assert body["query"]["topics"] == ["antitrust"]
    assert body["cases"], "topics narrow the upstream query, not the results"


def test_multiple_topics_are_parsed(client):
    body = client.get(
        "/api/search",
        params={"location": "CA", "topics": "antitrust, data_privacy ,"},
    ).json()
    assert body["query"]["topics"] == ["antitrust", "data_privacy"]


def test_rate_limit_surfaces_as_429(tmp_path, cache):
    transport = httpx.MockTransport(lambda r: httpx.Response(429, json={}))
    source = CourtListenerSource(cache=cache, client=httpx.Client(transport=transport))
    app = create_app(Settings(cache_path=str(tmp_path / "c.sqlite3")), source=source)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/search", params={"location": "CA"}
    )
    assert response.status_code == 429
    assert "COURTLISTENER_TOKEN" in response.json()["detail"]


def test_upstream_failure_surfaces_as_502(tmp_path, cache):
    transport = httpx.MockTransport(lambda r: httpx.Response(500, json={}))
    source = CourtListenerSource(cache=cache, client=httpx.Client(transport=transport))
    app = create_app(Settings(cache_path=str(tmp_path / "c.sqlite3")), source=source)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/search", params={"location": "CA"}
    )
    assert response.status_code == 502


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "CALS" in response.text
