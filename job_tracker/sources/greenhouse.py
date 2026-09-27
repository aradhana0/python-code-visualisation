from __future__ import annotations

from ..models import Job
from ..text import html_to_text, parse_datetime

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch(company: dict, fetch) -> list[Job]:
    data = fetch(API.format(slug=company["slug"]))
    jobs = []
    for item in data.get("jobs", []):
        location = (item.get("location") or {}).get("name", "")
        offices = ", ".join(o.get("name", "") for o in item.get("offices") or [] if o.get("name"))
        if offices and offices.lower() not in location.lower():
            location = f"{location} | {offices}" if location else offices
        jobs.append(
            Job(
                company=company["name"],
                title=item.get("title", "").strip(),
                location=location,
                url=item.get("absolute_url", ""),
                # first_published is the real posting date; updated_at moves on edits
                posted_at=parse_datetime(item.get("first_published") or item.get("updated_at")),
                description=html_to_text(item.get("content")),
                source="greenhouse",
                remote="remote" in location.lower(),
            )
        )
    return jobs
