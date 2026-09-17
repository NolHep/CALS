"""Normalized shapes returned by the API, independent of any upstream source."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Case:
    id: str
    source: str
    case_name: str
    court_id: str
    court: str
    state: str
    docket_number: str | None = None
    date_filed: str | None = None
    date_terminated: str | None = None
    nature_of_suit: str | None = None
    cause: str | None = None
    judge: str | None = None
    url: str | None = None
    parties: list[str] = field(default_factory=list)
    firms: list[str] = field(default_factory=list)
    latest_filing: str | None = None
    snippet: str | None = None
    confidence: float = 0.0
    confidence_reasons: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    cases: list[Case]
    total_available: int
    cached: bool
    source: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cases": [case.to_dict() for case in self.cases],
            "total_available": self.total_available,
            "cached": self.cached,
            "source": self.source,
            "notes": self.notes,
        }
