# Privacy — what the server sees and stores

> Single source for the consent wording: `frontend/src/lib/privacy-notice.ts`
> (`WEB_PRIVACY_PARAGRAPHS` / `DESKTOP_PRIVACY_PARAGRAPHS`). The paragraphs
> below match the blocking first-run dialog exactly.

## Web mode consent text (blocking dialog, version 1)

Assembly web mode processes your question, API keys and model choices in memory for the duration of one run and stores nothing on the server.

Server logs contain metadata only (run id, tier, timings, counts) — never your questions, answers or keys.

Your history and settings stay in this browser (IndexedDB). Nothing is stored on the server.

Each model provider handles your inputs under its own policy:

- gemini: Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.
- all other providers: Check this provider's terms for how free-tier inputs are handled.

Avoid sending sensitive or confidential information.

The desktop app keeps keys in the Windows Credential Manager and sends requests straight from your PC — keys never leave your machine except to authenticate with the provider.

## Desktop mode consent text (shorter, no server wording)

Assembly desktop mode runs entirely on your PC.

Your history and settings stay in this browser (IndexedDB).

Each model provider handles your inputs under its own policy:

- gemini: Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.
- all other providers: Check this provider's terms for how free-tier inputs are handled.

Avoid sending sensitive or confidential information.

Keys are kept in the Windows Credential Manager and requests go straight from your PC — keys never leave your machine except to authenticate with the provider.

## Acknowledgment storage

The dialog requires an explicit "I understand" button. The browser stores
`{version, acknowledged_at}` under `privacy_notice_ack` via `StorageService`
(IndexedDB in web, `DesktopStorage` on desktop). A run cannot start until the
stored version equals `PRIVACY_NOTICE_VERSION`; bumping the version re-prompts.
Settings → Privacy repeats the same text with a "Review again" link. The
acknowledgment record never contains keys, questions or answers.
