// VibeMind Launcher — Tauri 2 backend.
//
// Two commands the UI invokes via @tauri-apps/api/core invoke():
//   start_stack()  — spawns `pwsh.exe -NoProfile -File scripts/vibemind-start.ps1`
//   stop_stack()   — spawns `pwsh.exe -NoProfile -File scripts/vibemind-stop.ps1`
//
// stdout/stderr of the spawned child are streamed back to the UI as
// `log` events (event payload: { stream: "out"|"err", line: "...", ts: ms }).
// When the child exits, an `exit` event fires with { code: <i32>, kind: "start"|"stop" }.
//
// Repo-root resolution: walk parent dirs from the bundle exe until we
// find `infra/swarm/vibemind-stack.yml`. Works whether the .exe is run
// from build output (`src-tauri/target/release/`) or from a desktop
// shortcut placed anywhere. Falls back to CWD if not found.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Clone, Serialize)]
struct LogLine {
    stream: String,
    line: String,
    ts: u64,
}

#[derive(Clone, Serialize)]
struct ExitInfo {
    kind: String, // "start" or "stop"
    code: i32,
}

fn now_ms() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn find_repo_root() -> Option<PathBuf> {
    // 1. CWD walk (most reliable when launched from a shortcut whose
    //    "Start in" is set to the repo root).
    if let Ok(cwd) = std::env::current_dir() {
        if let Some(p) = walk_for_marker(&cwd) {
            return Some(p);
        }
    }
    // 2. Walk up from the exe path (handles cases where shortcut
    //    "Start in" isn't set).
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            if let Some(p) = walk_for_marker(parent) {
                return Some(p);
            }
        }
    }
    None
}

fn walk_for_marker(start: &Path) -> Option<PathBuf> {
    let marker = Path::new("infra").join("swarm").join("vibemind-stack.yml");
    let mut cur: PathBuf = start.to_path_buf();
    for _ in 0..10 {
        if cur.join(&marker).exists() {
            return Some(cur);
        }
        if !cur.pop() {
            break;
        }
    }
    None
}

fn spawn_script(app: AppHandle, script: &str, kind: &'static str) -> Result<(), String> {
    let repo = find_repo_root().ok_or_else(|| {
        "Repo root not found — could not locate infra/swarm/vibemind-stack.yml \
         in any parent of CWD or the launcher exe."
            .to_string()
    })?;
    let script_path = repo.join("scripts").join(script);
    if !script_path.exists() {
        return Err(format!("script not found: {}", script_path.display()));
    }

    // Use pwsh (PowerShell 7+) — same shell the user uses, same
    // behaviour as a desktop double-click on the .ps1.
    let mut cmd = Command::new("pwsh.exe");
    cmd.arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(&script_path)
        .current_dir(&repo)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn failed: {e} — is pwsh.exe in PATH?"))?;

    // Stream stdout
    if let Some(stdout) = child.stdout.take() {
        let app_clone = app.clone();
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for raw in reader.lines() {
                if let Ok(line) = raw {
                    let _ = app_clone.emit(
                        "log",
                        LogLine {
                            stream: "out".into(),
                            line,
                            ts: now_ms(),
                        },
                    );
                }
            }
        });
    }

    // Stream stderr
    if let Some(stderr) = child.stderr.take() {
        let app_clone = app.clone();
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for raw in reader.lines() {
                if let Ok(line) = raw {
                    let _ = app_clone.emit(
                        "log",
                        LogLine {
                            stream: "err".into(),
                            line,
                            ts: now_ms(),
                        },
                    );
                }
            }
        });
    }

    // Wait + emit exit event
    let app_clone = app.clone();
    let kind_s = kind.to_string();
    thread::spawn(move || {
        let code = child
            .wait()
            .map(|s| s.code().unwrap_or(-1))
            .unwrap_or(-1);
        let _ = app_clone.emit(
            "exit",
            ExitInfo {
                kind: kind_s,
                code,
            },
        );
    });

    Ok(())
}

#[tauri::command]
fn start_stack(app: AppHandle) -> Result<(), String> {
    spawn_script(app, "vibemind-start.ps1", "start")
}

#[tauri::command]
fn stop_stack(app: AppHandle) -> Result<(), String> {
    spawn_script(app, "vibemind-stop.ps1", "stop")
}

#[tauri::command]
fn repo_root_path() -> Result<String, String> {
    find_repo_root()
        .map(|p| p.display().to_string())
        .ok_or_else(|| "repo root not found".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![start_stack, stop_stack, repo_root_path])
        .setup(|app| {
            // surface the resolved repo root in the window title for sanity
            if let Some(window) = app.get_webview_window("main") {
                if let Some(root) = find_repo_root() {
                    let _ = window.set_title(&format!("VibeMind — {}", root.display()));
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
