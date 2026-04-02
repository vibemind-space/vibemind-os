/**
 * ServiceManager — Auto-starts and monitors backend services for one-click Generate.
 *
 * Services managed:
 *   1. FastAPI server (python -m uvicorn src.api.main:app)
 *   2. Docker Desktop (health check only, user must start manually)
 *
 * Lifecycle:
 *   Electron starts → ServiceManager.startAll()
 *     → spawn FastAPI child process
 *     → poll /health until ready
 *     → notify renderer via IPC event
 *   Electron quits → ServiceManager.stopAll()
 *     → kill FastAPI child process
 */

import { ChildProcess, spawn } from 'child_process'
import { join } from 'path'
import { existsSync } from 'fs'
import { execSync } from 'child_process'
import { BrowserWindow } from 'electron'

export interface ServiceStatus {
  name: string
  status: 'stopped' | 'starting' | 'running' | 'error'
  url?: string
  pid?: number
  error?: string
  upSince?: string
}

export interface AllServiceStatus {
  fastapi: ServiceStatus
  docker: ServiceStatus
  python: ServiceStatus
}

export class ServiceManager {
  private fastApiProcess: ChildProcess | null = null
  private fastApiStatus: ServiceStatus = { name: 'FastAPI', status: 'stopped' }
  private dockerStatus: ServiceStatus = { name: 'Docker', status: 'stopped' }
  private pythonStatus: ServiceStatus = { name: 'Python', status: 'stopped' }
  private engineRoot: string
  private apiPort: number
  private healthCheckInterval: ReturnType<typeof setInterval> | null = null
  private mainWindow: BrowserWindow | null = null

  constructor(engineRoot: string, apiPort: number = 8000) {
    this.engineRoot = engineRoot
    this.apiPort = apiPort
  }

  setMainWindow(win: BrowserWindow | null): void {
    this.mainWindow = win
  }

  /**
   * Start all services in order:
   * 1. Check Python availability
   * 2. Check Docker availability
   * 3. Start FastAPI server
   */
  async startAll(): Promise<AllServiceStatus> {
    console.log('[ServiceManager] Starting all services...')

    // 1. Check Python
    this.pythonStatus = this.checkPython()
    this.broadcastStatus()

    // 2. Check Docker
    this.dockerStatus = this.checkDocker()
    this.broadcastStatus()

    // 3. Start FastAPI (only if Python is available)
    if (this.pythonStatus.status === 'running') {
      await this.startFastAPI()
    } else {
      this.fastApiStatus = {
        name: 'FastAPI',
        status: 'error',
        error: 'Python not available — cannot start FastAPI server'
      }
    }

    this.broadcastStatus()

    // 4. Start periodic health monitoring (every 10s)
    this.startHealthMonitor()

    return this.getAllStatus()
  }

  /**
   * Stop all managed services
   */
  async stopAll(): Promise<void> {
    console.log('[ServiceManager] Stopping all services...')

    // Stop health monitor
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval)
      this.healthCheckInterval = null
    }

    // Kill FastAPI process
    await this.stopFastAPI()
  }

  /**
   * Get status of all services
   */
  getAllStatus(): AllServiceStatus {
    return {
      fastapi: { ...this.fastApiStatus },
      docker: { ...this.dockerStatus },
      python: { ...this.pythonStatus },
    }
  }

  // ── Python Check ──────────────────────────────────────────────────────

  private checkPython(): ServiceStatus {
    try {
      const version = execSync('python --version', {
        encoding: 'utf-8',
        stdio: 'pipe',
        cwd: this.engineRoot,
      }).trim()
      console.log(`[ServiceManager] Python found: ${version}`)
      return { name: 'Python', status: 'running', error: undefined }
    } catch {
      // Try python3 on non-Windows
      try {
        const version = execSync('python3 --version', {
          encoding: 'utf-8',
          stdio: 'pipe',
          cwd: this.engineRoot,
        }).trim()
        console.log(`[ServiceManager] Python3 found: ${version}`)
        return { name: 'Python', status: 'running', error: undefined }
      } catch {
        console.error('[ServiceManager] Python not found')
        return {
          name: 'Python',
          status: 'error',
          error: 'Python not found in PATH. Install Python 3.11+ and add to PATH.',
        }
      }
    }
  }

  // ── Docker Check ──────────────────────────────────────────────────────

  private checkDocker(): ServiceStatus {
    try {
      execSync('docker info', { encoding: 'utf-8', stdio: 'pipe' })
      console.log('[ServiceManager] Docker is running')
      return { name: 'Docker', status: 'running' }
    } catch {
      console.warn('[ServiceManager] Docker not accessible')
      return {
        name: 'Docker',
        status: 'error',
        error: 'Docker Desktop is not running. Start Docker Desktop for VNC preview and sandbox features.',
      }
    }
  }

  // ── FastAPI ───────────────────────────────────────────────────────────

  private async startFastAPI(): Promise<void> {
    // Check if FastAPI is already running (external instance)
    const alreadyRunning = await this.checkFastAPIHealth()
    if (alreadyRunning) {
      console.log('[ServiceManager] FastAPI already running on port', this.apiPort)
      this.fastApiStatus = {
        name: 'FastAPI',
        status: 'running',
        url: `http://localhost:${this.apiPort}`,
        upSince: new Date().toISOString(),
      }
      return
    }

    // Determine Python command
    const pythonCmd = this.getPythonCommand()
    if (!pythonCmd) {
      this.fastApiStatus = {
        name: 'FastAPI',
        status: 'error',
        error: 'Python not available',
      }
      return
    }

    console.log(`[ServiceManager] Starting FastAPI on port ${this.apiPort}...`)
    this.fastApiStatus = { name: 'FastAPI', status: 'starting' }
    this.broadcastStatus()

    try {
      // Spawn: python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
      this.fastApiProcess = spawn(
        pythonCmd,
        [
          '-m', 'uvicorn',
          'src.api.main:app',
          '--host', '0.0.0.0',
          '--port', String(this.apiPort),
        ],
        {
          cwd: this.engineRoot,
          env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',  // Force unbuffered output
            PYTHONIOENCODING: 'utf-8',
          },
          stdio: ['ignore', 'pipe', 'pipe'],
          // On Windows, don't create a console window
          windowsHide: true,
        }
      )

      const pid = this.fastApiProcess.pid
      console.log(`[ServiceManager] FastAPI process spawned with PID ${pid}`)

      // Capture stdout (with error handling for broken pipes)
      this.fastApiProcess.stdout?.on('data', (data: Buffer) => {
        try {
          const msg = data.toString('utf-8').trim()
          if (msg) {
            console.log(`[FastAPI] ${msg}`)
          }
        } catch { /* ignore write errors */ }
      })
      this.fastApiProcess.stdout?.on('error', () => { /* ignore pipe errors */ })

      // Capture stderr (with error handling for broken pipes)
      this.fastApiProcess.stderr?.on('data', (data: Buffer) => {
        try {
          const msg = data.toString('utf-8').trim()
          if (msg) {
            console.error(`[FastAPI:err] ${msg}`)
          }
        } catch { /* ignore write errors */ }
      })
      this.fastApiProcess.stderr?.on('error', () => { /* ignore pipe errors */ })

      // Handle process exit
      this.fastApiProcess.on('exit', (code, signal) => {
        console.log(`[ServiceManager] FastAPI exited with code=${code} signal=${signal}`)
        this.fastApiProcess = null
        if (this.fastApiStatus.status !== 'stopped') {
          this.fastApiStatus = {
            name: 'FastAPI',
            status: 'error',
            error: `Process exited unexpectedly (code=${code})`,
          }
          this.broadcastStatus()
        }
      })

      this.fastApiProcess.on('error', (err) => {
        console.error('[ServiceManager] FastAPI spawn error:', err)
        this.fastApiProcess = null
        this.fastApiStatus = {
          name: 'FastAPI',
          status: 'error',
          error: `Failed to start: ${err.message}`,
        }
        this.broadcastStatus()
      })

      // Poll health endpoint until ready (max 30 seconds)
      const ready = await this.waitForFastAPI(30_000)
      if (ready) {
        this.fastApiStatus = {
          name: 'FastAPI',
          status: 'running',
          url: `http://localhost:${this.apiPort}`,
          pid: pid,
          upSince: new Date().toISOString(),
        }
        console.log('[ServiceManager] FastAPI is ready!')
      } else {
        this.fastApiStatus = {
          name: 'FastAPI',
          status: 'error',
          pid: pid,
          error: 'FastAPI did not become ready within 30 seconds',
        }
        console.error('[ServiceManager] FastAPI failed to become ready')
      }
    } catch (err: any) {
      console.error('[ServiceManager] Failed to start FastAPI:', err)
      this.fastApiStatus = {
        name: 'FastAPI',
        status: 'error',
        error: err.message,
      }
    }
  }

  private async stopFastAPI(): Promise<void> {
    if (this.fastApiProcess) {
      console.log('[ServiceManager] Stopping FastAPI...')
      this.fastApiStatus = { name: 'FastAPI', status: 'stopped' }

      try {
        // On Windows, need to kill the process tree
        if (process.platform === 'win32' && this.fastApiProcess.pid) {
          execSync(`taskkill /PID ${this.fastApiProcess.pid} /T /F`, {
            stdio: 'pipe',
          })
        } else {
          this.fastApiProcess.kill('SIGTERM')
        }
      } catch (err) {
        console.warn('[ServiceManager] Error killing FastAPI process:', err)
      }

      this.fastApiProcess = null
    }
  }

  private async waitForFastAPI(timeoutMs: number): Promise<boolean> {
    const startTime = Date.now()
    const interval = 1000 // Poll every second

    while (Date.now() - startTime < timeoutMs) {
      const healthy = await this.checkFastAPIHealth()
      if (healthy) return true
      await this.sleep(interval)
    }
    return false
  }

  private async checkFastAPIHealth(): Promise<boolean> {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 3000)

      // Use 127.0.0.1 instead of localhost to avoid IPv6 resolution delay on Windows
      const response = await fetch(`http://127.0.0.1:${this.apiPort}/health`, {
        signal: controller.signal,
      })

      clearTimeout(timeoutId)
      if (response.ok) {
        console.log('[ServiceManager] Health check passed (200 OK)')
      }
      return response.ok
    } catch {
      return false
    }
  }

  // ── Health Monitor ────────────────────────────────────────────────────

  private startHealthMonitor(): void {
    // Check services every 10 seconds
    this.healthCheckInterval = setInterval(async () => {
      // Re-check FastAPI health
      if (this.fastApiStatus.status === 'running') {
        const healthy = await this.checkFastAPIHealth()
        if (!healthy) {
          console.warn('[ServiceManager] FastAPI health check failed — attempting restart...')
          this.fastApiStatus = {
            name: 'FastAPI',
            status: 'error',
            error: 'Health check failed',
          }
          this.broadcastStatus()

          // Try to restart
          await this.startFastAPI()
          this.broadcastStatus()
        }
      } else if (this.fastApiStatus.status === 'error' && this.fastApiProcess) {
        // Process is alive but was marked as error (e.g. slow startup) — re-check
        const healthy = await this.checkFastAPIHealth()
        if (healthy) {
          console.log('[ServiceManager] FastAPI recovered — now healthy!')
          this.fastApiStatus = {
            name: 'FastAPI',
            status: 'running',
            url: `http://localhost:${this.apiPort}`,
            pid: this.fastApiProcess.pid,
            upSince: new Date().toISOString(),
          }
          this.broadcastStatus()
        }
      }

      // Re-check Docker
      const prevDockerStatus = this.dockerStatus.status
      this.dockerStatus = this.checkDocker()
      if (prevDockerStatus !== this.dockerStatus.status) {
        this.broadcastStatus()
      }
    }, 10_000)
  }

  // ── Helpers ───────────────────────────────────────────────────────────

  private getPythonCommand(): string | null {
    // On Windows with pyenv/shims, we need the actual executable path
    // because spawn() doesn't work with .bat shims without shell: true
    try {
      const pyPath = execSync('python -c "import sys; print(sys.executable)"', {
        encoding: 'utf-8',
        stdio: 'pipe',
        cwd: this.engineRoot,
      }).trim()
      if (pyPath && existsSync(pyPath)) {
        console.log(`[ServiceManager] Resolved Python path: ${pyPath}`)
        return pyPath
      }
      return 'python'
    } catch {
      try {
        const pyPath = execSync('python3 -c "import sys; print(sys.executable)"', {
          encoding: 'utf-8',
          stdio: 'pipe',
          cwd: this.engineRoot,
        }).trim()
        if (pyPath && existsSync(pyPath)) {
          console.log(`[ServiceManager] Resolved Python3 path: ${pyPath}`)
          return pyPath
        }
        return 'python3'
      } catch {
        return null
      }
    }
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  private broadcastStatus(): void {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send('services:status-update', this.getAllStatus())
    }
  }
}
