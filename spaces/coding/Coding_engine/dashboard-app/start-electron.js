/**
 * Electron Startup Script
 *
 * This script launches the Electron app with proper environment setup.
 *
 * Key fix: Removes ELECTRON_RUN_AS_NODE environment variable which VSCode
 * (and other Electron-based IDEs) set, causing Electron to run in Node.js
 * mode instead of Electron mode.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const electronExe = path.join(__dirname, 'node_modules', 'electron', 'dist', 'electron.exe');
const mainScript = path.join(__dirname, 'out', 'main', 'main.js');

console.log('Starting Electron Dashboard...');

// Check if main script exists
if (!fs.existsSync(mainScript)) {
  console.error('Error: out/main/main.js not found. Run "npm run build" first.');
  process.exit(1);
}

// Check if electron exists
if (!fs.existsSync(electronExe)) {
  console.error('Error: electron.exe not found. Run npm install first.');
  process.exit(1);
}

// Spawn electron with the main script
// IMPORTANT: Remove ELECTRON_RUN_AS_NODE which VSCode/Atom/other Electron-based
// IDEs set, as it prevents Electron from running in proper Electron mode
// (causing require('electron') to return the npm package path instead of the APIs)
console.log('Launching Electron...');
const electronEnv = { ...process.env };
delete electronEnv.ELECTRON_RUN_AS_NODE;
electronEnv.ELECTRON_DISABLE_SECURITY_WARNINGS = 'true';

const electronProcess = spawn(electronExe, [mainScript], {
  cwd: __dirname,
  stdio: 'inherit',
  env: electronEnv
});

electronProcess.on('exit', (code) => {
  process.exit(code || 0);
});

electronProcess.on('error', (err) => {
  console.error('Failed to start Electron:', err);
  process.exit(1);
});

// Handle termination signals
process.on('SIGINT', () => {
  electronProcess.kill('SIGINT');
});

process.on('SIGTERM', () => {
  electronProcess.kill('SIGTERM');
});
