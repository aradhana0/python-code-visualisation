from __future__ import annotations

from ..models import Job
from ..text import html_to_text, parse_datetime

API = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"


def fetch(company: dict, fetch) -> list[Job]:
    data = fetch(API.format(slug=company["slug"]))
    jobs = []
    for item in data.get("jobs", []):
        places = item.get("locations") or [item]
        location = " | ".join(
            ", ".join(p for p in (loc.get("city"), loc.get("country")) if p) for loc in places
        )
        remote = bool(item.get("telecommuting"))
        if remote:
            location = f"{location} (Remote)" if location else "Remote"
        jobs.append(
            Job(
                company=company["name"],
                title=(item.get("title") or "").strip(),
                location=location,
                url=item.get("url") or item.get("shortlink") or "",
                posted_at=parse_datetime(item.get("published_on") or item.get("created_at")),
                description=html_to_text(item.get("description")),
                source="workable",
                remote=remote,
            )
        )
    return jobs
