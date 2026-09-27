# Job tracker

Scans the **official career pages** of a list of companies, filters postings against a
candidate profile, and writes one CSV per target market, plus a tailored resume (and a
cover letter for international roles) for every match.

No dependencies beyond Python 3.11+. PDF output uses a local Chrome/Chromium if one is installed.

## Output

| File | What's in it | Hard criteria |
|---|---|---|
| `output/bangalore_frontend.csv` | Frontend roles in Bengaluru | pay ≥ `min_pay_lpa` |
| `output/bangalore_fullstack.csv` | Full-stack roles in Bengaluru | pay ≥ `min_pay_lpa` |
| `output/remote.csv` | Remote roles open to candidates in India/anywhere | pay ≥ `min_pay_lpa` (converted from USD/EUR/GBP) |
| `output/uae.csv` | Frontend + full-stack roles in the UAE | visa sponsorship explicitly stated |
| `output/uk.csv` | Frontend + full-stack roles in the UK | visa sponsorship explicitly stated |
| `output/europe.csv` | Frontend + full-stack roles in the EU, EEA and Switzerland | visa sponsorship explicitly stated |

All buckets: posted within `max_age_days` (default 3), and the title must be a frontend or full-stack role. A generic "Software Engineer" title counts if its description is React-heavy.

Each row has: match score, the skills it matched, the JD skills you don't list, pay and how it was checked, the sentence proving sponsorship, recruiter emails, the official URL, links to the generated documents, and a UK sponsor-register check when it's configured.
You edit `status`, `applied_on`, `follow_up_on` and `my_notes`. Re-runs never overwrite these columns, and `follow_up_on` defaults to 7 days after `applied_on`.

`output/summary.md` lists new top matches, follow-ups that are due, why jobs were filtered out, and any company sources that failed.

`output/applications/<company>__<role>__<id>/` contains `resume.{md,html,pdf}`, `cover_letter.{md,html,pdf}` (UAE, UK and Europe only), and `job_notes.md`, which holds the full job description as published.
Existing folders are never overwritten, so you can hand-edit documents safely. Pass `--overwrite-docs` to regenerate them.

## How the criteria are checked

- **Official sources only.** Each company in `companies.toml` points at the public API behind its own careers site: Greenhouse, Lever, Ashby, SmartRecruiters or Workday. The URL in every CSV row is the employer's own posting.
- **Freshness** is the posting's publish date from the API. A job without a date is skipped.
- **Pay** comes from the structured salary field when the employer publishes one. Otherwise it is parsed from the text: `60-85 LPA`, `₹65,00,000`, `1.2 Cr`, `$150k`, `£85,000`.
  Most Indian postings don't publish pay, so `allow_undisclosed_pay = true` keeps those jobs with `pay_check = undisclosed`. Set it to `false` for strict mode.
  A published pay below the bar is always dropped.
- **Visa sponsorship** must be stated in the posting: for example "we offer visa sponsorship", "Skilled Worker visa", "relocation and visa support" or "employment visa provided".
  Any negative wording drops the job, even if positive wording is also present. Examples: "unable to sponsor", "must have the right to work".
  For the UK, you can also point `uk_sponsor_register_csv` at the Home Office "Register of licensed sponsors: workers" CSV, which is published on gov.uk.
- **Recruiter emails** are only ones printed in the posting itself. Privacy, legal and accessibility inboxes are excluded, and no addresses are guessed.
- **Tailoring** reorders your own headline, skills and bullets by relevance to the job. It never adds anything you didn't write.

## Usage

```bash
cp profile.example.toml profile.toml    # fill in (gitignored - never committed)
python -m job_tracker check-sources     # verify every company slug in companies.toml
python -m job_tracker run --pdf         # fetch, filter, write CSVs + documents
python -m job_tracker --only Stripe run --days 7
python -m unittest discover -s tests    # offline tests
```

Run it daily, for example with cron: `0 8 * * * cd /path/to/repo && python3 -m job_tracker run --pdf`.

## Adding companies

The list in `companies.toml` is a starter list, and its slugs are unverified. Run `check-sources` and fix or disable any that fail.
To add a company, open its careers page, look at where the "Apply" link goes, and copy the slug. The top of `companies.toml` explains how.
