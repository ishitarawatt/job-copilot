# Job Application Copilot: context for Claude

Multi-agent Python app that tailors a resume to a job posting without inventing experience.
Analyzer → Tailor ⇄ Critic → Coach. The Critic is deterministic code, not a model, and unverifiable
output is withheld (`needs_human`), never shown.

## Core principle
LLMs propose, code disposes. No model output reaches the user unless the Critic approves it.

## Layout
- `src/copilot/guardrails.py`: input guardrails (PII redaction, prompt-injection removal, size limits) and the
  fabrication check (token overlap >= 80%, no new numbers, no added strength words such as led/managed/senior)
  plus the summary check
- `src/copilot/agents.py`: Analyzer, Tailor, Coach (LLM) and Critic (code)
- `src/copilot/orchestrator.py`: guardrails → analyze → tailor ⇄ critic (max 1 retry) → coach; fail closed
- `src/copilot/llm.py`: `AnthropicClient` (live) and `MockClient` (offline; `fabricate_first_n`, `inflate_first_n`)
- `src/copilot/monitoring.py`: tracing to `logs/traces.jsonl`; no resume or JD content is stored
- `evals/`: `cases.json` + `run_evals.py` with gates (pass_rate 1.0, fabrication_rate 0, pii_leak_rate 0)
- `tests/`: unit tests; `tests/test_demo_parity.py` runs the demo's JS port in node against the Python originals
- `demo/index.html`: browser demo with its own JavaScript port of the guardrails and Critic
- `docs/`: PRD, ARCHITECTURE, GUARDRAILS (risk → control → test, plus known gaps), MONITORING, LAUNCH_PLAN

## Rules
- Before and after any change: `python -m pytest -q` and `PYTHONPATH=src python evals/run_evals.py` must pass.
- Never loosen the Critic or let model output bypass it. Fail closed: unverified resume is set to `None`.
- Every new failure mode gets a unit test and an eval case; update `docs/GUARDRAILS.md` (including known gaps).
- The demo carries a JS copy of the guardrails (between the `<parity:begin>`/`<parity:end>` markers in
  `demo/index.html`). Change a guardrail in one place and change the other; add a case to
  `tests/parity_cases.json` so the parity test covers it. Keep that block free of DOM access.
- Offline results come from the mock model. They validate the harness and guardrails, not live-model quality.
  Say so when reporting results, and do not claim live quality without `evals/run_evals.py --live`.
- Do not store resume or job-description content in traces or logs.

## Commands
```bash
pip install -r requirements.txt
python -m pytest -q
PYTHONPATH=src python evals/run_evals.py          # add --live (needs ANTHROPIC_API_KEY) for the real model
PYTHONPATH=src python -m copilot.cli --resume examples/resume.txt --job examples/job.txt
```
CI (`.github/workflows/ci.yml`) runs the first two on every push and pull request. `live-evals.yml` is manual only (it needs the
`ANTHROPIC_API_KEY` repository secret and costs money); `--live` skips the cases that have an `llm` fault-injection block.

## Next up (from docs/LAUNCH_PLAN.md and docs/GUARDRAILS.md)
1. Live eval run and record the results in the README.
2. Add real, anonymised eval cases (59 synthetic ones exist across 6 role families; see docs/LAUNCH_PLAN.md).
3. Semantic judge as a second, non-blocking fabrication signal; sampled human audits.
4. Scan the resume text for injection too (today only the JD is scanned), and enforce `MAX_RESUME_BULLETS`.
