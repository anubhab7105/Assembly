//! Assembly desktop shell (Tauri v2).
//!
//! Windows x86_64-pc-windows-msvc is the target platform. All Tauri /
//! OS-keyring / Windows Job Object integration is gated behind
//! `#[cfg(all(windows, feature = "desktop"))]`. The pure, host-agnostic logic
//! (state machine, port picking, input validation, in-memory credential store)
//! lives in `sidecar_core`, `keyring` and `errors` and compiles on any host.
//!
//! Non-Windows / non-desktop builds provide a no-op `run()` so `cargo
//! check`/`cargo test --no-default-features` works on Linux CI without dbus.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod errors;
mod keyring;
mod sidecar_core;

#[cfg(all(windows, feature = "desktop"))]
mod sidecar;

#[cfg(not(all(windows, feature = "desktop")))]
mod stub;

pub use errors::Error;
pub use keyring::{service_name, CredentialStore};
pub use sidecar_core::{
    validate_provider, validate_secret, validate_window_label, APP_MODE_ENV, BACKEND_PORT_ENV,
    BACKEND_TOKEN_ENV, MAIN_WINDOW_LABEL, READINESS_TOTAL_MS, SIDECAR_DEV_PATH_ENV,
};

use std::sync::Arc;

#[cfg(all(windows, feature = "desktop"))]
use tauri::Manager;

/// Entrypoint. Builds the Tauri app with the sidecar manager, keyring store
/// and validated IPC commands, then runs the event loop.
#[cfg(all(windows, feature = "desktop"))]
pub fn run() {
    use crate::keyring::KeyringStore;
    use crate::sidecar::SidecarManager;

    let manager = Arc::new(SidecarManager::new());
    let manager_clone = manager.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_single_instance::init(|_app, _args, _cwd| {
                // Single-instance guard: a second app copy focuses the main
                // window instead of spawning a competing sidecar.
                if let Some(window) = _app.get_webview_window(MAIN_WINDOW_LABEL) {
                    let _ = window.set_focus();
                }
            }),
        )
        .manage(manager_clone)
        .manage(crate::keyring::CredentialState::new(KeyringStore::new()))
        .setup(move |app| {
            let handle = app.handle().clone();
            let mgr = manager.clone();
            // Start the backend sidecar as part of app launch (no developer
            // process required). Failure is surfaced via state/events, not a
            // crash of the shell.
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = mgr.start_backend(app_handle).await {
                    tracing::error!("sidecar startup failed: {e}");
                }
            });
            // Shutdown hook: on main-window close, shut down the backend
            // sidecar gracefully, then force-kill after a short grace.
            let mgr2 = manager.clone();
            if let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) {
                let mgr3 = mgr2.clone();
                window.on_window_event(move |_window, event| {
                    use tauri::WindowEvent;
                    match event {
                        WindowEvent::CloseRequested { .. } => {
                            let _ = mgr3.stop_backend(graceful);
                            // Allow the close to proceed.
                        }
                        WindowEvent::Destroyed { .. } => {
                            let _ = mgr3.stop_backend(force);
                        }
                        _ => {}
                    }
                });
            }
            let _ = handle;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            backend_status,
            backend_restart,
            credential_save,
            credential_get,
            credential_exists,
            credential_delete,
            credential_list,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");

    fn graceful() {}
    fn force() {}
}

/// No-op entrypoint on non-Windows / non-desktop builds so the crate compiles
/// and its pure modules can be tested on any host.
#[cfg(not(all(windows, feature = "desktop")))]
pub fn run() {
    // The Tauri desktop shell only targets Windows. On other hosts this is a
    // stub so `cargo check --no-default-features` and the pure-logic unit
    // tests run in Linux CI.
}
