# Assembly desktop application

Assembly's Windows desktop shell uses [Tauri 2](https://tauri.app/) and a bundled Python backend sidecar. The application reuses the web frontend. Desktop/dev runs can store execution history in local SQLite; provider keys should use the OS credential-store integration, not the history database or ordinary files.

For the full Windows packaging and smoke-test checklist, see [`docs/windows-release.md`](../docs/windows-release.md). For the system design and data boundaries, see [`docs/architecture.md`](../docs/architecture.md) and [`docs/privacy.md`](../docs/privacy.md).

## Prerequisites

- Windows 10 or 11 for the supported Windows installer flow
- Node.js 20 or newer and npm
- Python 3.11 or newer
- Rust toolchain with Cargo
- The Python build/test dependencies from the repository's `requirements-dev.txt`
- WebView2 runtime (typically already installed on supported Windows systems)

## Install dependencies

From the repository root, create a virtual environment and install the development dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Then install the desktop JavaScript dependencies:

```powershell
cd desktop
npm install
```

## Run the Tauri development shell

From `desktop/`:

```powershell
npm run tauri -- dev
```

The configured pre-dev command starts Vite and prepares the shared frontend assets. For backend/API configuration, use the repository root README and the architecture documentation rather than treating the desktop shell as a separate web application.

## Build and package

From `desktop/` on a Windows build machine:

```powershell
npm run tauri -- build
```

The configured build hooks build the Python sidecar, copy frontend assets, and prepare the Tauri bundle. A successful frontend build alone is not proof that the packaged installer launches correctly. Use the clean-Windows verification checklist in [`docs/windows-release.md`](../docs/windows-release.md), including provider-key storage, a complete run, restart/history persistence, and uninstall behavior.

Build output and generated sidecar binaries should not be committed unless a release workflow explicitly requires them. Do not include real provider keys, private run data, or local databases in a release artifact.

## Before a release

- Verify the product/window/installer identity in `src-tauri/tauri.conf.json`; it is configuration, not a promise that branding is already final.
- Review the Tauri capabilities in `src-tauri/capabilities/`; grant only the permissions the app needs.
- Confirm provider keys are stored through the OS credential store and never written to SQLite, logs, URLs, or plain files.
- Run the installer on a clean Windows machine and record the actual result; do not mark environment-dependent checks as passed without running them.
