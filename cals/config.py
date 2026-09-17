"""Runtime configuration, all overridable by environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # A free token from https://www.courtlistener.com/profile/api-token/
    # lifts the limit from 125 requests/day to 5,000/hour.
    courtlistener_token: str | None = None
    courtlistener_base: str = "https://www.courtlistener.com/api/rest/v4"
    cache_path: str = "cals-cache.sqlite3"
    cache_ttl_seconds: int = 3600
    request_timeout_seconds: int = 30
    max_results: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            courtlistener_token=os.environ.get("COURTLISTENER_TOKEN") or None,
            courtlistener_base=os.environ.get(
                "COURTLISTENER_BASE", cls.courtlistener_base
            ),
            cache_path=os.environ.get("CALS_CACHE_PATH", cls.cache_path),
            cache_ttl_seconds=_int_env("CALS_CACHE_TTL", cls.cache_ttl_seconds),
            request_timeout_seconds=_int_env(
                "CALS_TIMEOUT", cls.request_timeout_seconds
            ),
            max_results=_int_env("CALS_MAX_RESULTS", cls.max_results),
        )
