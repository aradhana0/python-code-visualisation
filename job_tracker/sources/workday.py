"""Workday career sites (used by Adobe, Salesforce, NVIDIA, Walmart and others).

Configure with ``host`` (e.g. ``adobe.wd5.myworkdayjobs.com``), ``tenant`` and
``site`` - all three are visible in the company's careers URL:
https://<host>/en-US/<site>  ->  API at https://<host>/wday/cxs/<tenant>/<site>/jobs
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..models import Job
from ..text import html_to_text, parse_datetime

DEFAULT_SEARCH = ["frontend", "front end", "full stack", "react", "UI engineer"]
PAGE = 20
MAX_PER_TERM = 100


def posted_on_to_datetime(text: str, now: datetime | None = None) -> datetime | None:
    """Workday lists 'Posted Today', 'Posted Yesterday', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'."""
    now = now or datetime.now(timezone.utc)
    t = (text or "").lower()
    if "today" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", t)
    return now - timedelta(days=int(m.group(1))) if m else None


def fetch(company: dict, fetch) -> list[Job]:
    host, tenant, site = company["host"], company["tenant"], company["site"]
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    seen: dict[str, Job] = {}
    for term in company.get("search_terms", DEFAULT_SEARCH):
        for offset in range(0, MAX_PER_TERM, PAGE):
            data = fetch(f"{base}/jobs", data={"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": term})
            postings = data.get("jobPostings", [])
            for item in postings:
                path = item.get("externalPath")
                if not path or path in seen:
                    continue
                seen[path] = Job(
                    company=company["name"],
                    title=item.get("title", "").strip(),
                    location=item.get("locationsText", ""),
                    url=f"https://{host}/en-US/{site}{path}",
                    posted_at=posted_on_to_datetime(item.get("postedOn", "")),
                    description="",
                    source="workday",
                    remote="remote" in (item.get("locationsText") or "").lower(),
                    loader=_detail_loader(f"{base}{path}", fetch),
                )
            if len(postings) < PAGE:
                break
    return list(seen.values())


def _detail_loader(url: str, fetch):
    def load(job: Job) -> None:
        info = (fetch(url) or {}).get("jobPostingInfo") or {}
        job.description = html_to_text(info.get("jobDescription"))
        locations = [info.get("location", "")] + list(info.get("additionalLocations") or [])
        if any(locations):
            job.location = " | ".join(l for l in locations if l)
        if info.get("startDate"):
            job.posted_at = parse_datetime(info["startDate"]) or job.posted_at
        if (info.get("remoteType") or "").lower().startswith("remote"):
            job.remote = True
        if info.get("externalUrl"):
            job.url = info["externalUrl"]

    return load
