// Run tauri-build's codegen only when the `desktop` feature is enabled, so
// `--no-default-features` compiles the pure logic on any host without
// requiring the tauri runtime (dbus on Linux, etc.).
#[cfg(feature = "desktop")]
fn main() {
    tauri_build::build();
}

#[cfg(not(feature = "desktop"))]
fn main() {}
