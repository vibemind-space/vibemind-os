// Try to use the shim
let electron;
try {
  electron = require('./electron-shim');
  console.log('[Test] Using electron-shim');
} catch (e) {
  console.log('[Test] Shim failed:', e.message);
  electron = require('electron');
}

const { app, BrowserWindow } = electron;
console.log('[Test] app:', typeof app);
console.log('[Test] BrowserWindow:', typeof BrowserWindow);

if (app) {
  app.whenReady().then(() => {
    console.log('[Test] App is ready!');
    app.quit();
  });
} else {
  console.log('[Test] ERROR: app is not available');
  process.exit(1);
}
