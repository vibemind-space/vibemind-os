// Test loading Electron's builtin modules

console.log('=== Testing Electron Builtin Modules ===');

try {
  const browserInit = require('electron/js2c/browser_init');
  console.log('browser_init loaded:', typeof browserInit);
  console.log('browser_init keys:', Object.keys(browserInit || {}).slice(0, 10));
} catch (e) {
  console.log('browser_init error:', e.message);
}

try {
  const nodeInit = require('electron/js2c/node_init');
  console.log('node_init loaded:', typeof nodeInit);
  console.log('node_init keys:', Object.keys(nodeInit || {}).slice(0, 10));
} catch (e) {
  console.log('node_init error:', e.message);
}

// Try to find electron module in a different way
console.log('');
console.log('=== Checking global scope ===');
console.log('global.electron:', typeof global.electron);
console.log('');

// Check what process._linkedBinding can give us
if (process._linkedBinding) {
  console.log('=== Testing _linkedBinding ===');
  const testBindings = [
    'electron_browser_app',
    'electron_browser_window',
    'electron_browser_web_contents',
    'electron_common_v8_util',
    'electron_common_clipboard',
    'electron_common_screen'
  ];

  for (const name of testBindings) {
    try {
      const binding = process._linkedBinding(name);
      console.log(`${name}: ${typeof binding} - keys: ${Object.keys(binding || {}).slice(0, 5).join(', ')}`);
    } catch (e) {
      console.log(`${name}: ${e.message}`);
    }
  }
}

process.exit(0);
