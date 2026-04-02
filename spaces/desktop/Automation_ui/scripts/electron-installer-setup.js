/**
 * Electron Installer - AfterInstall Hook
 *
 * Dieses Script wird nach der Installation der Electron-App ausgeführt
 * und richtet den Desktop-Streaming-Client automatisch ein.
 *
 * Verwendung in electron-builder.yml:
 * afterInstall: ./scripts/electron-installer-setup.js
 */

const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

// Konfiguration
const CONFIG = {
  appName: "AutomationUI",
  desktopClientFolder: "desktop-client",
  requiredPythonVersion: "3.9",
  pythonPackages: ["mss", "Pillow", "websockets"],
  streamSettings: {
    fps: 4,
    quality: 75,
  },
};

/**
 * Logger für Installation
 */
class InstallLogger {
  constructor(installPath) {
    this.logPath = path.join(installPath, "install.log");
    this.ensureLogDir();
  }

  ensureLogDir() {
    const dir = path.dirname(this.logPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }

  log(level, message) {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] [${level}] ${message}`;
    console.log(logEntry);
    fs.appendFileSync(this.logPath, logEntry + "\n");
  }

  info(msg) {
    this.log("INFO", msg);
  }
  error(msg) {
    this.log("ERROR", msg);
  }
  success(msg) {
    this.log("SUCCESS", msg);
  }
  warn(msg) {
    this.log("WARN", msg);
  }
}

/**
 * Prüft Python-Installation
 */
function checkPython() {
  try {
    const version = execSync("python --version 2>&1", { encoding: "utf8" });
    const match = version.match(/Python (\d+)\.(\d+)/);
    if (match) {
      const major = parseInt(match[1]);
      const minor = parseInt(match[2]);
      const required = CONFIG.requiredPythonVersion.split(".").map(Number);
      return (
        major > required[0] || (major === required[0] && minor >= required[1])
      );
    }
  } catch (e) {
    return false;
  }
  return false;
}

/**
 * Python automatisch installieren (nur Windows)
 */
async function installPython(logger) {
  if (os.platform() !== "win32") {
    logger.error(
      "Automatische Python-Installation nur unter Windows unterstützt",
    );
    return false;
  }

  logger.info("Lade Python herunter...");

  const pythonUrl =
    "https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe";
  const installerPath = path.join(os.tmpdir(), "python-installer.exe");

  try {
    // Download mit curl (in Windows 10+ verfügbar)
    execSync(`curl -L -o "${installerPath}" "${pythonUrl}"`, {
      stdio: "inherit",
    });

    logger.info("Installiere Python...");
    execSync(
      `"${installerPath}" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1`,
      {
        stdio: "inherit",
      },
    );

    // Cleanup
    if (fs.existsSync(installerPath)) {
      fs.unlinkSync(installerPath);
    }

    logger.success("Python erfolgreich installiert");
    return true;
  } catch (e) {
    logger.error(`Python-Installation fehlgeschlagen: ${e.message}`);
    return false;
  }
}

/**
 * Python-Dependencies installieren
 */
function installPythonDependencies(logger, installPath) {
  logger.info("Installiere Python-Dependencies...");

  const desktopClientPath = path.join(installPath, CONFIG.desktopClientFolder);
  const requirementsFile = path.join(desktopClientPath, "requirements.txt");

  try {
    // pip upgrade
    execSync("python -m pip install --upgrade pip", { stdio: "pipe" });

    if (fs.existsSync(requirementsFile)) {
      execSync(`python -m pip install -r "${requirementsFile}"`, {
        stdio: "pipe",
      });
    } else {
      // Fallback: einzelne Pakete installieren
      for (const pkg of CONFIG.pythonPackages) {
        logger.info(`Installiere ${pkg}...`);
        execSync(`python -m pip install ${pkg}`, { stdio: "pipe" });
      }
    }

    logger.success("Dependencies installiert");
    return true;
  } catch (e) {
    logger.error(`Dependency-Installation fehlgeschlagen: ${e.message}`);
    return false;
  }
}

/**
 * Windows Task Scheduler einrichten
 */
function setupWindowsAutostart(logger, installPath) {
  if (os.platform() !== "win32") {
    logger.warn("Autostart-Setup nur unter Windows verfügbar");
    return false;
  }

  logger.info("Richte Windows Autostart ein...");

  const taskName = `${CONFIG.appName}_DesktopStream`;
  const desktopClientPath = path.join(installPath, CONFIG.desktopClientFolder);
  const pythonScript = path.join(
    desktopClientPath,
    "dual_screen_capture_client.py",
  );

  if (!fs.existsSync(pythonScript)) {
    logger.error(`Script nicht gefunden: ${pythonScript}`);
    return false;
  }

  // PowerShell-Script für Task-Erstellung
  const psScript = `
        $taskName = "${taskName}"
        $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
        if (-not $pythonPath) { exit 1 }
        
        # Existierende Task entfernen
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        
        # Neue Task erstellen
        $action = New-ScheduledTaskAction -Execute $pythonPath -Argument '"${pythonScript.replace(/\\/g, "\\\\")}" --fps ${CONFIG.streamSettings.fps} --quality ${CONFIG.streamSettings.quality}' -WorkingDirectory "${desktopClientPath.replace(/\\/g, "\\\\")}"
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 999
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Desktop-Streaming für ${CONFIG.appName}" -Force
    `;

  try {
    // PowerShell ausführen
    execSync(`powershell -Command "${psScript.replace(/"/g, '\\"')}"`, {
      stdio: "pipe",
      windowsHide: true,
    });

    logger.success(`Autostart-Task '${taskName}' erstellt`);
    return true;
  } catch (e) {
    logger.error(`Autostart-Setup fehlgeschlagen: ${e.message}`);
    return false;
  }
}

/**
 * macOS LaunchAgent einrichten
 */
function setupMacAutostart(logger, installPath) {
  if (os.platform() !== "darwin") {
    return false;
  }

  logger.info("Richte macOS LaunchAgent ein...");

  const launchAgentsDir = path.join(os.homedir(), "Library", "LaunchAgents");
  const plistName = `com.${CONFIG.appName.toLowerCase()}.desktopstream.plist`;
  const plistPath = path.join(launchAgentsDir, plistName);

  const desktopClientPath = path.join(installPath, CONFIG.desktopClientFolder);
  const pythonScript = path.join(
    desktopClientPath,
    "dual_screen_capture_client.py",
  );

  const plistContent = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.${CONFIG.appName.toLowerCase()}.desktopstream</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>${pythonScript}</string>
        <string>--fps</string>
        <string>${CONFIG.streamSettings.fps}</string>
        <string>--quality</string>
        <string>${CONFIG.streamSettings.quality}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${desktopClientPath}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${path.join(installPath, "stream.log")}</string>
    <key>StandardErrorPath</key>
    <string>${path.join(installPath, "stream-error.log")}</string>
</dict>
</plist>`;

  try {
    // LaunchAgents Verzeichnis erstellen falls nicht vorhanden
    if (!fs.existsSync(launchAgentsDir)) {
      fs.mkdirSync(launchAgentsDir, { recursive: true });
    }

    // Plist schreiben
    fs.writeFileSync(plistPath, plistContent);

    // LaunchAgent laden
    execSync(`launchctl load "${plistPath}"`, { stdio: "pipe" });

    logger.success("macOS LaunchAgent eingerichtet");
    return true;
  } catch (e) {
    logger.error(`macOS Autostart-Setup fehlgeschlagen: ${e.message}`);
    return false;
  }
}

/**
 * Linux systemd Service einrichten
 */
function setupLinuxAutostart(logger, installPath) {
  if (os.platform() !== "linux") {
    return false;
  }

  logger.info("Richte Linux systemd Service ein...");

  const systemdUserDir = path.join(os.homedir(), ".config", "systemd", "user");
  const serviceName = `${CONFIG.appName.toLowerCase()}-desktopstream.service`;
  const servicePath = path.join(systemdUserDir, serviceName);

  const desktopClientPath = path.join(installPath, CONFIG.desktopClientFolder);
  const pythonScript = path.join(
    desktopClientPath,
    "dual_screen_capture_client.py",
  );

  const serviceContent = `[Unit]
Description=${CONFIG.appName} Desktop Streaming Service
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=${desktopClientPath}
ExecStart=python3 ${pythonScript} --fps ${CONFIG.streamSettings.fps} --quality ${CONFIG.streamSettings.quality}
Restart=always
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
`;

  try {
    // systemd user directory erstellen
    if (!fs.existsSync(systemdUserDir)) {
      fs.mkdirSync(systemdUserDir, { recursive: true });
    }

    // Service-Datei schreiben
    fs.writeFileSync(servicePath, serviceContent);

    // Service aktivieren
    execSync("systemctl --user daemon-reload", { stdio: "pipe" });
    execSync(`systemctl --user enable ${serviceName}`, { stdio: "pipe" });

    logger.success("Linux systemd Service eingerichtet");
    return true;
  } catch (e) {
    logger.error(`Linux Autostart-Setup fehlgeschlagen: ${e.message}`);
    return false;
  }
}

/**
 * Konfigurationsdatei erstellen
 */
function createConfig(logger, installPath) {
  const configPath = path.join(installPath, "stream-config.json");

  const config = {
    installedAt: new Date().toISOString(),
    version: "1.0.0",
    platform: os.platform(),
    streaming: CONFIG.streamSettings,
    supabase: {
      url: process.env.SUPABASE_WS_URL || "ws://localhost:8007/ws/live-desktop",
    },
  };

  try {
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
    logger.success(`Konfiguration gespeichert: ${configPath}`);
    return true;
  } catch (e) {
    logger.error(`Konfiguration konnte nicht gespeichert werden: ${e.message}`);
    return false;
  }
}

/**
 * Desktop-Client starten
 */
function startDesktopClient(logger, installPath) {
  logger.info("Starte Desktop-Client...");

  const desktopClientPath = path.join(installPath, CONFIG.desktopClientFolder);
  const pythonScript = path.join(
    desktopClientPath,
    "dual_screen_capture_client.py",
  );

  if (!fs.existsSync(pythonScript)) {
    logger.error(`Script nicht gefunden: ${pythonScript}`);
    return false;
  }

  try {
    // Detached process starten
    const child = spawn(
      "python",
      [
        pythonScript,
        "--fps",
        CONFIG.streamSettings.fps.toString(),
        "--quality",
        CONFIG.streamSettings.quality.toString(),
      ],
      {
        cwd: desktopClientPath,
        detached: true,
        stdio: "ignore",
      },
    );

    child.unref();
    logger.success("Desktop-Client gestartet");
    return true;
  } catch (e) {
    logger.error(`Fehler beim Starten des Clients: ${e.message}`);
    return false;
  }
}

/**
 * Hauptfunktion - wird von electron-builder aufgerufen
 */
async function main() {
  // InstallPath aus Umgebungsvariable oder Standard
  const installPath =
    process.env.INSTALL_PATH ||
    path.join(os.homedir(), "AppData", "Local", CONFIG.appName);

  const logger = new InstallLogger(installPath);

  logger.info("==========================================");
  logger.info(`${CONFIG.appName} - Post-Install Setup`);
  logger.info(`Platform: ${os.platform()}`);
  logger.info(`Install Path: ${installPath}`);
  logger.info("==========================================");

  let success = true;

  // 1. Python prüfen/installieren
  if (!checkPython()) {
    logger.warn("Python nicht gefunden oder zu alt");
    if (!(await installPython(logger))) {
      logger.error("Python-Installation fehlgeschlagen - manuell installieren");
      success = false;
    }
  } else {
    const version = execSync("python --version", { encoding: "utf8" }).trim();
    logger.success(`Python gefunden: ${version}`);
  }

  // 2. Dependencies installieren
  if (success) {
    installPythonDependencies(logger, installPath);
  }

  // 3. Plattform-spezifisches Autostart
  if (success) {
    switch (os.platform()) {
      case "win32":
        setupWindowsAutostart(logger, installPath);
        break;
      case "darwin":
        setupMacAutostart(logger, installPath);
        break;
      case "linux":
        setupLinuxAutostart(logger, installPath);
        break;
    }
  }

  // 4. Konfiguration erstellen
  createConfig(logger, installPath);

  // 5. Client starten
  if (success) {
    startDesktopClient(logger, installPath);
  }

  logger.info("==========================================");
  logger.info(
    success ? "Installation erfolgreich!" : "Installation mit Fehlern beendet",
  );
  logger.info("==========================================");

  process.exit(success ? 0 : 1);
}

// Export für electron-builder
module.exports = main;

// Direkte Ausführung
if (require.main === module) {
  main().catch(console.error);
}
