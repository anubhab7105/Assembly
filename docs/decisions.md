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
