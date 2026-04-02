# Electron Module Resolution Issue - Troubleshooting Guide

## Problem Description

When running the Electron dashboard app, the following error occurs:

```
TypeError: Cannot read properties of undefined (reading 'whenReady')
```

This happens because `require('electron')` returns a string path instead of the Electron API object.

## Root Cause Analysis

After extensive investigation, this was identified as a **system-level issue**, not a code issue:

### Evidence
1. **`process.type: undefined`** - The main process is not properly initialized
2. **`process.versions.electron: 28.0.0`** - Confirms running inside Electron
3. **`electron in builtinModules: false`** - Electron's internal module is not registered
4. **Clean folder test fails** - Even without node_modules, the same issue occurs

### Diagnostic Output
```javascript
process.type: undefined  // Should be 'browser' for main process
process.versions.electron: 28.0.0  // Correctly set
builtinModules includes 'electron': false  // Should be true
```

### What This Means
Electron's browser process is not initializing correctly on this Windows system. The internal 'electron' module registration happens during Electron startup, but something is preventing this from occurring.

## Possible Causes

1. **Windows Insider Preview Build** (10.0.26200.7462)
   - Very recent Windows build may have incompatibilities
   - Try stable Windows 10/11 release

2. **Shell Environment**
   - Git Bash may interfere with Electron's process spawning
   - Try running from Windows CMD or PowerShell directly

3. **Security Software**
   - Antivirus/EDR may block Electron's browser process initialization
   - Try temporarily disabling security software

4. **Sandbox Restrictions**
   - Windows sandbox policies may restrict Electron
   - Check Windows Defender Application Guard settings

## Workarounds

### Option 1: Use Windows CMD directly
```cmd
cd c:\Users\User\Desktop\Coding_engine\dashboard-app
npm run build
.\node_modules\electron\dist\electron.exe .
```

### Option 2: Use the Web-Based Dashboard
The dashboard can run as a standard web application without Electron:

```bash
cd dashboard-app
npm run dev:web
```

Then open `http://localhost:5173` in your browser.

### Option 3: Try Different Machine
Test on a different Windows machine with a stable OS version.

### Option 4: Use WSL2
Run Electron inside WSL2 with an X server:

```bash
# In WSL2
export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0
npm run dev
```

## Web Dashboard Alternative

A web-based version of the dashboard is available that provides the same functionality without requiring Electron:

- **Project Management**: Works identically
- **Live Preview**: Uses iframe instead of embedded window
- **Docker Integration**: Calls Docker API directly
- **WebSocket**: Connects to Engine API for real-time updates

To use the web dashboard:
```bash
cd dashboard-app
npm run dev:web
# Open http://localhost:5173
```

## Technical Details

### The npm `electron` package
The `node_modules/electron/index.js` file exports the path to `electron.exe`:
```javascript
module.exports = getElectronPath();  // Returns string like "C:\...\electron.exe"
```

When running inside Electron, `require('electron')` should resolve to the built-in module instead. However, on this system, the built-in module is not being registered, causing the npm package to take precedence.

### What was tried
1. Module resolution shims - Didn't work
2. Different Electron versions (22, 25, 27, 28) - Same issue
3. Renaming/removing npm electron package - Leads to "Cannot find module"
4. Direct binary execution - Same initialization issue

## Versions Tested

| Electron Version | Result |
|------------------|--------|
| 22.0.0 | Same issue |
| 25.0.0 | Same issue |
| 27.0.0 | Same issue |
| 28.0.0 | Same issue |

## Reporting

If you encounter this issue, please report:
1. Windows version (`winver`)
2. Node.js version (`node -v`)
3. Shell being used (CMD, PowerShell, Git Bash)
4. Security software installed
5. Output of the diagnostic script (see below)

### Diagnostic Script
```javascript
// diagnose-electron.js
console.log('process.type:', process.type);
console.log('process.versions.electron:', process.versions.electron);
console.log('builtinModules:', require('module').builtinModules);
try {
  const e = require('electron');
  console.log('require electron result:', typeof e, e);
} catch (err) {
  console.log('require electron error:', err.message);
}
```

Run with: `.\node_modules\electron\dist\electron.exe diagnose-electron.js`
