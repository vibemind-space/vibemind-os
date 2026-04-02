# Electron Renderer Replacement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Electron dashboard-app's renderer with the unified web-app frontend, creating one codebase that works both as a standalone web app and as an Electron desktop app.

**Architecture:** A platform adapter (`services/platform.ts`) detects Electron vs browser and routes calls via IPC or REST. The Electron main process (IPC handlers, Docker, Ports) stays untouched. The web-app's Vite build output is loaded directly by `BrowserWindow.loadFile()`.

**Tech Stack:** React 18, Vite, Zustand, shadcn/ui, Electron 28, electron-vite, TypeScript

**Spec:** `docs/superpowers/specs/2026-03-16-electron-renderer-replacement-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `web-app/front/src/types/electron.d.ts` | TypeScript declarations for `window.electronAPI` |
| `web-app/front/src/services/platform.ts` | IPC/REST adapter (invoke + push events) |
| `web-app/front/src/services/vibeApi.ts` | Vibe WebSocket streaming API client |
| `web-app/front/src/services/clarificationApi.ts` | Clarification queue API client |
| `web-app/front/src/services/debugApi.ts` | Debug/logs API client |
| `web-app/front/src/stores/vibeStore.ts` | Vibe session state |
| `web-app/front/src/stores/projectStore.ts` | Project state (Engine + Vibe + RE) |
| `web-app/front/src/components/engine/TaskBoard.tsx` | Epic task list with rerun |
| `web-app/front/src/components/engine/ReviewChat.tsx` | Review Gate pause/resume chat |
| `web-app/front/src/components/engine/ServiceStatusBar.tsx` | FastAPI/Docker health |
| `web-app/front/src/components/engine/ClarificationPanel.tsx` | Clarification queue UI |
| `web-app/front/.env.electron` | Electron-specific env vars |

### Modified Files
| File | Change |
|------|--------|
| `web-app/front/src/stores/engineStore.ts` | Expand WebSocket handler to 15+ events, add epic/task state |
| `web-app/front/src/services/engineApi.ts` | Add epic/task REST endpoints |
| `web-app/front/src/components/engine/VncPreview.tsx` | Use platform adapter for port resolution |
| `web-app/front/src/components/engine/GenerationMonitor.tsx` | Wire TaskBoard, wire real sub-tabs |
| `web-app/front/src/components/Navbar.tsx` | Add ServiceStatusBar |
| `web-app/front/src/App.tsx` | No changes needed (routes already correct) |
| `dashboard-app/electron.vite.config.ts` | Remove renderer section |
| `dashboard-app/src/main/main.ts` | Update loadFile path |
| `dashboard-app/package.json` | Update build scripts |

---

## Chunk 1: Core Integration (Phase 1)

### Task 1: TypeScript Declarations for Electron API

**Files:**
- Create: `web-app/front/src/types/electron.d.ts`

- [ ] **Step 1: Create the type declaration file**

```typescript
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors related to `electronAPI`

- [ ] **Step 3: Commit**

```bash
git add web-app/front/src/types/electron.d.ts
git commit -m "feat: add TypeScript declarations for Electron API bridge"
```

---

### Task 2: Platform Adapter

**Files:**
- Create: `web-app/front/src/services/platform.ts`

- [ ] **Step 1: Create the platform adapter**

```typescript
// web-app/front/src/services/platform.ts

/** Detect if running inside Electron */
export const isElectron = (): boolean => {
  return typeof window !== 'undefined' && !!window.electronAPI;
};

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

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
      : Promise.resolve(parseInt(import.meta.env.VITE_VNC_PORT || '6080')),
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add web-app/front/src/services/platform.ts
git commit -m "feat: add platform adapter for IPC/REST dual-path routing"
```

---

### Task 3: Expand WebSocket Handler

**Files:**
- Modify: `web-app/front/src/stores/engineStore.ts`
- Modify: `web-app/front/src/services/engineApi.ts`

- [ ] **Step 1: Read current files**

Read `web-app/front/src/stores/engineStore.ts` and `web-app/front/src/services/engineApi.ts` to understand current structure.

- [ ] **Step 2: Update engineApi.ts — add epic/task endpoints and fix WS endpoint**

Add these to `web-app/front/src/services/engineApi.ts`:

```typescript
// Add to the existing engineApi object:

// Epic/Task REST endpoints
export const getEpics = async (projectPath: string): Promise<any> => {
  const response = await fetch(`${API_URL}/dashboard/epics?project_path=${encodeURIComponent(projectPath)}`);
  return response.json();
};

export const getEpicTasks = async (epicId: string, projectPath: string): Promise<any> => {
  const response = await fetch(`${API_URL}/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(projectPath)}`);
  return response.json();
};

export const runEpic = async (epicId: string, projectPath: string): Promise<any> => {
  const response = await fetch(`${API_URL}/dashboard/epic/${epicId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_path: projectPath }),
  });
  return response.json();
};

export const rerunTask = async (epicId: string, taskId: string, projectPath: string, fixInstructions?: string): Promise<any> => {
  const response = await fetch(`${API_URL}/dashboard/epic/${epicId}/task/${taskId}/rerun`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_path: projectPath, fix_instructions: fixInstructions }),
  });
  return response.json();
};
```

Also update `createEngineWebSocket` to use `/api/v1/ws` (the endpoint the FastAPI backend actually serves):

```typescript
// Change the WebSocket URL from:
const wsUrl = `${wsBase}/api/v1/engine/ws`;
// To:
const wsUrl = `${wsBase}/api/v1/ws`;
```

- [ ] **Step 3: Update engineStore.ts — expand WebSocket event handling**

Add these state fields to the store:

```typescript
// New state fields:
epics: [] as EpicInfo[],
tasks: [] as any[],
selectedEpicId: null as string | null,
reviewPaused: false,
reviewFeedback: '',
vncPreviewUrl: null as string | null,
logs: [] as string[],
clarifications: [] as any[],
taskProgress: { completed: 0, running: 0, failed: 0, pending: 0, total: 0, percent: 0 },
```

Expand the WebSocket message handler to cover all event types:

```typescript
// Inside the onMessage handler, expand the switch/if chain:
case 'CONVERGENCE_UPDATE':
  set({ progressPct: data.progress || data.percent || 0, phase: data.phase || get().phase });
  break;
case 'AGENT_STATUS':
  // Update agent in the agents array
  set(state => {
    const agents = [...state.agents];
    const idx = agents.findIndex(a => a.name === data.agent_name);
    const agent = { name: data.agent_name, status: data.status, task: data.task || '', elapsed_seconds: data.elapsed || 0 };
    if (idx >= 0) agents[idx] = agent; else agents.push(agent);
    return { agents };
  });
  break;
case 'REVIEW_PAUSED':
  set({ reviewPaused: true });
  break;
case 'REVIEW_RESUMED':
  set({ reviewPaused: false });
  break;
case 'vnc_preview_ready':
  set({ vncPreviewUrl: data.url || `http://localhost:${data.vnc_port}/vnc.html` });
  break;
case 'task_progress_update':
  set({ taskProgress: data });
  break;
case 'epic_status_changed':
  set(state => {
    const epics = state.epics.map(e => e.id === data.epic_id ? { ...e, ...data } : e);
    return { epics };
  });
  break;
case 'pipeline_progress':
  set({ progressPct: data.percent || 0, taskProgress: data });
  break;
case 'log_entry':
  set(state => ({ logs: [...state.logs.slice(-499), data.message || data.text || JSON.stringify(data)] }));
  break;
case 'clarification_requested':
  set(state => ({ clarifications: [...state.clarifications, data] }));
  break;
case 'engine:file_generated':
  // No-op for now, can be wired to file explorer refresh later
  break;
case 'engine:phase_change':
  set({ phase: data.phase });
  break;
case 'engine:agent_status':
  // Alias for AGENT_STATUS
  set(state => {
    const agents = [...state.agents];
    const idx = agents.findIndex(a => a.name === data.name);
    const agent = { name: data.name, status: data.status, task: data.task || '', elapsed_seconds: data.elapsed_seconds || 0 };
    if (idx >= 0) agents[idx] = agent; else agents.push(agent);
    return { agents };
  });
  break;
case 'engine:epic_progress':
  set(state => {
    const epics = state.epics.map(e => e.id === data.id ? { ...e, progress_pct: data.progress_pct, tasks_complete: data.tasks_complete } : e);
    return { epics };
  });
  break;
case 'engine:progress':
  set({ progressPct: data.progress_pct || data.percent || 0 });
  break;
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add web-app/front/src/stores/engineStore.ts web-app/front/src/services/engineApi.ts
git commit -m "feat: expand WebSocket handler to full 15+ event set and add epic/task API endpoints"
```

---

### Task 4: Wire VNC Preview to Platform Adapter

**Files:**
- Modify: `web-app/front/src/components/engine/VncPreview.tsx`

- [ ] **Step 1: Read current VncPreview.tsx**

Read `web-app/front/src/components/engine/VncPreview.tsx` to see current implementation.

- [ ] **Step 2: Update VncPreview to use platform adapter for port resolution**

Import and use the platform adapter:

```typescript
import { platform, isElectron } from '@/services/platform';
import { useEngineStore } from '@/stores/engineStore';
```

Add port resolution logic:

```typescript
const [vncPort, setVncPort] = useState<number | null>(null);
const vncPreviewUrl = useEngineStore(state => state.vncPreviewUrl);

useEffect(() => {
  if (projectName) {
    platform.ports.getVncPort(projectName).then(port => {
      if (port) setVncPort(port);
    });
  }
}, [projectName]);

// Build VNC URL from port or from store
const vncUrl = vncPreviewUrl
  || (vncPort ? `http://localhost:${vncPort}/vnc.html?autoconnect=true&resize=scale&reconnect=true` : null);
```

Replace the hardcoded VNC URL with the dynamic one.

- [ ] **Step 3: Verify it compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
git add web-app/front/src/components/engine/VncPreview.tsx
git commit -m "feat: wire VNC preview to platform adapter for dynamic port resolution"
```

---

### Task 5: Update Electron Build Config

**Files:**
- Modify: `dashboard-app/electron.vite.config.ts`
- Modify: `dashboard-app/src/main/main.ts`
- Modify: `dashboard-app/package.json`
- Create: `web-app/front/.env.electron`

- [ ] **Step 1: Read current files**

Read `dashboard-app/electron.vite.config.ts`, `dashboard-app/package.json`, and the `createWindow` function in `dashboard-app/src/main/main.ts` (look for `loadFile` or `loadURL`).

- [ ] **Step 2: Remove renderer section from electron.vite.config.ts**

Keep only main and preload sections. Remove the entire `renderer: { ... }` block.

- [ ] **Step 3: Update main.ts loadFile path**

Find the `loadFile` / `loadURL` section and update:

```typescript
// Dev mode: load Vite dev server URL for HMR
if (process.env.ELECTRON_RENDERER_URL) {
  mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
} else {
  // Production: load the web-app's built output
  // Path: out/main/ → ../../../web-app/front/dist/index.html
  mainWindow.loadFile(join(__dirname, '../../../web-app/front/dist/index.html'))
}
```

- [ ] **Step 4: Update package.json build scripts**

Add a script to build the web-app renderer before Electron packaging:

```json
{
  "scripts": {
    "build:renderer": "cd ../web-app/front && npm run build",
    "build:electron": "electron-vite build",
    "build": "npm run build:renderer && npm run build:electron",
    "dev": "ELECTRON_RENDERER_URL=http://localhost:5173 electron-vite dev",
    "dev:web": "cd ../web-app/front && npm run dev"
  }
}
```

- [ ] **Step 5: Create .env.electron for web-app**

```env
# web-app/front/.env.electron
VITE_API_URL=http://localhost:8000/api/v1
VITE_VNC_PORT=6080
VITE_APP_PORT=5173
```

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/electron.vite.config.ts dashboard-app/src/main/main.ts dashboard-app/package.json web-app/front/.env.electron
git commit -m "feat: configure Electron to load web-app as renderer"
```

---

## Chunk 2: Feature Merge (Phase 2)

### Task 6: Epic/Task Management UI

**Files:**
- Create: `web-app/front/src/components/engine/TaskBoard.tsx`
- Modify: `web-app/front/src/components/engine/GenerationMonitor.tsx`

- [ ] **Step 1: Read the current GenerationMonitor.tsx**

Read `web-app/front/src/components/engine/GenerationMonitor.tsx` to understand current tab structure.

- [ ] **Step 2: Create TaskBoard component**

```typescript
// web-app/front/src/components/engine/TaskBoard.tsx
import { useState } from 'react';
import { platform } from '@/services/platform';
import { useEngineStore } from '@/stores/engineStore';

interface Task {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  description?: string;
  elapsed_seconds?: number;
  error?: string;
}

export function TaskBoard({ projectPath }: { projectPath: string }) {
  const epics = useEngineStore(state => state.epics);
  const selectedEpicId = useEngineStore(state => state.selectedEpicId);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [fixInput, setFixInput] = useState<Record<string, string>>({});

  const loadTasks = async (epicId: string) => {
    setLoading(true);
    try {
      const result = await platform.engine.getEpicTasks(epicId, projectPath);
      setTasks(result.tasks || []);
      useEngineStore.setState({ selectedEpicId: epicId });
    } catch (e) {
      console.error('Failed to load tasks:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleRunEpic = async (epicId: string) => {
    await platform.engine.runEpic(epicId, projectPath);
  };

  const handleRerunTask = async (epicId: string, taskId: string) => {
    await platform.engine.rerunTask(epicId, taskId, projectPath, fixInput[taskId]);
    setFixInput(prev => ({ ...prev, [taskId]: '' }));
    // Reload tasks
    if (selectedEpicId) loadTasks(selectedEpicId);
  };

  const statusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-400';
      case 'running': return 'text-blue-400';
      case 'failed': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const statusDot = (status: string) => {
    switch (status) {
      case 'completed': return '✓';
      case 'running': return '▶';
      case 'failed': return '✗';
      default: return '○';
    }
  };

  return (
    <div className="flex h-full gap-4">
      {/* Epic list */}
      <div className="w-64 border-r border-white/10 pr-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-white/70 mb-3">Epics</h3>
        {epics.map(epic => (
          <div
            key={epic.id}
            onClick={() => loadTasks(epic.id)}
            className={`p-3 rounded-lg cursor-pointer mb-2 transition-colors ${
              selectedEpicId === epic.id ? 'bg-indigo-600/30 border border-indigo-500/50' : 'bg-white/5 hover:bg-white/10'
            }`}
          >
            <div className="text-sm font-medium text-white">{epic.name}</div>
            <div className="flex items-center gap-2 mt-1">
              <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${epic.progress_pct}%` }} />
              </div>
              <span className="text-xs text-white/50">{epic.tasks_complete}/{epic.tasks_total}</span>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); handleRunEpic(epic.id); }}
              className="mt-2 text-xs px-2 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Run Epic
            </button>
          </div>
        ))}
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto">
        <h3 className="text-sm font-semibold text-white/70 mb-3">
          Tasks {selectedEpicId && `(${tasks.length})`}
        </h3>
        {loading ? (
          <div className="text-white/50 text-sm">Loading tasks...</div>
        ) : tasks.length === 0 ? (
          <div className="text-white/50 text-sm">Select an epic to view tasks</div>
        ) : (
          <div className="space-y-2">
            {tasks.map(task => (
              <div key={task.id} className="p-3 bg-white/5 rounded-lg">
                <div className="flex items-center gap-2">
                  <span className={`text-sm ${statusColor(task.status)}`}>{statusDot(task.status)}</span>
                  <span className="text-sm text-white font-medium">{task.name}</span>
                  {task.elapsed_seconds && (
                    <span className="text-xs text-white/40 ml-auto">{task.elapsed_seconds}s</span>
                  )}
                </div>
                {task.description && (
                  <p className="text-xs text-white/50 mt-1 ml-6">{task.description}</p>
                )}
                {task.error && (
                  <p className="text-xs text-red-400 mt-1 ml-6">{task.error}</p>
                )}
                {task.status === 'failed' && selectedEpicId && (
                  <div className="ml-6 mt-2 flex gap-2">
                    <input
                      type="text"
                      placeholder="Fix instructions (optional)"
                      value={fixInput[task.id] || ''}
                      onChange={(e) => setFixInput(prev => ({ ...prev, [task.id]: e.target.value }))}
                      className="flex-1 text-xs px-2 py-1 rounded bg-white/10 border border-white/20 text-white placeholder:text-white/30"
                    />
                    <button
                      onClick={() => handleRerunTask(selectedEpicId, task.id)}
                      className="text-xs px-2 py-1 rounded bg-orange-600 hover:bg-orange-500 text-white"
                    >
                      Rerun
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire TaskBoard into GenerationMonitor's Tasks tab**

In `GenerationMonitor.tsx`, import and render `TaskBoard` in the Tasks sub-tab:

```typescript
import { TaskBoard } from './TaskBoard';

// In the Tasks tab content:
<TaskBoard projectPath={projectPath} />
```

- [ ] **Step 4: Verify it compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 5: Commit**

```bash
git add web-app/front/src/components/engine/TaskBoard.tsx web-app/front/src/components/engine/GenerationMonitor.tsx
git commit -m "feat: add TaskBoard component with epic/task management and rerun"
```

---

### Task 7: Review Gate UI

**Files:**
- Create: `web-app/front/src/components/engine/ReviewChat.tsx`
- Modify: `web-app/front/src/components/engine/GenerationMonitor.tsx`

- [ ] **Step 1: Create ReviewChat component**

```typescript
// web-app/front/src/components/engine/ReviewChat.tsx
import { useState } from 'react';
import { useEngineStore } from '@/stores/engineStore';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export function ReviewChat({ projectId }: { projectId: string }) {
  const reviewPaused = useEngineStore(state => state.reviewPaused);
  const [feedback, setFeedback] = useState('');
  const [sending, setSending] = useState(false);

  const handlePause = async () => {
    await fetch(`${API_BASE}/dashboard/generation/${projectId}/pause`, { method: 'POST' });
  };

  const handleResume = async () => {
    setSending(true);
    try {
      await fetch(`${API_BASE}/dashboard/generation/${projectId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback }),
      });
      setFeedback('');
    } finally {
      setSending(false);
    }
  };

  if (!reviewPaused) {
    return (
      <div className="p-4">
        <button
          onClick={handlePause}
          className="px-4 py-2 rounded-lg bg-yellow-600 hover:bg-yellow-500 text-white text-sm font-medium"
        >
          ⏸ Pause for Review
        </button>
        <p className="text-xs text-white/40 mt-2">
          Pauses generation at the next checkpoint so you can review and provide feedback.
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 border border-yellow-500/30 rounded-lg bg-yellow-500/5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
        <span className="text-sm font-semibold text-yellow-400">Generation Paused — Awaiting Review</span>
      </div>
      <textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder="Describe issues or adjustments needed..."
        className="w-full h-32 p-3 rounded-lg bg-white/5 border border-white/20 text-white text-sm placeholder:text-white/30 resize-none"
      />
      <div className="flex gap-2 mt-3">
        <button
          onClick={handleResume}
          disabled={sending}
          className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium disabled:opacity-50"
        >
          {sending ? 'Resuming...' : '▶ Resume with Feedback'}
        </button>
        <button
          onClick={() => { setFeedback(''); handleResume(); }}
          disabled={sending}
          className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm"
        >
          Resume (No Changes)
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add ReviewChat to GenerationMonitor**

Import `ReviewChat` and render it above the tab content when `reviewPaused` is true:

```typescript
import { ReviewChat } from './ReviewChat';
import { useEngineStore } from '@/stores/engineStore';

// Inside GenerationMonitor:
const reviewPaused = useEngineStore(state => state.reviewPaused);

// Render above tabs:
{reviewPaused && <ReviewChat projectId={projectName} />}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
git add web-app/front/src/components/engine/ReviewChat.tsx web-app/front/src/components/engine/GenerationMonitor.tsx
git commit -m "feat: add Review Gate UI with pause/resume and feedback chat"
```

---

### Task 8: Service Status Bar

**Files:**
- Create: `web-app/front/src/components/engine/ServiceStatusBar.tsx`
- Modify: `web-app/front/src/components/Navbar.tsx`

- [ ] **Step 1: Create ServiceStatusBar component**

```typescript
// web-app/front/src/components/engine/ServiceStatusBar.tsx
import { useState, useEffect } from 'react';
import { platform, platformEvents, isElectron } from '@/services/platform';

interface Status {
  fastapi: boolean;
  docker: boolean;
}

export function ServiceStatusBar() {
  const [status, setStatus] = useState<Status>({ fastapi: false, docker: false });

  useEffect(() => {
    // Initial check
    const checkStatus = async () => {
      try {
        if (isElectron()) {
          const s = await window.electronAPI!.services.getStatus();
          setStatus({ fastapi: s.fastapi, docker: s.docker });
        } else {
          // In browser, just check if FastAPI responds
          const res = await fetch((import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1') + '/engine/projects');
          setStatus({ fastapi: res.ok, docker: false });
        }
      } catch {
        setStatus({ fastapi: false, docker: false });
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 10000);

    // Listen for push events from Electron main process
    platformEvents.onServiceStatusUpdate((s) => {
      setStatus({ fastapi: s.fastapi, docker: s.docker });
    });

    return () => clearInterval(interval);
  }, []);

  const Dot = ({ active }: { active: boolean }) => (
    <span className={`w-1.5 h-1.5 rounded-full inline-block ${active ? 'bg-green-400' : 'bg-red-400'}`} />
  );

  return (
    <div className="flex items-center gap-3 text-xs text-white/60">
      <span className="flex items-center gap-1"><Dot active={status.fastapi} /> API</span>
      {isElectron() && <span className="flex items-center gap-1"><Dot active={status.docker} /> Docker</span>}
    </div>
  );
}
```

- [ ] **Step 2: Add ServiceStatusBar to Navbar**

Read `web-app/front/src/components/Navbar.tsx`, then add `ServiceStatusBar` next to the existing `EngineStatusPill`:

```typescript
import { ServiceStatusBar } from './engine/ServiceStatusBar';

// In the top-right area of the navbar, next to EngineStatusPill:
<ServiceStatusBar />
```

- [ ] **Step 3: Verify it compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 4: Commit**

```bash
git add web-app/front/src/components/engine/ServiceStatusBar.tsx web-app/front/src/components/Navbar.tsx
git commit -m "feat: add service status bar showing FastAPI/Docker health"
```

---

## Chunk 3: Advanced Features (Phase 3)

### Task 9: Clarification Panel

**Files:**
- Create: `web-app/front/src/services/clarificationApi.ts`
- Create: `web-app/front/src/components/engine/ClarificationPanel.tsx`
- Modify: `web-app/front/src/components/engine/GenerationMonitor.tsx`

- [ ] **Step 1: Create clarification API client**

```typescript
// web-app/front/src/services/clarificationApi.ts
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export interface Clarification {
  id: string;
  task_id: string;
  question: string;
  options?: { id: string; label: string; description?: string }[];
  status: 'pending' | 'resolved';
}

export const getClarifications = async (): Promise<Clarification[]> => {
  const res = await fetch(`${API_BASE}/clarifications`);
  return res.json();
};

export const submitClarificationChoice = async (id: string, choiceId: string): Promise<void> => {
  await fetch(`${API_BASE}/clarifications/${id}/choice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ choice_id: choiceId }),
  });
};
```

- [ ] **Step 2: Create ClarificationPanel component**

```typescript
// web-app/front/src/components/engine/ClarificationPanel.tsx
import { useState, useEffect } from 'react';
import { useEngineStore } from '@/stores/engineStore';
import { getClarifications, submitClarificationChoice, type Clarification } from '@/services/clarificationApi';

export function ClarificationPanel() {
  const wsClarifications = useEngineStore(state => state.clarifications);
  const [clarifications, setClarifications] = useState<Clarification[]>([]);
  const [submitting, setSubmitting] = useState<string | null>(null);

  // Load clarifications on mount and when WebSocket pushes new ones
  useEffect(() => {
    getClarifications().then(setClarifications).catch(() => {});
  }, [wsClarifications.length]);

  const handleChoice = async (clarId: string, choiceId: string) => {
    setSubmitting(clarId);
    try {
      await submitClarificationChoice(clarId, choiceId);
      setClarifications(prev => prev.filter(c => c.id !== clarId));
    } finally {
      setSubmitting(null);
    }
  };

  const pending = clarifications.filter(c => c.status === 'pending');

  if (pending.length === 0) {
    return <div className="p-4 text-sm text-white/40">No pending clarifications.</div>;
  }

  return (
    <div className="p-4 space-y-4">
      {pending.map(clar => (
        <div key={clar.id} className="p-4 bg-white/5 rounded-lg border border-amber-500/20">
          <div className="text-sm font-medium text-amber-400 mb-1">⚠ Clarification Needed</div>
          <p className="text-sm text-white mb-3">{clar.question}</p>
          {clar.options && (
            <div className="space-y-2">
              {clar.options.map(opt => (
                <button
                  key={opt.id}
                  onClick={() => handleChoice(clar.id, opt.id)}
                  disabled={submitting === clar.id}
                  className="w-full text-left p-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition-colors disabled:opacity-50"
                >
                  <div className="text-sm text-white font-medium">{opt.label}</div>
                  {opt.description && <div className="text-xs text-white/50 mt-1">{opt.description}</div>}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Wire ClarificationPanel into GenerationMonitor**

In the GenerationMonitor, add a notification badge and render the panel. When there are pending clarifications, show a badge on the tab.

- [ ] **Step 4: Verify it compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 5: Commit**

```bash
git add web-app/front/src/services/clarificationApi.ts web-app/front/src/components/engine/ClarificationPanel.tsx web-app/front/src/components/engine/GenerationMonitor.tsx
git commit -m "feat: add clarification panel with multi-choice responses"
```

---

### Task 10: Log Viewer

**Files:**
- Modify: `web-app/front/src/components/engine/GenerationMonitor.tsx`

- [ ] **Step 1: Add LogViewer to the Logs sub-tab**

```typescript
// Inline in GenerationMonitor.tsx or extract to a separate component:
function LogViewer() {
  const logs = useEngineStore(state => state.logs);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs.length]);

  return (
    <div ref={containerRef} className="h-full overflow-y-auto font-mono text-xs p-4 bg-black/30 rounded-lg">
      {logs.length === 0 ? (
        <div className="text-white/30">No logs yet. Start generation to see output.</div>
      ) : (
        logs.map((log, i) => (
          <div key={i} className="text-white/70 py-0.5 border-b border-white/5">{log}</div>
        ))
      )}
    </div>
  );
}
```

Wire this into the Logs sub-tab.

- [ ] **Step 2: Verify it compiles**

Run: `cd web-app/front && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 3: Commit**

```bash
git add web-app/front/src/components/engine/GenerationMonitor.tsx
git commit -m "feat: add real-time log viewer to Generation Monitor"
```

---

### Task 11: Final Integration Commit

- [ ] **Step 1: Build web-app to verify everything works**

```bash
cd web-app/front && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Push to remote**

```bash
cd /c/Users/User/Desktop/Dave\&Felix/DaveFelix-Coding-Engine && git push
```
