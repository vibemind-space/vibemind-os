// Simple test to check electron module loading
console.log('CWD:', process.cwd());
console.log('Module paths:', module.paths);

const e = require('electron');
console.log('Type of electron:', typeof e);
console.log('Is string:', typeof e === 'string');
console.log('Has app:', e && e.app !== undefined);

if (e.app) {
  console.log('SUCCESS: Got real electron module');
  e.app.quit();
} else {
  console.log('FAILED: Did not get real electron module');
  console.log('Value:', String(e).substring(0, 100));
  process.exit(1);
}
