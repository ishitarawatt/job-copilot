# Support Desk: context for Claude

Multi-agent customer-support resolver in Python. Part of the AI-PM-portfolio repo.
Work only inside `support-desk/` unless asked otherwise.

## Core principle
LLMs propose, code disposes. No model output can move money on its own.

## Architecture
Input guardrails → Triage (LLM) → routing → Knowledge → Resolver (LLM) ⇄ Policy Guard (code) + QA Critic (code) → Executor | Approval queue | Human
- `src/supportdesk/policy.py`: refund window 30 days, delivered-only, no double refunds, $100 auto-limit, ownership, action allow-list
- `src/supportdesk/guardrails.py`: input sanitization + QA Critic (false promises, amounts, foreign orders, grounding, PII)
- `src/supportdesk/tools.py`: order store, idempotent executor that re-checks invariants, approval queue, audit log
- `src/supportdesk/orchestrator.py`: routing, bounded revision loop (2), escalation with safe templates
- `src/supportdesk/llm.py`: `AnthropicClient` (live) and `MockClient` (offline, fault injection)
- `data/`: sample orders/customers/help center/inbox; fixed today = 2026-10-07 (`SUPPORTDESK_TODAY`)
- `evals/`: 19 cases + release gates (wrong action 0, false promise 0, PII 0, escalation recall 100%)
- `docs/`: PRD, architecture, guardrails, monitoring, launch plan

## Rules
- Before and after any change: `python -m pytest -q` and `PYTHONPATH=src python evals/run_evals.py` must pass.
- Never let an LLM output bypass `policy.evaluate` or the executor's invariant checks.
- Customer-facing escalation/approval messages stay as fixed templates.
- Every new failure mode gets an eval case; update the matching doc in `docs/`.

## Next up
1. Live evals (`--live`) and record results in README.
2. Browser demo like `job-copilot/demo/` (inbox view, approval queue, audit log).
3. Embedding-based retrieval + a retrieval eval.
4. Multi-turn conversations (customer replies to `awaiting_customer`).
