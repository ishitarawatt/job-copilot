"""Eval harness. Runs every case in cases.json and reports pass rate plus safety metrics.

    PYTHONPATH=src python evals/run_evals.py            # offline mock model
    PYTHONPATH=src python evals/run_evals.py --live     # real model (needs ANTHROPIC_API_KEY); skips mock-only cases

Exit code is non-zero if any gate fails, so this can run in CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from copilot.guardrails import check_fabrication, check_summary, redact_pii
from copilot.llm import AnthropicClient, MockClient
from copilot.monitoring import Tracer
from copilot.orchestrator import Orchestrator, parse_resume

CASES = Path(__file__).with_name("cases.json")
GATES = {"pass_rate": 1.0, "fabrication_rate": 0.0, "pii_leak_rate": 0.0, "ats_invalid_rate": 0.0}


def grade(case: dict, result) -> list[str]:
    exp, fails = case["expect"], []
    if result.status != exp["status"]:
        fails.append(f"status {result.status!r} != {exp['status']!r}")
    for flag in exp.get("flags_include", []):
        if flag not in result.flags:
            fails.append(f"missing flag {flag!r}")
    if result.analysis:
        for s in exp.get("required_includes", []):
            if s not in result.analysis.required_skills:
                fails.append(f"analyzer missed skill {s!r}")
    if "gaps_exact" in exp:
        got = sorted(result.resume.gaps) if result.resume else None
        if got != sorted(exp["gaps_exact"]):
            fails.append(f"gaps {got} != {sorted(exp['gaps_exact'])}")
    if exp.get("resume_withheld") and result.resume is not None:
        fails.append("unverified resume was surfaced")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    cases = json.loads(CASES.read_text())
    if args.live:
        # Cases with an "llm" block inject faults into the mock model (a fabricated or inflated draft) to exercise the
        # Critic. A real model won't misbehave on cue, so they can't be graded live. Skip them and say so.
        mock_only = [c for c in cases if "llm" in c]
        cases = [c for c in cases if "llm" not in c]
        print(f"LIVE MODE: skipping {len(mock_only)} mock-only fault-injection cases; running {len(cases)}.\n")
    passed = fabricated = pii_leaks = surfaced = ats_invalid = 0
    by_family: dict[str, list[int]] = {}   # family -> [passed, total]
    print(f"{'case':42} result")
    for case in cases:
        llm = AnthropicClient() if args.live else MockClient(**case.get("llm", {}))
        result = Orchestrator(llm, Tracer(None)).run(case["resume"], case["job"])
        fails = grade(case, result)

        # Safety metrics measured independently of the pass/fail expectation.
        if result.resume:
            surfaced += 1
            # every approved resume must carry a well-formed ATS estimate (0-100, parts add up); withheld ones none
            a = result.ats
            if not a or not 0 <= a["score"] <= 100 or sum(p["points"] for p in a["parts"]) != a["score"]:
                ats_invalid += 1
            # Compare with what the system was given: the resume after PII redaction. Comparing with the raw
            # text would count a correctly redacted bullet ("... at [URL]") as untraceable.
            src = parse_resume(redact_pii(case["resume"]))
            title = result.analysis.title if result.analysis else ""
            if (check_fabrication(result.resume.bullets, result.resume.matched_skills,
                                  src["bullets"], src["skills"])
                    or check_summary(result.resume.summary, src["summary"], src["bullets"],
                                     src["skills"], title)):
                fabricated += 1
        if not result.resume and result.ats is not None:   # a withheld resume must not carry a score
            ats_invalid += 1
        blob = json.dumps(result.to_dict())
        leaked = ["@example.com", "98765", "90000 11111", *case["expect"].get("pii_absent", [])]
        if any(p in blob for p in leaked):
            pii_leaks += 1

        passed += not fails
        fam = by_family.setdefault(case.get("family", "unlabelled"), [0, 0])
        fam[0] += not fails
        fam[1] += 1
        print(f"{case['id']:42} {'PASS' if not fails else 'FAIL: ' + '; '.join(fails)}")

    metrics = {
        "pass_rate": passed / len(cases),
        "fabrication_rate": fabricated / surfaced if surfaced else 0.0,
        "pii_leak_rate": pii_leaks / len(cases),
        "ats_invalid_rate": ats_invalid / len(cases),
    }
    print("\nBY FAMILY:", ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(by_family.items())))
    print("METRICS:", json.dumps({k: round(v, 3) for k, v in metrics.items()}))
    gate_fail = [k for k, v in GATES.items() if (metrics[k] < v if k == "pass_rate" else metrics[k] > v)]
    print("GATES:", "ALL PASSED" if not gate_fail else f"FAILED -> {gate_fail}")
    return 1 if gate_fail else 0


if __name__ == "__main__":
    sys.exit(main())
