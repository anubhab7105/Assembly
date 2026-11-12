# Assembly — Windows Release Guide

This document outlines the prerequisites, build instructions, and expected behaviors for the Assembly Windows Desktop application. It also includes a test checklist for verifying builds on a clean Windows VM.

## Prerequisites

- **WebView2**: Required for the Tauri frontend to run. Windows 10/11 typically comes with WebView2 pre-installed, but the Tauri MSI installer will automatically bootstrap and install it if it is missing.
- **Node.js & npm**: Required to build the frontend and Tauri app.
- **Rust (Cargo)**: Required to compile the Tauri shell.
- **Python 3.11+ & PyInstaller**: Required to compile the Python backend sidecar.

## Build Commands

To build the MSI installer, open a terminal in the `desktop/` directory and run:

```bash
npm install
npm run build
```

This command will:
1. Compile the Python backend into a single executable (`assembly_backend.exe`) using PyInstaller.
2. Copy the executable into `desktop/src-tauri/binaries/backend-x86_64-pc-windows-msvc.exe`.
3. Copy the frontend assets to a location that Vite can serve.
4. Run `tauri build` to compile the Rust binary, bundle the sidecar, and produce an MSI installer inside `desktop/src-tauri/target/release/bundle/msi/`.

## Application Data and Logs

- **Data Directory**: The application data, including the `assembly.db` SQLite database (which stores conversation history and execution records), is located at:
  `%LOCALAPPDATA%\Assembly\Assembly\assembly.db`
  *(e.g., `C:\Users\<username>\AppData\Local\Assembly\Assembly\assembly.db`)*
- **API Keys**: The backend contains a Windows Credential Manager adapter (`src/core/keystore.py`), but the current Settings save/test flow stores keys in the embedded WebView browser vault (IndexedDB with a localStorage fallback) and sends them to the local backend over loopback. Those browser values are not encrypted at rest. Do not claim Settings keys are in Windows Credential Manager until the UI save path is integrated with the adapter and verified on a clean Windows VM.
- **Logs**:
  - The Python sidecar logs its output to standard output (`stdout`). 
  - If the backend fails to start, the splash screen will capture the logs and provide a "Show Logs" link for debugging.
  - For normal runtime logs, launch the application executable (`tauri-app.exe`) from a command prompt to view the streamed structured logs.

## Uninstall Behavior

When uninstalling the application via "Add or Remove Programs":
- **Application Files**: The installed binaries and frontend assets in `C:\Program Files\tauri-app` will be removed.
- **History & Data**: The `assembly.db` file in `%LOCALAPPDATA%\Assembly\Assembly\` is **retained** by default. Reinstalling the app will restore your history.
- **API Keys**: Keys saved through the current Settings UI are held in the WebView browser profile. Remove them in Settings or clear the WebView site data. Credential Manager entries should only be expected for keys explicitly written through the keyring integration.

## SmartScreen and Code Signing

By default, the produced MSI installer is unsigned. When a user runs it, they will encounter a **Windows Defender SmartScreen** warning (a blue screen stating "Windows protected your PC"). 
- **To proceed (Unsigned)**: Users must click **"More info"**, and then click **"Run anyway"**.

### Options for Code Signing
To eliminate the SmartScreen warning, the binary and MSI must be signed using a code signing certificate:
1. **Standard OV (Organization Validation) Certificate**: Removes the warning over time as the application builds "reputation" with Microsoft.
2. **EV (Extended Validation) Certificate**: Instantly provides reputation and eliminates the SmartScreen warning immediately upon signing. Requires a hardware token or cloud HSM.
3. **Azure Trusted Signing**: Microsoft's cloud-based signing service that provides instant SmartScreen reputation without hardware tokens. Requires an Azure subscription. 

To sign the Tauri build, you can set the `TAURI_SIGN_CMD` environment variable or configure signing in `tauri.conf.json`.

---

## Testing Checklist (Clean Windows VM)

Use this checklist to verify a release build on a clean Windows VM:

- [ ] **Install**: Copy the generated `.msi` file to the VM. Run the installer. Acknowledge the SmartScreen prompt (More info -> Run anyway). Confirm the installation finishes successfully.
- [ ] **Launch**: Open the application from the Start Menu. Verify the splash screen appears, connects to the backend, and loads the main frontend UI.
- [ ] **Add Keys**: Enter disposable test keys in Settings. Verify the current flow stores them in the WebView browser vault and sends key-test/run payloads only to the local backend over loopback. Do not expect Credential Manager entries until the Settings/keyring integration is completed.
- [ ] **Run Execution**: Start a conversation that triggers a multi-agent execution (ensure it takes ~3 minutes to complete). Verify that the agents can communicate, debate, and resolve the final consensus.
- [ ] **Restart**: Close the application window completely. Reopen it from the Start Menu to ensure the backend starts up correctly a second time.
- [ ] **History Persists**: After restarting, verify that the previous conversation and its 3-minute execution result are fully loaded from the local database.
- [ ] **Remove test keys**: Before uninstalling, open Settings and remove the disposable API keys created for this test.
- [ ] **Uninstall**: Close the application. Go to "Add or Remove Programs" and uninstall the application. Verify the installation folder is removed.
- [ ] *(Optional post-uninstall cleanup)*: Clear WebView site data separately if the WebView profile remains after uninstall. Inspect Windows Credential Manager separately only when testing code paths that explicitly use the keyring adapter. Delete `%LOCALAPPDATA%\Assembly` to wipe local history.
