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
from .courts import courts_for_state, state_name, supported_states
from .geo import UnknownLocation, resolve_location
from .sources.base import SearchQuery
from .sources.courtlistener import CourtListenerError, CourtListenerSource

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Settings | None = None, source=None) -> FastAPI:
    settings = settings or Settings.from_env()
    cache = Cache(settings.cache_path, settings.cache_ttl_seconds)
    source = source or CourtListenerSource(
        cache=cache,
        token=settings.courtlistener_token,
        base_url=settings.courtlistener_base,
        timeout=settings.request_timeout_seconds,
    )

    app = FastAPI(
        title="CALS",
        description="Search federal class action lawsuits filed in your area.",
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.cache = cache
    app.state.source = source

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "source": source.name,
            "authenticated": bool(settings.courtlistener_token),
        }

    @app.get("/api/states")
    def states() -> dict:
        return {"states": supported_states()}

    @app.get("/api/topics")
    def topics() -> dict:
        return {
            "topics": [
                {"key": topic.key, "label": topic.label} for topic in TOPICS
            ]
        }

    @app.get("/api/search")
    def search(
        location: str = Query(..., description="ZIP code, state code or state name"),
        keywords: str = Query("", description="Extra full-text terms"),
        topics: str = Query("", description="Comma-separated topic keys"),
        days: int = Query(365, ge=1, le=3650, description="Look back this many days"),
        min_confidence: float = Query(0.35, ge=0.0, le=1.0),
        include_appeals: bool = Query(False),
        limit: int = Query(40, ge=1, le=200),
    ) -> JSONResponse:
        try:
            state = resolve_location(location)
        except UnknownLocation as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        courts = courts_for_state(state, include_appeals=include_appeals)
        filed_after = (date.today() - timedelta(days=days)).strftime("%m/%d/%Y")
        topic_keys = [t.strip() for t in topics.split(",") if t.strip()]

        query = SearchQuery(
            state=state,
            courts=courts,
            keywords=keywords,
            topics=topic_keys,
            filed_after=filed_after,
            min_confidence=min_confidence,
            limit=min(limit, settings.max_results),
        )

        try:
            result = source.search(query)
        except CourtListenerError as exc:
            status = 429 if exc.status_code == 429 else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        payload = result.to_dict()
        payload["query"] = {
            "state": state,
            "state_name": state_name(state),
            "courts": courts,
            "filed_after": filed_after,
            "days": days,
            "keywords": keywords,
            "topics": topic_keys,
            "min_confidence": min_confidence,
        }
        return JSONResponse(payload)

    if STATIC_DIR.is_dir():
        app.mount(
            "/static", StaticFiles(directory=str(STATIC_DIR)), name="static"
        )

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "index.html"))

    return app


app = create_app()
