"""FastAPI application exposing the class action search."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .cache import Cache
from .classify import TOPICS
from .config import Settings
from .courts import courts_for_state, supported_states
from .courts_ca import courts_for_province, supported_provinces
from .geo import UnknownLocation, resolve_location
from .sources.base import SearchQuery
from .sources.canlii import CanLIIError, CanLIISource
from .sources.courtlistener import CourtListenerError, CourtListenerSource

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(
    settings: Settings | None = None,
    source=None,
    canada_source=None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    cache = Cache(settings.cache_path, settings.cache_ttl_seconds)

    us_source = source or CourtListenerSource(
        cache=cache,
        token=settings.courtlistener_token,
        base_url=settings.courtlistener_base,
        timeout=settings.request_timeout_seconds,
    )
    ca_source = canada_source or CanLIISource(
        cache=cache,
        api_key=settings.canlii_api_key,
        base_url=settings.canlii_base,
        language=settings.canlii_language,
        timeout=settings.request_timeout_seconds,
        metadata_budget=settings.canlii_metadata_budget,
    )

    app = FastAPI(
        title="CALS",
        description="Search class action lawsuits in Canada and the US.",
        version="0.2.0",
    )
    app.state.settings = settings
    app.state.cache = cache
    app.state.sources = {"US": us_source, "CA": ca_source}

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "countries": {
                "CA": {
                    "source": ca_source.name,
                    "configured": bool(settings.canlii_api_key),
                    "needs": "CANLII_API_KEY",
                },
                "US": {
                    "source": us_source.name,
                    "configured": bool(settings.courtlistener_token),
                    "needs": "COURTLISTENER_TOKEN",
                },
            },
        }

    @app.get("/api/regions")
    def regions(country: str = Query("CA")) -> dict:
        code = country.strip().upper()
        if code == "CA":
            return {"country": "CA", "regions": supported_provinces()}
        if code == "US":
            return {"country": "US", "regions": supported_states()}
        raise HTTPException(status_code=400, detail=f"unsupported country {country!r}")

    @app.get("/api/topics")
    def topics() -> dict:
        return {
            "topics": [{"key": t.key, "label": t.label} for t in TOPICS]
        }

    @app.get("/api/search")
    def search(
        location: str = Query(..., description="Postal code, ZIP, province or state"),
        country: str = Query("", description="'CA' or 'US'; inferred when blank"),
        keywords: str = Query(""),
        topics: str = Query(""),
        days: int = Query(365, ge=1, le=3650),
        min_confidence: float = Query(0.35, ge=0.0, le=1.0),
        include_appeals: bool = Query(False),
        include_federal: bool = Query(True, description="Canada: add the Federal Court"),
        limit: int = Query(40, ge=1, le=200),
    ) -> JSONResponse:
        try:
            place = resolve_location(location, country or None)
        except UnknownLocation as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if place.is_canada:
            courts = courts_for_province(
                place.region,
                include_appeals=include_appeals,
                include_federal=include_federal,
            )
        else:
            courts = courts_for_state(place.region, include_appeals=include_appeals)

        filed_after = (date.today() - timedelta(days=days)).strftime("%m/%d/%Y")
        topic_keys = [t.strip() for t in topics.split(",") if t.strip()]

        query = SearchQuery(
            state=place.region,
            courts=courts,
            keywords=keywords,
            topics=topic_keys,
            filed_after=filed_after,
            min_confidence=min_confidence,
            limit=min(limit, settings.max_results),
        )

        active = app.state.sources[place.country]
        try:
            result = active.search(query)
        except (CourtListenerError, CanLIIError) as exc:
            status = exc.status_code if exc.status_code in (401, 429) else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        payload = result.to_dict()
        payload["query"] = {
            "country": place.country,
            "region": place.region,
            "region_name": place.region_name,
            "courts": courts,
            "filed_after": filed_after,
            "days": days,
            "keywords": keywords,
            "topics": topic_keys,
            "min_confidence": min_confidence,
        }
        return JSONResponse(payload)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "index.html"))

    return app


app = create_app()
