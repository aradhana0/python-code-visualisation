from __future__ import annotations

from ..models import Job, Salary
from ..text import html_to_text, parse_datetime

API = {
    "global": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "eu": "https://api.eu.lever.co/v0/postings/{slug}?mode=json",
}

_PER_YEAR = {"per-year-salary": 1, "per-month-salary": 12, "per-hour-wage": 2080}


def _salary(raw: dict | None) -> Salary | None:
    if not raw or not raw.get("currency"):
        return None
    factor = _PER_YEAR.get(raw.get("interval", "per-year-salary"), 1)
    lo, hi = raw.get("min"), raw.get("max")
    return Salary(
        min=lo * factor if lo else None,
        max=hi * factor if hi else None,
        currency=raw["currency"].upper(),
        source="structured",
    )


def fetch(company: dict, fetch) -> list[Job]:
    data = fetch(API[company.get("region", "global")].format(slug=company["slug"]))
    jobs = []
    for item in data or []:
        cats = item.get("categories") or {}
        locations = cats.get("allLocations") or [cats.get("location", "")]
        location = " | ".join(l for l in locations if l)
        parts = [item.get("descriptionPlain", "")]
        for block in item.get("lists") or []:
            parts.append(block.get("text", ""))
            parts.append(html_to_text(block.get("content")))
        parts.append(item.get("additionalPlain", ""))
        workplace = (item.get("workplaceType") or "").lower()
        jobs.append(
            Job(
                company=company["name"],
                title=item.get("text", "").strip(),
                location=location,
                url=item.get("hostedUrl", ""),
                posted_at=parse_datetime(item.get("createdAt")),
                description="\n\n".join(p for p in parts if p).strip(),
                source="lever",
                remote=workplace == "remote" or "remote" in location.lower(),
                salary=_salary(item.get("salaryRange")),
            )
        )
    return jobs
