"""Decide whether a federal docket looks like a class action, and what it is about.

PACER has no "is this a class action" flag, so this has to be inferred. The
strongest signal is the language parties use in their own filings ("Class
Action Complaint", "on behalf of all others similarly situated"), backed up
by the JS-44 nature-of-suit code the plaintiff selected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Phrases that appear in class action captions and complaint titles. Weights
# are rough confidence contributions, capped later at 1.0.
_STRONG_PHRASES: tuple[tuple[str, float], ...] = (
    ("class action complaint", 0.60),
    ("similarly situated", 0.55),
    ("putative class", 0.50),
    ("class action", 0.45),
    ("motion to certify class", 0.50),
    ("motion for class certification", 0.50),
    ("class certification", 0.40),
    ("collective action", 0.35),
    ("on behalf of all others", 0.45),
    ("rule 23", 0.35),
    ("class representative", 0.30),
    ("settlement class", 0.35),
)

# JS-44 nature-of-suit codes that class actions cluster in. A code alone is
# weak evidence, so these stay well below the certainty threshold.
_NOS_WEIGHTS: dict[str, float] = {
    "410": 0.20,  # Antitrust
    "440": 0.10,  # Other Civil Rights
    "442": 0.10,  # Civil Rights: Employment
    "470": 0.15,  # Racketeer Influenced and Corrupt Organizations
    "480": 0.20,  # Consumer Credit
    "710": 0.20,  # Fair Labor Standards Act
    "791": 0.15,  # ERISA
    "850": 0.20,  # Securities / Commodities / Exchange
    "890": 0.10,  # Other Statutory Actions
    "370": 0.15,  # Other Fraud
    "365": 0.10,  # Personal Injury: Product Liability
    "245": 0.10,  # Tort Product Liability
    "190": 0.05,  # Other Contract
}

_NOS_RE = re.compile(r"\b(\d{3})\b")

# JS-44 codes for proceedings that are individual by nature. A full-text hit
# on "class action" in one of these is almost always a brief citing some
# other case, not a class action of its own.
_NON_CLASS_NOS: frozenset[str] = frozenset(
    {
        "510",  # Motions to Vacate Sentence
        "530",  # Habeas Corpus: General
        "535",  # Habeas Corpus: Death Penalty
        "540",  # Mandamus and Other
        "463",  # Habeas Corpus: Alien Detainee
        "462",  # Naturalization Application
        "465",  # Other Immigration Actions
        "550",  # Prisoner Civil Rights
        "555",  # Prison Condition
    }
)

# Criminal dockets use a "-cr-" docket number; civil ones use "-cv-".
_CRIMINAL_DOCKET_RE = re.compile(r"\d+:\d+-cr-", re.IGNORECASE)


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    # Terms OR-ed into the upstream full-text query when this topic is chosen.
    query_terms: tuple[str, ...]
    # Words matched against case text to tag results after the fact.
    match_terms: tuple[str, ...] = field(default=())
    # Nature-of-suit codes that belong to this topic and this topic only.
    # Generic codes like 890 ("Other Statutory Actions") are deliberately
    # excluded: they are shared by half the topics and tagging from them
    # produces nonsense like a data breach case labelled "defective products".
    distinctive_nos: tuple[str, ...] = field(default=())

    def terms_for_matching(self) -> tuple[str, ...]:
        return self.match_terms or self.query_terms


TOPICS: tuple[Topic, ...] = (
    Topic(
        key="data_privacy",
        label="Data breach & privacy",
        query_terms=("data breach", "personally identifiable information",
                     "privacy", "wiretap"),
        match_terms=("data breach", "personally identifiable", "privacy",
                     "wiretap", "biometric", "bipa", "ccpa", "pii",
                     "unauthorized access", "session replay"),
    ),
    Topic(
        key="consumer",
        label="Consumer protection & false advertising",
        query_terms=("false advertising", "deceptive", "consumer protection",
                     "mislabeled"),
        match_terms=("false advertis", "deceptive", "consumer protection",
                     "mislabel", "unfair competition", "warranty",
                     "misrepresent", "unjust enrichment"),
    ),
    Topic(
        key="employment",
        label="Wages & employment",
        query_terms=("fair labor standards act", "unpaid overtime",
                     "wage and hour", "employment discrimination"),
        match_terms=("fair labor standards", "flsa", "overtime",
                     "wage and hour", "minimum wage", "discriminat",
                     "misclassif"),
        distinctive_nos=("710", "442"),
    ),
    Topic(
        key="securities",
        label="Securities & investors",
        query_terms=("securities fraud", "securities exchange act",
                     "shareholder"),
        match_terms=("securities", "shareholder", "investor", "10b-5",
                     "misleading statements", "stock"),
        distinctive_nos=("850",),
    ),
    Topic(
        key="antitrust",
        label="Antitrust & price fixing",
        query_terms=("antitrust", "price fixing", "sherman act", "monopoly"),
        match_terms=("antitrust", "price fixing", "price-fixing", "sherman",
                     "clayton act", "monopol", "conspiracy to fix"),
        distinctive_nos=("410",),
    ),
    Topic(
        key="product",
        label="Defective products & drugs",
        query_terms=("product liability", "defective", "recall"),
        match_terms=("product liability", "defect", "recall", "failure to warn",
                     "design defect"),
        distinctive_nos=("365", "245"),
    ),
    Topic(
        key="financial",
        label="Banking, fees & lending",
        query_terms=("overdraft fee", "debt collection", "truth in lending",
                     "consumer credit"),
        match_terms=("overdraft", "debt collection", "fdcpa", "tila",
                     "truth in lending", "junk fee", "interest rate",
                     "consumer credit"),
        distinctive_nos=("480",),
    ),
    Topic(
        key="insurance",
        label="Insurance & healthcare billing",
        query_terms=("insurance", "denial of benefits", "erisa",
                     "medical billing"),
        match_terms=("insurance", "insurer", "benefits", "erisa",
                     "medical bill", "surprise billing", "premium"),
        distinctive_nos=("791",),
    ),
)

TOPICS_BY_KEY: dict[str, Topic] = {topic.key: topic for topic in TOPICS}


def _searchable_text(case: dict) -> str:
    """Flatten the parts of a docket a human would read when judging it."""
    parts: list[str] = [
        str(case.get("caseName") or ""),
        str(case.get("case_name_full") or ""),
        str(case.get("cause") or ""),
        str(case.get("suitNature") or ""),
        str(case.get("juryDemand") or ""),
    ]
    for document in case.get("recap_documents") or []:
        parts.append(str(document.get("description") or ""))
        parts.append(str(document.get("short_description") or ""))
        parts.append(str(document.get("snippet") or ""))
    return " ".join(parts).lower()


def nature_of_suit_code(case: dict) -> str | None:
    """Pull the 3-digit JS-44 code out of a suitNature string like '890 Other'."""
    match = _NOS_RE.search(str(case.get("suitNature") or ""))
    return match.group(1) if match else None


def is_unlikely_class_action(case: dict) -> bool:
    """True for dockets whose own type rules out a class action.

    Used to withhold the benefit of the doubt that a full-text match would
    otherwise earn a docket.
    """
    if _CRIMINAL_DOCKET_RE.search(str(case.get("docketNumber") or "")):
        return True
    code = nature_of_suit_code(case)
    return bool(code and code in _NON_CLASS_NOS)


def class_action_confidence(case: dict) -> tuple[float, list[str]]:
    """Score 0.0-1.0 that ``case`` is a class action, with the reasons why."""
    text = _searchable_text(case)
    score = 0.0
    reasons: list[str] = []

    for phrase, weight in _STRONG_PHRASES:
        if phrase in text:
            score += weight
            reasons.append(f"mentions “{phrase}”")

    code = nature_of_suit_code(case)
    if code and code in _NOS_WEIGHTS:
        score += _NOS_WEIGHTS[code]
        reasons.append(f"nature of suit {case.get('suitNature')}")

    return min(score, 1.0), reasons


def topics_for(case: dict) -> list[str]:
    """Return the keys of every topic this docket plausibly falls under."""
    text = _searchable_text(case)
    code = nature_of_suit_code(case)
    hits: list[str] = []
    for topic in TOPICS:
        if any(term in text for term in topic.terms_for_matching()):
            hits.append(topic.key)
        elif code and code in topic.distinctive_nos:
            hits.append(topic.key)
    return hits
