# Launch Plan

## Phase 0: Pre-launch gates (must all be green)
- [ ] Live-model eval run passes all gates (`fabrication_rate = 0`, `pii_leak_rate = 0`, pass rate ≥ 90%)
- [ ] Eval set grown to ≥ 50 real, anonymised cases across 5+ role families
- [ ] Human audit of 30 outputs: zero fabrications, gap report agrees with reviewer ≥ 90%
- [ ] Privacy review: retention policy for resumes, deletion path, no content in traces
- [ ] Cost and latency measured on live model against targets in the PRD

## Phase 1: Dogfood (week 1-2, ~10 users)
Friends and career-switchers. Every run reviewed by hand. Goal: find failure modes the evals miss; add each as an eval case.

## Phase 2: Closed beta (week 3-6, ~100 users)
Waitlist. Feature flag per user. Instrument activation (first ok run), usage (download / prep opened), and trust (thumbs, `needs_human` complaints).
**Go/no-go to Phase 3:** zero confirmed fabrications reached users, `needs_human` between 5-15%, ≥ 60% of ok runs acted on, p95 latency within target.

## Phase 3: Public launch
Open signup with rate limits. Publish a short "how we prevent made-up experience" explainer: it is the product's differentiator and builds trust.

## Rollout controls
- Kill switch: flag that forces `needs_human` for all runs (degrades gracefully to "we're reviewing").
- Per-agent model pinning and canary: ship prompt or model changes to 5% first, compare eval + live metrics.
- Rollback: prompts and model IDs are config, not code deploys.

## Positioning and pricing hypotheses (to test, not assume)
- Free: 3 runs/month. Paid: unlimited + saved resume variants. Validate willingness to pay in beta.
- Message: *"Tailored to the job. Truthful to you."*

## Roadmap after launch
Cover-letter agent (parallel to tailor, same critic); LinkedIn profile pass; application tracker; semantic judge as second fabrication signal; multi-language.
