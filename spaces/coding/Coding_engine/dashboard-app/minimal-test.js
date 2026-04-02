// Minimal Electron test - no require('electron')
console.log('=== Minimal Electron Test ===');
console.log('process.versions.electron:', process.versions.electron);
console.log('process.type:', process.type);
console.log('process.electronBinding:', typeof process.electronBinding);
console.log('process._linkedBinding:', typeof process._linkedBinding);

// Try to trigger the browser process initialization
console.log('\n=== Trying to require electron/js2c/browser_init ===');
try {
  require('electron/js2c/browser_init');
  console.log('browser_init loaded successfully');
  console.log('process.type after init:', process.type);
  console.log('process.electronBinding after init:', typeof process.electronBinding);
} catch (e) {
  console.log('browser_init error:', e.message);
}

// Check what the built-in require resolves to
console.log('\n=== Checking require.resolve ===');
try {
  const electronPath = require.resolve('electron');
  console.log('require.resolve("electron"):', electronPath);
} catch (e) {
  console.log('require.resolve error:', e.message);
}

// Try direct require
console.log('\n=== Trying require("electron") ===');
try {
  const electron = require('electron');
  console.log('typeof electron:', typeof electron);
  if (typeof electron === 'object' && electron.app) {
    console.log('electron.app:', typeof electron.app);
    console.log('=== Electron loaded! Caching for child modules... ===');

    // Cache for child modules
    const Module = require('module');
    const path = require('path');
    const fakeModule = new Module('electron');
    fakeModule.exports = electron;
    fakeModule.loaded = true;
    const nodeModulesElectronIndex = path.join(__dirname, 'node_modules', 'electron', 'index.js');
    Module._cache[nodeModulesElectronIndex] = fakeModule;
    Module._cache['electron'] = fakeModule;
    Module._cache[path.join(__dirname, 'node_modules', 'electron')] = fakeModule;
    const originalLoad = Module._load;
    Module._load = function(request, parent, isMain) {
      if (request === 'electron') return electron;
      return originalLoad.call(this, request, parent, isMain);
    };

    console.log('=== Loading out/main/main.js... ===');
    require('./out/main/main.js');
  } else {
    console.log('ERROR: electron is not valid:', typeof electron);
    process.exit(1);
  }
} catch (e) {
  console.log('require error:', e.message);
  process.exit(1);
}
