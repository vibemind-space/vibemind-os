# VibeMind Launcher

Cross-platform Tauri 2 launcher app for the VibeMind server-mode start/stop
scripts (`scripts/vibemind-start.ps1` / `scripts/vibemind-stop.ps1`).

A small window with an animated star-circle (mirrors the project logo)
and Start / Stop / Clear-Log buttons. Spawns the matching PowerShell
script as a child process and streams stdout/stderr live into the
log pane below.

Cross-platform by design: WebView2 on Windows, WebKit on macOS,
WebKitGTK on Linux. ~3-5 MB release binary.

## Why not Electron

We have an Electron toolchain in the repo already (`vibemind-os/voice/
electron-app`), but Tauri's release binary is ~15× smaller (~3 MB vs
~80 MB) because the OS-native WebView replaces the bundled Chromium.

## Requirements

- **Rust** ≥ 1.77 (`rustc --version`)
- **Node** ≥ 20 (`node --version`)
- **WebView2 Runtime** on Windows (pre-installed on Windows 11; on
  Windows 10 install from <https://developer.microsoft.com/microsoft-edge/webview2/>).

## Build

```powershell
# from this directory
cd vibemind-os/launcher-app

# install JS deps (just @tauri-apps/cli + api)
npm install

# dev (hot-reload, opens a window):
npm run dev

# release (writes src-tauri/target/release/VibeMind Launcher.exe):
npm run build

# create a Desktop shortcut to the release binary:
pwsh -File .\install-desktop-shortcut.ps1
# remove the shortcut later:
pwsh -File .\install-desktop-shortcut.ps1 -Remove
```

## Layout

```
launcher-app/
├── package.json                — npm: tauri CLI + api
├── README.md                   — this file
├── install-desktop-shortcut.ps1 — create the Desktop .lnk after build
├── src/
│   └── index.html              — UI: animated canvas + buttons + log
└── src-tauri/
    ├── Cargo.toml              — Rust deps (tauri, serde)
    ├── build.rs                — tauri-build invocation
    ├── tauri.conf.json         — Tauri config (window, bundle, identifier)
    ├── capabilities/default.json — Tauri 2 permission grant
    ├── icons/                  — icon.ico (multi-size) + 32/128/512 PNG
    └── src/
        ├── main.rs             — entrypoint (delegates to lib)
        └── lib.rs              — spawn_pwsh + stream + tauri commands
```

## How it finds the repo root

The Rust backend (`lib.rs:find_repo_root`) walks up from the **current
working directory** first, then from the **launcher exe path**, looking
for the marker `infra/swarm/vibemind-stack.yml`. Up to 10 levels each.

That means the Desktop shortcut's "Start in" field controls which repo
checkout the launcher targets — the install script sets it to the
parent repo automatically.

If you move the .exe outside the repo tree, the walk from the exe path
will fail too and the UI shows "Repo root NOT FOUND" — at that point
edit the Desktop shortcut's "Start in" to point at the repo.

## Spawning behaviour

The launcher invokes:

```
pwsh.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass
         -File <repo>/scripts/vibemind-start.ps1
```

(or `vibemind-stop.ps1` for Stop). stdout / stderr are line-buffered
into Tauri events `log` (stream + line + ts) and an `exit` event when
the child terminates. Same shell, same script, same behaviour as
double-clicking the .ps1 directly.

## Notes

- No bundler / no node_modules pulled into the release binary (the
  frontend is just `src/index.html`).
- No telemetry, no network calls — the only thing the app does is
  spawn the two scripts and read their stdout.
- Permission model is Tauri 2's capabilities — see
  `src-tauri/capabilities/default.json`. We grant nothing beyond
  `core:default`; the commands are explicit Tauri commands (not the
  shell-plugin's open-arbitrary-process route).
