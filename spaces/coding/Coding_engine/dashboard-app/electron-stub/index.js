/**
 * Electron Stub Module
 *
 * This replaces node_modules/electron temporarily during development.
 * It exports Electron's built-in module directly using internal APIs.
 */

'use strict';

// Electron exposes its APIs through process.electronBinding
// This is available when running inside electron.exe

// Try different methods to get the electron module
let electron;

// Method 1: Use process._linkedBinding (Electron internal)
if (typeof process._linkedBinding === 'function') {
  try {
    // Get the common features binding
    const binding = process._linkedBinding('electron_common_features');
    if (binding) {
      electron = binding;
    }
  } catch (e) {
    // Not available
  }
}

// Method 2: Use process.electronBinding (older Electron versions)
if (!electron && typeof process.electronBinding === 'function') {
  try {
    electron = {
      app: process.electronBinding('app'),
      BrowserWindow: process.electronBinding('browser_window'),
      ipcMain: process.electronBinding('ipc_main'),
      // Add other bindings as needed
    };
  } catch (e) {
    // Not available
  }
}

// Method 3: For Electron 25+, the module is registered in Node's internal registry
// We need to access it through the internal module system
if (!electron) {
  try {
    // This is a hack but it works in Electron
    const { builtinModules } = require('module');
    if (builtinModules && builtinModules.includes('electron')) {
      // The electron module should be loadable as a builtin
      electron = require('node:electron');
    }
  } catch (e) {
    // Not available as builtin
  }
}

// Method 4: Last resort - check if we're actually in electron
if (!electron && process.versions.electron) {
  // We're in Electron but can't access the module
  // This shouldn't happen, but let's provide a helpful error
  console.error('WARNING: Running in Electron but cannot access electron module.');
  console.error('Electron version:', process.versions.electron);
  console.error('This stub module needs to be updated for this Electron version.');

  // Return empty object to prevent crashes
  electron = {};
}

// If we're not in Electron at all, this is the npm package being required
// Return the path to electron.exe like the original package does
if (!electron && !process.versions.electron) {
  const fs = require('fs');
  const path = require('path');

  // Find the actual electron package
  const actualElectronPath = path.join(__dirname, '..', '_electron-pkg');
  if (fs.existsSync(actualElectronPath)) {
    module.exports = require(path.join(actualElectronPath, 'index.js'));
    return;
  }
}

module.exports = electron || {};
