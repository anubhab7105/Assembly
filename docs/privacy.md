# Privacy — what the server sees and stores

> Single source for the consent wording: `frontend/src/lib/privacy-notice.ts`
> (`WEB_PRIVACY_PARAGRAPHS` / `DESKTOP_PRIVACY_PARAGRAPHS`). The paragraphs
> below match the blocking first-run dialog exactly.

## Web mode consent text (blocking dialog, version 3)

Assembly web mode sends your question, API keys and model choices to the hosted Assembly backend over HTTPS (localhost is used for local development). Submitted API keys are used for preflight, key-test or run requests and are not persisted by the Assembly application.

Saved web API keys stay in this browser across refreshes. They are stored as readable values (not encrypted at rest) in IndexedDB with a localStorage fallback until you remove them in Settings or clear browser/site data. Browser storage is not an OS-protected credential vault; same-origin JavaScript, including code injected through an XSS vulnerability, can read saved keys.

The Assembly application processes active request/run data in memory and does not write submitted web keys, questions or answers to its application database or disk. Its application logs record operational metadata (run id, tier, timings, counts and search-query lengths), not raw request bodies, search-query text or key values. Hosting providers may process network traffic and keep their own operational logs under their policies.

Your run history and settings stay in this browser (IndexedDB, with the documented localStorage fallback). The hosted application does not persist web run content or submitted API keys.

Each model provider handles your inputs under its own policy:

- gemini: Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.
- all other providers: Check this provider's terms for how free-tier inputs are handled.

Avoid sending sensitive or confidential information.


## Desktop mode consent text (shorter, no server wording)

Desktop mode uses an Assembly backend running locally on your PC. Its requests do not pass through the hosted Assembly web backend.

Desktop run history is stored locally in SQLite. UI settings and the current Settings key vault use the embedded WebView browser storage. Saved keys are readable values, not encrypted at rest; same-origin JavaScript, including injected code in an XSS incident, can read them.

Each model provider handles your inputs under its own policy:

- gemini: Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.
- all other providers: Check this provider's terms for how free-tier inputs are handled.

Avoid sending sensitive or confidential information.

The current Settings flow stores keys as readable values in the WebView browser profile (IndexedDB with a localStorage fallback; not encrypted at rest). Preflight, key tests and runs send them to the local backend over loopback, and that backend makes provider requests. The repository has a Windows Credential Manager adapter, but the current Settings save flow does not use it as the primary key store.

## Acknowledgment storage

The dialog requires an explicit "I understand" button. The browser stores
`{version, acknowledged_at}` under `privacy_notice_ack` via `StorageService`
(IndexedDB in web, `DesktopStorage` on desktop). A run cannot start until the
stored version equals `PRIVACY_NOTICE_VERSION`; bumping the version re-prompts.
Settings → Privacy repeats the same text with a "Review again" link. The
acknowledgment record never contains keys, questions or answers.

## Storage implementation details (not consent copy)

The descriptions above explain the user-facing privacy notice. Implementation details:

- In hosted web mode, saved provider keys are readable IndexedDB records with a localStorage fallback; they are not encrypted at rest or protected by an OS credential vault. Same-origin JavaScript (including injected script in an XSS incident) can read them. Users can remove keys in Settings or clear site/browser data. Preflight, key-test and run requests send relevant keys to the Assembly backend over HTTPS; request handlers use them transiently and do not write them to the Assembly application database or disk. Application logging is metadata-focused and the key-masking filter scrubs key-like values. Hosting platforms can still handle network traffic and keep separate operational logs under their own policies. History/settings/usage remain client-owned; storage failure must not be reported as a successful save or deletion.
- Browser storage is not cross-device backup. Export history JSON from Settings before clearing site data or moving to another browser profile. Import accepts the versioned Assembly export envelope; malformed rows are skipped and unsupported payload shapes are rejected.
- In Windows desktop mode, execution records are kept in the app's local SQLite database. The current Settings UI still saves provider keys to the embedded WebView's IndexedDB/localStorage vault and sends them to the local backend over loopback for tests/runs. A Windows Credential Manager adapter exists in `src/core/keystore.py`, but the current Settings save/test path does not use it as the primary store; do not describe keys entered through Settings as Credential Manager-only. The local SQLite execution records are separate from the browser key vault.
- Automated keyring tests use an in-memory fake and prove that canary keys do not appear in database rows, logs, or API responses. They do not prove a packaged Windows build or a real Windows Credential Manager installation works; those require a Windows smoke test.

## File attachments

When using attachments, text contents are sent to the Assembly backend for the active run and may be included in requests to the selected AI providers. Provider-specific data-handling terms apply. The web backend handles the contents in memory and does not store them on server disk or in its database; upload contents must not be written to logs or run events. Browser history stores only sanitized filename/type/size metadata, not the file body. v1 accepts bounded UTF-8 text formats only; PDF/DOCX, images and OCR are not supported. Do not attach credentials or sensitive material unless you have reviewed the selected providers' policies.
