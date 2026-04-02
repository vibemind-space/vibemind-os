# Electron Renderer Replacement — Design Spec

**Date:** 2026-03-16
**Status:** Approved
**Goal:** Replace the Electron dashboard-app's renderer with the new unified web-app frontend, keeping Electron's main process (IPC, Docker, Ports) intact. The result is one codebase that works both as a standalone web app and as an Electron desktop app.

---

## 1. Strategy

Replace `dashboard-app/src/renderer/` with `web-app/front/` as the Electron renderer. Add an adapter layer so the web-app detects whether it's running inside Electron (via `window.electronAPI`) and routes calls accordingly:

- **In Electron:** IPC → main process → Docker/ports/filesystem
- **In Browser:** REST → FastAPI backend directly

The existing dual-path pattern in the dashboard-app's engineStore (IPC-first, REST-fallback) becomes the standard for all service calls.

---

## 2. What Stays, What Changes

### Keep (Electron Main Process)
- `src/main/main.ts` — 40+ IPC handlers (docker, engine, projects, services, fs, debug)
- `src/main/docker-manager.ts` — Container lifecycle + VNC
- `src/main/port-allocator.ts` — Dynamic port assignment
- `src/main/service-manager.ts` — FastAPI health checks
- `src/preload/preload.ts` — IPC bridge exposing `window.electronAPI`

### Replace (Renderer)
- `src/renderer/` → Replaced entirely by `web-app/front/` build output
- Old components, stores, and API clients are superseded by the new UI

### Merge Into New UI (Features from Old Renderer)

**Components:**

| Feature | Old Location | New Location |
|---------|-------------|-------------|
| Epic management (load, run, rerun) | `engineStore.ts` (lines 400-600) | `stores/engineStore.ts` + `services/engineApi.ts` |
| Task board (per-epic tasks, rerun) | `GenerationMonitor/TaskList.tsx` | `components/engine/TaskBoard.tsx` |
| Review Gate (pause, chat, resume) | `ReviewChat/ReviewChat.tsx` + `projectStore.ts` | `components/engine/ReviewChat.tsx` |
| Clarification system | `ClarificationPanel.tsx` + `clarificationStore.ts` | `components/engine/ClarificationPanel.tsx` |
| Vibe Chat (WebSocket streaming) | `VibeChat/VibeChat.tsx` + `vibeStore.ts` | New `components/engine/VibeChat.tsx` (separate from ChatPanel) |
| Service status bar | `ServiceStatusBar.tsx` | `components/engine/ServiceStatusBar.tsx` |
| Docker control (start/stop engine) | `engineStore.ts` | `stores/engineStore.ts` via adapter |
| RE Project scanning | `projectStore.ts` | `stores/projectStore.ts` via adapter |

**API Clients:**

| Old Client | Purpose | New Location |
|-----------|---------|-------------|
| `vibeAPI.ts` | Vibe WebSocket streaming | `services/vibeApi.ts` |
| `clarificationAPI.ts` | Clarification queue | `services/clarificationApi.ts` |
| `debugAPI.ts` | Browser errors, Docker logs | `services/debugApi.ts` |
| `visionAPI.ts` | Claude Vision analysis | `services/visionApi.ts` |
| `portalAPI.ts` | Marketplace cells | `services/portalApi.ts` |
| `webAPI.ts` | Orchestrator project types | Merge into `services/engineApi.ts` |

**Zustand Stores:**

| Old Store | State | New Store |
|-----------|-------|-----------|
| `engineStore` (912 lines) | Generation, agents, epics, tasks, WS | `stores/engineStore.ts` (expand existing) |
| `projectStore` (786 lines) | Projects, orchestrator, RE projects | `stores/projectStore.ts` (new) |
| `clarificationStore` | Clarification queue | Merge into `stores/engineStore.ts` |
| `debugStore` | Debug mode state | Merge into `stores/engineStore.ts` |
| `vibeStore` | Vibe sessions | `stores/vibeStore.ts` (new) |
| `portalStore` | Marketplace state | `stores/portalStore.ts` (new) |
| `enrichmentStore` | Enrichment data | Drop (Phase 3 if needed) |
| `llmConfigStore` | LLM model configs | Drop (Phase 3 if needed) |
| `tenantStore` | Tenant switching | Drop (out of scope) |

---

## 3. IPC Adapter Pattern

A thin adapter that routes calls to IPC (Electron) or REST (browser). Supports both invoke-style (request/response) and push-style (main→renderer events).

```typescript
// services/platform.ts
export const isElectron = () => !!window.electronAPI;

// --- Invoke-style calls (request/response) ---
export const platform = {
  docker: {
    startEngine: () => isElectron()
      ? window.electronAPI!.docker.startEngine()
      : fetch('/api/v1/engine/docker/start', { method: 'POST' }).then(r => r.json()),
    stopEngine: () => isElectron()
      ? window.electronAPI!.docker.stopEngine()
      : fetch('/api/v1/engine/docker/stop', { method: 'POST' }).then(r => r.json()),
    getStatus: () => isElectron()
      ? window.electronAPI!.docker.getEngineStatus()
      : fetch('/api/v1/engine/docker/status').then(r => r.json()),
    startProject: (projectId: string, reqPath: string, outputDir: string) => isElectron()
      ? window.electronAPI!.docker.startProject(projectId, reqPath, outputDir)
      : fetch('/api/v1/engine/docker/project/start', { method: 'POST', body: JSON.stringify({ projectId, reqPath, outputDir }) }).then(r => r.json()),
    stopProject: (projectId: string) => isElectron()
      ? window.electronAPI!.docker.stopProject(projectId)
      : fetch('/api/v1/engine/docker/project/stop', { method: 'POST', body: JSON.stringify({ projectId }) }).then(r => r.json()),
    getProjectLogs: (projectId: string, tail?: number) => isElectron()
      ? window.electronAPI!.docker.getProjectLogs(projectId, tail)
      : fetch(`/api/v1/engine/docker/project/${projectId}/logs?tail=${tail || 100}`).then(r => r.json()),
  },
  ports: {
    getVncPort: (id: string) => isElectron()
      ? window.electronAPI!.ports.getVncPort(id)
      : Promise.resolve(parseInt(import.meta.env.VITE_VNC_PORT || '6080')),
    getAppPort: (id: string) => isElectron()
      ? window.electronAPI!.ports.getAppPort(id)
      : Promise.resolve(parseInt(import.meta.env.VITE_APP_PORT || '5173')),
  },
  fs: {
    openFolder: (path: string) => isElectron()
      ? window.electronAPI!.fs.openFolder(path)
      : Promise.resolve(), // No-op in browser
    showInExplorer: (path: string) => isElectron()
      ? window.electronAPI!.fs.showInExplorer(path)
      : Promise.resolve(), // No-op in browser
    exists: (path: string) => isElectron()
      ? window.electronAPI!.fs.exists(path)
      : fetch(`/api/v1/engine/fs/exists?path=${encodeURIComponent(path)}`).then(r => r.json()),
  },
  engine: {
    // Epic/task handlers: REST-only (deliberately).
    // The IPC handlers in main.ts are just fetch proxies to FastAPI anyway,
    // so calling REST directly eliminates the IPC hop without losing functionality.
    getEpics: (path: string) =>
      fetch(`/api/v1/dashboard/epics?project_path=${encodeURIComponent(path)}`).then(r => r.json()),
    getEpicTasks: (epicId: string, path: string) =>
      fetch(`/api/v1/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(path)}`).then(r => r.json()),
    runEpic: (epicId: string, path: string) =>
      fetch(`/api/v1/dashboard/epic/${epicId}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_path: path }) }).then(r => r.json()),
    rerunEpic: (epicId: string, path: string) =>
      fetch(`/api/v1/dashboard/epic/${epicId}/rerun`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_path: path }) }).then(r => r.json()),
    rerunTask: (epicId: string, taskId: string, path: string, fixInstructions?: string) =>
      fetch(`/api/v1/dashboard/epic/${epicId}/task/${taskId}/rerun`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_path: path, fix_instructions: fixInstructions }) }).then(r => r.json()),
    generateTaskLists: (path: string) =>
      fetch('/api/v1/dashboard/generate-task-lists', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_path: path }) }).then(r => r.json()),
    startGenerationWithPreview: (projectId: string, reqPath: string, outputDir: string, projectPath: string) => isElectron()
      ? window.electronAPI!.engine.startGenerationWithPreview(projectId, reqPath, outputDir, projectPath)
      : fetch('/api/v1/engine/projects/' + projectId + '/start', { method: 'POST' }).then(r => r.json()),
    stopGeneration: (projectId: string) => isElectron()
      ? window.electronAPI!.engine.stopGeneration(projectId)
      : fetch('/api/v1/engine/projects/' + projectId + '/stop', { method: 'POST' }).then(r => r.json()),
  },
  projects: {
    scanLocalDirs: () => isElectron()
      ? window.electronAPI!.projects.scanLocalDirs()
      : fetch('/api/v1/engine/projects/scan-local').then(r => r.json()),
    getREDetail: (path: string) => isElectron()
      ? window.electronAPI!.projects.getREDetail(path)
      : fetch(`/api/v1/engine/projects/re-detail?path=${encodeURIComponent(path)}`).then(r => r.json()),
  },
};

// --- Push-style events (main process → renderer) ---
export const platformEvents = {
  onServiceStatusUpdate: (callback: (status: any) => void) => {
    if (isElectron()) {
      window.electronAPI!.services.onStatusUpdate(callback);
    }
    // In browser: no push events from main process, use WebSocket instead
  },
};
```

---

## 4. WebSocket Reconciliation

The old renderer connects to `ws://localhost:8000/api/v1/ws` and handles 15+ event types. The new web-app connects to `/api/v1/engine/ws` and handles 4 event types. **The merged UI uses the old endpoint** (`/api/v1/ws`) since it's the one the FastAPI backend actually serves, and expands the handler to cover all event types:

### Event Types (merged set)

| Event | Source | Used By |
|-------|--------|---------|
| `CONVERGENCE_UPDATE` | Engine | Progress bar, phase display |
| `AGENT_STATUS` | Engine | Agent list |
| `REVIEW_PAUSED` / `REVIEW_RESUMED` | Engine | Review Gate UI |
| `vnc_preview_ready` | Docker/Engine | VNC panel auto-connect |
| `task_progress_update` | Epic Orchestrator | Task board (includes sub-types: plan_created, batch_started, task_status_changed) |
| `epic_status_changed` | Epic Orchestrator | Epic sidebar |
| `epic_execution_started` / `completed` | Epic Orchestrator | Epic progress |
| `pipeline_progress` | Epic Orchestrator | Overall progress bar |
| `log_entry` | Engine | Log viewer |
| `clarification_requested` | Engine | Clarification panel |
| `engine:file_generated` | Engine | File explorer refresh |
| `engine:phase_change` | Engine | Status pill |

The web-app's `engineStore.ts` WebSocket handler will be expanded to handle this full set, replacing the current 4-event handler.

---

## 5. Electron Build Integration

### Build Tooling Decision

The dashboard-app uses `electron-vite` (configured in `electron.vite.config.ts`). We **remove the renderer section** from `electron.vite.config.ts` and build the web-app independently with plain Vite. The main and preload sections remain under `electron-vite`.

```typescript
// electron.vite.config.ts — AFTER
export default defineConfig({
  main: { /* unchanged */ },
  preload: { /* unchanged */ },
  // renderer section REMOVED — built separately via web-app/front/
})
```

### Directory Structure

```
DaveFelix-Coding-Engine/
├── dashboard-app/
│   ├── src/
│   │   ├── main/           ← UNCHANGED (IPC, Docker, Ports)
│   │   └── preload/        ← UNCHANGED (Bridge)
│   ├── electron.vite.config.ts  ← Renderer section removed
│   └── package.json        ← Updated build scripts
├── web-app/
│   └── front/              ← The renderer source
│       ├── src/            ← React + Vite + shadcn/ui
│       └── dist/           ← Build output (loaded by Electron)
```

### Build Flow

1. `cd web-app/front && npm run build` → produces `web-app/front/dist/`
2. `cd dashboard-app && npm run build:main` → compiles main + preload only
3. Electron loads the web-app build output

### main.ts Path Fix

```typescript
// main.ts — loadFile path (from out/main/ → repo root → web-app/front/dist/)
if (process.env.ELECTRON_RENDERER_URL) {
  // Dev mode: load Vite dev server directly (HMR works)
  mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
} else {
  // Production: load built web-app
  mainWindow.loadFile(path.join(__dirname, '../../../web-app/front/dist/index.html'))
}
```

Path calculation: `__dirname` = `dashboard-app/out/main/` → `../` = `out/` → `../../` = `dashboard-app/` → `../../../` = repo root → `web-app/front/dist/index.html`.

### Dev Mode

Set `ELECTRON_RENDERER_URL=http://localhost:5173` and run the web-app's Vite dev server. Electron loads the URL, giving full HMR during development. The preload script still injects `window.electronAPI`.

### Environment Variables

The web-app uses `import.meta.env.VITE_API_URL` for API base URL. Configure per environment:
- **Browser (standalone):** `.env` with `VITE_API_URL=http://localhost:8000/api/v1`
- **Electron (production):** Build-time `.env.electron` with `VITE_API_URL=http://localhost:8000/api/v1`
- **Electron (dev):** `ELECTRON_RENDERER_URL=http://localhost:5173`, web-app uses its own `.env`
- **VNC port fallback:** `VITE_VNC_PORT=6080` (used when not in Electron; Electron uses PortAllocator via IPC)

---

## 6. TypeScript Type Declarations

Comprehensive types matching the actual preload.ts interface:

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

---

## 7. Feature Migration Priority

### Phase 1: Core Integration (Electron loads new UI)
**Acceptance:** Electron opens, renders the new UI, VNC preview works, Docker start/stop works via IPC.
1. Platform adapter (`services/platform.ts`) with invoke + push patterns
2. TypeScript declarations (`types/electron.d.ts`)
3. Remove renderer section from `electron.vite.config.ts`
4. Update main.ts `loadFile` path + dev mode `loadURL`
5. Wire VNC preview to use IPC port allocation in Electron, env var fallback in browser
6. Expand WebSocket handler to cover full event set

### Phase 2: Merge Missing Features
**Acceptance:** Epic/task management, Review Gate, and service status work end-to-end.
7. Epic management (load, select, run, rerun epics + tasks) via REST
8. Review Gate (pause/resume with chat feedback) via WebSocket events
9. Service status bar (FastAPI/Docker health via IPC or polling)
10. New API clients (vibeApi, clarificationApi, debugApi, visionApi, portalApi)
11. New stores (projectStore, vibeStore, portalStore)

### Phase 3: Advanced Features
**Acceptance:** All old renderer features available in new UI.
12. Clarification system (queue + multi-choice responses)
13. RE project scanning (local directory scan via IPC)
14. Docker control from UI (start/stop engine containers)

---

## 8. Routing

The web-app uses `react-router-dom` with pages: `/`, `/projects`, `/editor/:id`, `/engine-editor/:projectName`, `/marketplace`, `/documentation`. In Electron, the app loads as a single-page app (SPA), so all routing is client-side hash-based or history-based. No changes needed — `BrowserWindow.loadFile()` loads `index.html` and React Router handles navigation.

---

## 9. Out of Scope

- Rewriting Electron main process
- Changing IPC handler signatures
- Auto-update / code signing
- Mobile / responsive layout
- Multi-window Electron support
- Multi-tenant support (tenantStore dropped)
