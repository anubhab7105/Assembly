# Privacy — what the server sees and stores

> Single source for the consent wording: `frontend/src/lib/privacy-notice.ts`
> (`WEB_PRIVACY_PARAGRAPHS` / `DESKTOP_PRIVACY_PARAGRAPHS`). The paragraphs
> below match the blocking first-run dialog exactly.

## Web mode consent text (blocking dialog, version 2)

Assembly web mode sends your question, API keys and model choices to the Assembly backend over HTTPS. The backend uses submitted API keys only for the key-test or run request and does not persist them.

Saved web API keys stay in this browser across refreshes. They are stored in IndexedDB with a localStorage fallback until you remove them in Settings or clear browser/site data. Browser storage is not an OS-protected credential vault; protect access to your browser profile and device.

Server logs contain metadata only (run id, tier, timings, counts). Never your questions, answers or keys.

Your history and settings stay in this browser (IndexedDB). Nothing is stored on the server.

Each model provider handles your inputs under its own policy:

- gemini: Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.
- all other providers: Check this provider's terms for how free-tier inputs are handled.

Avoid sending sensitive or confidential information.

The desktop app keeps keys in the Windows Credential Manager and sends requests straight from your PC. Keys never leave your machine except to authenticate with the provider.

## Desktop mode consent text (shorter, no server wording)

Assembly desktop mode runs entirely on your PC.

Your history and settings stay in this browser (IndexedDB).

Each model provider handles your inputs under its own policy:

- gemini: Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.
- all other providers: Check this provider's terms for how free-tier inputs are handled.

Avoid sending sensitive or confidential information.

Keys are kept in the Windows Credential Manager and requests go straight from your PC. Keys never leave your machine except to authenticate with the provider.

## Acknowledgment storage

The dialog requires an explicit "I understand" button. The browser stores
`{version, acknowledged_at}` under `privacy_notice_ack` via `StorageService`
(IndexedDB in web, `DesktopStorage` on desktop). A run cannot start until the
stored version equals `PRIVACY_NOTICE_VERSION`; bumping the version re-prompts.
Settings → Privacy repeats the same text with a "Review again" link. The
acknowledgment record never contains keys, questions or answers.

## Storage implementation details (not consent copy)

The descriptions above explain the user-facing privacy notice. Implementation details:

- In web mode, saved provider keys are client-owned IndexedDB records with a localStorage fallback and survive refreshes. Users can remove a provider key or clear all keys in Settings; clearing site/browser data also removes them. Browser storage is not an OS-protected credential vault, so browser-profile/device access should be protected. When a key is submitted for a provider test or run, the backend uses it transiently and does not persist or log the key value. History/settings/usage remain client-owned; storage failure must not be reported as a successful save or deletion.
- Browser storage is not cross-device backup. Export history JSON from Settings before clearing site data or moving to another browser profile. Import accepts the versioned Assembly export envelope; malformed rows are skipped and unsupported payload shapes are rejected.
- In the Windows desktop mode, backend execution records are kept in the app's local SQLite database, and provider keys are held by the OS credential manager via the keyring abstraction. Browser-side UI settings/history can remain in the embedded WebView's storage. Those stores are distinct: SQLite is not a provider-key store.
- Automated keyring tests use an in-memory fake and prove that canary keys do not appear in database rows, logs, or API responses. They do not prove a packaged Windows build or a real Windows Credential Manager installation works; those require a Windows smoke test.

## File attachments

When using attachments, text contents are sent to the Assembly backend for the active run and may be included in requests to the selected AI providers. Provider-specific data-handling terms apply. The web backend handles the contents in memory and does not store them on server disk or in its database; upload contents must not be written to logs or run events. Browser history stores only sanitized filename/type/size metadata, not the file body. v1 accepts bounded UTF-8 text formats only; PDF/DOCX, images and OCR are not supported. Do not attach credentials or sensitive material unless you have reviewed the selected providers' policies.
