# Backend Audit — `src/` vs `docs/PRD.md` and `docs/WORKFLOW.md`

*Date: 2026-10-08 · Method: full read of `src/` (providers, agents, orchestration, api, database, research, core) plus grep verification (`wait_for|Semaphore|timeout`, `asyncio.gather`, `family`, `keyring|429|backoff|models.yaml`). No code changed.*

## 1. FR status table (PRD §8; IDs are non-contiguous in the PRD)

| FR | Requirement (short) | Status | Implements / notes |
|---|---|---|---|
| FR-1 | Planner classifies question, outputs team plan | done | `src/orchestration/planner.py:Planner.plan`, `_parse_plan`, `_default_plan` fallback |
| FR-2 | Team always has Solver + Critic + Synthesizer; Researcher when needed | partial | Prompt requests roles (`planner.py:59-63`), orchestrator always appends synthesizer (`orchestrator.py:253`); nothing validates LLM team contains Solver/Critic; Researcher depends on LLM flag only |
| FR-3 | Stage 1 independent solve, agents can't see each other | partial | First-round prompts are question-only (`solver.py:93-98`, `critic.py:93-104`, `researcher.py:91-95`); no enforcement — caller could pass peer data on round 1 |
| FR-4 | Structured JSON + schema validate + 1 retry + fallback model | partial | Contract + `_extract_json`/`_parse_response` + critique ID-filter exist (`base_agent.py:117-240`); retry/fallback/schema-check absent — failure returns text fallback at confidence 0.6 (`base_agent.py:149-158`) |
| FR-5 | Debate only on open disagreement; each round must change something | partial | Loop gated on consensus `decision == "continue"` (`orchestrator.py:200-204`); no explicit open-disagreement check, no per-round delta requirement |
| FR-6 | Consensus score from agreement/confidence/evidence/contradictions/new-info | done | `src/orchestration/consensus.py:ConsensusEngine.evaluate` (`:60-100`); weights differ from WORKFLOW §6 (0.35/0.20/0.20/0.15/0.10 vs 0.30/0.20/0.25/0.15/0.10), confidence is raw mean not calibrated |
| FR-7 | Adversarial round on early high agreement | partial | Devil's-advocate prompts in `critic.py:23-56,84-91`; no trigger, no round logic, no early-agreement detection anywhere |
| FR-8 | Stopping rule: threshold + low new-info, or safety cutoff pre-deadline | partial | `_make_decision` + `should_force_synthesis` wiring (`consensus.py:232`, `orchestrator.py:203,229`); path (b) looser than spec (new-info 0.225 vs 0.15, round≥2 + confidence gates added); reserve is flat 30 s, not `max(25 s, 12%)`; no round-time estimate |
| FR-9 | Weak consensus → answer states uncertainty | partial | Prompt-only (`synthesizer.py:31,34,92` + `remaining_uncertainty` plumbing); WORKFLOW §6 score tiers (≥0.85 / 0.60–0.85 / <0.60) not implemented programmatically |
| FR-10 | Router assigns by role, ≥3 distinct families | partial | Role routing table exists (`router.py:route`, `_get_routing_table`, `route_for_planning`); family concept absent — zero `family` mentions in `src/` (grep); counts providers, not families |
| FR-11 | Budget controller: time/token/agent/search/per-provider quotas | partial | Time/tokens/agents/rounds/searches enforced (`budget_controller.py:53-166`); per-provider rpm/rpd quota fields don't exist |
| FR-12 | Context compression between rounds | done | `src/orchestration/debate.py:DebateManager._compress_outputs` (`:107`): positions ≤1500 chars, evidence ≤3, reasoning ≤500, uncertainties ≤2, drops `raw_content` |
| FR-13 | Provider failure → fallback family; 429 → backoff + cooldown | partial | Failures isolated via `gather(return_exceptions=True)` → low-confidence fallbacks (`agent_manager.py:144-153`, `debate.py:88-92`); no 429 detection, backoff, cooldown, or replan anywhere in `src/` |
| FR-14 | Coding mode with shared artifact + reviewers | missing | — |
| FR-20 | Free web search + graceful fallback | partial | `src/research/search.py:SearchEngine.search` + `_tavily_search` (15 s timeout) with empty-list fallback; no free-source alternative (Wikipedia/arXiv/etc.) |
| FR-21 | Only used sources cited, numbered citations | missing | `citation_manager.py:get_final_sources(used_only=True)` ignores the flag, returns all sources; no numbering |
| FR-22 | Source dedupe + credibility ranking | partial | Dedupe by URL done (`add_source`/`_seen_urls`); no ranking code; `Source.credibility_score` unused |
| FR-23 | Free academic sources (arXiv/Semantic Scholar/Wikipedia) | missing | — |
| FR-30 | Key Setup wizard + Test button | missing | Only `.env` path; router log says "Add more API keys to .env" (`router.py:70-74`) |
| FR-31 | Windows Credential Manager storage | missing | No `keyring` code in `src/` (grep); plain `.env` via `config.py` |
| FR-32 | Website: browser-memory keys, no server persistence | missing | Contradicted: server-env keys only (`config.py:42-46`); `ExecutionRequest` has no key fields, `generate()` takes no per-request key |
| FR-33 | Keys redacted from logs/errors/stored records | missing | No masking filter in `logging_config.py:setup_logging`; only DB-URL masking exists (`main.py:_mask_db_url`) |
| FR-34 | Per-provider quota tracker (rpm/rpd) for planner | missing | Zero `rpm|rpd|quota` implementation hits in `src/` (grep) |
| FR-35 | Per-provider privacy notice | missing | — |
| FR-36 | Key health panel (valid/rate-limited/exhausted) | missing | Only boolean `is_available()`/`has_provider()` + ✓/✗ startup log (`router.py:61-63`) |
| FR-40 | Desktop: no login, local history | missing | All conversation/execution routes require JWT; no anonymous mode |
| FR-41 | Website auth: signup/login/OAuth, per-user history | partial | `api/auth.py:signup/login/get_me` + per-user scoping done; Google OAuth absent |
| FR-42 | Conversation/execution history with answer + sources | done | `api/conversations.py:list/get/delete`, `api/executions.py:get_execution/_run_execution` persists `final_answer/final_sources` + `Message(sources, execution_id)` (mostly) |
| FR-43 | Export answer as Markdown | missing | — |

Tally: **4 done · 13 partial · 12 missing.** WORKFLOW.md pipeline gaps (beyond the table): stage [0] capacity check, stage [5b] adversarial round, in-loop research/verify, and all §8 event names/states (`CAPACITY_CHECK`, `TEAM_READY`, `EVALUATING`, `CANCELLED`, `FAILED_PARTIAL`, `quota.warning`, `timer.tick`, …) are absent; planner output lacks `needs_code_execution`, `suggested_roles`, `estimated_rounds` (`planner.py:149-155`); the `except` path in `orchestrator.py:321` returns `status="failed"`, not a best-effort answer.

## 2. Places where API keys could leak

1. **No key-masking log filter.** `src/core/logging_config.py:setup_logging` (`:11-33`) uses a plain formatter. AGENTS.md requires a masking filter — it was never added.
2. **Raw exception strings logged in every provider.** `gemini_provider.py:generate` (`:77`), `groq` (`:57`), `cerebras` (`:61`), `openrouter` (`:61`), `huggingface` (`:70`), `experiential` (`:64`) all do `logger.error(f"…Error: {e}")` + `raise`. If an SDK echoes key material or request bodies in the exception, it lands in logs verbatim. Same pattern in `executions.py:_run_execution` (`:251`).
3. **JWT in URL + WS auth bypass.** `executions.py:websocket_progress` (`:140-149`): token arrives as `?token=` query param (frontend sends it at `frontend/js/app.js:448`) — tokens in URLs land in server/proxy logs. Worse, `if token:` means a **missing token skips verification and is allowed**; only a supplied-but-invalid token is closed (`4001`). No ownership check of execution vs user.
4. **Weak default JWT secret.** `core/config.py:31` defaults `jwt_secret_key` to `"change-me-to-a-random-secret-key-at-least-32-chars"` — if `.env` is unset, tokens are forgeable. No startup fail-fast on placeholder secret.
5. **BYOK-per-request path doesn't exist, so keys can only live server-side.** `database/schemas.py:ExecutionRequest` carries only `question/time_budget_minutes/conversation_id`; no provider `generate()` accepts a per-request key; everything reads `settings.*_api_key` from `.env`. FR-32 is contradicted by construction.
6. Clean (verified, keep it so): no key columns in `database/models.py` (`AgentRun` stores `model`/`provider` names only, `:118-119`); no key echo in `database/schemas.py` responses; `_run_execution` sets `status="failed"` without returning exception text; `health_check` returns `{connected:bool}` only; `main.py:_mask_db_url` (`:35-37`) masks the DB password at startup. User questions **are** stored verbatim (`Execution.question`, `Message.content`) — fine for keys, but sensitive question text persists; don't log it.

## 3. Hard-coded model names and provider assumptions

`models.yaml` does not exist (glob); the "all limits/names live in config" rule is violated in:

- `src/core/config.py:49-53` defaults: `gemini-2.0-flash`, `llama-3.1-8b-instant`, `llama-3.3-70b`, `meta-llama/llama-3.1-8b-instruct:free`, `meta-llama/Meta-Llama-3-8B-Instruct`.
- `gemini_provider.py:84` (`get_available_models`): `gemini-2.0-flash, gemini-2.5-flash, gemini-2.5-pro`.
- `groq_provider.py:64`: `llama-3.1-8b-instant, llama-3.3-70b-versatile, mixtral-8x7b-32768`.
- `cerebras_provider.py:68`: `llama-3.3-70b, llama-3.1-8b`.
- `openrouter_provider.py:68-73`: `meta-llama/llama-3.1-8b-instruct:free, meta-llama/llama-3.1-70b-instruct, mistralai/mistral-7b-instruct:free, google/gemma-2-9b-it:free`.
- `huggingface_provider.py:77-81`: `meta-llama/Meta-Llama-3-8B-Instruct, mistralai/Mistral-7B-Instruct-v0.3, microsoft/Phi-3-mini-4k-instruct`.
- `router.py:_get_routing_table` (`:160-229`) + `route_for_planning` (`:235-241`): repeats the above literals per role/budget.
- `experiential_provider.py:15-16,71`: `EXPERIENTIAL_BASE_URL="https://api.experientiallabs.ai/v1"`, model `"gpt-6-astra"`.

Provider assumptions baked into code: Cerebras/OpenRouter/Experiential are OpenAI-compatible `chat.completions.create` with hard-coded `base_url`s; Groq assumes `groq.AsyncGroq`; Gemini assumes `genai.GenerativeModel.generate_content_async` + `usage_metadata`; HuggingFace assumes sync `InferenceClient.chat_completion` (bridged via `run_in_executor`, `:52`) with OpenAI-shaped `choices[0].usage`; OpenRouter assumes the `:free` suffix convention. Dead code: `experiential_provider.py` reads `settings.experiential_api_key` / `settings.experiential_default_model` (`:24-29`), which **don't exist** in `config.py` — instantiation raises `AttributeError`; router docstring claims 6 providers but wires 5 (`router.py:8,49-55`).

## 4. Concurrency and timeout risks in orchestration

1. **Unbounded `gather`, no timeouts.** The only two `asyncio.gather` sites — `agent_manager.py:140` (`run_all_independent`) and `debate.py:80` (`run_debate_round`) — use `return_exceptions=True` with no `Semaphore`, no `asyncio.wait_for`, no per-agent timeout. Grep confirms **zero** `wait_for`/`Semaphore` in `src/` and no timeout parameter on any provider `generate()` (`base.py:45`); the single network timeout in the codebase is Tavily's `httpx.AsyncClient(timeout=15.0)` (`search.py:52`).
2. **No outer deadline — the hard time budget is cooperative, not enforced.** `Orchestrator.execute()` (`:76`) never wraps phases in a deadline. Budget is consulted only *between* phases: `can_search()` (`:156`), the debate `while decision == "continue" and can_debate() and not should_force_synthesis()` (`:200-204`), re-check at `:229`. A hung `Planner.plan()` (`planner.py:113`), solve phase, debate round, or `synthesize()` (`synthesizer.py:131`) cannot be pre-empted and blows the chosen tier silently.
3. **Final `synthesize()` runs unconditionally** (`orchestrator.py:264`) even when `should_force_synthesis()` is already true / token fraction ≥ 0.9 — the synthesis call itself can overrun the deadline it was meant to protect.
4. **Stale-data on total failure.** If all agents in a debate round fail, `debate.py:88-92` returns the previous outputs stamped `_failed_round`; only the consensus new-info exclusion (`consensus.py:203-210`) prevents false finalization — agreement/contradiction terms still compute over stale positions.
5. **Shared-mutable aliasing.** `debate.py:91` mutates `prev._failed_round` on an `AgentOutput` also referenced by the caller's list and already-published workspace payloads (snapshotted via `to_dict()`, so latent). `_compress_outputs` (`:129-141`) shares `supports`/`disagrees_with`/`sources` list objects by reference — any future in-place edit corrupts originals. `workspace.py` holds its lock only for append (`:69-72`) while `get_events`/`subscribe`/`cleanup` are lock-free, so `cleanup()` (`:123-126`, from `orchestrator.py:317/327`) can race a concurrent `publish`.
6. **Accounting gaps.** `record_agent_created` is write-only (never gated by `can_create_agent()`); `record_search(len(results))` (`orchestrator.py:163`) counts result items, not search calls; planner cost is never budgeted.

## 5. Top 10 fixes, ordered by risk to the hackathon demo

1. **Add per-call timeouts + an outer execution deadline.** Wrap each provider call (`asyncio.wait_for`, e.g. 60–90 s) and each phase so `execute()` *cannot* exceed budget + synthesis allowance. A single hung free-tier call today freezes the live demo with no recovery.
2. **Fix WS auth: reject missing tokens, check ownership, move token out of the URL.** Any audience member on the network can stream any execution's live progress; judges will probe exactly this after the security pitch.
3. **Add the key-masking logging filter (FR-33) and stop logging raw `{e}` from providers.** One rate-limit error echoing a key into logs demo-day violates the project's own headline metric (0 leaks) — and it's cheap (filter in `logging_config.py` + sanitize the six `generate` error logs).
4. **Make the router family-aware (FR-10).** Parse family from the model id, enforce ≥3 distinct families (warn at 2), force critic ≠ target family, collapse same-family votes to one in `_calculate_agreement`. Without this the "independent team" demo story is fiction — two Llama-backed solvers failing identically.
5. **Handle 429s: backoff with jitter + key cooldown + replan (FR-13/FR-34).** Free tiers (Groq ~30 rpm) *will* 429 during rehearsals; today that path is `logger.error + raise` with no recovery.
6. **Capacity-aware planning before starting (WORKFLOW §4).** Compute affordable calls from rpm/rpd with the 0.7 margin, pick the largest fitting plan, offer a smaller tier otherwise; set `synth_reserve = max(25 s, 12%)`. Prevents mid-run quota death on 10/15-min tiers.
7. **Retry once + fallback family on bad agent JSON (FR-4).** The silent confidence-0.6 text fallback feeds garbage into consensus and can finalize a nonsense answer on stage.
8. **Implement the adversarial trigger (FR-7/WORKFLOW §6).** Fire when score ≥ 0.85 in round 1 or all-agree-with-no-evidence, using the literal "assume the consensus is wrong" prompt. It's the signature anti-echo mechanism judges will ask to see.
9. **Fix citation integrity (FR-21/FR-22).** Honor `used_only`, emit numbered citations, add the official/academic/media/other ranking. "Sourced answer" is the demo's closing slide — unverified source lists undermine it.
10. **Fail fast at startup on bad config.** Refuse placeholder `JWT_SECRET_KEY`; fix or delete `experiential_provider.py` (currently `AttributeError` on init, unwired in router). A clean, verified boot sequence is the cheapest demo-day insurance.
