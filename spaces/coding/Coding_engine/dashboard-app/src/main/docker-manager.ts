import { spawn, ChildProcess, exec } from 'child_process'
import { promisify } from 'util'
import { join, resolve } from 'path'
import { existsSync } from 'fs'

const execAsync = promisify(exec)

/**
 * Sanitize a string to be used as a Docker container name.
 * Docker only allows [a-zA-Z0-9][a-zA-Z0-9_.-]
 */
function sanitizeContainerName(name: string): string {
  return name
    .normalize('NFD')                    // Decompose accented characters
    .replace(/[\u0300-\u036f]/g, '')     // Remove diacritical marks (ä→a, ö→o, etc.)
    .replace(/[^a-zA-Z0-9_.-]/g, '-')    // Replace invalid chars with dash
    .replace(/^[^a-zA-Z0-9]+/, '')       // Must start with alphanumeric
    .replace(/-+/g, '-')                 // Collapse multiple dashes
    .substring(0, 128)                   // Docker limit
}

interface ContainerInfo {
  id: string
  name: string  // Actual container name (with timestamp suffix)
  process: ChildProcess | null
  vncPort: number
  appPort: number
  status: 'starting' | 'running' | 'stopped' | 'error'
}

export class DockerManager {
  private containers = new Map<string, ContainerInfo>()
  private engineProcess: ChildProcess | null = null
  private engineRunning = false

  // Path to Coding Engine root (parent of dashboard-app)
  // __dirname in built code = .../dashboard-app/out/main/
  // We need to go up 3 levels: out/main/ → out/ → dashboard-app/ → Coding_engine/
  private engineRoot = join(__dirname, '..', '..', '..')

  /**
   * Check if a file or directory exists
   */
  private async fileExists(path: string): Promise<boolean> {
    return existsSync(path)
  }

  /**
   * Start the Coding Engine Docker stack
   */
  async startEngine(): Promise<{ success: boolean; error?: string }> {
    try {
      const composeFile = join(this.engineRoot, 'infra', 'docker', 'docker-compose.dashboard.yml')

      const { stdout, stderr } = await execAsync(
        `docker-compose -f "${composeFile}" up -d`,
        { cwd: this.engineRoot }
      )

      this.engineRunning = true
      console.log('Engine started:', stdout)

      return { success: true }
    } catch (error: any) {
      console.error('Failed to start engine:', error)
      return { success: false, error: error.message }
    }
  }

  /**
   * Stop the Coding Engine Docker stack
   */
  async stopEngine(): Promise<{ success: boolean; error?: string }> {
    try {
      const composeFile = join(this.engineRoot, 'infra', 'docker', 'docker-compose.dashboard.yml')

      await execAsync(
        `docker-compose -f "${composeFile}" down`,
        { cwd: this.engineRoot }
      )

      this.engineRunning = false
      return { success: true }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  /**
   * Get Engine status
   */
  async getEngineStatus(): Promise<{ running: boolean; services: string[] }> {
    try {
      const { stdout } = await execAsync('docker ps --format "{{.Names}}"')
      const services = stdout.trim().split('\n').filter(name =>
        name.includes('coding-engine') || name.includes('postgres') || name.includes('redis')
      )

      return { running: services.length > 0, services }
    } catch {
      return { running: false, services: [] }
    }
  }

  /**
   * Start a project container with VNC for live preview
   * Automatically detects if code exists in requirementsPath or outputDir
   */
  async startProjectContainer(
    projectId: string,
    requirementsPath: string,
    outputDir: string,
    vncPort: number,
    appPort: number
  ): Promise<{ success: boolean; vncPort?: number; appPort?: number; error?: string }> {
    try {
      const containerName = sanitizeContainerName(`project-${projectId}`)

      // Check if container already exists
      const existing = this.containers.get(projectId)
      if (existing && existing.status === 'running') {
        return { success: true, vncPort: existing.vncPort, appPort: existing.appPort }
      }

      // Stop any existing container with same name
      await this.stopProjectContainer(projectId)

      // Stop any containers using our ports to prevent "port already allocated" errors
      await this.stopContainersByPort(vncPort)
      await this.stopContainersByPort(appPort)

      // Determine mount path: check if requirementsPath has project files
      const isExistingProject = await this.fileExists(join(requirementsPath, 'app')) ||
                                await this.fileExists(join(requirementsPath, 'package.json')) ||
                                await this.fileExists(join(requirementsPath, 'requirements.txt'))

      // Ensure mount path is absolute - Docker on Windows needs full paths
      const mountPath = resolve(isExistingProject ? requirementsPath : outputDir)
      console.log(`[Project] Mount path: ${mountPath} (existing project: ${isExistingProject})`)

      // Start new container using spawn to avoid path mangling
      const dockerCmd = [
        'docker', 'run', '-d',
        '--name', containerName,
        '-v', `${mountPath}:/app`,
        '-p', `${vncPort}:6080`,
        '-p', `${appPort}:5173`,
        '-e', 'ENABLE_VNC=true',
        '-e', 'NODE_ENV=development',
        'coding-engine/sandbox:latest',
        // IMPORTANT: Use //bin/bash with double slash to prevent Git Bash from mangling
        // the path to C:/Program Files/Git/usr/bin/bash on Windows
        '//bin/bash', '-c', '//usr/local/bin/sandbox-entrypoint.sh test'
      ]

      const { stdout: containerId } = await new Promise<{ stdout: string }>((resolve, reject) => {
        const proc = spawn(dockerCmd[0], dockerCmd.slice(1), {
          shell: false,
          windowsHide: true,
          env: { ...process.env, MSYS_NO_PATHCONV: '1', MSYS2_ARG_CONV_EXCL: '*' }
        })
        let stdout = ''
        let stderr = ''
        proc.stdout?.on('data', (data) => { stdout += data.toString() })
        proc.stderr?.on('data', (data) => { stderr += data.toString() })
        proc.on('close', (code) => {
          if (code === 0) {
            resolve({ stdout })
          } else {
            reject(new Error(`Docker failed: ${stderr || stdout}`))
          }
        })
        proc.on('error', reject)
      })

      this.containers.set(projectId, {
        id: containerId.trim(),
        name: containerName,
        process: null,
        vncPort,
        appPort,
        status: 'running'
      })

      console.log(`[Project] Started container ${containerName} with VNC on port ${vncPort}`)

      return { success: true, vncPort, appPort }
    } catch (error: any) {
      console.error(`[Project] Failed to start container for ${projectId}:`, error)
      return { success: false, error: error.message }
    }
  }

  /**
   * Stop a project container
   */
  async stopProjectContainer(projectId: string): Promise<{ success: boolean; error?: string }> {
    try {
      const containerName = sanitizeContainerName(`project-${projectId}`)

      // Stop and remove container (force remove handles both running and stopped)
      try {
        await execAsync(`docker rm -f ${containerName}`)
      } catch {
        // Container doesn't exist, that's fine
      }

      this.containers.delete(projectId)

      return { success: true }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  /**
   * Stop any containers using a specific port
   * This prevents "port already allocated" errors when starting new containers
   */
  private async stopContainersByPort(port: number): Promise<void> {
    try {
      // Find containers using this port using docker ps with port filter
      const { stdout } = await execAsync(`docker ps -q --filter "publish=${port}"`)
      const containerIds = stdout.trim().split('\n').filter(id => id)

      for (const containerId of containerIds) {
        try {
          console.log(`[Docker] Stopping container ${containerId} using port ${port}`)
          await execAsync(`docker rm -f ${containerId}`)
        } catch {
          // Container might have already stopped, that's fine
        }
      }

      // Wait for port to be released by OS
      if (containerIds.length > 0) {
        console.log(`[Docker] Waiting for port ${port} to be released...`)
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    } catch {
      // No containers found or docker command failed, that's fine
    }
  }

  /**
   * Kill host processes (not Docker containers) using a specific port.
   * On Windows, uses PowerShell to find and terminate processes.
   * This is needed because stopContainersByPort only stops Docker containers,
   * but Node.js dev servers spawned directly on the host also hold ports.
   */
  private async killHostProcessOnPort(port: number): Promise<void> {
    try {
      // Use PowerShell to find process using this port
      const findCmd = `powershell -Command "Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"`

      const { stdout } = await execAsync(findCmd)
      const pids = stdout.trim().split('\n').filter(pid => pid && pid.trim() !== '' && pid.trim() !== '0')

      for (const pid of pids) {
        const trimmedPid = pid.trim()
        try {
          console.log(`[Docker] Killing host process ${trimmedPid} using port ${port}`)
          await execAsync(`powershell -Command "Stop-Process -Id ${trimmedPid} -Force -ErrorAction SilentlyContinue"`)
        } catch {
          // Process might have already exited
        }
      }

      if (pids.length > 0) {
        // Wait for port to be released
        console.log(`[Docker] Waiting for port ${port} to be released...`)
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    } catch {
      // PowerShell command failed, port likely not in use
    }
  }

  /**
   * Stop all generation containers matching a pattern (by name prefix)
   * More reliable than port-based cleanup for cases with encoding issues
   */
  private async stopGenerationContainersByPattern(pattern: string): Promise<void> {
    try {
      const { stdout } = await execAsync(`docker ps --format "{{.Names}}" --filter "name=${pattern}"`)
      const containers = stdout.trim().split('\n').filter(name => name)

      for (const containerName of containers) {
        try {
          console.log(`[Docker] Stopping container by pattern: ${containerName}`)
          await execAsync(`docker rm -f ${containerName}`)
        } catch {
          // Container might have already stopped
        }
      }

      if (containers.length > 0) {
        console.log(`[Docker] Waiting for containers to release ports...`)
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
    } catch {
      // No containers found
    }
  }

  /**
   * Get project container status
   */
  async getProjectStatus(projectId: string): Promise<{
    running: boolean
    vncPort?: number
    appPort?: number
    health?: string
  }> {
    const containerName = sanitizeContainerName(`project-${projectId}`)

    try {
      const { stdout } = await execAsync(
        `docker inspect --format='{{.State.Status}}' ${containerName}`
      )

      const status = stdout.trim()
      const info = this.containers.get(projectId)

      return {
        running: status === 'running',
        vncPort: info?.vncPort,
        appPort: info?.appPort,
        health: status
      }
    } catch {
      return { running: false }
    }
  }

  /**
   * Get container logs
   */
  async getProjectLogs(projectId: string, tail: number = 100): Promise<string> {
    const containerName = sanitizeContainerName(`project-${projectId}`)

    try {
      const { stdout } = await execAsync(`docker logs --tail ${tail} ${containerName}`)
      return stdout
    } catch (error: any) {
      return `Error fetching logs: ${error.message}`
    }
  }

  /**
   * Start a code generation job (legacy - without VNC preview)
   */
  async startGeneration(
    requirementsPath: string,
    outputDir: string
  ): Promise<{ success: boolean; error?: string }> {
    try {
      // Run generation via the engine API or directly
      const cmd = `python run_society_hybrid.py "${requirementsPath}" --output-dir "${outputDir}" --fast`

      const childProcess = spawn('python', [
        'run_society_hybrid.py',
        requirementsPath,
        '--output-dir', outputDir,
        '--fast'
      ], {
        cwd: this.engineRoot,
        detached: true,
        stdio: 'ignore',
        shell: true,
        env: { ...global.process.env }
      })

      childProcess.unref()

      return { success: true }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  /**
   * Start code generation WITH VNC preview container
   *
   * This is the main method for the Electron dashboard:
   * 1. Starts a VNC-enabled sandbox container with the output directory mounted
   * 2. Starts the Python generation process which writes to the output directory
   * 3. The container watches for changes and serves the app via VNC
   *
   * The user can see the app being built in real-time via the embedded VNC viewer.
   *
   * @param forceGenerate - If true, always run code generation even if project files exist.
   *                        Use this for orchestrator projects where we want to regenerate.
   */
  async startGenerationWithPreview(
    projectId: string,
    requirementsPath: string,
    outputDir: string,
    vncPort: number,
    appPort: number,
    forceGenerate: boolean = false
  ): Promise<{
    success: boolean
    vncPort?: number
    appPort?: number
    generationPid?: number
    error?: string
  }> {
    try {
      console.log(`[Generation] Starting with VNC preview for project ${projectId}`)
      console.log(`[Generation] Requirements: ${requirementsPath}`)
      console.log(`[Generation] Output: ${outputDir}`)
      console.log(`[Generation] VNC Port: ${vncPort}, App Port: ${appPort}`)

      // Step 1: Start VNC-enabled sandbox container
      // Use timestamp suffix to prevent name collisions when rapidly restarting
      const timestamp = Date.now().toString(36)
      const sanitizedProjectId = sanitizeContainerName(projectId)
      const containerName = sanitizeContainerName(`generation-${projectId}-${timestamp}`)
      console.log(`[Docker] Sanitized container name: ${containerName}`)

      // Stop ALL containers for this project (handles encoding mismatches and old timestamps)
      // This is more aggressive than just removing the exact name
      const projectPattern = `generation-${sanitizedProjectId}`
      await this.stopGenerationContainersByPattern(projectPattern)

      // Also stop by general pattern to handle any other encoding mismatches
      await this.stopGenerationContainersByPattern('generation-')

      // Stop any containers using our ports to prevent "port already allocated" errors
      await this.stopContainersByPort(vncPort)
      await this.stopContainersByPort(appPort)
      await this.stopContainersByPort(appPort + 1)  // Backend API port for fullstack projects

      // Also kill host processes (Node dev servers, etc.) using these ports
      // This is needed because Docker containers are not the only things that can hold ports
      await this.killHostProcessOnPort(vncPort)
      await this.killHostProcessOnPort(appPort)
      await this.killHostProcessOnPort(appPort + 1)  // Backend API port for fullstack projects

      // Wait for all ports to be fully released before proceeding
      // Windows is notoriously slow to release ports after processes are killed
      console.log('[Docker] Waiting for all ports to be released...')
      await new Promise(resolve => setTimeout(resolve, 3000))

      // Build sandbox image if not exists
      const sandboxDockerfile = join(this.engineRoot, 'infra', 'docker', 'Dockerfile.sandbox')
      const sandboxEntrypoint = join(this.engineRoot, 'infra', 'docker', 'sandbox-entrypoint.sh')

      // Check if image exists, build if not
      try {
        await execAsync('docker image inspect coding-engine/sandbox:latest')
      } catch {
        console.log('[Generation] Building sandbox image...')
        await execAsync(
          `docker build -t coding-engine/sandbox:latest -f "${sandboxDockerfile}" "${join(this.engineRoot, 'infra', 'docker')}"`,
          { cwd: this.engineRoot }
        )
      }

      // Step 2: Check if this is an existing project BEFORE starting container
      // ALWAYS check for existing code - even with forceGenerate=true
      // Orchestrator projects are complete projects that should be RUN, not regenerated
      const hasExistingCode = await this.fileExists(join(requirementsPath, 'app')) ||
                              await this.fileExists(join(requirementsPath, 'src')) ||
                              await this.fileExists(join(requirementsPath, 'package.json'))

      // For orchestrator projects with existing code: run them directly
      // For requirements files/folders without code: generate new code
      let isExistingProject = hasExistingCode
      let actualRequirementsPath = requirementsPath

      // If forceGenerate is true, ALWAYS generate new code (don't just run existing)
      if (forceGenerate) {
        isExistingProject = false  // Force generation mode

        // Look for requirements.json to use as input
        const nestedReqs = join(requirementsPath, 'docs', 'requirements', 'imported_requirements.json')
        const rootReqs = join(requirementsPath, 'requirements.json')

        if (await this.fileExists(nestedReqs)) {
          actualRequirementsPath = nestedReqs
          console.log(`[VNC] forceGenerate=true, using nested requirements: ${nestedReqs}`)
        } else if (await this.fileExists(rootReqs)) {
          actualRequirementsPath = rootReqs
          console.log(`[VNC] forceGenerate=true, using root requirements: ${rootReqs}`)
        } else {
          // Use the requirementsPath as-is (might be a requirements file itself)
          console.log(`[VNC] forceGenerate=true, using path as requirements: ${requirementsPath}`)
        }
      }

      console.log(`[VNC] forceGenerate: ${forceGenerate}, hasExistingCode: ${hasExistingCode}, isExistingProject: ${isExistingProject}`)

      // Determine which path to mount - ensure it's absolute for Docker
      const mountPath = resolve(isExistingProject ? requirementsPath : outputDir)
      console.log(`[VNC] Mount path: ${mountPath} (existing project: ${isExistingProject})`)

      // Start container with VNC enabled
      // Use different bash script based on project type
      // IMPORTANT: Use // prefix on Linux paths to prevent Git Bash from mangling them to Windows paths
      let bashScript: string
      if (isExistingProject) {
        // For existing projects, start immediately
        bashScript = 'echo "Starting existing project..." && //usr/local/bin/sandbox-entrypoint.sh test'
      } else {
        // For new generation, wait for files to appear
        bashScript = 'echo "Waiting for generated files..." && while [ ! -f //app/package.json ] && [ ! -f //app/requirements.txt ]; do sleep 2; done && echo "Files detected, starting sandbox..." && //usr/local/bin/sandbox-entrypoint.sh test'
      }

      // Detect project type to set correct environment variable
      const hasPythonReqs = await this.fileExists(join(mountPath, 'requirements.txt'))
      const hasPackageJson = await this.fileExists(join(mountPath, 'package.json'))

      // Check if Node project has both express AND vite/react (node_fullstack)
      let isNodeFullstack = false
      if (hasPackageJson && !hasPythonReqs) {
        try {
          const pkgJson = require('fs').readFileSync(join(mountPath, 'package.json'), 'utf-8')
          const hasExpress = pkgJson.includes('"express"') || pkgJson.includes('"fastify"')
          const hasVite = pkgJson.includes('"vite"') || pkgJson.includes('"react"')
          isNodeFullstack = hasExpress && hasVite
        } catch {
          // Ignore errors reading package.json
        }
      }

      // Fullstack: has both frontend (package.json) AND backend (requirements.txt)
      const isFullstack = hasPackageJson && hasPythonReqs
      const isPythonOnly = hasPythonReqs && !hasPackageJson
      const projectType = isFullstack ? 'fullstack'
        : isNodeFullstack ? 'node_fullstack'
        : isPythonOnly ? 'python_fastapi'
        : hasPackageJson ? 'react'
        : 'auto'

      console.log(`[VNC] Detected project type: ${projectType} (fullstack: ${isFullstack}, nodeFullstack: ${isNodeFullstack})`)

      // Build docker command as array to avoid shell escaping issues
      // Port mapping depends on project type:
      // - Fullstack: frontend (5173) + API (8000)
      // - Python only: API (8000)
      // - Node/React: frontend (5173)
      const portMappings = isFullstack
        ? ['-p', `${appPort}:5173`, '-p', `${appPort + 1}:8000`]  // Both ports
        : isPythonOnly
          ? ['-p', `${appPort}:8000`]  // API only
          : ['-p', `${appPort}:5173`]  // Frontend only

      const dockerCmd = [
        'docker', 'run', '-d',
        '--name', containerName,
        '-v', `${mountPath}:/app`,
        '-p', `${vncPort}:6080`,
        ...portMappings,
        '-e', 'ENABLE_VNC=true',
        '-e', 'NODE_ENV=development',
        '-e', `PROJECT_TYPE=${projectType}`,
        '-e', `PROJECT_ID=${projectId}`,
        '-e', `CONTAINER_NAME=${containerName}`,
        // Engine API URL for error reporting (host.docker.internal resolves to host machine)
        '-e', 'ENGINE_API_URL=http://host.docker.internal:8000',
        'coding-engine/sandbox:latest',
        // IMPORTANT: Use //bin/bash with double slash to prevent Git Bash from mangling
        // the path to C:/Program Files/Git/usr/bin/bash on Windows
        '//bin/bash', '-c', bashScript
      ]

      // Use spawn instead of exec for better Windows compatibility
      // Set MSYS_NO_PATHCONV=1 to prevent Git Bash from mangling paths like //bin/bash
      // Retry loop for port conflicts - Windows can be slow to release ports
      let containerId = ''
      const maxRetries = 3
      for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
          const result = await new Promise<{ stdout: string }>((resolve, reject) => {
            const proc = spawn(dockerCmd[0], dockerCmd.slice(1), {
              shell: false,
              windowsHide: true,
              env: { ...process.env, MSYS_NO_PATHCONV: '1', MSYS2_ARG_CONV_EXCL: '*' }
            })
            let stdout = ''
            let stderr = ''
            proc.stdout?.on('data', (data) => { stdout += data.toString() })
            proc.stderr?.on('data', (data) => { stderr += data.toString() })
            proc.on('close', (code) => {
              if (code === 0) {
                resolve({ stdout })
              } else {
                reject(new Error(`Docker failed: ${stderr || stdout}`))
              }
            })
            proc.on('error', reject)
          })
          containerId = result.stdout
          break  // Success, exit retry loop
        } catch (error: any) {
          const errorMsg = error.message || ''
          if (errorMsg.includes('port') && (errorMsg.includes('not available') || errorMsg.includes('already allocated')) && attempt < maxRetries - 1) {
            console.log(`[Docker] Port conflict on attempt ${attempt + 1}, retrying in 3s...`)
            // Force kill any lingering processes on all ports
            await this.killHostProcessOnPort(vncPort)
            await this.killHostProcessOnPort(appPort)
            await this.killHostProcessOnPort(appPort + 1)
            await this.stopContainersByPort(vncPort)
            await this.stopContainersByPort(appPort)
            await this.stopContainersByPort(appPort + 1)
            await new Promise(resolve => setTimeout(resolve, 3000))
          } else {
            throw error  // Not a port error or max retries reached
          }
        }
      }

      this.containers.set(projectId, {
        id: containerId.trim(),
        name: containerName,
        process: null,
        vncPort,
        appPort,
        status: 'starting'
      })

      console.log(`[VNC] Container ${containerName} started`)

      // isExistingProject was already determined above before starting container
      let processPid: number | undefined

      if (isExistingProject) {
        // Existing project: sandbox-entrypoint.sh handles startup via PROJECT_TYPE env var
        // No need for separate docker exec - entrypoint already starts the app
        console.log(`[VNC] Existing project from ${requirementsPath} - entrypoint handling startup`)

        const container = this.containers.get(projectId)
        if (container) {
          container.status = 'running'
        }
      } else {
        // Generate new code (requirementsPath is a JSON file or directory with requirements)
        console.log(`[VNC] Generating new code from ${requirementsPath}`)

        // Step 3a: Ensure output directory exists
        if (!existsSync(outputDir)) {
          const { mkdirSync } = require('fs')
          mkdirSync(outputDir, { recursive: true })
          console.log(`[Generation] Created output directory: ${outputDir}`)
        }

        // Step 3a-2: Clear any stale checkpoint for fresh generation
        const checkpointFile = join(outputDir, '.generation_checkpoint.json')
        if (existsSync(checkpointFile)) {
          const { unlinkSync } = require('fs')
          unlinkSync(checkpointFile)
          console.log(`[Generation] Cleared stale checkpoint for fresh generation`)
        }

        // Step 3b: Initialize git repo in output directory with CLAUDE.md at root
        try {
          console.log(`[Git] Initializing git repo in ${outputDir}`)
          await execAsync(`git init`, { cwd: outputDir })

          const { mkdirSync, writeFileSync, unlinkSync: fsUnlink, readdirSync } = require('fs')

          // Clean up any 'nul' files (Windows shell redirection artifacts)
          // These files are created when shell commands use '2>nul' in certain contexts
          const cleanupNulFiles = (dir: string) => {
            try {
              const entries = readdirSync(dir, { withFileTypes: true })
              for (const entry of entries) {
                const fullPath = join(dir, entry.name)
                if (entry.isFile() && entry.name === 'nul') {
                  console.log(`[Git] Removing stale 'nul' file: ${fullPath}`)
                  try { fsUnlink(fullPath) } catch { /* ignore */ }
                } else if (entry.isDirectory() && !['node_modules', '.git'].includes(entry.name)) {
                  cleanupNulFiles(fullPath)
                }
              }
            } catch { /* ignore errors */ }
          }
          cleanupNulFiles(outputDir)

          // Write default CLAUDE.md at project root (not in .claude/ folder)
          const claudeMd = `# Claude Instructions for ${projectId}

## Project Overview
This project was generated by the Coding Engine.

## Key Files
- Check package.json for dependencies
- Check src/ for source code

## Build Commands
\`\`\`bash
npm install
npm run dev
\`\`\`
`
          writeFileSync(join(outputDir, 'CLAUDE.md'), claudeMd)
          console.log(`[Git] Created CLAUDE.md at project root`)

          // Create .gitignore to exclude common artifacts
          const gitignorePath = join(outputDir, '.gitignore')
          if (!existsSync(gitignorePath)) {
            const gitignoreContent = `# Dependencies
node_modules/
.pnpm-store/

# Build outputs
dist/
build/
out/

# Environment
.env
.env.local
.env.*.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Windows shell artifacts
nul
`
            writeFileSync(gitignorePath, gitignoreContent)
            console.log(`[Git] Created .gitignore`)
          }

          // Add safe.directory config (Windows ownership fix)
          await execAsync(`git config --global --add safe.directory "${outputDir.replace(/\\/g, '/')}"`, { cwd: outputDir })

          // Initial commit
          await execAsync(`git add -A && git commit -m "Initial scaffold (auto-generated)" --allow-empty`, { cwd: outputDir })
          console.log(`[Git] Initial commit created`)
        } catch (gitError: any) {
          // Git init is optional, continue even if it fails
          console.warn(`[Git] Warning: ${gitError.message}`)
        }

        // Step 3c: Spawn generation process
        // Use actualRequirementsPath which may be a nested requirements.json
        console.log(`[Generation] Spawning with requirements: ${actualRequirementsPath}`)
        const generationProcess = spawn('python', [
          'run_society_hybrid.py',
          actualRequirementsPath,
          '--output-dir', outputDir,
          '--fast',
          '--no-preview',
          '--continuous-sandbox',       // Enable DeploymentTeam continuous test cycles
          '--enable-continuous-debug',  // Enable ContinuousDebugAgent for auto-fixing
        ], {
          cwd: this.engineRoot,
          detached: false,
          stdio: ['ignore', 'pipe', 'pipe'],
          shell: true,
          env: (() => {
            const env = { ...process.env }
            // Remove CLAUDECODE env var to prevent "nested session" error
            // when the generation pipeline spawns Claude CLI subprocesses
            delete env.CLAUDECODE
            return env
          })()
        })

        processPid = generationProcess.pid

        generationProcess.stdout?.on('data', (data) => {
          console.log(`[Generation] ${data.toString().trim()}`)
        })
        generationProcess.stderr?.on('data', (data) => {
          console.error(`[Generation] ${data.toString().trim()}`)
        })

        generationProcess.on('exit', (code) => {
          console.log(`[Generation] Process exited with code ${code}`)
          const container = this.containers.get(projectId)
          if (container) {
            container.status = code === 0 ? 'running' : 'error'
          }
        })

        const container = this.containers.get(projectId)
        if (container) {
          container.process = generationProcess
          container.status = 'running'
        }
      }

      return {
        success: true,
        vncPort,
        appPort,
        generationPid: processPid
      }
    } catch (error: any) {
      console.error(`[Generation] Failed:`, error)
      return { success: false, error: error.message }
    }
  }

  /**
   * Stop a generation (container + process)
   */
  async stopGeneration(projectId: string): Promise<{ success: boolean; error?: string }> {
    try {
      const container = this.containers.get(projectId)

      // Kill the generation process if running
      if (container?.process && !container.process.killed) {
        container.process.kill('SIGTERM')
      }

      // Stop the container - use stored name (with timestamp) if available
      // Otherwise use pattern-based cleanup to catch all containers for this project
      if (container?.name) {
        try {
          await execAsync(`docker rm -f ${container.name}`)
        } catch {
          // Container doesn't exist, that's fine
        }
      }
      // Also cleanup by pattern to catch orphaned containers (encoding issues, old timestamps)
      const sanitizedProjectId = sanitizeContainerName(projectId)
      await this.stopGenerationContainersByPattern(`generation-${sanitizedProjectId}`)

      this.containers.delete(projectId)

      return { success: true }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  /**
   * Stop all containers on app quit
   * This is called when the Electron app is closing
   */
  async stopAllContainers(): Promise<void> {
    console.log('[Docker] Stopping all containers...')

    // Stop all tracked containers (both project and generation)
    const stopPromises = Array.from(this.containers.keys()).map(async (id) => {
      try {
        await this.stopGeneration(id)
      } catch {
        // Ignore errors during cleanup
      }
      try {
        await this.stopProjectContainer(id)
      } catch {
        // Ignore errors during cleanup
      }
    })
    await Promise.all(stopPromises)

    // Also stop any orphaned containers by pattern (catches containers not in our tracking)
    console.log('[Docker] Cleaning up orphaned containers...')
    await this.stopGenerationContainersByPattern('generation-')
    await this.stopGenerationContainersByPattern('project-')

    console.log('[Docker] All containers stopped')
  }
}
