"""Deterministic guardrails. These never call an LLM, so they cannot be talked out of a decision.

Input side : PII redaction, prompt-injection detection, size limits.
Output side: fabrication check (the critical one for a resume product).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_JD_CHARS = 12_000
MIN_JD_CHARS = 40
MAX_RESUME_BULLETS = 40

# --------------------------------------------------------------------------- #
# PII redaction (regex based; see GUARDRAILS.md for what it does not cover)
# --------------------------------------------------------------------------- #
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(
    r"(?:https?://|www\.)\S+|\b(?:linkedin|github|gitlab|twitter|x)\.com/\S+", re.IGNORECASE
)
# Runs after emails are gone, so any remaining "@name" is a social handle.
HANDLE_RE = re.compile(r"(?<![\w@.])@[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*")
# Case-sensitive on purpose: "42 Baker Street" matches, "5 experiments to drive" does not.
ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Z][\w.'-]*\s+){1,3}"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Drive|Dr|Nagar|Marg)\b\.?"
)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3,5}\)?[\s.-]?){2,3}\d{2,4}(?!\d)")

# --------------------------------------------------------------------------- #
# Prompt-injection detection
# --------------------------------------------------------------------------- #
# Patterns are matched against NORMALISED text (see _normalize): lower-cased by the regex flag,
# accents stripped, zero-width characters removed, compatibility forms (full-width) folded.
INJECTION_PATTERNS = [
    # English: override / forget / ignore
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?|rules)",
    r"disregard (all |any )?(the )?(previous|prior|above|earlier)",
    r"forget (all |any |everything |the )*(previous|prior|above|earlier|your)\b",
    r"forget everything",
    r"override (the |your )?(previous|prior|system) (instructions|rules|prompt)",
    r"(do not|don't|stop) follow(ing)? (the |any |your )?(previous|prior|above|earlier|original)",
    r"new instructions?\s*:",
    # role / persona hijack
    r"you are now\b",
    r"pretend (to be|you are|you're)",
    r"jailbreak|developer mode|\bdan mode\b",
    # prompt exfiltration
    r"system prompt",
    r"reveal (your|the) (instructions|prompt)",
    # steering the verdict
    r"(rate|rank|score|mark|grade) (this|the|that) (candidate|applicant|resume)\b.{0,20}\b"
    r"(10|perfect|highest|best|excellent|top)",
    r"(always|must|should|just) (approve|recommend|shortlist) (this|the|that) (candidate|applicant|resume)",
    # chat-template / role markers
    r"<\s*/?\s*(system|assistant)\s*>",
    r"\[/?inst\]|<<\s*/?\s*sys\s*>>|###\s*(system|instruction)",
    r"^\s*(system|assistant)\s*:",
    # a few non-English variants of "ignore previous instructions"
    r"ignora (todas )?las instrucciones (anteriores|previas)",
    r"ignorez? (toutes )?les instructions (precedentes|ci-dessus)",
    r"ignoriere (alle )?(vorherigen|obigen|bisherigen|fruheren) anweisungen",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)


def _normalize(s: str) -> str:
    """Fold text so cosmetic obfuscation (zero-width chars, full-width letters, accents) can't hide a match."""
    s = unicodedata.normalize("NFKD", s).translate(_INVISIBLE)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[ \t]+", " ", s)


@dataclass
class InputCheck:
    ok: bool
    cleaned_jd: str
    flags: list[str]


def redact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = URL_RE.sub("[URL]", text)
    text = HANDLE_RE.sub("[HANDLE]", text)
    text = ADDRESS_RE.sub("[ADDRESS]", text)
    return PHONE_RE.sub("[PHONE]", text)


def check_job_description(jd: str) -> InputCheck:
    flags: list[str] = []
    jd = jd.strip()
    if len(jd) < MIN_JD_CHARS:
        return InputCheck(False, jd, ["jd_too_short"])
    if len(jd) > MAX_JD_CHARS:
        jd = jd[:MAX_JD_CHARS]
        flags.append("jd_truncated")

    lines = jd.splitlines()
    norm = [_normalize(line) for line in lines]
    hits = {i for i, n in enumerate(norm) if INJECTION_RE.search(n)}
    drop: set[int] = set(hits)
    for i in range(len(norm) - 1):
        # An instruction split across two lines. Only pair lines that are innocent on their own,
        # otherwise a clean line next to an injected one would be dropped with it.
        if i not in hits and i + 1 not in hits and INJECTION_RE.search(norm[i] + " " + norm[i + 1]):
            drop.update((i, i + 1))
    if drop:
        flags.append("prompt_injection_removed")
    kept = [line for i, line in enumerate(lines) if i not in drop]  # drop offending lines; rest is data
    return InputCheck(True, "\n".join(kept), sorted(set(flags)))


# --------------------------------------------------------------------------- #
# Fabrication check (the Critic's engine)
# --------------------------------------------------------------------------- #
_NUM_RE = re.compile(r"\d[\d,.]*%?")
_WORD_RE = re.compile(r"[a-z0-9]+")

# Words that make a claim bigger than it was. Grouped into families so "lead/led/leading" count as one.
# If one appears in a tailored bullet or summary and NOT in the source it came from, the claim was
# strengthened ("Used SQL dashboards" -> "Led SQL dashboards") even though token overlap stays high.
_INFLATION_FAMILIES = {
    "lead": {"lead", "led", "leads", "leading"},
    "manage": {"manage", "managed", "manages", "managing"},
    "direct": {"directed", "directing", "directs"},
    "own": {"owned", "owns", "owning", "ownership"},
    "spearhead": {"spearhead", "spearheaded", "spearheading"},
    "head": {"head", "headed", "heading"},
    "architect": {"architected", "architecting"},
    "found": {"founded", "founding", "cofounded"},
    "drive": {"drove", "driven", "drives", "driving"},
    "launch": {"launched", "launching"},
    "pioneer": {"pioneer", "pioneered"},
    "oversee": {"oversee", "oversaw", "overseen", "overseeing"},
    "champion": {"championed"},
    "sole": {"sole", "solely", "handedly"},
    "entire": {"entire"},
    "global": {"global", "worldwide"},
    "enterprise": {"enterprise"},
    "senior": {"senior"},
    "principal": {"principal"},
    "director": {"director"},
    "vp": {"vp"},
    "chief": {"chief"},
}
_WORD_TO_FAMILY = {w: fam for fam, words in _INFLATION_FAMILIES.items() for w in words}


def _tokens(s: str) -> set[str]:
    return set(_WORD_RE.findall(s.lower()))


def _numbers(s: str) -> set[str]:
    """Numbers in `s`, ignoring sentence punctuation ('40000.' and '40000' are the same number)."""
    return {n.rstrip(".,") for n in _NUM_RE.findall(s)} - {""}


def _inflation(out_tokens: set[str], *source_token_sets: set[str]) -> list[str]:
    """Inflation families present in the output but in none of the allowed source token sets."""
    have = {_WORD_TO_FAMILY[t] for ts in source_token_sets for t in ts if t in _WORD_TO_FAMILY}
    new = {_WORD_TO_FAMILY[t] for t in out_tokens if t in _WORD_TO_FAMILY} - have
    return sorted(new)


def _bullet_problem(bullet: str, source_bullets: list[str]) -> str | None:
    """None if the bullet is faithful to a source bullet; otherwise a human-readable issue."""
    b_tokens = _tokens(bullet)
    if not b_tokens:
        return None
    inflated: list[str] = []
    for src in source_bullets:
        s_tokens = _tokens(src)
        overlap = len(b_tokens & s_tokens) / len(b_tokens)
        if overlap >= 0.8 and not (_numbers(bullet) - _numbers(src)):
            inflated = _inflation(b_tokens, s_tokens)
            if not inflated:
                return None
    if inflated:
        return (f"Strengthened claim (adds {', '.join(inflated)} not present in the source bullet): "
                f"{bullet!r}")
    return f"Unsupported bullet (not traceable to source resume): {bullet!r}"


def _bullet_supported(bullet: str, source_bullets: list[str]) -> bool:
    """A bullet is supported if it closely matches a source bullet, adds no new numbers, no stronger claim."""
    return _bullet_problem(bullet, source_bullets) is None


def check_fabrication(out_bullets: list[str], matched_skills: list[str],
                      source_bullets: list[str], source_skills: list[str]) -> list[str]:
    """Return a list of human-readable issues. Empty list means clean."""
    issues = []
    for b in out_bullets:
        problem = _bullet_problem(b, source_bullets)
        if problem:
            issues.append(problem)
    blob = " ".join(source_bullets + source_skills).lower()
    for s in matched_skills:
        if s.lower() not in blob:
            issues.append(f"Claimed skill with no evidence in resume: {s!r}")
    return issues


def check_summary(summary: str, source_summary: str, source_bullets: list[str],
                  source_skills: list[str], job_title: str = "") -> list[str]:
    """Summary is free text, so hold it to the same two rules: no new numbers, no stronger claims.

    The job title is allowed because the summary legitimately names the target role.
    """
    source_text = " ".join([source_summary, *source_bullets, *source_skills])
    allowed_numbers = _numbers(source_text) | _numbers(job_title)
    issues = []
    new_numbers = sorted(_numbers(summary) - allowed_numbers)
    if new_numbers:
        issues.append(f"Summary introduces numbers not in the source resume: {new_numbers}")
    inflated = _inflation(_tokens(summary), _tokens(source_text), _tokens(job_title))
    if inflated:
        issues.append(f"Summary strengthens claims (adds {', '.join(inflated)} not present in the source resume)")
    return issues
