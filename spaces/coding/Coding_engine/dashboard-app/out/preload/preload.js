"use strict";
const electron = require("electron");
const electronAPI = {
  // ============================================================================
  // Service Management (FastAPI, Docker, Python health)
  // ============================================================================
  services: {
    getStatus: () => electron.ipcRenderer.invoke("services:get-status"),
    restartFastAPI: () => electron.ipcRenderer.invoke("services:restart-fastapi"),
    onStatusUpdate: (callback) => {
      electron.ipcRenderer.on("services:status-update", (_, status) => callback(status));
      return () => electron.ipcRenderer.removeAllListeners("services:status-update");
    }
  },
  // ============================================================================
  // Docker Management
  // ============================================================================
  docker: {
    startEngine: () => electron.ipcRenderer.invoke("docker:start-engine"),
    stopEngine: () => electron.ipcRenderer.invoke("docker:stop-engine"),
    getEngineStatus: () => electron.ipcRenderer.invoke("docker:get-engine-status"),
    startProject: (projectId, requirementsPath, outputDir) => electron.ipcRenderer.invoke("docker:start-project", projectId, requirementsPath, outputDir),
    stopProject: (projectId) => electron.ipcRenderer.invoke("docker:stop-project", projectId),
    getProjectStatus: (projectId) => electron.ipcRenderer.invoke("docker:get-project-status", projectId),
    getProjectLogs: (projectId, tail) => electron.ipcRenderer.invoke("docker:get-project-logs", projectId, tail)
  },
  // ============================================================================
  // Port Allocation
  // ============================================================================
  ports: {
    getVncPort: (projectId) => electron.ipcRenderer.invoke("ports:get-vnc-port", projectId),
    getAppPort: (projectId) => electron.ipcRenderer.invoke("ports:get-app-port", projectId),
    getAll: () => electron.ipcRenderer.invoke("ports:get-all")
  },
  // ============================================================================
  // Engine API
  // ============================================================================
  engine: {
    startGeneration: (requirementsPath, outputDir) => electron.ipcRenderer.invoke("engine:start-generation", requirementsPath, outputDir),
    // Start generation WITH VNC preview (for live preview in dashboard)
    startGenerationWithPreview: (projectId, requirementsPath, outputDir, forceGenerate = false) => electron.ipcRenderer.invoke(
      "engine:start-generation-with-preview",
      projectId,
      requirementsPath,
      outputDir,
      forceGenerate
    ),
    // Start generation for orchestrator project WITH VNC preview
    startOrchestratorGenerationWithPreview: (projectId, projectPath, outputDir) => electron.ipcRenderer.invoke(
      "engine:start-orchestrator-generation-with-preview",
      projectId,
      projectPath,
      outputDir
    ),
    // Stop a running generation
    stopGeneration: (projectId) => electron.ipcRenderer.invoke("engine:stop-generation", projectId),
    getApiUrl: () => electron.ipcRenderer.invoke("engine:get-api-url"),
    // ============================================================================
    // Epic-based Task Management
    // ============================================================================
    // Start epic-based generation (routes through EpicOrchestrator instead of run_society_hybrid.py)
    startEpicGeneration: (projectId, projectPath, outputDir) => electron.ipcRenderer.invoke("engine:start-epic-generation", projectId, projectPath, outputDir),
    // Load all epics from a project
    getEpics: (projectPath) => electron.ipcRenderer.invoke("engine:get-epics", projectPath),
    // Get tasks for a specific epic
    getEpicTasks: (epicId, projectPath) => electron.ipcRenderer.invoke("engine:get-epic-tasks", epicId, projectPath),
    // Run a specific epic
    runEpic: (epicId, projectPath) => electron.ipcRenderer.invoke("engine:run-epic", epicId, projectPath),
    // Rerun a specific epic (reset and run again)
    rerunEpic: (epicId, projectPath) => electron.ipcRenderer.invoke("engine:rerun-epic", epicId, projectPath),
    // Rerun a single task within an epic
    rerunTask: (epicId, taskId, projectPath, fixInstructions) => electron.ipcRenderer.invoke("engine:rerun-task", epicId, taskId, projectPath, fixInstructions),
    // Generate task lists for all epics
    generateTaskLists: (projectPath) => electron.ipcRenderer.invoke("engine:generate-task-lists", projectPath)
  },
  // ============================================================================
  // File System
  // ============================================================================
  fs: {
    openFolder: (path) => electron.ipcRenderer.invoke("fs:open-folder", path),
    showInExplorer: (path) => electron.ipcRenderer.invoke("fs:show-in-explorer", path),
    exists: (path) => electron.ipcRenderer.invoke("fs:exists", path)
  },
  // ============================================================================
  // Claude Chat (Cursor-like interactive coding assistant)
  // ============================================================================
  claude: {
    chat: (payload) => electron.ipcRenderer.invoke("claude:chat", payload)
  },
  // ============================================================================
  // Debug Mode (Screen Recording + Error Tracking)
  // ============================================================================
  debug: {
    getBrowserErrors: () => electron.ipcRenderer.invoke("debug:get-browser-errors"),
    getDockerLogs: (projectId, tail) => electron.ipcRenderer.invoke("debug:get-docker-logs", projectId, tail || 200),
    captureScreenshot: (projectId) => electron.ipcRenderer.invoke("debug:capture-screenshot", projectId)
  },
  // ============================================================================
  // Projects (from req-orchestrator API)
  // ============================================================================
  projects: {
    getAll: () => electron.ipcRenderer.invoke("projects:get-all"),
    get: (id) => electron.ipcRenderer.invoke("projects:get", id),
    create: (data) => electron.ipcRenderer.invoke("projects:create", data),
    delete: (id) => electron.ipcRenderer.invoke("projects:delete", id),
    getStatus: (id) => electron.ipcRenderer.invoke("projects:get-status", id),
    sendToEngine: (projectIds) => electron.ipcRenderer.invoke("projects:send-to-engine", projectIds),
    scanLocalDirs: (paths) => electron.ipcRenderer.invoke("projects:scan-local-dirs", paths),
    getREDetail: (projectPath) => electron.ipcRenderer.invoke("projects:get-re-detail", projectPath)
  }
};
electron.contextBridge.exposeInMainWorld("electronAPI", electronAPI);
