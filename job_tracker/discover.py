"""Find which job-board API a company's careers page uses and print a companies.toml entry."""
from __future__ import annotations

import re

_PATTERNS = [
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"(?:job-)?boards(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"(?:jobs|api)\.(eu\.)?lever\.co/(?:v0/postings/)?([A-Za-z0-9_-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)")),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/(?:api/v\d/(?:widget/)?accounts/)?([A-Za-z0-9_-]+)")),
    ("workday", re.compile(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)")),
]
_IGNORE = {"embed", "api", "v0", "v1", "jobs", "job_board", "static", "assets", "careers", "wday", "en-US"}


def detect(html: str) -> list[dict]:
    """Return candidate config entries (most frequent first) found in a page's HTML."""
    counts: dict[tuple, int] = {}
    for ats, rx in _PATTERNS:
        for m in rx.finditer(html):
            if ats == "workday":
                tenant, wd, site = m.groups()
                if site in _IGNORE:
                    continue
                key = (ats, ("host", f"{tenant}.{wd}.myworkdayjobs.com"), ("tenant", tenant), ("site", site))
            elif ats == "lever":
                eu, slug = m.groups()
                if slug in _IGNORE:
                    continue
                key = (ats, ("slug", slug)) + ((("region", "eu"),) if eu else ())
            else:
                slug = m.group(1)
                if slug in _IGNORE:
                    continue
                key = (ats, ("slug", slug))
            counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts, key=lambda k: -counts[k])
    return [{"ats": k[0], **dict(k[1:])} for k in ranked]


def toml_entry(name: str, found: dict) -> str:
    lines = ["[[company]]", f'name = "{name}"'] + [f'{k} = "{v}"' for k, v in found.items()]
    return "\n".join(lines)
