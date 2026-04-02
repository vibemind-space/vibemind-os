/**
 * Simple API Server for Desktop Client Setup
 * Allows frontend to trigger permission setup via button click
 */
import express from 'express';
import { exec, spawn } from 'child_process';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3001;

app.use(cors());
app.use(express.json());

/**
 * Check if script is running with admin privileges
 */
function isAdmin() {
  return new Promise((resolve) => {
    exec('net session', (error) => {
      resolve(!error);
    });
  });
}

/**
 * Run PowerShell script and stream output
 */
function runPowerShellScript(scriptPath, res) {
  return new Promise((resolve, reject) => {
    const powershell = spawn('powershell.exe', [
      '-ExecutionPolicy', 'Bypass',
      '-File', scriptPath
    ], {
      cwd: __dirname,
      windowsHide: false
    });

    let stdout = '';
    let stderr = '';

    powershell.stdout.on('data', (data) => {
      const output = data.toString();
      stdout += output;

      // Stream output to client in real-time
      res.write(`data: ${JSON.stringify({ type: 'stdout', message: output })}\n\n`);
    });

    powershell.stderr.on('data', (data) => {
      const output = data.toString();
      stderr += output;

      res.write(`data: ${JSON.stringify({ type: 'stderr', message: output })}\n\n`);
    });

    powershell.on('close', (code) => {
      if (code === 0) {
        resolve({ success: true, stdout, stderr });
      } else {
        reject({ success: false, code, stdout, stderr });
      }
    });

    powershell.on('error', (error) => {
      reject({ success: false, error: error.message, stdout, stderr });
    });
  });
}

/**
 * GET /api/setup/check-admin
 * Check if server is running with admin privileges
 */
app.get('/api/setup/check-admin', async (req, res) => {
  try {
    const admin = await isAdmin();
    res.json({
      isAdmin: admin,
      message: admin
        ? 'Server has administrator privileges'
        : 'Server needs administrator privileges for setup'
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * POST /api/setup/run-permissions
 * Run the permission setup script
 */
app.post('/api/setup/run-permissions', async (req, res) => {
  try {
    // Set headers for Server-Sent Events (SSE)
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // Check admin privileges
    const admin = await isAdmin();
    if (!admin) {
      res.write(`data: ${JSON.stringify({
        type: 'error',
        message: 'Server must run as Administrator to modify permissions'
      })}\n\n`);
      res.end();
      return;
    }

    // Run setup script
    const scriptPath = path.join(__dirname, 'setup-permissions.ps1');

    res.write(`data: ${JSON.stringify({
      type: 'info',
      message: 'Starting permission setup...'
    })}\n\n`);

    try {
      const result = await runPowerShellScript(scriptPath, res);

      res.write(`data: ${JSON.stringify({
        type: 'success',
        message: 'Setup completed successfully!',
        result
      })}\n\n`);
    } catch (error) {
      res.write(`data: ${JSON.stringify({
        type: 'error',
        message: 'Setup failed',
        error
      })}\n\n`);
    }

    res.end();
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * POST /api/setup/check-permissions
 * Run diagnostic script
 */
app.post('/api/setup/check-permissions', async (req, res) => {
  try {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const scriptPath = path.join(__dirname, 'check-screen-capture-permissions.ps1');

    res.write(`data: ${JSON.stringify({
      type: 'info',
      message: 'Running diagnostics...'
    })}\n\n`);

    try {
      const result = await runPowerShellScript(scriptPath, res);

      res.write(`data: ${JSON.stringify({
        type: 'success',
        message: 'Diagnostics complete',
        result
      })}\n\n`);
    } catch (error) {
      res.write(`data: ${JSON.stringify({
        type: 'error',
        message: 'Diagnostics failed',
        error
      })}\n\n`);
    }

    res.end();
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * POST /api/setup/restart-client
 * Restart the desktop capture client
 */
app.post('/api/setup/restart-client', async (req, res) => {
  try {
    // Kill existing python processes running dual_screen_capture_client.py
    exec('taskkill /F /IM python.exe /FI "WINDOWTITLE eq *dual_screen_capture_client*"', (error) => {
      if (error) {
        console.log('No existing client process found or could not kill');
      }
    });

    // Wait a bit for process to terminate
    setTimeout(() => {
      // Start new client process
      const clientScript = path.join(__dirname, 'dual_screen_capture_client.py');

      const python = spawn('python', [clientScript], {
        cwd: __dirname,
        detached: true,
        stdio: 'ignore'
      });

      python.unref();

      res.json({
        success: true,
        message: 'Desktop client restarted',
        pid: python.pid
      });
    }, 1000);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * GET /api/setup/status
 * Check if desktop client is running
 */
app.get('/api/setup/status', (req, res) => {
  exec('tasklist /FI "IMAGENAME eq python.exe" /FO CSV', (error, stdout) => {
    const isRunning = stdout.includes('python.exe');

    res.json({
      clientRunning: isRunning,
      message: isRunning
        ? 'Desktop client is running'
        : 'Desktop client is not running'
    });
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Desktop Client Setup API running on http://localhost:${PORT}`);
  console.log('');
  console.log('Available endpoints:');
  console.log('  GET  /api/setup/check-admin      - Check admin privileges');
  console.log('  POST /api/setup/run-permissions  - Run permission setup');
  console.log('  POST /api/setup/check-permissions - Run diagnostics');
  console.log('  POST /api/setup/restart-client   - Restart desktop client');
  console.log('  GET  /api/setup/status           - Check client status');
  console.log('');

  isAdmin().then(admin => {
    if (admin) {
      console.log('✅ Running with Administrator privileges');
    } else {
      console.log('⚠️  Not running as Administrator - setup functions will be limited');
      console.log('   Run as admin: Right-click and "Run as administrator"');
    }
  });
});
