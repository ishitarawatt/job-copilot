"""Deterministic guardrails. These never call an LLM, so they cannot be talked out of a decision.

Input side : PII redaction, prompt-injection detection, size limits.
Output side: fabrication check (the critical one for a resume product).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_JD_CHARS = 12_000
MIN_JD_CHARS = 40
MAX_RESUME_BULLETS = 40

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3,5}\)?[\s.-]?){2,3}\d{2,4}(?!\d)")

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above)",
    r"you are now\b",
    r"system prompt",
    r"reveal (your|the) (instructions|prompt)",
    r"(rate|rank|score) (this|the) (candidate|resume) (as )?(10|perfect|highest)",
    r"<\s*/?\s*(system|assistant)\s*>",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


@dataclass
class InputCheck:
    ok: bool
    cleaned_jd: str
    flags: list[str]


def redact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL]", text)
    return PHONE_RE.sub("[PHONE]", text)


def check_job_description(jd: str) -> InputCheck:
    flags: list[str] = []
    jd = jd.strip()
    if len(jd) < MIN_JD_CHARS:
        return InputCheck(False, jd, ["jd_too_short"])
    if len(jd) > MAX_JD_CHARS:
        jd = jd[:MAX_JD_CHARS]
        flags.append("jd_truncated")
    kept = []
    for line in jd.splitlines():
        if INJECTION_RE.search(line):
            flags.append("prompt_injection_removed")
            continue  # drop the offending line; treat the rest as data
        kept.append(line)
    return InputCheck(True, "\n".join(kept), sorted(set(flags)))


_NUM_RE = re.compile(r"\d[\d,.]*%?")
_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> set[str]:
    return set(_WORD_RE.findall(s.lower()))


def _bullet_supported(bullet: str, source_bullets: list[str]) -> bool:
    """A bullet is supported if it closely matches a source bullet and adds no new numbers."""
    b_tokens = _tokens(bullet)
    if not b_tokens:
        return True
    for src in source_bullets:
        s_tokens = _tokens(src)
        overlap = len(b_tokens & s_tokens) / len(b_tokens)
        new_numbers = set(_NUM_RE.findall(bullet)) - set(_NUM_RE.findall(src))
        if overlap >= 0.8 and not new_numbers:
            return True
    return False


def check_fabrication(out_bullets: list[str], matched_skills: list[str],
                      source_bullets: list[str], source_skills: list[str]) -> list[str]:
    """Return a list of human-readable issues. Empty list means clean."""
    issues = []
    for b in out_bullets:
        if not _bullet_supported(b, source_bullets):
            issues.append(f"Unsupported bullet (not traceable to source resume): {b!r}")
    blob = " ".join(source_bullets + source_skills).lower()
    for s in matched_skills:
        if s.lower() not in blob:
            issues.append(f"Claimed skill with no evidence in resume: {s!r}")
    return issues
