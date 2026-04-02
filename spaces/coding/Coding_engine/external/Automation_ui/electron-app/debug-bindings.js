// Debug script to find available Electron bindings

console.log('=== Electron Debug ===');
console.log('Electron version:', process.versions.electron);
console.log('Node version:', process.version);
console.log('');

// Check process properties
console.log('=== Process Properties ===');
console.log('process.electronBinding:', typeof process.electronBinding);
console.log('process._linkedBinding:', typeof process._linkedBinding);
console.log('process.resourcesPath:', process.resourcesPath);
console.log('process.type:', process.type);
console.log('');

// Check require.cache for electron modules
console.log('=== Module Cache (electron related) ===');
for (const key of Object.keys(require.cache)) {
  if (key.includes('electron') || key.includes('asar')) {
    console.log(key);
  }
}
console.log('');

// Try to list available bindings
if (process.electronBinding) {
  console.log('=== Trying electronBinding ===');
  const possibleBindings = [
    'electron',
    'app',
    'browser_window',
    'ipc_main',
    'electron_browser_app',
    'electron_browser',
    'electron_common',
    'electron_main',
    'v8_util'
  ];

  for (const name of possibleBindings) {
    try {
      const binding = process.electronBinding(name);
      console.log(`${name}: ${typeof binding} - keys: ${Object.keys(binding || {}).slice(0, 5).join(', ')}`);
    } catch (e) {
      console.log(`${name}: ERROR - ${e.message}`);
    }
  }
}

console.log('');
console.log('=== Checking Module internals ===');
const Module = require('module');
console.log('Module._extensions:', Object.keys(Module._extensions));
console.log('');

// Check if electron is in the builtinModules
console.log('=== Builtin Modules ===');
console.log('builtin modules:', Module.builtinModules ? Module.builtinModules.join(', ') : 'N/A');

// Try direct path resolution
console.log('');
console.log('=== Module paths ===');
console.log('module.paths:', module.paths);

// Exit
process.exit(0);
