from __future__ import annotations

from ..models import Job, Salary
from ..text import html_to_text, parse_datetime

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _salary(comp: dict | None) -> Salary | None:
    for part in (comp or {}).get("summaryComponents") or []:
        if part.get("compensationType") != "Salary" or not part.get("currencyCode"):
            continue
        factor = 12 if "MONTH" in (part.get("interval") or "").upper() else 1
        lo, hi = part.get("minValue"), part.get("maxValue")
        return Salary(
            min=lo * factor if lo else None,
            max=hi * factor if hi else None,
            currency=part["currencyCode"].upper(),
            source="structured",
        )
    return None


def fetch(company: dict, fetch) -> list[Job]:
    data = fetch(API.format(slug=company["slug"]))
    jobs = []
    for item in data.get("jobs", []):
        if item.get("isListed") is False:
            continue
        locations = [item.get("location", "")]
        locations += [s.get("location", "") for s in item.get("secondaryLocations") or []]
        location = " | ".join(l for l in locations if l)
        jobs.append(
            Job(
                company=company["name"],
                title=item.get("title", "").strip(),
                location=location,
                url=item.get("jobUrl", ""),
                posted_at=parse_datetime(item.get("publishedAt")),
                description=item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml")),
                source="ashby",
                remote=bool(item.get("isRemote")) or (item.get("workplaceType") or "").lower() == "remote",
                salary=_salary(item.get("compensation")),
            )
        )
    return jobs
