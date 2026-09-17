"""Interface every case source implements."""

from __future__ import annotations

from typing import Protocol

from ..models import SearchResult


class SearchQuery:
    def __init__(
        self,
        state: str,
        courts: list[str],
        keywords: str = "",
        topics: list[str] | None = None,
        filed_after: str | None = None,
        filed_before: str | None = None,
        min_confidence: float = 0.35,
        limit: int = 40,
    ) -> None:
        self.state = state
        self.courts = courts
        self.keywords = keywords
        self.topics = topics or []
        self.filed_after = filed_after
        self.filed_before = filed_before
        self.min_confidence = min_confidence
        self.limit = limit

    def cache_key_parts(self) -> tuple:
        return (
            self.state,
            tuple(sorted(self.courts)),
            self.keywords.strip().lower(),
            tuple(sorted(self.topics)),
            self.filed_after,
            self.filed_before,
            self.limit,
        )


class Source(Protocol):
    name: str

    def search(self, query: SearchQuery) -> SearchResult: ...
