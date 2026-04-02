const { contextBridge, ipcRenderer } = require('electron');

// @moire/canvas API
let moireAPI = null;
try {
  const { exposeMoireAPI } = require('@moire/canvas/electron-preload');
  exposeMoireAPI();
  moireAPI = true;
  console.log('[Preload] Moire API exposed');
} catch (error) {
  console.log('[Preload] @moire/canvas not available - Moire API disabled');
}

// Frame-Callbacks für Screen Capture
const frameCallbacks = new Set();
const displayCallbacks = new Set();

// Listener für Screen Capture Events vom Main Process
ipcRenderer.on('screen-capture:frame', (event, frame) => {
  for (const callback of frameCallbacks) {
    try {
      callback(frame);
    } catch (error) {
      console.error('[Preload] Frame callback error:', error);
    }
  }
});

ipcRenderer.on('screen-capture:displays', (event, displays) => {
  for (const callback of displayCallbacks) {
    try {
      callback(displays);
    } catch (error) {
      console.error('[Preload] Display callback error:', error);
    }
  }
});

// Exponiere sichere APIs für das Renderer-Fenster
contextBridge.exposeInMainWorld('electronAPI', {
  // ============================================
  // App-Informationen
  // ============================================
  getAppVersion: () => process.env.npm_package_version || '1.0.0',
  getPlatform: () => process.platform,
  isElectron: () => true,

  // ============================================
  // Fenster-Steuerung
  // ============================================
  minimizeWindow: () => ipcRenderer.send('window-minimize'),
  maximizeWindow: () => ipcRenderer.send('window-maximize'),
  closeWindow: () => ipcRenderer.send('window-close'),

  // ============================================
  // Screen Capture APIs
  // ============================================

  // Displays abrufen
  getDisplays: () => ipcRenderer.invoke('screen-capture:get-displays'),

  // Screen Capture starten
  startScreenCapture: (options = {}) => ipcRenderer.invoke('screen-capture:start', options),

  // Screen Capture stoppen
  stopScreenCapture: () => ipcRenderer.invoke('screen-capture:stop'),

  // Capture-Status abrufen
  getCaptureStatus: () => ipcRenderer.invoke('screen-capture:get-status'),

  // Capture-Optionen setzen
  setCaptureOptions: (options) => ipcRenderer.invoke('screen-capture:set-options', options),

  // Frame-Callback registrieren
  onFrame: (callback) => {
    frameCallbacks.add(callback);
    // Return cleanup function
    return () => frameCallbacks.delete(callback);
  },

  // Display-Liste Callback registrieren
  onDisplaysChanged: (callback) => {
    displayCallbacks.add(callback);
    return () => displayCallbacks.delete(callback);
  },

  // Frame-Callback entfernen
  offFrame: (callback) => {
    frameCallbacks.delete(callback);
  },

  // ============================================
  // Benachrichtigungen
  // ============================================
  showNotification: (title, body) => {
    new Notification(title, { body });
  },

  // ============================================
  // Logging
  // ============================================
  log: (level, message) => {
    ipcRenderer.send('log', { level, message });
  },

  // ============================================
  // Moire Canvas Features
  // ============================================
  isMoireAvailable: () => moireAPI !== null,

  // OCR via Moire
  performOCR: async (imageData, options = {}) => {
    if (!moireAPI) {
      throw new Error('Moire API not available');
    }
    return ipcRenderer.invoke('moire:ocr', { imageData, options });
  },

  // Moire Detection
  detectMoire: async (imageData) => {
    if (!moireAPI) {
      throw new Error('Moire API not available');
    }
    return ipcRenderer.invoke('moire:detect', { imageData });
  },

  // Stream frame to Moire
  streamFrame: (frameData, metadata = {}) => {
    ipcRenderer.send('moire:stream-frame', { frameData, metadata });
  }
});

// Zeige dass Electron geladen ist
console.log('[Preload] Electron Preload loaded');
console.log('[Preload] Moire API:', moireAPI ? 'Enabled' : 'Disabled');
console.log('[Preload] Screen Capture API: Enabled');
