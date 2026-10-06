"""CLI: python -m copilot.cli --resume resume.txt --job job.txt [--live] [--json]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .llm import AnthropicClient, MockClient
from .monitoring import Tracer
from .orchestrator import Orchestrator


def render(result) -> str:
    out = [f"STATUS: {result.status}  (trace {result.trace_id})"]
    if result.flags:
        out.append("FLAGS: " + "; ".join(result.flags))
    if result.analysis:
        a = result.analysis
        out += ["", f"== ROLE: {a.title} ({a.seniority}) ==",
                "Required: " + ", ".join(a.required_skills),
                "Nice to have: " + (", ".join(a.nice_to_have) or "-")]
    if result.resume:
        r = result.resume
        out += ["", "== TAILORED RESUME ==", r.summary, ""] + [f"- {b}" for b in r.bullets]
        out += ["", "Matched: " + (", ".join(r.matched_skills) or "-"),
                "Gaps: " + (", ".join(r.gaps) or "none")]
    if result.prep:
        out += ["", "== INTERVIEW PREP =="]
        for q in result.prep.questions:
            out += [f"Q: {q['question']}", f"   Tip: {q['tip']}"]
        out += [f"Gap: {g}" for g in result.prep.gap_talking_points]
    if result.status == "needs_human" and result.critic and not result.critic.approved:
        out += ["", "== CRITIC ISSUES =="] + [f"- {i}" for i in result.critic.issues]
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Job Application Copilot (multi-agent)")
    p.add_argument("--resume", required=True, type=Path)
    p.add_argument("--job", required=True, type=Path)
    p.add_argument("--live", action="store_true", help="use the real Anthropic API (needs ANTHROPIC_API_KEY)")
    p.add_argument("--json", action="store_true", help="print raw JSON result")
    p.add_argument("--trace-file", default="logs/traces.jsonl")
    args = p.parse_args(argv)

    llm = AnthropicClient() if args.live else MockClient()
    tracer = Tracer(args.trace_file)
    result = Orchestrator(llm, tracer).run(args.resume.read_text(), args.job.read_text())
    print(json.dumps(result.to_dict(), indent=2) if args.json else render(result))
    print("\nTELEMETRY:", json.dumps(tracer.summary()), file=sys.stderr)
    return 0 if result.status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
