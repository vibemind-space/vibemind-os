/**
 * Electron Module Preload Patch
 *
 * This script must be loaded BEFORE the main script using electron's -r flag.
 * It patches Node's module system to properly resolve the 'electron' built-in module.
 */

'use strict';

const Module = require('module');
const path = require('path');

// Store the original functions
const originalResolveFilename = Module._resolveFilename;
const originalLoad = Module._load;

// Get the electron module while we can (in the preload context)
let electronModule = null;
try {
  // In Electron's main process, the electron module should be available
  // before any user code runs
  const originalElectron = originalLoad.call(Module, 'electron', module, false);
  if (originalElectron && typeof originalElectron === 'object' && originalElectron.app) {
    electronModule = originalElectron;
    console.log('[preload-patch] Successfully captured electron module');
  }
} catch (e) {
  // Couldn't get it yet, will try again in _load
}

// Patch _resolveFilename to handle 'electron' specially
Module._resolveFilename = function(request, parent, isMain, options) {
  if (request === 'electron') {
    // Return 'electron' as-is, we'll handle it in _load
    return 'electron';
  }
  return originalResolveFilename.call(this, request, parent, isMain, options);
};

// Patch _load to return our cached electron module
Module._load = function(request, parent, isMain) {
  if (request === 'electron') {
    if (electronModule) {
      return electronModule;
    }

    // Try to get it now
    try {
      const result = originalLoad.call(this, 'electron', parent, isMain);
      if (result && typeof result === 'object' && result.app) {
        electronModule = result;
        return electronModule;
      }
    } catch (e) {
      // Fall through
    }

    // Last resort: throw a helpful error
    throw new Error(
      'Cannot load electron module. This usually means the electron npm package ' +
      'is shadowing the built-in module. Try removing or renaming node_modules/electron.'
    );
  }

  return originalLoad.call(this, request, parent, isMain);
};

console.log('[preload-patch] Module system patched for electron resolution');
