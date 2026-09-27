"""Match score: how much of a job's tech stack the candidate already covers."""
from __future__ import annotations

import re

from .models import Job

# canonical skill -> regex. Covers the common vocabulary of frontend/fullstack JDs so we
# can report both what matches and what is missing from the candidate's profile.
VOCABULARY: dict[str, str] = {
    "React": r"\breact(\.?js)?\b",
    "TypeScript": r"\btypescript\b",
    "JavaScript": r"\bjavascript\b|\bes6\b|\becmascript\b",
    "Next.js": r"\bnext\.?js\b",
    "Redux": r"\bredux\b",
    "React Query": r"\breact query\b|\btanstack\b",
    "Zustand": r"\bzustand\b",
    "HTML/CSS": r"\bhtml5?\b|\bcss3?\b",
    "Tailwind": r"\btailwind\b",
    "Micro-frontends": r"micro[\s-]?frontends?",
    "Design systems": r"design systems?|component librar(y|ies)",
    "Web performance": r"web vitals|web performance|frontend performance|performance optimi[sz]ation",
    "Accessibility": r"\baccessibility\b|\bwcag\b|\ba11y\b",
    "Angular": r"\bangular\b",
    "Vue": r"\bvue(\.?js)?\b",
    "Svelte": r"\bsvelte\b",
    "GraphQL": r"\bgraphql\b",
    "REST APIs": r"\brest(ful)?\b|\bapis?\b",
    "Node.js": r"\bnode(\.?js)?\b",
    "Python": r"\bpython\b",
    "FastAPI": r"\bfastapi\b",
    "Django": r"\bdjango\b",
    "Go": r"\bgolang\b|(?-i:\bGo\b)",
    "Java": r"\bjava\b",
    "SQL/Postgres": r"\bsql\b|\bpostgres(ql)?\b|\bmysql\b",
    "MongoDB": r"\bmongo(db)?\b",
    "AWS": r"\baws\b|amazon web services",
    "GCP": r"\bgcp\b|google cloud",
    "Azure": r"\bazure\b",
    "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b",
    "CI/CD": r"\bci/cd\b|\bcontinuous (integration|delivery)\b",
    "Jest": r"\bjest\b",
    "React Testing Library": r"testing library",
    "Cypress": r"\bcypress\b",
    "Playwright": r"\bplaywright\b",
    "LLMs": r"\bllms?\b|large language models?|generative ai|\bgenai\b",
    "AI agents": r"\bagentic\b|\bai agents?\b|\bllm agents?\b",
    "MCP": r"\bmcp\b|model context protocol",
    "Electron": r"\belectron\b",
    "System design": r"system design|architecture|architect",
    "Fintech": r"\bfintech\b|payments?\b|banking",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in VOCABULARY.items()}


def skills_in(text: str) -> list[str]:
    return [skill for skill, rx in _COMPILED.items() if rx.search(text or "")]


def score(job: Job, candidate_skills: list[str]) -> None:
    """Populate job.match_score / matched_skills / missing_skills."""
    wanted = skills_in(f"{job.title}\n{job.description}")
    have = {s.lower() for s in candidate_skills}
    matched = [s for s in wanted if s.lower() in have]
    missing = [s for s in wanted if s.lower() not in have]
    base = 100 * len(matched) / len(wanted) if wanted else 50
    # Titles that name the candidate's core stack are a stronger signal than body text.
    if re.search(r"front[\s-]?end|full[\s-]?stack|react|ui engineer", job.title, re.I):
        base += 10
    if re.search(r"\b(senior|staff|lead|principal|sde[\s-]?(3|iii)|sr\.?)\b", job.title, re.I):
        base += 5
    job.match_score = max(0, min(100, round(base)))
    job.matched_skills = matched
    job.missing_skills = missing
