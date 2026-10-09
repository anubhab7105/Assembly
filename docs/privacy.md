# Privacy — what the server sees and stores

This is the exact privacy contract for Assembly's stateless web mode
(`APP_MODE=web`) and the local desktop mode (`APP_MODE=desktop`).

## Web mode (`APP_MODE=web`)

**The server stores nothing.** No accounts, no database file, no disk
writes. Each run lives in an in-memory registry with a TTL and a global
concurrency cap, and is forgotten when it finishes or expires.

What the server transiently sees during `POST /api/run` (memory only):

- The question text (to run the team; never written to disk or logs —
  logs carry the question length only).
- The provider keys you send (`provider_keys`; held in memory for that
  run only, wiped in a `finally` path, never logged, never returned).
- The model selection and usage snapshot you send (to plan capacity;
  counts only, never keys).
- The generated answer and sources (streamed back to you as SSE events;
  never stored).

What the server logs (metadata only):

- Run id prefix, requested tier, model-selection size (`auto` or count),
  timings, capacity verdicts, and error classes. No question text, no
  keys, no answers. The key-masking log filter still scrubs anything
  resembling a secret.

Abuse protection without accounts: per-IP rate limits, request size
limit, max question length (2000 chars), SSE origin check, and a CORS
allow-list. No fingerprinting, no cookies, no tracking.

## Desktop mode (`APP_MODE=desktop`)

Everything stays on your machine: run history in a local SQLite file
under your OS data directory, provider keys in the OS credential
manager (Windows Credential Manager via `keyring`), never in plain
files or `.env`. No data leaves the device except provider API calls
made with your own keys.

## Browser storage (both modes)

History, settings, and daily usage counters live in your browser
(IndexedDB) via the `StorageService` interface — never on our server.
"Remember on this device" encrypts keys with WebCrypto AES-GCM under a
key derived from YOUR passphrase via PBKDF2 (210,000 iterations); the
passphrase is never stored. History Export/Import is a JSON file you
control.

## What we will never do

- Store, log, or return your provider keys (only provider/model names).
- Store questions or answers server-side in web mode.
- Require an account, email, or password for any feature.
