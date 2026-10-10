# Assembly — Tech Stack

*v1.1 · October 10, 2026 · Companion to the PRD v1.1 · Goal: hackathon demo first, free-tier only, BYOK*

> **Verify before you rely on it.** Free-tier limits and model names change often. The numbers below come from third-party summaries read in October 2026. Open each provider's dashboard and confirm your own limits before the demo. Keep every limit and model name in a config file (`models.yaml`), never hard-coded.

---

## 1. Decisions at a glance

| Layer | Choice | Why |
|---|---|---|
| AI access | **Provider APIs with the user's own free keys (BYOK)** | Free quotas are per account and small; one shared key would run dry after a few executions |
| Models | 4–6 **model families** from free tiers (section 3) | Independence needs different families, not just different providers |
| Orchestration | Custom Python (already built in Phase 1) | It is your differentiator; do not replace it with a framework |
| Backend | FastAPI + asyncio + httpx + Pydantic | Already built; async fits parallel agent calls and WebSockets |
| Realtime | WebSocket (already built); SSE as simple fallback | Live progress, consensus meter and countdown |
| Database | SQLite for desktop only; no database for web (D8) | Desktop history is local; the web backend is stateless and stores nothing |
| Event bus | In-memory asyncio pub/sub (already built) | Redis adds nothing until you run several workers |
| Frontend | Next.js + TypeScript + Tailwind CSS | Planned in your PRD; one UI for web and desktop |
| Windows app | **Tauri 2 shell + bundled Python backend (sidecar)**; Electron as fallback | Small installer, keys stay on the machine (section 4) |
| Key storage | Windows Credential Manager via the `keyring` library (desktop); browser memory + opt-in encrypted IndexedDB (web) | OS-encrypted on desktop; in-memory by default on web |
| Search | A free search source with fallback (section 6) | Research is a core feature |
| Auth | None — no accounts, no login in any mode (D8). The desktop shell uses a per-launch local token (`X-Assembly-Token`, `src/main.py`) only to stop other local programs calling the backend. | Nothing to log into; nothing to leak |
| Testing | pytest, a log-scan test for keys, a benchmark harness | Proves both safety and your hypothesis |

---

## 2. "Should it be API keys, or something else?"

**API keys are the right approach.** The alternatives, and why they lose:

| Option | Verdict |
|---|---|
| Official provider APIs with free tiers | **Use this.** Stable, documented, structured output, legal |
| Local models (Ollama, LM Studio) | **Good optional add-on** for the Windows app: no limits, full privacy. Needs a decent GPU or lots of RAM, and small local models are weaker. Add as a provider later |
| Automating chat websites (ChatGPT, Gemini, Grok web UIs) | **Do not.** Breaks provider terms, breaks whenever the page changes, and gets accounts banned |
| Paid APIs | Out of scope for this project |
| One shared key held by you | Fails at the second or third user |

**Why Grok is not in the core list:** the xAI API has no permanent free tier. New accounts get promotional credits (reported around $25), and consumer grok.com plans do not include API credits. Keep a Grok provider class as an optional extra for users who have credits.

---

## 3. Free model lineup

### 3.1 Providers and what each is good for

| Provider | Typical free models (as listed Mar–Oct 2026) | Strength for Assembly | Key page |
|---|---|---|---|
| **Google AI Studio (Gemini)** | Gemini Flash and Flash-Lite family. Pro models are no longer free (since April 2026) | Long context, strong general reasoning for a free model; good Researcher and Synthesizer | aistudio.google.com/apikey |
| **Groq** | Llama 3.3 70B, Llama 4 Scout, Kimi K2, GPT-OSS and others. Reported free tier: no card, about 30 requests/min and 14,400/day | Very fast; high volume for debate rounds; Critic and verifier | console.groq.com/keys |
| **Cerebras** | Llama 3.3 70B, Qwen3 235B, GPT-OSS-120B and others. Very high speed; limits less clearly published | Fast parallel exploration; extra Solver | cloud.cerebras.ai |
| **OpenRouter** | 20+ free-tagged models, including DeepSeek R1, GPT-OSS-120B, Llama variants. One key for many models, with failover | Reasoning diversity (DeepSeek R1) and a fallback path | openrouter.ai/keys |
| **Mistral (La Plateforme)** | Mistral Small/Large-class models; phone verification; about 1 request/second | Different family for independence | console.mistral.ai |
| **NVIDIA NIM** (optional) | Llama, Qwen, Mistral and others via a developer program | Extra capacity | build.nvidia.com |
| **Hugging Face** (low priority) | Reported free credit is tiny (about $0.10/month) | Not enough for multi-agent runs; keep as optional | huggingface.co/settings/tokens |
| **xAI Grok** (optional) | Promotional credits only | Only if the user already has credits | console.x.ai |

### 3.2 Independence rule

Count **families**, not providers. Groq, Cerebras and OpenRouter can all serve Llama or GPT-OSS. Two agents on the same family can make the same mistake for the same reason, which defeats independent first-pass reasoning.

| Family | Example sources |
|---|---|
| Gemini | Google AI Studio |
| Llama | Groq, Cerebras, OpenRouter, NVIDIA |
| Qwen | Cerebras, OpenRouter |
| GPT-OSS | Groq, Cerebras, OpenRouter |
| DeepSeek | OpenRouter |
| Mistral | Mistral |
| Kimi | Groq |

The router must pick at least **3 distinct families** when available. With only two, run but show a warning.

### 3.3 Suggested role mapping (starting point; confirm with your benchmark)

| Role | First choice | Fallback |
|---|---|---|
| Planner (classify and plan) | Fast, cheap model: Llama on Groq | Gemini Flash-Lite |
| Solver A | Gemini Flash | Mistral |
| Solver B | Llama 3.3 70B (Groq or Cerebras) | Llama via OpenRouter |
| Solver C | Qwen3 or GPT-OSS-120B (Cerebras or Groq) | DeepSeek R1 via OpenRouter |
| Researcher | Gemini Flash (long context for sources) | GPT-OSS-120B |
| Critic / adversarial verifier | A family **different from the one being criticized** | Any other family |
| Synthesizer | Strongest available free model (usually Gemini Flash or a 120B+ model) | Next strongest |

### 3.4 Minimum and recommended key sets

| Set | Keys | What it supports |
|---|---|---|
| Minimum (demo works) | Gemini + Groq + one of Cerebras/OpenRouter | 3 families, 3–5 minute runs |
| Recommended | Gemini + Groq + Cerebras + OpenRouter + Mistral | 5–6 families, 10–15 minute runs, resilient to a rate limit |

### 3.5 `models.yaml` (all limits and names live here)

```yaml
providers:
  groq:
    base: openai-compatible
    url: https://api.groq.com/openai/v1
    enabled: true
    models:
      - id: <gpt-oss id>
        family: gpt-oss
        roles: [critic, solver]
        scope: model   # or `account` when the cap is shared across models
        limits:
          rpm: <fill>             # or `unlimited` / null (unknown)
          rpd: <fill>             # null on an enabled model fails startup
          tpm: <fill>
          context_tokens: <fill>  # source + checked-date comment on each
```

One shape only: limits live under each model (`rpm/rpd/tpm/context_tokens`,
each an int, `unlimited`, or null) with a `scope` (`model` = per key+model
bucket, `account` = shared bucket). There is no provider-level `limits:`.
Null on an enabled provider fails startup loudly (`validate_limits_filled`);
unfilled providers stay `enabled: false`.

Most providers above expose an OpenAI-compatible endpoint, so **one generic provider class plus config** covers most of them. Gemini keeps its own class.

---

## 4. Windows app: recommendation

**Build the website UI first, then wrap it in a desktop shell. Use Tauri 2 with the Python backend bundled as a sidecar. If Rust setup slows you down, use Electron instead.**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Tauri 2 + Python sidecar** | Small installer; strong security model; keys stay local; reuses the Next.js UI | Needs the Rust toolchain; Next.js must be built as a static export; bundling Python adds size | **Recommended** |
| Electron + Python subprocess | All JavaScript tooling; easiest if Rust feels risky; huge community | Larger installer (100 MB+); more memory | **Fallback** |
| Native Python UI (PyQt, Tkinter) | One language | You build the UI twice (web and desktop); weaker visuals for a demo | Not recommended |
| PWA only | Zero packaging | Not a real Windows app; cannot bundle the backend | Not enough for the stated goal |

How the desktop version works:

```
Tauri window (static Next.js UI)
        │  http://127.0.0.1:<random port>  +  WebSocket
        ▼
Bundled FastAPI backend (PyInstaller exe, started by Tauri)
        │
        ├── SQLite file in the user's app-data folder
        ├── Keys read from Windows Credential Manager (keyring)
        └── HTTPS calls straight to Gemini / Groq / Cerebras / OpenRouter / Mistral
```

Notes: bind the backend to `127.0.0.1` only; use a random port and a per-launch token so other local programs cannot call it; WebView2 ships with Windows 11 and the installer can bootstrap it on Windows 10.

**Hackathon shortcut:** for the first demo you can start the backend with a script and open the Tauri or even a browser window. Package the installer in the last phase.

---

## 5. Key security design (BYOK)

You are a security student; make this a visible feature.

| Rule | Implementation |
|---|---|
| Desktop keys never leave the machine except to the provider | Orchestrator runs locally; keys read from Credential Manager just before each call |
| No plain-text key files | Use `keyring` (Windows Credential Manager); never `.env` for user keys |
| Website keys are not stored | Held in browser memory (session); sent with each execution request over HTTPS; backend keeps them only in memory for that run and drops them at the end |
| Never in logs, errors or database | A logging filter masks anything that looks like a key; stored execution records contain provider and model names only |
| Prove it | A pytest that runs a full execution with a fake key string and scans logs, DB and responses for that string |
| Do not leak through URLs | Keys only in headers or body |
| Untrusted web content | Search results are passed to agents as quoted data with an instruction that they are not commands (prompt-injection defense) |
| Provider privacy | Show a one-line notice per provider: free tiers may use inputs for improvement (reported for Gemini free tier); do not send sensitive data |
| Key test | "Test key" button makes one tiny call and reports valid, invalid or rate-limited |

---

## 6. Web search (free options)

| Source | Notes |
|---|---|
| Tavily (already integrated) | Has a free monthly allowance; check the current size; keep the graceful fallback you already built |
| Wikipedia / Wikidata API | Free, no key; good for factual and general questions |
| arXiv and Semantic Scholar APIs | Free; ideal for research questions and student users |
| DuckDuckGo via an unofficial library | No key, but unofficial and can break; use only as a fallback |
| Brave, Serper and similar | Check whether a free tier still exists before depending on it |

Design: a `SearchProvider` interface like the model providers, a search budget per execution, and caching of results inside a run so agents do not repeat the same query.

---

## 7. Hosting the website (secondary for the demo)

| Part | Where | Caveat |
|---|---|---|
| Frontend | Vercel (you already use it) | Static or SSR is fine |
| Backend (long-running, WebSocket) | A free long-running host (for example Render, Fly.io, Railway, Hugging Face Spaces, or an always-free cloud VM) | Free tiers often **sleep** when idle and may limit long requests. Vercel serverless functions are the wrong place for 15-minute executions |
| Database | None — the backend is stateless (D8) | No database to run, nothing to leak; history lives in the browser |
| Auth | None (D8) | No login of any kind |

Rule for the demo: **run it locally**. A sleeping free server is the most common cause of failed live demos.

---

## 8. Changes to your existing Phase 1 code

| File (from your progress log) | Change |
|---|---|
| `providers/router.py` | Enforce **3 distinct model families**, not 3 providers; read quotas; mark a key cooling down after a 429 |
| `providers/*` | Merge Groq, Cerebras, OpenRouter, Mistral into one OpenAI-compatible provider class driven by `models.yaml`; keep Gemini separate; move Hugging Face to optional |
| `orchestration/budget_controller.py` | Add per-provider requests-per-minute and per-day tracking; add the capacity-aware planner (see WORKFLOW.md section 4) |
| `core/config.py`, `.env.example` | Remove server-side provider keys for the BYOK path; keep them only as an optional developer mode |
| `core/security.py` | Superseded by D8 (stateless web): file deleted; there is no user auth. Desktop local calls use a per-launch token (`src/main.py`); web keys travel per request and are wiped after the run. |
| `core/logging_config.py` | Add a key-masking filter |
| `api/executions.py` | Desktop-only local history (D8). Web runs use stateless `POST /api/run` (SSE) in `src/api/run.py`; per-request keys are never persisted |
| `orchestration/consensus.py` | Keep your multi-factor score; add the adversarial-round trigger and calibration (WORKFLOW.md section 6) |
| `database/models.py` | SQLite for desktop only (D8); store provider, model, family and tokens per agent run; never store keys |
| `static/` frontend | Migrate to Next.js + TypeScript + Tailwind after the end-to-end run works |
| Docs and diagrams | Replace OpenAI/GPT boxes with the free lineup |

---

## 9. Dev tooling

| Need | Tool |
|---|---|
| Backend env | Python 3.11+, venv, `pip-tools` or `uv` |
| Lint and types | ruff, mypy (optional) |
| Frontend | Node LTS, pnpm or npm, ESLint, Prettier |
| Tests | pytest + pytest-asyncio; mock providers for unit tests; a small "replay" provider that returns recorded outputs for demos |
| Packaging | PyInstaller (backend), Tauri bundler (installer) |
| CI | GitHub Actions: lint, tests, key-leak scan |
| Benchmark | A `bench/` folder: `questions.jsonl`, `run_single.py`, `run_assembly.py`, `grade.py`, results CSV |

---

## 10. What to do first (this week)

1. Create free keys for **Gemini, Groq, and Cerebras (or OpenRouter)**; add them locally.
2. Run your Phase 1 app end to end with one real question.
3. Switch the router to the distinct-family rule and add the key-masking log filter.
4. Write 10 benchmark questions, run a single model and Assembly on each, and look at the results before building more.
