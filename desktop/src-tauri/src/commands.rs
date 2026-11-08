use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::errors::{Error, Secret};
use crate::keyring::CredentialState;
use crate::sidecar::{
    EVENT_BACKEND_READY, EVENT_BACKEND_CRASHED, EVENT_BACKEND_FAILED, EVENT_BACKEND_STOPPED,
    MAIN_WINDOW_LABEL,
};
use crate::sidecar_core::{
    validate_provider, validate_secret, validate_window_label, wrap_secret, SidecarState,
};
use crate::SidecarManager;

// ────────────────────────────────────────────────────────────
// Request / response types (serializable, no secrets echoed)
// ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct BackendStatusResponse {
    pub state: String,
    pub base_url: Option<String>,
    // The auth token is deliberately NOT returned to the webview. The
    // webview asks Rust to perform backend operations; Rust injects the
    // token into the backend request/environment.
    pub ready: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CredentialSaveRequest {
    pub provider: String,
    pub secret: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CredentialSaveResponse {
    pub provider: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CredentialExistsResponse {
    pub provider: String,
    pub exists: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CredentialDeleteResponse {
    pub provider: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CredentialListResponse {
    pub providers: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct CommandError {
    pub code: String,
    pub message: String,
}

impl From<Error> for CommandError {
    fn from(e: Error) -> Self {
        let code = match &e {
            Error::SidecarNotFound => "sidecar_not_found",
            Error::SidecarNotExecutable => "sidecar_not_executable",
            Error::SidecarStartFailed { .. } => "sidecar_start_failed",
            Error::PortUnavailable => "port_unavailable",
            Error::ReadinessTimeout { .. } => "readiness_timeout",
            Error::ProcessCrashed { .. } => "process_crashed",
            Error::ShutdownFailed { .. } => "shutdown_failed",
            Error::InvalidInput { .. } => "invalid_input",
            Error::ProviderNotAllowed { .. } => "provider_not_allowed",
            Error::SecretEmpty => "secret_empty",
            Error::SecretTooLarge => "secret_too_large",
            Error::KeyringUnavailable { .. } => "keyring_unavailable",
            Error::CredentialNotFound => "credential_not_found",
            Error::UnauthorizedWindow => "unauthorized_window",
            Error::Io { .. } => "io_error",
        };
        CommandError {
            code: code.to_string(),
            message: e.to_string(),
        }
    }
}

// ────────────────────────────────────────────────────────────
// Guard: restrict commands to the main window label
// ────────────────────────────────────────────────────────────

fn require_main_window(window: &tauri::Window) -> Result<(), Error> {
    validate_window_label(window.label())?;
    if window.label() != MAIN_WINDOW_LABEL {
        return Err(Error::UnauthorizedWindow);
    }
    Ok(())
}

// ────────────────────────────────────────────────────────────
// Commands
// ────────────────────────────────────────────────────────────

/// Current backend sidecar state and base URL. Never returns the auth token.
#[tauri::command]
pub async fn backend_status(
    manager: State<'_, Arc<SidecarManager>>,
    window: tauri::Window,
) -> Result<BackendStatusResponse, CommandError> {
    require_main_window(&window)?;
    let state = manager.state().await;
    Ok(BackendStatusResponse {
        state: state_name(&state),
        base_url: state.base_url(),
        ready: state.is_ready(),
    })
}

/// Restart the backend sidecar.
#[tauri::command]
pub async fn backend_restart(
    manager: State<'_, Arc<SidecarManager>>,
    window: tauri::Window,
    app_handle: tauri::AppHandle,
) -> Result<(), CommandError> {
    require_main_window(&window)?;
    manager.restart(app_handle).await.map_err(Into::into)
}

/// Save a provider credential to the OS keyring. The secret is never echoed
/// back and never written to logs/files/SQLite/browser storage.
#[tauri::command]
pub async fn credential_save(
    store: State<'_, CredentialState>,
    window: tauri::Window,
    req: CredentialSaveRequest,
) -> Result<CredentialSaveResponse, CommandError> {
    require_main_window(&window)?;
    validate_provider(&req.provider)?;
    let secret = wrap_secret(validate_secret(&req.secret)?);
    store.save(&req.provider, &secret)?;
    Ok(CredentialSaveResponse {
        provider: req.provider,
    })
}

/// Check whether a credential exists for a provider (no value revealed).
#[tauri::command]
pub async fn credential_exists(
    store: State<'_, CredentialState>,
    window: tauri::Window,
    provider: String,
) -> Result<CredentialExistsResponse, CommandError> {
    require_main_window(&window)?;
    validate_provider(&provider)?;
    let exists = store.exists(&provider)?;
    Ok(CredentialExistsResponse {
        provider,
        exists,
    })
}

/// Delete a provider credential from the OS keyring.
#[tauri::command]
pub async fn credential_delete(
    store: State<'_, CredentialState>,
    window: tauri::Window,
    provider: String,
) -> Result<CredentialDeleteResponse, CommandError> {
    require_main_window(&window)?;
    validate_provider(&provider)?;
    store.delete(&provider)?;
    Ok(CredentialDeleteResponse { provider })
}

/// List provider names that have a stored credential (names only, never
/// values).
#[tauri::command]
pub async fn credential_list(
    store: State<'_, CredentialState>,
    window: tauri::Window,
) -> Result<CredentialListResponse, CommandError> {
    require_main_window(&window)?;
    let providers = store.list()?;
    Ok(CredentialListResponse { providers })
}

fn state_name(state: &SidecarState) -> String {
    match state {
        SidecarState::Stopped => "stopped".to_string(),
        SidecarState::Starting => "starting".to_string(),
        SidecarState::Ready { .. } => "ready".to_string(),
        SidecarState::Stopping => "stopping".to_string(),
        SidecarState::Failed { .. } => "failed".to_string(),
        SidecarState::Crashed { .. } => "crashed".to_string(),
    }
}

// Re-export event names for the frontend TS client to match.
pub const BACKEND_READY_EVENT: &str = EVENT_BACKEND_READY;
pub const BACKEND_CRASHED_EVENT: &str = EVENT_BACKEND_CRASHED;
pub const BACKEND_FAILED_EVENT: &str = EVENT_BACKEND_FAILED;
pub const BACKEND_STOPPED_EVENT: &str = EVENT_BACKEND_STOPPED;
