// web-app/front/src/types/electron.d.ts
interface ServiceStatus {
  fastapi: boolean;
  docker: boolean;
  python: boolean;
}

interface ElectronAPI {
  services: {
    getStatus: () => Promise<ServiceStatus>;
    restartFastAPI: () => Promise<void>;
    onStatusUpdate: (callback: (status: ServiceStatus) => void) => void;
  };
  docker: {
    startEngine: () => Promise<{ success: boolean; services?: string[] }>;
    stopEngine: () => Promise<{ success: boolean }>;
    getEngineStatus: () => Promise<{ running: boolean; services: string[] }>;
    startProject: (projectId: string, requirementsPath: string, outputDir: string) => Promise<{ success: boolean; vncPort?: number; appPort?: number }>;
    stopProject: (projectId: string) => Promise<{ success: boolean }>;
    getProjectStatus: (projectId: string) => Promise<{ running: boolean; containerId?: string }>;
    getProjectLogs: (projectId: string, tail?: number) => Promise<string>;
  };
  ports: {
    getVncPort: (projectId: string) => Promise<number>;
    getAppPort: (projectId: string) => Promise<number>;
    getAll: () => Promise<Record<string, { vnc: number; app: number }>>;
  };
  engine: {
    startGeneration: (requirementsPath: string, outputDir: string) => Promise<any>;
    startGenerationWithPreview: (projectId: string, requirementsPath: string, outputDir: string, projectPath: string) => Promise<any>;
    startOrchestratorGenerationWithPreview: (projectId: string, projectPath: string, outputDir: string) => Promise<any>;
    startEpicGeneration: (projectId: string, projectPath: string, outputDir: string) => Promise<any>;
    stopGeneration: (projectId: string) => Promise<any>;
    getApiUrl: () => Promise<string>;
    getEpics: (projectPath: string) => Promise<{ epics: any[] }>;
    getEpicTasks: (epicId: string, projectPath: string) => Promise<{ tasks: any[] }>;
    runEpic: (epicId: string, projectPath: string) => Promise<any>;
    rerunEpic: (epicId: string, projectPath: string) => Promise<any>;
    rerunTask: (epicId: string, taskId: string, projectPath: string, fixInstructions?: string) => Promise<any>;
    generateTaskLists: (projectPath: string) => Promise<any>;
  };
  fs: {
    openFolder: (path: string) => Promise<void>;
    showInExplorer: (path: string) => Promise<void>;
    exists: (path: string) => Promise<boolean>;
  };
  projects: {
    getAll: () => Promise<any[]>;
    get: (id: string) => Promise<any>;
    create: (data: any) => Promise<any>;
    delete: (id: string) => Promise<any>;
    getStatus: (id: string) => Promise<any>;
    sendToEngine: (projectIds: string[]) => Promise<any>;
    scanLocalDirs: () => Promise<any[]>;
    getREDetail: (projectPath: string) => Promise<any>;
  };
  claude: {
    chat: (payload: { prompt: string; context?: string }) => Promise<{ response: string }>;
  };
  debug: {
    getBrowserErrors: () => Promise<any[]>;
    getDockerLogs: (containerId: string) => Promise<string>;
    captureScreenshot: () => Promise<{ base64: string }>;
  };
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export {};
