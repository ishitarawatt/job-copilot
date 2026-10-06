# Monitoring Plan

## What is emitted today
`Tracer` (`src/copilot/monitoring.py`) writes one JSON line per agent call to `logs/traces.jsonl`:

`trace_id, agent, status, in_tokens, out_tokens, retries, latency_ms, cost_usd` (+ `error` on failure).

No resume or JD content is stored in traces, only sizes and metadata. `Tracer.summary()` aggregates error rate, p50/p95 latency, retries, and cost. Token counts are approximate (chars/4) and prices are illustrative; replace with provider-reported usage in production.

## Dashboards and alerts (to wire up at launch)
| Signal | Source | Alert |
|---|---|---|
| Fabrication caught by critic (rate of `critic_rejected_*` flags) | result flags | > 25% over 1h → model/prompt regression |
| `needs_human` rate | result status | < 2% (critic may be lax) or > 20% (quality or input problem) |
| `agent_failure` / malformed-output retries | spans | retries per run > 0.5 |
| Prompt-injection flags | result flags | spike → someone is probing; review samples |
| p95 latency | spans | > 25 s |
| Cost per run | spans | > 2× baseline |
| Provider errors / rate limits | spans `status=error` | error rate > 2% |

## Quality monitoring beyond infra
- **Weekly eval run on live model** (`evals/run_evals.py --live`) against a frozen set; block deploys if any gate fails.
- **Sampled human review:** 20 surfaced resumes/week checked for subtle embellishment the lexical critic misses.
- **User feedback:** thumbs up/down on tailored resume and on each interview question; downvotes feed new eval cases.
- **Drift:** re-run the eval set whenever the model version or any prompt changes.

## Production upgrades
Replace `Tracer._emit` with OpenTelemetry spans (fields already map 1:1) or Langfuse; keep `trace_id` as the correlation id surfaced in support tickets.
