# Documentation drift (updated October 12, 2026)

Statements in docs that still contradict the code or PRD v1.1 (D8).
Resolved findings are removed from this active list as documentation is corrected. Verified against `src/` (no `src/api/auth.py`;
no `get_current_user`/`current_user`; `src/database/models.py` has no
User table; web runs are stateless SSE in `src/api/run.py`).

## Must-fix (describe features that do not exist)

- `docs/threat-model.md:15` — "**JWT secret key** | Signs all user sessions in web mode". Suggested fix: there are no user sessions; re-scope to the desktop per-launch token (`X-Assembly-Token`, `src/main.py`) or mark historical.
- `docs/threat-model.md:18` — "**User account credentials** | Email + bcrypt-hashed passwords in the database". Suggested fix: remove; no user table exists.
- `docs/threat-model.md:30,34` — the data-flow still shows web JWT authentication. Suggested fix: redraw the web boundary for stateless SSE and desktop-only local authentication.
- `docs/threat-model.md:49` — "TB1 Internet to FastAPI: CORS + JWT (web)". Suggested fix: "CORS + per-IP rate limits + origin checks" (`src/main.py`, `src/core/rate_limit.py`).
- `docs/threat-model.md:63,66-67` — "S1 | Forged JWT…", "S4 | Replay of old session JWT…", "S5 | Brute-force login". Suggested fix: remove; there is no login and no session JWT to forge, replay, or brute-force.
- `docs/threat-model.md:93-94` — "I3 | JWT token in WebSocket query string", "I4 | JWT secret dual-used as quota HMAC salt". Suggested fix: mark fixed-and-obsolete — WS auth is a first-message payload (`src/api/executions.py:303`) and quota uses a dedicated salt.
- `docs/threat-model.md:116` — "E1 | dev auth bypass … `get_current_user_id` skips JWT". Suggested fix: remove; the function does not exist in `src/`.
- `docs/threat-model.md:133,135-136` — "Auth (web) | JWT HS256…", "Authorization | user_id enforced…", "Rate limiting | Per-IP + per-user". Suggested fix: "Auth (web): none"; "Authorization: none (no users)"; "Rate limiting: per-IP + concurrency cap".
- `docs/threat-model.md:147-165` — GAP-1..GAP-4 fix notes cite `src/api/auth.py` and `src/core/security.py`, both deleted. Suggested fix: mark the GAP notes historical; keep the still-valid mitigations (rate limits, first-message WS auth, quota salt).
- `docs/project.md:13,51,72-73,86` — `src/core/security.py` JWT/bcrypt, `src/api/auth.py` signup/login, "User created, JWT returned", "Add Google OAuth". Suggested fix: annotate as Phase-1 historical or update to the stateless design.
- `docs/Assembly — Product Requirements Document v1.0.md` — whole file is the frozen v1.0 copy. Suggested fix: add a "Superseded by `docs/PRD.md` v1.1" banner or delete the duplicate.

## Should-fix (overstatements)

- `docs/PRD.md:65` (§4 non-goal) — "No manual team building or manual model selection by the user". The model picker exists (`frontend/src/components/model-picker.tsx`; `model_selection.selected` + `pins` in `src/database/schemas.py`), defaulting to Auto. Suggested fix: narrow to "No manual team building; model selection is picker-only (Auto default), the router still assigns by role and family".
- `docs/PRD.md:87-94` (§7.1) and `docs/WORKFLOW.md:100-107` (§4) — per-tier call bands are still estimates ("to be measured" / "replace with measured numbers"): no real-key benchmark has run (`bench/results/REPORT.md` is synthetic demo data; all `bench/questions.jsonl` answers carry `NEEDS HUMAN VERIFICATION`). Suggested fix: keep the "estimated" labels until the first graded benchmark lands.

## No fix needed (dated records)

- `docs/audit.md:34-35,45-46,85` — 2026-10-08 point-in-time audit ("No code changed"); describes since-deleted auth/JWT code. Suggested fix: none; optionally add a banner pointing at PRD v1.1.
- `docs/progress.md:13,51,72-73,86` and `docs/project.md` Phase-1 section — append-only Phase-1 log entries. Suggested fix: none; history stays.
