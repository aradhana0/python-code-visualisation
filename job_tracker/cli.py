from __future__ import annotations

import argparse
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import classify, criteria, documents, store
from .http import get_json
from .pipeline import Result, process
from .sources import fetch_company


def load_toml(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_companies(path: str, only: list[str] | None) -> list[dict]:
    companies = load_toml(path).get("company", [])
    if only:
        wanted = {o.lower() for o in only}
        companies = [c for c in companies if c["name"].lower() in wanted]
    return [c for c in companies if c.get("enabled", True)]


def fetch_all(companies: list[dict], workers: int, fetch=get_json):
    jobs, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_company, c, fetch): c for c in companies}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                found = fut.result()
                jobs.extend(found)
            except Exception as exc:
                errors.append(f"{c['name']} ({c['ats']}): {exc}")
    return jobs, errors


def cmd_run(args, fetch=get_json) -> int:
    profile = load_toml(args.profile)
    if args.days:
        profile["criteria"]["max_age_days"] = args.days
    companies = load_companies(args.companies, args.only)
    now = store.utcnow()
    out = Path(args.out)
    print(f"Fetching {len(companies)} companies from their official career-page APIs...", file=sys.stderr)
    jobs, errors = fetch_all(companies, args.workers, fetch)
    register = criteria.load_uk_sponsor_register(profile["criteria"].get("uk_sponsor_register_csv"))

    result = Result()
    result.errors.extend(errors)
    process(jobs, profile, now, register, result)

    letters_for = set(profile["criteria"].get("cover_letter_for", ["uae", "uk", "europe"]))
    apps = out / "applications"
    needs_letter = {id(j) for b in letters_for for j in result.buckets.get(b, [])}
    new_counts, all_rows = {}, {}
    for bucket in classify.BUCKETS:
        fresh_rows = []
        for job in result.buckets[bucket]:
            resume = letter = ""
            if not args.no_docs:
                rp, lp = documents.write_documents(
                    profile, job, apps, cover_letter=id(job) in needs_letter, pdf=args.pdf, overwrite=args.overwrite_docs,
                )
                resume = str(rp.relative_to(out))
                letter = str(lp.relative_to(out)) if lp else ""
            hit = criteria.on_uk_register(job.company, register) if bucket == "uk" else None
            fresh_rows.append(store.job_row(job, resume, letter, now, hit))
        path = out / f"{bucket}.csv"
        existing = store.read_rows(path)
        known = {r["official_url"] for r in existing}
        rows = store.merge(existing, fresh_rows, int(profile["criteria"]["max_age_days"]), now.date())
        store.write_rows(path, rows)
        new_counts[bucket] = sum(1 for r in fresh_rows if r["official_url"] not in known)
        all_rows[bucket] = rows

    summary = render_summary(all_rows, new_counts, result, len(jobs), now)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


def render_summary(all_rows, new_counts, result: Result, fetched: int, now) -> str:
    lines = [f"# Job tracker run — {now:%Y-%m-%d %H:%M} UTC", "", f"Postings scanned: {fetched}", "",
             "| Bucket | Rows | New this run |", "|---|---:|---:|"]
    for bucket in classify.BUCKETS:
        lines.append(f"| {bucket} | {len(all_rows[bucket])} | {new_counts[bucket]} |")
    top = sorted((r for rows in all_rows.values() for r in rows if r.get("status") == "new"),
                 key=lambda r: -int(r.get("match_score") or 0))[:15]
    if top:
        lines += ["", "## Top matches", ""]
        lines += [f"- **{r['match_score']}** — {r['title']} @ {r['company']} ({r['location']}) — {r['pay_check']} — {r['official_url']}" for r in top]
    due = [r for rows in all_rows.values() for r in store.follow_ups_due(rows, now.date())]
    if due:
        lines += ["", "## Follow-ups due", ""]
        lines += [f"- {r['title']} @ {r['company']} (applied {r['applied_on']}) — {r['recruiter_emails'] or r['official_url']}" for r in due]
    if result.rejected:
        lines += ["", "## Filtered out", ""]
        lines += [f"- {reason}: {n}" for reason, n in result.rejected.most_common()]
    if result.errors:
        lines += ["", "## Source errors (check slugs in companies.toml)", ""]
        lines += [f"- {e}" for e in result.errors]
    return "\n".join(lines) + "\n"


def cmd_check(args, fetch=get_json) -> int:
    companies = load_companies(args.companies, args.only)
    bad = 0
    for c in companies:
        try:
            n = len(fetch_company(c, fetch))
            print(f"OK    {c['name']:<28} {c['ats']:<16} {n} postings")
        except Exception as exc:
            bad += 1
            print(f"FAIL  {c['name']:<28} {c['ats']:<16} {exc}")
    print(f"\n{len(companies) - bad}/{len(companies)} sources reachable")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m job_tracker", description=__doc__)
    p.add_argument("--profile", default="profile.toml")
    p.add_argument("--companies", default="companies.toml")
    p.add_argument("--only", action="append", help="limit to a company name (repeatable)")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="fetch, filter, write CSVs and tailored documents")
    run.add_argument("--out", default="output")
    run.add_argument("--days", type=int, help="override max_age_days")
    run.add_argument("--workers", type=int, default=8)
    run.add_argument("--no-docs", action="store_true", help="skip resume/cover letter generation")
    run.add_argument("--pdf", action="store_true", help="also print documents to PDF with a local Chrome/Chromium")
    run.add_argument("--overwrite-docs", action="store_true", help="regenerate documents even if the folder exists")
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check-sources", help="verify every company in companies.toml is reachable")
    check.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)
