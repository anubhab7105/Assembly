# Live-test report — fixed tree (Prompt A + Group 1), real UI run (2026-10-10)

REPORT-ONLY session: no code/config/branch changes; nothing committed,
merged, or pushed. Branch `main`. Hygiene pre-flight skipped (done
earlier); all key-safety, isolation, and quota rules from the earlier
prompt were kept.

## 1. Environment

- Branch `main`; HEAD `fb15c2a` (Prompt A) plus uncommitted Group 1 work
  (shared preflight context, Link navigation, vault persistence). Tree
  Motions: report-only, no commits by this session.
- Backend: Python 3.13.15, uvicorn, 1 worker, `APP_MODE=web
  APP_ENV=production PORT=8000`, `CORS_ALLOW_LIST` overridden to
  `http://localhost:3000,http://127.0.0.1:3000` (launch env only — stock
  `.env` still points at the hosted frontend), all six key names blanked
  in the launch env. Status endpoint: zero server-side keys, `BLOCKED`.
- Frontend: Node v24.19.0, Next 16.4.0, fresh `npm run build` in 21 s
  (tsc clean, no warnings this time), static `out/` ≈3.2 MB (largest
  chunks 599/224/156 KB JS), served with `npx serve out -l 3000`
  (`output:"export"` so `next start` does not apply — known gap).
- Quota before: `No quota usage recorded`, reset ~9:36. Quota after:
  identical (server table stays empty in web mode). Provider-side spend:
  3 Test calls (groq valid; gemini ran ~45 s then client timed out;
  openrouter instant 429, skipped per rule) + ONE tier-5 run
  (~6 LLM calls). No other live calls; every failure probe used mocks
  or validation-first canaries.
- Playwright: Chromium 1440px, trace/video/HAR OFF throughout,
  screenshots only on key-free screens, inputs cleared after fills.

## 2. Verdict: READY WITH FIXES

The three blockers are fixed and proven live: preflight sees browser
keys (200, gate OK), keys survive landing navigation (5-family chip on
chat), and one real tier-5 run completed end-to-end (18 s, COMPLETED,
consensus 64%). Remaining issues are real but non-blocking: Gemini is
unusable (limits unfilled + safety-blocked Test probe), vault Remember
was not exercised live, and several UX/log rough edges persist.

## 3. Issues table

ID | severity | where | what the user experiences | how to reproduce (exact steps) | evidence (never a key) | suggested fix | effort
---|---|---|---|---|---|---|---
N-01 | High | `models.yaml` gemini limits + `src/api/keys.py` Test probe | A valid Gemini key can never be used: the router loud-skips gemini (null rpm/rpd/tpm) and its Test reports failure — this time the probe ran 45 s and the UI timed out waiting. | 1. Save gemini key, press Test. 2. Watch 45 s timeout. | Server log: `LIMITS NOT FILLED for enabled provider 'gemini'` (×N) + `finish_reason is 2` safety error on the probe; UI `test-result: timeout` | Fill gemini limits from the dashboard (or disable until filled) + safety-neutral probe (Group 3 item 9) | S
N-02 | High | OpenRouter free tier | First minimal Test call instantly `rate_limited` (server log: 60 s cooldown set), so OpenRouter contributed only the critic call in the run and any heavier use degrades. | Save openrouter key → Test → "Key is valid but rate-limited." | UI result + `cooling down for 60s` log line; run still COMPLETED via groq | Surface quota-reset guidance in the Test result; prefer non-rate-limited providers in routing | S
N-03 | Medium | `src/core/logging_config.py:64` `_LONG_TOKEN_RE` | OpenRouter model ids render as `***:free` in logs (e.g. critic routed to `***:free`), breaking the names-only attribution the codebase promises. | Run with an OpenRouter model; read server log. | `critic → ***:free (nemotron)`, `Tokens solve r1 critic agent_03 ***:free` | Exclude `provider/model`-shaped tokens (allow `/`, `:free` suffix, catalog ids) from the long-token pattern | S
N-04 | Medium | `frontend/src/components/final-answer.tsx:48` vs composed answer | Confidence chip says "High" while the answer text ends "Confidence: Moderate…" — contradictory labels on the same screen. | Complete any non-high-confidence run; compare chip vs answer tail. | r2-final screenshot (chip High, text Moderate) | Derive the chip from the same capped label the composer emits | S
N-05 | Medium | model picker (`model-picker.tsx:39-49`) | Picker claims "7 families ready" with no keys (counts disabled/keyless providers); narrowing selection can silently drop coverage. Re-verified post-fix. | Open chat keyless: picker 7 families vs chat chip 0. | r2-chat-ready screenshot | Count only enabled providers with usable keys (Group 3 item 11) | S
N-06 | Medium | stock CORS allow-list | Unchanged: local production frontend gets `400` on catalog preflights without a launch-env override (this session used the override). | Start backend with stock env + static frontend; Settings shows no cards. | Prior session evidence; banner shows "catalog order" fallback | Dev default allow-list (Group 2 item 6) | S
N-07 | Medium | executions view post-run | After completion: timer `--:--`, "Active Team (0) / Forming temporary team…", no per-provider call/timing breakdown (usage holds only the `run` total). | Finish any run; read the executions page. | r2-final screenshot; usage `[{provider:run,count:1,tokens:7026}]` | Freeze final team/timer state; record per-provider usage entries | M
N-08 | Low | planner research gate | A "compare battery chemistries" question classified `Type=general, Research=False` → 0 searches; keyless providers never exercised though the question wanted sources. "No external sources" wording was correct. | Ask the battery question at 5 min; read planner log line. | `Research=False`, `0 searches`, answer with uncertainties but no citations | Tune research trigger or expose a research toggle | M
N-09 | Low | refresh mid-run | Still no beforeunload warning (Group 3 item 12 not implemented); mocked slow-run reload loses the stream with no history and no message (re-verified; one probe read `missing-page` on chip lookup after reload). | Mock slow SSE, reload mid-run. | r3 results (`refresh_history` unknown, no warning UI) | beforeunload + "cancelled when the page closed" notice | S
N-10 | Low | static serving noise | RSC `__next.*.txt` prefetch 404s and `GET /v1/models 404` (external local poller, not this app) clutter logs. | Serve `out/` statically; watch network/server log. | Serve log `404` lines | Document static-serve path; ignore `/v1/models` (no such API) | S
Fixed since last time (verified live, not issues): B-01 preflight-with-keys (`POST /api/preflight` 200, gate OK 3 families); B-02 Link navigation (5-family chip survived settings→landing→chat); 400 `blocked_no_usable_keys` + 410 old preflights live; foreign-origin run 403; validation 422s + 2 MB 413; key-test limiter 10×404→429; Tavily warning once at startup; Tavily UI field saves; unlock prompt + wrong-passphrase error + memory banner all working (mocked, canary only); disconnect cancels server task and frees the slot.

## 4. User pain — top 10, ranked

1. Gemini key appears broken (timeout/rate-limit style failure on Test) though the fault is null limits + probe text.
2. OpenRouter free key rate-limits on first touch; the run survives on groq but users will blame setup.
3. Confidence says High and Moderate on the same screen.
4. No sources on a research-flavored question with no explanation of why (planner skipped research silently).
5. Post-run page looks unfinished (dead timer, empty team box, no per-provider breakdown).
6. Local setup still needs a CORS override or Settings is empty.
7. Refresh during the 5-minute wait kills everything silently.
8. Picker's "7 families" overpromises vs the chat chip's honest count.
9. 45-second Test hang on gemini with no progress indicator.
10. First-time users must discover Settings via a banner; no guided setup order.

## 5. Measurements

- Build 21 s, tsc clean; bundle ≈3.2 MB (599/224/156 KB top chunks).
- Load: landing ~70–190 ms, chat similar (local).
- Key Tests: groq valid (~1 s); gemini timeout at 45 s client cap (server errored later); openrouter instant rate_limited.
- THE run: tier 5, question Batt-chemistry (77 chars); first status 65 ms; finished 18.4 s vs 300 s budget; COMPLETED; consensus 64% (solver 80 / researcher 65 / critic 70 / synthesizer 78); tokens 7026 total (planner 563, solve 1123+951+1922, synthesis 2467); ~6 LLM calls (groq 20b planner+solver, groq qwen researcher, openrouter nemotron critic, groq 120b synthesis); 1 debate round (early stop, no open disagreement); 0 searches; 0 failed agents; 0 provider 429s mid-run.
- Answer (2012 chars): solid-state most likely, sodium-ion niche, lithium-ion dominant through 2035, uncertainties listed. Honest opinion: good — specific, hedged, correctly scoped; no citations because no research ran.
- Server: warm `/health` ~27 ms; empty-keys run <1 s; RSS flat across runs (prior session); disconnect → `EXECUTION CANCELLED` + slot freed.
- Browsers this session: Chromium only (Firefox/WebKit verified last session, UI unchanged since except Link/vault).

## 6. What could NOT be tested and why

- Tavily-keyed research (by design: keyless default path per instructions; server flag stayed false).
- Remember-me live flow (passphrase persistence verified with mocks/canary only — real keys never persisted).
- SSE proxy gaps, deadline-during-synthesis, real provider outages, real devices/screen readers, installer/hosting sleep, 20-way server-busy: same as last session, still open.
- Full backend suite re-run post-fix (other agents occupying the tree; targeted suites green: 98 + 25 + 6 preflight-context).
- `pip-audit` (not installed); `npm audit` unchanged from last session.

## 7. Key hygiene result

- Allowlist loader (dotenv `.env`→`.env.dev`, names only in this report) held 3 values in memory; Playwright `fill` into password inputs; inputs verified cleared; no trace/video/HAR anywhere; screenshots on key-free screens only (settings screenshotted before fills; chat/final/unlock contain no key material).
- One live execution only (tier 5); one 429 seen (openrouter Test) → provider skipped, never retried; run itself saw zero 429s.
- Scanner (allowlisted values in memory + generic `gsk_/sk-or-/AIza/hf_/tvly-/csk-` patterns) over `.local/live-test/`, the copied server log, and this report: **clean** (0 hits; canary markers also 0 in server log).
- Artifacts deleted after the clean scan. No keys committed, no rotations required.
