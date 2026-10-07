"""ATS-style readiness estimate: a deterministic 0-100 score for the *verified* tailored resume.

This is code, not a model, and it never gates anything: it only reports. It is a heuristic about the things most
applicant tracking systems and recruiters scan for, not the score any real ATS would give. Keywords only count when
they are real evidence in the resume text, so the score cannot be raised by stuffing in skills you do not have.
"""
from __future__ import annotations

import re

from .guardrails import skill_in_text
from .schemas import JobAnalysis, TailoredResume

# (id, label, max points). Weights sum to 100.
PARTS = (("keywords", "Required keywords", 50), ("nice", "Nice-to-have keywords", 10),
         ("results", "Measurable results", 15), ("structure", "Structure", 15), ("clarity", "Bullet length", 10))
MIN_BULLETS, MAX_BULLETS = 3, 15
MIN_WORDS, MAX_WORDS = 8, 30
RESULTS_TARGET = 0.5      # half the bullets with a number earns full marks


def _words(s: str) -> int:
    return len(re.findall(r"\S+", s))


def _r(x: float) -> int:
    """Round half up (Python's round() is banker's rounding; the demo's JS port uses Math.floor(x + .5))."""
    return int(x + 0.5)


def ats_score(tailored: TailoredResume, analysis: JobAnalysis) -> dict:
    text = " ".join([tailored.summary, *tailored.bullets, *tailored.matched_skills])
    bullets = tailored.bullets
    n = len(bullets)

    req = analysis.required_skills
    req_hit = [s for s in req if skill_in_text(s, text)]
    nice = analysis.nice_to_have
    nice_hit = [s for s in nice if skill_in_text(s, text)]
    with_number = sum(1 for b in bullets if re.search(r"\d", b))
    ok_len = sum(1 for b in bullets if MIN_WORDS <= _words(b) <= MAX_WORDS)

    pts = {
        "keywords": 50 * len(req_hit) / len(req) if req else 0,
        "nice": 10 * len(nice_hit) / len(nice) if nice else 10,
        "results": 15 * min(1.0, (with_number / n) / RESULTS_TARGET) if n else 0,
        "structure": 5 * bool(tailored.summary.strip()) + 5 * bool(tailored.matched_skills)
                     + 5 * (MIN_BULLETS <= n <= MAX_BULLETS),
        "clarity": 10 * ok_len / n if n else 0,
    }
    notes = {
        "keywords": f"{len(req_hit)} of {len(req)} required skills appear in your resume",
        "nice": f"{len(nice_hit)} of {len(nice)} nice-to-have skills appear" if nice else "none listed in the posting",
        "results": f"{with_number} of {n} bullets contain a number",
        "structure": f"summary {'yes' if tailored.summary.strip() else 'no'}, skills {'yes' if tailored.matched_skills else 'no'}, "
                     f"{n} bullets (aim for {MIN_BULLETS}-{MAX_BULLETS})",
        "clarity": f"{ok_len} of {n} bullets are {MIN_WORDS}-{MAX_WORDS} words",
    }
    parts = [{"id": i, "label": lbl, "points": _r(pts[i]), "max": mx, "note": notes[i]} for i, lbl, mx in PARTS]

    tips = []
    if len(req_hit) < len(req):
        missing = ", ".join(s for s in req if s not in req_hit)
        tips.append(f"Missing keywords: {missing}. Add them only if you genuinely have the experience.")
    if n and with_number / n < RESULTS_TARGET:
        tips.append("Add real numbers (users, %, time saved) to more bullets, but only ones you can back up.")
    if n and ok_len < n:
        tips.append(f"Keep each bullet between {MIN_WORDS} and {MAX_WORDS} words so it scans quickly.")
    if not tailored.summary.strip():
        tips.append("Add a one or two line summary at the top.")
    if not (MIN_BULLETS <= n <= MAX_BULLETS):
        tips.append(f"Use {MIN_BULLETS} to {MAX_BULLETS} bullets.")
    return {"score": sum(p["points"] for p in parts), "parts": parts, "tips": tips,
            "missing": [s for s in req if s not in req_hit]}
