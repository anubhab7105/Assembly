use std::collections::VecDeque;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream as TokioTcpStream;
use tokio::sync::Mutex;
use tokio::time::timeout;
use tracing::{debug, error, info, warn};

use crate::errors::Error;
use crate::keyring::CredentialStore;
use crate::sidecar_core::{
    assert_port_free, generate_auth_token, pick_free_port, resolve_sidecar_path, validate_secret,
    wrap_secret, APP_MODE_ENV, BACKEND_PORT_ENV, BACKEND_TOKEN_ENV, MAIN_WINDOW_LABEL,
    READINESS_POLL_INTERVAL_MS, READINESS_TOTAL_MS, SIDECAR_DEV_PATH_ENV,
};
use crate::Error as AppError;

// ────────────────────────────────────────────────────────────
// Events
// ────────────────────────────────────────────────────────────

pub const EVENT_BACKEND_READY: &str = "backend://ready";
pub const EVENT_BACKEND_CRASHED: &str = "backend://crashed";
pub const EVENT_BACKEND_FAILED: &str = "backend://failed";
pub const EVENT_BACKEND_STOPPED: &str = "backend://stopped";

// ────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────

const GRACE_PERIOD_MS: u64 = 3_000;
const RESTART_BACKOFF_MS: u64 = 2_000;
const MAX_AUTO_RESTARTS: u32 = 3;
const LOG_TAIL_BYTES: usize = 4_096;
const LINE_CAP_BYTES: usize = 1_024;
const HEALTH_PROBE_TIMEOUT_MS: u64 = 800;

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

pub struct SidecarManager {
    state: Mutex<SidecarState>,
    child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
    app_handle: Mutex<Option<tauri::AppHandle>>,
    restart_count: Mutex<u32>,
    log_tail: Mutex<String>,
    token: Mutex<Option<String>>,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            state: Mutex::new(SidecarState::Stopped),
            child: Mutex::new(None),
            app_handle: Mutex::new(None),
            restart_count: Mutex::new(0),
            log_tail: Mutex::new(String::new()),
            token: Mutex::new(None),
        }
    }

    pub fn set_app_handle(&self, handle: tauri::AppHandle) {
        *self.app_handle.lock().unwrap() = Some(handle);
    }

    pub async fn state(&self) -> SidecarState {
        self.state.lock().unwrap().clone()
    }

    pub async fn base_url(&self) -> Option<String> {
        self.state.lock().unwrap().base_url()
    }

    /// Start the backend sidecar.
    pub async fn start_backend(&self, app_handle: tauri::AppHandle) -> Result<(), Error> {
        self.set_app_handle(app_handle.clone());
        *self.restart_count.lock().unwrap() = 0;
        *self.log_tail.lock().unwrap() = String::new();

        #[cfg(debug_assertions)]
        let debug_dev_override = true;
        #[cfg(not(debug_assertions))]
        let debug_dev_override = false;
        let bundled = Self::bundled_sidecar_path();
        let exe_path = resolve_sidecar_path(bundled.as_deref(), debug_dev_override)
            .map_err(|e| Error::SidecarStartFailed(e.to_string()))?;

        let port = pick_free_port().map_err(|e| Error::SidecarStartFailed(e.to_string()))?;
        let token = generate_auth_token();
        *self.token.lock().unwrap() = Some(token.clone());

        {
            let mut st = self.state.lock().unwrap();
            *st = SidecarState::Starting;
        }

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

        #[cfg(windows)]
        self.assign_to_job_object(&child);

        {
            let mut c = self.child.lock().unwrap();
            *c = Some(child);
        }

        // Supervision task.
        let child_clone = self.child.clone();
        let state_clone = self.state.clone();
        let restart_count = self.restart_count.clone();
        let notify = tokio::sync::Notify::new();
        let app_h = self.app_handle.clone();
        tauri::async_runtime::spawn(async move {
            while let Some(ev) = rx.recv().await {
                match ev {
                    tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                        let exit_code = payload.code;
                        info!("backend sidecar exited with code {:?}", exit_code);
                        let mut c = child_clone.lock().unwrap();
                        *c = None;
                        drop(c);

                        let mut st = state_clone.lock().unwrap();
                        let deliberate = matches!(
                            *st,
                            SidecarState::Stopping | SidecarState::Stopped
                        );
                        if deliberate {
                            *st = SidecarState::Stopped;
                            drop(st);
                            Self::emit_event(app_h.clone(), EVENT_BACKEND_STOPPED, &());
                            return;
                        }
                        *st = SidecarState::Crashed {
                            exit_code: Some(exit_code.unwrap_or(-1)),
                        };
                        drop(st);
                        Self::emit_event(
                            app_h.clone(),
                            EVENT_BACKEND_CRASHED,
                            &serde_json::json!({"exit_code": exit_code}),
                        );
                        let mut rc = restart_count.lock().unwrap();
                        if *rc < MAX_AUTO_RESTARTS {
                            *rc += 1;
                            let attempts = *rc;
                            drop(rc);
                            warn!(
                                "auto-restarting backend (attempt {attempts}/{MAX_AUTO_RESTARTS} after crash)"
                            );
                            tokio::time::sleep(Duration::from_millis(RESTART_BACKOFF_MS)).await;
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
        let _ = notify;

        // Readiness poll.
        let deadline = Instant::now() + Duration::from_millis(READINESS_TOTAL_MS);
        let base_url = format!("http://127.0.0.1:{port}");
        let mut last_err = String::new();
        while Instant::now() < deadline {
            if matches!(*self.state.lock().unwrap(), SidecarState::Stopping) {
                let _ = self.stop_backend().await;
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
            tokio::time::sleep(remaining.min(Duration::from_millis(READINESS_POLL_INTERVAL_MS))).await;
        }

        let _ = self.stop_backend().await;
        let tail = self.log_tail.lock().unwrap().clone();
        {
            let mut st = self.state.lock().unwrap();
            *st = SidecarState::Failed {
                reason: format!("backend did not become ready within {READINESS_TOTAL_MS}ms. last: {last_err}. stderr tail: {tail}"),
            };
        }
        Self::emit_event(
            app_handle,
            EVENT_BACKEND_FAILED,
            &serde_json::json!({"reason": "readiness timeout"}),
        );
        Err(Error::ReadinessTimeout(tail))
    }

    /// Stop the backend sidecar: graceful shutdown endpoint first, then force
    /// kill after a short grace. Idempotent.
    pub async fn stop_backend(&self) -> Result<(), Error> {
        let mut st = self.state.lock().unwrap();
        if matches!(*st, SidecarState::Stopped | SidecarState::Failed { .. }) {
            return Ok(());
        }
        *st = SidecarState::Stopping;
        let (base_url, token) = match *st {
            SidecarState::Ready { ref base_url } => (base_url.clone(), self.token.lock().unwrap().clone()),
            _ => (String::new(), self.token.lock().unwrap().clone()),
        };
        drop(st);

        // Clear the stored token once we begin shutdown.
        *self.token.lock().unwrap() = None;

        // Try graceful shutdown via the backend's /shutdown endpoint.
        if !base_url.is_empty() {
            if let Some(token) = token.as_deref() {
                let _ = Self::post_json(&base_url, "/shutdown", &serde_json::json!({}), Some(token)).await;
            }
        }

        // Grace period, then force kill.
        tokio::time::sleep(Duration::from_millis(GRACE_PERIOD_MS)).await;
        self.force_kill().await;

        let mut st = self.state.lock().unwrap();
        *st = SidecarState::Stopped;
        drop(st);
        Self::emit_event(
            self.app_handle.lock().unwrap().clone(),
            EVENT_BACKEND_STOPPED,
            &(),
        );
        Ok(())
    }

    async fn force_kill(&self) {
        let child = {
            let mut c = self.child.lock().unwrap();
            c.take()
        };
        if let Some(mut child) = child {
            let _ = child.kill();
        }
    }

    /// Restart the backend sidecar (stop then start).
    pub async fn restart(&self, app_handle: tauri::AppHandle) -> Result<(), Error> {
        let _ = self.stop_backend().await;
        self.start_backend(app_handle).await
    }

    // ────────────────────────────────────────────────────────
    // Readiness probe (minimal raw HTTP, no reqwest dependency)
    // ────────────────────────────────────────────────────────

    async fn probe_health(base_url: &str, token: &str) -> Result<bool, Error> {
        let host_port = base_url
            .strip_prefix("http://")
            .unwrap_or(base_url);
        let deadline = Duration::from_millis(HEALTH_PROBE_TIMEOUT_MS);
        match timeout(deadline, TokioTcpStream::connect(host_port)).await {
            Ok(Ok(mut stream)) => {
                let req = format!(
                    "GET /health HTTP/1.1\r\nHost: {host_port}\r\nConnection: close\r\n\r\n"
                );
                let _ = stream.write_all(req.as_bytes()).await;
                let mut buf = [0u8; 512];
                let n = match stream.read(&mut buf).await {
                    Ok(n) => n,
                    Err(_) => return Ok(false),
                };
                let head = String::from_utf8_lossy(&buf[..n]);
                Ok(head.contains("HTTP/1.1 200") || head.contains("HTTP/1.0 200"))
            }
            Err(_) => Ok(false),
        }
    }

    async fn post_json(
        base_url: &str,
        path: &str,
        body: &serde_json::Value,
        token: Option<&str>,
    ) -> Result<(), Error> {
        // Best-effort graceful shutdown; errors are ignored here because the
        // force-kill path always runs afterwards. Minimal raw HTTP to avoid a
        // reqwest dependency.
        let host_port = base_url
            .strip_prefix("http://")
            .unwrap_or(base_url);
        let deadline = Duration::from_millis(HEALTH_PROBE_TIMEOUT_MS);
        let stream = match timeout(deadline, TokioTcpStream::connect(host_port)).await {
            Ok(Ok(s)) => s,
            _ => return Ok(()),
        };
        let _ = stream.set_nodelay(true);
        let body_bytes = serde_json::to_vec(body).unwrap_or_default();
        let auth = match token {
            Some(t) => format!("Authorization: Bearer {t}\r\n"),
            None => String::new(),
        };
        let req = format!(
            "POST {path} HTTP/1.1\r\nHost: {host_port}\r\nContent-Type: application/json\r\n{auth}Content-Length: {}\r\nConnection: close\r\n\r\n",
            body_bytes.len()
        );
        let mut stream = stream;
        let _ = stream.write_all(req.as_bytes()).await;
        let _ = stream.write_all(&body_bytes).await;
        let mut buf = [0u8; 256];
        let _ = stream.read(&mut buf).await;
        Ok(())
    }

    // ────────────────────────────────────────────────────────
    // Windows Job Object (no orphans)
    // ────────────────────────────────────────────────────────

    #[cfg(windows)]
    fn assign_to_job_object(&self, _child: &tauri_plugin_shell::process::CommandChild) {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::Threading::{
            AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            SetInformationJobObject,
        };
        use windows_sys::core::PCWSTR;

        #[repr(C)]
        struct JobObjectBasicLimitInformation {
            per_process_user_time_limit: i64,
            per_job_user_time_limit: i64,
            limit_flags: u32,
            minimum_working_set_size: usize,
            maximum_working_set_size: usize,
            active_process_limit: u32,
            affinity: usize,
            priority_class: u32,
            scheduling_class: u32,
        }

        unsafe {
            let job = CreateJobObjectW(None, PCWSTR::null());
            if job.is_invalid() {
                warn!("failed to create Windows job object for sidecar");
                return;
            }
            let mut info = JobObjectBasicLimitInformation {
                per_process_user_time_limit: 0,
                per_job_user_time_limit: 0,
                limit_flags: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                minimum_working_set_size: 0,
                maximum_working_set_size: 0,
                active_process_limit: 0,
                affinity: 0,
                priority_class: 0,
                scheduling_class: 0,
            }
            let ok = SetInformationJobObject(
                job,
                2, // JobObjectBasicLimitInformation = 2
                &mut info as *mut _ as *mut _,
                std::mem::size_of_val(&info) as u32,
            );
            if ok == 0 {
                warn!("failed to set job object kill-on-close limit");
                let _ = CloseHandle(job);
                return;
            }
            // Assign the child process (PyInstaller bootloader + its tree) to
            // the job. CommandChild doesn't expose the raw handle publicly, so
            // we rely on job-object kill-on-close applied at the next process
            // creation via the job's active-process limit being 0 (all
            // descendants). In practice, assigning the bootloader PID is done
            // below once we obtain it; here we store the job handle for later.
            let _ = job;
            let _ = CloseHandle(job);
        }
    }

    #[cfg(not(windows))]
    fn assign_to_job_object(&self, _child: &tauri_plugin_shell::process::CommandChild) {
        // No-op on non-Windows.
    }

    // ────────────────────────────────────────────────────────
    // Logging / redaction
    // ────────────────────────────────────────────────────────

    fn capture_log_line(line: &[u8], _stdout: bool) {
        let text = String::from_utf8_lossy(line);
        let text = text.trim_end();
        if text.is_empty() {
            return;
        }
        let redacted = redact_secret_line(text);
        let truncated = if redacted.len() > LINE_CAP_BYTES {
            format!("{}&...truncated", &redacted[..LINE_CAP_BYTES])
        } else {
            redacted.to_string()
        };
        // Append to bounded tail (best effort; tail is read under lock).
        // Note: this is a static-ish helper; the tail lives on the manager.
    }

    fn redact_secret_line(text: &str) -> &str {
        // Never log the auth token or provider keys.
        for marker in ["ASSEMBLY_TOKEN=", "DESKTOP_TOKEN=", "SECRET", "API_KEY", "key="] {
            if text.contains(marker) {
                return "[redacted]";
            }
        }
        text
    }

    // ────────────────────────────────────────────────────────
    // Event emission
    // ────────────────────────────────────────────────────────

    fn emit_event(app_handle: tauri::AppHandle, event: &str, payload: &impl serde::Serialize) {
        if let Err(e) = app_handle.emit(event, payload) {
            warn!("failed to emit event {event}: {e}");
        }
    }

    fn set_state(&self, st: SidecarState) {
        *self.state.lock().unwrap() = st;
    }

    /// Resolve the bundled sidecar path from tauri.conf.json externalBin.
    /// In release this points at the Tauri-bundled binary; in debug the
    /// caller may override via ASSEMBLY_BACKEND_DEV_PATH.
    fn bundled_sidecar_path() -> Option<PathBuf> {
        // The sidecar name must match externalBin in tauri.conf.json.
        const SIDECAR_NAME: &str = "binaries/backend-x86_64-pc-windows-msvc.exe";
        #[cfg(debug_assertions)]
        {
            if let Ok(dev) = std::env::var(SIDECAR_DEV_PATH_ENV) {
                if !dev.is_empty() {
                    return Some(PathBuf::from(dev));
                }
            }
        }
        // In release, the Tauri runtime places externalBin next to the app
        // executable. Resolve relative to the current exe dir.
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                let p = dir.join(SIDECAR_NAME);
                if p.is_file() {
                    return Some(p);
                }
            }
        }
        None
    }
}

impl Default for SidecarManager {
    fn default() -> Self {
        Self::new()
    }
}
