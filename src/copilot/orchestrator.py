"""Orchestrator: guardrails -> analyze -> tailor <-> critic (bounded loop) -> coach -> escalate on failure."""
from __future__ import annotations

import json
import re

from .ats import ats_score
from .agents import Analyzer, Coach, Critic, Tailor
from .guardrails import check_job_description, redact_pii
from .llm import LLMClient
from .monitoring import Tracer, approx_tokens
from .schemas import CopilotResult

MAX_AGENT_RETRIES = 2      # malformed-output retries per agent
MAX_CRITIC_LOOPS = 1       # tailor re-runs after critic rejection


def parse_resume(text: str) -> dict:
    """Plain-text resume -> {summary, skills, bullets}. Bullets start with -, *, or the bullet char."""
    bullets, skills, summary_lines = [], [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("skills:"):
            skills = [s.strip() for s in line.split(":", 1)[1].split(",") if s.strip()]
        elif line[0] in "-*•":
            bullets.append(line.lstrip("-*• ").strip())
        elif (not line.endswith(":") and "|" not in line and len(line.split()) > 3
              and not any(m in line for m in ("[EMAIL]", "[PHONE]", "[URL]", "[HANDLE]", "[ADDRESS]"))):
            summary_lines.append(line)  # skips the name / contact header lines
    return {"summary": " ".join(summary_lines[:2]), "skills": skills, "bullets": bullets}


class Orchestrator:
    def __init__(self, llm: LLMClient, tracer: Tracer | None = None):
        self.analyzer, self.tailor = Analyzer(llm), Tailor(llm)
        self.coach, self.critic = Coach(llm), Critic()
        self.tracer = tracer or Tracer(None)

    def _call(self, trace_id: str, name: str, fn, input_text: str):
        """Run one agent with tracing and bounded retries on malformed output."""
        last: Exception | None = None
        for attempt in range(MAX_AGENT_RETRIES + 1):
            with_span = self.tracer.span(trace_id, name, input_text)
            try:
                with with_span as rec:
                    rec["retries"] = attempt
                    out = fn()
                    rec["out_tokens"] = approx_tokens(json.dumps(getattr(out, "__dict__", out), default=str))
                    return out
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                last = e
        raise RuntimeError(f"{name} failed after {MAX_AGENT_RETRIES + 1} attempts: {last}")

    def run(self, resume_text: str, job_description: str) -> CopilotResult:
        trace_id = self.tracer.new_trace_id()
        result = CopilotResult(status="ok", trace_id=trace_id)

        # 1. Input guardrails
        check = check_job_description(job_description)
        result.flags += check.flags
        if not check.ok:
            result.status = "blocked"
            return result

        resume = parse_resume(redact_pii(resume_text))
        if not resume["bullets"]:
            result.status, result.flags = "blocked", result.flags + ["resume_has_no_bullets"]
            return result

        try:
            # 2. Analyze the job
            analysis = self._call(trace_id, "analyzer", lambda: self.analyzer.run(check.cleaned_jd), check.cleaned_jd)
            result.analysis = analysis
            if not analysis.required_skills:
                result.flags.append("no_skills_extracted")
                result.status = "needs_human"
                return result

            # 3. Tailor, then critic loop
            feedback: list[str] | None = None
            tailored = None
            for loop in range(MAX_CRITIC_LOOPS + 1):
                tailored = self._call(trace_id, "tailor",
                                      lambda: self.tailor.run(resume, analysis, feedback), json.dumps(resume))
                with self.tracer.span(trace_id, "critic") as rec:
                    report = self.critic.run(resume, tailored, analysis.title)
                    rec["out_tokens"] = approx_tokens(json.dumps(report.__dict__))
                result.critic = report
                if report.approved:
                    break
                feedback = report.issues
                result.flags.append(f"critic_rejected_loop_{loop}")
            result.resume = tailored
            if not result.critic.approved:
                result.status = "needs_human"
                result.resume = None   # never surface unverified resume content
                return result

            result.ats = ats_score(tailored, analysis)   # informational only; computed from the approved resume

            # 4. Interview prep (runs after approval so gap list is trustworthy)
            result.prep = self._call(trace_id, "coach",
                                     lambda: self.coach.run(analysis, tailored.gaps), json.dumps(analysis.__dict__))
        except RuntimeError as e:
            result.status = "needs_human"
            result.flags.append(f"agent_failure: {e}")
        return result
