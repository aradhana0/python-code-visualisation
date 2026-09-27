from __future__ import annotations

from ..models import Job
from ..text import html_to_text, parse_datetime

LIST_API = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"
DETAIL_API = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{id}"
PUBLIC_URL = "https://jobs.smartrecruiters.com/{slug}/{id}"
MAX_PAGES = 10


def _detail_loader(slug: str, posting_id: str, fetch):
    def load(job: Job) -> None:
        data = fetch(DETAIL_API.format(slug=slug, id=posting_id))
        sections = ((data or {}).get("jobAd") or {}).get("sections") or {}
        job.description = "\n\n".join(
            html_to_text((sections.get(k) or {}).get("text"))
            for k in ("jobDescription", "qualifications", "additionalInformation", "companyDescription")
        ).strip()

    return load


def fetch(company: dict, fetch) -> list[Job]:
    slug = company["slug"]
    jobs = []
    for page in range(MAX_PAGES):
        data = fetch(LIST_API.format(slug=slug, offset=page * 100))
        items = data.get("content", [])
        for item in items:
            loc = item.get("location") or {}
            location = loc.get("fullLocation") or ", ".join(
                p for p in (loc.get("city"), loc.get("region"), loc.get("country", "").upper()) if p
            )
            if loc.get("remote"):
                location = f"{location} (Remote)" if location else "Remote"
            jobs.append(
                Job(
                    company=company["name"],
                    title=item.get("name", "").strip(),
                    location=location,
                    url=PUBLIC_URL.format(slug=slug, id=item["id"]),
                    posted_at=parse_datetime(item.get("releasedDate")),
                    description="",
                    source="smartrecruiters",
                    remote=bool(loc.get("remote")),
                    loader=_detail_loader(slug, item["id"], fetch),
                )
            )
        if len(items) < 100 or (page + 1) * 100 >= data.get("totalFound", 0):
            break
    return jobs
