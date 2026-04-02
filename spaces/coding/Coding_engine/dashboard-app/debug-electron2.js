"use strict";
// Debug what's available in Electron
console.log("process.type:", process.type);
console.log("process.versions.electron:", process.versions.electron);
console.log("process.electronBinding:", typeof process.electronBinding);

// Try different ways to access electron
console.log("\n--- Trying different require approaches ---");

// Try using Module._load directly to bypass node_modules
const Module = require('module');
const originalLoad = Module._load;

// Check what modules are built-in
console.log("Module.builtinModules:", Module.builtinModules);

// Check for electron in require.cache
const cacheKeys = Object.keys(require.cache).filter(k => k.includes('electron'));
console.log("electron-related cache keys:", cacheKeys);

// Try direct paths
try {
  const internal = process.binding ? process.binding('electron') : 'no binding';
  console.log("process.binding('electron'):", internal);
} catch (e) {
  console.log("process.binding('electron') error:", e.message);
}

// Check if there's an internal electron module
try {
  // In Electron, require('electron') in main process should work
  // but node_modules/electron shadows it
  // Let's try to delete it from cache and re-require

  const electronPackagePath = require.resolve('electron');
  console.log("require.resolve('electron'):", electronPackagePath);

} catch (e) {
  console.log("Error:", e.message);
}

// Check process for any electron-related properties
const electronProps = Object.keys(process).filter(k => k.toLowerCase().includes('electron'));
console.log("process electron properties:", electronProps);

process.exit(0);
