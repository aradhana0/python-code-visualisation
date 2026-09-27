from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass
class Salary:
    """A pay range as published by the employer, normalised to a yearly amount."""

    min: float | None
    max: float | None
    currency: str  # ISO code, e.g. INR, USD, GBP, EUR, AED
    source: str  # "structured" (ATS field) or "text" (parsed from description)

    @property
    def best(self) -> float | None:
        return self.max if self.max is not None else self.min


@dataclass
class Job:
    company: str
    title: str
    location: str
    url: str  # official posting URL on the company's own careers page / ATS
    posted_at: datetime | None
    description: str  # plain text
    source: str  # greenhouse | lever | ashby | smartrecruiters | workday
    remote: bool = False
    salary: Salary | None = None
    # Some sources list postings without descriptions; this fetches the detail
    # page lazily so we only hit it for jobs that survive the cheap filters.
    loader: Callable[["Job"], None] | None = field(default=None, repr=False, compare=False)

    # Brands hiring through a parent company's board (e.g. talabat on Delivery Hero's)
    brands: list[str] = field(default_factory=list)

    # Filled in by the pipeline
    bucket: str = ""
    role_type: str = ""  # frontend | fullstack
    pay_lpa: float | None = None
    pay_check: str = ""
    visa_evidence: str = ""
    recruiter_emails: list[str] = field(default_factory=list)
    match_score: int = 0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def load_details(self) -> None:
        if self.loader is not None:
            loader, self.loader = self.loader, None
            loader(self)

    @property
    def key(self) -> str:
        return self.url.split("?")[0].rstrip("/")
