# Job Application Copilot

A multi-agent product that tailors your resume to a job posting **without inventing experience**, reports your honest skill gaps, and prepares you for the interview.

Four agents: **Analyzer → Tailor ⇄ Critic → Coach**, wrapped in deterministic guardrails, full tracing, and an eval suite with CI-style gates.

## Quick start (no API key needed)
```bash
pip install -r requirements.txt          # pytest (+ anthropic for live mode)
PYTHONPATH=src python -m copilot.cli --resume examples/resume.txt --job examples/job.txt
```

## Live mode (real Claude)
```bash
export ANTHROPIC_API_KEY=...             # optional: COPILOT_MODEL=claude-sonnet-5-5
PYTHONPATH=src python -m copilot.cli --resume examples/resume.txt --job examples/job.txt --live
```

## Verify
```bash
python -m pytest -q                          # 12 unit tests
PYTHONPATH=src python evals/run_evals.py     # 8 eval cases + safety gates (non-zero exit on failure)
```

> The offline runs use a deterministic **mock model** so the harness, guardrails and failure paths are testable and free. They validate the system, **not live-model quality**. Run `evals/run_evals.py --live` before trusting results.

## Layout
```
docs/PRD.md            AI PRD: problem, users, metrics, risks
docs/ARCHITECTURE.md   agent design + flow diagram
docs/GUARDRAILS.md     risk → control → test table, known gaps
docs/MONITORING.md     telemetry, alerts, quality monitoring
docs/LAUNCH_PLAN.md    gates, phased rollout, kill switch
src/copilot/           agents, orchestrator, guardrails, tracing, LLM clients, CLI
evals/                 cases.json + run_evals.py (pass rate, fabrication rate, PII leak rate)
tests/                 unit tests
examples/              sample resume and job description
```

## Statuses
`ok` result is verified · `needs_human` system could not verify, unverified resume withheld · `blocked` input unusable (reason in flags). CLI exit code: 0 / 2 / 2.
