// Diagnostic script to find available Electron APIs
console.log('=== Electron Environment Diagnostics ===');
console.log('');

console.log('process.versions.electron:', process.versions.electron);
console.log('process.type:', process.type);
console.log('');

console.log('typeof process.electronBinding:', typeof process.electronBinding);
console.log('typeof process._linkedBinding:', typeof process._linkedBinding);
console.log('');

// Check Module builtins
const Module = require('module');
console.log('electron in builtinModules:', Module.builtinModules.includes('electron'));
console.log('');

// List some builtinModules
console.log('First 20 builtin modules:', Module.builtinModules.slice(0, 20));
console.log('');

// Try to find electron-related properties on process
const electronProps = Object.keys(process).filter(k =>
  k.toLowerCase().includes('electron') ||
  k.toLowerCase().includes('binding')
);
console.log('Electron-related process properties:', electronProps);
console.log('');

// Try different ways to access electron
const attempts = [
  () => { const e = require('electron'); return { type: typeof e, keys: typeof e === 'object' ? Object.keys(e).slice(0, 10) : String(e).slice(0, 50) }; },
  () => { return { electronBinding: typeof process.electronBinding }; },
  () => { return { _linkedBinding: typeof process._linkedBinding }; },
];

for (let i = 0; i < attempts.length; i++) {
  try {
    console.log(`Attempt ${i + 1}:`, attempts[i]());
  } catch (e) {
    console.log(`Attempt ${i + 1} error:`, e.message);
  }
}
console.log('');

// Try _linkedBinding if available
if (typeof process._linkedBinding === 'function') {
  console.log('Testing _linkedBinding:');
  const bindings = [
    'electron_common_features',
    'electron_common_v8_util',
    'electron_common_asar',
    'electron_browser_app',
    'electron_browser_browser_window',
  ];

  for (const b of bindings) {
    try {
      const result = process._linkedBinding(b);
      console.log(`  ${b}: SUCCESS`, typeof result, result ? Object.keys(result).slice(0, 5) : 'null');
    } catch (e) {
      console.log(`  ${b}: FAILED -`, e.message.slice(0, 50));
    }
  }
}

console.log('');
console.log('=== End Diagnostics ===');
process.exit(0);
