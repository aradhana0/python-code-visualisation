"""Decide which role type (frontend / fullstack) and which region buckets a job belongs to."""
from __future__ import annotations

import re

from .models import Job

BUCKETS = ["bangalore_frontend", "bangalore_fullstack", "remote", "uae", "uk", "europe"]
INTERNATIONAL = {"uae", "uk", "europe"}


def _rx(words: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(words) + r")\b", re.I)


REGIONS = {
    "bangalore": _rx(["bangalore", "bengaluru", "karnataka"]),
    "uae": _rx(["uae", "u\\.a\\.e\\.?", "united arab emirates", "dubai", "abu dhabi", "sharjah"]),
    "uk": _rx([
        "uk", "u\\.k\\.", "united kingdom", "great britain", "england", "scotland", "wales",
        "london", "manchester", "edinburgh", "bristol", "leeds", "glasgow", "oxford", "belfast",
    ]),
    "europe": _rx([
        "germany", "netherlands", "ireland", "france", "spain", "portugal", "italy", "sweden",
        "denmark", "norway", "finland", "poland", "austria", "switzerland", "belgium", "luxembourg",
        "czech republic", "czechia", "estonia", "lithuania", "latvia", "greece", "hungary", "romania",
        "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "amsterdam", "rotterdam",
        "utrecht", "eindhoven", "the hague", "dublin", "paris", "madrid", "barcelona", "lisbon",
        "porto", "milan", "stockholm", "copenhagen", "oslo", "helsinki", "warsaw", "krakow", "kraków",
        "vienna", "zurich", "zürich", "geneva", "brussels", "prague", "tallinn", "vilnius", "riga",
        "athens", "budapest", "bucharest",
    ]),
}

_REMOTE_OK = _rx(["anywhere", "worldwide", "global", "globally", "india", "apac", "asia", "asia pacific"])
_REMOTE_RESTRICTED = _rx([
    "us", "usa", "u\\.s\\.", "united states", "canada", "latam", "americas", "north america",
    "uk", "united kingdom", "europe", "eu", "emea", "germany", "france", "spain", "netherlands",
    "poland", "ireland", "australia", "brazil", "mexico", "japan", "singapore",
])
_DESC_RESTRICTED = re.compile(
    r"(must|need to|required to)\s+(be\s+)?(located|based|reside|residing|live|living)\s+(in|within)\s+(the\s+)?"
    r"(us|u\.s\.|united states|canada|uk|united kingdom|eu|europe|emea|americas)\b"
    r"|\b(us|u\.s\.)[- ]based\b"
    r"|authori[sz]ed to work in the (us|u\.s\.|united states)"
    r"|\bremote\s*[-–(]\s*(us|usa|united states|canada|uk|eu|europe|emea)\b",
    re.I,
)

_FRONTEND_TITLE = re.compile(
    r"front[\s-]?end|\bui\b|\breact\b|\bweb (developer|engineer)\b|\bjavascript\b|\btypescript\b"
    r"|\bangular\b|\bvue\b|design systems? engineer|\bux engineer\b",
    re.I,
)
_FULLSTACK_TITLE = re.compile(r"full[\s-]?stack", re.I)
_GENERIC_TITLE = re.compile(
    r"software (engineer|developer)|\bsde\b|\bswe\b|product engineer|member of technical staff|\bmts\b"
    r"|application(s)? engineer|software development engineer|\bdeveloper\b",
    re.I,
)
# Specialisms that rule out a *generic* title ("Software Engineer, Data") but not an
# explicit one ("Senior Frontend Engineer, Data Visualisation").
_OTHER_SPECIALTY = re.compile(
    r"\b(data|machine learning|ml|ai research|android|ios|mobile|devops|sre|site reliability|security|qa|sdet|"
    r"test|embedded|firmware|hardware|backend|back[\s-]end|infrastructure|platform|network|support|salesforce)\b",
    re.I,
)
_FRONTEND_TERMS = re.compile(r"\b(react|typescript|front[\s-]?end|css|next\.?js|redux|web ui|javascript)\b", re.I)
_BACKEND_TERMS = re.compile(
    r"\b(python|node\.?js|fastapi|django|flask|back[\s-]?end|apis?|microservices|postgres|sql|go|golang|java)\b", re.I
)


def role_type(job: Job, exclude: re.Pattern) -> str:
    """Return 'frontend', 'fullstack' or '' (not a match)."""
    title = job.title
    if exclude.search(title):
        return ""
    if _FULLSTACK_TITLE.search(title):
        return "fullstack"
    if _FRONTEND_TITLE.search(title):
        return "frontend"
    if _GENERIC_TITLE.search(title) and job.description and not _OTHER_SPECIALTY.search(title):
        fe = len(set(m.lower() for m in _FRONTEND_TERMS.findall(job.description)))
        be = len(set(m.lower() for m in _BACKEND_TERMS.findall(job.description)))
        if fe >= 2 and be >= 2:
            return "fullstack"
        if fe >= 3:
            return "frontend"
    return ""


def title_could_match(job: Job, exclude: re.Pattern) -> bool:
    """Cheap pre-check (before fetching descriptions) that the title is worth a look."""
    t = job.title
    if exclude.search(t):
        return False
    if _FULLSTACK_TITLE.search(t) or _FRONTEND_TITLE.search(t):
        return True
    return bool(_GENERIC_TITLE.search(t)) and not _OTHER_SPECIALTY.search(t)


def regions(location: str) -> set[str]:
    return {name for name, rx in REGIONS.items() if rx.search(location or "")}


def remote_scope(job: Job) -> str:
    """'anywhere' | 'india/apac' | 'unspecified' (eligible) or 'restricted' (not eligible from India)."""
    loc = job.location or ""
    remote_parts = [p for p in re.split(r"[|;/]", loc) if "remote" in p.lower()] or ([loc] if job.remote else [])
    text = " ".join(remote_parts)
    ok = _REMOTE_OK.search(text)
    if ok:
        return "india/apac" if ok.group(0).lower() in {"india", "apac", "asia", "asia pacific"} else "anywhere"
    if _REMOTE_RESTRICTED.search(text) or regions(text) - {"bangalore"}:
        return "restricted"
    if _DESC_RESTRICTED.search(job.description or ""):
        return "restricted"
    if re.search(r"\b(work from anywhere|fully distributed|remote[- ]first,? (worldwide|global))\b", job.description or "", re.I):
        return "anywhere"
    return "unspecified"


def buckets_for(job: Job) -> list[str]:
    found = regions(job.location)
    out: list[str] = []
    is_remote = job.remote or "remote" in (job.location or "").lower()
    if is_remote and remote_scope(job) != "restricted":
        out.append("remote")
    if "bangalore" in found and not (is_remote and "remote" in out):
        out.append(f"bangalore_{job.role_type}")
    for region in ("uae", "uk", "europe"):
        if region in found:
            out.append(region)
    return out
