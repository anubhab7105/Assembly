# Assembly - STRIDE Threat Model

**Date:** 2026-10-09
**Reviewer:** Security Audit (Antigravity)
**Scope:** Web mode (FastAPI + Vercel) and Desktop mode (Tauri 2 + PyInstaller sidecar)
**Revision:** 1.0

---

## 1. Assets

| Asset | Description | Sensitivity |
|---|---|---|
| **User AI provider keys** | BYOK keys (Gemini, Groq, Cerebras, OpenRouter, HuggingFace, Tavily). Web: in-memory per-request; desktop: Windows Credential Manager. | **Critical** |
| **JWT secret key** | Signs all user sessions in web mode. Compromise = full user impersonation. | **Critical** |
| **Desktop token** | secrets.token_hex(32) generated at sidecar startup. Authorizes all local HTTP calls. | **High** |
| **Conversation history** | User questions and final answers stored in SQLite (desktop) or PostgreSQL (web). | **High** |
| **User account credentials** | Email + bcrypt-hashed passwords in the database (web mode). | **High** |
| **Execution events** | Intermediate agent reasoning, positions, debate transcripts. | **Medium** |
| **Model routing telemetry** | Provider names, model names, family tags, token counts. No keys. | **Low** |

---

## 2. Trust Boundaries

`
WEB MODE
  [Browser]--HTTPS-->[Vercel Frontend]
      |                     |
  (JWT)           (REST/WS + Bearer JWT)
                            |
                   [FastAPI on Render] <--TB1
                        |   |
                   [SQLite/Postgres]  <--TB2
                        |
        [Gemini API]  [Groq API]  [Tavily API]  <--TB3

DESKTOP MODE
  [Tauri WebView]--local HTTP-->[Python sidecar]  <--TB4
      |                              |
  (desktop_token)           [SQLite app data]
                                     |
                          [Windows Credential Mgr] <--TB5
                                     |
                         [AI Provider APIs]  <--TB3
`

Boundary definitions:
- TB1 Internet to FastAPI: CORS + JWT (web), desktop_token (desktop)
- TB2 FastAPI to Database: SQLAlchemy ORM (parameterized; no raw SQL)
- TB3 FastAPI to External APIs: HTTPS; keys in headers/body only
- TB4 Tauri WebView to Sidecar: localhost 127.0.0.1 only; desktop_token
- TB5 Sidecar to OS Keyring: Windows Credential Manager via keyring

---

## 3. STRIDE Threat Analysis

### 3.1 Spoofing

| ID | Threat | Mode | Current Mitigation |
|---|---|---|---|
| S1 | Forged JWT to access another user data | Web | JWT signed with jwt_secret_key; sub enforced on every DB query |
| S2 | Cross-origin WebSocket from malicious page | Web | Origin checked vs frontend_url; token required |
| S3 | Sidecar spoofed by another local process | Desktop | desktop_token (32-byte hex) required on every request |
| S4 | Replay of old session JWT | Web | exp claim enforced; 24h window |
| S5 | Brute-force login [GAP-1] | Web | NO RATE LIMIT on /api/auth/login or /api/auth/signup |

### 3.2 Tampering

| ID | Threat | Mode | Current Mitigation |
|---|---|---|---|
| T1 | Modify another user's conversation | Both | user_id filter on every conversation/execution query |
| T2 | MITM modifies transit data | Web | HTTPS enforced; HSTS header set |
| T3 | Malicious models.yaml via file | Desktop | Read-only at startup; not user-editable via API |
| T4 | Prompt injection via web search results | Both | sanitize.py pipeline; UNTRUSTED_WEB_CONTENT delimiters; system prompt note |
| T5 | Prompt injection via user question [GAP-7] | Both | NO INJECTION SCAN on user question |

### 3.3 Repudiation

| ID | Threat | Mode | Current Mitigation |
|---|---|---|---|
| R1 | User denies submitting a question | Web | Execution row with user_id, question, started_at in DB |
| R2 | Key use untraceable | Both | Quota fingerprinting (HMAC of key); provider/model logged per agent run |
| R3 | No tamper-evident audit trail | Both | Standard DB; no WORM/signed log -- Accepted risk (MVP) |

### 3.4 Information Disclosure

| ID | Threat | Mode | Current Mitigation |
|---|---|---|---|
| I1 | Provider API key leaked in logs | Both | KeyMaskingFilter on root + third-party loggers; SecretStr; reveal() only at call site |
| I2 | Provider key in API responses | Both | _FORBIDDEN_KEYS in event sanitization; generic 422 handler |
| I3 | JWT token in WebSocket query string [GAP-2] | Web | ?token=JWT LOGGED by reverse proxy/CDN access logs |
| I4 | JWT secret dual-used as quota HMAC salt [GAP-4] | Both | quota.py:57 uses jwt_secret_key as HMAC salt |
| I5 | Stack traces in 500 errors | Both | Global handler returns generic message |
| I6 | Desktop token printed to stdout | Desktop | Tauri controls child stdout; low risk |
| I7 | Live API keys in OneDrive-synced .env [GAP-8] | Dev | Keys not committed to git but stored on OneDrive |
| I8 | Cross-user conversation access | Both | user_id filters on all queries |
| I9 | Desktop SQLite readable by local admin | Desktop | OS ACL; accepted risk |

### 3.5 Denial of Service

| ID | Threat | Mode | Current Mitigation |
|---|---|---|---|
| D1 | Flood execution endpoint | Web | 5 req/60s; 1 concurrent per user; global cap 50 |
| D2 | Flood key-test endpoint | Web | 10 req/60s |
| D3 | Huge request body | Both | 1 MB limit middleware |
| D4 | Execution never terminates | Both | Time-budget cutoff; BudgetController; Deadline |
| D5 | Rate limiter lost on restart | Web | In-memory only -- accepted risk (no Redis) |
| D6 | WebSocket connection exhaustion [GAP-5] | Web | NO per-execution WS connection cap |

### 3.6 Elevation of Privilege

| ID | Threat | Mode | Current Mitigation |
|---|---|---|---|
| E1 | dev auth bypass in production [GAP-3] | Web | get_current_user_id skips JWT if APP_MODE=dev, regardless of APP_ENV |
| E2 | SSRF via search URL injection | Both | All search targets hardcoded -- SAFE |
| E3 | SSRF via Tavily response URL reflection | Both | URLs stored as strings; backend never fetches them -- SAFE |
| E4 | Tauri shell:default grants broad shell access [GAP-6] | Desktop | default.json:11 allows arbitrary JS shell commands |
| E5 | opener:default opens arbitrary URLs | Desktop | Intentional; accepted risk with user-gating |
| E6 | User cancels another user's execution | Web | user_id ownership check in cancel endpoint |

---

## 4. Current Mitigations Summary

| Category | Status |
|---|---|
| Key storage | SecretStr wrap; reveal() single call site; mode-appropriate backends |
| Log scrubbing | KeyMaskingFilter on root + httpx + openai + groq + keyring loggers |
| Prompt injection (web content) | sanitize.py pipeline; UNTRUSTED_WEB_CONTENT delimiters; tripwire scan |
| SSRF | All HTTP targets hardcoded; no user-controlled URL fetching |
| Auth (web) | JWT HS256 with audience claim; sub on every DB query |
| Auth (desktop) | desktop_token (32 hex bytes) on every non-health request; first-message WS auth |
| Authorization | user_id enforced on conversation, execution, event queries |
| Rate limiting | Per-IP + per-user sliding window; concurrent execution cap |
| Input validation | Pydantic at all external boundaries; 1 MB body cap; 2000-char question max |
| Error handling | Generic 500 + 422; exc_info server-side only |
| TLS | HTTPS in production; HSTS header set |
| Event sanitization | _FORBIDDEN_KEYS blocklist; _FORBIDDEN_SUFFIXES; 2000-char value cap |
| Key wipe | key_store.clear() in success, cancel, and error paths |

---

## 5. Gaps with File and Line References

### GAP-1 (S5): No rate limit on auth endpoints
File: src/api/auth.py lines 18, 48
Risk: Brute-force passwords; signup flooding to burn quota.
Fix applied: Added rate_limiter("login", 10, 60) and rate_limiter("signup", 5, 60) dependencies.

### GAP-2 (I3): JWT in WebSocket query string
File: src/api/executions.py lines 356-367
Risk: Token captured in reverse proxy/CDN access logs.
Fix applied: Web-mode WS now uses first-message auth (same pattern as desktop mode).

### GAP-3 (E1): dev-mode auth bypass not gated on app_env
File: src/core/security.py lines 87-88
Risk: Accidental APP_MODE=dev in production skips all JWT auth.
Fix applied: Added production guard -- raises RuntimeError if app_mode=dev AND app_env=production.

### GAP-4 (I4): JWT secret dual-used as quota HMAC salt
File: src/providers/quota.py line 57
Risk: Dual-use of critical signing secret weakens key separation.
Fix applied: Added quota_salt config field; startup warning if not set in production.

### GAP-5 (D6): No WebSocket connection limit per execution
File: src/api/executions.py lines 388-392
Risk: WS connection exhaustion per execution (file descriptor and memory DoS).
Fix applied: Cap at MAX_WS_CONNECTIONS_PER_EXEC = 20; 503 returned for excess.

### GAP-6 (E4): shell:default in Tauri capability
File: desktop/src-tauri/capabilities/default.json line 11
Risk: JS in webview can run arbitrary OS commands via Tauri shell plugin.
Fix applied: Replaced shell:default with shell:allow-open (URL opening only).

### GAP-7 (T5): No injection scan on user question
File: src/api/executions.py lines 116-126
Risk: Attacker embeds prompt instructions in question.
Fix applied: scan_for_injection() called at submission; flags logged as warnings.

### GAP-8 (I7): Live API keys in OneDrive-synced .env -- CRITICAL -- MANUAL ACTION REQUIRED
File: .env lines 38-54
Exposed: CEREBRAS_API_KEY, OPENROUTER_API_KEY, HUGGINGFACE_API_KEY, TAVILY_API_KEY
Risk: Keys not committed to git (verified via git log) but .env is in a OneDrive-synced
      folder. Microsoft OneDrive may have already uploaded these to cloud storage.
Fix -- cannot be automated:
  1. Rotate all four keys immediately at their provider dashboards.
  2. Move the project folder outside OneDrive OR add it to OneDrive selective-sync exclusions.
  3. For dev keys, consider using Windows Credential Manager (APP_MODE=desktop) instead of .env.

### GAP-9 (I7): Weak default JWT secret
File: .env line 21, .env.example line 27
Risk: change-me-to-a-random-secret-key-at-least-32-chars is the literal .env value.
      If deployed as-is, anyone knowing this string can forge JWTs for any user.
Fix applied: Startup check refuses web+production mode when JWT_SECRET_KEY matches placeholder.

---

## 6. Accepted Risks

| ID | Risk | Rationale |
|---|---|---|
| AR-1 | Rate-limiter state lost on restart | No Redis in MVP; in-memory only. Render restarts infrequent. |
| AR-2 | No WORM/signed audit log | Not required for MVP; full DB row per execution suffices. |
| AR-3 | Prompt injection via novel paraphrases | Tripwire only; model instruction following is defense-in-depth. |
| AR-4 | SQLite desktop DB readable by local admin | OS ACL assumed; multi-user desktop not in MVP scope. |
| AR-5 | Desktop token printed to stdout | Tauri controls child stdout; single-user desktop; low risk. |
| AR-6 | No CSP on FastAPI JSON responses | FastAPI serves JSON only; Vercel sets CSP for HTML. |
| AR-7 | opener:default Tauri capability | Intentional for opening result links in default browser; user-gated. |
| AR-8 | No SQLite encryption on desktop | Windows DPAPI protects keys; conversation text less sensitive. |

---

## 7. Dependency Risk Notes

| Package | Constraint | Risk |
|---|---|---|
| python-jose[cryptography] | >=3.3.0 | Community-maintained; slow releases. Consider migrating to PyJWT. |
| passlib[bcrypt] | >=1.7.4 | passlib is unmaintained (last release 2023). Consider bcrypt directly or argon2-cffi. |
| google-generativeai | >=0.8.0 | No upper bound; breaking 0.x change could auto-install. Pin to minor version. |
| psycopg2-binary | >=2.9.0 | Binary wheel supply-chain risk. Consider psycopg[binary] (psycopg3). |
| aiohttp | >=3.9.0 | Not used in codebase (httpx used instead). Remove to reduce surface area. |

---

Generated: 2026-10-09. Scope: key exposure, prompt injection, SSRF, WebSocket auth, desktop token, dependency risks.
