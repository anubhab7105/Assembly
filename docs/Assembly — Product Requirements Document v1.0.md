> **Historical specification — not current implementation guidance.** This document records the v1.0 product requirements as of October 8, 2026. It is retained for historical context only and may contain superseded requirements or implementation assumptions. For the current source of truth, use [`docs/PRD.md`](PRD.md) (v1.1 or later), [the architecture guide](architecture.md), and the current code. In particular, the current design has no accounts or login and does not persist web-mode data on the server.

# Assembly — Product Requirements Document

*Multi-Agent AI Consensus Platform · v1.0 · October 8, 2026 · Owner: Anubhab Das · Supersedes v0.1 (August 16, 2026)*

## 1. Summary

Assembly turns one question into a temporary team of AI agents. The agents solve the problem independently, challenge each other, verify evidence, and only converge when the evidence supports it. The user sees one thing: a final answer with sources, produced inside a time budget they chose (3, 5, 10 or 15 minutes).

**Core promise:** Ask once. Assembly builds a temporary expert team that researches, solves, challenges and verifies, then gives you the strongest answer it can within your time.

### What changed from v0.1

| Topic | v0.1 | v1.0 (this document) |
| --- | --- | --- |
| Model access | OpenAI, Gemini, Groq, open-source | **Free-tier only.** OpenAI removed. Grok demoted to optional (no permanent free API). |
| Who supplies capacity | Unspecified (implied: the operator) | **BYOK: each user brings their own free API keys.** |
| Primary goal | General product launch | **Hackathon / competition demo first**, product later. |
| Platforms | Website | **Website + Windows app** from one codebase. |
| Agent independence | Different providers | Different **model families** (two providers serving the same Llama model are not independent). |
| Infrastructure | PostgreSQL, Redis, Kubernetes-style scale | **SQLite + in-memory event bus** for the demo; Postgres only for the hosted website. Redis dropped from MVP. |
| Time tiers | Fixed agent counts | **Capacity-aware**: the plan adapts to the free quota the user's keys actually have. |

## 2. Problem and core hypothesis

A single model answer is fast but has no built-in self-correction: a confident wrong answer looks identical to a confident right one. Asking several models and blending the outputs does not fix this; it averages unverified answers.

**Hypothesis to prove:** a temporary team that reasons independently, cross-examines, and verifies produces measurably better answers than the best single free model on the same question.

Everything in the MVP exists to test and demonstrate this one hypothesis.

## 3. Goals and success metrics

### 3.1 Goals (in priority order)

1. **Win a live demo.** A judge types a hard question, watches the team work, and gets a visibly better, sourced answer.
2. **Prove the hypothesis with numbers.** A small benchmark: Assembly vs. the best single free model.
3. **Cost the user nothing.** Every feature works on free-tier keys.
4. **Keep keys safe.** User API keys never reach a server database or a log file.

### 3.2 Metrics

| Metric | Target for demo |
| --- | --- |
| Win rate vs. best single free model on a 30–50 question set (blind rubric grading) | Above 60% win/tie-adjusted, with the method documented |
| Demo run completes without a provider error surfacing to the user | 100% over 10 rehearsal runs |
| Executions that finalize with consensus before the safety cutoff | Above 80% |
| Time overrun versus chosen budget | 0 (hard cutoff) |
| Calls per execution by tier (measured, not guessed) | Recorded and published in the benchmark report |
| Key leakage in logs, DB or crash reports | 0 occurrences (checked by a log-scan test) |

## 4. Non-goals (for this release)

- No paid models, no billing, no pricing tiers (monetization is deferred until real costs are measured).
- No manual team building or manual model selection by the user.
- No exposure of full agent chain-of-thought as a default (see Insight Mode, section 11.4, for a deliberate exception).
- No mobile app, no public API, no saved teams.
- No guarantee of correctness. The product states uncertainty when consensus is weak.

## 5. Users

**Primary (demo audience):** hackathon judges and mentors, who need to understand the value in under two minutes.

**Product users (later):** developers (debugging, architecture trade-offs), students (math and science explanations), researchers (multi-source questions).

**Assumption:** target users are technical enough to create a free API key from at least two providers. A guided key-setup wizard is therefore a core feature, not a nice-to-have.

## 6. Key product decisions

| # | Decision | Reason |
| --- | --- | --- |
| D1 | BYOK. Users paste their own free keys. | Free quotas are per account and small; a shared operator key would be exhausted by a few runs. |
| D2 | Free-tier models only. | Hard project constraint. |
| D3 | Diversity is measured by **model family**, not provider. Groq and Cerebras can both serve Llama; that is one family. | Correlated errors destroy the value of independent first-pass reasoning. |
| D4 | Local-first orchestration on Windows: the orchestrator runs on the user's machine, so keys never leave it. | Strongest security story; also the most reliable demo setup (no cold-starting free server). |
| D5 | The website sends keys per request over HTTPS and never stores or logs them. | Honest, auditable minimum for a hosted version. |
| D6 | Capacity-aware planning. The orchestrator reads the user's available providers and quotas before choosing team size and rounds. | Free rate limits vary by account and change over time. |
| D7 | Time budget is a hard constraint with a safety cutoff. | Core feature; also protects the demo. |

## 7. Core user experience

1. **First run:** Key Setup wizard. The user adds keys for at least two providers (three recommended). Each key has a Test button. The app shows which model families are now available.
2. **Ask:** the user types a question and picks a thinking time (3 / 5 / 10 / 15 min). Mode is Auto.
3. **Watch:** the Team Progress view shows active roles, a live consensus meter, disagreements found and resolved, sources being checked, and the countdown.
4. **Receive:** a final answer, a confidence statement, and the sources actually used.
5. **Return:** conversation history lists past questions and answers.

### 7.1 Time tiers (indicative, capacity-aware)

| Tier | Strategy | Estimated model calls (to be measured) |
| --- | --- | --- |
| 3 min | 2–3 agents, 1 critique round, fast synthesis | 8–12 |
| 5 min | 3–4 agents, 2 rounds, basic verification | 15–22 |
| 10 min | 4–5 agents, multiple rounds, web research | 25–40 |
| 15 min | 5–6 agents, deep research, adversarial verification | 40–60 |

If the user's keys cannot support the chosen tier (for example only two providers with small daily quotas), the app says so before starting and offers a smaller plan instead of failing mid-run.

## 8. Functional requirements

Priority: **M** = must for the demo, **S** = should, **C** = could.

### 8.1 Orchestration

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-1 | Planner classifies each question (type, complexity, needs-research) and outputs a team plan. | M |
| FR-2 | Team always includes at least one Solver, one Critic and one Synthesizer; a Researcher is added when research is needed. | M |
| FR-3 | Stage 1: agents solve independently and cannot see each other's answers. | M |
| FR-4 | Agents return structured JSON: position, confidence, evidence, supports, disagrees\_with, remaining\_uncertainty. Output is schema-validated; one retry, then fallback model. | M |
| FR-5 | Debate rounds happen only while there is an open disagreement or missing evidence; each round must change something (resolve, add evidence, fix an error, or move confidence). | M |
| FR-6 | Consensus engine produces a score from agreement, confidence, evidence quality, contradictions and new-information rate. | M |
| FR-7 | Adversarial round: when agreement is high too early, one agent is told to assume the consensus is wrong and find the strongest counterargument. | M |
| FR-8 | Stopping rule: finalize on consensus above threshold with low new information, or at the safety threshold before the deadline. | M |
| FR-9 | If consensus is weak at the deadline, the final answer states what is uncertain instead of sounding confident. | M |
| FR-10 | Router assigns models by role and enforces at least 3 distinct model families when available (2 minimum with a visible warning). | M |
| FR-11 | Budget controller enforces time, token, agent, search and per-provider request quotas. | M |
| FR-12 | Context compression between rounds so cost does not grow quadratically with team size. | M |
| FR-13 | Provider failure triggers fallback to another family; a 429 triggers backoff and a quota cooldown for that key. | M |
| FR-14 | Coding mode with a shared artifact (code and tests) and security and performance reviewers. | C |

### 8.2 Research

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-20 | Web search through a free search source with graceful fallback when quota is out. | M |
| FR-21 | Only sources actually used appear in the final answer, with numbered citations. | M |
| FR-22 | Source deduplication and a simple credibility ranking (official, academic, reputable media, other). | S |
| FR-23 | Optional free academic sources (arXiv, Semantic Scholar, Wikipedia) for research questions. | C |

### 8.3 Keys and providers (BYOK)

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-30 | Key Setup wizard with per-provider instructions and a Test button. | M |
| FR-31 | Windows app stores keys in the Windows Credential Manager (encrypted by the OS), never in plain files. | M |
| FR-32 | Website keeps keys in browser memory for the session by default; no server-side persistence. | M |
| FR-33 | Keys are redacted from all logs, error messages and stored execution records. | M |
| FR-34 | Per-provider quota tracker (requests per minute and per day) that the planner reads. | M |
| FR-35 | Privacy notice per provider where free tiers may use inputs for model improvement (for example Gemini free tier). | M |
| FR-36 | Key health panel: valid, rate-limited, exhausted for today. | S |

### 8.4 Accounts and history

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-40 | Windows app: no login required; history stored locally. | M |
| FR-41 | Website: sign up, login, Google OAuth, history per user. | S |
| FR-42 | Conversation and execution history with final answer and sources. | M |
| FR-43 | Export an answer as Markdown. | C |

## 9. Platforms

- **Website:** Next.js frontend, hosted FastAPI backend that runs long executions and streams progress.
- **Windows app:** the same frontend in a desktop shell, with the Python backend bundled and run locally.
- Both share one frontend codebase and one backend codebase. The only difference is where the orchestrator runs and where keys are stored.

Details and rationale are in the companion document TECH\_STACK.md.

## 10. Non-functional requirements

**Security and privacy**

- Keys never written to the database, logs, analytics or crash reports.
- All website traffic over HTTPS; keys sent per request in headers or body, never in URLs.
- Prompt-injection awareness: web content is treated as untrusted data, never as instructions to agents.
- Users are told which providers may retain or train on their inputs.

**Reliability**

- Any single provider can fail mid-run without failing the execution.
- Executions survive a WebSocket disconnect and can be re-attached.
- Hard cutoff: the app never runs past the chosen time budget plus a short synthesis allowance.

**Performance**

- Parallel calls inside a round, limited by each provider's rate limit.
- First progress event within 3 seconds of submitting a question.

**Observability**

- Every call logs provider, model family, tokens, latency and outcome (never the key).

## 11. UX requirements

### 11.1 Chat screen

Question box, time selector (3 / 5 / 10 / 15), mode indicator (Auto), and a small capacity indicator showing how many providers are ready.

### 11.2 Team Progress view

Role list with plain-language activity, consensus percentage, open and resolved disagreements, sources checked, countdown timer. High-level only.

### 11.3 Answer view

Final answer, confidence statement, numbered sources, and a short "how this was verified" summary (for example "4 agents, 3 model families, 2 disagreements resolved").

### 11.4 Insight Mode (new, optional, off by default)

A toggle that shows the debate timeline: who disagreed with whom, what evidence changed a position. This deliberately relaxes the v0.1 non-goal of hiding the debate. Reason: for a hackathon, judges need to see the mechanism, and it makes the echo-chamber protection visible. **Decision needed from owner** (see section 15).

### 11.5 Settings

Key management, provider health, privacy notices, theme.

## 12. Hackathon plan

### 12.1 Scope tiers

**Must (demo-critical):** FR-1 to FR-13, FR-20, FR-21, FR-30 to FR-35, FR-40, FR-42, progress view, answer view, benchmark report.

**Should:** Insight Mode, key health panel, source ranking, hosted website with login.

**Could:** coding mode, Markdown export, academic search sources.

### 12.2 Benchmark plan

- 30–50 questions across math and science, reasoning, coding and research-style questions, with known answers where possible.
- Baseline: the best single free model, run once per question. Second baseline: simple "ask 3 models and take the majority" to show that orchestration beats naive voting.
- Grading: automatic where answers are checkable; a fixed rubric for open questions; shuffle and hide system names when grading.
- Output: a one-page results slide (win rate, average consensus score, calls per tier, failure rate).

### 12.3 Demo script (target 3 minutes)

1. One-sentence pitch (the core promise).
2. Ask a question that single models often get wrong (chosen from benchmark failures).
3. Show the single-model answer for contrast.
4. Run Assembly on the 3-minute tier; narrate the progress view and the disagreement being resolved.
5. Show the final answer and sources.
6. Show the benchmark slide, then the key-security point (keys never leave the machine).

### 12.4 Demo safeguards

- Run the demo from the local Windows app, not a free-tier hosted server.
- Keys from at least three providers loaded and tested the morning of the demo.
- A recorded replay of a successful run as a fallback if the network or a provider fails.
- Pre-selected demo questions rehearsed at least 10 times.

## 13. Roadmap (relative; adjust once the deadline is known)

| Phase | Focus | Exit criteria |
| --- | --- | --- |
| 0 | Finish the existing MVP | Real keys added; one end-to-end run (question to sourced answer) works |
| 1 | Reliability and capacity | Quota tracker, 429 handling, distinct-family router, key redaction, log-scan test |
| 2 | Benchmark harness | Question set, baselines, grading script, first results |
| 3 | Frontend upgrade | Next.js + TypeScript + Tailwind; Key Setup wizard; progress view; answer view |
| 4 | Windows app | Desktop shell with bundled backend; keys in Credential Manager; installer builds |
| 5 | Demo polish | Insight Mode (if approved), replay fallback, rehearsals, slides |
| 6 | Hosted website (post-demo or in parallel if time allows) | Login, per-request keys, deployment on a long-running free host |

## 14. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Free limits change or shrink | Plans stop fitting | Quota values are configuration, verified in each provider's dashboard; planner adapts |
| One provider's free tier retains or trains on inputs | Privacy concern | Per-provider notice; do not send sensitive data; local models as a later option |
| Same-family models give correlated errors | False consensus | Distinct-family rule; adversarial round |
| Free models are weaker than paid ones | Benchmark margin is small | Honest baselines; focus on verification wins; choose questions fairly |
| Free hosting sleeps or times out on long runs | Website demo fails | Demo from local app; website is secondary |
| Users find key setup too hard | Drop-off | Wizard with direct links and a Test button; two-provider minimum mode |
| Long runs and WebSocket drops | Lost progress | Execution state stored; client can re-attach |

## 15. Open questions

1. **When is the hackathon deadline?** This decides which phases are cut.
2. **Approve Insight Mode?** It improves the demo but changes a v0.1 non-goal.
3. **Does the competition require a hosted, publicly reachable site**, or is a local app plus a short website acceptable?
4. **Is a team working on this,** or is it one developer? This affects the scope of the benchmark and the frontend migration.
5. **Which question types will the judges see?** The benchmark and demo questions should match.

## 16. Companion documents

- **TECH\_STACK.md:** chosen technologies, the free model lineup and how to get each key, hosting, and key-security design.
- **WORKFLOW.md:** the execution pipeline step by step, state machine, consensus and stopping logic, failure handling, and the build workflow.

*Free-tier limits quoted in the companion documents come from third-party summaries checked in October 2026 and must be verified in each provider's own dashboard before the demo.*
