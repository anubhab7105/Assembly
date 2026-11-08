# Assembly Desktop (Tauri + FastAPI backend sidecar)

Windows 10/11 x64 (`x86_64-pc-windows-msvc`) is the target platform.

## Stack
- Shell: Tauri v2 (Rust), `desktop/src-tauri/`.
- Backend: FastAPI (`src/main.py`), packaged as the sidecar with PyInstaller.
- Secrets: Windows Credential Manager (OS keyring) only — never browser storage, logs, SQLite, or plain files.

## Prerequisites
- Rust toolchain (stable) with the `x86_64-pc-windows-msvc` target.
- Python 3.11+ + `pyinstaller` (for the backend sidecar).
- Node.js + npm (for the Tauri frontend).

## Building

### 1. Backend sidecar (PyInstaller)
The backend is packaged into a one-file executable and copied into the Tauri
bundle so the shell can start it with no separate developer process:

```bash
# From the repo root
cd desktop
npm run build:backend
```

This runs `pyinstaller assembly_backend.spec` (repo root) and copies the output
to `desktop/src-tauri/binaries/backend-x86_64-pc-windows-msvc.exe`, matching
`externalBin` in `tauri.conf.json`.

The `assembly_backend.spec` bundles `models.yaml` and the Python dependencies
needed by `src.main`. Keep it reproducible: do not add non-free-tier or
paid-provider code paths.

### 2. Frontend + Tauri app
```bash
cd desktop
npm run prebuild     # builds backend + copies frontend assets
npm run tauri build  # produces the Windows installer in src-tauri/target/release/
```

`npm run tauri build` (or `cargo tauri build`) invokes the Rust build script
which embeds `tauri.conf.json` and compiles the sidecar manager, keyring, and
validated IPC commands.

## How it works
- On launch, the Tauri shell starts the backend sidecar itself (no developer
  process required). It picks a free loopback port (`127.0.0.1`), passes a
  per-launch auth token, and waits for `GET /health` to return 200 before
  marking the backend Ready.
- The sidecar runs in a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`,
  so the backend and its process tree die even if the shell crashes (no orphans).
- Provider credentials are stored in Windows Credential Manager via the `keyring`
  crate (`CredentialStore` trait; in-memory impl for tests).
- IPC is via explicit `#[tauri::command]` functions only:
  `backend_status`, `backend_restart`, `credential_save`, `credential_exists`,
  `credential_delete`, `credential_list`. No shell execution, no arbitrary file
  or URL access. Commands are restricted to the `main` window.

## Frontend
- `desktop/src/main.ts` is the Tauri dev entry (sidecar bootstrap).
- The Next.js frontend (`frontend/`) is copied into `desktop/public/` and
  served by Tauri. It detects Tauri vs. web at runtime and, in desktop mode,
  routes provider-key save/read/delete to the keyring commands instead of
  browser storage.

## Tests
- Rust pure logic (state machine, port picking, validation, in-memory keyring)
  runs on any host:
  ```bash
  cd desktop/src-tauri
  cargo test --no-default-features
  ```
- Windows CI job runs `cargo fmt --check`, `cargo clippy -D warnings`,
  `cargo test`, and the frontend tests on `windows-latest`.

## Security
- Credentials never leave the OS keyring. The webview never receives raw
  secrets; it asks Rust to start a run with a provider and Rust injects the
  key into the backend request.
- `tauri.conf.json` CSP `connect-src` is limited to loopback (`127.0.0.1:*`)
  for the backend plus `tauri:` for IPC.
- No `shell:allow-execute`-style broad permissions; only the named sidecar
  binary may be spawned.
