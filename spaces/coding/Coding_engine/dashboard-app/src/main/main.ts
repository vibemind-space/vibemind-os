import { app, BrowserWindow, ipcMain, shell, dialog } from 'electron'
import { join, resolve } from 'path'
import { existsSync, mkdirSync, readFileSync, readdirSync } from 'fs'
import { execSync } from 'child_process'
import * as dotenv from 'dotenv'
import { DockerManager } from './docker-manager'
import { PortAllocator } from './port-allocator'
import { ServiceManager } from './service-manager'

// ── Suppress EPIPE errors from broken pipes (FastAPI stdout/stderr) ──
// These occur when child processes write to pipes that were closed during shutdown.
// They are harmless and should not show error dialogs.
process.on('uncaughtException', (err: NodeJS.ErrnoException) => {
  if (err.code === 'EPIPE' || err.code === 'ERR_STREAM_DESTROYED') {
    // Silently ignore broken pipe errors
    return
  }
  // For all other uncaught exceptions, log and show dialog
  console.error('[Main] Uncaught exception:', err)
  dialog.showErrorBox('Unexpected Error', `${err.message}\n\n${err.stack}`)
})

// Load .env from Coding Engine root (parent of dashboard-app)
// __dirname in built code = .../dashboard-app/out/main/
// We need to go up 3 levels: out/main/ → out/ → dashboard-app/ → Coding_engine/
const engineRoot = join(__dirname, '..', '..', '..')
const envPath = join(engineRoot, '.env')
if (existsSync(envPath)) {
  dotenv.config({ path: envPath })
  console.log('[Main] Loaded .env from:', envPath)
  console.log('[Main] ANTHROPIC_API_KEY:', process.env.ANTHROPIC_API_KEY ? 'set' : 'NOT SET')
} else {
  console.warn('[Main] .env not found at:', envPath)
}

/**
 * Check if Docker is accessible
 */
function isDockerAccessible(): { accessible: boolean; error?: string } {
  try {
    execSync('docker info', { encoding: 'utf-8', stdio: 'pipe' })
    return { accessible: true }
  } catch (error: any) {
    return {
      accessible: false,
      error: 'Docker is not accessible. Please ensure Docker Desktop is running and you have permissions.'
    }
  }
}

/**
 * Check if req-orchestrator container exists and is running
 */
function isOrchestratorRunning(): { running: boolean; exists: boolean; error?: string } {
  try {
    const result = execSync('docker inspect --format="{{.State.Running}}" req-orchestrator', {
      encoding: 'utf-8',
      stdio: 'pipe'
    }).trim()

    // Result is 'true' or 'false' (as string)
    const isRunning = result === 'true' || result === '"true"'
    return { running: isRunning, exists: true }
  } catch (error: any) {
    // Container doesn't exist
    return {
      running: false,
      exists: false,
      error: 'The req-orchestrator container is not running.\n\n' +
        'To start it, run:\n' +
        '  docker-compose -f path/to/orchestrator/docker-compose.yml up -d\n\n' +
        'Or use local requirements files instead of orchestrator projects.'
    }
  }
}

/**
 * Copy requirements from Docker container to local path
 * Translates /app/projects/... paths from req-orchestrator container
 */
async function copyRequirementsFromDocker(dockerPath: string, engineRoot: string): Promise<string> {
  // If it's already a local path, return as-is
  if (!dockerPath.startsWith('/app/projects/')) {
    return dockerPath
  }

  // 1. Check Docker is accessible
  const dockerCheck = isDockerAccessible()
  if (!dockerCheck.accessible) {
    console.error('[Requirements] Docker not accessible:', dockerCheck.error)
    throw new Error(dockerCheck.error!)
  }

  // 2. Check req-orchestrator container exists and is running
  const orchestratorCheck = isOrchestratorRunning()
  if (!orchestratorCheck.exists) {
    console.error('[Requirements] req-orchestrator container not found')
    throw new Error(orchestratorCheck.error!)
  }
  if (!orchestratorCheck.running) {
    console.error('[Requirements] req-orchestrator container exists but is not running')
    throw new Error(
      'The req-orchestrator container exists but is stopped.\n\n' +
      'To start it, run:\n' +
      '  docker start req-orchestrator'
    )
  }

  // Extract project folder name
  const projectFolder = dockerPath.replace('/app/projects/', '')
  const localReqDir = join(engineRoot, '.requirements-cache', projectFolder)

  // Create cache directory
  if (!existsSync(join(engineRoot, '.requirements-cache'))) {
    mkdirSync(join(engineRoot, '.requirements-cache'), { recursive: true })
  }

  // 3. Copy from Docker container
  try {
    console.log(`[Requirements] Copying from req-orchestrator:${dockerPath} to ${localReqDir}`)
    execSync(`docker cp req-orchestrator:${dockerPath} "${localReqDir}"`, { encoding: 'utf-8' })

    // Return the path to requirements.json if it exists, otherwise the folder
    const reqJsonPath = join(localReqDir, 'requirements.json')
    if (existsSync(reqJsonPath)) {
      return reqJsonPath
    }
    return localReqDir
  } catch (error: any) {
    console.error(`[Requirements] Failed to copy from Docker:`, error.message)
    throw new Error(`Could not copy requirements from Docker: ${error.message}`)
  }
}

// Initialize managers
const dockerManager = new DockerManager()
const portAllocator = new PortAllocator()
const serviceManager = new ServiceManager(engineRoot, 8000)

let mainWindow: BrowserWindow | null = null

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 800,
    webPreferences: {
      preload: join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    },
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0f172a',
    show: false
  })

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show()
  })

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  // Load the app
  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../../../web-app/front/dist/index.html'))
  }

  // Open DevTools in development
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools()
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// App lifecycle
app.whenReady().then(async () => {
  // Sync with existing Docker containers to track their ports
  // This keeps existing containers running and prevents port conflicts
  await portAllocator.syncWithDocker()

  createWindow()

  // Auto-start backend services (FastAPI, health checks)
  // ServiceManager spawns FastAPI as a child process and monitors its health
  if (mainWindow) {
    serviceManager.setMainWindow(mainWindow)
  }
  console.log('[App] Auto-starting backend services...')
  const serviceStatus = await serviceManager.startAll()
  console.log('[App] Service status:', JSON.stringify(serviceStatus, null, 2))

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', async () => {
  // Stop all Docker containers and backend services before quitting
  console.log('[App] Window closed, cleaning up services and Docker containers...')
  await serviceManager.stopAll()
  await dockerManager.stopAllContainers()

  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// Track if we've already started cleanup to prevent double-cleanup
let isCleaningUp = false

app.on('before-quit', async (event) => {
  // Prevent duplicate cleanup
  if (isCleaningUp) return

  isCleaningUp = true
  event.preventDefault()

  console.log('[App] Before quit - stopping services and Docker containers...')
  try {
    await serviceManager.stopAll()
    await dockerManager.stopAllContainers()
  } catch (error) {
    console.error('[App] Error during cleanup:', error)
  }

  // Now quit for real
  app.exit(0)
})

// ============================================================================
// IPC Handlers - Docker Management
// ============================================================================

ipcMain.handle('docker:start-engine', async () => {
  return await dockerManager.startEngine()
})

ipcMain.handle('docker:stop-engine', async () => {
  return await dockerManager.stopEngine()
})

ipcMain.handle('docker:get-engine-status', async () => {
  return await dockerManager.getEngineStatus()
})

ipcMain.handle('docker:start-project', async (_, projectId: string, requirementsPath: string, outputDir: string) => {
  const vncPort = await portAllocator.allocate(projectId)
  const appPort = await portAllocator.allocateAppPort(projectId)
  const success = await dockerManager.startProjectContainer(projectId, requirementsPath, outputDir, vncPort, appPort)
  return { success, vncPort, appPort }
})

ipcMain.handle('docker:stop-project', async (_, projectId: string) => {
  portAllocator.release(projectId)
  return await dockerManager.stopProjectContainer(projectId)
})

ipcMain.handle('docker:get-project-status', async (_, projectId: string) => {
  return await dockerManager.getProjectStatus(projectId)
})

ipcMain.handle('docker:get-project-logs', async (_, projectId: string, tail: number = 100) => {
  return await dockerManager.getProjectLogs(projectId, tail)
})

// ============================================================================
// IPC Handlers - Port Allocation
// ============================================================================

ipcMain.handle('ports:get-vnc-port', (_, projectId: string) => {
  return portAllocator.getVncPort(projectId)
})

ipcMain.handle('ports:get-app-port', (_, projectId: string) => {
  return portAllocator.getAppPort(projectId)
})

ipcMain.handle('ports:get-all', () => {
  return portAllocator.getAllAllocations()
})

// ============================================================================
// IPC Handlers - Service Management (FastAPI, Docker, Python health)
// ============================================================================

ipcMain.handle('services:get-status', async () => {
  return serviceManager.getAllStatus()
})

ipcMain.handle('services:restart-fastapi', async () => {
  console.log('[IPC] Restarting FastAPI server...')
  await serviceManager.stopAll()
  const status = await serviceManager.startAll()
  return status
})

// ============================================================================
// IPC Handlers - Engine API
// ============================================================================

ipcMain.handle('engine:start-generation', async (_, requirementsPath: string, outputDir: string) => {
  return await dockerManager.startGeneration(requirementsPath, outputDir)
})

// New: Start generation WITH VNC preview (for dashboard live preview)
ipcMain.handle('engine:start-generation-with-preview', async (
  _,
  projectId: string,
  requirementsPath: string,
  outputDir: string,
  forceGenerate: boolean = false
) => {
  try {
    // FIX: Define engineRoot - same as docker-manager.ts
    // __dirname in built code = .../dashboard-app/out/main/
    // We need 3 levels: out/main/ → out/ → dashboard-app/ → Coding_engine/
    const engineRoot = join(__dirname, '..', '..', '..')

    // Convert Docker paths to local paths if needed
    let localRequirementsPath = requirementsPath
    if (requirementsPath.startsWith('/app/projects/')) {
      localRequirementsPath = await copyRequirementsFromDocker(requirementsPath, engineRoot)
      console.log(`[Generation] Converted Docker path to local: ${localRequirementsPath}`)
    }

    const vncPort = await portAllocator.allocate(projectId)
    const appPort = await portAllocator.allocateAppPort(projectId)

    // FIX: Convert relative outputDir to absolute path (relative to engineRoot, not CWD)
    const absoluteOutputDir = outputDir.startsWith('.')
      ? join(engineRoot, outputDir.replace(/^\.\//, ''))
      : outputDir

    return await dockerManager.startGenerationWithPreview(
      projectId,
      localRequirementsPath,
      absoluteOutputDir,
      vncPort,
      appPort,
      forceGenerate
    )
  } catch (error: any) {
    console.error('[Generation] Error:', error)
    return { success: false, error: error.message }
  }
})

ipcMain.handle('engine:stop-generation', async (_, projectId: string) => {
  portAllocator.release(projectId)
  return await dockerManager.stopGeneration(projectId)
})

ipcMain.handle('engine:get-api-url', () => {
  return 'http://localhost:8000'
})

// ============================================================================
// IPC Handlers - File System
// ============================================================================

ipcMain.handle('fs:open-folder', async (_, path: string) => {
  return shell.openPath(path)
})

ipcMain.handle('fs:show-in-explorer', async (_, path: string) => {
  shell.showItemInFolder(path)
})

ipcMain.handle('fs:exists', async (_, path: string) => {
  return existsSync(path)
})

// ============================================================================
// IPC Handlers - Projects (from req-orchestrator API at port 8087)
// ============================================================================

const ORCHESTRATOR_API = 'http://localhost:8087'
const TECHSTACK_API = `${ORCHESTRATOR_API}/api/v1/techstack`

ipcMain.handle('projects:get-all', async () => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()
    // API returns { projects: [...], total: N }
    console.log(`[Projects] Loaded ${data.total || data.projects?.length || 0} projects from orchestrator`)
    return data.projects || []
  } catch (error: any) {
    console.error('[Projects] Failed to fetch all projects:', error.message)
    // Return empty array if orchestrator is not running
    return []
  }
})

ipcMain.handle('projects:get', async (_, id: string) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects/${id}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error: any) {
    console.error(`[Projects] Failed to fetch project ${id}:`, error.message)
    return null
  }
})

ipcMain.handle('projects:create', async (_, data: any) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error: any) {
    console.error('[Projects] Failed to create project:', error.message)
    throw error
  }
})

ipcMain.handle('projects:delete', async (_, id: string) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects/${id}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return { success: true }
  } catch (error: any) {
    console.error(`[Projects] Failed to delete project ${id}:`, error.message)
    throw error
  }
})

ipcMain.handle('projects:get-status', async (_, id: string) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects/${id}/status`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error: any) {
    console.error(`[Projects] Failed to get project status ${id}:`, error.message)
    return null
  }
})

// Send selected projects to Coding Engine for generation
ipcMain.handle('projects:send-to-engine', async (_, projectIds: string[]) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/send-to-engine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_ids: projectIds })
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || `HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error: any) {
    console.error('[Projects] Failed to send to engine:', error.message)
    return { success: false, error: error.message }
  }
})

// ============================================================================
// IPC Handlers - Local RE (Requirements Engineer) Projects
// ============================================================================

/**
 * Scan local directories for RE documentation projects.
 * Detects projects by checking for MASTER_DOCUMENT.md, tech_stack/, etc.
 */
ipcMain.handle('projects:scan-local-dirs', async (_, scanPaths?: string[]) => {
  const defaultScanDir = join(engineRoot, 'Data', 'all_services')
  const dirsToScan = scanPaths && scanPaths.length > 0 ? scanPaths : [defaultScanDir]
  const results: any[] = []

  for (const scanDir of dirsToScan) {
    if (!existsSync(scanDir)) {
      console.log(`[RE] Scan directory not found: ${scanDir}`)
      continue
    }

    let entries: any[]
    try {
      entries = readdirSync(scanDir, { withFileTypes: true })
    } catch (err: any) {
      console.error(`[RE] Failed to read directory ${scanDir}:`, err.message)
      continue
    }

    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const projectDir = join(scanDir, entry.name)

      // Check RE project indicators (same as DocumentationLoader.is_documentation_project)
      const indicators = [
        join(projectDir, 'MASTER_DOCUMENT.md'),
        join(projectDir, 'tech_stack', 'tech_stack.json'),
        join(projectDir, 'user_stories', 'user_stories.md'),
        join(projectDir, 'content_analysis.json'),
      ]
      const isREProject = indicators.some(p => existsSync(p))
      if (!isREProject) continue

      try {
        const summary = readREProjectSummary(projectDir, entry.name)
        results.push(summary)
        console.log(`[RE] Found project: ${summary.project_name} (${summary.requirements_count} reqs, ${summary.tasks_count} tasks)`)
      } catch (err: any) {
        console.warn(`[RE] Failed to read project ${entry.name}:`, err.message)
      }
    }
  }

  console.log(`[RE] Scan complete: ${results.length} RE projects found`)
  return results
})

/**
 * Get full detail for an RE project by path.
 */
ipcMain.handle('projects:get-re-detail', async (_, projectPath: string) => {
  try {
    return readREProjectDetail(projectPath)
  } catch (err: any) {
    console.error(`[RE] Failed to read project detail:`, err.message)
    return null
  }
})

/**
 * Read RE project summary metadata from directory.
 */
function readREProjectSummary(projectDir: string, folderName: string): any {
  let projectName = folderName
  const techStackTags: string[] = []
  let architecturePattern = ''
  let requirementsCount = 0
  let userStoriesCount = 0
  let tasksCount = 0
  let diagramCount = 0
  let qualityIssues = { critical: 0, high: 0, medium: 0 }
  let hasApiSpec = false
  let hasMasterDocument = false
  const techStackFull: Record<string, string> = {}

  // Read tech_stack.json
  const techStackPath = join(projectDir, 'tech_stack', 'tech_stack.json')
  if (existsSync(techStackPath)) {
    try {
      const data = JSON.parse(readFileSync(techStackPath, 'utf-8'))
      const rawName = data.project_name || ''
      projectName = (rawName && rawName !== 'unnamed_project') ? rawName : folderName
      architecturePattern = data.architecture_pattern || ''
      if (data.frontend_framework) techStackTags.push(data.frontend_framework)
      if (data.backend_framework) techStackTags.push(data.backend_framework)
      if (data.primary_database) techStackTags.push(data.primary_database)
      if (data.cache_layer && data.cache_layer !== 'none') techStackTags.push(data.cache_layer)
      // Store full tech stack for detail view
      for (const [key, val] of Object.entries(data)) {
        if (typeof val === 'string' && key !== 'project_name') {
          techStackFull[key] = val
        }
      }
    } catch { /* skip */ }
  }

  // Read user_stories.json for count (check both user_stories/ and root)
  const userStoriesPaths = [
    join(projectDir, 'user_stories', 'user_stories.json'),
    join(projectDir, 'user_stories.json'),
  ]
  const userStoriesJsonPath = userStoriesPaths.find(p => existsSync(p)) || ''
  if (userStoriesJsonPath) {
    try {
      const data = JSON.parse(readFileSync(userStoriesJsonPath, 'utf-8'))
      if (Array.isArray(data)) {
        userStoriesCount = data.length
        // Count unique linked requirements
        const reqIds = new Set<string>()
        for (const story of data) {
          if (story.linked_requirement) reqIds.add(story.linked_requirement)
        }
        requirementsCount = reqIds.size || userStoriesCount
      }
    } catch { /* skip */ }
  }

  // Read task_list.json for count
  const taskListPath = join(projectDir, 'tasks', 'task_list.json')
  if (existsSync(taskListPath)) {
    try {
      const data = JSON.parse(readFileSync(taskListPath, 'utf-8'))
      tasksCount = data.total_tasks || 0
      if (!tasksCount && data.features) {
        for (const tasks of Object.values(data.features) as any[]) {
          if (Array.isArray(tasks)) tasksCount += tasks.length
        }
      }
    } catch { /* skip */ }
  }

  // Count diagrams
  const diagramsDir = join(projectDir, 'diagrams')
  if (existsSync(diagramsDir)) {
    try {
      const files = readdirSync(diagramsDir)
      diagramCount = files.filter((f: string) => f.endsWith('.mmd') || f.endsWith('.md')).length
    } catch { /* skip */ }
  }

  // Read quality report
  const qualityPath = join(projectDir, 'quality', 'self_critique_report.json')
  if (existsSync(qualityPath)) {
    try {
      const data = JSON.parse(readFileSync(qualityPath, 'utf-8'))
      const bySeverity = data.summary?.by_severity || {}
      qualityIssues = {
        critical: bySeverity.critical || 0,
        high: bySeverity.high || 0,
        medium: bySeverity.medium || 0,
      }
    } catch { /* skip */ }
  }

  // Check for API spec and master document
  hasApiSpec = existsSync(join(projectDir, 'api', 'openapi_spec.yaml')) ||
               existsSync(join(projectDir, 'api', 'api_documentation.md'))
  hasMasterDocument = existsSync(join(projectDir, 'MASTER_DOCUMENT.md'))

  return {
    project_id: folderName,
    project_name: projectName,
    project_path: projectDir,
    source: 'local_re' as const,
    tech_stack_tags: techStackTags,
    architecture_pattern: architecturePattern,
    requirements_count: requirementsCount,
    user_stories_count: userStoriesCount,
    tasks_count: tasksCount,
    diagram_count: diagramCount,
    quality_issues: qualityIssues,
    has_api_spec: hasApiSpec,
    has_master_document: hasMasterDocument,
  }
}

/**
 * Read full RE project detail including tasks, quality issues, etc.
 */
function readREProjectDetail(projectDir: string): any {
  const folderName = require('path').basename(projectDir)
  const summary = readREProjectSummary(projectDir, folderName)

  // Read tasks grouped by feature
  const tasksByFeature: Record<string, any[]> = {}
  const taskListPath = join(projectDir, 'tasks', 'task_list.json')
  if (existsSync(taskListPath)) {
    try {
      const data = JSON.parse(readFileSync(taskListPath, 'utf-8'))
      for (const [featureId, tasks] of Object.entries(data.features || {})) {
        if (Array.isArray(tasks)) {
          tasksByFeature[featureId] = tasks.map((t: any) => ({
            id: t.id || '',
            title: t.title || '',
            task_type: t.task_type || '',
            complexity: t.complexity || 'medium',
            estimated_hours: t.estimated_hours || 0,
          }))
        }
      }
    } catch { /* skip */ }
  }

  // Read quality issues list
  let qualityIssuesList: any[] = []
  const qualityPath = join(projectDir, 'quality', 'self_critique_report.json')
  if (existsSync(qualityPath)) {
    try {
      const data = JSON.parse(readFileSync(qualityPath, 'utf-8'))
      qualityIssuesList = (data.issues || []).map((i: any) => ({
        id: i.id || '',
        category: i.category || '',
        severity: i.severity || 'medium',
        title: i.title || '',
      }))
    } catch { /* skip */ }
  }

  // Read master document excerpt
  let masterDocExcerpt = ''
  const masterDocPath = join(projectDir, 'MASTER_DOCUMENT.md')
  if (existsSync(masterDocPath)) {
    try {
      const content = readFileSync(masterDocPath, 'utf-8')
      masterDocExcerpt = content.slice(0, 2000)
    } catch { /* skip */ }
  }

  // Read feature breakdown
  let featureBreakdown: any[] = []
  const fbPath = join(projectDir, 'work_breakdown', 'feature_breakdown.json')
  if (existsSync(fbPath)) {
    try {
      const data = JSON.parse(readFileSync(fbPath, 'utf-8'))
      for (const [featId, feat] of Object.entries(data.features || {})) {
        const f = feat as any
        featureBreakdown.push({
          feature_id: f.feature_id || featId,
          feature_name: f.feature_name || '',
          requirements: f.requirements || [],
        })
      }
    } catch { /* skip */ }
  }

  // Read full tech stack
  let techStackFull: Record<string, string> = {}
  const techStackPath = join(projectDir, 'tech_stack', 'tech_stack.json')
  if (existsSync(techStackPath)) {
    try {
      const data = JSON.parse(readFileSync(techStackPath, 'utf-8'))
      for (const [key, val] of Object.entries(data)) {
        if (typeof val === 'string') techStackFull[key] = val
      }
    } catch { /* skip */ }
  }

  return {
    ...summary,
    tech_stack_full: techStackFull,
    tasks_by_feature: tasksByFeature,
    quality_issues_list: qualityIssuesList,
    master_document_excerpt: masterDocExcerpt,
    feature_breakdown: featureBreakdown,
  }
}

// ============================================================================
// IPC Handlers - Orchestrator Projects with VNC Preview
// ============================================================================

/**
 * Start generation for orchestrator project WITH VNC preview
 * This combines: 1) VNC container start, 2) Generation job creation
 */
ipcMain.handle('engine:start-orchestrator-generation-with-preview', async (
  _,
  projectId: string,
  projectPath: string,
  outputDir: string
) => {
  try {
    // Resolve output directory to absolute path for Docker compatibility
    // __dirname in built code = .../dashboard-app/out/main/
    // We need 3 levels: out/main/ → out/ → dashboard-app/ → Coding_engine/
    const engineRoot = join(__dirname, '..', '..', '..')
    const absoluteOutputDir = outputDir.startsWith('.')
      ? join(engineRoot, outputDir.replace(/^\.\//, ''))
      : outputDir

    console.log(`[Orchestrator] Starting generation with VNC for project ${projectId}`)
    console.log(`[Orchestrator] Project path: ${projectPath}`)
    console.log(`[Orchestrator] Output dir (absolute): ${absoluteOutputDir}`)

    // 1. Copy requirements from Docker container if needed
    let localRequirementsPath = projectPath
    if (projectPath.startsWith('/app/projects/')) {
      localRequirementsPath = await copyRequirementsFromDocker(projectPath, engineRoot)
      console.log(`[Orchestrator] Local requirements path: ${localRequirementsPath}`)
    }

    // 2. Allocate ports for VNC and app preview
    const vncPort = await portAllocator.allocate(projectId)
    const appPort = await portAllocator.allocateAppPort(projectId)
    console.log(`[Orchestrator] Allocated ports - VNC: ${vncPort}, App: ${appPort}`)

    // 3. Start VNC-enabled sandbox container with forceGenerate=true
    // Orchestrator projects should ALWAYS trigger generation, even if they have existing files
    const containerResult = await dockerManager.startGenerationWithPreview(
      projectId,
      localRequirementsPath, // Use LOCAL path for Python generation
      absoluteOutputDir,
      vncPort,
      appPort,
      true  // forceGenerate: always generate for orchestrator projects
    )

    if (!containerResult.success) {
      console.error(`[Orchestrator] Failed to start VNC container:`, containerResult.error)
      return { success: false, error: containerResult.error }
    }

    console.log(`[Orchestrator] VNC container started on port ${vncPort}`)

    // 3. Optionally notify Coding Engine API about the job
    // The generation is already started by startGenerationWithPreview()
    // This is for tracking purposes
    try {
      const jobResponse = await fetch('http://localhost:8000/api/v1/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          project_path: projectPath,
          output_dir: outputDir,
          vnc_port: vncPort,
          app_port: appPort
        })
      })

      if (jobResponse.ok) {
        const jobData = await jobResponse.json()
        console.log(`[Orchestrator] Job registered with Coding Engine:`, jobData.id)
      }
    } catch (apiError) {
      // Non-fatal: generation runs even if API tracking fails
      console.warn(`[Orchestrator] Could not register job with API:`, apiError)
    }

    return {
      success: true,
      vncPort,
      appPort,
      generationPid: containerResult.generationPid
    }
  } catch (error: any) {
    console.error(`[Orchestrator] Generation failed:`, error)
    portAllocator.release(projectId)
    return { success: false, error: error.message }
  }
})

// ============================================================================
// IPC Handlers - Epic-based Task Management (proxy to FastAPI at port 8000)
// ============================================================================

const ENGINE_API = process.env.ENGINE_API_URL || 'http://localhost:8000'

ipcMain.handle('engine:get-epics', async (_, projectPath: string) => {
  console.log(`[Epic:IPC] get-epics called with path: ${projectPath}`)
  try {
    const url = `${ENGINE_API}/api/v1/dashboard/epics?project_path=${encodeURIComponent(projectPath)}`
    console.log(`[Epic:IPC] Fetching: ${url}`)
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    console.log(`[Epic:IPC] Got ${data.epics?.length ?? 0} epics from API`)
    return data
  } catch (error: any) {
    console.error('[Epic:IPC] Failed to get epics:', error.message)
    return { project_path: projectPath, total_epics: 0, epics: [] }
  }
})

ipcMain.handle('engine:get-epic-tasks', async (_, epicId: string, projectPath: string) => {
  try {
    const response = await fetch(
      `${ENGINE_API}/api/v1/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(projectPath)}`
    )
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } catch (error: any) {
    console.error(`[Epic] Failed to get tasks for ${epicId}:`, error.message)
    return { epic_id: epicId, tasks: [], total_tasks: 0 }
  }
})

ipcMain.handle('engine:run-epic', async (_, epicId: string, projectPath: string) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/epic/${epicId}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } catch (error: any) {
    console.error(`[Epic] Failed to run ${epicId}:`, error.message)
    return { success: false, error: error.message }
  }
})

ipcMain.handle('engine:rerun-epic', async (_, epicId: string, projectPath: string) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/epic/${epicId}/rerun`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } catch (error: any) {
    console.error(`[Epic] Failed to rerun ${epicId}:`, error.message)
    return { success: false, error: error.message }
  }
})

ipcMain.handle('engine:rerun-task', async (
  _,
  epicId: string,
  taskId: string,
  projectPath: string,
  fixInstructions?: string
) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/epic/${epicId}/task/${taskId}/rerun`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath,
        fix_instructions: fixInstructions || null,
      })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } catch (error: any) {
    console.error(`[Epic] Failed to rerun task ${taskId}:`, error.message)
    return { success: false, error: error.message }
  }
})

ipcMain.handle('engine:generate-task-lists', async (_, projectPath: string) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/generate-task-lists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projectPath })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } catch (error: any) {
    console.error('[Epic] Failed to generate task lists:', error.message)
    return { success: false, error: error.message }
  }
})

ipcMain.handle('engine:start-epic-generation', async (
  _,
  projectId: string,
  projectPath: string,
  outputDir: string
) => {
  try {
    const engineRoot = join(__dirname, '..', '..', '..')
    const absoluteOutputDir = outputDir.startsWith('.')
      ? join(engineRoot, outputDir.replace(/^\.\//, ''))
      : outputDir

    console.log(`[EpicGen] Starting epic-based generation for ${projectId}`)
    console.log(`[EpicGen] Project path: ${projectPath}`)
    console.log(`[EpicGen] Output dir: ${absoluteOutputDir}`)

    // 1. Allocate ports for VNC and app preview
    const vncPort = await portAllocator.allocate(projectId)
    const appPort = await portAllocator.allocateAppPort(projectId)
    console.log(`[EpicGen] Allocated ports - VNC: ${vncPort}, App: ${appPort}`)

    // 2. Start sandbox container (VNC preview only, no run_society_hybrid.py)
    const containerResult = await dockerManager.startProjectContainer(
      projectId,
      absoluteOutputDir,  // Mount output dir for live preview
      absoluteOutputDir,
      vncPort,
      appPort
    )

    if (!containerResult.success) {
      console.error(`[EpicGen] Failed to start VNC container:`, containerResult.error)
      portAllocator.release(projectId)
      return { success: false, error: containerResult.error }
    }

    // 3. Call FastAPI to start EpicOrchestrator in background
    try {
      const response = await fetch(`${ENGINE_API}/api/v1/dashboard/start-epic-generation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath,
          output_dir: absoluteOutputDir,
          vnc_port: vncPort,
          app_port: appPort,
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        console.error(`[EpicGen] FastAPI returned ${response.status}:`, errorData)
        // Non-fatal: container is running, generation can be started manually
      } else {
        const data = await response.json()
        console.log(`[EpicGen] EpicOrchestrator started:`, data)
      }
    } catch (apiError: any) {
      // Non-fatal: VNC container is running, user can trigger epic run manually
      console.warn(`[EpicGen] Could not start EpicOrchestrator via API:`, apiError.message)
    }

    console.log(`[EpicGen] Epic generation started on VNC port ${vncPort}`)
    return { success: true, vncPort, appPort }
  } catch (error: any) {
    console.error(`[EpicGen] Generation failed:`, error)
    portAllocator.release(projectId)
    return { success: false, error: error.message }
  }
})

// ============================================================================
// Claude Chat (Cursor-like interactive coding assistant)
// ============================================================================

ipcMain.handle('claude:chat', async (_, payload: {
  message: string,
  projectPath: string,
  outputDir: string,
  conversationHistory?: Array<{ role: string; content: string }>,
}) => {
  try {
    const apiUrl = process.env.ENGINE_API_URL || 'http://localhost:8000'
    const response = await fetch(`${apiUrl}/api/v1/dashboard/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: payload.message,
        project_path: payload.projectPath,
        output_dir: payload.outputDir,
        history: payload.conversationHistory || [],
      }),
    })

    if (!response.ok) {
      return {
        success: false,
        error: `API error: ${response.status} ${response.statusText}`,
        response: '',
        files_modified: [],
        files_created: [],
      }
    }

    return await response.json()
  } catch (error: any) {
    console.error('[Claude Chat] Error:', error)
    return {
      success: false,
      error: error.message,
      response: '',
      files_modified: [],
      files_created: [],
    }
  }
})

// =============================================================================
// Debug Mode - Browser Errors, Docker Logs, Screenshots
// =============================================================================

ipcMain.handle('debug:get-browser-errors', async () => {
  try {
    const response = await fetch('http://localhost:8765/api/browser-errors')
    if (response.ok) {
      const data = await response.json()
      return data.errors || []
    }
    return []
  } catch {
    // Error receiver server may not be running
    return []
  }
})

ipcMain.handle('debug:get-docker-logs', async (_, projectId: string, tail: number = 200) => {
  try {
    return await dockerManager.getProjectLogs(projectId, tail)
  } catch (error: any) {
    console.error('[Debug] Docker logs error:', error)
    return ''
  }
})

ipcMain.handle('debug:capture-screenshot', async (_, projectId: string) => {
  try {
    const apiUrl = process.env.ENGINE_API_URL || 'http://localhost:8000'
    const response = await fetch(`${apiUrl}/api/v1/vnc/${projectId}/screenshot`, {
      method: 'POST',
    })
    if (response.ok) {
      const data = await response.json()
      return { success: true, screenshot: data.screenshot }
    }
    return { success: false, error: `Screenshot API returned ${response.status}` }
  } catch (error: any) {
    console.error('[Debug] Screenshot error:', error)
    return { success: false, error: error.message }
  }
})
