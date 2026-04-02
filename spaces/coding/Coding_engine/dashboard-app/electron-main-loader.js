/**
 * Electron Main Process Loader
 *
 * This loader script runs INSIDE Electron and patches the module system
 * before loading the actual main process script.
 */

// In Electron's main process, the 'electron' module should be available
// via the internal binding system. We need to access it before Node's
// module system tries to load from node_modules.

const Module = require('module');
const path = require('path');

// Store original resolve
const originalResolve = Module._resolveFilename;

// Patch module resolution to handle 'electron' specially
Module._resolveFilename = function(request, parent, isMain, options) {
  if (request === 'electron') {
    // Try to access Electron's internal electron module
    // This should work because we're running inside electron.exe
    try {
      // Return a special marker that we'll handle in _load
      return 'electron-internal';
    } catch (e) {
      // Fall through to original behavior
    }
  }
  return originalResolve.call(this, request, parent, isMain, options);
};

// Store original load
const originalLoad = Module._load;

// Patch module loading
Module._load = function(request, parent, isMain) {
  if (request === 'electron-internal' || request === 'electron') {
    // Access Electron's built-in APIs directly
    // These are available as globals or through special bindings in Electron
    try {
      // In Electron, these should be available through process bindings
      // or through the native require that Electron provides
      const electronApis = {};

      // Check if we have access to electron internals
      if (typeof process !== 'undefined' && process.electronBinding) {
        // Try getting modules through electronBinding
        electronApis.app = process.electronBinding('app').app;
        electronApis.BrowserWindow = process.electronBinding('browser_window').BrowserWindow;
      }

      // If that didn't work, try accessing through global
      if (!electronApis.app && typeof global !== 'undefined') {
        // Sometimes Electron exposes APIs on global
        electronApis.app = global.app;
        electronApis.BrowserWindow = global.BrowserWindow;
      }

      if (electronApis.app) {
        return electronApis;
      }
    } catch (e) {
      console.error('Failed to access Electron internals:', e);
    }
  }
  return originalLoad.call(this, request, parent, isMain);
};

// Now load the actual main process script
console.log('Loading main process...');
require('./out/main/main.js');
