// front/src/stores/engineStore.ts
import { create } from 'zustand';
import type { AgentInfo, EpicInfo, GenerationPhase } from '@/services/engineApi';
import { createEngineWebSocket } from '@/services/engineApi';

interface TaskProgress {
  completed: number;
  running: number;
  failed: number;
  pending: number;
  total: number;
  percent: number;
}

interface EngineState {
  // Connection
  connected: boolean;
  ws: WebSocket | null;

  // Active generation
  activeProject: string | null;
  phase: GenerationPhase;
  progressPct: number;
  agents: AgentInfo[];
  epics: EpicInfo[];

  // Extended state (from Electron dashboard)
  selectedEpicId: string | null;
  reviewPaused: boolean;
  reviewFeedback: string;
  vncPreviewUrl: string | null;
  logs: string[];
  clarifications: any[];
  taskProgress: TaskProgress;

  // Actions
  connect: () => void;
  disconnect: () => void;
  setActiveProject: (name: string | null) => void;
}

export const useEngineStore = create<EngineState>((set, get) => ({
  connected: false,
  ws: null,
  activeProject: null,
  phase: 'idle',
  progressPct: 0,
  agents: [],
  epics: [],

  // Extended state defaults
  selectedEpicId: null,
  reviewPaused: false,
  reviewFeedback: '',
  vncPreviewUrl: null,
  logs: [],
  clarifications: [],
  taskProgress: { completed: 0, running: 0, failed: 0, pending: 0, total: 0, percent: 0 },

  connect: () => {
    if (get().ws) return; // Already connected

    const connectWithRetry = () => {
      const ws = createEngineWebSocket((type, data) => {
        switch (type) {
        case 'engine:agent_status':
        case 'AGENT_STATUS':
          set((s) => {
            const agents = [...s.agents];
            const name = data.agent_name || data.name;
            const idx = agents.findIndex((a) => a.name === name);
            const agent: AgentInfo = {
              name,
              status: data.status,
              task: data.task || '',
              elapsed_seconds: data.elapsed_seconds || data.elapsed || 0,
            };
            if (idx >= 0) agents[idx] = agent;
            else agents.push(agent);
            return { agents };
          });
          break;

        case 'engine:epic_progress':
          set((s) => ({
            epics: s.epics.map((e) =>
              e.id === data.id
                ? { ...e, progress_pct: data.progress_pct, tasks_complete: data.tasks_complete }
                : e
            ),
          }));
          break;

        case 'engine:progress':
          set({ progressPct: data.progress_pct || data.percent || 0, phase: data.phase || get().phase });
          break;

        case 'engine:phase_change':
          set({ phase: data.phase });
          break;

        case 'CONVERGENCE_UPDATE':
          set({ progressPct: data.progress || data.percent || 0, phase: data.phase || get().phase });
          break;

        case 'generation_progress':
          set({
            progressPct: data.progress_pct || 0,
            phase: data.phase || 'generation',
            taskProgress: {
              completed: data.completed || 0,
              failed: data.failed || 0,
              total: data.total || 0,
              running: data.agents || 0,
              pending: (data.total || 0) - (data.completed || 0) - (data.failed || 0),
              percent: data.progress_pct || 0,
            },
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
        case 'pipeline_progress':
          set({ taskProgress: data, progressPct: data.percent || get().progressPct });
          break;

        case 'epic_status_changed':
          set((s) => ({
            epics: s.epics.map((e) => (e.id === data.epic_id ? { ...e, ...data } : e)),
          }));
          break;

        case 'log_entry':
          set((s) => ({
            logs: [...s.logs.slice(-499), data.message || data.text || JSON.stringify(data)],
          }));
          break;

        case 'clarification_requested':
          set((s) => ({ clarifications: [...s.clarifications, data] }));
          break;

        case 'engine:file_generated':
          // No-op for now, can be wired to file explorer refresh later
          break;

        default:
          break;
      }
    });

      ws.onopen = () => set({ connected: true });
      ws.onclose = (e) => {
        set({ connected: false, ws: null });
        // Auto-reconnect after 3 seconds unless manually disconnected
        if (e.code !== 1000) {
          console.log('[EngineStore] WS closed unexpectedly, reconnecting in 3s...');
          setTimeout(() => {
            if (!get().ws) {
              connectWithRetry();
            }
          }, 3000);
        }
      };

      set({ ws });
    };

    connectWithRetry();
  },

  disconnect: () => {
    const { ws } = get();
    if (ws) {
      ws.close(1000, 'Manual disconnect'); // Code 1000 prevents auto-reconnect
      set({ ws: null, connected: false });
    }
  },

  setActiveProject: (name) => set({ activeProject: name }),
}));
