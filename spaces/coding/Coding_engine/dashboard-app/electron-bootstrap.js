/**
 * Electron Bootstrap Script
 *
 * This script runs FIRST when Electron starts. It patches Module._load to
 * intercept require('electron') and return Electron's built-in module instead
 * of the npm package.
 */

'use strict';

const Module = require('module');
const path = require('path');

console.log('[bootstrap] Electron bootstrap starting...');
console.log('[bootstrap] process.versions.electron:', process.versions.electron);

// Step 1: Delete the npm electron package from require cache and resolution
const nodeModulesElectron = path.join(__dirname, 'node_modules', 'electron');
const nodeModulesElectronIndex = path.join(nodeModulesElectron, 'index.js');

// Clear any cached references to the npm package
Object.keys(require.cache).forEach(key => {
  if (key.includes('node_modules') && key.includes('electron')) {
    delete require.cache[key];
  }
});

// Step 2: Patch Module._resolveFilename to skip node_modules/electron
const originalResolveFilename = Module._resolveFilename;
Module._resolveFilename = function(request, parent, isMain, options) {
  if (request === 'electron') {
    // Return a special marker that we'll intercept in _load
    return 'electron';
  }
  return originalResolveFilename.call(this, request, parent, isMain, options);
};

// Step 3: Patch Module._load to return Electron's built-in module
const originalLoad = Module._load;
let electronModule = null;

Module._load = function(request, parent, isMain) {
  if (request === 'electron') {
    if (!electronModule) {
      // Use Electron's internal binding to get the real electron module
      // This bypasses Node's module resolution entirely
      electronModule = process.electronBinding ?
        { app: require.main } : // fallback
        originalLoad.call(this, 'electron', null, false);

      // If we still got a string (the npm package), try to get actual Electron APIs
      if (typeof electronModule === 'string' || !electronModule.app) {
        // Access Electron internals directly
        const electronCommon = process._linkedBinding?.('electron_common_features');
        if (electronCommon) {
          console.log('[bootstrap] Using linked binding for electron');
        }

        // Last resort: construct from individual requires
        // Electron exposes these as internal modules
        try {
          electronModule = {
            app: process.electronBinding?.('app')?.app || originalLoad.call(this, 'electron', null, false)?.app,
          };
        } catch (e) {
          // Use whatever we got
        }
      }
    }
    console.log('[bootstrap] Intercepted require("electron"), type:', typeof electronModule);
    return electronModule;
  }
  return originalLoad.call(this, request, parent, isMain);
};

// Step 4: Now try to get the electron module
let electronTest;
try {
  electronTest = require('electron');
  console.log('[bootstrap] Electron module type:', typeof electronTest);
  console.log('[bootstrap] Has app?', !!electronTest?.app);
  console.log('[bootstrap] Available APIs:', electronTest ? Object.keys(electronTest).slice(0, 10).join(', ') + '...' : 'none');
} catch (e) {
  console.error('[bootstrap] Failed to load electron module:', e.message);
}

// Step 2: Cache it so that child modules can access it
// We need to put it in the Module._cache so require('electron') returns it

// Create a fake module that exports our electron object
const fakeModule = new Module('electron');
fakeModule.exports = electronModule;
fakeModule.loaded = true;
fakeModule.filename = 'electron';
fakeModule.paths = [];

// Add to cache with multiple possible keys that Node might look for
Module._cache['electron'] = fakeModule;

// Also handle the case where Node resolves to node_modules/electron
const nodeModulesElectronPath = path.join(__dirname, 'node_modules', 'electron');
const nodeModulesElectronIndex = path.join(nodeModulesElectronPath, 'index.js');
Module._cache[nodeModulesElectronPath] = fakeModule;
Module._cache[nodeModulesElectronIndex] = fakeModule;

// Step 3: Patch Module._load to intercept 'electron' requires
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === 'electron') {
    console.log('[bootstrap] Intercepted require("electron")');
    return electronModule;
  }
  return originalLoad.call(this, request, parent, isMain);
};

// Step 4: Now load the actual main script
console.log('[bootstrap] Loading main script...');
try {
  require('./out/main/main.js');
} catch (e) {
  console.error('[bootstrap] Error loading main script:', e);
  process.exit(1);
}
