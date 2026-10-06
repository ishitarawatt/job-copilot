"""LLM clients. A real Anthropic-backed client and a deterministic offline mock.

Agents never import a provider SDK directly; they depend on the `LLMClient`
protocol, which keeps the system testable and the provider swappable.
"""
from __future__ import annotations

import json
import os
import re
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, role: str, system: str, user: str) -> str: ...


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group(0))


class AnthropicClient:
    """Thin wrapper over the Anthropic Messages API."""

    def __init__(self, model: str | None = None, max_tokens: int = 2000):
        import anthropic  # imported lazily so the mock path needs no dependency

        self._client = anthropic.Anthropic()
        self.model = model or os.getenv("COPILOT_MODEL", "claude-sonnet-5-5")
        self.max_tokens = max_tokens

    def complete(self, role: str, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


# --------------------------------------------------------------------------- #
# Offline mock: keyword heuristics so the whole pipeline + evals run with no key.
# --------------------------------------------------------------------------- #
SKILL_VOCAB = [
    "python", "sql", "java", "javascript", "typescript", "react", "aws", "gcp",
    "azure", "docker", "kubernetes", "machine learning", "llm", "prompt engineering",
    "product management", "roadmapping", "a/b testing", "experimentation",
    "data analysis", "tableau", "stakeholder management", "agile", "scrum",
    "okrs", "user research", "go-to-market", "evals", "rag", "api design",
    "leadership", "communication", "excel", "figma", "analytics",
]
SENIORITY = [("principal", "principal"), ("staff", "staff"), ("senior", "senior"),
             ("lead", "lead"), ("junior", "junior"), ("intern", "intern")]


def _find_skills(text: str) -> list[str]:
    low = text.lower()
    return [s for s in SKILL_VOCAB if re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z])", low)]


class MockClient:
    """Deterministic stand-in for an LLM.

    `fabricate_first_n` makes the tailor invent a bullet on its first N calls so
    the critic / retry / escalation path can be exercised in tests.
    """

    def __init__(self, fabricate_first_n: int = 0, inflate_first_n: int = 0):
        self.fabricate_first_n = fabricate_first_n
        self.inflate_first_n = inflate_first_n   # strengthen a verb ("Owned" -> "Led") on the first N calls
        self.tailor_calls = 0

    def complete(self, role: str, system: str, user: str) -> str:
        payload = json.loads(user)
        handler = getattr(self, f"_{role}", None)
        if handler is None:
            raise ValueError(f"mock has no handler for role {role!r}")
        return json.dumps(handler(payload))

    def _analyzer(self, p: dict) -> dict:
        jd = p["job_description"]
        low = jd.lower()
        required, nice = [], []
        # Split on "nice to have"/"preferred" so the two buckets differ.
        parts = re.split(r"nice to have|preferred|bonus", low, maxsplit=1)
        required = _find_skills(parts[0])
        if len(parts) > 1:
            nice = [s for s in _find_skills(parts[1]) if s not in required]
        title = next((l.strip() for l in jd.splitlines() if l.strip()), "Unknown role")[:80]
        seniority = next((v for k, v in SENIORITY if k in low), "mid")
        resp = [l.strip("-• ").strip() for l in jd.splitlines()
                if l.strip().startswith(("-", "•")) and len(l) > 20][:5]
        return {"title": title, "required_skills": required, "nice_to_have": nice,
                "seniority": seniority, "key_responsibilities": resp}

    def _tailor(self, p: dict) -> dict:
        self.tailor_calls += 1
        resume, analysis = p["resume"], p["analysis"]
        want = [s.lower() for s in analysis["required_skills"] + analysis["nice_to_have"]]
        have_blob = " ".join(resume["bullets"] + resume["skills"]).lower()
        have_skills = [s for s in analysis["required_skills"] if s.lower() in have_blob]
        gaps = [s for s in analysis["required_skills"] if s.lower() not in have_blob]

        def score(b: str) -> int:
            return sum(1 for s in want if s in b.lower())

        bullets = sorted(resume["bullets"], key=score, reverse=True)
        if self.tailor_calls <= self.fabricate_first_n:
            bullets = ["Led a 40-person team to deliver a $12M revenue increase"] + bullets
        if self.tailor_calls <= self.inflate_first_n and bullets:
            first, _, rest = bullets[0].partition(" ")
            bullets = [f"Led {rest}".strip()] + bullets[1:]   # same facts, bigger claim
        top = ", ".join(have_skills[:3]) if have_skills else "relevant experience"
        summary = f"{resume.get('summary', '').strip()} Focused on {top} for the {analysis['title']} role.".strip()
        return {"summary": summary, "bullets": bullets, "matched_skills": have_skills, "gaps": gaps}

    def _coach(self, p: dict) -> dict:
        analysis, gaps = p["analysis"], p["gaps"]
        qs = []
        strengths = [s for s in analysis["required_skills"] if s not in gaps] or analysis["required_skills"]
        for skill in strengths[:5]:
            qs.append({
                "question": f"Tell me about a time you used {skill} to deliver a measurable outcome.",
                "why_asked": f"{skill} is a stated requirement.",
                "tip": "Use situation, action, result. Quantify the result using only real numbers.",
            })
        qs.append({
            "question": "Why this role, and why now?",
            "why_asked": "Tests motivation and role understanding.",
            "tip": f"Tie your answer to the {analysis['seniority']}-level responsibilities in the posting.",
        })
        points = [f"Be upfront that {g} is newer for you; describe how you would ramp up in 30 days." for g in gaps]
        return {"questions": qs, "gap_talking_points": points}
