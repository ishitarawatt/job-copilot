# Agent Architecture

```
resume + job description
        │
        ▼
 ┌──────────────────────┐   blocked  ┌─────────────┐
 │  Input guardrails    │──────────▶ │ status:     │
 │  size · injection ·  │            │ blocked     │
 │  PII redaction       │            └─────────────┘
 └─────────┬────────────┘
           ▼
 ┌──────────────────────┐
 │ Analyzer (LLM)       │  JD → {required, nice_to_have, seniority, responsibilities}
 └─────────┬────────────┘
           │ no skills extracted ──▶ needs_human
           ▼
 ┌──────────────────────┐        ┌────────────────────────┐
 │ Tailor (LLM)         │◀──────▶│ Critic (deterministic) │
 │ source-facts-only    │ issues │ trace, numbers, verbs  │
 └─────────┬────────────┘ fed    └────────────────────────┘
           │ approved       back, max 1 loop; still failing ──▶ needs_human
           ▼                                  (resume withheld)
 ┌──────────────────────┐
 │ Coach (LLM)          │  analysis + verified gaps → questions, honest gap talking points
 └─────────┬────────────┘
           ▼
     CopilotResult  (every step traced to logs/traces.jsonl)
```

## Agents
| Agent | Kind | Input | Output | Failure handling |
|---|---|---|---|---|
| Analyzer | LLM | sanitized JD | `JobAnalysis` | up to 2 retries on malformed JSON, then `needs_human` |
| Tailor | LLM | parsed resume + analysis (+ critic feedback) | `TailoredResume` | same retry policy |
| Critic | Code | source resume + tailored output | `CriticReport` | rejects → tailor loop (max 1) → escalate |
| Coach | LLM | analysis + verified gaps | `InterviewPrep` | same retry policy |

## Key design decisions
1. **Critic is not an LLM.** Verification by the same class of system that fabricates is weak. A deterministic check is auditable, free, and cannot be sweet-talked.
2. **Coach runs after the critic.** Its gap list comes from an approved resume, so prep never builds on a rejected claim.
3. **Fail closed.** On unresolved critic issues the tailored resume is set to `None`. The user sees the issues, not the risky content.
4. **Typed contracts** (`schemas.py`) between agents; each agent parses model output into a dataclass, so drift fails loudly in one place.
5. **Provider-agnostic.** Agents depend on the `LLMClient` protocol. `MockClient` makes CI deterministic and free; `AnthropicClient` is the live path.
6. **Bounded autonomy.** Retry and loop limits are constants (`MAX_AGENT_RETRIES`, `MAX_CRITIC_LOOPS`); no unbounded agent loops.

## Scaling notes
Agents are stateless; the orchestrator can run per-request in a worker. Add a queue and idempotency key (hash of resume + JD) for retries and caching. Tailor and a future cover-letter agent can run in parallel once the analysis exists.
