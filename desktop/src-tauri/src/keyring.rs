//! OS keyring integration for provider API keys.
//!
//! The `KeyRing` trait is abstracted so unit tests can use an in-memory
//! backend instead of the OS keyring (Windows Credential Manager,
//! macOS Keychain, GNOME Keyring / SecretService on Linux).
//!
//! Secrets never leave this module as plaintext across IPC unless explicitly
//! requested via `read_key`. The backend reads keys server-side from the OS
//! keyring, so the webview normally never needs the raw value.

use serde::{Deserialize, Serialize};
use keyring::Entry;
use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

/// Stable service name, consistent with the product identity from issue #92
/// and with `src/core/keystore.py` (`KeyringKeyStore(service = "Assembly")`).
pub const SERVICE: &str = "Assembly";

/// Typed keyring error.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeyRingError {
    pub code: String,
    pub message: String,
}

impl std::fmt::Display for KeyRingError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for KeyRingError {}

/// Abstraction over OS-encrypted storage. Implementations:
/// - `OsKeyring`: real OS keyring (production desktop).
/// - `MemoryKeyring`: in-memory (tests only).
pub trait KeyRing: Send + Sync {
    fn set(&self, service: &str, user: &str, password: &str) -> Result<(), KeyRingError>;
    fn get(&self, service: &str, user: &str) -> Result<Option<String>, KeyRingError>;
    fn delete(&self, service: &str, user: &str) -> Result<(), KeyRingError>;
}

/// Production implementation backed by the `keyring` crate.
pub struct OsKeyring;

impl KeyRing for OsKeyring {
    fn set(&self, service: &str, user: &str, password: &str) -> Result<(), KeyRingError> {
        keyring::set_password(service, user, password)
            .map_err(|e| KeyRingError { code: "keyring_set_failed".into(), message: e.to_string() })
    }
    fn get(&self, service: &str, user: &str) -> Result<Option<String>, KeyRingError> {
        keyring::get_password(service, user)
            .map_err(|e| KeyRingError { code: "keyring_get_failed".into(), message: e.to_string() })
    }
    fn delete(&self, service: &str, user: &str) -> Result<(), KeyRingError> {
        keyring::delete_password(service, user)
            .map_err(|e| KeyRingError { code: "keyring_delete_failed".into(), message: e.to_string() })
    }
}

/// In-memory implementation for unit tests.
#[derive(Debug, Clone, Default)]
pub struct MemoryKeyring {
    store: Arc<Mutex<HashMap<(String, String), String>>>,
}

impl MemoryKeyring {
    pub fn new() -> Self {
        Self::default()
    }
}

impl KeyRing for MemoryKeyring {
    fn set(&self, service: &str, user: &str, password: &str) -> Result<(), KeyRingError> {
        self.store.lock().unwrap().insert((service.to_string(), user.to_string()), password.to_string());
        Ok(())
    }
    fn get(&self, service: &str, user: &str) -> Result<Option<String>, KeyRingError> {
        Ok(self.store.lock().unwrap().get(&(service.to_string(), user.to_string())).cloned())
    }
    fn delete(&self, service: &str, user: &str) -> Result<(), KeyRingError> {
        self.store.lock().unwrap().remove(&(service.to_string(), user.to_string()));
        Ok(())
    }
}

// ── Convenience commands backed by the OS keyring (process-global) ─────

static OS_KEYRING: std::sync::OnceLock<OsKeyring> = std::sync::OnceLock::new();

fn os_keyring() -> &'static OsKeyring {
    OS_KEYRING.get_or_init(OsKeyring::new)
}

pub fn save_key(provider: &str, key: &str) -> Result<(), KeyRingError> {
    os_keyring().set(SERVICE, provider, key)
}

pub fn has_key(provider: &str) -> Result<bool, KeyRingError> {
    Ok(os_keyring().get(SERVICE, provider)?.is_some())
}

pub fn delete_key(provider: &str) -> Result<(), KeyRingError> {
    os_keyring().delete(SERVICE, provider)
}

pub fn read_key(provider: &str) -> Result<Option<String>, KeyRingError> {
    os_keyring().get(SERVICE, provider)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn memory_keyring_roundtrip() {
        let kr = MemoryKeyring::new();
        assert!(!kr.get(SERVICE, "gemini").unwrap().is_some());
        kr.set(SERVICE, "gemini", "secret-key-value").unwrap();
        assert!(kr.has_key(SERVICE, "gemini").unwrap());
        assert_eq!(kr.get(SERVICE, "gemini").unwrap().as_deref(), Some("secret-key-value"));
        // Other providers unaffected.
        assert!(!kr.get(SERVICE, "groq").unwrap().is_some());
        kr.delete(SERVICE, "gemini").unwrap();
        assert!(!kr.has_key(SERVICE, "gemini").unwrap());
    }

    #[test]
    fn memory_keyring_delete_missing_is_noop() {
        let kr = MemoryKeyring::new();
        kr.delete(SERVICE, "nonexistent").unwrap(); // must not error
    }
}
