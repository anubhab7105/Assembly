# Assembly — Product Requirements Document

*Multi-Agent AI Consensus Platform · v1.1 · October 10, 2026 · Owner: Anubhab Das · Supersedes v1.0 (October 8, 2026)*

## Status key

| Status | Meaning |
| --- | --- |
| Done | Built as specified. |
| Done-different | Deliberately changed; cites the superseding decision ID. The old text stays quoted for traceability. |
| Deferred | Post-demo; not required for the demo or the web deploy. |
| Optional | Stretch; not required for demo or deploy. |
| Out of scope | Will not be built in this release. |

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
| Infrastructure | PostgreSQL, Redis, Kubernetes-style scale | **SQLite + in-memory event bus** for the demo; Postgres only for the hosted website (v1.0; superseded in v1.1 — no database for web, SQLite for desktop only, D8). Redis dropped from MVP. |
| Time tiers | Fixed agent counts | **Capacity-aware**: the plan adapts to the free quota the user's keys actually have. |
| Accounts (v1.1, D8) | Login + per-user server history (v1.0 FR-41) | **No accounts, no login, no server-side storage in any mode.** Web history lives in the browser (IndexedDB); desktop history is local SQLite. |

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
| D8 | No accounts, no login and no server-side data storage in any mode. | BYOK + privacy (nothing on the server to leak) + simpler hosting (no database to run). See consequences in section 8.4 and risks in section 14. |

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
| FR-11 | Budget enforcement across time, tokens, agents, searches and per-provider quotas; this may be split across components (for example BudgetController and QuotaLimiter). | M |
| FR-12 | Context compression between rounds so cost does not grow quadratically with team size. | M |
| FR-13 | Provider failure triggers fallback to another family; a 429 triggers backoff and a quota cooldown for that key. | M |
| FR-14 | Coding mode with a shared artifact (code and tests) and security and performance reviewers. | Optional — Deferred post-demo (see note below). |

Note on FR-11: time/token/agent/search budgets live in `src/orchestration/budget_controller.py`; per-provider rpm/rpd/tpm quotas, cooldowns and fingerprints live in `src/providers/quota.py`; capacity planning reads both in `src/orchestration/capacity.py`.

Note on FR-14: the planner field `needs_code_execution` exists (`src/orchestration/planner.py`) but has no consumer; it is reserved for a future coding mode. No shared code/test artifact and no security/performance reviewers exist.

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
| FR-36 | Key health panel: valid, rate-limited, exhausted for today. | C (acceptance: per-key status is visible in Settings — see note below). |

Note on FR-36: each provider card in Settings shows a per-key status (`unknown` / `valid` / `invalid` / `rate_limited` / `testing`, `frontend/src/components/keys-manager.tsx`) plus a family-readiness chip. There is no consolidated valid / rate-limited / exhausted-for-today panel with cooldown display.

### 8.4 Accounts and history (D8: no accounts anywhere)

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-40 | Windows app: no login required; history stored locally in SQLite. | M |
| FR-41 | Done-different (see D8). Old text, kept for traceability: "Website: sign up, login, Google OAuth, history per user." There is no signup, login, OAuth, or per-user server history; web history lives in the browser. | — |
| FR-42 | Conversation and execution history with final answer and sources: web UI history/settings in browser IndexedDB with localStorage fallback (`frontend/src/lib/storage.ts`, versioned Export/Import JSON); desktop backend execution history in local SQLite (`src/database/models.py`, desktop-only endpoints in `src/api/executions.py`). | M |
| FR-43 | Copy or download the final answer as Markdown (`frontend/src/components/final-answer.tsx`). | Done |

D8 consequences, stated honestly: no cross-device sync. Web history lives in the browser (IndexedDB) and can be lost if site data is cleared, so Export/Import exists (`StorageService.exportJSON`/`importJSON` in `frontend/src/lib/storage.ts`). Desktop history is a local SQLite file. Abuse control without accounts relies on per-IP rate limits, a server concurrency cap and origin checks (`src/core/rate_limit.py`, `src/api/run.py`, `src/main.py`).

## 9. Platforms

- **Website:** Next.js frontend, hosted stateless FastAPI backend (`POST /api/run`, SSE) that runs executions and streams progress. No accounts, no login, no server-side storage (D8).
- **Windows app:** the same frontend in a desktop shell, with the Python backend bundled and run locally; history in local SQLite.
- Both share one frontend codebase and one backend codebase. The only difference is where the orchestrator runs and where keys are stored.

### 9.1 Release tracks

| Track | Target | Gate for web deploy? |
| --- | --- | --- |
| R1 — stateless website | Deployed frontend + stateless backend (D8). This is the deploy target. | Yes: R1 readiness gates the web release. |
| R2 — Windows desktop app | Tauri shell + bundled backend (track R2, separate release). | No: R2 is not a gate for the web deploy. |

R2 open pre-release items (verified in the repo): `desktop/src/` is scaffold only (`main.ts`, `styles.css`, `assets/` — the Next.js build is not wired in); `productName` is still `tauri-app` (`desktop/src-tauri/tauri.conf.json`); no installer artifact exists under `desktop/`; no clean-VM install test has been recorded. See `docs/windows-release.md` for the build and checklist procedure.

Details and rationale are in the companion document TECH\_STACK.md.

## 10. Non-functional requirements

**Security and privacy**

- Keys never written to the database, logs, analytics or crash reports.
- No user accounts, no user login tokens, no per-user server data in any mode (D8). The only token is the desktop shell's per-launch local token (`X-Assembly-Token`, `src/main.py`), which only stops other local programs from calling the backend.
- All website traffic over HTTPS; keys sent per request in headers or body, never in URLs.
- Prompt-injection awareness: web content is treated as untrusted data, never as instructions to agents.
- Users are told which providers may retain or train on their inputs.

**Reliability**

- Any single provider can fail mid-run without failing the execution.
- Re-attach depends on the mode: desktop executions survive a WebSocket disconnect and can be re-attached (`after_seq` replay plus the `GET /{id}/events` REST fallback, `src/api/executions.py`); web `/api/run` SSE runs have no re-attach — a client disconnect cancels the run (`src/api/run.py`).
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

### 11.4 Insight Mode (Optional)

Status: Optional — revisit after the benchmark and rehearsals.

What exists today: the executions view always shows a debate/progress timeline (open and resolved disagreements, sources checked, consensus trend, event log — `frontend/src/app/executions/page.tsx`). The off-by-default Insight Mode toggle is not built; there is no `Insight` control anywhere in `frontend/src/`.

### 11.5 Settings

Key management, provider health, privacy notices. Theme setting: Optional (the app ships one dark theme via Tailwind tokens in `frontend/src/app/globals.css`; no user-facing theme switch exists).

## 12. Hackathon plan

### 12.1 Scope tiers

**Must (demo-critical):** FR-1 to FR-13, FR-20, FR-21, FR-30 to FR-35, FR-40, FR-42, progress view, answer view, benchmark report.

**Should:** source ranking, stateless hosted website R1 (no login, D8).

**Could:** coding mode (FR-14), academic search sources, key health panel consolidation (FR-36), Insight Mode toggle, theme setting.

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

### 12.4 Demo fallback ladder

Climb down only when the rung above is not ready. Prerequisites are stated so nobody assumes a setup that does not exist.

1. **Deployed website (R1)** — but only if a full 5-minute run has been tested on the host (free hosts sleep and cap long requests; an untested deploy is not a demo plan).
2. **The website stack run locally on the demo laptop** (backend + frontend on localhost) — but only if a documented one-command start exists. It does not: `make run` starts the backend only (`Makefile`), the frontend needs `npm run dev` in `frontend/`, and there is no combined script in `scripts/`. Action item: document or script a single local-start command before relying on this rung.
3. **Windows app (R2)** — only if the R2 pre-release items in section 9.1 are done (branded installer built, clean-VM test recorded).
4. **Recorded replay** — always available as the last resort (`scripts/record_run.py`, `scripts/replay_run.py`).

Other safeguards, unchanged: keys from at least three providers loaded and tested the morning of the demo; pre-selected demo questions rehearsed at least 10 times.

## 13. Roadmap (relative; adjust once the deadline is known)

| Phase | Focus | Exit criteria |
| --- | --- | --- |
| 0 | Finish the existing MVP | Real keys added; one end-to-end run (question to sourced answer) works |
| 1 | Reliability and capacity | Quota tracker, 429 handling, distinct-family router, key redaction, log-scan test |
| 2 | Benchmark harness | Question set, baselines, grading script, first results |
| 3 | Frontend upgrade | Next.js + TypeScript + Tailwind; Key Setup wizard; progress view; answer view |
| 4 (track R2) | Windows app (separate release; not a gate for R1) | Branded shell (no `tauri-app` strings), backend sidecar bundled, keys in Credential Manager, installer builds, clean-VM install test recorded (`docs/windows-release.md`) |
| 5 | Demo polish | Replay fallback, rehearsals, slides |
| 6 (track R1) | Stateless hosted website (D8: no login, no server storage) | Per-request keys over HTTPS, deployment on a long-running free host, one full 5-minute run tested on the host |

## 14. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Free limits change or shrink | Plans stop fitting | Quota values are configuration, verified in each provider's dashboard; planner adapts |
| One provider's free tier retains or trains on inputs | Privacy concern | Per-provider notice; do not send sensitive data; local models as a later option |
| Same-family models give correlated errors | False consensus | Distinct-family rule; adversarial round |
| Free models are weaker than paid ones | Benchmark margin is small | Honest baselines; focus on verification wins; choose questions fairly |
| Free hosting sleeps or times out on long runs | Website demo fails | Demo from local app; website is secondary |
| Users find key setup too hard | Drop-off | Wizard with direct links and a Test button; two-provider minimum mode |
| Long runs and WebSocket drops | Lost progress | Desktop execution state stored; desktop client can re-attach (`after_seq` replay). Web SSE runs cancel on disconnect — use the replay fallback, not re-attach |
| No accounts means no server-side abuse identity (D8) | One IP can burn shared free-host resources | Per-IP rate limits, server concurrency cap, SSE/WebSocket origin checks (`src/core/rate_limit.py`, `src/api/run.py`, `src/main.py`) |
| Web history lives only in the browser (D8) | User clears site data and loses history | Export/Import JSON in Settings (`frontend/src/lib/storage.ts`); say so in the UI before the demo |

## 15. Open questions

1. **When is the hackathon deadline?** This decides which phases are cut.
2. **Does the competition require a hosted, publicly reachable site**, or is a local app plus a short website acceptable?
3. **Is a team working on this,** or is it one developer? This affects the scope of the benchmark and the frontend migration.
4. **Which question types will the judges see?** The benchmark and demo questions should match.

(Resolved in v1.1: Insight Mode approval — it is Optional; revisit after the benchmark and rehearsals.)

## 16. Companion documents

- **TECH\_STACK.md:** chosen technologies, the free model lineup and how to get each key, hosting, and key-security design.
- **WORKFLOW.md:** the execution pipeline step by step, state machine, consensus and stopping logic, failure handling, and the build workflow.

*Free-tier limits quoted in the companion documents come from third-party summaries checked in October 2026 and must be verified in each provider's own dashboard before the demo.*

## 17. Changelog (v1.1 · October 10, 2026)

- Status key added (Done, Done-different, Deferred, Optional, Out of scope).
- D8 added to the section 6 decisions table: no accounts, no login, no server-side storage in any mode.
- FR-41 marked Done-different (superseded by D8); section 8.4 rewritten (FR-40 unchanged; FR-42 notes IndexedDB for web and SQLite for desktop; D8 consequences stated).
- Section 1 table: Accounts row added; Infrastructure row notes the v1.1 supersession.
- Section 9: release tracks added (R1 stateless website gates the web deploy; R2 Windows app is separate) with verified R2 pre-release items.
- Section 10: security notes the desktop-only local token; re-attach described per mode (desktop `after_seq` replay; web SSE disconnect cancels).
- FR-11 reworded (split across BudgetController and QuotaLimiter, with file locations).
- FR-14 set to Optional / Deferred; planner `needs_code_execution` noted as reserved with no consumer.
- Insight Mode (11.4) set to Optional with current-state note; removed from section 12.1 Should and section 15; decision recorded to revisit after benchmark and rehearsals.
- FR-36 priority set to Could with acceptance note (per-key status in Settings).
- Theme setting (11.5) marked Optional.
- Section 12.1 Should/Could lists updated (no login; demoted items moved to Could).
- Section 12.4 rewritten as a 4-rung demo fallback ladder with prerequisites (incl. the missing one-command local start as an action item).
- Section 13: Phase 4 marked track R2 and Phase 6 track R1 with per-track exit criteria.
- Section 14: abuse-without-accounts and browser-only-history risks added.
- Section 15: Insight Mode question resolved and removed; remaining questions renumbered.
- `docs/prd-gap-report.md` created for v1.1; `BUILD_PROMPTS.md` was not found in the repo (see decisions log for the intended Prompt 6.1/6.2/8.4 markings).
- Issue #21: FR-42 clarified browser vs desktop history and fallback storage; FR-43 marked Done because Markdown copy/download controls are implemented. Browser persistence and import failure contracts now have a dedicated Vitest suite wired into CI.
