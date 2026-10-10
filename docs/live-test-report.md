# Live-test report — local production run as a user (2026-10-10)

REPORT-ONLY session: no code, config, models.yaml, test, or branch changes;
nothing committed, merged, or pushed. Branch `main`, commit `df5d687`.

## 1. Environment

- Commit `df5d687`, branch `main` (first command output). Working tree had
  pre-existing modifications (`docs/progress.md`, `__pycache__`, untracked
  `docs/live-test-report.md` from an earlier session); this session added no
  source changes.
- Backend: Python 3.13.15, uvicorn 0.34.0, single worker:
  `APP_MODE=web APP_ENV=production PORT=8000 DEBUG=false
  CORS_ALLOW_LIST=http://localhost:3000,http://127.0.0.1:3000`
  plus all six key names blanked (`GEMINI/GROQ/CEREBRAS/OPENROUTER/
  HUGGINGFACE/TAVILY_API_KEY=""`) so the `Settings` dotenv loader could not
  pick up `.env` values. Zero server-side keys (status endpoint: all
  `available:false`, `families:[]`, `diversity:BLOCKED`).
- Frontend: Node v24.19.0, Next 16.4.0. `npm run build` in `frontend/`.
  First attempt failed type-check on a stale `.next/dev` cache (deleted
  `.next`, rebuilt — build cache only, no source change). Second build:
  22 s, static export to `out/` (routes `/`, `/chat`, `/executions`,
  `/settings`, `/styleguide`, `/_not-found`), total ~3.2 MB. Largest
  assets: 599 KB + 224 KB + 156 KB JS chunks, 86 KB styleguide.html,
  59 KB index.html. Warnings: Turbopack workspace-root inference (dual
  lockfiles at repo root and `frontend/`); `output:"export"` means
  `next start` does not apply — served with `npx serve out -l 3000`
  (documented gap vs the `next build + start` instruction).
- Quota report before: `No quota usage recorded for 2026-10-10 UTC`,
  resets in ~11:59. Quota report after: identical (no billed executions;
  server-side table stays empty in web mode — per-request usage lives in
  the browser). Provider-side spend this session: ~4 tiny groq Test calls
  (valid), 2 gemini Test probes (safety-blocked, see U-06), 3 openrouter
  Test attempts (rate-limited, stopped per quota rule), 1 canary outbound
  auth-failure (unbilled). **Zero live executions** — the UI path is
  blocked (B-01), so the one allowed live run could not be spent.
- Test counts: backend suite not re-run (report-only); frontend production
  build type-check passed on second attempt.

## 2. Verdict: NOT READY for a public deploy

A user with valid keys cannot start any run from the web UI: preflight
ignores browser keys and always answers infeasible (B-01). Keys vanish on
normal navigation because the vault is memory-only and landing links force
full reloads (B-02); the "remember" persistence self-destructs on load
(B-03). Fix the run path, key survival, and persistence before any public
exposure; the remaining issues are real but secondary.

## 3. Issues table

ID | severity | where | what the user experiences | how to reproduce (exact steps) | evidence (never a key) | suggested fix | effort
---|---|---|---|---|---|---|---
B-01 | Blocker | `src/api/executions.py:70` + `frontend/src/lib/api-client.ts:72` + `frontend/src/app/chat/page.tsx:137` | With valid keys saved, Launch shows "Checking capacity…" then "Not feasible: …0 affordable", and no run ever starts. | 1. Serve production frontend + web backend. 2. Save a valid groq key (Test: valid, chip: 2 families). 3. Ask anything, Launch. | `POST /api/executions/preflight` → `feasible:false, usable_keys:0` (probed); server log shows zero `POST /api/run`; `_build_preflight` uses the shared server router, `ApiClient.preflight` sends no keys | Accept `provider_keys` in preflight and build a per-request router (as `/api/run` already does) | M
B-02 | Blocker | `frontend/src/app/page.tsx:70,101` (plain `<a>`) + `frontend/src/lib/key-vault.ts:45` (memory-only) | Keys entered on Settings are gone by the time Chat loads when the user passes through the landing page (the only Settings→Chat path in the sidebar). Chat shows 0 families; Launch disabled. | 1. Chat → Configure Keys → save groq key (readiness: 2 families). 2. Click logo → Start Researching. 3. Chat chip reads 0 families. | Marker probe: JS marker survives settings→landing, dies landing→chat (full reload); `dbg.mjs` chip 2→0 | Use Next `<Link>` on landing CTAs and/or keep chat reachable without full reloads; warn before navigation loses keys | S
B-03 | Blocker | `frontend/src/components/keys-manager.tsx:54-62,68-77` | "Remember on this device" does not survive a reload: after reload the passphrase box is gone, readiness is 0, and the saved vault is unrecoverable. | 1. Settings: check Remember, set passphrase, save key (mocked or real Test). 2. Reload. | `ls_before:"true"` → `ls_after:"false"`; mount effect calls `setRemember(false)` (writes flag + `clearPersisted()` deletes the blob) before `load()` restores state | Gate the mount sync-effect behind vault load (`vaultLoaded`), never clear persisted data on mount | S
U-01 | High | `src/api/executions.py:70-83`, `src/research/search.py:22-26`, `src/research/providers.py:110-113` | Web search silently uses the server `.env` key in web mode, or silently does nothing when blanked; there is no UI field for a search key, so research answers ship with no live sources and the user is never told. | 1. Run any research question. 2. Note no sources / no notice. Code: `SearchEngine` reads `settings.tavily_api_key`; `KeysManager` renders catalog LLM providers only. | Server runs only worked because launch blanked the key (`tavily_configured:False`); without blanking, `.env` search key would serve all web users | Add a per-request search-key field or disable search in web mode with a visible notice | M
U-02 | High | backend CORS allow-list (`.env` `FRONTEND_URL`) | A local production frontend gets `400` on every `OPTIONS /api/catalog` and an empty catalog (no provider cards, banner falls back to "catalog order") unless the operator overrides `CORS_ALLOW_LIST`. | 1. Start backend with stock `.env` + static frontend on :3000. 2. Open Settings. | Server log: repeated `OPTIONS /api/catalog → 400`; `provider_cards:0` before override, `4` after | Document the override; fail visibly in UI when catalog is unreachable (picker already shows "Could not load model catalog", settings does not) | S
U-03 | High | `src/core/rate_limit.py:19-30` + `/api/run` ordering | Invalid/oversized requests consume the 5/min run budget, so fumbling with a 2001-char question can lock the user out with 429s. | Send 6 atypical `/api/run` POSTs in a minute (probed: 422/413s then `429`). | `mem_probe` outcomes opened `http-429` ×4 before window reset | Count only accepted runs toward the run limiter, or return 429 headers with reset info | S
U-04 | Medium | `src/core/rate_limit.py:37-38` | `X-Forwarded-For` is ignored (`request.client.host` only), so behind any proxy all users share one IP budget (one abuser throttles everyone; `MAX_RUNS_PER_IP=2` misfires). | Send `/api/run` with spoofed `X-Forwarded-For` variants — all counted as 127.0.0.1. | Code read; no proxy-header handling anywhere in `src/` | Trusted-proxy config (`PROXY_HEADERS`) or document single-IP behavior | S
U-05 | Medium | `frontend/src/components/model-picker.tsx:39-49` | Model picker overstates readiness ("7 families") by counting disabled providers and keyless families; narrowing selection can silently drop to 2 families. | Open chat with no keys: picker chip reads 7 families while chat chip reads 0; select 2 models → "2 families ready". | `j4-results.json` (`picker_chip_auto` vs chat chip; 14 checkboxes) | Filter picker by enabled providers and/or keyed families; share one gate component | S
U-06 | Medium | `/api/keys/test` + `src/providers/gemini_provider.py` | The gemini key Test reported "invalid" while the server log shows the probe itself was safety-blocked (`finish_reason 2` on "Reply with the word ok."), i.e. a valid key can read as invalid. | Save gemini key → Test → invalid; server log: `response.text … requires a valid Part … finish_reason is 2` (3 occurrences). | Change probe text to something safety-neutral or map safety-blocks to a distinct "untestable" state | S
U-07 | Medium | `frontend/src/components/keys-manager.tsx:22-26` + no trim in `handleSaveAndTest` | Pasted keys with leading/trailing whitespace are stored verbatim (no trim) and the masked placeholder reveals first+last 4 chars of whatever was saved. | Fill `␣␣gsk_canary…␣␣` (canary, unsaved): hint is advisory-only; code stores `rawKey` as-is. | Code read + whitespace probe (`whitespace_cleared:true`, hint text recorded) | Trim on save; mask with fixed bullets revealing nothing | S
U-08 | Medium | catalog vs `Settings`/`EnvKeyStore` | The `nvidia` provider card (enabled) has no documented key name: no `NVIDIA_API_KEY` in `.env.example` or `Settings` (`has_provider` omits it), so dev-mode users cannot configure it while the UI invites a key. Same class: `mistral` card exists only when enabled. | Open Settings: 4 cards incl. nvidia; `.env.example` lists 5 LLM keys; `src/core/config.py:54-58` + `keystore.py:171-178` lack nvidia/mistral. | Add the missing key names or hide/disable cards without a key path | S
U-09 | Low | chat run flow (`handleLaunch`) | Refresh or tab-close mid-run silently kills the run: the SSE disconnect cancels the server task and nothing is saved (history persists only after completion), with no "run cancelled" notice. | Start canary `/api/run`, disconnect after 2 chunks → `EXECUTION CANCELLED`, follow-up accepted (slot freed). | Server log `Run finished` + `EXECUTION CANCELLED`; follow-up 200 | Distinguish cancel vs failure in a visible status; optionally retain partial runs | M
U-10 | Low | static export serving | RSC prefetch URLs (`/__next.*.txt`, `/settings/__next.*`) 404 on the static server, and `next start` is unusable with `output:"export"` (deviates from `next build + start`). | Serve `out/` statically; watch network log during nav. | Serve log: repeated `404` on `*.txt` prefetch paths | Document the static-serve path or switch to a server build | S
U-11 | Low | `serve` headers | Static frontend emits no CSP/HSTS (backend API has `nosniff`, `Referrer-Policy`, HSTS; CSP only exists in `next.config.ts` and is not emitted for static export). | `curl -I :3000/` vs `:8000/health` header comparison. | Add headers at the hosting layer and document them | S
U-12 | Low | `npm audit` | 9 high / 4 low, all in dev toolchain (eslint-plugin-next, shadcn/ts-morph chain, micromatch/braces/fast-glob); 0 critical. `pip-audit` not installed (gap). | `npm audit --json` metadata; `pip_audit` module missing. | Bump toolchain deps; add `pip-audit` to dev requirements | S

## 4. User pain — 10 most likely reasons a first-timer gives up, ranked

1. "Not feasible" dead end: with good keys, Launch never starts a run (B-01). Nothing to try; looks like quota.
2. Keys vanish navigating Settings → Chat via the landing page (B-02). Re-entering keys repeatedly feels broken.
3. "Remember on this device" forgets everything after reload — and destroys the saved blob (B-03). Trust lost.
4. Local setup shows an empty Settings page (no provider cards) because of the stock CORS allow-list (U-02). Looks like the app is down.
5. Gemini key reported "invalid" though the key is fine (probe safety-block, U-06). User concludes the product is wrong about their key.
6. OpenRouter Test immediately "rate_limited" on a fresh key (observed on first minimal probe) with no guidance on which quota or when it resets.
7. No live sources in research answers and no notice that web search needs a server key the UI cannot set (U-01).
8. Refresh mid-run loses everything with no message (U-09); the 5-minute wait ends in silence.
9. Fumbling with long questions triggers 429s that also block valid runs for a minute (U-03).
10. No progress view for web runs: chat shows only status text ("Checking capacity…"/"Running team…") and history appears only after completion — a 5-minute black box (observed: `time_to_first_status_ms:67`, then nothing until navigation).

## 5. Measurements

- Build: 22 s (after `.next` cache clear; first attempt failed type-check on stale `.next/dev` types referencing a deleted `setup/page`). Total `out/`: ~3.2 MB; top chunks 599/224/156 KB JS; `index.html` 59 KB.
- Load: landing 67–186 ms (Chromium), 465 ms (Firefox), 209 ms (WebKit) locally; chat similar; slow-3G reload ≈1780 ms. No horizontal scroll at 375/768/1440. First Tab stop: "Configure Keys".
- Key Tests (live, minimal): groq valid (×4 runs of script, each 1 call), gemini invalid (safety-blocked probe), openrouter rate_limited on first attempt — stopped per quota rule, never retried.
- Live run: none possible (B-01). `time_to_first_status_ms:67` then preflight-infeasible abort; `total_run_ms: timeout` (370 s cap, page stayed on chat, no history/usage saved).
- Mocked: double-click → exactly 1 `POST /api/run` (loading guard works); mocked failed run → navigates to `/executions?id=local-…` with failed status; offline-after-load banner shows; reload-while-offline shows browser error page (no app offline page); export download works; import toast works; clearing site data re-shows privacy notice.
- Server: `/health` 27 ms warm; restart-to-ready <10 s locally. Empty-keys `/api/run` completes <1 s (BLOCKED SSE, tokens 0). RSS flat 152,356 KB across 6 completed + 4 rejected runs (delta 0). Disconnect mid-run → `EXECUTION CANCELLED`, slot freed (follow-up 200). Validation: wrong types/unknown fields/empty/whitespace/2001-char/bad tier → 422; 2 MB body → 413; unknown-provider key-tests → 404×10 then 429 (10/min limiter works); foreign-origin `/api/run` → 403, `/api/catalog` → 200 (public by design).
- Browsers: Chromium/Firefox/WebKit all render landing/chat/privacy identically.

## 6. What could NOT be tested and why

- The one allowed live execution (and everything downstream: time-to-first-event, run time vs budget, calls/provider, tokens, agent failures, research quality, citations, confidence/uncertainty wording): blocked by B-01 — the UI cannot start runs in web mode. No quota was spent working around it.
- SSE through buffering proxies / 30–60 s idle gaps: no long-lived stream exists without a live run (heartbeat is 15 s by config: `max(5, SSE_HEARTBEAT_SECONDS)`); longest idle gap unmeasured.
- Deadline-during-synthesis and countdown-vs-deadline drift: needs a live run.
- Real provider outages / real 429 mid-run recovery: only the openrouter Test 429 was observed (reported, not retried).
- Real devices, mobile browsers, screen readers: desktop Chromium/Firefox/WebKit only; keyboard pass limited to focus order/labels spot-checks.
- Windows installer / hosted deploy / sleeping free hosts: local `serve` + uvicorn only.
- `pip-audit`: not installed; `npm audit` covered frontend only.
- MAX_CONCURRENT_RUNS=20 "server busy": not forceable without 20 concurrent billed runs; slot release verified instead.

## 7. Key hygiene result

- Keys loaded only inside scripts via `dotenv` (same `.env`-then-`.env.dev` order as `scripts/`), passed to the browser solely through Playwright `fill` on password inputs or held in page memory. No key in any command line, log, file, screenshot, snapshot, HAR, trace, or video. Trace/video/HAR stayed OFF throughout; screenshots taken only on pages with no key visible (inputs cleared first; settings never screenshotted after fills).
- Artifacts lived only in `.local/live-test/` (verified git-ignored). Browser contexts were fresh per section; the one vault-persistence context was left with no saved state (persistence self-destructs, B-03).
- Scanner (`.local/key_scan.py`: allowlisted values compared in memory only + generic `gsk_/sk-or-/AIza/hf_/tvly-/csk-` patterns) over `.local/live-test/`, copied server logs, and this report: **clean** (0 hits). Canary strings used `canary` + underscores and match no generic pattern; no real key appears in any artifact.
- Pre-delete file count in `.local/live-test/`: 40+ (scripts, result JSONs, PNGs, build logs, probes). **Artifacts deleted** after the clean scan; helper scripts kept outside the folder are names-only.
- Rotations: none required — no real key left the vault path; no key committed (branch `main` untouched, nothing staged). Note: the openrouter 429 and gemini safety-block are provider-side states, not leaks.
