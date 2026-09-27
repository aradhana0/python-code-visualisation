import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from job_tracker import classify, criteria, store
from job_tracker.cli import cmd_run
from job_tracker.models import Job
from job_tracker.sources import fetch_company
from job_tracker.sources.workday import posted_on_to_datetime

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime.now(timezone.utc)


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def ms(days_ago: float) -> int:
    return int((NOW - timedelta(days=days_ago)).timestamp() * 1000)


GREENHOUSE = {
    "jobs": [
        {   # Bangalore frontend, pay stated >= 60 LPA
            "title": "Senior Frontend Engineer",
            "location": {"name": "Bengaluru, India"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "first_published": iso(1),
            "content": "&lt;p&gt;Build React and TypeScript UIs. Compensation: 60-85 LPA. "
                       "Questions? Email priya.sharma@acme.com or privacy@acme.com&lt;/p&gt;",
        },
        {   # London fullstack with explicit sponsorship
            "title": "Full Stack Engineer",
            "location": {"name": "London, UK"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
            "first_published": iso(2),
            "content": "<p>React, TypeScript, Python and FastAPI. We offer visa sponsorship for this role. "
                       "Salary £85,000 - £105,000.</p>",
        },
        {   # London, but no sponsorship -> rejected
            "title": "Senior Frontend Engineer",
            "location": {"name": "London, UK"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/3",
            "first_published": iso(1),
            "content": "<p>React. We are unable to sponsor visas; you must have the right to work in the UK.</p>",
        },
        {   # too old
            "title": "Frontend Engineer",
            "location": {"name": "Bengaluru"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4",
            "first_published": iso(10),
            "content": "<p>React</p>",
        },
        {   # not a role we want
            "title": "Backend Engineer, Payments",
            "location": {"name": "Bengaluru"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/5",
            "first_published": iso(1),
            "content": "<p>Java</p>",
        },
    ]
}

LEVER = [
    {   # remote anywhere with USD pay -> converts above 60 LPA
        "text": "Senior Full-Stack Engineer",
        "categories": {"location": "Remote - Worldwide"},
        "workplaceType": "remote",
        "hostedUrl": "https://jobs.lever.co/beta/abc",
        "createdAt": ms(0.5),
        "descriptionPlain": "React, TypeScript, Node.js and Postgres. Careers: jobs@beta.io",
        "lists": [],
        "additionalPlain": "",
        "salaryRange": {"min": 90000, "max": 120000, "currency": "USD", "interval": "per-year-salary"},
    },
    {   # remote US only -> excluded from remote bucket
        "text": "Frontend Engineer",
        "categories": {"location": "Remote - US"},
        "workplaceType": "remote",
        "hostedUrl": "https://jobs.lever.co/beta/def",
        "createdAt": ms(1),
        "descriptionPlain": "React",
        "lists": [],
        "additionalPlain": "",
    },
    {   # Bangalore fullstack paying under the bar
        "text": "Full Stack Developer",
        "categories": {"location": "Bangalore"},
        "hostedUrl": "https://jobs.lever.co/beta/ghi",
        "createdAt": ms(1),
        "descriptionPlain": "React and Python. CTC 25-35 LPA.",
        "lists": [],
        "additionalPlain": "",
    },
]

ASHBY = {
    "jobs": [
        {   # Dubai with visa provided
            "title": "Senior Software Engineer",
            "location": "Dubai, United Arab Emirates",
            "publishedAt": iso(1),
            "jobUrl": "https://jobs.ashbyhq.com/gamma/1",
            "descriptionPlain": "You'll build React and TypeScript front ends and Python APIs. "
                                "Employment visa provided, plus relocation support.",
            "isListed": True,
        },
        {   # Berlin with Blue Card support
            "title": "Frontend Engineer (React)",
            "location": "Berlin, Germany",
            "publishedAt": iso(2),
            "jobUrl": "https://jobs.ashbyhq.com/gamma/2",
            "descriptionPlain": "React, TypeScript, design systems. We provide relocation and visa support including the EU Blue Card.",
            "isListed": True,
        },
    ]
}

SR_LIST = {"content": [
    {"id": "77", "name": "Senior UI Engineer", "releasedDate": iso(1),
     "location": {"city": "Bengaluru", "country": "in", "remote": False}},
    {"id": "88", "name": "Senior Frontend Engineer", "releasedDate": iso(1),
     "location": {"city": "Dubai", "country": "ae", "remote": False}},
], "totalFound": 2}
SR_DETAIL = {"jobAd": {"sections": {"jobDescription": {"text": "<p>React, Redux, Jest.</p>"}}}}
SR_DETAIL_TALABAT = {"jobAd": {"sections": {"jobDescription": {
    "text": "<p>Join talabat to build React and TypeScript apps. Visa sponsorship is provided.</p>"}}}}
WORKABLE = {"jobs": [{"title": "Senior Full Stack Engineer", "url": "https://apply.workable.com/zeta-uae/j/ABC123/",
                      "published_on": (NOW - timedelta(days=1)).date().isoformat(), "city": "Abu Dhabi",
                      "country": "United Arab Emirates", "telecommuting": False,
                      "description": "<p>React, Node.js and Python. We offer visa sponsorship and relocation.</p>"}]}

WORKDAY_LIST = {"jobPostings": [{"title": "Lead Frontend Engineer", "externalPath": "/job/Bangalore/Lead-FE_R1",
                                 "locationsText": "Bangalore, India", "postedOn": "Posted Yesterday"}]}
WORKDAY_DETAIL = {"jobPostingInfo": {"jobDescription": "<p>React TypeScript. Salary ₹65,00,000 – ₹90,00,000</p>",
                                     "location": "Bangalore, India", "startDate": (NOW - timedelta(days=1)).date().isoformat()}}


def fake_fetch(url, data=None, **_):
    if "greenhouse" in url:
        return GREENHOUSE
    if "lever.co" in url:
        return LEVER
    if "ashbyhq" in url:
        return ASHBY
    if "smartrecruiters" in url:
        if url.rstrip("/").endswith("/77"):
            return SR_DETAIL
        if url.rstrip("/").endswith("/88"):
            return SR_DETAIL_TALABAT
        return SR_LIST
    if "workable" in url:
        return WORKABLE
    if "myworkdayjobs" in url:
        if url.endswith("/jobs"):
            return WORKDAY_LIST if data["searchText"] == "frontend" else {"jobPostings": []}
        return WORKDAY_DETAIL
    raise AssertionError(url)


COMPANIES = """
[[company]]
name = "Acme"
ats = "greenhouse"
slug = "acme"
[[company]]
name = "Beta"
ats = "lever"
slug = "beta"
[[company]]
name = "Gamma"
ats = "ashby"
slug = "gamma"
[[company]]
name = "Delta"
ats = "smartrecruiters"
slug = "Delta"
brands = ["talabat"]
[[company]]
name = "Epsilon"
ats = "workday"
host = "eps.wd1.myworkdayjobs.com"
tenant = "eps"
site = "Ext"
[[company]]
name = "Zeta UAE"
ats = "workable"
slug = "zeta-uae"
[[company]]
name = "Adobe"
ats = "greenhouse"
slug = "adobe"
[[company]]
name = "Tabby"
ats = "unknown"
careers_url = "https://tabby.ai/careers"
"""


class CriteriaTests(unittest.TestCase):
    def test_pay_parsing(self):
        cases = {
            "CTC: 60-85 LPA": (60e5, 85e5, "INR"),
            "₹65,00,000 – ₹90,00,000 per annum": (65e5, 90e5, "INR"),
            "Up to 1.2 Cr": (1.2e7, 1.2e7, "INR"),
            "$150,000 - $190,000 USD": (150000, 190000, "USD"),
            "£85k–£100k": (85000, 100000, "GBP"),
        }
        for text, (lo, hi, cur) in cases.items():
            s = criteria.salary_from_text(text)
            self.assertIsNotNone(s, text)
            self.assertEqual((s.min, s.max, s.currency), (lo, hi, cur), text)
        self.assertIsNone(criteria.salary_from_text("We raised $5M and have 20 engineers."))

    def test_pay_threshold(self):
        job = Job("X", "t", "Bangalore", "u", NOW, "Salary 40-55 LPA", "greenhouse")
        self.assertEqual(criteria.check_pay(job, 60, {})[0], False)
        job = Job("X", "t", "Remote", "u", NOW, "Pay $80,000 - $100,000", "lever")
        ok, label = criteria.check_pay(job, 60, {"USD": 88})
        self.assertTrue(ok)
        self.assertIn("USD", label)
        job = Job("X", "t", "Bangalore", "u", NOW, "Great benefits", "lever")
        self.assertEqual(criteria.check_pay(job, 60, {}), (None, "undisclosed"))

    def test_visa(self):
        yes = [
            "We offer visa sponsorship for the right candidate.",
            "Visa sponsorship is available for this position.",
            "We can sponsor a Skilled Worker visa.",
            "Relocation and visa support provided.",
            "Employment visa provided for you and your family.",
        ]
        no = [
            "We are unable to sponsor visas for this role.",
            "Unfortunately we cannot offer visa sponsorship.",
            "Candidates must have the right to work in the UK. We offer great benefits.",
            "We have a great office.",
            "Visa sponsorship is not available.",
        ]
        for s in yes:
            self.assertTrue(criteria.visa_sponsorship(s)[0], s)
        for s in no:
            self.assertFalse(criteria.visa_sponsorship(s)[0], s)

    def test_recruiter_emails(self):
        text = "Contact priya.s@acme.com, careers@acme.com, accommodations@acme.com or no-reply@acme.com."
        self.assertEqual(criteria.recruiter_emails(text), ["priya.s@acme.com", "careers@acme.com (team inbox)"])

    def test_remote_scope(self):
        def job(loc, desc=""):
            return Job("X", "t", loc, "u", NOW, desc, "lever", remote=True)
        self.assertEqual(classify.remote_scope(job("Remote - Worldwide")), "anywhere")
        self.assertEqual(classify.remote_scope(job("Remote (India)")), "india/apac")
        self.assertEqual(classify.remote_scope(job("Remote - US")), "restricted")
        self.assertEqual(classify.remote_scope(job("Remote", "You must be located in the United States.")), "restricted")
        self.assertEqual(classify.remote_scope(job("Remote")), "unspecified")

    def test_workday_posted_on(self):
        self.assertEqual(posted_on_to_datetime("Posted Today", NOW), NOW)
        self.assertEqual(posted_on_to_datetime("Posted 3 Days Ago", NOW), NOW - timedelta(days=3))
        self.assertEqual(posted_on_to_datetime("Posted 30+ Days Ago", NOW), NOW - timedelta(days=30))


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "companies.toml").write_text(COMPANIES)
        self.args = SimpleNamespace(
            profile=str(ROOT / "profile.example.toml"), companies=str(self.dir / "companies.toml"),
            only=None, out=str(self.dir / "out"), days=None, workers=2, no_docs=False, pdf=False,
            overwrite_docs=False,
        )
        # The example profile excludes nothing; exclude "Adobe" like a real profile would.
        text = (ROOT / "profile.example.toml").read_text().replace("exclude_companies = []", 'exclude_companies = ["Adobe"]')
        (self.dir / "profile.toml").write_text(text)
        self.args.profile = str(self.dir / "profile.toml")

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, bucket):
        with open(self.dir / "out" / f"{bucket}.csv", newline="") as f:
            return list(csv.DictReader(f))

    def test_run_buckets_and_documents(self):
        cmd_run(self.args, fetch=fake_fetch)
        titles = {b: sorted(r["title"] for r in self.rows(b)) for b in classify.BUCKETS}
        self.assertEqual(titles["bangalore_frontend"], ["Lead Frontend Engineer", "Senior Frontend Engineer", "Senior UI Engineer"])
        self.assertEqual(titles["bangalore_fullstack"], [])  # 25-35 LPA job filtered out
        self.assertEqual(titles["remote"], ["Senior Full-Stack Engineer"])
        self.assertEqual(titles["uk"], ["Full Stack Engineer"])  # no-sponsorship job filtered out
        self.assertEqual(titles["uae"], ["Senior Frontend Engineer", "Senior Full Stack Engineer", "Senior Software Engineer"])
        uae = {r["title"]: r for r in self.rows("uae")}
        self.assertEqual(uae["Senior Frontend Engineer"]["company"], "talabat (Delta)")
        self.assertEqual(uae["Senior Full Stack Engineer"]["location"], "Abu Dhabi, United Arab Emirates")
        self.assertEqual(titles["europe"], ["Frontend Engineer (React)"])

        fe = {r["title"]: r for r in self.rows("bangalore_frontend")}
        self.assertEqual(fe["Senior Frontend Engineer"]["recruiter_emails"], "priya.sharma@acme.com")
        self.assertEqual(fe["Senior Frontend Engineer"]["pay"], "85 LPA")
        self.assertEqual(fe["Lead Frontend Engineer"]["pay"], "90 LPA")
        self.assertEqual(fe["Senior UI Engineer"]["pay_check"], "undisclosed")

        uk = self.rows("uk")[0]
        self.assertIn("visa sponsorship", uk["visa_sponsorship_evidence"])
        out = self.dir / "out"
        self.assertTrue((out / uk["resume"]).exists())
        letter = (out / uk["cover_letter"]).with_suffix(".md").read_text()
        self.assertIn("Full Stack Engineer role at Acme", letter)
        self.assertIn("visa sponsorship", letter)
        # Bangalore jobs get a resume but no cover letter
        self.assertEqual(fe["Senior Frontend Engineer"]["cover_letter"], "")
        self.assertTrue((out / "summary.md").exists())

    def test_rerun_keeps_user_columns(self):
        cmd_run(self.args, fetch=fake_fetch)
        path = self.dir / "out" / "uk.csv"
        rows = self.rows("uk")
        rows[0].update(status="applied", applied_on="2026-01-01", my_notes="spoke to recruiter")
        store.write_rows(path, rows)
        cmd_run(self.args, fetch=fake_fetch)
        row = self.rows("uk")[0]
        self.assertEqual((row["status"], row["applied_on"], row["my_notes"]), ("applied", "2026-01-01", "spoke to recruiter"))
        self.assertEqual(row["follow_up_on"], "2026-01-08")

    def test_all_connectors_parse(self):
        import tomllib
        companies = tomllib.loads(COMPANIES)["company"]
        for c in companies:
            if c["ats"] == "unknown":
                continue
            jobs = fetch_company(c, fake_fetch)
            self.assertTrue(jobs, c["name"])
            for j in jobs:
                self.assertTrue(j.url.startswith("https://"), j)


class DiscoverTests(unittest.TestCase):
    def test_detect(self):
        from job_tracker.discover import detect
        cases = {
            '<a href="https://job-boards.greenhouse.io/careem/jobs/123">': {"ats": "greenhouse", "slug": "careem"},
            '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme">': {"ats": "greenhouse", "slug": "acme"},
            'href="https://jobs.lever.co/beta/abc-123"': {"ats": "lever", "slug": "beta"},
            'href="https://jobs.eu.lever.co/beta/abc"': {"ats": "lever", "slug": "beta", "region": "eu"},
            'href="https://jobs.ashbyhq.com/tabby/9f1"': {"ats": "ashby", "slug": "tabby"},
            'href="https://apply.workable.com/noon/j/AB12/"': {"ats": "workable", "slug": "noon"},
            'href="https://jobs.smartrecruiters.com/DeliveryHero/744"': {"ats": "smartrecruiters", "slug": "DeliveryHero"},
            'href="https://acme.wd3.myworkdayjobs.com/en-US/Careers/job/X"':
                {"ats": "workday", "host": "acme.wd3.myworkdayjobs.com", "tenant": "acme", "site": "Careers"},
        }
        for html, want in cases.items():
            self.assertEqual(detect(html)[0], want, html)
        self.assertEqual(detect("<div id=root></div>"), [])

    def test_discover_write(self):
        from job_tracker.cli import cmd_discover
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "companies.toml"
            path.write_text(COMPANIES)
            args = SimpleNamespace(companies=str(path), only=None, url=None, name=None, write=True)
            page = '<a href="https://jobs.ashbyhq.com/tabby/1">Apply</a>'
            self.assertEqual(cmd_discover(args, get_page=lambda url: page), 0)
            import tomllib
            tabby = [c for c in tomllib.loads(path.read_text())["company"] if c["name"] == "Tabby"][0]
            self.assertEqual((tabby["ats"], tabby["slug"]), ("ashby", "tabby"))


if __name__ == "__main__":
    unittest.main()
