"""Per-job tailored resume and cover letter.

Tailoring only *reorders and selects* the candidate's own content (headline, skills,
bullets) by relevance to the job description. Nothing is invented.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import shutil
import subprocess
from pathlib import Path

from .models import Job
from .scoring import VOCABULARY
from .text import slugify

_WORD = re.compile(r"[a-z][a-z0-9+#.]{2,}")
_STOP = set(
    "the and for with from that this you your our are will have has was were been into across over under "
    "their they them who what when where which while about through within using used use build built "
    "team teams work working role company experience years strong ability skills including".split()
)


def _relevance(text: str, job: Job) -> float:
    jd = f"{job.title}\n{job.description}".lower()
    score = 0.0
    for skill in job.matched_skills:
        if re.search(VOCABULARY[skill], text, re.I):
            score += 3
    jd_words = set(_WORD.findall(jd)) - _STOP
    score += 0.3 * len(set(_WORD.findall(text.lower())) & jd_words)
    return score


def _ranked(items: list[str], job: Job) -> list[str]:
    # stable sort keeps the author's order among equally relevant items
    return sorted(items, key=lambda t: -_relevance(t, job))


def _matched_first(items: list[str], job: Job) -> list[str]:
    """Skills named in the JD move to the front; otherwise the author's order is kept."""
    def hit(item: str) -> bool:
        return any(re.search(VOCABULARY[s], item, re.I) for s in job.matched_skills)
    return sorted(items, key=lambda t: not hit(t))


def job_folder(root: Path, job: Job) -> Path:
    digest = hashlib.sha1(job.key.encode()).hexdigest()[:6]
    return root / f"{slugify(job.company, 30)}__{slugify(job.title, 50)}__{digest}"


# ---------------------------------------------------------------- resume


def tailor_resume(profile: dict, job: Job) -> dict:
    cand, res = profile["candidate"], profile["resume"]
    headline = cand["headline_frontend"] if job.role_type == "frontend" else cand["headline_fullstack"]

    skills = []
    for group in res.get("skills", []):
        items = _matched_first(group["items"], job)
        skills.append({"category": group["category"], "items": items, "rel": sum(_relevance(i, job) for i in items)})
    # Keep the first category (core stack) on top, reorder the rest by relevance.
    if skills:
        skills = skills[:1] + sorted(skills[1:], key=lambda g: -g["rel"])

    experience = []
    for role in res.get("experience", []):
        sections = [
            {"name": s.get("name", ""), "bullets": _ranked(s["bullets"], job)} for s in role.get("sections", [])
        ]
        sections.sort(key=lambda s: -sum(_relevance(b, job) for b in s["bullets"]))
        experience.append({**role, "sections": sections})

    projects = res.get("projects", [])  # a project reads as a story; keep its bullet order
    return {
        "candidate": cand,
        "headline": headline,
        "summary": res.get("summary", ""),
        "strengths": _ranked(res.get("strengths", []), job)[:4],
        "skills": skills,
        "experience": experience,
        "projects": projects,
        "education": res.get("education", []),
        "certifications": (res.get("certifications") or {}).get("items", []),
    }


def _contact_line(cand: dict) -> list[tuple[str, str | None]]:
    parts: list[tuple[str, str | None]] = []
    if cand.get("open_to_relocation"):
        parts.append(("Open to Relocation", None))
    for key, label in (("location", None), ("email", None), ("phone", None), ("linkedin", "LinkedIn"), ("portfolio", "Portfolio")):
        value = cand.get(key)
        if not value:
            continue
        if key == "email":
            parts.append((value, f"mailto:{value}"))
        elif label:
            parts.append((label, value))
        else:
            parts.append((value, None))
    return parts


def resume_markdown(r: dict) -> str:
    cand = r["candidate"]
    contact = " | ".join(f"[{t}]({u})" if u else t for t, u in _contact_line(cand))
    out = [f"# {cand['name']}", f"**{r['headline']}**", "", contact, "", "## Professional Summary", r["summary"], ""]
    if r["strengths"]:
        out += ["## Core Strengths", *[f"- {s}" for s in r["strengths"]], ""]
    out.append("## Technical Skills")
    out += [f"- **{g['category']}:** {', '.join(g['items'])}" for g in r["skills"]]
    out += ["", "## Professional Experience"]
    for role in r["experience"]:
        out += ["", f"### {role['title']}, {role['company']} — {role['dates']}"]
        for sec in role["sections"]:
            if sec["name"]:
                out += ["", f"*{sec['name']}*", ""]
            out += [f"- {b}" for b in sec["bullets"]]
    for p in r["projects"]:
        out += ["", "## AI Product — Personal Project", f"### {p['name']} — {p.get('tagline', '')}".rstrip(" —")]
        if p.get("stack"):
            out += [f"*Stack: {p['stack']}*", ""]
        out += [f"- {b}" for b in p["bullets"]]
    out += ["", "## Education"]
    out += [f"- {e['degree']} — {e['school']} ({e['dates']})" for e in r["education"]]
    if r["certifications"]:
        out += ["", "## Certifications", *[f"- {c}" for c in r["certifications"]]]
    return "\n".join(out).strip() + "\n"


_CSS = """
@page { size: A4; margin: 14mm 14mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1a1a1a; font-size: 10.5pt;
       line-height: 1.38; max-width: 800px; margin: 24px auto; padding: 0 16px; background: #fff; }
h1 { font-size: 20pt; margin: 0; letter-spacing: .5px; }
.headline { font-weight: 600; color: #333; margin: 2px 0 4px; }
.contact { color: #444; font-size: 9.5pt; }
.contact a { color: #1f4e79; text-decoration: none; }
h2 { font-size: 10.5pt; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #999;
     padding-bottom: 2px; margin: 14px 0 6px; color: #1f4e79; }
h3 { font-size: 10.5pt; margin: 8px 0 2px; display: flex; justify-content: space-between; gap: 12px; }
h3 .dates { font-weight: normal; color: #444; white-space: nowrap; }
.sub { font-style: italic; color: #333; margin: 4px 0 2px; }
ul { margin: 2px 0 4px 18px; padding: 0; }
li { margin: 1px 0; }
p { margin: 4px 0; }
@media print { body { margin: 0; max-width: none; } }
"""


def _e(s: str) -> str:
    return html.escape(s or "")


def resume_html(r: dict) -> str:
    cand = r["candidate"]
    contact = " | ".join(f'<a href="{_e(u)}">{_e(t)}</a>' if u else _e(t) for t, u in _contact_line(cand))
    b = [f"<h1>{_e(cand['name'])}</h1>", f'<div class="headline">{_e(r["headline"])}</div>', f'<div class="contact">{contact}</div>']
    b += ["<h2>Professional Summary</h2>", f"<p>{_e(r['summary'])}</p>"]
    if r["strengths"]:
        b += ["<h2>Core Strengths</h2><ul>", *[f"<li>{_e(s)}</li>" for s in r["strengths"]], "</ul>"]
    b.append("<h2>Technical Skills</h2><ul>")
    b += [f"<li><b>{_e(g['category'])}:</b> {_e(', '.join(g['items']))}</li>" for g in r["skills"]]
    b.append("</ul><h2>Professional Experience</h2>")
    for role in r["experience"]:
        b.append(f'<h3><span>{_e(role["title"])}, {_e(role["company"])}</span><span class="dates">{_e(role["dates"])}</span></h3>')
        for sec in role["sections"]:
            if sec["name"]:
                b.append(f'<div class="sub">{_e(sec["name"])}</div>')
            b += ["<ul>", *[f"<li>{_e(x)}</li>" for x in sec["bullets"]], "</ul>"]
    for p in r["projects"]:
        b += ["<h2>AI Product — Personal Project</h2>", f"<h3><span>{_e(p['name'])} — {_e(p.get('tagline', ''))}</span></h3>"]
        if p.get("stack"):
            b.append(f'<div class="sub">Stack: {_e(p["stack"])}</div>')
        b += ["<ul>", *[f"<li>{_e(x)}</li>" for x in p["bullets"]], "</ul>"]
    b.append("<h2>Education</h2><ul>")
    b += [f"<li>{_e(e['degree'])} — {_e(e['school'])} <span class=dates>({_e(e['dates'])})</span></li>" for e in r["education"]]
    b.append("</ul>")
    if r["certifications"]:
        b += ["<h2>Certifications</h2><ul>", *[f"<li>{_e(c)}</li>" for c in r["certifications"]], "</ul>"]
    return _page(f"{cand['name']} — Resume", "\n".join(b))


def _page(title: str, body: str) -> str:
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_e(title)}</title>'
        f"<style>{_CSS}</style></head><body>\n{body}\n</body></html>\n"
    )


# ---------------------------------------------------------------- cover letter


def _as_sentence(bullet: str) -> str:
    text = bullet.strip().rstrip(".")
    return text[0].lower() + text[1:] if text[:1].isupper() and not text[1:2].isupper() else text


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" and {items[-1]}"


def _city(job: Job) -> str:
    first = re.split(r"[|;]", job.location or "")[0]
    return first.split(",")[0].strip() or job.location


def cover_letter_paragraphs(profile: dict, job: Job, resume: dict) -> list[str]:
    cand, cl = profile["candidate"], profile.get("cover_letter", {})
    kind = "frontend" if job.role_type == "frontend" else "full-stack"
    stack = cl.get(f"stack_{job.role_type}") or cl.get("stack_fullstack", "")
    intro = f"I am writing to apply for the {job.title} role at {job.company}. I am a {kind} engineer with {cand.get('years_experience')} years of experience"
    intro += f" building production products with {stack}" if stack else ""
    intro += f", {cl['current_role_proof']}." if cl.get("current_role_proof") else "."
    paras = [intro]

    ranked = sorted(
        ((_relevance(b, job), role["company"], b) for role in resume["experience"] for sec in role["sections"] for b in sec["bullets"]),
        key=lambda t: -t[0],
    )
    if ranked:
        first = ranked[0]
        # Prefer a second example from a different employer to show range.
        second = next((r for r in ranked[1:] if r[1] != first[1]), ranked[1] if len(ranked) > 1 else None)
        text = f"Some of the work I would bring: at {first[1]}, I {_as_sentence(first[2])}."
        if second:
            text += f" At {second[1]}, I {_as_sentence(second[2])}."
        paras.append(text)

    if job.matched_skills:
        text = f"The role's focus on {_join(job.matched_skills[:5])} maps directly to what I do day to day."
        if cl.get("working_style"):
            text += f" {cl['working_style']}"
        paras.append(text)

    if cl.get("ai_paragraph") and re.search(r"\b(ai|llm|llms|genai|generative|agent|agentic|copilot)\b", job.description, re.I):
        paras.append(cl["ai_paragraph"])

    visa = " I noted that the role offers visa sponsorship, which I would need." if job.visa_evidence else ""
    paras.append(
        f"I am currently based in {cand.get('location', '')} and am ready to relocate to {_city(job)}.{visa} "
        f"I would welcome the chance to talk about how I could contribute to {job.company}. Thank you for your time and consideration."
    )
    return paras


def cover_letter_markdown(profile: dict, job: Job, paras: list[str]) -> str:
    cand = profile["candidate"]
    head = [cand["name"], cand.get("email", ""), cand.get("linkedin", "")]
    return "\n".join(
        ["  \n".join(h for h in head if h), "", f"Dear {job.company} Hiring Team,", "", *[p + "\n" for p in paras], "Kind regards,  ", cand["name"]]
    ) + "\n"


def cover_letter_html(profile: dict, job: Job, paras: list[str]) -> str:
    cand = profile["candidate"]
    contact = " | ".join(f'<a href="{_e(u)}">{_e(t)}</a>' if u else _e(t) for t, u in _contact_line(cand))
    body = [f"<h1>{_e(cand['name'])}</h1>", f'<div class="contact">{contact}</div>', "<br>",
            f"<p>Dear {_e(job.company)} Hiring Team,</p>", *[f"<p>{_e(p)}</p>" for p in paras],
            f"<p>Kind regards,<br>{_e(cand['name'])}</p>"]
    return _page(f"{cand['name']} — Cover letter — {job.company}", "\n".join(body))


# ---------------------------------------------------------------- notes + pdf


def job_notes(job: Job) -> str:
    return "\n".join([
        f"# {job.title} — {job.company}",
        "",
        f"- **Official posting:** {job.url}",
        f"- **Location:** {job.location}",
        f"- **Posted:** {job.posted_at:%Y-%m-%d}" if job.posted_at else "- **Posted:** unknown",
        f"- **Pay:** {job.pay_check}",
        f"- **Visa sponsorship evidence:** {job.visa_evidence or 'n/a'}",
        f"- **Recruiter email(s):** {', '.join(job.recruiter_emails) or 'none published — apply via the official link'}",
        f"- **Match score:** {job.match_score}",
        f"- **Matched skills:** {', '.join(job.matched_skills) or '-'}",
        f"- **Skills in JD you don't list:** {', '.join(job.missing_skills) or '-'} "
        "(add them to the resume only if you genuinely have them)",
        *(f"- **Note:** {n}" for n in job.notes),
        "",
        "## Job description (as published)",
        "",
        job.description,
        "",
    ])


def _chrome() -> str | None:
    candidates = [os.environ.get("CHROME_PATH"), "chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/opt/pw-browsers/chromium"]
    for c in candidates:
        if c and (shutil.which(c) or (os.path.isfile(c) and os.access(c, os.X_OK))):
            return shutil.which(c) or c
    return None


def html_to_pdf(html_path: Path) -> Path | None:
    chrome = _chrome()
    if not chrome:
        return None
    pdf = html_path.with_suffix(".pdf")
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf}", html_path.resolve().as_uri()],
        check=False, capture_output=True, timeout=60,
    )
    return pdf if pdf.exists() else None


def write_documents(profile: dict, job: Job, root: Path, *, cover_letter: bool, pdf: bool, overwrite: bool) -> tuple[Path, Path | None]:
    """Write resume (+ cover letter) for a job. Existing folders are left alone unless overwrite=True,
    so manual edits to generated documents survive re-runs."""
    folder = job_folder(root, job)
    resume_path = folder / "resume.html"
    letter_path = folder / "cover_letter.html"
    if folder.exists() and not overwrite:
        return resume_path, (letter_path if letter_path.exists() else None)
    folder.mkdir(parents=True, exist_ok=True)

    tailored = tailor_resume(profile, job)
    (folder / "resume.md").write_text(resume_markdown(tailored), encoding="utf-8")
    resume_path.write_text(resume_html(tailored), encoding="utf-8")
    (folder / "job_notes.md").write_text(job_notes(job), encoding="utf-8")
    written = [resume_path]
    if cover_letter:
        paras = cover_letter_paragraphs(profile, job, tailored)
        (folder / "cover_letter.md").write_text(cover_letter_markdown(profile, job, paras), encoding="utf-8")
        letter_path.write_text(cover_letter_html(profile, job, paras), encoding="utf-8")
        written.append(letter_path)
    if pdf:
        for path in written:
            html_to_pdf(path)
    return resume_path, (letter_path if cover_letter else None)
