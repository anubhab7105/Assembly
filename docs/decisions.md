# Decisions Log

Append-only log of significant technical and product decisions.

## Format

```markdown
## YYYY-MM-DD — Short title

- Context: ...
- Decision: ...
- Consequences: ...
```

## 2026-10-08 — Test harness: mock routing by prompt markers, lint scoped to new files

- Context: New `MockProvider` must serve concurrent agents deterministically; `ruff check src tests` reports 277 pre-existing violations (UP/I001/BLE001) across untouched `src/` files.
- Decision: (1) Mock scripts selected by matching role markers in request text (planner/synthesizer/critic/researcher/solver), with `fail_next`/`always_fail` fault injection and `from_fixture` JSON loading. (2) `make lint` gates only `src/providers/mock_provider.py` + `tests/`; full-`src/` ruff cleanup is a separate task. (3) Autouse socket guard blocks non-loopback `connect` (Windows asyncio needs 127.0.0.1 socketpair; respx intercepts HTTP without sockets).
- Consequences: `pytest` provably makes zero external network calls; pre-existing lint debt stays visible and untouched.

## 2026-10-08 — Smoke run: live-verified model IDs, 120 s Gemini bound

- Context: First real-key run failed 100% of calls — every hard-coded model ID was retired (Gemini 2.x, Groq Llama-*, old OpenRouter slugs). Gemini 2.5-flash is also gated for new API keys; only 3.x works there.
- Decision: Refresh IDs from live provider catalogs (`scripts/list_models.py`, names-only output): Gemini → `gemini-3.8-flash`, Groq → `openai/gpt-oss-20b` / `openai/gpt-oss-120b`, Cerebras → `gpt-oss-120b` / `qwen-3.8-27b`, OpenRouter free → `google/gemma-4-26b-a4b-it:free` (+ nemotron/inkling fallbacks). Bound the legacy Gemini SDK call with `asyncio.wait_for(120 s)` since it can hang indefinitely and the SDK offers no timeout.
- Consequences: Complete 3-min runs work (6 calls, ~5k tokens, <11 s when Gemini cooperates). Long-term fix is still `models.yaml` + per-call timeouts everywhere (audit #1); Groq no longer serves any Llama model, which weakens the family-diversity story until the router is family-aware.

## 2026-10-08 — Provider layer is config-driven (models.yaml + registry)

- Context: Every model id lived in 3+ places (router tables, provider lists, settings defaults); all rotted simultaneously. Four `openai`-SDK provider modules duplicated the same 60 lines.
- Decision: (1) `models.yaml` is the single catalog (TECH_STACK 3.5 schema + `enabled`/`headers`/`timeout_seconds`; limits/context are null placeholders with dashboard pointers). (2) One `OpenAICompatibleProvider` (httpx) for Groq/Cerebras/OpenRouter/Mistral/NVIDIA; retry only 429 (+Retry-After, capped)/502-504/timeouts/connect errors, never 401/403/400/malformed. (3) `get_provider(provider_id, api_key)` registry; Gemini kept native but raises the same `RateLimited/AuthError/ProviderDown/BadResponse` via shared `classify_exception`. (4) HuggingFace `enabled: false` (registry refuses it); dead `ExperientialProvider` + per-provider modules deleted; `openai`+`groq` SDK deps removed (verified zero imports). (5) `Settings.*_default_model` fields removed — defaults come from yaml. (6) `make lint` now gates `src/providers tests scripts` (also micro-cleaned `base.py` annotations).
- Consequences: Switching a model id = editing models.yaml only (proven by test + grep: only the family-vocabulary enum remains in code). Router resolves (provider, model, family) from catalog order. Pre-existing violations outside providers/tests/scripts remain untouched.

## 2026-10-08 — BYOK key handling (TECH_STACK s5): stores, SecretStr, endpoints

- Context: Keys lived as plain strings from settings `.env` only; no per-request path, no key test, no status view, no mode switch.
- Decision: (1) `src/core/keystore.py` with `RequestKeyStore` (web, per-run memory, wiped in orchestrator success+failure paths), `KeyringKeyStore` (desktop, lazy `keyring` import, catalog enumeration), `EnvKeyStore` (dev, refuses to construct when `app_env=production`); `get_keystore()` on new `APP_MODE=dev|web|desktop` (Literal-validated). (2) All key fields are `SecretStr`; added `reveal()` used only at provider/SDK/JWT call sites (fixed a real bug found en route: f-string of a SecretStr sends literal `**********` as the bearer token). (3) `provider_keys` request field flows to `Orchestrator.execute(provider_keys=...)` via an isolated `ModelRouter(keys=...)`; never mapped onto the `Execution` record. (4) `POST /api/keys/test` (SecretStr body, tiny call, `{valid, rate_limited, error_code}`, 404 on unknown provider) and `GET /api/providers/status` (names/families + rough 0.7-margin capacity from yaml limits) in new `src/api/keys.py`, registered in `main.py`. Removed `Settings.*_default_model` leftovers already gone; added `keyring` dep (Windows needs pywin32 alongside).
- Consequences: `make lint` gate extended to owned files (`src/providers`, keystore/config/keys, tests, scripts); pre-existing B008/BLE001/S110 in auth/conversations/executions/orchestrator left untouched. Live smoke after the refactor hit Gemini 429 quota-exhausted and failed cleanly — confirming free-tier 429 handling (cooldown/retry) is the next must-fix, already audit #5.
