"use strict";
// Debug script to check electron module
const electron = require("electron");
console.log("electron module:", electron);
console.log("typeof electron:", typeof electron);
console.log("electron.app:", electron.app);
console.log("Object.keys(electron):", Object.keys(electron || {}));

// Try to access app directly
if (electron.app) {
  electron.app.whenReady().then(() => {
    console.log("App is ready!");
    electron.app.quit();
  });
} else {
  console.log("electron.app is undefined!");
  console.log("Full electron object:", JSON.stringify(electron, null, 2));
  process.exit(1);
}
