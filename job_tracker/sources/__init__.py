"""Connectors for the public job-board APIs that power companies' own career pages.

Every connector reads the employer's official listing (not an aggregator) and
returns ``Job`` objects whose ``url`` is the official posting page.
"""
from __future__ import annotations

from typing import Callable

from ..http import get_json
from ..models import Job
from . import ashby, greenhouse, lever, smartrecruiters, workday

Fetcher = Callable[..., object]

CONNECTORS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "workday": workday.fetch,
}


def fetch_company(company: dict, fetch: Fetcher = get_json) -> list[Job]:
    ats = company["ats"]
    if ats not in CONNECTORS:
        raise ValueError(f"{company['name']}: unknown ats '{ats}' (use one of {sorted(CONNECTORS)})")
    return CONNECTORS[ats](company, fetch)
