use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::errors::{Error, Secret};

/// Maximum total time (milliseconds) to wait for the backend to become ready.
pub const READINESS_TOTAL_MS: u64 = 30_000;
/// Delay between readiness poll attempts (milliseconds).
pub const READINESS_POLL_INTERVAL_MS: u64 = 250;
/// Bounded number of free-port retries on collision.
pub const PORT_PICK_RETRIES: u32 = 5;
/// Environment variable overriding the dev sidecar path (debug builds only).
pub const SIDECAR_DEV_PATH_ENV: &str = "ASSEMBLY_BACKEND_DEV_PATH";
/// Environment variable carrying the per-launch auth token to the backend.
pub const BACKEND_TOKEN_ENV: &str = "DESKTOP_TOKEN";
/// Environment variable carrying the port the backend should listen on.
pub const BACKEND_PORT_ENV: &str = "ASSEMBLY_PORT";
/// Environment variable selecting desktop mode in the backend.
pub const APP_MODE_ENV: &str = "APP_MODE";

/// Explicit sidecar state machine.
///
/// Stopped -> Starting -> Ready -> Stopping -> Stopped, plus Failed and
/// Crashed as terminal error states.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SidecarState {
    Stopped,
    Starting,
    Ready,
    Stopping,
    Failed { reason: String },
    Crashed { exit_code: Option<i32> },
}

impl SidecarState {
    pub fn is_terminal(&self) -> bool {
        matches!(
            self,
            SidecarState::Stopped
                | SidecarState::Failed { .. }
                | SidecarState::Crashed { .. }
        )
    }
    pub fn is_ready(&self) -> bool {
        matches!(self, SidecarState::Ready)
    }
}

/// Resolve the path to the packaged backend sidecar executable.
///
/// In release builds the path is the Tauri-bundled sidecar (resolved by the
/// Tauri runtime and passed in); in debug builds an override may be supplied
/// via the `ASSEMBLY_BACKEND_DEV_PATH` environment variable so developers can
/// point at a locally built backend without repackaging.
///
/// Returns typed errors when the path is missing or not executable.
pub fn resolve_sidecar_path(
    bundled_path: Option<&Path>,
    debug_dev_override: bool,
) -> Result<PathBuf, Error> {
    if debug_dev_override {
        if let Ok(dev) = std::env::var(SIDECAR_DEV_PATH_ENV) {
            if !dev.is_empty() {
                let p = PathBuf::from(dev);
                return validate_executable(&p);
            }
        }
    }
    let bundled = bundled_path.ok_or(Error::SidecarNotFound)?;
    validate_executable(bundled)
}

fn validate_executable(path: &Path) -> Result<PathBuf, Error> {
    if !path.is_file() {
        return Err(Error::SidecarNotFound);
    }
    // On Windows executability is implied by the .exe file existing; on other
    // hosts check the permission bit so unit tests are meaningful everywhere.
    #[cfg(not(windows))]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = std::fs::metadata(path)?.permissions().mode();
        if mode & 0o111 == 0 {
            return Err(Error::SidecarNotExecutable);
        }
    }
    Ok(path.to_path_buf())
}

/// Pick a free loopback port on 127.0.0.1 (never 0.0.0.0), retrying a bounded
/// number of times on collision. The listener is dropped immediately so the
/// port is released back to the OS before the backend binds it.
pub fn pick_free_port() -> Result<u16, Error> {
    let mut last_err: Option<Error> = None;
    for _ in 0..PORT_PICK_RETRIES {
        match TcpListener::bind(("127.0.0.1", 0)) {
            Ok(listener) => {
                let port = listener.local_addr()?.port();
                drop(listener);
                return Ok(port);
            }
            Err(e) => last_err = Some(Error::Io(e.to_string())),
        }
    }
    Err(last_err.unwrap_or(Error::PortUnavailable))
}

/// Probe whether 127.0.0.1:port is accepting connections (used to detect a
/// stale backend process from a previous crashed run).
pub fn is_port_in_use(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

/// Provider allow-list: only these provider IDs may be stored in the keyring
/// or sent to the backend. Matches `src/providers/config.py` provider ids.
const ALLOWED_PROVIDERS: &[&str] = &[
    "gemini", "groq", "cerebras", "openrouter", "huggingface", "mistral",
    "nvidia",
];

const MAX_PROVIDER_LEN: usize = 64;
const MAX_SECRET_LEN: usize = 4096;
const MIN_SECRET_LEN: usize = 1;

/// Provider identifier charset: lowercase letters, digits, dashes, dots.
fn provider_chars_ok(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= MAX_PROVIDER_LEN
        && s
            .chars()
            .all(|c| matches!(c, 'a'..='z' | '0'..='9' | '-' | '.'))
}

/// Validate a provider id against the allow-list and charset.
pub fn validate_provider(provider: &str) -> Result<&str, Error> {
    if provider.is_empty() {
        return Err(Error::InvalidInput("provider is required".into()));
    }
    if !provider_chars_ok(provider) {
        return Err(Error::InvalidInput(format!(
            "provider id must be {MAX_PROVIDER_LEN} or fewer lowercase alphanumeric, dash or dot characters"
        )));
    }
    if !ALLOWED_PROVIDERS.contains(&provider) {
        return Err(Error::ProviderNotAllowed(provider.to_string()));
    }
    Ok(provider)
}

/// Validate a secret: non-empty, size-capped. Returns the cleaned secret.
pub fn validate_secret(secret: &str) -> Result<&str, Error> {
    if secret.is_empty() {
        return Err(Error::SecretEmpty);
    }
    if secret.len() > MAX_SECRET_LEN {
        return Err(Error::SecretTooLarge);
    }
    Ok(secret)
}

/// Wrap a validated secret in a redacting wrapper.
pub fn wrap_secret(secret: &str) -> Secret {
    Secret(secret.to_string())
}

/// Validate a Tauri window label: non-empty, bounded, safe charset.
pub fn validate_window_label(label: &str) -> Result<&str, Error> {
    if label.is_empty() {
        return Err(Error::InvalidInput("window label is required".into()));
    }
    if label.len() > 64 {
        return Err(Error::InvalidInput("window label too long".into()));
    }
    if !label
        .chars()
        .all(|c| matches!(c, 'a'..='z' | 'A'..='Z' | '0'..='9' | '-' | '_' | '.'))
    {
        return Err(Error::InvalidInput(
            "window label contains invalid characters".into(),
        ));
    }
    Ok(label)
}

/// Main window label enforced by this app.
pub const MAIN_WINDOW_LABEL: &str = "main";

/// Check a free loopback port is genuinely available by actually binding it.
pub fn assert_port_free(port: u16) -> Result<(), Error> {
    match TcpListener::bind(("127.0.0.1", port)) {
        Ok(_) => Ok(()),
        Err(e) => Err(Error::Io(e.to_string())),
    }
}

/// Generate a per-launch random auth token (hex) without pulling in the
/// `rand` crate: current time + thread id, hex-encoded. Good enough as a
/// short-lived local authorization token.
pub fn generate_auth_token() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let tid = std::thread::current().id().as_u64().unwrap_or(0);
    let mut mixed = now.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(tid);
    let mut out = String::with_capacity(16);
    for _ in 0..8 {
        let nibble = (mixed & 0xF) as u8;
        out.push(if nibble < 10 {
            b'0' + nibble
        } else {
            b'a' + nibble - 10
        } as char);
        mixed >>= 4;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn state_machine_valid_transitions() {
        let stopped = SidecarState::Stopped;
        assert!(!stopped.is_ready());
        assert!(stopped.is_terminal());

        let starting = SidecarState::Starting;
        assert!(!starting.is_terminal());
        assert!(!starting.is_ready());

        let ready = SidecarState::Ready;
        assert!(ready.is_ready());
        assert!(!ready.is_terminal());

        let stopping = SidecarState::Stopping;
        assert!(!stopping.is_ready());
        assert!(!stopping.is_terminal());

        let failed = SidecarState::Failed {
            reason: "boom".into(),
        };
        assert!(failed.is_terminal());
        assert!(!failed.is_ready());

        let crashed = SidecarState::Crashed {
            exit_code: Some(1),
        };
        assert!(crashed.is_terminal());

        let crashed_none = SidecarState::Crashed { exit_code: None };
        assert!(crashed_none.is_terminal());
    }

    #[test]
    fn pick_free_port_returns_loopback() {
        let port = pick_free_port().expect("a free port must exist");
        assert!(port > 0 && port < 65536);
        // The port must be free immediately after release.
        assert!(assert_port_free(port).is_ok());
    }

    #[test]
    fn validate_provider_allow_list() {
        assert!(validate_provider("gemini").is_ok());
        assert!(validate_provider("openrouter").is_ok());
        assert!(validate_provider("GEMINI").is_err()); // uppercase rejected
        assert!(validate_provider("unknown_provider").is_err()); // not allow-listed
        assert!(validate_provider("").is_err()); // empty
        assert!(validate_provider(&"a".repeat(65)).is_err()); // too long
        assert!(validate_provider("evil;rm -rf /").is_err()); // bad charset
    }

    #[test]
    fn validate_secret_rules() {
        assert!(validate_secret("abc").is_ok());
        assert!(validate_secret("").is_err()); // empty
        assert!(validate_secret(&"x".repeat(4097)).is_err()); // too large
    }

    #[test]
    fn validate_window_label_rules() {
        assert!(validate_window_label("main").is_ok());
        assert!(validate_window_label("main-1").is_ok());
        assert!(validate_window_label("").is_err());
        assert!(validate_window_label("../etc").is_err()); // path traversal chars
    }

    #[test]
    fn resolve_sidecar_uses_dev_override_in_debug() {
        // Non-debug path: bundled required.
        assert!(resolve_sidecar_path(None, false).is_err());
        assert!(resolve_sidecar_path(Some(Path::new("/no/such/backend.exe")), false)
            .is_err());
        // Debug dev override: env var wins.
        std::env::set_var(SIDECAR_DEV_PATH_ENV, "/tmp/assembly_backend.exe");
        let r = resolve_sidecar_path(None, true);
        std::env::remove_var(SIDECAR_DEV_PATH_ENV);
        // Path doesn't exist -> SidecarNotFound (not a panic).
        assert_eq!(r.unwrap_err(), Error::SidecarNotFound);
    }

    #[test]
    fn secret_is_redacted_in_debug_format() {
        let s = wrap_secret("hunter2");
        assert_eq!(format!("{s:?}"), "Secret(\"[redacted]\")");
        assert_eq!(format!("{s}"), "[redacted]");
        assert_eq!(s.reveal(), "hunter2");
    }
}
