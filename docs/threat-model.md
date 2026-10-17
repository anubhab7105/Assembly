# Assembly threat model

**Status:** Maintained security overview  
**Last reviewed:** 2026-10-17  
**Scope:** Web deployment, local development, and the Windows Tauri desktop application

This document describes the main assets, trust boundaries, mitigations, and remaining risks in the current architecture. It is a practical threat model, not a penetration-test report or a guarantee that every control has been independently verified. When implementation and this document disagree, inspect the current code and update this model with the change.

Start with the [architecture guide](architecture.md), [privacy notes](privacy.md), and [prompt-injection defense](security.md).

## 1. Security goals and assets

| Asset | Where it lives | Primary security goal |
|---|---|---|
| Provider API keys | Browser KeyVault storage when saved by the user; transient request memory on the web backend; Windows Credential Manager in desktop mode | Prevent disclosure in transit, logs, errors, files, and database records |
| Questions, answers, and research results | Browser history; active web run memory; local desktop history database | Avoid unintended server-side persistence and explain where user data is retained |
| Attachment text | Browser-selected file and the active run request/context | Bound its size, treat it as untrusted input, and avoid logging or persisting the body on the server |
| Run events and temporary orchestration state | Active backend process memory; browser UI | Prevent cross-run confusion and avoid exposing secrets through events |
| Local desktop history | SQLite under the user's application-data directory | Keep it local and be clear that it is not a provider-key store or an encrypted vault |
| Runtime configuration and deployment secrets | Deployment environment and developer-controlled local configuration | Keep secrets out of source control and require explicit production settings |
| Integrity of answers and citations | Model responses plus selected research sources | Make uncertainty visible; do not imply that consensus proves truth |

## 2. Modes and trust boundaries

### Web mode

1. The browser UI communicates with the FastAPI service over HTTPS in production.
2. Provider keys, questions, and supported attachment text are sent to the backend when needed for a run or provider check.
3. The web backend keeps run inputs and orchestration state in memory for the active request. It is designed not to persist questions, answers, attachments, or provider keys to a server database or disk.
4. Relevant prompt content is sent to external model and search providers. Their terms, retention practices, and training policies are separate trust boundaries.
5. The browser may retain history, settings, usage metadata, and saved provider-key configuration in IndexedDB, with localStorage fallback in relevant storage modules. Browser data is sensitive and can be available to same-origin script executing in that profile.

### Windows desktop mode

1. The Tauri WebView communicates with the local Python sidecar over loopback.
2. A per-launch local token is used to protect sidecar requests; it is not an account system or a substitute for OS-level security.
3. Conversation and execution records may be stored in local SQLite. Browser-side UI state may also live in the embedded WebView's browser storage.
4. Provider keys are accessed through the OS credential-store abstraction, using Windows Credential Manager on Windows. Keys should not be copied into SQLite, ordinary files, URLs, logs, or API responses.
5. The sidecar sends the necessary prompt content to the user's selected external providers.

### Local development

Development configuration can expose different endpoints and may use environment-based keys. Developers must use their own test credentials, keep local .env files out of Git, and avoid putting secrets or private data in logs, fixtures, issues, or screenshots.

## 3. Threats and controls

| ID | Threat | Current mitigations | Remaining concern |
|---|---|---|---|
| T1 | Provider key disclosure through logs or error responses | Keys are wrapped with SecretStr in backend key stores; key-masking filters scrub log records; run failures use sanitized codes/messages; web request keys are cleared after execution | Masking is defense in depth, not proof that every future log or dependency is safe; test new paths with canary keys |
| T2 | Provider key theft from a browser profile | Browser key storage is client-side; HTTPS protects transit; access to keys is limited to the web request path | Saved browser keys remain sensitive same-origin data and may be exposed by a compromised device, browser profile, extension, or same-origin script |
| T3 | Accidental server persistence of web inputs | Web mode is configured to avoid database initialization and server-side disk persistence; run registry and request key store are in memory | Verify logging, tracing, crash reporting, reverse proxies, hosting configuration, and future middleware before adding observability features |
| T4 | Prompt injection through search results or attachments | External text is treated as untrusted evidence; sanitization, delimiters, size limits, and pattern-based tripwires reduce common attack paths | Pattern detection can be bypassed; models may still follow hostile content. Never treat a scan as a safety guarantee |
| T5 | Malicious attachment or oversized request | Server-side validation is authoritative; supported inputs are bounded by file count, per-file/combined byte limits, and prompt-context limits | Supported v1 attachments are UTF-8 text only. Do not enable binary formats, parsing, or OCR without new validation and threat review |
| T6 | Denial of service through repeated runs or long execution | Per-IP rate limits, invalid-request limits, global and per-IP concurrency caps, a run TTL, time budgeting, and provider quota handling | Current rate-limit and concurrency counters are in-process; restarts reset state and multiple workers do not share these counters |
| T7 | Unexpected external provider behavior or data retention | Provider integrations use explicit API calls and sanitized failure messages; privacy notice warns that provider policies apply | Prompt content necessarily leaves the user's device when sent to providers; users must review the relevant provider's terms before sharing sensitive information |
| T8 | Unauthorized access to the local desktop sidecar | Loopback communication and a per-launch token reduce access by unrelated local processes; Tauri permissions are narrower than broad shell access | A compromised user account or local malware can bypass many application-level protections; local token auth is not protection against a hostile machine owner |
| T9 | Exposure of desktop history | SQLite is local under the user's application-data directory; provider keys are kept in the OS credential store rather than SQLite | Local history is not documented as encrypted. A user with sufficient local account or administrator access may be able to read it |
| T10 | Spoofed frontend origin or unsafe cross-origin requests | Production requires an explicit CORS allow-list; production API documentation endpoints are disabled | CORS is not authentication. Keep deployment origins exact and test hosting/proxy behavior whenever domains change |
| T11 | Dependency, build, or release compromise | Dependency checks and CI are part of the contributor workflow; desktop builds use an explicit Tauri capability file | CI does not prove a packaged release is safe. Review dependency alerts, permissions, sidecar artifacts, and clean-Windows smoke tests |
| T12 | False confidence from consensus or fabricated citations | Consensus is described as a heuristic; source/evidence checks and uncertainty notes are part of the workflow | Several models can share the same blind spots; sources can be irrelevant or misrepresented. Independently verify important claims |

## 4. Security invariants for contributors

- Never persist provider keys in server databases, SQLite history, ordinary files, URLs, events, or logs.
- Never log raw questions, answers, attachment bodies, provider request bodies, or raw provider exception messages.
- Keep provider IDs, supported models, and quota metadata in the model catalog rather than duplicating them through application code.
- Treat search results, uploaded text, imported history, and model responses as untrusted input.
- Apply validation and limits on the server, even when equivalent frontend checks exist.
- Keep production CORS configuration explicit; do not introduce wildcard credentialed CORS.
- Do not add accounts, server-side user records, analytics, or persistent web storage without updating the architecture, privacy notice, tests, and this model.
- Update the threat model when the storage model, key flow, API boundary, Tauri capabilities, attachment support, or deployment topology changes.

## 5. Verification and incident handling

Normal tests should use mock or replay providers and synthetic credentials. Add regression tests for secret masking, error paths, attachment validation, prompt-injection handling, rate limits, and data-retention boundaries when changing those areas. Live provider calls and clean-Windows installer checks require separate, explicitly reported verification.

For suspected credential exposure, revoke or rotate the affected credential with its provider, remove it from the unsafe location, and check logs and history for other exposure paths. Do not post suspected vulnerabilities or live secrets in public issues; follow the repository's [security policy](../SECURITY.md).

## 6. Supporting implementation references

- [Web run lifecycle and in-memory registry](../src/api/run.py)
- [Request/desktop key-store backends](../src/core/keystore.py)
- [Key masking and logging](../src/core/logging_config.py)
- [Rate limits and concurrency caps](../src/core/rate_limit.py)
- [Attachment handling](../src/research/attachments.py)
- [Untrusted research-content sanitization](../src/research/sanitize.py)
- [Desktop capability configuration](../desktop/src-tauri/capabilities/default.json)
- [Architecture guide](architecture.md)
- [Privacy guide](privacy.md)
