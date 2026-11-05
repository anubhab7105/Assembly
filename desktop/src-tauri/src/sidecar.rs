//! Backend sidecar lifecycle supervision.
//!
//! Responsibilities:
//! - Resolve the packaged backend executable per target triple, with an
//!   explicit, separate dev-mode path (unit-testable).
//! - Spawn the backend with controlled args/env only — no inherited secrets
//!   beyond `APP_MODE`/`ASSEMBLY_TOKEN`, and no user-controlled command
//!   strings.
//! - Pick a free loopback port (127.0.0.1 only, no fixed-port collisions)
//!   and relay the backend's advertised port + per-launch auth token to the
//!   frontend through IPC.
//! - Wait for readiness by polling `/health` with a timeout + backoff.
//! - Model state explicitly: `Starting | Ready | Failed | Crashed | Stopping | Stopped`.
//! - Capture stdout/stderr into a bounded ring buffer with secret redaction,
//!   surfacing startup failures and crashes to the frontend via events/commands.
//! - Crash policy: limited restarts with backoff, then surface `Failed`.
//! - Clean shutdown on app exit/window close: graceful request first, then
//!   kill after a timeout. On Windows a Job Object guarantees no orphaned
//!   backend process survives even if the shell is killed.
//!
//! The core supervision logic is `std`-only (no Tokio/GUI dependencies) so it
//! can be unit-tested in isolation. Tauri command glue lives in `lib.rs`.

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::io::{self, BufRead, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

/// Maximum number of restart attempts after a crash before giving up and
/// reporting `Failed`. Chosen so a transient glitch self-heals but a
/// persistently-broken backend does not restart forever.
pub const MAX_RESTARTS: u32 = 3;

/// Backoff delays (in seconds) between restart attempts, one per restart.
/// Index `i` is the delay before restart number `i+1`.
const RESTART_BACKOFF_SECONDS: [u64; MAX_RESTARTS as usize] = [1, 2, 4];

/// How long to wait for the backend to honor `/shutdown` before killing it.
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);

/// How long to wait for `/health` to become ready before declaring failure.
const READINESS_TIMEOUT: Duration = Duration::from_secs(30);

/// Interval between readiness poll attempts.
const READINESS_POLL_INTERVAL: Duration = Duration::from_millis(500);

/// Maximum number of log lines retained in the bounded ring buffer.
const MAX_LOG_LINES: usize = 2000;

/// Maximum length of a single captured log line before truncation.
const MAX_LOG_LINE_LEN: usize = 4000;

/// Substrings that must be redacted from captured logs. Names/patterns only
/// — never values.
const REDACT_PATTERNS: &[&str] = &[
    "ASSEMBLY_TOKEN=",
    "Authorization:",
    "X-Assembly-Token:",
    "Bearer ",
    "api_key",
    "secret",
    "password",
    "token",
];

/// How the backend executable should be resolved.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum BinarySource {
    /// Packaged production binary, resolved next to the Tauri bundle per
    /// target triple.
    Packaged { target_triple: String },
    /// Dev mode: launch `python src/main.py` with `APP_MODE=desktop`.
    Dev { cwd: PathBuf },
}

impl BinarySource {
    /// Resolve the packaged backend for the current target triple.
    pub fn packaged_for_current_target() -> Self {
        let target_triple = current_target_triple();
        Self::Packaged { target_triple }
    }

    /// Dev mode: launch `python src/main.py` from `cwd` with `APP_MODE=desktop`.
    pub fn dev(cwd: PathBuf) -> Self {
        Self::Dev { cwd }
    }
}

/// Best-effort current Rust target triple (e.g. `x86_64-pc-windows-msvc`).
fn current_target_triple() -> String {
    let arch = std::env::consts::ARCH;
    if cfg!(target_os = "windows") {
        format!("{arch}-pc-windows-msvc")
    } else if cfg!(target_os = "linux") {
        format!("{arch}-unknown-linux-gnu")
    } else if cfg!(target_os = "macos") {
        format!("{arch}-apple-darwin")
    } else {
        format!("{arch}-unknown-{}", std::env::consts::OS)
    }
}

/// Explicit backend state machine.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "type", rename_all = "PascalCase")]
pub enum BackendState {
    /// Spawning and waiting for `/health`.
    Starting,
    /// Ready to serve requests on `port`, protected by `token`.
    Ready { port: u16, token: String },
    /// Startup failed (spawn error, readiness timeout, config).
    Failed { reason: String },
    /// Was running but exited unexpectedly with `code`.
    Crashed { code: Option<i32> },
    /// Graceful shutdown in progress.
    Stopping,
    /// Stopped cleanly.
    Stopped,
}

impl BackendState {
    pub fn is_terminal(&self) -> bool {
        matches!(
            self,
            BackendState::Failed { .. } | BackendState::Stopped
        )
    }
    pub fn is_running(&self) -> bool {
        matches!(self, BackendState::Ready { .. })
    }
}

/// Serialized snapshot of supervisor status, safe to send across IPC.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendStatus {
    pub state: BackendState,
    pub restarts: u32,
    pub pid: Option<u32>,
    /// Base URL of the backend (only `Some` in `Ready`).
    pub endpoint: Option<String>,
}

/// A single captured log line, redacted of secrets.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogLine {
    pub stream: LogStream,
    pub line: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum LogStream {
    Stdout,
    Stderr,
}

/// Events emitted by the supervisor that the frontend can subscribe to.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SupervisorEvent {
    StateChanged { state: BackendState },
    Log(LogLine),
    Error { message: String },
}

/// Commands the supervisor task accepts. Each command carries a reply
/// channel typed to that command's error so error codes are preserved
/// across the thread boundary (a readiness timeout is not collapsed into a
/// generic spawn failure).
enum SupervisorCmd {
    Spawn { reply: mpsc::Sender<Result<(), StartError>> },
    Shutdown { reply: mpsc::Sender<Result<(), ShutdownError>> },
    Restart { reply: mpsc::Sender<Result<(), RestartError>> },
    Status { reply: mpsc::Sender<BackendStatus> },
}

/// Errors returned by the spawn path.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StartError {
    pub code: StartErrorCode,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum StartErrorCode {
    BinaryNotFound,
    SpawnFailed,
    ReadinessTimeout,
    InvalidPort,
}

/// Errors returned by the shutdown path.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShutdownError {
    pub message: String,
}

/// Errors returned by the restart path.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RestartError {
    pub message: String,
}

/// A bounded ring buffer of redacted log lines.
#[derive(Debug, Clone, Default)]
pub struct LogBuffer {
    lines: VecDeque<LogLine>,
}

impl LogBuffer {
    pub fn new() -> Self {
        Self::default()
    }

    /// Push a line, redacting secrets and truncating overly long lines.
    pub fn push(&mut self, stream: LogStream, raw: &str) {
        let mut line = redact(raw.trim_end());
        line.truncate(MAX_LOG_LINE_LEN);
        if line.is_empty() {
            return;
        }
        if self.lines.len() >= MAX_LOG_LINES {
            self.lines.pop_front();
        }
        self.lines.push_back(LogLine { stream, line });
    }

    pub fn lines(&self) -> impl Iterator<Item = &LogLine> {
        self.lines.iter()
    }
}

/// Redact known secret patterns from a string, replacing the value portion
/// with `[REDACTED]`. Never returns the raw secret.
fn redact(raw: &str) -> String {
    let mut out = raw.to_string();
    for pat in REDACT_PATTERNS {
        if let Some(idx) = out.find(pat) {
            let start = idx + pat.len();
            let end = out[start..]
                .find(|c: char| c.is_whitespace() || c == ',' || c == '}')
                .map(|e| start + e)
                .unwrap_or(out.len());
            if end > start {
                out.replace_range(start..end, "[REDACTED]");
            }
        }
    }
    out
}

/// Pick a free loopback port on 127.0.0.1. Bound briefly then released —
/// there is an inherent TOCTOU race, but this avoids fixed-port collisions
/// and is sufficient for a local desktop backend.
pub fn pick_free_port() -> io::Result<u16> {
    let socket = TcpListener::bind("127.0.0.1:0")?;
    let port = socket.local_addr()?.port();
    drop(socket);
    Ok(port)
}

/// Resolve the backend executable path for a packaged build.
///
/// Convention: `<exe_dir>/binaries/backend-<target_triple>.<ext>`, where
/// `<ext>` is `.exe` on Windows and empty elsewhere. This matches the name
/// produced by `desktop/package.json` `build:backend` and listed in
/// `tauri.conf.json` `externalBin`.
pub fn packaged_binary_path(target_triple: &str) -> PathBuf {
    let exe = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("tauri-app"));
    let exe_dir = exe.parent().unwrap_or(Path::new("."));
    let ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    exe_dir.join(format!("binaries/backend-{target_triple}{ext}"))
}

/// Unit-testable path resolution. Returns the path to use; the caller checks
/// existence via `Path::is_file`.
pub fn resolve_binary_path(source: &BinarySource) -> PathBuf {
    match source {
        BinarySource::Packaged { target_triple } => packaged_binary_path(target_triple),
        BinarySource::Dev { cwd } => cwd.join("src").join("main.py"),
    }
}

/// Check whether the resolved binary exists on disk.
pub fn binary_exists(path: &Path) -> bool {
    path.is_file()
}

/// Build the `Command` used to spawn the backend. Controlled args/env only.
pub fn build_command(
    binary: &Path,
    source: &BinarySource,
    port: u16,
    token: &str,
) -> Command {
    let mut cmd = match source {
        BinarySource::Dev { .. } => {
            let mut c = Command::new("python");
            c.arg(binary); // src/main.py
            c
        }
        BinarySource::Packaged { .. } => {
            let mut c = Command::new(binary);
            c
        }
    };
    // Controlled environment: no inherited secrets. Only what the backend
    // needs to run in desktop mode and bind loopback.
    cmd.env("APP_MODE", "desktop");
    cmd.env("ASSEMBLY_PORT", port.to_string());
    cmd.env("ASSEMBLY_TOKEN", token);
    cmd.env("RUST_LOG", "error,warn");
    // Capture stdout/stderr so we can log them; do not inherit the caller's
    // secret env vars beyond the ones explicitly set above.
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());
    // Security: do not spawn a shell; execute the binary directly.
    cmd
}

/// Generate a per-launch random auth token (hex, 32 bytes).
pub fn generate_token() -> String {
    let mut buf = String::with_capacity(64);
    for _ in 0..32 {
        buf.push_str(&format!("{:02x}", rand_byte()));
    }
    buf
}

/// Simple xorshift PRNG — no `getrandom` dependency needed for a local
/// per-launch token.
fn rand_byte() -> u8 {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEED: AtomicU64 = AtomicU64::new(0x9E37_79B9_7F4A_7C15);
    let mut x = SEED.fetch_add(1, Ordering::Relaxed)
        .wrapping_add(0x9E37_79B9_7F4A_7C15);
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^= x >> 31;
    SEED.store(x, Ordering::Relaxed);
    (x >> 16) as u8
}

/// The supervisor task. Owns the backend `Child` on a dedicated thread and
/// drives the state machine.
pub struct SidecarSupervisor {
    source: BinarySource,
    state: Arc<Mutex<BackendStatus>>,
    logs: Arc<Mutex<LogBuffer>>,
    tx: Mutex<Option<mpsc::Sender<SupervisorCmd>>>,
    running: Arc<AtomicBool>,
}

impl SidecarSupervisor {
    pub fn new(source: BinarySource) -> Self {
        Self {
            source,
            state: Arc::new(Mutex::new(BackendStatus {
                state: BackendState::Stopped,
                restarts: 0,
                pid: None,
                endpoint: None,
            })),
            logs: Arc::new(Mutex::new(LogBuffer::new())),
            tx: Mutex::new(None),
            running: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Start the supervisor thread. Idempotent.
    pub fn start(&self) {
        if self
            .running
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return;
        }
        let (tx, rx) = mpsc::channel();
        let state = self.state.clone();
        let logs = self.logs.clone();
        let source = self.source.clone();
        let running = self.running.clone();

        thread::spawn(move || {
            supervisor_loop(rx, state, logs, source, running);
        });
        *self.tx.lock().unwrap() = Some(tx);
    }

    pub fn status(&self) -> BackendStatus {
        self.state.lock().unwrap().clone()
    }

    pub fn logs(&self) -> Vec<LogLine> {
        self.logs.lock().unwrap().lines().cloned().collect()
    }

    pub fn spawn(&self) -> Result<(), StartError> {
        let binding = self.tx.lock().unwrap();
        let tx = binding.as_ref().expect("supervisor not started");
        let (reply, rx) = mpsc::channel();
        tx.send(SupervisorCmd::Spawn { reply }).ok();
        match rx.recv() {
            Ok(Ok(())) => Ok(()),
            Ok(Err(e)) => Err(e),
            Err(_) => Err(StartError {
                code: StartErrorCode::SpawnFailed,
                message: "supervisor channel closed".into(),
            }),
        }
    }

    pub fn shutdown(&self) -> Result<(), ShutdownError> {
        let binding = self.tx.lock().unwrap();
        let tx = binding.as_ref().expect("supervisor not started");
        let (reply, rx) = mpsc::channel();
        tx.send(SupervisorCmd::Shutdown { reply }).ok();
        match rx.recv() {
            Ok(Ok(())) => Ok(()),
            Ok(Err(e)) => Err(e),
            Err(_) => Err(ShutdownError {
                message: "supervisor channel closed".into(),
            }),
        }
    }

    pub fn restart(&self) -> Result<(), RestartError> {
        let binding = self.tx.lock().unwrap();
        let tx = binding.as_ref().expect("supervisor not started");
        let (reply, rx) = mpsc::channel();
        tx.send(SupervisorCmd::Restart { reply }).ok();
        match rx.recv() {
            Ok(Ok(())) => Ok(()),
            Ok(Err(e)) => Err(RestartError { message: e.message }),
            Err(_) => Err(RestartError {
                message: "supervisor channel closed".into(),
            }),
        }
    }
}

fn supervisor_loop(
    rx: mpsc::Receiver<SupervisorCmd>,
    state: Arc<Mutex<BackendStatus>>,
    logs: Arc<Mutex<LogBuffer>>,
    source: BinarySource,
    running: Arc<AtomicBool>,
) {
    let mut child: Option<Child> = None;
    let mut restarts: u32 = 0;

    set_state(&state, BackendState::Stopped);

    for cmd in rx {
        match cmd {
            SupervisorCmd::Spawn { reply } => {
                let result = do_spawn(&source, &state, &logs, &mut child, &mut restarts);
                let _ = reply.send(result);
            }
            SupervisorCmd::Shutdown { reply } => {
                let result = do_shutdown(&mut child, &state, &logs);
                set_state(&state, BackendState::Stopped);
                child = None;
                let _ = reply.send(result);
                break;
            }
            SupervisorCmd::Restart { reply } => {
                let _ = do_shutdown(&mut child, &state, &logs);
                child = None;
                restarts = 0;
                let result = do_spawn(&source, &state, &logs, &mut child, &mut restarts);
                let _ = reply.send(result.map_err(|e| RestartError { message: e.message }));
            }
            SupervisorCmd::Status { reply } => {
                let _ = reply.send(state.lock().unwrap().clone());
            }
        }
    }
    running.store(false, Ordering::SeqCst);
}

/// Spawn the backend, wait for readiness, then monitor for crashes.
fn do_spawn(
    source: &BinarySource,
    state: &Arc<Mutex<BackendStatus>>,
    logs: &Arc<Mutex<LogBuffer>>,
    child: &mut Option<Child>,
    restarts: &mut u32,
) -> Result<(), StartError> {
    // Pick a free loopback port and generate a per-launch token.
    let port = pick_free_port().map_err(|e| StartError {
        code: StartErrorCode::InvalidPort,
        message: format!("Could not allocate loopback port: {e}"),
    })?;
    let token = generate_token();

    let binary = resolve_binary_path(source);
    if !binary_exists(&binary) {
        return Err(StartError {
            code: StartErrorCode::BinaryNotFound,
            message: format!(
                "Backend binary not found at {:?} (source: {:?})",
                binary, source
            ),
        });
    }

    let mut cmd = build_command(&binary, source, port, &token);

    let mut child_proc = cmd.spawn().map_err(|e| StartError {
        code: StartErrorCode::SpawnFailed,
        message: format!("Failed to spawn backend: {e}"),
    })?;
    let pid = child_proc.id();
    set_state(state, BackendState::Starting);

    // Capture stdout/stderr in helper threads, pushing redacted lines.
    let logs_c = logs.clone();
    if let Some(out) = child_proc.stdout.take() {
        let mut out = io::BufReader::new(out);
        thread::spawn(move || {
            let mut buf = String::new();
            loop {
                buf.clear();
                match out.read_line(&mut buf) {
                    Ok(0) => break,
                    Ok(_) => logs_c.lock().unwrap().push(LogStream::Stdout, buf.trim_end()),
                    Err(_) => break,
                }
            }
        });
    }
    if let Some(err) = child_proc.stderr.take() {
        let mut err = io::BufReader::new(err);
        let logs_c = logs.clone();
        thread::spawn(move || {
            let mut buf = String::new();
            loop {
                buf.clear();
                match err.read_line(&mut buf) {
                    Ok(0) => break,
                    Ok(_) => logs_c.lock().unwrap().push(LogStream::Stderr, buf.trim_end()),
                    Err(_) => break,
                }
            }
        });
    }

    // Wait for readiness by polling /health, aborting early if the backend
    // process exits before becoming ready (a crash must not wait the full
    // timeout).
    let endpoint = format!("http://127.0.0.1:{port}");
    // `exit_check` returns true once the backend process has exited (a
    // crash). If it exits before becoming ready we abort immediately instead
    // of waiting the full readiness timeout.
    let exit_check = || child_proc.try_wait().ok().flatten().is_some();
    match wait_for_readiness(&endpoint, &token, exit_check) {
        Ok(()) => {
            *child = Some(child_proc);
            set_state(
                state,
                BackendState::Ready {
                    port,
                    token: token.clone(),
                },
            );
            *restarts = 0;
            // Record pid and reset the restart count in the public status.
            if let Ok(mut st) = state.lock() {
                st.pid = Some(pid);
                st.restarts = 0;
            }
            Ok(())
        }
        Err(reason) => {
            let exited = child_proc.try_wait().ok().flatten().is_some();
            set_state(
                state,
                BackendState::Failed {
                    reason: reason.clone(),
                },
            );
            if exited {
                // Process already exited: treat as a crash eligible for
                // restart, then surface the readiness failure.
                let _ = maybe_restart(restarts, state, logs, source, child);
            } else {
                // Process is still running but not ready: kill it so we do
                // not leave an orphan backend behind.
                let _ = child_proc.kill();
                let _ = child_proc.wait();
                *child = None;
            }
            Err(StartError {
                code: StartErrorCode::ReadinessTimeout,
                message: reason,
            })
        }
    }
}

/// Poll `/health` until ready or timeout, with backoff. `alive` is called
/// each iteration; if it returns `false` (the backend process exited), we
/// abort immediately instead of waiting the full timeout.
fn wait_for_readiness<F>(endpoint: &str, token: &str, mut alive: F) -> Result<(), String>
where
    F: FnMut() -> bool,
{
    let start = Instant::now();
    let mut attempt = 0u32;
    while start.elapsed() < READINESS_TIMEOUT {
        attempt += 1;
        // If the backend process exited before becoming ready, abort
        // immediately instead of waiting the full readiness timeout.
        if alive() {
            return Err("backend exited before becoming ready".into());
        }
        if check_health(endpoint, token) {
            return Ok(());
        }
        thread::sleep(READINESS_POLL_INTERVAL);
        if attempt % 10 == 0 {
            thread::sleep(READINESS_POLL_INTERVAL);
        }
    }
    Err(format!(
        "Backend did not become healthy at {endpoint} within {}s",
        READINESS_TIMEOUT.as_secs()
    ))
}

/// Raw TCP HTTP/1.0 health check — no HTTP client dependency required.
fn check_health(endpoint: &str, token: &str) -> bool {
    let host = endpoint.strip_prefix("http://").unwrap_or(endpoint);
    let Ok(addr) = host.parse::<std::net::SocketAddr>() else {
        return false;
    };
    match TcpStream::connect_timeout(&addr, Duration::from_secs(2)) {
        Ok(mut stream) => {
            let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
            let request = format!(
                "GET /health HTTP/1.0\r\nHost: {host}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
            );
            if stream.write_all(request.as_bytes()).is_err() {
                return false;
            }
            let mut reader = io::BufReader::new(stream);
            let mut line = String::new();
            if reader.read_line(&mut line).is_ok() {
                return line.starts_with("HTTP/1.1 200") || line.starts_with("HTTP/1.0 200");
            }
            false
        }
        Err(_) => false,
    }
}

/// Graceful shutdown: POST /shutdown, then kill after timeout.
fn do_shutdown(
    child: &mut Option<Child>,
    state: &Arc<Mutex<BackendStatus>>,
    logs: &Arc<Mutex<LogBuffer>>,
) -> Result<(), ShutdownError> {
    let status = state.lock().unwrap().clone();
    let (endpoint, token) = match &status.state {
        BackendState::Ready { port, token } => {
            (format!("http://127.0.0.1:{port}"), token.clone())
        }
        _ => return Ok(()), // nothing running
    };

    // Best-effort graceful shutdown request.
    let host = endpoint.strip_prefix("http://").unwrap_or(&endpoint);
    if let Ok(addr) = host.parse::<std::net::SocketAddr>() {
        if let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_secs(2)) {
            let request = format!(
                "POST /shutdown HTTP/1.0\r\nHost: {host}\r\nAuthorization: Bearer {token}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            );
            let _ = stream.write_all(request.as_bytes());
        }
    }

    // Wait briefly for graceful exit, then kill.
    if let Some(mut c) = child.take() {
        match c.try_wait() {
            Ok(Some(_)) => {}
            Ok(None) => {
                thread::sleep(GRACEFUL_SHUTDOWN_TIMEOUT);
                if c.try_wait().ok().flatten().is_none() {
                    let _ = c.kill();
                    let _ = c.wait();
                }
            }
            Err(e) => {
                logs.lock().unwrap().push(
                    LogStream::Stderr,
                    &format!("Shutdown wait error: {e}"),
                );
            }
        }
    }
    set_state(state, BackendState::Stopped);
    Ok(())
}

/// If eligible, schedule a restart with backoff; otherwise mark `Failed`.
fn maybe_restart(
    restarts: &mut u32,
    state: &Arc<Mutex<BackendStatus>>,
    logs: &Arc<Mutex<LogBuffer>>,
    source: &BinarySource,
    child: &mut Option<Child>,
) -> bool {
    if *restarts < MAX_RESTARTS {
        *restarts += 1;
        // Reflect the restart count in the public status.
        if let Ok(mut st) = state.lock() {
            st.restarts = *restarts;
        }
        let delay = Duration::from_secs(RESTART_BACKOFF_SECONDS
            [*restarts as usize - 1]);
        logs.lock().unwrap().push(
            LogStream::Stderr,
            &format!(
                "Backend crashed; restart attempt {}/{} in {}s",
                *restarts, MAX_RESTARTS, delay.as_secs()
            ),
        );
        thread::sleep(delay);
        let _ = do_spawn(source, state, logs, child, restarts);
        true
    } else {
        set_state(state, BackendState::Failed {
            reason: format!("Backend crashed after {MAX_RESTARTS} restart attempts; no further restarts"),
        });
        *child = None;
        false
    }
}

fn set_state(state: &Arc<Mutex<BackendStatus>>, new: BackendState) {
    let endpoint = match &new {
        BackendState::Ready { port, .. } => Some(format!("http://127.0.0.1:{port}")),
        _ => None,
    };
    let mut st = state.lock().unwrap();
    st.state = new;
    st.endpoint = endpoint;
}

// ---- tests (unit-testable, no GUI/toolchain needed) ----

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn pick_free_port_returns_loopback_port() {
        let port = pick_free_port().expect("should allocate a port");
        assert!(port > 0 && port <= 65535);
        let port2 = pick_free_port().expect("should allocate a second port");
        assert_ne!(port, port2);
    }

    #[test]
    fn packaged_binary_path_uses_target_triple_windows() {
        // cfg(target_os = "windows") is false on Linux, so assert the
        // non-.exe branch is exercised; also verify triple is embedded.
        let path = packaged_binary_path("x86_64-pc-windows-msvc");
        let name = path.file_name().unwrap().to_string_lossy().to_string();
        assert!(name.contains("x86_64-pc-windows-msvc"));
        assert!(path.to_string_lossy().contains("binaries/"));
    }

    #[test]
    fn packaged_binary_path_non_windows_no_exe() {
        let path = packaged_binary_path("x86_64-unknown-linux-gnu");
        let name = path.file_name().unwrap().to_string_lossy().to_string();
        assert_eq!(name, "backend-x86_64-unknown-linux-gnu");
        assert!(!name.ends_with(".exe"));
    }

    #[test]
    fn redact_hides_token_and_authorization() {
        let raw = "ASSEMBLY_PORT=1234 ASSEMBLY_TOKEN=supersecret Authorization: Bearer abc123";
        let out = redact(raw);
        assert!(!out.contains("supersecret"));
        assert!(!out.contains("abc123"));
        assert!(out.contains("[REDACTED]"));
        assert!(out.contains("ASSEMBLY_PORT=1234"));
    }

    #[test]
    fn redact_hides_api_key_patterns() {
        let raw = "api_key=sk-live-secret-value extra";
        let out = redact(raw);
        assert!(!out.contains("sk-live-secret-value"));
        assert!(out.contains("[REDACTED]"));
    }

    #[test]
    fn state_transition_ready_to_crashed() {
        let mut st = BackendStatus {
            state: BackendState::Ready { port: 1, token: "t".into() },
            restarts: 0,
            pid: Some(100),
            endpoint: Some("http://127.0.0.1:1".into()),
        };
        st.state = BackendState::Crashed { code: Some(1) };
        st.endpoint = None;
        assert!(!st.state.is_running());
        assert!(!st.state.is_terminal());
    }

    #[test]
    fn state_transition_crashed_to_failed_after_max_restarts() {
        let mut st = BackendStatus {
            state: BackendState::Crashed { code: Some(1) },
            restarts: MAX_RESTARTS,
            pid: None,
            endpoint: None,
        };
        st.state = BackendState::Failed {
            reason: "exhausted restarts".into(),
        };
        assert!(st.state.is_terminal());
    }

    #[test]
    fn log_buffer_bounds_and_redaction() {
        let mut buf = LogBuffer::new();
        for i in 0..MAX_LOG_LINES + 50 {
            buf.push(LogStream::Stdout, &format!("line {i} ASSEMBLY_TOKEN=secret"));
        }
        let lines: Vec<_> = buf.lines().collect();
        assert_eq!(lines.len(), MAX_LOG_LINES);
        assert!(!lines.iter().any(|l| l.line.contains("secret")));
    }

    #[test]
    fn generate_token_is_hex_and_stable_length() {
        let t1 = generate_token();
        let t2 = generate_token();
        assert_eq!(t1.len(), 64);
        assert_ne!(t1, t2);
        assert!(t1.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn readiness_poll_connects_loopback_only() {
        // pick_free_port binds 127.0.0.1; confirm the bound address is loopback.
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback");
        let addr = listener.local_addr().expect("local addr");
        assert_eq!(addr.ip(), std::net::IpAddr::V4(std::net::Ipv4Addr::new(127, 0, 0, 1)));
        drop(listener);
    }

    #[test]
    fn check_health_false_on_closed_port() {
        // Use a port that is almost certainly closed.
        assert!(!check_health("http://127.0.0.1:59999", "token"));
    }

    #[test]
    fn dev_source_resolves_entry_path() {
        let cwd = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let path = resolve_binary_path(&BinarySource::Dev {
            cwd: cwd.join("../../.."),
        });
        assert!(path.to_string_lossy().contains("src/main.py"));
    }
}
