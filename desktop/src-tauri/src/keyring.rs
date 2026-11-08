use std::collections::HashMap;
use std::sync::RwLock;

use crate::errors::{Error, Secret};
use crate::sidecar_core::validate_provider;

/// OS-credential-store abstraction. Desktop secrets live in the OS keyring
/// (Windows Credential Manager) only — never in plain files, SQLite, logs,
/// browser storage, or the Tauri store plugin.
///
/// Implementations:
/// - `KeyringStore` (Windows, `#[cfg(windows)]`): Windows Credential Manager
///   via the `keyring` crate (`windows-native` feature).
/// - `InMemoryStore`: process-memory store for unit tests on any host.
pub trait CredentialStore: Send + Sync {
    /// Store (or replace) a secret for a provider. Provider must be validated.
    fn save(&self, provider: &str, secret: &Secret) -> Result<(), Error>;
    /// Return the secret for a provider, or `None` if absent. The caller
    /// must treat the returned value as secret and keep it in memory only.
    fn get(&self, provider: &str) -> Result<Option<Secret>, Error>;
    /// Return `true` if a credential is held for the provider, without
    /// revealing the value.
    fn exists(&self, provider: &str) -> Result<bool, Error>;
    /// Delete the credential for a provider. No-op if absent.
    fn delete(&self, provider: &str) -> Result<(), Error>;
    /// Provider names only — never values.
    fn list(&self) -> Result<Vec<String>, Error>;
}

/// Service name derived from the Tauri app identifier
/// (`com.ankush-das.tauri-app` in `tauri.conf.json`).
pub fn service_name() -> String {
    "Assembly".to_string()
}

/// Holds a `CredentialStore` for registration as Tauri `State`.
pub struct CredentialState {
    store: Box<dyn CredentialStore>,
}

impl CredentialState {
    pub fn new(store: impl CredentialStore + 'static) -> Self {
        Self { store: Box::new(store) }
    }

    pub fn save(&self, provider: &str, secret: &Secret) -> Result<(), Error> {
        self.store.save(provider, secret)
    }

    pub fn get(&self, provider: &str) -> Result<Option<Secret>, Error> {
        self.store.get(provider)
    }

    pub fn exists(&self, provider: &str) -> Result<bool, Error> {
        self.store.exists(provider)
    }

    pub fn delete(&self, provider: &str) -> Result<(), Error> {
        self.store.delete(provider)
    }

    pub fn list(&self) -> Result<Vec<String>, Error> {
        self.store.list()
    }
}

// ────────────────────────────────────────────────────────────
// In-memory implementation (tests, any host)
// ────────────────────────────────────────────────────────────

/// In-memory credential store. Holds `Secret` values (redacting `Debug`)
/// purely for unit testing; not used in production desktop builds.
#[derive(Debug, Default)]
pub struct InMemoryStore {
    inner: RwLock<HashMap<String, Secret>>,
}

impl InMemoryStore {
    pub fn new() -> Self {
        Self::default()
    }
}

impl CredentialStore for InMemoryStore {
    fn save(&self, provider: &str, secret: &Secret) -> Result<(), Error> {
        validate_provider(provider)?;
        self.inner
            .write()
            .unwrap()
            .insert(provider.to_string(), secret.clone());
        Ok(())
    }

    fn get(&self, provider: &str) -> Result<Option<Secret>, Error> {
        validate_provider(provider)?;
        Ok(self.inner.read().unwrap().get(provider).cloned())
    }

    fn exists(&self, provider: &str) -> Result<bool, Error> {
        validate_provider(provider)?;
        Ok(self.inner.read().unwrap().contains_key(provider))
    }

    fn delete(&self, provider: &str) -> Result<(), Error> {
        validate_provider(provider)?;
        self.inner.write().unwrap().remove(provider);
        Ok(())
    }

    fn list(&self) -> Result<Vec<String>, Error> {
        Ok(self
            .inner
            .read()
            .unwrap()
            .keys()
            .cloned()
            .collect::<Vec<_>>())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn in_memory_save_get_delete_list() {
        let store = InMemoryStore::new();
        assert!(!store.exists("gemini").unwrap());
        assert_eq!(store.list().unwrap(), Vec::<String>::new());

        let secret = crate::sidecar_core::wrap_secret("sk-test123");
        store.save("gemini", &secret).unwrap();
        assert!(store.exists("gemini").unwrap());
        assert_eq!(store.get("gemini").unwrap().unwrap().reveal(), "sk-test123");
        assert_eq!(store.list().unwrap(), vec!["gemini".to_string()]);

        store.delete("gemini").unwrap();
        assert!(!store.exists("gemini").unwrap());
        assert_eq!(store.get("gemini").unwrap(), None);
        assert_eq!(store.list().unwrap(), Vec::<String>::new());
    }

    #[test]
    fn in_memory_rejects_bad_provider() {
        let store = InMemoryStore::new();
        let secret = crate::sidecar_core::wrap_secret("sk-test123");
        assert!(store.save("GEMINI", &secret).is_err()); // uppercase
        assert!(store.save("bad;provider", &secret).is_err());
        assert!(store.save("", &secret).is_err());
        assert!(store.get("GEMINI").is_err());
        assert!(store.delete("bad;provider").is_err());
    }

    #[test]
    fn secret_values_never_appear_in_list() {
        let store = InMemoryStore::new();
        store
            .save("groq", &crate::sidecar_core::wrap_secret("super-secret"))
            .unwrap();
        let names = store.list().unwrap();
        assert_eq!(names, vec!["groq".to_string()]);
        assert!(!names.iter().any(|n| n.contains("super-secret")));
    }
}

// ────────────────────────────────────────────────────────────
// Windows Credential Manager implementation
// ────────────────────────────────────────────────────────────

#[cfg(windows)]
mod windows_impl {
    use super::*;

    /// Windows Credential Manager backend (service name from tauri.conf.json
    /// app identifier). Keys never touch disk outside Credential Manager.
    #[derive(Debug, Default, Clone)]
    pub struct KeyringStore;

    impl KeyringStore {
        pub fn new() -> Self {
            Self
        }
    }

    impl CredentialStore for KeyringStore {
        fn save(&self, provider: &str, secret: &Secret) -> Result<(), Error> {
            validate_provider(provider)?;
            let value = secret.reveal();
            if value.is_empty() {
                return Err(Error::SecretEmpty);
            }
            keyring::set_password(&service_name(), provider, value)
                .map_err(|e| Error::KeyringUnavailable(e.to_string()))
        }

        fn get(&self, provider: &str) -> Result<Option<Secret>, Error> {
            validate_provider(provider)?;
            match keyring::get_password(&service_name(), provider) {
                Ok(Some(value)) if !value.is_empty() => {
                    Ok(Some(crate::sidecar_core::wrap_secret(&value)))
                }
                _ => Ok(None),
            }
        }

        fn exists(&self, provider: &str) -> Result<bool, Error> {
            validate_provider(provider)?;
            match keyring::get_password(&service_name(), provider) {
                Ok(Some(value)) if !value.is_empty() => Ok(true),
                _ => Ok(false),
            }
        }

        fn delete(&self, provider: &str) -> Result<(), Error> {
            validate_provider(provider)?;
            // Deleting a missing entry is fine: Credential Manager may error,
            // which we treat as already-absent.
            let _ = keyring::delete_password(&service_name(), provider);
            Ok(())
        }

        fn list(&self) -> Result<Vec<String>, Error> {
            // Credential Manager has no generic "enumerate by service" API,
            // so we probe the known provider catalog and report those present.
            let providers = [
                "gemini", "groq", "cerebras", "openrouter", "huggingface",
                "mistral", "nvidia",
            ];
            let mut found = Vec::new();
            for p in providers {
                if self.exists(p).unwrap_or(false) {
                    found.push(p.to_string());
                }
            }
            found.sort();
            Ok(found)
        }
    }
}

#[cfg(windows)]
pub use windows_impl::KeyringStore;
