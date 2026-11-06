# Assembly Desktop (Tauri shell)

The desktop application is a Tauri v2 shell that launches a local FastAPI
backend as a sidecar process, supervises its lifecycle, and provides OS
keyring storage for provider API keys. The web frontend (`frontend/`, Next.js)
is bundled inside the Tauri bundle and talks to the backend over loopback.

## Architecture

```
Tauri shell (Rust)  <-->  IPC commands  <-->  Backend sidecar (FastAPI, Python)
       |                                               |
  OS keyring                                  local SQLite (desktop mode)
  (Windows Credential Manager)                + loopback HTTP (127.0.0.1)
```

- The Rust shell owns the backend process: it spawns it, waits for readiness,
  forwards the port + per-launch token to the frontend, and shuts it down on
  exit.
- The frontend never spawns or shells out to the backend; all interaction goes
  through typed Tauri commands.
- Provider API keys are held in the OS keyring (Windows Credential Manager on
  Windows), never in localStorage/IndexedDB/sessionSQLite, never logged, never
  returned raw to the webview unless explicitly requested.

## Dev vs packaged launch

### Packaged (release)
1. `desktop/package.json` `build:backend` builds the FastAPI backend with
   PyInstaller (`assembly_backend.spec`) into `dist/assembly_backend.exe`.
2. The executable is copied to
   `desktop/src-tauri/binaries/backend-<target-triple>.exe` (e.g.
   `backend-x86_64-pc-windows-msvc.exe`) and listed in `tauri.conf.json`
   `externalBin` as `binaries/backend`.
3. `tauri build` bundles the sidecar and produces the MSI installer.

### Dev (`tauri dev`)
The sidecar resolves a dev path and launches
`python <cwd>/src/main.py` with `APP_MODE=desktop`. The backend binds loopback
and prints `ASSEMMBLY_PORT=` / `ASSEMMBLY_TOKEN=` to stdout, which the sidecar
reads to determine the endpoint. No PyInstaller build is required.

The sidecar picks a free loopback port (`127.0.0.1` only, never a fixed port)
and passes it to the backend via `ASSEMMBLY_PORT`. A per-launch random token is
passed via `ASSEMMBLY_TOKEN`; the frontend must send it as a `Bearer` token on
every backend request so other local processes cannot call the API.

## IPC contract

Commands are defined in `desktop/src-tauri/src/lib.rs` and mirrored in
TypeScript in `desktop/src/ipc.ts`. Keep the two in sync.

| Command | Purpose |
|---------|---------|
| `start_backend` | Spawn (or ensure) the backend and wait for readiness. Returns `BackendStatus`. |
| `get_backend_status` | Current supervisor status (state, endpoint, restarts, pid). |
| `get_backend_endpoint` | Backend base URL + per-launch auth token (only in `Ready`). |
| `restart_backend` | Restart the backend sidecar. |
| `stop_backend` | Graceful shutdown, then kill after timeout. |
| `get_backend_logs` | Redacted captured stdout/stderr lines. |
| `save_provider_key(provider, key)` | Store a provider key in the OS keyring. |
| `has_provider_key(provider)` | Check whether a provider key is stored. |
| `delete_provider_key(provider)` | Delete one provider key from the keyring. |
| `read_provider_key(provider)` | Controlled read of one key (desktop key-setup flow only). |

Every input is validated: provider names are an allowlist
(`gemini`, `groq`, `cerebras`, `openrouter`, `huggingface`), keys are length-
bounded, and no shell strings or arbitrary paths are accepted. Errors are
typed (`CommandError` with `code` + `message`), never raw strings or panics.
No `shell` plugin permission is granted; the sidecar is spawned directly with
`std::process::Command` (no shell).

### Backend state machine

`Starting | Ready | Failed | Crashed | Stopping | Stopped`, modeled explicitly
and published via `get_backend_status`. Transitions are tested
(`desktop/src-tauri/src/sidecar.rs` unit tests).

## Keyring

- Backed by the Rust `keyring` crate behind a `KeyRing` trait, so tests use an
  in-memory backend (`MemoryKeyring`) instead of the OS keyring.
- Stable service name: `Assembly` (matches `src/core/keystore.py` and the
  product identity from issue #92).
- On Windows this is the Windows Credential Manager.
- Production injects keys into backend requests from Rust; the webview normally
  never receives a raw key. `read_provider_key` exists only for the key-setup
  flow and is minimal.
- Keyring-unavailable errors surface a clear user-facing message.

## Crash / shutdown policy

- **Crash policy:** limited restart with backoff (1s, 2s, 4s), up to
  `MAX_RESTARTS = 3` attempts. After exhaustion the supervisor reports
  `Failed` and stops restarting. This is tested
  (`crash_restarts_then_fails`).
- **Readiness:** the supervisor polls `GET /health` (127.0.0.1 only) with a
  30s timeout and backoff. If the backend exits before becoming ready, the
  supervisor detects the crash immediately rather than waiting the full timeout
  (readiness-timeout test).
- **Shutdown:** a graceful `POST /shutdown` request is sent first; if the
  backend does not exit within 5s it is killed. On Windows, a Job Object
  (`cfg(windows)`) ensures no orphan backend process survives even if the
  shell is killed. Stale processes from prior crashed runs are reaped/killed
  before a new spawn.
- **No orphan processes:** verified by integration test (`spawn_ready_shutdown_no_orphan`
  asserts the backend PID is gone after shutdown).

## Verification status

- Rust unit + integration tests for the sidecar pass (`cargo test` in
  `desktop/src-tauri`). They exercise path resolution, state transitions, log
  redaction/token generation, spawn → readiness → shutdown (no orphan), crash
  restart-then-fail, and readiness timeout.
- The full Tauri crate could not be compiled in this environment (missing
  system `libdbus` for the Tauri GUI dependencies on Linux), so `cargo check`
  on `desktop/src-tauri` and the Windows Job Object / keyring runtime behavior
  remain to be verified on a Windows machine. The Rust supervision core is
  `std`-only and fully tested independently.
- A clean-VM Windows smoke checklist lives in `docs/windows-release.md`.
