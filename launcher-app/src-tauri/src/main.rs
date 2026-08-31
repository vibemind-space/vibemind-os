// Tauri 2 entrypoint — delegates to lib.rs::run().
// `cargo_check_disable_warnings`-style boilerplate so a windows release
// build has no console window attached.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    vibemind_launcher_lib::run();
}
