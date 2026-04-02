/**
 * Electron Shim
 * Workaround for module resolution issue where node_modules/electron
 * shadows the built-in electron module.
 */

// Check if we're running inside Electron
const isElectronRuntime = !!(process.versions && process.versions.electron);

if (!isElectronRuntime) {
  throw new Error('This module must be run inside Electron');
}

// Access Electron's internal module loader
// In Electron, the built-in modules are available via process._linkedBinding
// or through the internal module system

let electronModule;

try {
  // Method 1: Try to access electron through the internal module
  // When running in Electron, there's a special resolution for 'electron'
  // that should provide the built-in module, but node_modules shadows it.

  // We can trick Node by temporarily modifying the require paths
  const Module = require('module');
  const originalResolveFilename = Module._resolveFilename;

  // Temporarily override resolution to skip node_modules for 'electron'
  Module._resolveFilename = function(request, parent, isMain, options) {
    if (request === 'electron' || request.startsWith('electron/')) {
      // Return a special path that Electron's runtime will intercept
      return 'electron';
    }
    return originalResolveFilename.apply(this, arguments);
  };

  // Now require electron - this should get the built-in module
  electronModule = require('electron');

  // Restore original resolver
  Module._resolveFilename = originalResolveFilename;

  // Check if we got the real electron module
  if (typeof electronModule === 'string') {
    throw new Error('Got path instead of module');
  }

} catch (error) {
  console.error('[electron-shim] Method 1 failed:', error.message);

  try {
    // Method 2: Try using Electron's internal binding
    // This is not documented but might work
    electronModule = process._linkedBinding('electron_common_features');
  } catch (error2) {
    console.error('[electron-shim] Method 2 failed:', error2.message);

    // Method 3: Last resort - the electron module might be accessible
    // through the global scope in some Electron versions
    if (typeof global.electron !== 'undefined') {
      electronModule = global.electron;
    } else {
      throw new Error('Could not load built-in electron module. Ensure you are running inside Electron.');
    }
  }
}

module.exports = electronModule;
