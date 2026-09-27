"""Hard criteria: freshness, minimum pay, explicit visa sponsorship, recruiter contacts."""
from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job, Salary

# ---------------------------------------------------------------- freshness


def is_fresh(job: Job, max_age_days: int, now: datetime | None = None) -> bool:
    if job.posted_at is None:
        return False  # can't prove it is recent -> skip
    now = now or datetime.now(timezone.utc)
    return now - job.posted_at <= timedelta(days=max_age_days)


# ---------------------------------------------------------------- pay

_NUM = r"(\d+(?:\.\d+)?)"
_RANGE_SEP = r"\s*(?:-|–|—|to)\s*"
_LAKH_UNIT = r"\s*(?:lpa|lakhs?|lacs?|l)\b"
_LAKH_RANGE = re.compile(_NUM + _RANGE_SEP + _NUM + _LAKH_UNIT, re.I)
_LAKH_SINGLE = re.compile(_NUM + _LAKH_UNIT, re.I)
_CRORE = re.compile(_NUM + r"(?:" + _RANGE_SEP + _NUM + r")?\s*(?:cr|crores?)\b", re.I)
_RUPEES = re.compile(r"(?:₹|\binr\b|\brs\.?)\s*([\d,]{6,}(?:\.\d+)?)(?:" + _RANGE_SEP + r"(?:₹|inr|rs\.?)?\s*([\d,]{6,}))?", re.I)
_FOREIGN = re.compile(
    r"([$£€]|\bUSD|\bGBP|\bEUR|\bAED)\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?[kK])"
    r"(?:" + _RANGE_SEP + r"(?:[$£€]|USD|GBP|EUR|AED)?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?[kK]))?",
)
_SYMBOL = {"$": "USD", "£": "GBP", "€": "EUR"}


def _amount(token: str) -> float:
    token = token.replace(",", "").strip()
    if token[-1:] in "kK":
        return float(token[:-1]) * 1000
    return float(token)


def salary_from_text(text: str) -> Salary | None:
    """Best-effort extraction of an annual pay range written in the description."""
    if not text:
        return None
    m = _LAKH_RANGE.search(text)
    if m:
        return Salary(float(m.group(1)) * 1e5, float(m.group(2)) * 1e5, "INR", "text")
    m = _CRORE.search(text)
    if m:
        hi = m.group(2) or m.group(1)
        return Salary(float(m.group(1)) * 1e7, float(hi) * 1e7, "INR", "text")
    m = _RUPEES.search(text)
    if m:
        lo = _amount(m.group(1))
        hi = _amount(m.group(2)) if m.group(2) else None
        return Salary(lo, hi, "INR", "text")
    m = _LAKH_SINGLE.search(text)
    if m and float(m.group(1)) >= 3:  # avoid matching things like "2L" in unrelated contexts
        return Salary(float(m.group(1)) * 1e5, None, "INR", "text")
    for m in _FOREIGN.finditer(text):
        cur = _SYMBOL.get(m.group(1), m.group(1).upper())
        lo = _amount(m.group(2))
        hi = _amount(m.group(3)) if m.group(3) else None
        if (hi or lo) >= 10000:  # ignore hourly rates, stipends, "$5M funding", etc.
            return Salary(lo, hi, cur, "text")
    return None


def to_lpa(amount: float | None, currency: str, fx_to_inr: dict[str, float]) -> float | None:
    if amount is None:
        return None
    rate = 1.0 if currency == "INR" else fx_to_inr.get(currency)
    if rate is None:
        return None
    return round(amount * rate / 1e5, 1)


def check_pay(job: Job, min_lpa: float, fx: dict[str, float], rule: str = "max") -> tuple[bool | None, str]:
    """Return (meets?, human label). ``None`` means pay is not disclosed."""
    salary = job.salary or salary_from_text(job.description)
    job.salary = salary
    if salary is None:
        return None, "undisclosed"
    lo = to_lpa(salary.min, salary.currency, fx)
    hi = to_lpa(salary.max, salary.currency, fx)
    shown = f"{lo:g}" if lo is not None else "?"
    if hi is not None and hi != lo:
        shown += f"–{hi:g}"
    label = f"{shown} LPA"
    if salary.currency != "INR":
        native = "–".join(f"{v:,.0f}" for v in (salary.min, salary.max) if v)
        label += f" ({salary.currency} {native})"
    value = lo if rule == "min" else (hi if hi is not None else lo)
    job.pay_lpa = value
    if value is None:
        return None, f"undisclosed (no FX rate for {salary.currency})"
    return value >= min_lpa, label


# ---------------------------------------------------------------- visa

_SENTENCE = re.compile(r"(?<=[.!?\n])\s+")
_VISA_TOPIC = re.compile(r"visa|sponsor|work permit|blue card|right to work|work authori[sz]ation", re.I)
_VISA_NEGATIVE = re.compile(
    r"\b(not|unable|cannot|can't|can not|don't|do not|won't|will not|no|without|unfortunately)\b[^.]{0,60}"
    r"(sponsor|visa|work permit)"
    r"|(sponsorship|visa)[^.]{0,30}\b(is|are)\s+not\s+(available|offered|provided|possible)"
    r"|must (already )?(have|hold|possess)[^.]{0,40}(right to work|work authori[sz]ation|valid (work )?visa|work permit)"
    r"|(right to work|work authori[sz]ation)[^.]{0,30}\b(required|is a must|mandatory)",
    re.I,
)
_VISA_POSITIVE = re.compile(
    r"visa sponsorship (is )?(available|provided|offered|possible|support)"
    r"|(offer|offers|offering|provide|provides|providing)\b[^.]{0,40}\b(visa|sponsorship|work permit|blue card)"
    r"|(we|will|can|able to|happy to|do|are)\s+(\w+\s+)?sponsor(s|ing)?\b[^.]{0,40}(visa|work permit|candidates|you|applicants)"
    r"|(sponsor|sponsorship|support|assistance|help)\s+(for|with)\s+(your\s+|a\s+|the\s+)?(visa|work permit|blue card|relocation and visa)"
    r"|(visa|immigration)\s+(support|assistance|sponsorship)\b"
    r"|relocation\s+(and|&)\s+visa"
    r"|skilled worker (visa|sponsorship)"
    r"|(employment|residence|residency|work)\s+visa\s+(is\s+)?(provided|included|covered|sponsored)",
    re.I,
)


def visa_sponsorship(description: str) -> tuple[bool, str]:
    """Explicit sponsorship check. Returns (sponsored, evidence sentence or reason)."""
    positive = ""
    for sentence in _SENTENCE.split(description or ""):
        if not _VISA_TOPIC.search(sentence):
            continue
        s = sentence.strip()
        if _VISA_NEGATIVE.search(s):
            return False, f"negative: {s[:220]}"
        if not positive and _VISA_POSITIVE.search(s):
            positive = s[:220]
    return (True, positive) if positive else (False, "not mentioned")


def load_uk_sponsor_register(path: str | Path | None) -> set[str]:
    """Names from the UK Home Office 'Register of licensed sponsors: workers' CSV (optional)."""
    if not path or not Path(path).exists():
        return set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        col = next((c for c in reader.fieldnames or [] if "organisation" in c.lower()), None)
        if not col:
            return set()
        return {_norm_company(row[col]) for row in reader if row.get(col)}


def _norm_company(name: str) -> str:
    name = re.sub(r"\b(ltd|limited|plc|llp|inc|uk|group|holdings|technologies|technology)\b\.?", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", name)


def on_uk_register(company: str, register: set[str]) -> bool | None:
    if not register:
        return None
    key = _norm_company(company)
    return any(key and (key == r or r.startswith(key)) for r in register)


# ---------------------------------------------------------------- recruiter contacts

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SKIP_EMAIL = re.compile(
    r"^(no-?reply|donotreply|do-not-reply|privacy|dataprotection|data-protection|gdpr|dpo|legal|security|"
    r"accommodations?|accessibility|reasonable-?accommodation|disability|fraud|abuse|support|help|info|press|media|"
    r"compliance|ethics|investors?)@",
    re.I,
)
_TEAM_EMAIL = re.compile(r"^(careers?|jobs|recruit(ing|ment|er)?|talent|hr|hiring|people|apply|work)[._-]?\w*@", re.I)


def recruiter_emails(text: str) -> list[str]:
    """Emails published in the official posting, excluding legal/privacy/accessibility inboxes."""
    found: list[str] = []
    for email in _EMAIL.findall(text or ""):
        email = email.rstrip(".").lower()
        if _SKIP_EMAIL.match(email) or email.endswith(("example.com", "sentry.io")) or email in found:
            continue
        found.append(email)
    return [f"{e} (team inbox)" if _TEAM_EMAIL.match(e) else e for e in found]
