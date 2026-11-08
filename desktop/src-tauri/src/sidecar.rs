use std::collections::VecDeque;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::sync::{Mutex, Notify};
use tokio::time::error::Elapsed;
use tracing::{debug, error, info, warn};

use crate::errors::Error;
use crate::keyring::CredentialStore;
use crate::sidecar_core::{
    assert_port_free, pick_free_port, resolve_sidecar_path, validate_secret, wrap_secret,
    APP_MODE_ENV, BACKEND_PORT_ENV, BACKEND_TOKEN_ENV, MAIN_WINDOW_LABEL,
    READINESS_POLL_INTERVAL_MS, READINESS_TOTAL_MS, SIDECAR_DEV_PATH_ENV,
};
use crate::Error as AppError;

// ────────────────────────────────────────────────────────────
// Events
// ────────────────────────────────────────────────────────────

/// Tauri events emitted by the sidecar manager so the frontend can react.
pub const EVENT_BACKEND_READY: &str = "backend://ready";
pub const EVENT_BACKEND_CRASHED: &str = "backend://crashed";
pub const EVENT_BACKEND_FAILED: &str = "backend://failed";
pub const EVENT_BACKEND_STOPPED: &str = "backend://stopped";

// ────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────

/// Grace period (ms) given to the backend to shut down gracefully before
/// force-kill.
const GRACE_PERIOD_MS: u64 = 3_000;
/// How long the supervisor waits between child-exit auto-restart attempts.
const RESTART_BACKOFF_MS: u64 = 2_000;
/// Maximum auto-restart attempts before giving up and surfacing Failed.
const MAX_AUTO_RESTARTS: u32 = 3;
/// Bounded size of the captured stdout/stderr tail (bytes) kept for error
/// diagnostics. Secrets are redacted before storage.
const LOG_TAIL_BYTES: usize = 4_096;
/// Bounded size of each line appended to the capture buffer.
const LINE_CAP_BYTES: usize = 1_024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SidecarState {
    Stopped,
    Starting,
    Ready { base_url: String },
    Stopping,
    Failed { reason: String },
    Crashed { exit_code: Option<i32> },
}

impl SidecarState {
    pub fn is_ready(&self) -> bool {
        matches!(self, SidecarState::Ready { .. })
    }
    pub fn is_terminal(&self) -> bool {
        matches!(
            self,
            SidecarState::Stopped | SidecarState::Failed { .. } | SidecarState::Crashed { .. }
        )
    }
    pub fn base_url(&self) -> Option<String> {
        match self {
            SidecarState::Ready { base_url } => Some(base_url.clone()),
            _ => None,
        }
    }
}

// ────────────────────────────────────────────────────────────
// SidecarManager
// ────────────────────────────────────────────────────────────

/// Supervises the FastAPI backend sidecar process.
///
/// Runs as Tauri `State` (an `Arc<Mutex<SidecarManager>>`). Only one manager
/// exists per app, enforced by the single-instance plugin.
pub struct SidecarManager {
    state: Mutex<SidecarState>,
    child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
    app_handle: Mutex<Option<tauri::AppHandle>>,
    // Auto-restart bookkeeping.
    restart_count: Mutex<u32>,
    notify: Notify,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            state: Mutex::new(SidecarState::Stopped),
            child: Mutex::new(None),
            app_handle: Mutex::new(None),
            restart_count: Mutex::new(0),
            notify: Notify::new(),
        }
    }

    pub fn set_app_handle(&self, handle: tauri::AppHandle) {
        *self.app_handle.lock().unwrap() = Some(handle);
    }

    pub async fn state(&self) -> SidecarState {
        self.state.lock().unwrap().clone()
    }

    /// Base URL of the ready backend, or `None` if not ready.
    pub async fn base_url(&self) -> Option<String> {
        self.state.lock().unwrap().base_url()
    }
}
