// Explore Electron's internal module system
console.log('=== Exploring Electron Internals ===\n');

console.log('process.versions.electron:', process.versions.electron);
console.log('process.type:', process.type);
console.log('process.resourcesPath:', process.resourcesPath);

console.log('\n=== Available process methods/properties ===');
const electronMethods = Object.keys(process).filter(k =>
  k.toLowerCase().includes('electron') ||
  k.includes('binding') ||
  k.includes('Binding')
);
console.log('Electron-related:', electronMethods);

console.log('\n=== Checking process._linkedBinding ===');
if (process._linkedBinding) {
  console.log('process._linkedBinding exists');
  try {
    const binding = process._linkedBinding('electron_common_features');
    console.log('electron_common_features:', binding);
  } catch (e) {
    console.log('electron_common_features error:', e.message);
  }
}

console.log('\n=== Checking Module internals ===');
const Module = require('module');
console.log('Module._cache keys containing electron:');
for (const key of Object.keys(Module._cache)) {
  if (key.toLowerCase().includes('electron')) {
    console.log('  -', key);
  }
}

console.log('\n=== Checking Module.builtinModules ===');
console.log('builtinModules:', Module.builtinModules);

console.log('\n=== Trying direct require paths ===');
const paths = [
  'electron',
  'electron/js2c/browser_init',
  'electron/main',
];

for (const p of paths) {
  console.log(`\nTrying require('${p}'):`);
  try {
    const result = require(p);
    console.log('  type:', typeof result);
    if (typeof result === 'object') {
      console.log('  keys:', Object.keys(result).slice(0, 10));
      if (result.app) console.log('  has app:', typeof result.app);
    } else if (typeof result === 'string') {
      console.log('  value:', result.substring(0, 100));
    }
  } catch (e) {
    console.log('  error:', e.message);
  }
}

console.log('\n=== Checking global objects ===');
console.log('global.electron:', typeof global.electron);

// Try to find where electron is loaded from
console.log('\n=== Module search paths ===');
console.log('module.paths:', module.paths);

// Check if there's an internal electron namespace
console.log('\n=== Done ===');
