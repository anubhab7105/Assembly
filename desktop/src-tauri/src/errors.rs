use serde::{Deserialize, Serialize};

/// Typed, serializable errors returned by Tauri commands and the sidecar
/// manager. Never embed secrets or raw user input in the variants — error
/// messages are safe to surface to the UI and to log.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "code", content = "message", rename_all = "snake_case")]
pub enum Error {
    /// The bundled backend sidecar executable could not be resolved.
    SidecarNotFound,
    /// The resolved sidecar exists but is not executable.
    SidecarNotExecutable,
    /// Spawning the sidecar failed (message describes the cause).
    SidecarStartFailed(String),
    /// No free loopback port could be found after bounded retries.
    PortUnavailable,
    /// The backend did not report healthy before the readiness deadline.
    /// The captured stderr tail is carried in the message.
    ReadinessTimeout(String),
    /// The backend process exited unexpectedly.
    ProcessCrashed { exit_code: Option<i32> },
    /// Graceful/forced shutdown of the backend failed.
    ShutdownFailed(String),
    /// Input failed validation (length, charset, provider allow-list, …).
    InvalidInput(String),
    /// Provider is not on the allow-list.
    ProviderNotAllowed(String),
    /// Secret was empty.
    SecretEmpty,
    /// Secret exceeded the size cap.
    SecretTooLarge,
    /// The OS keyring is unavailable on this machine.
    KeyringUnavailable(String),
    /// No credential is stored for the given provider.
    CredentialNotFound,
    /// The command was invoked from a disallowed window label.
    UnauthorizedWindow,
    /// Underlying I/O / OS error (message is the OS error, no secrets).
    Io(String),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::SidecarNotFound => write!(f, "backend sidecar not found"),
            Error::SidecarNotExecutable => write!(f, "backend sidecar is not executable"),
            Error::SidecarStartFailed(m) => write!(f, "failed to start backend sidecar: {m}"),
            Error::PortUnavailable => write!(f, "no free loopback port available"),
            Error::ReadinessTimeout(tail) => {
                write!(f, "backend did not become ready in time. stderr tail: {tail}")
            }
            Error::ProcessCrashed { exit_code } => match exit_code {
                Some(code) => write!(f, "backend process crashed with exit code {code}"),
                None => write!(f, "backend process crashed"),
            },
            Error::ShutdownFailed(m) => write!(f, "backend shutdown failed: {m}"),
            Error::InvalidInput(m) => write!(f, "invalid input: {m}"),
            Error::ProviderNotAllowed(p) => write!(f, "provider not allowed: {p}"),
            Error::SecretEmpty => write!(f, "secret must not be empty"),
            Error::SecretTooLarge => write!(f, "secret exceeds the size limit"),
            Error::KeyringUnavailable(m) => write!(f, "OS keyring unavailable: {m}"),
            Error::CredentialNotFound => write!(f, "no credential stored for that provider"),
            Error::UnauthorizedWindow => write!(f, "command not allowed from this window"),
            Error::Io(m) => write!(f, "I/O error: {m}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Error::Io(e.to_string())
    }
}

/// A redacting wrapper for secret values. `Debug`/`Display` never reveal the
/// contents so secrets can never leak into logs or error strings.
#[derive(Clone, PartialEq, Eq)]
pub struct Secret(pub String);

impl std::fmt::Debug for Secret {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_tuple("Secret").field(&"[redacted]").finish()
    }
}

impl std::fmt::Display for Secret {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("[redacted]")
    }
}

impl Secret {
    pub fn reveal(&self) -> &str {
        &self.0
    }
}
