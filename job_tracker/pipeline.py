from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from . import classify, criteria, scoring
from .models import Job

_MULTI_LOCATION = re.compile(r"\d+\s+locations", re.I)


class Result:
    def __init__(self) -> None:
        self.buckets: dict[str, list[Job]] = {b: [] for b in classify.BUCKETS}
        self.rejected: Counter = Counter()
        self.errors: list[str] = []


def process(jobs: list[Job], profile: dict, now: datetime, uk_register: set[str] | None = None, result: Result | None = None) -> Result:
    crit = profile["criteria"]
    fx = profile.get("fx_to_inr", {})
    exclude_title = re.compile(crit.get("exclude_title_regex") or r"(?!x)x", re.I)
    excluded_companies = {c.lower() for c in crit.get("exclude_companies", [])}
    max_age = int(crit.get("max_age_days", 3))
    min_lpa = float(crit.get("min_pay_lpa", 60))
    visa_buckets = set(crit.get("require_visa_for", ["uae", "uk", "europe"]))
    skills = profile["resume"].get("match_skills", [])
    result = result or Result()
    seen: set[str] = set()

    for job in jobs:
        if job.key in seen:
            continue
        seen.add(job.key)
        if job.company.lower() in excluded_companies:
            result.rejected["excluded company"] += 1
            continue
        if not criteria.is_fresh(job, max_age, now):
            result.rejected[f"older than {max_age} days / no date"] += 1
            continue
        if not classify.title_could_match(job, exclude_title):
            result.rejected["title not frontend/fullstack/senior"] += 1
            continue
        loc = job.location or ""
        if not (classify.regions(loc) or job.remote or "remote" in loc.lower() or _MULTI_LOCATION.search(loc)):
            result.rejected["location outside target regions"] += 1
            continue
        try:
            job.load_details()
        except Exception as exc:  # one bad detail page shouldn't stop the run
            result.errors.append(f"{job.company}: detail fetch failed for {job.url}: {exc}")
            continue
        if not criteria.is_fresh(job, max_age, now):
            result.rejected[f"older than {max_age} days / no date"] += 1
            continue
        job.role_type = classify.role_type(job, exclude_title)
        if not job.role_type:
            result.rejected["title not frontend/fullstack/senior"] += 1
            continue
        buckets = classify.buckets_for(job)
        if not buckets:
            result.rejected["location outside target regions (or remote restricted)"] += 1
            continue

        scoring.score(job, skills)
        job.recruiter_emails = criteria.recruiter_emails(job.description)
        meets_pay, pay_label = criteria.check_pay(job, min_lpa, fx, crit.get("pay_rule", "max"))
        job.pay_check = pay_label
        if "remote" in buckets:
            scope = classify.remote_scope(job)
            if scope == "unspecified":
                job.notes.append("remote region not stated - confirm India is eligible")

        for bucket in buckets:
            if bucket in visa_buckets:
                ok, evidence = criteria.visa_sponsorship(job.description)
                if not ok:
                    result.rejected[f"{bucket}: no explicit visa sponsorship"] += 1
                    continue
                job.visa_evidence = evidence
            else:
                if meets_pay is False:
                    result.rejected[f"{bucket}: pay below {min_lpa:g} LPA"] += 1
                    continue
                if meets_pay is None and not crit.get("allow_undisclosed_pay", True):
                    result.rejected[f"{bucket}: pay not disclosed"] += 1
                    continue
            result.buckets[bucket].append(job)
    return result
