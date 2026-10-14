# Project Progress Log

## 2026-10-14 — Free-first crawler implementation (PR in progress)

- Added a bounded static HTML crawler under `src/research/crawler.py`, using existing HTTPX plus standard-library HTMLParser/RobotFileParser (no new runtime dependencies or paid API). It normalizes search results, fetches up to five pages per run, follows same-origin links to depth one, honors robots rules, and bounds response size, redirects, ports, and total time.
- Wired crawler enrichment into the existing researcher/search pipeline, respecting the synthesis reserve and preserving search snippets when crawling is blocked, unsafe, non-HTML, or unsuccessful.
- Added offline `respx` tests for extraction, same-origin traversal, page caps, robots exclusions, non-public DNS results, unsafe URLs, redirects, size/content-type failures, and Pydantic search-result normalization. Test execution is pending CI review.

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
- [x] Database portability experiment (historical; PostgreSQL hosting was superseded by D8, the stateless-web decision; SQLite remains for desktop/dev)
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

## Database Portability & Ownership (2026-10-08)

- Added `alembic` to `requirements.txt` and generated the baseline migration using `alembic init alembic` and `alembic revision --autogenerate -m "baseline"`.
- Validated SQLite-specific code removal; ensured `sqlalchemy.types.JSON` was used for cross-compatibility between SQLite and Postgres, and conditionally enabled thread-check in `src/database/base.py`.
- Added `user_id` column to `Execution` in `models.py` and modified `api/executions.py` to directly filter by `user_id` instead of checking the `Conversation` hierarchy. Also fixed `test_key_leak.py` and `test_time_controller.py` to properly expect HTTP 403 Forbidden on wrong user ownership.
- Wrote `docker-compose.yml` for Postgres local testing and updated `.github/workflows/ci.yml` with a matrix testing pipeline targeting both `sqlite` and `postgres` DB engines.
- Result: 325 backend tests passing.

## Security Threat Model & Audit Remediation (2026-10-09)

- Completed a STRIDE-style threat model (`docs/threat-model.md`) covering web and desktop modes, trust boundaries, and assets.
- **GAP-1 (Missing Rate Limits on Unauthenticated APIs):** Added `unauth_rate_limiter` dependency in `src/core/rate_limit.py` and applied to `POST /api/auth/login` and `POST /api/auth/signup` in `src/api/auth.py`.
- **GAP-2 (WebSocket Token in URL):** Moved WebSocket authentication from query parameters (`?token=...`) to a first-message JSON payload (`{"type": "auth", "token": "..."}`) in `src/api/executions.py` to prevent token leakage in CDN logs. Fixed all associated `TestClient` uses in `tests/test_events.py`, `tests/test_limits.py`, and `tests/test_log_canary.py`.
- **GAP-4 (JWT Secret Reuse for Quota Salt):** Added an explicit `quota_salt` field in `src/core/config.py` (via `QUOTA_SALT` env var). Updated `src/providers/quota.py` to use `quota_salt`, falling back to a dev random salt rather than the JWT signing key.
- **GAP-5 (WebSocket DoS via Connection Exhaustion):** Added `MAX_WS_CONNECTIONS_PER_EXEC = 20` cap per execution ID in `src/api/executions.py`.
- **GAP-6 (Tauri OS Execution Risk):** Restricted Tauri desktop permissions in `desktop/src-tauri/capabilities/default.json` by replacing `shell:default` with `shell:allow-open` to prevent JS from executing arbitrary system commands.
- **GAP-7 (Prompt Injection via User Question):** Integrated `scan_for_injection` from the research module into `src/api/executions.py` at execution submission. Flags are logged for operator abuse monitoring without blocking valid use cases.
- **GAP-9 (Weak Default JWT Secret):** Added a startup configuration check in `src/main.py` lifespan that immediately refuses to start the server in production web mode if `jwt_secret_key` matches the default insecure placeholder.
- Added `clear_rate_limits` fixture to `tests/conftest.py` to prevent `429 Too Many Requests` masking test failures. Fixed blocked DNS in tests for `test_exe.py` by whitelisting localhost loopbacks in `socket.getaddrinfo`.
- Result: **333 passed, 41 warnings**; `ruff check` green. Security gaps addressed (except manual key rotation for GAP-8 and accepted risks).

## Model verifier script (2026-10-09)

- New: `scripts/verify_models.py` (async httpx, per enabled provider: list-endpoint existence check + one tiny probe per catalog model printing HTTP status and `x-ratelimit-*`/`retry-after` headers + plan/quota/not-found classification; Gemini via header-auth REST so headers are visible; keys revealed only at call site, output is names/counts/statuses, snippets masked). No `models.yaml` values invented — script only reports observed headers/errors for manual fill-in.
- `--save` flag writes a limit-headers-only markdown report to `.local/verify_report.md` (git-ignored; status + classification + `x-ratelimit-limit-*` only, no keys/remaining/reset); covered by 3 extra tests (limit filter, file content scan, `--save` CLI path).
- Result: **11 passed** in new file; `ruff check` + `format --check` green on both new files.
- Skipped (per DoD): live real-key run — user runs `python scripts/verify_models.py` locally; no live calls made here. Per-model limits schema change proposed separately, not applied.

## Per-model limits migration (2026-10-09, branch `feat/per-model-limits`, unmerged)

- `models.yaml` is now one shape only: per-model `limits: {rpm, rpd, tpm, context_tokens}` (int, `unlimited`, or null) + `scope: model|account`; provider-level `limits:` deleted (fails validation). Filled from the 2026-10-09 verify report + user dashboard values (groq 30/1000/8000/8000 per model; openrouter 20/50/unlimited/262144 account-shared; gemini-3.8-flash context 1M with rpm/rpd/tpm null pending the 60 s re-probe). Retired gemini 2.5 ids dropped; cerebras/mistral/nvidia/huggingface `enabled: false`.
- Code: `config.py` (`LimitValue`, `scope`, `limits_of`/`scope_of`/`model_spec`, `LimitsNotFilledError` + `validate_limits_filled` for enabled providers with models); `quota.py` keyed `(provider, key, bucket)` + per-model cooldowns, token-aware `acquire(provider, key_id, model_id, est_tokens)` with pre-send tpm rejection, 429 cools only the model; `router.py` loud per-provider skip + per-model usability + per-bucket snapshot/capacity; `openai_compat`/`gemini` pass model ids; `keys.py` status aggregates per-model remaining; `debate.py` per-recipient compression budget (min(context, 12000) − 4500 answer reserve − 500 overhead, floor 1200 chars, legacy caps + warning when unknown); `main.py` lifespan logs unfilled limits loudly without blocking boot (hard refusal deferred until post-reprobe fill).
- DB: `quota_usage` gains `model_id` PK column (`""` = account bucket); new Alembic revision `c41a9e2f7b3d` (explicit rebuild; upgrade preserves rows, downgrade keeps account rows). Existing dev DBs predate Alembic stamping — run `alembic stamp db244319c60b && alembic upgrade head` once (verified on a copy of assembly.db).
- Tests: `make_models_yaml()` builder in `tests/conftest.py` replaces all hand-written YAML; new `test_quota_migration.py` (chain + upgrade/downgrade + key-leak scan) and `test_debate_budget.py` (budget math, floor, legacy fallback, per-recipient round). Full suite **369 passed, 1 skipped**; `ruff check` + `format --check` clean on all touched lines (remaining hits in main.py/quota.py/conftest.py/keys.py/models.py are pre-existing debt on untouched lines).
- Post-migration live re-verify (2026-10-09, tiny probes): groq 3/3 HTTP 200, headers confirm `limit-requests=1000`/`limit-tokens=8000` (rpm=30 still needs the dashboard confirm noted in yaml); openrouter nemotron 200, gemma 429 upstream-transient (same as the earlier report), both still listed. Gemini re-probe (60 s timeout) left to the user before filling rpm/rpd/tpm.
- Follow-up round (same branch, unmerged): optional `tpd` limit (int/`unlimited`/absent = not enforced, never fails validation) tracked in daily token windows with pre-send rejection; capacity `KeyBudget` gains `tpm_limit`/`tpd_remaining` with `AVG_TOKENS_PER_CALL=2000` conversion (snapshot/mappings/planner wiring included; OpenRouter pair verified to count as ONE shared rpd pool); unknown limiter pairs still fail open but log one warning per pair. Preflight paste with live keys (groq + one shared openrouter bucket; gemini loud-skipped): tpm binds every groq bucket at all tiers (12/20/40/60 calls for 3/5/10/15 min), rpd=50 binds openrouter; all four tiers feasible (60/77/118/161 affordable).
## 2026-10-09 — feat/tier-scaling (1) per-stage token measurement
- Ran one real 5-min execution (question: "Is React better than Vue for a large cybersecurity platform?"). Per-call log (stage/role/provider/model/in/out/reasoning/total): planner gemini 325/73/0/398; solve solver 440/443/0/883 + critic (openrouter nemotron) 586/782/467/1368, researcher (groq gpt-oss-20b) failed all calls ("Tool choice is none, but model called a tool", 0 tokens); debate r2 solver 791/412/1203, r3 solver 791/379/1170 + critic 1047/1031/718/2078; synthesis 1043/1202/0/2245. Reasoning tokens reported by OpenRouter only (294-1196/critic call); Gemini 0. Second run hit Gemini 429 (free-tier 20 req/day) at synthesis, exposing a synthesizer fallback crash (`self.router` vs `self._router`) � fixed.
- Changed: `ProviderResponse.reasoning_tokens` + OpenAI/Gemini extractors; `AgentOutput` input/output/reasoning + `BaseAgent.run` propagation; debate compression preserves split; planner provenance on `PlanResult`; orchestrator `call_log` on `ExecutionResult` (per-call `Tokens` log lines); replay record round-trips reasoning; `MockProvider` reasoning param; new `scripts/measure_tokens.py`.
- Config: `src/core/config.py` per-stage avg/p90 totals with source run id `debug-5m-001` + date 2026-10-09 (planner 398/398, solve 1126/1368, debate 1484/2078, adversarial=debate, synthesis 2245/2245; failed 0-token calls excluded; adversarial n=0 so reuses debate).
- Tests: new `tests/test_token_measurement.py` (8 tests: propagation, extractors, compression, replay, call-log stages, config provenance, key-leak) + `tests/test_replay.py` allowed-keys update for `reasoning_tokens`. Suite: 359 passed, 1 skipped.

## 2026-10-09 � feat/tier-scaling (2-4) ceilings, preflight, --pin-team
- Why 10/15 stayed 4 agents/2 rounds: heuristic/LLM wish is 4 roles + 2 rounds for medium; `_desired_for_tier` clips wish to ceiling (`min(wish, MAX)`), so wish wins when below ceiling. Ceilings only bind oversized wishes.
- Changed: `TIER_MAX_ROUNDS` {3:1,5:3,10:5,15:8} + `BudgetController` max_debate_rounds {1,3,5,8} (ceilings; consensus FINALIZE still stops early, extra time funds DEBATE/ADVERSARIAL only when not converged). Updated `tests/test_capacity.py` (5-min full-team now (4,3,4)) + `tests/test_planner.py` (VALID_PLAN rounds 3 passes 5-min ceiling).
- Preflight: `PreflightResponse` gains `ceiling_agents/ceiling_rounds/expected_calls_median/expected_calls_worst` (median=planned rounds, worst=ceiling rounds via `cost_of_plan`). New table (workflow question, ample quota): 3m 3/1/2 ? 10/10; 5m 4/2/4 ? 18/22 (ceil 4/3); 10m 4/2/8 ? 22/34 (ceil 5/5); 15m 4/2/10 ? 24/48 (ceil 6/8).
- Bench: `bench/run_assembly.py --pin-team [--pin-families a,b] [--pin-max-wait-seconds 3600] [--pin-max-retries 3]` pins answering families (first run or explicit), sleeps until quota reset on outside-family answers instead of silently substituting, retries same question; each row records `families` (actually answered from call log), `answered/routed/pinned_families`, true `agent_count`, `pin_retries`. New `tests/test_bench_assembly.py` (6 offline helper tests).
- Result: full suite 359 passed, 1 skipped (live excluded). Branch `feat/tier-scaling` NOT merged � diff + preflight table shown for review.

## 2026-10-09 - Pre-merge fixes (no merge)
- Groq root cause (live probe): gpt-oss-20b emits native browser.search on research prompts; no tools defined -> Groq 400 tool_use_failed. Fixed via ToolCallError + family fallback + per-run CircuitBreaker (2 failures) with reroute, agent.status trip events, verification flags, reduced-research caveat. Tests: tests/test_circuit_breaker.py (17 tests incl. researcher-fails run).
- Sources: debug-5m-001 and measure-5m-20261009 both ran with needs_research=False, so zero sources retrieved, zero cited (measure run additionally failed at synthesis on Gemini 429).
- Gemini: thoughtsTokenCount/camelCase/dict parsing; est_tokens = max_tokens + 700 reserve; quota lease + 429 reporting added.
- Capacity: estimated_tokens_median/worst on TeamPlan + preflight (expected_tokens_median/worst); p90 worst-case gates tier fit vs token caps (50k/80k/150k/250k); planner tokens counted in total + budget (e2e updated).
- Chaos: 11-scenario sweep green (exit 0), incl. synthesizer fallback recovery and total-outage graceful failure.
- Bench: pin wait validated to 24h max; waits log "waiting for <provider> quota until <time>".
- Result: full suite 382 passed, 1 skipped (live excluded); ruff check clean on touched files (remaining hits pre-existing in untouched code); chaos exit 0. Branch NOT merged.

## 2026-10-09 - Planner OR, sources wording, cross-run memory (no merge)
- Planner._apply_research_or: LLM OR heuristic for needs_research (+researcher when room, reason noted). Tests: comparative / evidence-seeking / time-sensitive rescued, LLM-true untouched, plain question quiet (5 new tests).
- Composer: "No external sources were used." section + verification.external_sources_used whenever nothing cited.
- Breaker: CrossRunHealth (30-min TTL singleton) wired into fallback skip (warning log) + reroute (should_avoid); 4 new tests incl. TTL-expiry and skip-log; per-file autouse reset keeps suite hermetic.
- Groq docs: no disable option exists; probes proved prompt-dependent 400s (exact prompt 3/3 fail, short prompts pass) -> failover stands.
- Result: full suite 392 passed, 1 skipped; ruff clean on touched files; chaos still green from prior run (mock-only, unaffected). Branch NOT merged - merge/rebase plan below awaits OK.

## 2026-10-09 - Merge + rebase + live-run blocked (no merge of tier branch)
- Merged feat/per-model-limits into main (dry-run clean, committed 783e1f0): full suite on main 378 passed, 1 skipped.
- Committed tier work (b6349d5) and rebased onto main: 4 true conflicts (openai_compat acquire args, gemini lease structure, docs appends) resolved; capacity/orchestrator/planner/debate/executions/test_capacity auto-merged and audited. Rebase tooling stalled on continue with clean tree, finished via staged manual commit 360f936 (reflog-safe path, content verified).
- Rebase follow-ups: AVG_TOKENS_PER_CALL replaced by measured tpm_tokens_per_call() (max stage avg) with back-compat alias; per-model token tests rewritten to the divisor; single Gemini lease (model_name + reserve); DebateManager config wired; acquire-count tests pass model_name.
- alembic heads: exactly one (c41a9e2f7b3d). Copy of assembly.db (unstamped, no model_id) stamped db244319c60b + upgraded to head: model_id present, tables intact. Migration tests green (no new DB columns from tier work).
- quota_report baseline: no usage recorded today; window resets in ~11h. Live 5-min research run ABORTED pre-execution: 0 LLM calls made. Post-merge LimitsNotFilledError skips Gemini (null limits pending re-probe) and cerebras is catalog-disabled, leaving groq+openrouter = 2 < 3 minimum. No 429 involved. Awaiting user: fill Gemini limits (needs authorized re-probe), enable a third provider, or authorize another path. No exploratory probes run.
- Result: rebased suite 432 passed, 1 skipped; chaos 11/11 green; ruff clean on touched files (consensus/time_controller/workspace/quota hits pre-date both branches).

## Stateless web (2026-10-09, branch `feat/stateless-web`, merged)

- Deleted `src/api/auth.py`, `src/api/conversations.py`, `src/core/security.py`, `docker-compose.yml`, Supabase client, login/signup pages, sign-out button; all `user_id` ownership and Postgres/Supabase config removed (`User/Conversation/Message` tables gone; `is_postgres` compat-false; desktop/dev local SQLite only).
- New `POST /api/run` (SSE, 15s heartbeat, in-memory TTL registry + global cap, cancel on disconnect, usage counters; keys/questions/answers never stored, metadata-only logs) and `GET /api/catalog` (models.yaml only). Planner + limiter accept client `usage_snapshot` with max() semantics (memory day-counters in web, DB rows desktop-only). Orchestrator logs question length, never content.
- Frontend: `StorageService` (IndexedDB history/settings/usage + Export/Import JSON), passphrase-derived (PBKDF2+AES-GCM) opt-in key persistence, catalog-driven `ModelPicker` (Auto/pins/3-family warning), keys-manager from catalog, local-`id` history rendering, no Supabase deps. Playwright suite reworked to catalog/run-SSE mocks.
- Tests: 2 auth-only tests removed (`test_api_cancel_forbidden_for_other_user`, `test_rest_events_auth` → 404-only), helpers rewritten to no-auth dev harness; new `tests/test_stateless_web.py` (7: no-DB-file web boot, catalog, SSE e2e canary-free, 422 canary-free, snapshot-shrinks-plan, snapshot-max merge, cancel-settles-cancelled). Full suite **384 passed, 1 skipped**; `ruff` clean on new backend files; frontend `tsc --noEmit` + `vitest` (4) green.
- Docs: `docs/privacy.md` (exact server-sees/stores statement), `docs/decisions.md` entry. Config: `APP_MODE=web|desktop|dev`, CORS allow-list, run TTL/cap/heartbeat, per-IP limits; `render.yaml`/`Dockerfile` webless of DB/JWT/provider keys; `python-jose/passlib/bcrypt/psycopg2` dropped (+`platformdirs`).
- Skipped (per DoD): live real-key end-to-end run — no live keys in this environment (mock-router SSE e2e is the verification); Playwright browsers not launched here (spec file updated, CI runs it).
- Merged into `main` with `feat/tier-scaling` (merged first): kept tier-scaling's measured-token divisor, TeamPlan token estimates, round ceilings and preflight ceiling/expected fields; stateless usage_snapshot subtracts inside the same divisor math. Suite re-run on the merge (see below).

## 2026-10-09 — Key persistence + clear-all endpoint

- **Problem:** Keys were safe at rest (Windows Credential Manager / AES-GCM IndexedDB) but there was no single "clear all" operation — the backend only supported per-provider deletion (`DELETE /api/keys/{provider}`), and the frontend "Clear all keys" button only wiped the frontend vault, not the backend keyring.
- **Changes:**
  - `src/api/keys.py`: Added `DELETE /api/keys` endpoint that calls `store.clear()` to wipe every key from the keyring in one call (desktop mode only).
  - `frontend/src/lib/api-client.ts`: Added `ApiClient.clearAllKeys()` method.
  - `frontend/src/components/keys-manager.tsx`: `handleClearAll()` now calls both `globalVault.clearAll()` (frontend) and `ApiClient.clearAllKeys()` (backend keyring), with a toast confirming removal from "memory, disk, and system keyring."
  - `tests/test_key_handling.py`: Added `test_delete_all_keys_clears_keyring` (verifies all keys wiped, no key material in response) and `test_delete_all_keys_rejects_non_desktop` (400 in web mode).
- **Result:** 14 passed in key-handling + key-leak suites; `ruff check` clean on touched files; diff secret-free.
- **Key persistence model (unchanged, now fully documented):**
  - **Desktop:** Keys in Windows Credential Manager (OS-encrypted via DPAPI). Persist until user clicks "Clear all keys" or deletes via Windows Credential Manager.
  - **Frontend "remember" mode:** Keys in IndexedDB, AES-GCM encrypted with PBKDF2-derived key from user passphrase. Persist until "Clear all keys."
  - **Web mode:** Keys in-memory only, wiped after each run (ephemeral by design — most secure).
  - **Dev mode:** Keys in `.env` file (git-ignored). Persist until user removes from `.env`.

## 2026-10-10 — Privacy notice consent (FR-35)

- Backend: `ProviderSpec.privacy_note` optional + gemini note in `models.yaml` + `GET /api/catalog` exposes it (`src/api/catalog.py`).
- Frontend: `frontend/src/lib/privacy-notice.ts` single source (`PRIVACY_NOTICE_VERSION=1`); `PrivacyDialog` blocks first run in web/desktop; ack `{version, acknowledged_at}` via `StorageService`; Settings Privacy section with "Review again"; `docs/privacy.md` matches dialog exactly.
- Tests: `tests/test_privacy_notice.py` (3) + `frontend/src/lib/privacy-notice.test.ts` + `privacy-dialog.test.tsx` (9 vitest). New backend total 444 collected (441 before + 3).

## 2026-10-10 — Family-based gate and capacity UI (FR-10, D3)

- Backend: `DiversityGate` + `diversity_gate()` + `FAMILY_GATE_THRESHOLDS={ok:3,warn:2}` in `src/providers/router.py`; `_enforce_minimum` blocks only BLOCKED; gate in providers/status, preflight (`diversity` field), `/api/run` `run.started` SSE event; `cap_label_for_degraded` caps DEGRADED High→Moderate in `src/orchestration/orchestrator.py`.
- Frontend: `frontend/src/lib/diversity-gate.ts` mirror + chip in chat (`diversity-chip`), keys-manager (`readiness-chip`), model-picker (`picker-gate-chip`); confirm step at DEGRADED, Run disabled only at BLOCKED.
- Tests: `tests/test_diversity_gate.py` (12: 4-family OK, llama-only DEGRADED, 2-family WARN, BLOCKED, selection narrowing, cooldown/daily-quota/unfilled-limits exclusion, enforce-only-on-zero, status+preflight shape, label cap) + `frontend/src/lib/diversity-gate.test.ts` (6 chip states). Updated `test_key_handling.py::test_execution_with_request_keys_leaks_nothing` to the disabled-provider BLOCKED path (see decisions log for why). New backend total 456 collected (444 + 12).

## 2026-10-10 — PRD v1.1 status updates (docs only, no code)

- D8 recorded (no accounts/login/server storage); PRD bumped to v1.1 with status key + changelog; FR-41 Done-different, FR-14 Optional/Deferred, Insight Optional, FR-36 Could, theme Optional, FR-11 reworded; release tracks R1/R2 with verified pre-release items; demo fallback ladder; TECH_STACK/WORKFLOW aligned; `docs/prd-gap-report.md` created; `BUILD_PROMPTS.md` absent (intended markings logged in decisions); remaining contradictions listed in `docs/doc-drift.md`.

## 2026-10-10 — FR-30 key setup instructions (A)

- Backend: `ProviderSpec.key_steps/key_notes/sensitive_signup` optional (absent allowed); `models.yaml` generic 7-step `key_steps` per provider, `sensitive_signup: null` everywhere; `GET /api/catalog` exposes steps/notes/signup + `recommended_order` (capacity-sorted), `minimum_families=3`, fallback text.
- Frontend: `key-setup.ts` helpers + `KeysManager` Minimum-to-start banner, expandable stepper, copy-link, prefix hint (display-only, never blocks), inline Test result, Why line from roles/families; `api-client.ts` types extended.
- Tests: `tests/test_key_setup.py` (4: catalog steps+fallback, absent-fields schema, capacity order, no blocking format) + `key-setup.test.ts` (4) + `keys-manager.test.tsx` (banner/stepper/copy/hint/why/fallback). Backend total 460 collected (456 + 4).

## 2026-10-10 — FR-2 solver and critic always present (B)

- Backend: `core_roles.py` guarantee + `Planner` double-call + `plan.adjusted` event + preflight `final_roles` + single-family warning/confidence cap; `event-schema.json` regenerated (18 types).
- Tests: `tests/test_core_roles.py` (9: no-critic/no-solver adds, researcher-first drop, 3-min keeps trio, never-drop-last, preflight roles, single-family warning+cap, event contract, orchestrator emit). Updated `tests/test_events.py` (17→18 counts + `plan.adjusted` minimal payload, justified by new event) and fixed `test_events_canary_end_to_end` + `test_log_canary::test_canary_end_to_end_api_db_ws` to mock routing (pre-existing live-call slowness under TestClient portals caused `cancelled` instead of `completed`; now offline hermetic, still canary-scanned). Backend total 469 collected (460 + 9).

## 2026-10-10 — FR-5 stop stagnant debates (C)

- Backend: `stagnation.py` (RoundDelta, needs_debate, note) + `Settings` thresholds + `round.stagnated` event + orchestrator skip/stagnant/adversarial-once/force-finalize; `event-schema.json` regenerated (19 types).
- Tests: `tests/test_stagnation.py` (9: static/converging/thrashing/partial-failure, epsilon config, needs_debate, event contract, static ≤1 debate, stagnant→adversarial→finalize). Updated `tests/test_events.py` 18→19 (new event, justified). Backend total 478 collected (469 + 9).

## 2026-10-10 — Benchmark verification and guards (D)

- Schema: `bench/questions.jsonl` gains `verification` (40× `unverified`); reference answers untouched.
- Tool: `bench/verify_questions.py` (interactive, method/source required, atomic, `--status`/`--export/import-csv`).
- Runners/grader: `--verified-only` (default ON), `--questions-file`, `--limit`, `--seed`; rows carry `live` + `verification_status`; `run_single.py --models a,b,c` pilot (not run).
- Guards: `analyze.py` header + preview-only refusal + watermark; demo results moved to `bench/results/demo/` + README; docs scrubbed (demo-script, slides-outline → `[insert verified number]`).
- Schedule: `bench/plan_schedule.py` offline estimator.
- Tests: `tests/test_bench_verify.py` (9) + updated `tests/test_bench_grade.py` (verified fixtures + new args, justified by new schema). Backend total 487 collected (478 + 9). No live calls made; no benchmark run.
## 2026-10-10 — Key-safety isolated web run (names-only audit)

- Pre-flight: .env/.env.dev ignored + untracked + no history; allowlist = 5 provider keys + TAVILY (Settings/.env.example); leftovers none. Script `.local/preflight_names.py` (names/status/class only).
- Web isolation on :8001 with all 6 key names blanked: /health web-stateless healthy; /providers/status all unavailable, BLOCKED 0 families; Settings check tavily/gemini/groq all False. LLM path has no env fallback (PASS).
- Failure case POST /api/run provider_keys={}: SSE BLOCKED + failed_partial + run.finished failed, tokens 0, no provider call (planner routing error in logs). Suggest upfront 400 for empty-keys BLOCKED.
- Gap: no UI field for Tavily search key (keys-manager renders catalog LLM providers only); SearchEngine/TavilySearchProvider read settings.tavily_api_key server-side, so web isolation depends on blanking env. Recommend per-request search key or web-mode guard. Browser injection skipped (no keys handled).
- Scan `.local/key_scan.py`: clean (live-test artifacts + docs/live-test-report.md + generic prefixes); artifacts under .local/live-test/ deleted. Report: docs/live-test-report.md. No rotations required.

## 2026-10-10 — Prompt A implementation (web BYOK + search keys + BLOCKED 400 + salt)

- Backend: `ALLOW_SERVER_SEARCH_KEY`, `enforce_web_key_policy()` (startup fail on server provider keys in web; one warning for ignored Tavily), `resolve_tavily_key()`, per-run `SearchRouter` with keyless fallback + providers-used/empty events, `search_keys` on run/execution schemas, 400 `blocked_no_usable_keys`, per-mode quota salt (web per-process, desktop persisted 0o600, assertion in lifespan), `.dockerignore` (no `.env*` in image), `render.yaml` flag pinned false.
- Frontend: Tavily search-key card (keyless-sources note), `searchKeys` split out of vault keys in chat, server error detail surfaced on run failure. `tsc` clean; one pre-existing eslint error (chat set-state-in-effect, untouched); keys-manager snapshot test updated for the new card (justified).
- Tests: `tests/test_prompt_a.py` (16, all offline, canary). Backend subset re-run green; full offline suite pending as final gate.

## 2026-10-10 — Group 1 implementation (blockers)

- Shared context: `src/api/request_context.py` feeds both preflight and run; `POST /api/preflight` (RunRequest body, canary-clean 422); old executions preflight routes return 410; frontend sends keys/selection/usage.
- Navigation: landing CTAs → `<Link>`; `internal-links.test.ts` guard green.
- Vault: load-first mount, unlock prompt, explicit forget, memory-only banner; `key-vault.test.ts` 5/5; Playwright `keys-persist.spec.ts` passes (mocked, canary only).
- Tests: backend group-1 files green; full offline suite as final gate (see commit).

## 2026-10-10 — Gemini key-Test fix (valid key showed invalid)

- Branch `main` (no branch ops, no push). Live diag (2 Gemini calls, httpx, no SDK retry, script deleted): list 200 / 50 models / `gemini-3.8-flash` listed; generation timeout at 20 s → case = timeout, key valid, generation probe misreported it.
- Backend: Test now uses one auth-only list GET (15 s, no retries, never 500) classified by status only (200 valid, 400 API_KEY_INVALID/401/403 invalid, 429 rate-limited amber, 404/missing model = key-valid + alternatives, transport = unreachable); `clean_key()` trim at every key entry point; Gemini safe candidate/parts extraction + `TruncatedResponse` (never auth); legacy SDK has no thinking-budget param (verified, none set).
- Frontend: `testKey` maps valid/rate_limited/invalid/model_unavailable/unreachable (+ endpoint-429 → rate_limited, network failure → unreachable, never invalid); KeysManager shows message, copy-spaces hint on invalid, usable-model list on model_unavailable; readiness counts valid + rate_limited only.
- Tests: `tests/test_gemini_key_test.py` (12 mocked incl. trimming + canary) green; `api-client.test.ts` (8) green; vitest 9 files / 38 green; ruff check + format clean on touched files; canary/key-leak/key-setup/stateless (26) green. Full offline suite as final gate (see commit); one pre-existing failure (`test_run_with_failing_researcher_reports_reduced_research`) reproduces on clean HEAD, unrelated.

## 2026-10-11 — WORKFLOW Phase 0 grind (MVP real)

- Fixed pre-existing `test_run_with_failing_researcher_reports_reduced_research` (failed on clean HEAD): MockRouter has no `fallback_for`, so solve-phase single failure never tripped the breaker (threshold 2), and FR-5 now skips debate when no open disagreement — the old debate second-failure path is gone. Test-only fix: mock-b also `always_fail` researcher + one-step `fallback_for` mock-a → mock-b (same `mock-model` name) → 2 failures on (`mock-model`, `researcher`) trip in solve phase; `emit_breaker_trips()` emits the visible `agent.status` event. No product code touched; FR-5 savings + breaker threshold preserved. Verified: 1 passed single, 32 passed (breaker+stagnation+e2e), ruff clean.
- DB: AppData `assembly.db` predated Alembic (`no such column: quota_usage.model_id` in live logs) → `alembic stamp db244319c60b && alembic upgrade head` → head `c41a9e2f7b3d`; `quota_report.py` clean, no warnings.
- Smoke: `scripts/smoke.py` aborted on outdated provider-count gate (`need at least 3 live providers`; live = groq+openrouter = 2 providers, 4 families). Updated to family gate per D3 (`diversity_gate()`; BLOCKED aborts, WARN/DEGRADED notes and proceeds). ruff format clean. Live 3-min run re-launched (pending).
- Skipped (per DoD): full offline suite re-run pending live-run completion; no keys in diff/logs (names-only).

## 2026-10-11 — WORKFLOW Phase 1 grind (reliability + capacity)

- Live smoke `smoke-run` COMPLETED: 3-min tier in 35.7 s, 5 calls, 7231 tokens, consensus 65% Moderate, solver+researcher+critic across gpt-oss/qwen/nemotron (groq+openrouter, gate OK 4 families). Search fell back gracefully (wikipedia/arxiv failed, semantic-scholar 429, duckduckgo 0) with 0 searches; answer completed with synth-cited sources.
- N-03 fixed (`src/core/logging_config.py:64`): `/` dropped from `_LONG_TOKEN_RE`; canary green (14 passed, background 156 s); ruff check clean (format debt in `setup_logging` pre-existing, untouched).
- Stale `test_orchestrator_records_routing` fixed (test-only): single-family warning asserted present per FR-2/B; routing 13 passed.
- Batches green (mock, offline): routing+diversity+quota 48 passed; capacity+planner+consensus 80 passed; quota-migration+key-handling+preflight+core-roles 33 passed; breaker+stagnation+e2e 32 passed (earlier).
- Pending: `test_key_leak.py` background run; full offline suite as final Phase 1 gate; then Phase 2 benchmark.

## 2026-10-11 — WORKFLOW Phase 2 pilot (benchmark loop, 5 questions)

- `test_key_leak.py` green (1 passed, 0.53 s). Phase 1 targeted batches all green: routing+diversity+quota 48, capacity+planner+consensus 80, quota-migration+key-handling+preflight+core-roles 33, breaker+stagnation+e2e 32, canary 14. Full offline suite running in background as final gate.
- Pilot (user chose 5-question live over full-40): `bench/pilot_questions.jsonl` (ms-01, ms-02, logic-01, logic-02, code-01; all computationally verified, main file untouched). Bench env bug fixed (`.env.dev` loaded post-import → 0 live providers; `.local/run_with_env.py` wrapper pre-loads).
- `pilot-single` (groq gpt-oss-20b): 5/5 answered, 0 failed, 5 calls, 1702 tokens, 61.9 s; graded 5/5 mean 1.000, 0 judge calls.
- `pilot-vote` ABANDONED: OpenRouter gemma 429 every call, 60 s sleeps (N-02); vote is Optional per WORKFLOW.
- `pilot-assembly` launched (tier 3, `--pin-families gpt-oss,qwen`, groq-only, background). Grade + comparison pending its completion. Pilot results are UNVERIFIED loop-proofs, never slide numbers.

## 2026-10-12 — Four-task grind (pins, research, providers, consensus)

- Task 1 DONE: pin enforcement end-to-end (router `PinViolationError` + allowlist on route_team/route/route_for_planning; manager fallback walk; planner zero-call fallback; orchestrator threading + re-raise; bench up-front `validate_pins` + structural fast-abort; replay compat). 15 new tests; suites green: routing+bench-assembly 37, planner+agents 89, research+agents 51, consensus 23, stagnation+composer 32, provider/quota/diversity/capacity/key/verify/setup 97+38. Ruff check clean on touched files (remaining flags pre-existing on untouched lines). Live 1-question pin verification (`gpt-oss,qwen,nemotron`) running in background.
- Task 2 DONE: search router never-raises hardened + error detail in fallback warnings; synthesizer no-invent-citations rule (empty-search runs now honest via composer's existing "No external sources" path).
- Task 3 DONE: gemini re-probe (list 200/50 models; probe 503, no headers → nothing to fill); disable-tried-and-reverted (12 test failures + hidden setup/Test); gemini stays enabled with dated note; nvidia disabled (no key; zero test impact). Re-enable paths in `models.yaml`.
- Task 4 DONE: no scoring change (as-designed; reproduced 0.579 offline ≈ live); factor breakdown added to consensus logs; tuning deferred to `bench/analyze.py` with real numbers.
- Pending: background full suite (mock-only) + old pilot-assembly (pre-fix code) + pin verification run; grade pilot-assembly vs single when jobs land.

## 2026-10-12 — Verification: pins enforced live, search diagnosed

- `pilot-pins-verify` (code-01, tier 3, pins gpt-oss/qwen/nemotron): validation passed up front; team solver→gpt-oss, critic→nemotron, researcher→qwen, synthesizer→gpt-oss, planner→gpt-oss — zero outside-pin calls, no violation, no retries, 26.6 s, 5 calls. Graded correct (assembly 1/0/0). Task 1 proven live.
- Search diagnosis (Task 2): new error-detail logs identified every failure — Wikipedia HTTP 403 for any UA ("respect our robot policy", IP-level bot filtering; probed directly, must not be evaded), arXiv HTTP 500 transient (re-probe: 200, code fine), Semantic Scholar 429 rate limit, DuckDuckGo 0 results on long queries. All environmental; fallback chain is the correct handling. No provider code bug.
- Consensus factor log verified live: `factors=(agree=0.33 conf=0.92 evid=0.78 contra=0.00 stab=0.00)` → 63%, matching the offline reconstruction. Task 4 closed with data.

## 2026-10-12 — Pin audit close-out (prevention, not detection)

- Audited all 12 routing/selection paths: 4 bypasses found and closed (agent validation retry, synthesizer transport retry, planner validation retry, retry-agent rebuild). Critic selection, adversarial strikes, debate rounds use existing in-pin agents (no routing); `_last_resort`/prefer paths guarded; web model-pins orthogonal.
- Suites green: bench-assembly+routing+planner+agents 94, routing/bench/planner/agents/consensus/e2e/circuit/replay/preflight/roles/stagnation/composer 204. Ruff check clean on touched files (remaining flags pre-existing on untouched lines).
- 19 prevention-proof tests total: pins constrain teams/singles/planner/synthesizer/fallbacks with zero out-of-pin calls asserted (not just violation detection).
- Still uncommitted per instruction; Phase 3 not started.

## 2026-10-12 — Fresh-run verification + planner-timeout fix, then commit

- Fresh pinned run (`pilot-pins-fresh`, correct pins): zero pin violations; code-01 ok 63%, logic-01 ok 78% (with a real round-2 debate 58→78%); logic-02/ms-02/ms-01 FAILED on hung Groq planner calls (15 s bound, empty `TimeoutError`) — fixed via orchestrator TimeoutError→heuristic fallback (contract-restoring, cancellation-safe) + regression test.
- Structural run (`pilot-pins-structural`, bad pins): PinViolation in 1.5 s, 0 team calls, no retries — no-sleep abort proven.
- Full mock suite re-run as commit gate; results/CSV artifacts stay out of the commit.

## 2026-10-12 — Commit gate green, changes committed

- Full suite on final code: 458 + 86 = 544 passed, 1 skipped (live-excluded) across all 41 test files, in two foreground chunks (background runner kept dying with Shell.NotFoundError).
- Committed code+tests+docs+config only (results JSONLs/CSVs, `.local/` scratch stay out).

## 2026-10-12 — P0 key-persistence fix (refresh regression closed, uncommitted)

- Root cause (reproduced in real Chromium, mocked network, canary only): default Save never wrote to any persistent store (memory-only vault), so reload wiped everything; Remember+passphrase users still faced an unlock prompt plus a readiness gate on memory-only Test statuses. No stray deleter or key mismatch found.
- Fix: canonical persistent `KeyVault` (IndexedDB `assembly_keys_v1` + localStorage fallback, serialized read-modify-write, honest `KeyStorageError`); Remember/passphrase gate removed from save path with one-time legacy migration; presence-based readiness (invalid excluded) so Settings/chat/picker agree post-refresh; per-provider Remove; chat focus re-read.
- Gates: `tsc` clean, vitest 48/48, `next build` green, eslint clean on touched lines (1 pre-existing untouched), Playwright 12/12 (9 new refresh scenarios + 3 e2e). Backend suite running as final gate. Diff canary-only, no secrets. Not committed per task instruction (commit only after regression reproduced as fixed + gates green — backend pending).

## 2026-10-12 — P0 blank-run failure states (diagnostics + guard, uncommitted)

- Trace: preflight passes with persisted keys, then the orchestrator settles failed (raise pre/post agents, or failed `ExecutionResult`); three silent layers turned that into a blank "forming team" page (unknown-status resolve, unconditional save+navigate, bare failed event). KeyVault proven unrelated, untouched.
- Fix: backend stage/code/class/message diagnostics (secret-free logs + SSE); `startRunStream` rejects missing-terminal streams and returns failure diagnostics; `run-outcome.ts` guard blocks navigation for any non-completed/empty-answer run (history still saved with true failed status, no fabricated fields); aborts save `cancelled`, broken streams `failed` under the original ID; executions view shows `run-failed-banner` + failed-team/consensus states for `failed`/`unknown`.
- Gates: `tsc` clean, vitest 55/55 (12 files: +4 stream-terminal, +3 outcome-guard), `next build` green, touched-line eslint clean (repo-wide flags pre-existing), new backend diagnostics 5/5 + stateless/key-leak/log-canary/orchestrator-e2e 32/32; full backend suite + Playwright re-run per task 8 (Playwright 12/12 green). Diff canary-only, no secrets.

## 2026-10-12 — P0 follow-up: init-gap, canary, CI paths + live dummy-key proof

- Review found three gaps in the committed failure-state fix: (1) `_execute_run` initialized limiter/router/`Orchestrator()` before the `try`, so an init raise skipped diagnostics and could leave the SSE on heartbeats with no `run.finished`; (2) the new backend test's `sk-` canary tripped Gitleaks; (3) `ci.yml` still pointed at `./frontend/app` (repo root is `frontend/`).
- Fix: init moved inside the protected block with tracked stages (`run_init`/`limiter_init`/`router_init`/`orchestrator_init`/`orchestrator_start`) and null-guarded limiter cleanup; canary replaced with `TEST-ONLY-CANARY-NOT-A-REAL-CREDENTIAL` (assertions unchanged, no scanner config touched); CI working dir, lockfile, and report paths corrected to `frontend/` (YAML validated).
- Gates: diagnostics file 7/7 (new router-init + orchestrator-init tests), `ruff check` clean, `tsc` clean, vitest 55/55. Live proof (`scripts/live_dummy_check.py`, disposable groq+openrouter dummy keys, 3-min tier): preflight 200 feasible, SSE terminated in `run.finished` status `failed`, stage `synthesizing`, code `execution_failed`, actionable message — a clear failure, never a forming-team hang. Full backend suite re-run pending as final gate.

## 2026-10-12 — Frontend audit gate: katex fixed compatibly, braces unpatched upstream

- CI `npm audit --audit-level=high` reported 13 vulns (9 high). Triage against the advisory DB: all 9 highs are one advisory, GHSA-vfj7-8cjw-p6xm / CVE-2026-93687 (braces stack-exhaustion, CVSS 8.7) — affected `<= 3.0.3`, **patched: none**. Installed braces 3.0.3 is the latest release and still flagged, so no version bump can clear it; npm's only remediation is breaking majors (`shadcn@1.0.0`, eslint-config-next downgrade to 14.x, rehype-katex downgrade to 1.x) — rejected, never `--force`. The chain enters only via build/dev tooling (eslint plugin, shadcn CLI/CSS) and is unreachable from production request handling.
- Compatible fix applied: katex CVE-2026-103923 (Low, patched 0.18.2) had nested 0.16.47 copies under remark-math/rehype-katex while top-level was already fixed 0.19.0 — added `"overrides": { "katex": "$katex" }`. Correction (2026-10-12): this is NOT semver-safe — consumers declare `^0.16.0`, which does not include 0.19.0, so the override forces a version outside their declared range. Kept because build/tests pass plus the new `math-pipeline.test.tsx` renders inline+block math through the real pipeline. Result: 13 → 9 vulns, all 9 residual traceable to the single unpatched braces advisory; `tsc` clean, vitest 55/55, `next build` green on all routes.
- Gate decision held for the final round: options are (a) leave the hard audit blocker red on an unfixable upstream advisory, or (b) mirror the backend's existing `pip-audit || echo …review later` pattern so the step still runs and reports without blocking lint/tsc/Playwright. No scanner rule disabled either way; Gitleaks stays fully enforcing.

## 2026-10-12 — Frontend audit gate: allowlisted braces, CI green on new vulns only

- Ran `npm audit --audit-level=high` in `frontend/`: 9 high, all GHSA-vfj7-8cjw-p6xm (braces <=3.0.3, patched None). katex from the earlier 13-vuln report is already clean (0.19.0 deduped). `npm audit fix` is a no-op; `--force` rejected (breaking shadcn 4.x to 1.0.0 downgrade).
- Implemented the allowlist gate per user choice: `frontend/scripts/audit-high.mjs` (parses `npm audit --json`, resolves transitive `via` chains, passes only when all high/critical map to the allowlist), `audit:high` npm script, CI step now `npm run audit:high`. No versions changed.
- Verified: `npm run audit:high` PASS (9 allowlisted, 0 blocking); synthetic unknown GHSA blocks; `npx tsc --noEmit` clean; `npm run lint` shows only pre-existing chat/settings set-state-in-effect errors, none in the new script. No secrets in diff. No live-key e2e (frontend CI-only change).

## 2026-10-12 — Audit gate hardening + katex pipeline proof (review follow-up)

- Hardened `frontend/scripts/audit-high.mjs`: `validateReport()` fails closed on `error` payloads, non-object reports, and missing/non-object `vulnerabilities`; advisory matching is now `ghsa@package` (same GHSA on another package blocks); exception carries `owner: assembly-maintainers`, `reviewBy: 2027-01-12`, printed on every run.
- Regression tests: `frontend/scripts/audit-high.test.mjs` (`npm run audit:test`, node:test 8/8 pass — service-error/malformed rejection, empty-via blocking, braces chain, synthetic new-GHSA block, package enforcement, metadata); `frontend/src/components/math-pipeline.test.tsx` (vitest 1/1 — inline `$…$` + block `$$…$$` through the real ReactMarkdown/remark-math/rehype-katex stack assert `.katex` x2, `.katex-display`, no `.katex-error`). This keeps the katex 0.19.0 override despite it forcing a version outside consumers' declared `^0.16.0` (wording corrected above — not semver-safe).
- Verified: `npm run audit:high` PASS (9 allowlisted, header shows owner/review date); `npm run audit:test` 8/8; math test 1/1; `npx tsc --noEmit` clean. `npm run lint` still fails repo-wide on pre-existing chat/settings errors — explicitly NOT claimed as passing; separate cleanup task. Backend suites untouched by this frontend-only change; blank-run fix stays provisional pending those suites per review.


## 2026-10-12 — Remove PostgreSQL from active setup

- Removed the PostgreSQL service/matrix and `psycopg2-binary` install from backend CI; CI now validates migrations and tests against SQLite only.
- Removed the unused `Settings.is_postgres` compatibility flag. Kept SQLAlchemy, Alembic, SQLite configuration/models, and desktop/dev local persistence for the future Windows app.
- Rewrote deployment instructions for stateless web hosting, corrected the active stack/security storage descriptions, and removed the obsolete production PostgreSQL checklist item.
- Validation status: implementation committed; CI is the next verification gate. No PostgreSQL runtime support is retained or claimed.

## 2026-10-12 — Mobile polish + contrast + SEO static fixes

- Fixed horizontal overflow: body overflow-x clip, orbit radius 140px to 104px on <=480px, pre/code overflow-x auto, executions ID break-all, min-w-0 flex fixes.
- Light-mode contrast to WCAG AA: brand/primary to #8a5e00, accent text #7a5200, success #146c46, warning #8a4e00, muted #5f5a54 (dark already passed).
- Mobile menu: aria labels/expanded, Escape close, dialog semantics, 44px targets; history delete visible on touch with aria-label; designed history empty state.
- Forms: chat label + alert-style errors, 44px time buttons; keys inputs labelled with alert errors; model-picker labels + 44px controls.
- Console: gated layout-wrapper/use-execution/error-boundary logs to non-prod. Source maps already off (default).
- Footer: fixed portfolio typo, added clickable mailto anubhab7105@gmail.com. robots/sitemap force-static (build green). Removed unused zod + template SVGs.
- Verified: tsc clean, eslint clean on touched files, next build green, robots/sitemap served, Playwright overflow=0 at 360/390/768/1280, vitest 56 passed.

## 2026-10-12 — Copy rewrite for one buyer (technical skeptic with free keys)

- Landing: new H1 "Stop trusting one model with hard questions.", support line with 3+ families and 3 to 15 minutes, primary CTA "Run my first question", objection line under CTA (no account, keys in browser, first progress in seconds). Removed "measurably better" (unsupported) and fabricated orbit labels (ChatGPT/Claude/Grok/Midjourney/DALL-E/Copilot/Cohere/Perplexity replaced with real families Gemini/GPT-OSS/Qwen/Gemma/Nemotron plus real roles Solver/Critic/Researcher/Verifier/Synthesizer).
- Steps rewritten benefit first; section heads specific ("One answer you can check", "Worried? Read this"). FAQ rewritten to buyer objections with matching FAQPage schema.
- Chat: H1 "Ask one hard question", CTA "Run my question", placeholder rewritten. Settings H1 "Add your free keys". 404, error boundary, empty states, key toasts, run banners rewritten. All user-facing em dashes removed. Meta titles/descriptions rewritten per page.
- Verified: tsc clean, eslint clean on touched files, next build green, targeted vitest 24 passed (key-setup test made case-insensitive).

## 2026-10-12 — Legal audit + draft pages (NOT legal advice, lawyer review required)

- Added /privacy, /terms, /cookies, /refunds pages (server components, footer-linked, sitemap-listed), each with a visible draft notice. Content based on actual behavior: no accounts, no cookies/analytics, browser-only keys/history, transient server runs, provider data sharing, India + GDPR rights, no payments.
- Added informational cookie banner (nothing to block: zero cookies set) with localStorage dismissal. Privacy dialog now requires a consent checkbox before I understand. Skip-to-content link + global focus-visible style.
- Verified: tsc clean, eslint clean, next build green (12 routes), privacy/key-setup tests pass.


## 2026-10-13 — Frontend navigation and compact composer UX

- Context: The sidebar's New Investigation action routed to `/` (the marketing landing page) rather than the question composer. The chat screen also displayed the full model picker and long example cards on every visit, making the primary task feel crowded.
- Decision: Route New Investigation to `/chat` and send users to the composer if they delete the currently open history item. Move model/role configuration into an accessible dialog; use compact prompt suggestions and shorter copy in the composer while retaining key readiness, family-gate, and API connection warnings. Separate the history delete button from its link to avoid nested interactive controls. Add a Playwright regression for navigation and align run-flow selectors with the compact composer.
- Verification status: Regression coverage updated. Browser suite/build have not yet been run from this connector session; do not treat the UI change as live-browser verified until CI passes.


## 2026-10-13 — Follow-up: privacy test flow and hydration mismatch

- Context: Post-merge Playwright run had 10/13 passing. Two tests clicked the privacy acknowledgement while its required consent checkbox was unchecked; another expected the model picker to be in the chat page after it had moved to advanced settings. The same run logged a cookie-banner server/client hydration mismatch and Next.js workspace-root / scroll-behavior warnings.
- Decision: Update those tests to check consent and open advanced model settings before reading the picker. Make the cookie banner render hidden on both server and first client render, then read localStorage in an effect. Set the Turbopack root to the frontend working directory and add `data-scroll-behavior="smooth"` to the root HTML.
- Verification status: Fixes are committed on a follow-up branch. Await CI on that branch before claiming the end-to-end suite passes.


## 2026-10-13 — Cookie banner hydration fix refined to satisfy lint

- Context: The first hydration fix moved the localStorage read into an effect, but CI lint rejected synchronous state updates inside effects.
- Decision: Use `useSyncExternalStore` with a stable server snapshot and browser snapshot for the cookie-banner preference. Dismissal is broadcast to same-tab subscribers and stored in localStorage when available.
- Verification status: Awaiting the latest PR CI run; do not claim lint or browser tests are green until confirmed.


## 2026-10-14 — Issue #17: consistent unknown-limit readiness

- Found that `ModelRouter` already skips providers with null required limits, but `GET /api/catalog` still listed those families as available and the Settings UI counted a saved key as ready. Startup logged the validation error without stopping the API.
- Added a shared provider-limit issue helper, catalog readiness fields, filtered capacity recommendation/family output, explicit Settings warnings, and a clearer startup diagnostic. Gemini remains enabled for key validation, but unavailable for runs until RPM/RPD/TPM are verified; no quotas were guessed.
- Verification: pending CI on the issue branch. Google AI Studio's model/project usage tier is account-specific; public docs do not establish these values for this project.


## 2026-10-14 — Issue #17 CI follow-up

- The first full CI run passed frontend lint, TypeScript, npm audit, and Gitleaks. Playwright exposed stale cases in `frontend/tests/keys-persist.spec.ts` whose mocked catalog did not include the new `limits_ready`/limits-issue contract and still counted the Gemini family as run-ready. Updated the fixture to mark Gemini enabled but not routable, and changed checks to assert the explicit warning while other configured families remain ready.
- Backend pytest was still running at the time of this entry; rerun CI and record the final result before merge.
