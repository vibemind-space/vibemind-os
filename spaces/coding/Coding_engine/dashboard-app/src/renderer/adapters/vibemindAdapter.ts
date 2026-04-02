/**
 * VibeMind Adapter
 *
 * Bridges the Coding Engine Dashboard with VibeMind's API surface.
 * When the dashboard runs inside VibeMind (via BrowserView), this adapter
 * maps window.vibemind to the expected window.electronAPI interface.
 */

// Types for VibeMind API (exposed by dashboard-preload.js)
interface VibeMindAPI {
  services?: {
    getStatus: () => Promise<any>;
    restartFastAPI: () => Promise<any>;
    onStatusUpdate: (callback: (status: any) => void) => () => void;
  };
  docker: {
    startEngine: () => Promise<{ success: boolean; message?: string }>;
    stopEngine: () => Promise<{ success: boolean; message?: string }>;
    getEngineStatus: () => Promise<{ running: boolean; containerId?: string }>;
    startProject: (
      projectId: string,
      outputDir: string
    ) => Promise<{ success: boolean; vncPort?: number; appPort?: number }>;
    stopProject: (projectId: string) => Promise<{ success: boolean }>;
    getProjectStatus: (
      projectId: string
    ) => Promise<{ status: string; containerId?: string; ports?: { vnc?: number; app?: number } }>;
    getProjectLogs: (
      projectId: string,
      tail?: number
    ) => Promise<{ logs: string }>;
  };
  ports: {
    getVncPort: (projectId: string) => Promise<number | undefined>;
    getAppPort: (projectId: string) => Promise<number | undefined>;
    getAll: () => Promise<Record<string, { vncPort: number; appPort: number }>>;
  };
  engine: {
    startGeneration: (
      requirementsPath: string,
      outputDir: string
    ) => Promise<{ success: boolean; jobId?: string }>;
    getApiUrl: () => Promise<string>;
  };
  fs: {
    openFolder: (path: string) => Promise<void>;
    showInExplorer: (path: string) => Promise<void>;
  };
  projects: {
    getAll: () => Promise<unknown[]>;
    get: (id: string) => Promise<unknown>;
    create: (data: unknown) => Promise<unknown>;
    delete: (id: string) => Promise<void>;
    getStatus: (id: string) => Promise<unknown>;
  };
  onPythonMessage: (callback: (message: unknown) => void) => void;
  sendToPython: (message: unknown) => void;
  closeDashboard: () => void;
  isEmbedded: boolean;
}

// Extend window with both API types
declare global {
  interface Window {
    vibemind?: VibeMindAPI;
    electronAPI?: VibeMindAPI;
  }
}

/**
 * Check if running in embedded (VibeMind) mode
 */
export function isEmbeddedMode(): boolean {
  return !!(window.vibemind && window.vibemind.isEmbedded);
}

/**
 * Initialize the VibeMind adapter
 * Maps window.vibemind to window.electronAPI for compatibility
 */
export function initVibeMindAdapter(): void {
  // Only initialize if we're in VibeMind and electronAPI isn't already set
  if (window.vibemind && !window.electronAPI) {
    console.log('[VibeMindAdapter] Initializing adapter for embedded mode');

    // Map vibemind API to electronAPI
    window.electronAPI = {
      docker: window.vibemind.docker,
      ports: window.vibemind.ports,
      engine: window.vibemind.engine,
      fs: window.vibemind.fs,
      projects: window.vibemind.projects,
      onPythonMessage: window.vibemind.onPythonMessage,
      sendToPython: window.vibemind.sendToPython,
      closeDashboard: window.vibemind.closeDashboard,
      isEmbedded: window.vibemind.isEmbedded,
    };

    console.log('[VibeMindAdapter] Adapter initialized - electronAPI now available');
  } else if (window.electronAPI) {
    console.log('[VibeMindAdapter] Running in standalone mode - electronAPI already available');
  } else {
    console.warn('[VibeMindAdapter] No API available - running in browser dev mode?');
  }
}

/**
 * Get the active API (either vibemind or electronAPI)
 */
export function getAPI(): VibeMindAPI | undefined {
  return window.electronAPI || window.vibemind;
}

/**
 * Close the dashboard (only works in embedded mode)
 */
export function closeDashboard(): void {
  if (window.vibemind?.closeDashboard) {
    window.vibemind.closeDashboard();
  }
}

/**
 * Check if a specific API feature is available
 */
export function hasFeature(feature: keyof VibeMindAPI): boolean {
  const api = getAPI();
  return api ? feature in api : false;
}

export default {
  initVibeMindAdapter,
  isEmbeddedMode,
  getAPI,
  closeDashboard,
  hasFeature,
};
