import { contextBridge, ipcRenderer } from 'electron'

/**
 * Electron API exposed to renderer via contextBridge
 */
const electronAPI = {
  // ============================================================================
  // Service Management (FastAPI, Docker, Python health)
  // ============================================================================
  services: {
    getStatus: () => ipcRenderer.invoke('services:get-status'),
    restartFastAPI: () => ipcRenderer.invoke('services:restart-fastapi'),
    onStatusUpdate: (callback: (status: any) => void) => {
      ipcRenderer.on('services:status-update', (_, status) => callback(status))
      return () => ipcRenderer.removeAllListeners('services:status-update')
    },
  },

  // ============================================================================
  // Docker Management
  // ============================================================================
  docker: {
    startEngine: () => ipcRenderer.invoke('docker:start-engine'),
    stopEngine: () => ipcRenderer.invoke('docker:stop-engine'),
    getEngineStatus: () => ipcRenderer.invoke('docker:get-engine-status'),

    startProject: (projectId: string, requirementsPath: string, outputDir: string) =>
      ipcRenderer.invoke('docker:start-project', projectId, requirementsPath, outputDir),
    stopProject: (projectId: string) =>
      ipcRenderer.invoke('docker:stop-project', projectId),
    getProjectStatus: (projectId: string) =>
      ipcRenderer.invoke('docker:get-project-status', projectId),
    getProjectLogs: (projectId: string, tail?: number) =>
      ipcRenderer.invoke('docker:get-project-logs', projectId, tail),
  },

  // ============================================================================
  // Port Allocation
  // ============================================================================
  ports: {
    getVncPort: (projectId: string) =>
      ipcRenderer.invoke('ports:get-vnc-port', projectId),
    getAppPort: (projectId: string) =>
      ipcRenderer.invoke('ports:get-app-port', projectId),
    getAll: () => ipcRenderer.invoke('ports:get-all'),
  },

  // ============================================================================
  // Engine API
  // ============================================================================
  engine: {
    startGeneration: (requirementsPath: string, outputDir: string) =>
      ipcRenderer.invoke('engine:start-generation', requirementsPath, outputDir),

    // Start generation WITH VNC preview (for live preview in dashboard)
    startGenerationWithPreview: (
      projectId: string,
      requirementsPath: string,
      outputDir: string,
      forceGenerate: boolean = false
    ) =>
      ipcRenderer.invoke(
        'engine:start-generation-with-preview',
        projectId,
        requirementsPath,
        outputDir,
        forceGenerate
      ),

    // Start generation for orchestrator project WITH VNC preview
    startOrchestratorGenerationWithPreview: (
      projectId: string,
      projectPath: string,
      outputDir: string
    ) =>
      ipcRenderer.invoke(
        'engine:start-orchestrator-generation-with-preview',
        projectId,
        projectPath,
        outputDir
      ),

    // Stop a running generation
    stopGeneration: (projectId: string) =>
      ipcRenderer.invoke('engine:stop-generation', projectId),

    getApiUrl: () => ipcRenderer.invoke('engine:get-api-url'),

    // ============================================================================
    // Epic-based Task Management
    // ============================================================================

    // Start epic-based generation (routes through EpicOrchestrator instead of run_society_hybrid.py)
    startEpicGeneration: (projectId: string, projectPath: string, outputDir: string) =>
      ipcRenderer.invoke('engine:start-epic-generation', projectId, projectPath, outputDir),

    // Load all epics from a project
    getEpics: (projectPath: string) =>
      ipcRenderer.invoke('engine:get-epics', projectPath),

    // Get tasks for a specific epic
    getEpicTasks: (epicId: string, projectPath: string) =>
      ipcRenderer.invoke('engine:get-epic-tasks', epicId, projectPath),

    // Run a specific epic
    runEpic: (epicId: string, projectPath: string) =>
      ipcRenderer.invoke('engine:run-epic', epicId, projectPath),

    // Rerun a specific epic (reset and run again)
    rerunEpic: (epicId: string, projectPath: string) =>
      ipcRenderer.invoke('engine:rerun-epic', epicId, projectPath),

    // Rerun a single task within an epic
    rerunTask: (epicId: string, taskId: string, projectPath: string, fixInstructions?: string) =>
      ipcRenderer.invoke('engine:rerun-task', epicId, taskId, projectPath, fixInstructions),

    // Generate task lists for all epics
    generateTaskLists: (projectPath: string) =>
      ipcRenderer.invoke('engine:generate-task-lists', projectPath),
  },

  // ============================================================================
  // File System
  // ============================================================================
  fs: {
    openFolder: (path: string) => ipcRenderer.invoke('fs:open-folder', path),
    showInExplorer: (path: string) => ipcRenderer.invoke('fs:show-in-explorer', path),
    exists: (path: string): Promise<boolean> => ipcRenderer.invoke('fs:exists', path),
  },

  // ============================================================================
  // Claude Chat (Cursor-like interactive coding assistant)
  // ============================================================================
  claude: {
    chat: (payload: {
      message: string,
      projectPath: string,
      outputDir: string,
      conversationHistory?: Array<{ role: string; content: string }>,
    }) => ipcRenderer.invoke('claude:chat', payload),
  },

  // ============================================================================
  // Debug Mode (Screen Recording + Error Tracking)
  // ============================================================================
  debug: {
    getBrowserErrors: () => ipcRenderer.invoke('debug:get-browser-errors'),
    getDockerLogs: (projectId: string, tail?: number) =>
      ipcRenderer.invoke('debug:get-docker-logs', projectId, tail || 200),
    captureScreenshot: (projectId: string) =>
      ipcRenderer.invoke('debug:capture-screenshot', projectId),
  },

  // ============================================================================
  // Projects (from req-orchestrator API)
  // ============================================================================
  projects: {
    getAll: () => ipcRenderer.invoke('projects:get-all'),
    get: (id: string) => ipcRenderer.invoke('projects:get', id),
    create: (data: any) => ipcRenderer.invoke('projects:create', data),
    delete: (id: string) => ipcRenderer.invoke('projects:delete', id),
    getStatus: (id: string) => ipcRenderer.invoke('projects:get-status', id),
    sendToEngine: (projectIds: string[]) => ipcRenderer.invoke('projects:send-to-engine', projectIds),
    scanLocalDirs: (paths?: string[]) => ipcRenderer.invoke('projects:scan-local-dirs', paths),
    getREDetail: (projectPath: string) => ipcRenderer.invoke('projects:get-re-detail', projectPath),
  },
}

// Expose the API to the renderer
contextBridge.exposeInMainWorld('electronAPI', electronAPI)

// TypeScript type definitions for renderer
export type ElectronAPI = typeof electronAPI
