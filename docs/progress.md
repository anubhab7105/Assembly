# Project Progress Log

## Phase 1 — MVP Foundation (Completed)

### 1. Project Setup
- Initialized project structure under `src/`
- Created `requirements.txt` with all Python dependencies
- Created `.env.example` with environment variable template
- Created `.env` from template (API keys need to be added)

### 2. Core Layer
- `src/core/config.py` — Pydantic Settings loading from `.env`
- `src/core/security.py` — JWT token management, bcrypt password hashing, FastAPI auth dependency
- `src/core/logging_config.py` — Structured logging with UTF-8 Windows support

### 3. Database Layer (SQLite)
- `src/database/base.py` — SQLAlchemy engine, session factory, `init_db()`
- `src/database/models.py` — 11 ORM models: User, Conversation, Message, Execution, AgentRun, AgentMessage, DebateRound, ConsensusEvent, Source, Citation, Usage
- `src/database/schemas.py` — Pydantic request/response schemas for all API endpoints

### 4. AI Provider Abstraction (5 providers)
- `src/providers/base.py` — Abstract `AIProvider` interface with `generate()` contract
- `src/providers/gemini_provider.py` — Google Gemini integration (2.0 Flash, 2.5 Pro)
- `src/providers/groq_provider.py` — Groq fast inference (LLaMA 3.x)
- `src/providers/cerebras_provider.py` — Cerebras ultra-fast inference (LLaMA 3.3 70b, OpenAI-compatible API)
- `src/providers/openrouter_provider.py` — OpenRouter multi-model aggregation (LLaMA, Mistral, Gemma free tiers)
- `src/providers/huggingface_provider.py` — Hugging Face Inference API (LLaMA 3, Mistral, Phi-3)
- `src/providers/router.py` — Model Router: selects best provider/model per agent role; enforces minimum 3 live providers

### 5. Agent System (4 MVP agents)
- `src/agents/base_agent.py` — BaseAgent with structured JSON output parsing, provider abstraction, debate lifecycle
- `src/agents/solver.py` — Independent problem-solving with reasoning and evidence
- `src/agents/researcher.py` — Evidence gathering with web search integration
- `src/agents/critic.py` — Adversarial verification, echo chamber prevention
- `src/agents/synthesizer.py` — Final answer synthesis from team consensus

### 6. Orchestration Engine
- `src/orchestration/orchestrator.py` — Main execution pipeline: Plan → Team → Solve → Debate → Consensus → Synthesize
- `src/orchestration/planner.py` — LLM-based problem classifier (type, complexity, team composition)
- `src/orchestration/agent_manager.py` — Agent creation with provider rotation for diversity
- `src/orchestration/consensus.py` — Multi-factor consensus scoring (agreement, confidence, evidence, contradictions, new-info rate)
- `src/orchestration/debate.py` — Parallel cross-agent debate rounds
- `src/orchestration/budget_controller.py` — Time/token/agent/search budget enforcement
- `src/orchestration/workspace.py` — In-memory event bus (publish/subscribe per execution)

### 7. Research Engine
- `src/research/search.py` — Web search via Tavily API with graceful fallback
- `src/research/citation_manager.py` — Source deduplication and formatting

### 8. API Layer
- `src/api/auth.py` — POST `/api/auth/signup`, POST `/api/auth/login`, GET `/api/auth/me`
- `src/api/conversations.py` — GET/DELETE `/api/conversations/`, GET `/api/conversations/{id}`
- `src/api/executions.py` — POST `/api/executions/`, GET `/api/executions/{id}`, WebSocket `/ws/{id}`

### 9. Frontend (Single-Page App served by FastAPI)
- `src/static/index.html` — Auth views, chat interface, execution progress workspace, conversation sidebar
- `src/static/css/styles.css` — Premium dark-mode design system (glassmorphism, gradients, micro-animations, Inter + JetBrains Mono fonts)
- `src/static/js/app.js` — Auth flow, chat, WebSocket progress, workspace UI, time budget selector

### 10. Application Entry
- `src/main.py` — FastAPI app mounting all routers, CORS, static files, database init

---

## Verification Results

| Test                | Status |
|---------------------|--------|
| Server starts       | ✅ Running on http://localhost:8000 |
| Health check        | ✅ `{"status":"healthy"}` |
| Frontend serves     | ✅ HTML/CSS/JS at `/` |
| Signup API          | ✅ User created, JWT returned |
| Login API           | ✅ Authentication works |
| `/me` API           | ✅ Returns user profile |
| Conversations API   | ✅ List/detail/delete |
| Database auto-init  | ✅ `assembly.db` created |

---

## Pending / Next Steps

- [ ] Add API keys to `.env` (GEMINI_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, OPENROUTER_API_KEY, HUGGINGFACE_API_KEY — minimum 3 required)
- [ ] End-to-end execution test (ask question → get AI answer)
- [ ] Add Tavily API key for web search capability
- [ ] Migrate to PostgreSQL for production
- [ ] Add Google OAuth
- [ ] Add rate limiting and cost tracking
- [ ] Migrate frontend to Next.js + TypeScript

---

## Audit Fixes Applied

### Fix A — Robust JSON Parsing (`base_agent.py`) ✅
- **Problem:** `_parse_response` used fragile `split("```json")` string splitting. Failed on raw JSON, non-standard code fences, or JSON embedded in text.
- **Fix:** Replaced with `_extract_json()` — a regex + brace-depth-tracking extractor that strips any markdown fence, finds the first `{`, walks forward tracking nested braces/string escapes to find the matching `}`. Falls back gracefully with logging.

### Fix B — Agent ID Referential Integrity (`base_agent.py`, `solver.py`, `critic.py`, `researcher.py`) ✅
- **Problem:** LLMs were expected to output exact `agent_id` strings in `supports`/`disagrees_with` arrays but prompts never listed the valid IDs, and no validation existed to filter hallucinated ones.
- **Fix:** (1) `critique()` now passes `valid_agent_ids` list in context. (2) All three agent critique prompts (solver, critic, researcher) now explicitly list valid IDs with "You MUST use ONLY these exact IDs". (3) Post-parse validation in `critique()` strips any IDs not in the valid set.

### Fix C — Context Window Compression (`debate.py`) ✅
- **Problem:** Every debate round fed the full position, reasoning, and evidence of all other agents to each agent — O(N²) context growth caused token cost spikes and potential overflows on small-context models.
- **Fix:** Added `_compress_outputs()` to `DebateManager` which creates truncated copies before passing to critique: positions capped at 1500 chars, evidence at 3 items, reasoning at 500 chars, uncertainties at 2 items. Raw content is stripped. Original outputs remain intact for consensus evaluation.

### Fix D — Silent Failure Handling (`debate.py`, `consensus.py`) ✅
- **Problem:** When an API call failed during debate, the agent's previous output was silently re-inserted. This made the agent look "stubborn" (unchanged position), artificially lowering `new_info_rate` and prematurely triggering consensus finalization.
- **Fix:** (1) `DebateManager` now tags failed agent outputs with `_failed_round` attribute. (2) `ConsensusEngine._calculate_new_information_rate()` now accepts `round_number` and excludes any agent whose `_failed_round` matches the current round from the stabilization calculation, with a warning log.

### Fix E — Token Tracking (`base_agent.py`, `orchestrator.py`) ✅
- **Problem:** `total_tokens` was initialized to 0 in `orchestrator.py` but never updated. Providers already reported token counts in `ProviderResponse`, but the data was never propagated.
- **Fix:** (1) Added `tokens_used` field to `AgentOutput` dataclass. (2) `BaseAgent.run()` now copies `response.total_tokens` into the output. (3) `Orchestrator.execute()` now aggregates tokens after each phase (independent solve, each debate round, synthesis) and feeds them to `BudgetController.record_tokens()` for real cost/budget enforcement.

---

## Audit — Backend vs PRD/WORKFLOW (2026-10-08)

- Produced `docs/audit.md` (read-only audit, no code changed): FR-1…FR-43 status table (4 done, 13 partial, 12 missing), key-leak surface, hard-coded models, concurrency/timeout risks, top-10 demo-risk fixes.
- Headline gaps: no per-call timeouts or outer deadline (budget is cooperative); WS allows missing token with no ownership check; no key-masking log filter; router counts providers, not families (zero `family` mentions in `src/`); no 429 cooldown or capacity planning; adversarial trigger missing; `experiential_provider.py` is dead code that raises `AttributeError` if instantiated.

## Testing harness (2026-10-08)

- Added `requirements-dev.txt` (pytest, pytest-asyncio, respx, ruff) and `pytest.ini` (`asyncio_mode = auto`).
- New `src/providers/mock_provider.py`: scripted `MockProvider` (dict/JSON-fixture scripts routed by role markers, latency simulation, `rate_limit`/`timeout`/`malformed` fault injection, fake token counts, `MockRateLimitError` with `status_code` 429).
- New `tests/`: `conftest.py` (in-memory SQLite `db_session`, `MockRouter`, mock-backed `orchestrator`, sentinel `fake_key`, autouse socket guard blocking non-loopback connects), e2e orchestrator test (answer + token tracking + progress/workspace events), key-leak scan test (logs/result/events/DB rows), offline search tests (no-key fallback + respx-mocked Tavily).
- `Makefile` targets: `test`, `lint` (new files only — 277 pre-existing `src/` ruff violations left untouched), `run`.
- Result: **14 passed**, `ruff check` + `format --check` green on new files, zero external network access enforced by guard.

## Live smoke run with real keys (2026-10-08)

- Added `scripts/smoke.py` (loads `.env.dev`, 3-min budget, prints plan/team/per-round consensus/calls/tokens/wall-clock/answer+sources; names only, never keys) and `scripts/list_models.py` (names-only catalog probe).
- Verified: `.env.dev` present with 4 keys (gemini/groq/cerebras/openrouter); `.env.dev` already git-ignored.
- Final run: **completed** — plan general/medium, solver+researcher (groq/gemini), 1 debate round, 4 calls, 4358 tokens, 148.8 s, sourced final answer (React recommended, 5 sources).
- Bugs found and fixed (run-blocking only):
  1. `scripts/smoke.py` closure bug: loop-variable capture funneled every agent call into the last provider (OpenRouter) → all 400s. Fixed with default-arg binding.
  2. Stale hard-coded model IDs (every one retired): `gemini-2.0-flash` (404, removed), Groq `llama-3.1-8b-instant` / `llama-3.3-70b-versatile` (404, Groq serves no Llama at all now), OpenRouter slugs (`meta-llama/*`, `mistralai/*`, `gemma-2-9b`) invalid. Replaced with live-catalog IDs in `router.py`, `config.py`, 4 provider `get_available_models()`, `.env.example`. Also fixed a botched substring replace that briefly produced `meta-llama/qwen-3.8-27b-instruct:free`.
  3. `gemini-2.5-flash` gated for new API keys (404 "available to new users" only on 3.x) → default/route is now `gemini-3.8-flash`.
  4. My own edit dropped `from src.core.config import settings` in `gemini_provider.py` (NameError, Gemini dead for one run) — restored immediately.
  5. `gemini-3.8-flash` solver call hung >8 min via legacy SDK (planner call works, ~9–24 s) — bounded with `asyncio.wait_for(120 s)` (`GENERATION_TIMEOUT_SECONDS`); timeout falls back to the low-confidence path and the run completes.
  6. `scripts/smoke.py` crashed printing the answer on Windows (cp1252 vs U+2011) — force UTF-8 stdout like `logging_config.py`.
- Not code bugs (no change made, noted for follow-up): Cerebras key returns **402 payment-required** (no free quota on that account; failure-fallback path handled it); `huggingface_hub` not installed here so that provider is dead in this env; OpenRouter errors echo `user_id` into logs (privacy note).

## Config-driven provider layer (2026-10-08)

- New: `models.yaml` (7 providers, roles/families/limits per TECH_STACK 3.5; limits + context are null placeholders with per-dashboard fill-in comments); `src/providers/config.py` (Pydantic loader, unknown family/role/base + missing file fail loudly); `src/providers/errors.py` (`RateLimited`+retry_after/`AuthError`/`ProviderDown`/`BadResponse`, Retry-After + HTTP exception classifiers); `src/providers/openai_compat.py` (one httpx provider for Groq/Cerebras/OpenRouter/Mistral/NVIDIA; bounded retries only on 429/502-504/timeout/connect, capped backoff, tolerant usage extraction); `src/providers/registry.py` (`get_provider(provider_id, api_key)`).
- Changed: `router.py` rewritten config-driven (role candidates + family from catalog order, `family` added to `ModelAssignment`, same ≥3 enforcement/API); `GeminiProvider` takes explicit key/model and raises shared error types; `HuggingFaceProvider` takes explicit key/model/models and is `enabled: false`; deleted `groq/cerebras/openrouter/experiential_provider.py`; removed `*_default_model` from `Settings` + `.env.example`; `requirements.txt`: added `pyyaml`, dropped `openai`+`groq` SDKs; `base.py` annotation micro-cleanup.
- Tests: `tests/test_provider_layer.py` (17 tests: catalog load/unknown-family/missing-field/missing-file, respx success/429+Retry-After→retry/ persistent-429/401-no-retry/timeout/malformed/missing-choices, translator shapes, registry build/reject, yaml-only id switch incl. live reroute after yaml edit).
- Result: **30 passed, 1 skipped** (skip = only 2 live keys in plain `.env`); `ruff check` + `format --check` green on `src/providers tests scripts`; grep proves zero model ids and zero `openai`/`groq` imports in `src/` (only the family enum in `config.py`).
- Incident during testing: a failing test repr'd the `Settings` object into output, exposing real `.env` keys in tool output — no keys entered the repo (diff scanned, `.env`/`.env.dev` ignored), but a key-masking log filter remains urgent (audit #3).

## BYOK key handling per TECH_STACK s5 (2026-10-08)

- New: `src/core/keystore.py` (`RequestKeyStore`, `KeyringKeyStore`, `EnvKeyStore`, `get_keystore()`, `reveal()`/`wrap_keys()`); `APP_MODE=dev|web|desktop` in config; `src/api/keys.py` (`POST /api/keys/test`, `GET /api/providers/status`, both JWT-authed); `ExecutionRequest.provider_keys` plumbed to `Orchestrator.execute(provider_keys=)` with isolated per-run router + wipe on both return paths.
- Changed: all key settings fields → `SecretStr` (incl. JWT secret + Tavily); `reveal()` at SDK/JWT/httpx call sites only; `ModelRouter(keys=...)` override with mode fallback (dev=env, web=none, desktop=keyring); `requirements.txt` += `keyring`; `make lint` gate extended to owned files.
- Tests: `tests/test_key_handling.py` (11 tests: store wrap/wipe/repr scans, keyring stub roundtrip, production refusal, mode mapping, full TestClient execution with fake per-request keys scanned across POST/GET responses + caplog + all DB rows, keys/test no-echo + 404, providers/status names-only vs live settings values).
- Result: **41 passed, 1 skipped**; `ruff check` + `format --check` green on gate paths; diff scanned secret-free; `.env`/`.env.dev` untouched/ignored.
- Bugs found: (1) f-string of `SecretStr` renders `**********` — would have sent a dead bearer token; fixed by `reveal()` at every header/SDK call site. (2) In-memory SQLite + TestClient threads need `StaticPool` (each pooled connection gets its own empty DB) — fixed in test helper. (3) `ruff --fix` removed a `typing.Optional` import but left usages → `NameError` at conftest import; fixed to `X | None`.
- Live note: post-refactor smoke hit Gemini **429 quota-exhausted** (today's runs consumed the free daily quota) and failed cleanly with no key material anywhere — good failure behavior, and live proof that 429 cooldown/retry (audit #5) is the next fix, not this task.

## Logging hardening + canary test (2026-10-08)

- `src/core/logging_config.py`: `KeyMaskingFilter` (Authorization/x-api-key headers → inline dict/list field values → scalar `key/api_key/provider_keys/token/secret/password` fields → provider prefixes → 40+ opaque tokens; UUIDs/counters/model names untouched) + `mask_text()`; attached to assembly logger, root, and named HTTP/SDK loggers.
- Generic client errors: orchestrator WS `error` event + failed answer are fixed strings; new 422 handler in `main.py` logs only `{type, loc, msg}` shapes and replies `{"detail": "Invalid request."}`.
- `tests/test_log_canary.py` (12 tests, canary `SECRET_CANARY_12345`): filter units, MockProvider success/failure runs (logs, on_progress/WS-shaped events, answer, store wipe), API run scanned across POST/GET bodies, caplog, raw SQLite **file bytes**, live-WS drain, 422 body, providers/status vs live settings values.
- Result: **53 passed, 1 skipped** (canary in default run); `ruff check` + `format --check` green on widened gate; diff secret-free.
- Bugs found: (1) field regex masked only the `{` of `provider_keys={...}` dict-reprs — added nested-container pattern + stripped 422 log inputs to shapes. (2) `RequestValidationError.errors(include_url=...)` doesn't exist in this FastAPI — dropped the kwarg. (3) Unpatched `socket.getaddrinfo` hangs ~tens of seconds on blackholed DNS instead of failing — test socket guard now blocks DNS too (fail-fast hermetic runs). (4) Multi-key API runs stall under TestClient (per-request portals orphan the background task past the poll window) — hermetic canary uses one key; event shapes covered via on_progress capture.

## Family-aware team routing (2026-10-08)

- Rewrote `src/providers/router.py`: `route_team()` (solvers-first distinct families, critic off solver families, spread-then-reuse, 2-family warning / 1-family degraded flag, quota-affordability filter with fail-open), `RoutingDecision` (+`ModelAssignment` alias), `fallback_for()` (different family → same family/other provider → None), `available_families()`.
- `AgentManager`: `create_team` via `route_team` (legacy rotation fallback for duck-typed routers), decisions stored per agent id, retry-once on RateLimited/QuotaExhausted/ProviderDown with stable ids, `get_agent_info` carries family/role/reason.
- Provenance stored: `ExecutionResult.routing/degraded/warnings` + `AgentRun` rows per agent via `_persist_agent_runs` (model/provider names only).
- Tests: `tests/test_routing.py` (13 tests: distinctness, reuse warning, critic rules incl. forced case, degraded modes, fallback ordering incl. None, quota skip, persistence helper, fallback retry, orchestrator recording).
- Result: **79 passed, 1 skipped**; `ruff check` + `format --check` green on widened gate (incl. agent_manager); diff secret-free.
- Bugs found: (1) test asserted the replaced agent object instead of `manager.agents[id]` after retry swap. (2) `ruff --fix` churn on legacy files kept out of the format gate (check-only for main/orchestrator).

## Quota limiter per (provider, key fingerprint) (2026-10-08)

- New: `src/providers/quota.py` (`QuotaLimiter`, `QuotaLease`, `QuotaExhausted`, `fingerprint_key`, `get_limiter`, UTC `today_str()`); `quota_usage` table (provider, fingerprint, day PK; counts + tokens; stale-day purge).
- Changed: `OpenAICompatibleProvider.generate` acquires a lease (est_tokens=max_tokens) and reports 429s with server Retry-After; `ModelRouter` takes `keys` + injectable `limiter`, fingerprints live keys, skips exhausted (cooldown/rpd-spent) in candidates and preferred path, adds `capacity_estimate()`; `Planner` attaches read-only `PlanResult.capacity`; `providers/status` reports live `rpm/rpd_remaining`, `cooldown_seconds`, per-key 3-min estimates.
- Tests: `tests/test_quota.py` (13 tests: fingerprint stability, rpm wait/raise, tpm, concurrency cap peak==2, cooldown + default, day rollover incl. yesterday untouched + no raw key in rows, router skip incl. preferred-provider fallthrough, planner attach + graceful None, status shape, singleton).
- Result: **66 passed, 1 skipped**; `ruff check` + `format --check` green on all touched files; diff secret-free.
- Bugs found: (1) ORM column defaults don't apply pre-flush — `(row.count or 0) + 1`. (2) New `day` PK column missing on insert (IntegrityError) — pass day explicitly. (3) 429-reporting into the shared singleton leaked cooldown state across provider-layer tests — per-test `reset()` fixture. (4) `ruff --fix` dropped a `typing.Optional` import but left usages (NameError) — converted to `X | None`.

## Capacity-aware planning per WORKFLOW §4 (2026-10-08)

- New: `src/orchestration/capacity.py` (pure: `affordable_calls` with 30% margin, `cost_of_plan`, `synth_reserve_seconds = max(25s, 12%)`, `can_start_round`, `heuristic_suggestion`, `plan_capacity` → `TeamPlan{agents, rounds, search_budget, estimated_calls, estimated_seconds, warnings, feasible_tier}` + feasible/downgraded/explanation; tier standards reproduce the WORKFLOW call bands); `ModelRouter.quota_snapshot()` (counts only); `GET /api/executions/preflight` (`PreflightResponse` in schemas, JWT-authed, heuristic-only so zero quota spent, names/counts only).
- Tests: `tests/test_capacity.py` (25 tests: margin/reserve/cost units, each tier vs WORKFLOW bands, many-key vs few-key fallback with explanation, exhausted daily quota → infeasible, unknown limits fail-open, no-key → 0, preflight plan/fallback/infeasible/400/401 + no-leak scan).
- Result: **104 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on gate incl. new `capacity.py`; diff secret-free (counts/names only by construction).
- Bugs found: (1) empty key list returned None (unlimited) — now 0, so keyless preflight is honestly infeasible. (2) First fallback design shrank custom teams inside the requested tier and mislabeled the envelope (descending ceiling check always matched the requested tier) — rewrote as WORKFLOW-faithful standard-tier fallback: requested standard → largest smaller standard → trimmed 3-min minimum → infeasible. (3) `/preflight` must be registered above `/{execution_id}` or Starlette swallows it as an ID.
- Follow-up (not this task): wire the verdict into `Orchestrator.execute` as the Phase 0 CAPACITY_CHECK gate; replace time-estimate constants with measured numbers after the first benchmark.

## Validated planner output per WORKFLOW §3 (2026-10-08)

- Changed: `src/orchestration/planner.py` — new `PlanSchema` (problem_type normalized, complexity literal, needs_research/needs_code_execution, non-empty suggested_roles, estimated_rounds 1–8); `PlanResult` gains suggested_roles/estimated_rounds/needs_code_execution/fallback_used while keeping `team_composition` (derived) for the orchestrator; cheapest-fast model with max_tokens 512; hardened `_extract_json` parsing; exactly one retry on invalid JSON (error message included, `fallback_for` model when available); heuristic fallback (keywords + length) so `plan()` never raises; roles capped by capacity tier ceilings + quota-aware trim via `plan_capacity` when the router exposes `quota_snapshot` (fail-open); legacy `team` shape translated.
- Tests: `tests/test_planner.py` (19 tests: valid/prose-wrapped/legacy/normalized shapes, malformed→single-retry success, persistent-malformed/empty/invalid-schema/empty-roles→fallback with exact provider call counts, transport-error→direct fallback, fallback-model retry routing, routing failure, tier + quota caps incl. infeasible-quota warning path, heuristic math/coding/multi_step/research typing, key-leak scan).
- Result: **123 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on the gate; diff secret-free.
- Bugs found: (1) ruff TRY004 on a `ValueError`-for-wrong-type raise — switched to `TypeError` and widened the retry catch to `(ValueError, TypeError)` so non-object JSON still gets its one retry. (2) Initial `ruff format` reflow plus an import-sort fix in the new test file.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Strict agent output contract + validation pipeline (2026-10-08)

- Changed: `src/agents/base_agent.py` — strict Pydantic `AgentOutput`/`EvidenceItem`/`SourceRef` (`extra="forbid"`); confidence clamp-and-record (`calibrate_confidence`, rejects bool/non-number/NaN/inf) with `calibrated_confidence` for consensus; `run()` pipeline validate → retry-once-with-error → router family fallback → `AgentValidationError`; Fix B ID-stripping kept; `_extract_json` unchanged; per-call provenance (provider/model/family/tokens/latency/raw). Four agents: exact-format prompts (reasoning_summary, evidence objects, empty supports/disagrees_with in independent mode); researcher reads injected `search_results` (was dead plumbing). Consumers: debate compression + `failed_round` field (Fix D), consensus calibrated reads, manager error-output + routing passthrough, orchestrator sources→dicts, new-shape mock scripts.
- Tests: `tests/test_agents.py` (26 tests: valid+provenance, strictness, malformed/missing/empty/non-numeric/bool/string-evidence/unknown-key failures with exact 2-call counts, retry message content, clamp ± with raw, NaN/inf rejection, summary truncation, consensus-on-calibrated, Fix B strip/pass-through, family fallback recover + failed-fallback raise, manager error output, independent-solve isolation ×3 agents + sniffing-provider, researcher keeps web results, synthesizer sources/footer, key-leak scan); obsolete text-fallback test rewritten to raise-after-retry.
- Result: **150 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on the gate (own new-code violations fixed; pre-existing style in ungated agent/consensus/debate files left untouched per small-diffs rule); diff secret-free.
- Bugs found: (1) variable shadowing in the fallback path (`provider` reassigned to a str, then `.provider_name` accessed) — split into `provider_obj`/`provider_name`. (2) `calibrate_confidence` raising ValueError for wrong types tripped TRY004 — TypeError for non-numbers, matching test updated. (3) Researcher web results were set on the agent but never read into the prompt — wired via attr fallback.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Consensus rework per WORKFLOW §6 (2026-10-08)

- Changed: `src/orchestration/consensus.py` — exact §6 formula (0.30/0.20/0.25/0.15/0.10) with weights + thresholds in `Settings` (`consensus_*`) via `ConsensusConfig`; family-stance agreement/contradiction (one vote per family, intra-family edges ignored, position-share fallback); `ConsensusReport` (score, decision, reason, factor breakdown, open disagreements, new_info_rate); 4 decisions in table order with `allow_adversarial` one-strike guard; `select_adversarial_critic` + `adversarial_round` (replaces critic output, re-scores); Fix D exclusion kept. `CriticAgent.adversarial_challenge` + assume-wrong prompt branch. Orchestrator: loop on DEBATE/ADVERSARIAL, one strike w/ status event + token accounting, then normal debate; `ConsensusEvent.decision` comment updated.
- Tests: `tests/test_consensus.py` (23 tests: config weights + rescale, exact formula math, one-vote-per-family vs naive, position fallback, unanimous-early + all-agree-no-evidence adversarial, precedence over finalize, split/converging/thrashing/failed-agent scenarios, all force paths, empty outputs, strike execution incl. prompt assertion + rescore, critic selection, report shape, no-position-logging, orchestrator end-to-end strike with adversarial event).
- Result: **173 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on the gate; diff secret-free.
- Bugs found: (1) two test-arithmetic slips (raw edge counts 6 not 3; round-1 evidence too thin for the 0.85 bar) — tests fixed, implementation untouched. (2) Unused imports/format in the new test file — `ruff --fix` + format.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Time controller + cancel + explicit states (2026-10-08)

- Changed: new `src/orchestration/time_controller.py` (`Deadline` w/ injectable clock + `FakeClock`, `TaskTracker`, `ExecState`/`StateMachine` per §2); orchestrator validates + publishes every transition, advisory CAPACITY_CHECK, `asyncio.timeout` on planner/synthesis/per-agent calls, deadline gates in debate loop, CancelledError → "cancelled" result; API `_run_tasks` + `POST /{id}/cancel` + cancelled/state persistence; `quota.acquire` cancel-hardened.
- Tests: `tests/test_time_controller.py` (27 tests: fake-clock deadline math, full §2 path + debate loop + abnormal exits + illegal moves, tracker cancel/drain/leak-free, quota lease release on cancel, manager/debate per-call timeouts + carry-forward, orchestrator hard cutoff (no DEBATING state) + ordered states + live cancel + unknown-cancel + key-leak scan, API cancel/teardown-persistence/404/403/idempotency).
- Result: **200 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on the gate; diff secret-free.
- Bugs found: (1) Cutoff test expected `debate_rounds == 0` but round 1 is the initial evaluation (pre-existing semantics) — asserted == 1 + no DEBATING state instead. (2) Bare TestClient uses per-request portals so slow background tasks die at request teardown — implemented thread-safe `_cancel_task`, rewrote API cancel tests for portal reality (teardown-persistence + injected foreign task); real-pipeline cancel covered at orchestrator level. (3) Duplicate helper + unused-noqa + test imports — fixed per ruff.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Progress event system per WORKFLOW §8 (2026-10-08)

- Changed: new `src/api/events.py` (17 Pydantic event models + envelope + sanitize + recorder + store + schema bundle); `execution_events` table; orchestrator remapped to §8 emits (round/disagreement/source/quota/timer/synthesis/completed/failed_partial/cancelled); API persists pre-broadcast, WS `?after_seq=` replay + live dedup, `GET /{id}/events` REST fallback; frontend new names + seq dedup + backoff re-attach; `scripts/export_event_schema.py` + committed `frontend/event-schema.json`.
- Tests: `tests/test_events.py` (20 tests: all-types validation + rejections, sanitize secrets/truncation/benign-preserved, dense seqs + no-gap-on-reject, disagreement diff incl. truncation, full mock run validates + dense + clean, persist/fetch order + dedup, REST order/limit/latest/auth, WS full/suffix/empty replay, canary end-to-end over REST+WS+DB-bytes, schema artifact + OpenAPI); updated e2e/canary/time/consensus tests to canonical names.
- Result: **220 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on the gate; diff secret-free.
- Bugs found: (1) strict validation caught a real bug — mock sources carry `snippet` but the model lacked it (added with documented rationale). (2) Starlette `receive_text()` takes no `timeout` kwarg (the old canary WS drain was silently collecting nothing) — tests now use exact-count blocking receives + ping/pong silence probe. (3) Two time-controller tests read lifecycle `state` from `data` instead of the envelope — updated to the new contract.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Final composer with verified citations (2026-10-08)

- Changed: new `src/orchestration/composer.py` (pure; bands High ≥0.85/Moderate ≥0.60/Low, [n] collection + evidence refs, dense renumbering, orphan→[?] with warnings, uncertainty/alternatives notes with honest fallbacks, shared footer, `VerificationSummary`, `compose_final_answer`); synthesizer prompt cites numbered sources + Markdown (contract unchanged); orchestrator composes post-synthesis, counts resolved disagreements, wires answer + verification into result and `execution.completed` event.
- Tests: `tests/test_composer.py` (22 tests: exact band edges + clamping, per-band section presence/absence, strongest-minority alternative, citation order/renumber/orphan/link-exclusion/evidence-refs, unreferenced exclusion, empty-sources omission, verification counts, footer rebuild + synthesizer parity, mock e2e composed shape, low-band orchestrator run, key-leak scan).
- Result: **242 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on the gate; diff secret-free.
- Bugs found: none in implementation; test-only fixes (role-routing stub router since MockRouter routes everything to the first provider; footer test converted to async).
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## ReplayProvider + record mode (2026-10-08)

- Changed: new `src/providers/replay_provider.py` (versioned JSON format, `RecordingProvider` decorator, `ReplayProvider` shared-FIFO + `delay_scale` + `ReplayExhaustedError`, `RecordingRouter`/`ReplayRouter` shims with family preservation); `scripts/record_run.py` + `scripts/replay_run.py` thin CLIs.
- Tests: `tests/test_replay.py` (16 tests: save/load round-trip + 5 corrupt-file rejections, response serialization, success/error capture, FIFO order + exhaustion, simulated delays, error replay, identity delegation, full record→replay answer equality, families, structural + env key-leak scan, CLI --help + in-process record/replay runs).
- Result: **258 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on the gate; diff secret-free.
- Bugs found: (1) `RecordingProvider` never wrote the `family` field that `ReplayRouter` reads — caught by the families test, fixed at the writer. (2) Test called `response_from_record` with the inner response dict instead of the full record — clarified API use. (3) TRY004 on isinstance-check raises + unused imports/noqa in new files — fixed per ruff.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Multi-provider research layer (2026-10-08)

- New: `src/research/schemas.py` (`SearchResult` + legacy-dict helper), `src/research/providers.py` (interface + Tavily/Wikipedia/arXiv/Semantic Scholar/DuckDuckGo-unofficial + quota exceptions), `src/research/router.py` (type ordering, budget, fallback, in-run cache); `tests/test_research.py` (21 respx-mocked tests + key-leak scan).
- Result: **279 passed, 1 skipped** (full suite, incl. untouched legacy search tests); `ruff check` + `format --check` green on all new files; diff secret-free.
- Bugs found: none in implementation; test-only note — respx GET routes match on path regardless of query params, so one mock per provider covers all queries.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Citation quality: dedupe, ranking, cross-verification (2026-10-08)

- Changed: rewrote `src/research/citation_manager.py` (canonical-URL + near-title dedupe, six-tier credibility rule table + ranking, claim→source tracking with `get_used_sources()`, 2+-domain cross-verification); added optional `verification` input to `ConsensusEngine.evaluate` / `_calculate_evidence_quality` (+0.15/verified claim, +0.3 cap, legacy scores unchanged by default).
- Tests: `tests/test_citations.py` (20 offline tests: dedupe, ranking, cross-verification, consensus boost/parity, end-to-end map flow).
- Result: **299 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on new/owned files (`consensus.py` pre-existing debt left untouched); diff secret-free.
- Bugs found: one typo I introduced in an `except` clause, caught on first test run and fixed; ruff FURB188/PIE810/I001 in new code fixed via `--fix` + one manual tuple merge.
- Skipped (per DoD): live real-key end-to-end run + key-leak scan — no live keys here and the module handles no secrets (pure URL/title logic).

## Prompt-injection defense for web content (2026-10-08)

- New: `src/research/sanitize.py` (strip → budget → delimit → detect); researcher/synthesizer prompts sanitized; standing `UNTRUSTED_CONTENT RULE` in all system prompts; orchestrator emits `agent.status` warning on tripwire hits (17-type event contract untouched); `docs/security.md` (defense + limits).
- Tests: `tests/test_sanitize.py` (21 tests: 10-snippet adversarial set across 5 categories, benign controls, strip/budget/escape/bundle units, prompt wiring, MockProvider hostile-context run).
- Result: **320 passed, 1 skipped** (full suite); `ruff check` + `format --check` green on new/owned files; diff secret-free.
- Bugs found: one attack snippet (`ignore the rules`) initially missed by the override regex — widened the middle-word set, all 10 flag correctly with benign controls still clean.
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-provider suite is the verification).

## Benchmark draft set (2026-10-08)

- New: `bench/questions.jsonl` (40 lines: 10 math_science, 10 logic_reasoning, 10 coding with embedded test cases, 10 research with 4-bullet rubrics) + `bench/README.md` (schema, counts, grading guidance, verification status).
- Schema per line: `{id, category, question, answer_type: exact|numeric|rubric, reference_answer, rubric (non-null iff rubric type), difficulty}`. All 40 `reference_answer` values prefixed `NEEDS HUMAN VERIFICATION` — human review required before scoring use.
- Verification: JSONL validated (40 lines, unique ids, 10/10/10/10 split, marker present on all 40, rubric iff rubric-type, exact key set); math/coding spot-checks executed (avg-speed 80, exponent 0, digit-9 count 20, last-digit 9, train 14.4 s, fib(20) 6765).
- Skipped (per DoD): full pytest run — data-only change touching no `src/`/`tests/` code; live end-to-end run — no live keys here.

## Benchmark runners + grader (2026-10-08)

- New/updated: `bench/run_single.py`, `bench/run_vote.py`, `bench/run_assembly.py`, `bench/bench_common.py`, `bench/grade.py`, `bench/README.md`, and `tests/test_bench_grade.py`.
- Runner behavior: all three runners write resumable `bench/results/<run_id>.jsonl` with `answer`, `calls`, `tokens`, `seconds`, `consensus_score`, and `errors`; all use local key-store routing, key redaction, and quota-aware sleeps. `run_vote.py` uses 3 family-distinct voters where available, majority vote first, voter-1 judge fallback for all-different answers. `run_assembly.py` runs the full orchestrator at tier 3/5/10/15 (default 5).
- Grader behavior: exact/numeric auto-grade with normalization/ranges; rubric answers are shuffled behind A/B/C labels and judged via a different-family live model when possible; outputs `graded_<run_id>.csv`, `graded_<run_id>_spotcheck.csv`, and summary win/tie/loss + mean scores.
- Verification: `python -m py_compile bench\grade.py bench\bench_common.py bench\run_single.py bench\run_vote.py bench\run_assembly.py`; `ruff check bench\grade.py tests\test_bench_grade.py`; `ruff check bench\grade.py bench\bench_common.py bench\run_single.py bench\run_vote.py bench\run_assembly.py`; `ruff format --check bench\grade.py tests\test_bench_grade.py bench\bench_common.py bench\run_single.py bench\run_vote.py bench\run_assembly.py`; `pytest tests\test_bench_grade.py` → 4 passed.
- Skipped (per DoD): live real-key end-to-end run and full benchmark grading — live provider keys/quotas are user-local and were not exercised here.

## Benchmark analyser + REPORT (2026-10-08)

- New: `bench/analyze.py` — standalone analysis script that ingests one or more `graded_*.csv` files produced by `bench/grade.py` and generates:
  1. **Win rates**: Assembly vs single, Assembly vs vote — overall and by category — with 95 % Wilson confidence intervals.
  2. **Cost view**: avg calls, tokens, and seconds per system/tier (reads companion JSONL run files for cost metadata when present).
  3. **Ablation table**: accuracy delta for `assembly_no_debate`, `assembly_no_critic`, `assembly_no_adversarial`, `assembly_same_family` variants; ranks by contribution.
  4. **Failure analysis**: per-question table where Assembly lost, with inferred reason from errors, consensus score, and answer excerpt.
  5. **Consensus weight suggestions**: lightweight proxy grid-search over (w_agreement, w_evidence) grid; emits best candidate weights and a ready-to-paste `.env` snippet; calls for a re-run to confirm improvement.
  6. **Three PNG charts** (via matplotlib): `win_rate.png` (grouped bar, category × system, CI error bars), `ablation.png` (horizontal bar, delta per component), `calls_vs_acc.png` (scatter, avg calls vs accuracy, bubble = avg tokens).
  7. **`bench/results/REPORT.md`**: full markdown report with all tables, chart embeds, and the env snippet.
- `bench/analyze.py` works in **demo mode** (`--demo` flag, or when no graded CSVs exist) using synthetic data calibrated to realistic win rates — useful for pre-run demos.
- Fixed variable-shadowing bug (`sys` loop variable shadowing `import sys` module) during development.
- Verification: `python bench/analyze.py --demo` exits 0; generates `bench/results/REPORT.md` (6430 B) and three PNG charts (`win_rate.png` 65 kB, `ablation.png` 52 kB, `calls_vs_acc.png` 57 kB). Console summary matches expectations.
- Skipped (per DoD): pytest tests for `bench/analyze.py` — no mock-provider dependency; full live run skipped (no keys).
