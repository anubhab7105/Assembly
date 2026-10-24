# Hosted Web Rehearsal — Issue #37

This runbook distinguishes deterministic CI checks from evidence needed to mark R1 demo-ready. A mock test or local replay is **not** evidence of a hosted live run.

## 1. Release gate

Do not call the deployed website demo-ready until:
- [ ] The deployed frontend and backend URLs are recorded, and `/health` is healthy.
- [ ] A full run with a 5-minute requested budget completes on the actual deployed host and its elapsed time is recorded.
- [ ] Ten rehearsal attempts have been recorded; provider errors never reveal raw provider messages, keys, tracebacks, or internal exceptions.
- [ ] First progress-event latency is measured from the browser's run-submit timestamp to the first SSE progress event and meets the PRD target (<3 seconds).
- [ ] Timeout / hard-cutoff behavior is observed at a budget boundary.
- [ ] The local one-command fallback has been tested from a clean terminal.
- [ ] A real recorded replay has been captured and replayed successfully offline.

If the host times out or terminates streaming before the 5-minute run can finish, mark the hosted rung **unavailable**, preserve the evidence, and use the tested local/replay fallback. Do not silently treat a shorter run as satisfying the five-minute gate.

## 2. Safe execution

Use real provider keys only in the application's browser Settings/Key Vault or a private local environment such as ignored `.env.dev`. Never paste credentials into a command argument, terminal transcript, screenshot, log, CI variable, rehearsal report, or issue/PR comment. Do not use a real provider key in CI.

For each attempt, prepare the browser DevTools Network panel before starting:
1. Filter to `/api/run`; note the start time immediately before submitting.
2. Observe the initial response and subsequent SSE events. Record the timestamp of the first progress event and the timestamp of `run.finished` (or disconnect/error).
3. Record only the requested tier, actual plan/tier if shown, provider/model names or families (no key data), source-rendering result, final status, elapsed time, and sanitized error category.
4. If an error occurs, verify the UI offers an actionable generic outcome and inspect only redacted operational metadata. Do not copy raw provider response bodies into the report.
5. Remove transient test keys from the browser when the rehearsal is over, if they were created solely for rehearsal.

## 3. Scenario matrix

Complete one row per attempt. Use separate keys/accounts or carefully planned quota budgets for negative/quota scenarios, and stop if a test risks consuming a production user's quota.

| Scenario | Setup | Expected observation |
|---|---|---|
| Successful sourced answer | Valid keys, question that needs research, search key configured if required | Completed status, sources actually used render, no source fabrication |
| Transient provider failure / timeout | Use a provider known to fail or a controlled outage window; do not corrupt shared production credentials | Fallback provider/family used when available; otherwise safe partial/failure state |
| Invalid key | Temporarily configure a disposable invalid key in the test browser | Key test/run gets safe actionable status; no raw body or credential leakage |
| 429 / quota exhaustion | Use an already-limited disposable key or wait for natural exhaustion; do not intentionally exhaust a shared key | Reduced capacity or fallback is explained; secrets and raw provider detail remain hidden |
| Refresh / close tab during SSE | Start a safe investigation and refresh/close the test tab | Confirm the web request is cancelled on disconnect; record that web SSE does not reattach |
| Budget boundary | Request 5 minutes and let the host run close to its cutoff (or use a longer supported test with time safely reserved) | No overrun past the application budget; final status is surfaced safely |

Do not perform fake outages, quota exhaustion, or repeated provider calls against production users. If a case cannot safely be run, mark it **not tested** with the reason.

## 4. Ten-run rehearsal record

Copy this template to a private local note or to the release evidence file after each rehearsal. Never include questions containing sensitive information, keys, provider response bodies, or user data.

| # | Date/time (UTC) | Target + deploy ID | Requested tier | Actual tier/plan | First progress (ms) | Elapsed (s) | Final status | Provider families | Sources rendered? | Failure / safe UX notes |
|---:|---|---|---:|---|---:|---:|---|---|---|---|
| 1 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 2 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 3 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 4 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 5 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 6 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 7 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 8 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 9 | NOT RUN | — | — | — | — | — | — | — | — | — |
| 10 | NOT RUN | — | — | — | — | — | — | — | — | — |

## 5. Local fallback: one command

Prerequisites: Python dependencies installed at repository root and frontend dependencies installed under `frontend/`.

- Install once: `python -m pip install -r requirements-dev.txt` and `npm ci --legacy-peer-deps` from `frontend/`.
- Start both services from the root: `python scripts/dev_web.py` (or `make run-web`).
- Open `http://127.0.0.1:3000`. Configure provider keys through the browser UI.
- Stop the stack with Ctrl+C. The launcher checks port availability, waits for both HTTP readiness endpoints, and terminates both child processes on shutdown.

To use alternate ports: `python scripts/dev_web.py --backend-port 8001 --frontend-port 3001`. The launcher injects the selected API URL and local CORS origins for its child processes; it does not edit `.env` or source files. Existing port conflicts fail with a clear error instead of killing an unrelated process.

## 6. Recorded replay fallback

Record a suitable run privately with `python scripts/record_run.py --budget 3 --out recordings/demo-run.json`; use keys loaded from ignored `.env.dev`. Treat recordings as sensitive because they contain prompts, model responses, and possibly source text even though they omit API keys. Do not commit recordings containing non-public prompts or data.

Replay without network access: `python scripts/replay_run.py recordings/demo-run.json`. Confirm it exits with code 0 and the expected answer and sources render. Retain a sanitized, demo-safe recording and know its exact path before the presentation.

## 7. What CI can and cannot prove

CI should test launcher argument/port checks and docs/runbook invariants without requiring provider keys or reaching external providers. CI does **not** prove live hosted streaming, provider quota behavior, platform timeout limits, ten successful demo runs, or that a real recorded replay is presentation-ready. Those need an operator rehearsal with real deployments and disposable/controlled keys.
