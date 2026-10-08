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
