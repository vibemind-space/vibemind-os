// web-app/front/src/services/platform.ts

/** Detect if running inside Electron */
export const isElectron = (): boolean => {
  return typeof window !== 'undefined' && !!window.electronAPI;
};

import { API_URL } from './api';
const API_BASE = API_URL;

const jsonPost = (url: string, body?: any) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json());

const jsonGet = (url: string) => fetch(url).then(r => r.json());

/** Platform-agnostic service calls. IPC in Electron, REST in browser. */
export const platform = {
  docker: {
    startEngine: (): Promise<any> => isElectron()
      ? window.electronAPI!.docker.startEngine()
      : jsonPost(`${API_BASE}/engine/docker/start`),
    stopEngine: (): Promise<any> => isElectron()
      ? window.electronAPI!.docker.stopEngine()
      : jsonPost(`${API_BASE}/engine/docker/stop`),
    getStatus: (): Promise<any> => isElectron()
      ? window.electronAPI!.docker.getEngineStatus()
      : jsonGet(`${API_BASE}/engine/docker/status`),
    startProject: (projectId: string, reqPath: string, outputDir: string): Promise<any> => isElectron()
      ? window.electronAPI!.docker.startProject(projectId, reqPath, outputDir)
      : jsonPost(`${API_BASE}/engine/docker/project/start`, { projectId, reqPath, outputDir }),
    stopProject: (projectId: string): Promise<any> => isElectron()
      ? window.electronAPI!.docker.stopProject(projectId)
      : jsonPost(`${API_BASE}/engine/docker/project/stop`, { projectId }),
    getProjectLogs: (projectId: string, tail?: number): Promise<string> => isElectron()
      ? window.electronAPI!.docker.getProjectLogs(projectId, tail)
      : jsonGet(`${API_BASE}/engine/docker/project/${projectId}/logs?tail=${tail || 100}`),
  },

  ports: {
    getVncPort: (projectId: string): Promise<number> => isElectron()
      ? window.electronAPI!.ports.getVncPort(projectId)
      : Promise.resolve(parseInt(import.meta.env.VITE_VNC_PORT || '6090')),
    getAppPort: (projectId: string): Promise<number> => isElectron()
      ? window.electronAPI!.ports.getAppPort(projectId)
      : Promise.resolve(parseInt(import.meta.env.VITE_APP_PORT || '5173')),
  },

  fs: {
    openFolder: (path: string): Promise<void> => isElectron()
      ? window.electronAPI!.fs.openFolder(path)
      : Promise.resolve(),
    showInExplorer: (path: string): Promise<void> => isElectron()
      ? window.electronAPI!.fs.showInExplorer(path)
      : Promise.resolve(),
    exists: (path: string): Promise<boolean> => isElectron()
      ? window.electronAPI!.fs.exists(path)
      : jsonGet(`${API_BASE}/engine/fs/exists?path=${encodeURIComponent(path)}`),
  },

  engine: {
    // Epic/task: always REST (IPC handlers are just proxies anyway)
    getEpics: (projectPath: string) =>
      jsonGet(`${API_BASE}/dashboard/epics?project_path=${encodeURIComponent(projectPath)}`),
    getEpicTasks: (epicId: string, projectPath: string) =>
      jsonGet(`${API_BASE}/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(projectPath)}`),
    runEpic: (epicId: string, projectPath: string) =>
      jsonPost(`${API_BASE}/dashboard/epic/${epicId}/run`, { project_path: projectPath }),
    rerunEpic: (epicId: string, projectPath: string) =>
      jsonPost(`${API_BASE}/dashboard/epic/${epicId}/rerun`, { project_path: projectPath }),
    rerunTask: (epicId: string, taskId: string, projectPath: string, fixInstructions?: string) =>
      jsonPost(`${API_BASE}/dashboard/epic/${epicId}/task/${taskId}/rerun`, { project_path: projectPath, fix_instructions: fixInstructions }),
    generateTaskLists: (projectPath: string) =>
      jsonPost(`${API_BASE}/dashboard/generate-task-lists`, { project_path: projectPath }),
    startGenerationWithPreview: (projectId: string, reqPath: string, outputDir: string, projectPath: string): Promise<any> => isElectron()
      ? window.electronAPI!.engine.startGenerationWithPreview(projectId, reqPath, outputDir, projectPath)
      : jsonPost(`${API_BASE}/engine/projects/${projectId}/start`),
    stopGeneration: (projectId: string): Promise<any> => isElectron()
      ? window.electronAPI!.engine.stopGeneration(projectId)
      : jsonPost(`${API_BASE}/engine/projects/${projectId}/stop`),
  },

  projects: {
    scanLocalDirs: (): Promise<any[]> => isElectron()
      ? window.electronAPI!.projects.scanLocalDirs()
      : jsonGet(`${API_BASE}/engine/projects/scan-local`),
    getREDetail: (projectPath: string) => isElectron()
      ? window.electronAPI!.projects.getREDetail(projectPath)
      : jsonGet(`${API_BASE}/engine/projects/re-detail?path=${encodeURIComponent(projectPath)}`),
  },

  claude: {
    chat: (payload: { prompt: string; context?: string }): Promise<{ response: string }> => isElectron()
      ? window.electronAPI!.claude.chat(payload)
      : jsonPost(`${API_BASE}/dashboard/chat`, payload),
  },

  debug: {
    getBrowserErrors: (): Promise<any[]> => isElectron()
      ? window.electronAPI!.debug.getBrowserErrors()
      : jsonGet(`${API_BASE}/debug/browser-errors`),
    getDockerLogs: (containerId: string): Promise<string> => isElectron()
      ? window.electronAPI!.debug.getDockerLogs(containerId)
      : jsonGet(`${API_BASE}/debug/docker-logs/${containerId}`),
    captureScreenshot: (): Promise<any> => isElectron()
      ? window.electronAPI!.debug.captureScreenshot()
      : jsonPost(`${API_BASE}/debug/screenshot`),
  },
};

/** Push-style events from Electron main process → renderer */
export const platformEvents = {
  onServiceStatusUpdate: (callback: (status: any) => void): void => {
    if (isElectron()) {
      window.electronAPI!.services.onStatusUpdate(callback);
    }
    // In browser: service status comes via WebSocket, not push events
  },
};
