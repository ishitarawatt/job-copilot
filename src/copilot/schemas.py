"""Typed data contracts passed between agents."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class JobAnalysis:
    title: str
    required_skills: list[str]
    nice_to_have: list[str]
    seniority: str
    key_responsibilities: list[str]


@dataclass
class TailoredResume:
    summary: str
    bullets: list[str]          # reordered / rephrased, drawn from the source resume
    matched_skills: list[str]
    gaps: list[str]             # required skills the candidate does NOT show evidence of


@dataclass
class InterviewPrep:
    questions: list[dict[str, str]]   # {"question": ..., "why_asked": ..., "tip": ...}
    gap_talking_points: list[str]


@dataclass
class CriticReport:
    approved: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class CopilotResult:
    status: str                       # "ok" | "needs_human" | "blocked"
    analysis: JobAnalysis | None = None
    resume: TailoredResume | None = None
    prep: InterviewPrep | None = None
    critic: CriticReport | None = None
    ats: dict | None = None           # ATS-style readiness estimate, set only for an approved resume
    flags: list[str] = field(default_factory=list)
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
