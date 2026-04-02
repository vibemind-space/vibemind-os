// front/src/services/engineApi.ts
import { API_URL } from './api';

// Types
export interface EngineProject {
  name: string;
  path: string;
  service_count: number;
  endpoint_count: number;
  story_count: number;
  epic_count: number;
  has_user_stories: boolean;
  has_api_docs: boolean;
  has_data_dictionary: boolean;
  created_at: string | null;
  type: 'engine' | 'vibe';
}

// Backend response from /dashboard/local-projects
interface LocalProjectResponse {
  project_id: string;
  project_name: string;
  project_path: string;
  has_user_stories: boolean;
  has_api_docs: boolean;
  has_data_dictionary: boolean;
  epic_count: number;
  user_story_count: number;
  created_at: string | null;
}

interface LocalProjectsResponse {
  projects: LocalProjectResponse[];
  total: number;
  scan_path: string;
}

export interface EngineProjectDetail extends EngineProject {
  services: Array<{
    name: string;
    port: number;
    endpoint_count: number;
    entity_count: number;
    story_count: number;
  }>;
  generation_order: string[];
  dependency_graph: Record<string, string[]>;
}

export type AgentStatus = 'running' | 'done' | 'queued' | 'failed';
export type GenerationPhase = 'idle' | 'parsing' | 'skeleton' | 'generation' | 'validation' | 'integration' | 'complete' | 'failed';

export interface AgentInfo {
  name: string;
  status: AgentStatus;
  task: string;
  elapsed_seconds: number;
}

export interface EpicInfo {
  id: string;
  name: string;
  progress_pct: number;
  tasks_total: number;
  tasks_complete: number;
}

export interface GenerationStatus {
  project_name: string;
  phase: GenerationPhase;
  progress_pct: number;
  agents: AgentInfo[];
  epics: EpicInfo[];
  service_count: number;
  endpoint_count: number;
}

// REST API
export const engineApi = {
  listProjects: async (): Promise<EngineProject[]> => {
    const res = await fetch(`${API_URL}/dashboard/local-projects`);
    if (!res.ok) throw new Error(`Failed to list engine projects: ${res.status}`);
    const data: LocalProjectsResponse = await res.json();
    // Map backend response to EngineProject format
    return data.projects.map((p) => ({
      name: p.project_id,
      path: p.project_path,
      service_count: 0, // Not available from scan endpoint
      endpoint_count: 0,
      story_count: p.user_story_count,
      epic_count: p.epic_count,
      has_user_stories: p.has_user_stories,
      has_api_docs: p.has_api_docs,
      has_data_dictionary: p.has_data_dictionary,
      created_at: p.created_at,
      type: 'engine' as const,
    }));
  },

  getProject: async (name: string): Promise<EngineProjectDetail> => {
    // Use local-projects scan to get project detail
    const res = await fetch(`${API_URL}/dashboard/local-projects`);
    if (!res.ok) throw new Error(`Failed to get engine project: ${res.status}`);
    const data: LocalProjectsResponse = await res.json();
    const p = data.projects.find((proj) => proj.project_id === name);
    if (!p) throw new Error(`Project not found: ${name}`);
    return {
      name: p.project_id,
      path: p.project_path,
      service_count: 0,
      endpoint_count: 0,
      story_count: p.user_story_count,
      epic_count: p.epic_count,
      has_user_stories: p.has_user_stories,
      has_api_docs: p.has_api_docs,
      has_data_dictionary: p.has_data_dictionary,
      created_at: p.created_at,
      type: 'engine' as const,
      services: [],
      generation_order: [],
      dependency_graph: {},
    };
  },

  getStatus: async (_name: string): Promise<GenerationStatus> => {
    try {
      // Try the dashboard/status endpoint first (primary), fall back to project/status
      let res = await fetch(`${API_URL}/dashboard/status?projectId=${encodeURIComponent(_name)}`);
      if (!res.ok) {
        // Fallback: try project-specific status endpoint
        res = await fetch(`${API_URL}/dashboard/project/status?projectId=${encodeURIComponent(_name)}`);
      }
      if (!res.ok) {
        // No active generation — return idle status
        return {
          project_name: _name,
          phase: 'idle',
          progress_pct: 0,
          agents: [],
          epics: [],
          service_count: 0,
          endpoint_count: 0,
        };
      }
      const data = await res.json();
      return {
        project_name: _name,
        phase: data.phase || data.status || 'idle',
        progress_pct: data.progress_pct || data.progress || 0,
        agents: data.agents || [],
        epics: data.epics || [],
        service_count: data.service_count || 0,
        endpoint_count: data.endpoint_count || 0,
      };
    } catch {
      return {
        project_name: _name,
        phase: 'idle',
        progress_pct: 0,
        agents: [],
        epics: [],
        service_count: 0,
        endpoint_count: 0,
      };
    }
  },

  startGeneration: async (
    name: string,
    opts: { projectPath?: string; parallelism?: number } = {},
  ): Promise<GenerationStatus> => {
    const projectPath = opts.projectPath || `/app/Data/all_services/${name}`;
    const outputDir = `/app/output/${name}`;

    // Step 1: Try to start sandbox container (non-blocking, ok to fail)
    try {
      await fetch(`${API_URL}/dashboard/project/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectId: name,
          outputDir,
          vncPort: 6090,
          appPort: 3100,
        }),
      });
    } catch {
      // Sandbox container start is optional — generation works without it
    }

    // Step 2: Start the epic-based generation pipeline
    // Try the primary endpoint, fall back to dashboard path
    let genRes: Response;
    try {
      genRes = await fetch(`${API_URL}/dashboard/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectId: name,
          requirementsPath: projectPath,
          outputDir: outputDir,
        }),
      });
    } catch (fetchErr) {
      throw new Error(`Failed to start generation: network error`);
    }

    if (!genRes.ok) {
      const err = await genRes.text();
      throw new Error(`Failed to start generation: ${genRes.status} - ${err}`);
    }

    return {
      project_name: name,
      phase: 'generation',
      progress_pct: 0,
      agents: [],
      epics: [],
      service_count: 0,
      endpoint_count: 0,
    };
  },

  stopGeneration: async (name: string): Promise<GenerationStatus> => {
    const res = await fetch(`${API_URL}/dashboard/stop-generation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: name }),
    });
    if (!res.ok) throw new Error(`Failed to stop generation: ${res.status}`);
    return {
      project_name: name,
      phase: 'idle',
      progress_pct: 0,
      agents: [],
      epics: [],
      service_count: 0,
      endpoint_count: 0,
    };
  },
};

// Epic/Task REST endpoints
export const getEpics = async (projectPath: string): Promise<any> => {
  const response = await fetch(`${API_URL}/dashboard/epics?project_path=${encodeURIComponent(projectPath)}`);
  return response.json();
};

export const getEpicTasks = async (epicId: string, projectPath: string): Promise<any> => {
  const response = await fetch(`${API_URL}/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(projectPath)}`);
  return response.json();
};

// --- DB-backed API endpoints (PostgreSQL) ---

export const getDbProjects = async (): Promise<any[]> => {
  const response = await fetch(`${API_URL}/dashboard/db/projects`);
  if (!response.ok) throw new Error(`Failed to load projects: ${response.status}`);
  return response.json();
};

export const getDbTasks = async (projectId: number): Promise<{ job: any; tasks: any[] }> => {
  const response = await fetch(`${API_URL}/dashboard/db/projects/${projectId}/tasks`);
  if (!response.ok) throw new Error(`Failed to load tasks: ${response.status}`);
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

// WebSocket connection
export function createEngineWebSocket(
  onEvent: (type: string, data: any) => void,
): WebSocket {
  // Build WS URL: in dev mode (relative API_URL like /api/v1), use current host
  // In production or absolute URL mode, replace http with ws
  let wsUrl: string;
  if (API_URL.startsWith('/')) {
    // Relative URL — build from window.location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsUrl = `${protocol}//${window.location.host}/api/v1/engine/generation/ws`;
  } else {
    wsUrl = API_URL.replace(/^http/, 'ws').replace('/api/v1', '') + '/api/v1/engine/generation/ws';
  }

  console.log('[Engine WS] Connecting to:', wsUrl);
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('[Engine WS] Connected');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      // Support both {type, data} and {event, ...rest} message formats
      const eventType = msg.type || msg.event;
      const eventData = msg.data || msg;
      if (eventType) {
        onEvent(eventType, eventData);
      }
    } catch (e) {
      console.error('Failed to parse engine WS message:', e);
    }
  };

  ws.onerror = (e) => console.error('[Engine WS] Error:', e);
  ws.onclose = (e) => console.log('[Engine WS] Closed:', e.code, e.reason);

  return ws;
}
