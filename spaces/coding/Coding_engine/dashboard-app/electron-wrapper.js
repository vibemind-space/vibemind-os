// Electron Wrapper - loads electron module and caches it for child modules
console.log('[wrapper] Starting...');
console.log('[wrapper] process.versions.electron:', process.versions.electron);

// Step 1: Get the electron module
console.log('[wrapper] Loading electron module...');
const electron = require('electron');
console.log('[wrapper] typeof electron:', typeof electron);

if (typeof electron === 'object' && electron.app) {
  console.log('[wrapper] Got Electron APIs! Caching for child modules...');

  // Step 2: Cache for child modules
  const Module = require('module');
  const path = require('path');

  // Create a fake module
  const fakeModule = new Module('electron');
  fakeModule.exports = electron;
  fakeModule.loaded = true;

  // Add to cache
  const nodeModulesElectronIndex = path.join(__dirname, 'node_modules', 'electron', 'index.js');
  Module._cache[nodeModulesElectronIndex] = fakeModule;
  Module._cache['electron'] = fakeModule;
  Module._cache[path.join(__dirname, 'node_modules', 'electron')] = fakeModule;

  // Patch Module._load
  const originalLoad = Module._load;
  Module._load = function(request, parent, isMain) {
    if (request === 'electron') {
      return electron;
    }
    return originalLoad.call(this, request, parent, isMain);
  };

  // Step 3: Load the main script
  console.log('[wrapper] Loading out/main/main.js...');
  require('./out/main/main.js');
} else {
  console.log('[wrapper] ERROR: electron is not an object or has no app:', typeof electron);
  process.exit(1);
}
