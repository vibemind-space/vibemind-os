"use strict";
// Debug available Electron bindings

console.log("=== Electron Debug ===");
console.log("process.versions.electron:", process.versions.electron);
console.log("process.type:", process.type);

// Check what bindings are available
console.log("\n=== Available bindings ===");
if (process._linkedBinding) {
  console.log("process._linkedBinding exists");

  // Try common electron binding names
  const bindingNames = [
    'electron_browser_electron',
    'electron_common_features',
    'electron_browser_app',
    'electron',
    'electron_common_v8_util',
    'electron_browser_window'
  ];

  for (const name of bindingNames) {
    try {
      const binding = process._linkedBinding(name);
      console.log(`  ${name}:`, typeof binding, Object.keys(binding || {}).slice(0, 5));
    } catch (e) {
      console.log(`  ${name}: ERROR - ${e.message}`);
    }
  }
}

// Check process.electronBinding
if (process.electronBinding) {
  console.log("\nprocess.electronBinding exists");
  const electronBindingNames = ['app', 'browser_window', 'ipc_main'];
  for (const name of electronBindingNames) {
    try {
      const binding = process.electronBinding(name);
      console.log(`  ${name}:`, typeof binding, Object.keys(binding || {}).slice(0, 5));
    } catch (e) {
      console.log(`  ${name}: ERROR - ${e.message}`);
    }
  }
}

// Check for internal modules
console.log("\n=== Module check ===");
const Module = require('module');
console.log("Module.builtinModules includes electron:", Module.builtinModules.includes('electron'));

// Try to find how electron-vite accesses electron
console.log("\n=== Require cache ===");
const electronKeys = Object.keys(require.cache).filter(k => k.includes('electron'));
console.log("Electron-related cache entries:", electronKeys.length);
electronKeys.slice(0, 5).forEach(k => console.log("  ", k));

process.exit(0);
