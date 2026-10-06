# AI PRD: Job Application Copilot

**Status:** Draft v1 · **Owner:** (you) · **Date:** 2026-10-07

## 1. Problem
Job seekers, especially career-switchers into product roles, send the same resume to every posting. Tailoring by hand takes 30-60 minutes per application, so most people skip it. The shortcut, pasting everything into a chatbot, has a worse failure: **LLMs invent experience**, and a fabricated claim discovered in an interview ends the candidacy.

## 2. Target user and job-to-be-done
- **Primary:** mid-career professional applying to 5-20 roles a month.
- **JTBD:** "When I find a role I want, help me present my *real* experience in the strongest relevant light and prepare for the interview, without me having to lie or spend an hour."

## 3. Why this is a multi-agent product (and not a chatbot)
| Need | Why one prompt fails | Agent answer |
|---|---|---|
| Understand the posting | Long, messy, may contain hostile text | **Analyzer** treats the JD as data and returns structured requirements |
| Rewrite truthfully | Same model that writes also invents | **Tailor** under hard "source facts only" rules |
| Catch invention | A model rarely catches its own fabrications | **Critic** is deterministic code, not an LLM |
| Interview prep | Needs the gap list from the tailor | **Coach** runs after approval, grounded in verified gaps |

## 4. Goals and non-goals
**Goals:** truthful tailoring; honest gap reporting; interview prep grounded in the actual posting; safe handling of untrusted job text.
**Non-goals (v1):** auto-applying to jobs, writing cover letters, ATS keyword stuffing, resume design/PDF layout, multi-language.

## 5. User stories and acceptance criteria
1. *As a candidate, I paste my resume and a job description and get a tailored resume.*
   AC: every bullet is traceable to my source resume; every number is unchanged.
2. *I see where I fall short.* AC: required skills with no evidence in my resume are listed as gaps, never silently covered.
3. *I get interview questions.* AC: questions target skills I can credibly speak to; gap talking points are honest.
4. *Hostile or broken input doesn't hurt me.* AC: injected instructions in a JD are stripped and flagged; unusable input is blocked with a reason.
5. *When the system is unsure, it says so.* AC: unverifiable output is withheld and routed to `needs_human`, never shown.

## 6. Success metrics
| Metric | Target | Type |
|---|---|---|
| Fabrication rate in surfaced resumes | **0%** (hard gate) | Safety |
| Gap-report accuracy vs human label | ≥ 90% | Quality |
| Skill-extraction recall (required skills) | ≥ 90% | Quality |
| Critic-reject → recovered rate | ≥ 70% | Reliability |
| `needs_human` rate | 5-15% (too low = critic is lax; too high = annoying) | Health |
| p95 end-to-end latency | < 25 s live | Performance |
| Cost per run | < $0.05 | Economics |
| User action: resume downloaded / interview prep opened | ≥ 60% of ok runs | Product |
| 2-week return rate | ≥ 30% | Retention |

## 7. AI-specific requirements
- **Failure modes designed for:** hallucinated experience, prompt injection via JD, malformed JSON, silent skill inflation, PII leakage to logs.
- **Autonomy level:** system *proposes*; user always reviews. No external side effects in v1.
- **Human-in-the-loop:** `needs_human` state with the critic's issues shown.
- **Model policy:** one model for generation agents (configurable via `COPILOT_MODEL`); critic is code. Re-evaluate smaller/cheaper models per agent once evals exist.
- **Data:** resumes are sensitive. PII redacted before any model call; traces store token counts, not content.

## 8. Risks and open questions
- Mock-model evals prove the *harness and guardrails*, not live model quality. A live eval run is required before launch.
- The fabrication check is lexical (token overlap + number match). It can miss subtle semantic embellishment ("led" vs "contributed to"). Mitigation: add an LLM-judge as a second, non-blocking signal; sample human review.
- Skill vocabulary in the mock is small; live analyzer must generalise.
- Legal/ToS: scraping job boards is out of scope; user pastes the JD.
