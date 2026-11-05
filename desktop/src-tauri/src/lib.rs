// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};
use std::thread;

use tauri::State;
use tauri_plugin_single_instance::SingleInstanceExt;

mod sidecar;
mod keyring;

use keyring::KeyRing;
use sidecar::{
    BackendState, BackendStatus, BinarySource, SidecarSupervisor,
};

/// Typed error returned by every IPC command. Never raw strings or panics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandError {
    pub code: String,
    pub message: String,
}

impl std::fmt::Display for CommandError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for CommandError {}

impl From<sidecar::StartError> for CommandError {
    fn from(e: sidecar::StartError) -> Self {
        CommandError { code: format!("{:?}", e.code), message: e.message }
    }
}

impl From<sidecar::ShutdownError> for CommandError {
    fn from(e: sidecar::ShutdownError) -> Self {
        CommandError { code: "shutdown_failed".into(), message: e.message }
    }
}

impl From<sidecar::RestartError> for CommandError {
    fn from(e: sidecar::RestartError) -> Self {
        CommandError { code: "restart_failed".into(), message: e.message }
    }
}

impl From<keyring::KeyRingError> for CommandError {
    fn from(e: keyring::KeyRingError) -> Self {
        CommandError { code: e.code, message: e.message }
    }
}

/// Tauri-managed state owning the backend sidecar supervisor.
pub struct BackendSupervisorState {
    inner: Mutex<Option<Arc<sidecar::SidecarSupervisor>>>,
}

impl Default for BackendSupervisorState {
    fn default() -> Self {
        Self { inner: Mutex::new(None) }
    }
}

// ── IPC commands ───────────────────────────────────────────────────────

/// Get the current backend status (state, endpoint, restarts, pid).
#[tauri::command]
fn get_backend_status(state: State<'_, BackendSupervisorState>) -> Result<BackendStatus, CommandError> {
    let slot = state.inner.lock().unwrap();
    match &*slot {
        Some(sup) => Ok(sup.status()),
        None => Ok(BackendStatus {
            state: BackendState::Stopped,
            restarts: 0,
            pid: None,
            endpoint: None,
        }),
    }
}

/// Get the backend base URL and per-launch auth token. Only populated in `Ready`.
#[tauri::command]
fn get_backend_endpoint(state: State<'_, BackendSupervisorState>) -> Result<BackendEndpoint, CommandError> {
    let slot = state.inner.lock().unwrap();
    match &*slot {
        Some(sup) => match &slot.as_ref().unwrap().status().state {
            BackendState::Ready { port, token } => Ok(BackendEndpoint {
                url: format!("http://127.0.0.1:{port}"),
                token: token.clone(),
            }),
            other => Err(CommandError {
                code: "backend_not_ready".into(),
                message: format!("Backend is {:?}, not ready", other),
            }),
        },
        None => Err(CommandError {
            code: "backend_not_started".into(),
            message: "Backend supervisor has not been started".into(),
        }),
    }
}

/// Start (or ensure started) the backend sidecar and wait for readiness.
#[tauri::command]
fn start_backend(state: State<'_, BackendSupervisorState>) -> Result<BackendStatus, CommandError> {
    let mut slot = state.inner.lock().unwrap();
    let sup = match &*slot {
        Some(s) => s.clone(),
        None => {
            let source = BinarySource::packaged_for_current_target();
            let s = Arc::new(sidecar::SidecarSupervisor::new(source));
            s.start();
            s.spawn().map_err(|e| CommandError::from(e))?;
            slot.replace(s.clone());
            s
        }
    };
    drop(slot);
    Ok(sup.status())
}

/// Restart the backend sidecar.
#[tauri::command]
fn restart_backend(state: State<'_, BackendSupervisorState>) -> Result<BackendStatus, CommandError> {
    let slot = state.inner.lock().unwrap();
    let sup = slot.as_ref().ok_or_else(|| CommandError {
        code: "backend_not_started".into(),
        message: "Backend supervisor has not been started".into(),
    })?;
    sup.restart().map_err(|e| CommandError::from(e))?;
    Ok(sup.status())
}

/// Gracefully stop the backend sidecar.
#[tauri::command]
fn stop_backend(state: State<'_, BackendSupervisorState>) -> Result<BackendStatus, CommandError> {
    let mut slot = state.inner.lock().unwrap();
    if let Some(sup) = slot.take() {
        sup.shutdown().map_err(|e| CommandError::from(e))?;
    }
    Ok(BackendStatus {
        state: BackendState::Stopped,
        restarts: 0,
        pid: None,
        endpoint: None,
    })
}

/// Get captured (redacted) backend logs.
#[tauri::command]
fn get_backend_logs(state: State<'_, BackendSupervisorState>) -> Result<Vec<sidecar::LogLine>, CommandError> {
    let slot = state.inner.lock().unwrap();
    match &*slot {
        Some(sup) => Ok(sup.logs()),
        None => Ok(vec![]),
    }
}

// ── Keyring IPC commands (Phase 3) ────────────────────────────────────

#[tauri::command]
fn save_provider_key(
    state: State<'_, BackendSupervisorState>,
    provider: String,
    key: String,
) -> Result<(), CommandError> {
    let _ = state; // keyring is process-global; no supervisor needed
    keyring::save_key(&provider, &key)?;
    Ok(())
}

#[tauri::command]
fn has_provider_key(provider: String) -> Result<bool, CommandError> {
    Ok(keyring::has_key(&provider)?)
}

#[tauri::command]
fn delete_provider_key(provider: String) -> Result<(), CommandError> {
    keyring::delete_key(&provider)?;
    Ok(())
}

#[tauri::command]
fn read_provider_key(provider: String) -> Result<Option<String>, CommandError> {
    // Controlled read: only used by the desktop key-setup flow to confirm a
    // key was stored. The backend reads keys server-side from the OS keyring,
    // so the webview normally never needs the raw value.
    Ok(keyring::read_key(&provider)?)
}

// ── Tauri app ──────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            use tauri::Manager;
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        // NOTE: `tauri-plugin-opener` and `tauri-plugin-shell` are intentionally
        // not loaded here. The backend sidecar is spawned directly via
        // `std::process::Command` (no shell), and no arbitrary file/open
        // permissions are granted. Capabilities are scoped in
        // `capabilities/default.json` to `core:default` only.
        .manage(BackendSupervisorState::default())
        .invoke_handler(tauri::generate_handler![
            get_backend_status,
            get_backend_endpoint,
            start_backend,
            restart_backend,
            stop_backend,
            get_backend_logs,
            save_provider_key,
            has_provider_key,
            delete_provider_key,
            read_provider_key,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
