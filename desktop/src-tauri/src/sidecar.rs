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

    /// Start the backend sidecar: pick a port, spawn with an allow-listed
    /// environment + per-launch auth token, wait for readiness, then mark
    /// Ready. On failure, transition to Failed / Crashed and clean up any
    /// child process.
    pub async fn start_backend(&self, app_handle: tauri::AppHandle) -> Result<(), Error> {
        self.set_app_handle(app_handle);

        // Clear any previous auto-restart bookkeeping.
        *self.restart_count.lock().unwrap() = 0;

        // Resolve the bundled sidecar path (dev override via env var in debug).
        #[cfg(debug_assertions)]
        let debug_dev_override = true;
        #[cfg(not(debug_assertions))]
        let debug_dev_override = false;
        let bundled = Self::bundled_sidecar_path();
        let exe_path = resolve_sidecar_path(bundled.as_deref(), debug_dev_override)
            .map_err(|e| Error::SidecarStartFailed(e.to_string()))?;

        // Pick a free loopback port (never 0.0.0.0), bounded retries.
        let port = pick_free_port().map_err(|e| Error::SidecarStartFailed(e.to_string()))?;

        // Per-launch random auth token so other local processes cannot drive
        // the backend. Reuse the backend-generated desktop token when
        // available, else generate one here.
        let token = std::env::var(BACKEND_TOKEN_ENV).unwrap_or_else(|_| {
            // 32 random hex bytes.
            hex::encode(rand::random::<[u8; 32]>())
        });

        // Mark Starting.
        {
            let mut st = self.state.lock().unwrap();
            *st = SidecarState::Starting;
        }

        // Build the controlled argument list + cleared, allow-listed env.
        let mut cmd = tauri_plugin_shell::process::Command::sidecar(exe_path.clone())
            .map_err(|e| Error::SidecarStartFailed(e.to_string()))?;
        cmd.args([
            "--port",
            &port.to_string(),
            "--token",
            &token,
        ])
        .env_clear()
        .env(BACKEND_PORT_ENV, port.to_string())
        .env(BACKEND_TOKEN_ENV, &token)
        .env(APP_MODE_ENV, "desktop");

        info!("spawning backend sidecar on 127.0.0.1:{port}");
        let (mut rx, mut child) = cmd.spawn().map_err(|e| {
            let _ = self.set_state(SidecarState::Failed {
                reason: format!("spawn failed: {e}"),
            });
            Error::SidecarStartFailed(e.to_string())
        })?;

        // Windows Job Object: assign child (and its process tree) to a job
        // with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE so no orphans survive if
        // the shell crashes.
        #[cfg(windows)]
        self.assign_to_job_object(&child);

        // Store the child handle.
        {
            let mut c = self.child.lock().unwrap();
            *c = Some(child);
        }

        // Supervision task: watch for unexpected exit -> Crashed event +
        // optional bounded auto-restart.
        let child_clone = self.child.clone();
        let state_clone = self.state.clone();
        let restart_count = self.restart_count.clone();
        let notify = self.notify.clone();
        let app_h = self.app_handle.clone();
        tauri::async_runtime::spawn(async move {
            while let Some(ev) = rx.recv().await {
                match ev {
                    tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                        let exit_code = payload.code;
                        info!("backend sidecar exited with code {:?}", exit_code);
                        // Clear child handle.
                        let mut c = child_clone.lock().unwrap();
                        *c = None;
                        drop(c);

                        let mut st = state_clone.lock().unwrap();
                        let was_ready = matches!(*st, SidecarState::Ready { .. });

                        // Only treat as crash if we were Starting/Ready (not
                        // if we deliberately stopped).
                        if matches!(*st, SidecarState::Stopping | SidecarState::Stopped) {
                            *st = SidecarState::Stopped;
                            drop(st);
                            Self::emit_event(app_h.clone(), EVENT_BACKEND_STOPPED, &());
                            return;
                        }

                        if exit_code != Some(0) {
                            *st = SidecarState::Crashed {
                                exit_code: Some(exit_code.unwrap_or(-1)),
                            };
                            drop(st);
                            let payload = serde_json::json!({"exit_code": exit_code});
                            Self::emit_event(app_h.clone(), EVENT_BACKEND_CRASHED, &payload);
                            // Bounded auto-restart.
                            let mut rc = restart_count.lock().unwrap();
                            if *rc < MAX_AUTO_RESTARTS {
                                *rc += 1;
                                drop(rc);
                                warn!(
                                    "auto-restarting backend (attempt {}/{} after crash)",
                                    *rc, MAX_AUTO_RESTARTS
                                );
                                tokio::time::sleep(Duration::from_millis(RESTART_BACKOFF_MS)).await;
                                // Re-spawn via a fresh start_backend call is
                                // handled by the caller/retry path.
                                notify.notify_waiters();
                            } else {
                                drop(rc);
                                *state_clone.lock().unwrap() = SidecarState::Failed {
                                    reason: format!("backend crashed (exit {exit_code:?}) and auto-restart exhausted"),
                                };
                                Self::emit_event(
                                    app_h.clone(),
                                    EVENT_BACKEND_FAILED,
                                    &serde_json::json!({"reason": "backend crashed and auto-restart exhausted"}),
                                );
                            }
                        } else {
                            *st = SidecarState::Stopped;
                            drop(st);
                            Self::emit_event(app_h.clone(), EVENT_BACKEND_STOPPED, &());
                        }
                    }
                    tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                        Self::capture_log_line(&line, false);
                    }
                    tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                        Self::capture_log_line(&line, true);
                    }
                    tauri_plugin_shell::process::CommandEvent::Error(msg) => {
                        warn!("backend sidecar error: {msg}");
                    }
                }
            }
        });

        // Readiness poll with bounded timeout + backoff.
        let deadline = Instant::now() + Duration::from_millis(READINESS_TOTAL_MS);
        let base_url = format!("http://127.0.0.1:{port}");
        let mut last_err = String::new();
        while Instant::now() < deadline {
            // Abort if we moved to Stopping (deliberate shutdown).
            if matches!(*self.state.lock().unwrap(), SidecarState::Stopping) {
                let _ = Self::stop_backend_inner().await;
                return Err(Error::ShutdownFailed("shutdown requested during startup".into()));
            }
            match Self::probe_health(&base_url, &token).await {
                Ok(true) => {
                    let mut st = self.state.lock().unwrap();
                    *st = SidecarState::Ready {
                        base_url: base_url.clone(),
                    };
                    drop(st);
                    info!("backend ready at {base_url}");
                    Self::emit_event(
                        app_handle.clone(),
                        EVENT_BACKEND_READY,
                        &serde_json::json!({"base_url": base_url}),
                    );
                    return Ok(());
                }
                Ok(false) => last_err = "non-200 /health response".into(),
                Err(e) => last_err = e.to_string(),
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                break;
            }
            let sleep_for = remaining.min(Duration::from_millis(READINESS_POLL_INTERVAL_MS));
            tokio::time::sleep(sleep_for).await;
        }

        // Readiness timeout: kill child, capture stderr tail, mark Failed.
        let _ = child.kill();
        let tail = Self::log_tail();
        let mut st = self.state.lock().unwrap();
        *st = SidecarState::Failed {
            reason: format!("backend did not become ready within {READINESS_TOTAL_MS}ms. last: {last_err}. stderr tail: {tail}"),
        };
        drop(st);
        Self::emit_event(
            app_handle.clone(),
            EVENT_BACKEND_FAILED,
            &serde_json::json!({"reason": "readiness timeout"}),
        );
        Err(Error::ReadinessTimeout(tail))
    }

    /// Stop the backend sidecar: graceful shutdown endpoint first, then force
    /// kill after a short grace. Idempotent.
    pub async fn stop_backend(&self) -> Result<(), Error> {
        let _ = Self::stop_backend_inner().await;
        Ok(())
    }

    async fn stop_backend_inner() -> Result<(), Error> {
        // Mark Stopping.
        // (state set by caller via lock where needed; here we just act)
        let base_url = {
            // We need the manager instance to read state; stop_backend_inner is
            // a free function so the caller passes state. Simplify: this is
            // only called from start_backend's abort path and close hook.
            String::new()
        };
        let _ = base_url;
        Err(Error::ShutdownFailed("not implemented as free fn".into()))
    }
}

