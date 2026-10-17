# Assembly — Windows release guide

This guide covers building and verifying the Tauri 2 Windows desktop application. A successful frontend build is not the same as a successfully packaged or smoke-tested Windows installer.

## Prerequisites

Build on a Windows 10/11 machine with:

- Python 3.11 or newer
- Node.js 20 or newer and npm
- Rust stable toolchain with Cargo
- WebView2 runtime
- The Python build dependencies installed from `requirements-dev.txt`

Use a clean working tree and do not build releases with real user data or production API keys in the checkout.

## Prepare the Python environment

From the repository root, create/activate the virtual environment and install the build dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If your project setup requires local environment configuration, copy `.env.example` to `.env` and set a unique local `QUOTA_SALT`. Never commit the local `.env` file or real provider credentials.

## Build the installer

From `desktop/`:

```powershell
npm install
npm run tauri -- build
```

The configured Tauri build hook calls the desktop package build, which builds the Python sidecar, copies the shared frontend assets, runs TypeScript compilation, builds the Vite shell, and invokes Tauri's bundler. The Windows installer is normally emitted under:

```text
desktop/src-tauri/target/release/bundle/msi/
```

The exact output depends on Tauri configuration and the selected bundle targets. Review `desktop/src-tauri/tauri.conf.json` before changing product identity, bundle targets, icons, Content Security Policy, or frontend build commands.

For local iteration, launch the Tauri development shell from `desktop/` with `npm run tauri -- dev`.

## Data and credentials

- **Web mode:** designed not to create a server database or persist run content to server disk.
- **Desktop/dev mode:** may use local SQLite for execution history. The effective database path comes from the application configuration; do not assume it is portable between environments.
- **Provider keys:** desktop mode should use the OS credential-store integration (Windows Credential Manager on Windows). Keys must not be written into SQLite, ordinary files, URLs, logs, screenshots, or release artifacts.
- **Browser-side state:** settings/history in the embedded WebView may use browser storage and are distinct from SQLite.
- **Provider requests:** questions, attachment text, and other necessary prompt context are sent to the providers chosen for the run. Their data-handling policies still apply.

See [privacy documentation](privacy.md) for the detailed user-facing data-flow explanation.

## Clean-Windows smoke-test checklist

Run this checklist on a clean Windows VM or machine that does not depend on your development checkout. Record actual results; do not mark environment-dependent steps as passed without testing.

- [ ] **Install:** Run the generated installer and confirm installation completes.
- [ ] **Launch:** Open Assembly from the installed location and verify the WebView UI loads and the local backend becomes ready.
- [ ] **Key storage:** Add a test provider key and verify it is stored through Windows Credential Manager, not in SQLite or plain files.
- [ ] **Execution:** Run a small investigation with a valid test key and check progress, completion/failure messages, and source/uncertainty rendering.
- [ ] **Provider error path:** Test an invalid or exhausted test key and confirm the app provides a safe, actionable message without exposing credentials.
- [ ] **Restart:** Close and relaunch the application; verify backend startup and UI readiness.
- [ ] **Local history:** Confirm expected history persistence across restart, if enabled for the selected mode.
- [ ] **Uninstall:** Uninstall through Windows settings and check the actual behavior of app files, local history, and credential-store entries. Do not assume user data or credentials are removed automatically.
- [ ] **Clean installation:** Confirm the build works without access to the source checkout, developer environment variables, or build-only assets.

## Signing and release hygiene

Unsigned Windows installers may trigger Microsoft Defender SmartScreen warnings. Do not instruct users to ignore security warnings without providing trustworthy release provenance. Before distributing a release, consider code signing, publish checksums, link to the source commit, and document known limitations.

Review Tauri permissions in `desktop/src-tauri/capabilities/` and keep them minimal. Do not bundle local databases, logs, cached run data, or real provider keys. Keep generated sidecar/installer output out of Git unless the release process explicitly calls for a published artifact.
