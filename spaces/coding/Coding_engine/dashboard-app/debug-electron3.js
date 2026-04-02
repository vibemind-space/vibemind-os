"use strict";
// Try to properly initialize Electron main process

// First, require the browser init to set up the main process
try {
  require('electron/js2c/browser_init');
  console.log("browser_init loaded");
} catch (e) {
  console.log("browser_init error:", e.message);
}

console.log("process.type after init:", process.type);

// Now try to require electron
// We need to remove the cached require
delete require.cache[require.resolve('electron')];

// Try to get the internal electron module
const Module = require('module');

// Look for the electron module in Electron's internal modules
try {
  // In Electron, there should be a special handler for 'electron' that provides the API
  // Let's check if we can trigger it by deleting the npm package from resolution
  const originalResolveFilename = Module._resolveFilename;
  Module._resolveFilename = function(request, parent, isMain, options) {
    if (request === 'electron') {
      // Force it to look for the built-in module
      return 'electron';
    }
    return originalResolveFilename.call(this, request, parent, isMain, options);
  };

  const electron = require('electron');
  console.log("electron after patch:", typeof electron, electron);
  console.log("electron.app:", electron.app);

} catch (e) {
  console.log("Error:", e.message);
}

process.exit(0);
