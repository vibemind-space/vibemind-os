// Electron module loading
// Note: The 'electron' folder in node_modules has been renamed to '.electron-runtime'
// to prevent Node's module resolution from shadowing Electron's built-in module
const { app, BrowserWindow, Tray, Menu, nativeImage, dialog, shell, ipcMain } = require('electron');

const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// Delay screenCapture import to after app context is ready
let screenCapture = null;

// @moire/canvas Integration
let moireIPC = null;
try {
  const { setupMoireIPC } = require('@moire/canvas/electron');
  moireIPC = setupMoireIPC;
} catch (error) {
  console.log('[Moire] @moire/canvas not installed - Moire features disabled');
}

// Konfiguration
const CONFIG = {
  devServerUrl: 'http://localhost:3003',
  ocrDesignerPath: '/electron',
  devServerStartTimeout: 30000,
  devServerCheckInterval: 1000,
  projectRoot: path.join(__dirname, '..'),
  windowWidth: 1400,
  windowHeight: 900,
  enableMoireOCR: true,
  autoStartCapture: true, // Automatisch Screen Capture starten
  captureFPS: 15,
  captureQuality: 80
};

// Globale Variablen
let mainWindow = null;
let tray = null;
let devServerProcess = null;
let isQuitting = false;

// Logging
function log(level, message) {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] [${level}] ${message}`;
  console.log(logMessage);

  const logDir = path.join(CONFIG.projectRoot, 'logs');
  if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
  }
  fs.appendFileSync(
    path.join(logDir, 'electron-app.log'),
    logMessage + '\n'
  );
}

// Dev-Server starten
function startDevServer() {
  return new Promise((resolve, reject) => {
    log('INFO', 'Starting Dev-Server (npm run dev)...');

    checkDevServer().then(running => {
      if (running) {
        log('INFO', 'Dev-Server already running');
        resolve();
        return;
      }

      const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
      devServerProcess = spawn(npmCmd, ['run', 'dev'], {
        cwd: CONFIG.projectRoot,
        shell: true,
        stdio: ['ignore', 'pipe', 'pipe']
      });

      devServerProcess.stdout.on('data', (data) => {
        const output = data.toString();
        if (output.includes('Local:') || output.includes('localhost:3003') || output.includes('ready in')) {
          log('INFO', 'Dev-Server is ready!');
          resolve();
        }
      });

      devServerProcess.stderr.on('data', (data) => {
        // Ignore stderr noise
      });

      devServerProcess.on('error', (error) => {
        log('ERROR', `Dev-Server error: ${error.message}`);
        reject(error);
      });

      devServerProcess.on('exit', (code) => {
        log('WARN', `Dev-Server exited with code: ${code}`);
        devServerProcess = null;
      });

      // Timeout check
      const startTime = Date.now();
      const checkInterval = setInterval(() => {
        checkDevServer().then(running => {
          if (running) {
            clearInterval(checkInterval);
            resolve();
          } else if (Date.now() - startTime > CONFIG.devServerStartTimeout) {
            clearInterval(checkInterval);
            reject(new Error('Dev-Server Timeout'));
          }
        });
      }, CONFIG.devServerCheckInterval);
    });
  });
}

// Prüfe ob Dev-Server läuft
function checkDevServer() {
  return new Promise(resolve => {
    const http = require('http');
    // Extract port from CONFIG.devServerUrl
    const urlMatch = CONFIG.devServerUrl.match(/:(\d+)/);
    const port = urlMatch ? parseInt(urlMatch[1]) : 3003;

    const options = {
      hostname: '127.0.0.1', // IPv4 explicit statt localhost
      port: port,
      path: '/',
      method: 'GET',
      timeout: 3000
    };

    const req = http.request(options, (res) => {
      log('INFO', `Dev-Server check: status ${res.statusCode}`);
      resolve(res.statusCode === 200 || res.statusCode === 304);
    });

    req.on('error', (err) => {
      log('INFO', `Dev-Server check failed: ${err.message}`);
      resolve(false);
    });

    req.on('timeout', () => {
      log('INFO', 'Dev-Server check timeout');
      req.destroy();
      resolve(false);
    });

    req.end();
  });
}

// Hauptfenster erstellen
function createWindow() {
  mainWindow = new BrowserWindow({
    width: CONFIG.windowWidth,
    height: CONFIG.windowHeight,
    minWidth: 800,
    minHeight: 600,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    show: false,
    title: 'TRAE Desktop Streaming'
  });

  const url = CONFIG.devServerUrl + CONFIG.ocrDesignerPath;
  log('INFO', `Loading: ${url}`);
  mainWindow.loadURL(url);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    log('INFO', 'Main window displayed');

    // Auto-Start Screen Capture
    if (CONFIG.autoStartCapture) {
      startScreenCaptureForWindow();
    }
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();

      if (tray) {
        tray.displayBalloon({
          title: 'TRAE Desktop Streaming',
          content: 'App is running in background.\nClick tray icon to open.'
        });
      }
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }
}

// Screen Capture für Window starten
async function startScreenCaptureForWindow() {
  log('INFO', 'Starting native screen capture...');

  // Frame-Callback registrieren
  screenCapture.onFrame((frame) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('screen-capture:frame', frame);
    }
  });

  // Capture starten
  const result = await screenCapture.startCapture({
    fps: CONFIG.captureFPS,
    quality: CONFIG.captureQuality
  });

  if (result.success) {
    log('INFO', `Screen capture started: ${result.displays?.length || 0} displays`);

    // Displays an Renderer senden
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('screen-capture:displays', result.displays);
    }
  } else {
    log('ERROR', `Screen capture failed: ${result.error}`);
  }
}

// System Tray erstellen
function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'tray-icon.png');
  let trayIcon;

  if (fs.existsSync(iconPath)) {
    trayIcon = nativeImage.createFromPath(iconPath);
  } else {
    trayIcon = nativeImage.createEmpty();
  }

  tray = new Tray(trayIcon);
  tray.setToolTip('TRAE Desktop Streaming');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open Window',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Restart Dev-Server',
      click: async () => {
        if (devServerProcess) {
          devServerProcess.kill();
        }
        await startDevServer();
      }
    },
    {
      label: 'Restart Screen Capture',
      click: async () => {
        if (screenCapture) {
          screenCapture.stopCapture();
          await startScreenCaptureForWindow();
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Open Logs',
      click: () => {
        shell.openPath(path.join(CONFIG.projectRoot, 'logs'));
      }
    },
    {
      label: 'Open Project Folder',
      click: () => {
        shell.openPath(CONFIG.projectRoot);
      }
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  log('INFO', 'System Tray created');
}

// IPC Handler für Window Controls
function setupIPCHandlers() {
  ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
  });

  ipcMain.on('window-maximize', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
      } else {
        mainWindow.maximize();
      }
    }
  });

  ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close();
  });

  ipcMain.on('log', (event, { level, message }) => {
    log(level, `[Renderer] ${message}`);
  });
}

// Alle Child-Prozesse beenden
function cleanupProcesses() {
  log('INFO', 'Cleaning up processes...');

  if (screenCapture) {
    screenCapture.stopCapture();
  }

  if (devServerProcess) {
    log('INFO', '  Stopping Dev-Server...');
    devServerProcess.kill();
    devServerProcess = null;
  }
}

// App Events
app.whenReady().then(async () => {
  log('INFO', '═══════════════════════════════════════════');
  log('INFO', '  TRAE Desktop Streaming - Native Capture');
  log('INFO', '═══════════════════════════════════════════');

  try {
    // Load screenCapture module now that app is ready
    const screenCaptureModule = require('./screenCapture');
    screenCapture = screenCaptureModule.screenCapture;
    log('INFO', 'Screen capture module loaded');

    // Setup IPC handlers
    setupIPCHandlers();
    screenCapture.setupIPC();

    // Setup Moire IPC if available
    if (moireIPC) {
      log('INFO', 'Setting up Moire IPC...');
      await moireIPC({ enableOCR: CONFIG.enableMoireOCR });
      log('INFO', 'Moire IPC initialized with OCR support');
    }

    // System Tray erstellen
    createTray();

    // Check if dev server is already running (started by external script)
    log('INFO', 'Checking if dev server is running...');
    const isRunning = await checkDevServer();

    if (isRunning) {
      log('INFO', 'Dev server already running - creating window immediately');
      createWindow();
    } else {
      // Dev server not ready yet - wait and retry
      log('INFO', 'Dev server not ready - waiting 5 seconds...');
      await new Promise(r => setTimeout(r, 5000));

      const retryCheck = await checkDevServer();
      if (retryCheck) {
        log('INFO', 'Dev server now available - creating window');
        createWindow();
      } else {
        // Try to start it ourselves as fallback
        log('INFO', 'Dev server still not available - attempting to start...');
        await startDevServer();
        createWindow();
      }
    }

    log('INFO', 'All components started!');

  } catch (error) {
    log('ERROR', `Startup error: ${error.message}`);
    dialog.showErrorBox(
      'Startup Error',
      `App could not start:\n\n${error.message}\n\nPlease check the logs.`
    );
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
});

app.on('will-quit', () => {
  cleanupProcesses();
});

process.on('uncaughtException', (error) => {
  log('ERROR', `Uncaught exception: ${error.message}`);
  log('ERROR', error.stack);
});
