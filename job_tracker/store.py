"""One CSV per bucket. Re-runs merge in new jobs and keep the columns you edit by hand."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import Job

COLUMNS = [
    "status", "match_score", "company", "title", "role_type", "location", "posted_date", "days_old",
    "pay", "pay_check", "visa_sponsorship_evidence", "uk_sponsor_register", "recruiter_emails",
    "official_url", "source", "matched_skills", "missing_skills", "resume", "cover_letter",
    "applied_on", "follow_up_on", "my_notes", "first_seen",
]
# Columns you own: never overwritten by a run.
USER_COLUMNS = ["status", "applied_on", "follow_up_on", "my_notes"]
FOLLOW_UP_DAYS = 7


def job_row(job: Job, resume: str, cover_letter: str, now: datetime, register_hit: bool | None) -> dict:
    return {
        "status": "new",
        "match_score": job.match_score,
        "company": job.company,
        "title": job.title,
        "role_type": job.role_type,
        "location": job.location,
        "posted_date": f"{job.posted_at:%Y-%m-%d}" if job.posted_at else "",
        "days_old": (now - job.posted_at).days if job.posted_at else "",
        "pay": f"{job.pay_lpa:g} LPA" if job.pay_lpa is not None else "",
        "pay_check": job.pay_check,
        "visa_sponsorship_evidence": job.visa_evidence,
        "uk_sponsor_register": "" if register_hit is None else ("listed" if register_hit else "not found"),
        "recruiter_emails": "; ".join(job.recruiter_emails),
        "official_url": job.url,
        "source": job.source,
        "matched_skills": ", ".join(job.matched_skills),
        "missing_skills": ", ".join(job.missing_skills),
        "resume": resume,
        "cover_letter": cover_letter,
        "applied_on": "",
        "follow_up_on": "",
        "my_notes": "; ".join(job.notes),
        "first_seen": f"{now:%Y-%m-%d}",
    }


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge(existing: list[dict], fresh: list[dict], max_age_days: int, today: date) -> list[dict]:
    by_url = {r["official_url"]: r for r in existing}
    out: dict[str, dict] = {}
    for row in fresh:
        old = by_url.get(row["official_url"])
        if old:
            for col in USER_COLUMNS + ["first_seen", "resume", "cover_letter"]:
                if old.get(col):
                    row[col] = old[col]
        out[row["official_url"]] = row
    for url, old in by_url.items():
        if url in out:
            continue
        # Keep anything you're tracking; drop untouched rows once they're past the freshness window.
        tracking = (old.get("status") or "new") != "new" or old.get("my_notes")
        posted = old.get("posted_date")
        stale = not posted or (today - date.fromisoformat(posted)).days > max_age_days
        if tracking or not stale:
            if posted:
                old["days_old"] = (today - date.fromisoformat(posted)).days
            out[url] = old
    rows = list(out.values())
    for row in rows:
        if row.get("applied_on") and not row.get("follow_up_on"):
            try:
                row["follow_up_on"] = str(date.fromisoformat(row["applied_on"]) + timedelta(days=FOLLOW_UP_DAYS))
            except ValueError:
                pass
    rows.sort(key=lambda r: (r.get("status") != "new", -int(r.get("match_score") or 0)))
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def follow_ups_due(rows: list[dict], today: date) -> list[dict]:
    due = []
    for r in rows:
        if r.get("follow_up_on") and (r.get("status") or "").lower() in {"applied", "follow-up"}:
            try:
                if date.fromisoformat(r["follow_up_on"]) <= today:
                    due.append(r)
            except ValueError:
                continue
    return due


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
