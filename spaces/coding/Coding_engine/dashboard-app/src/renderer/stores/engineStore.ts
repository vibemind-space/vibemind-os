import { create } from 'zustand'
import { useProjectStore } from './projectStore'
import type { QueuedClarification } from '../api/clarificationAPI'

interface EngineEvent {
  type: string
  data: any
  timestamp: string
}

interface AgentActivityItem {
  agent: string
  action: string
  timestamp: string
  status: 'running' | 'completed' | 'failed'
}

export interface TaskChunk {
  chunk_id: string
  requirements: string[]
  service_group: string
  complexity: 'simple' | 'medium' | 'complex'
  status: 'pending' | 'running' | 'completed' | 'failed'
  wave_id: number | null
  estimated_minutes: number
  error_message: string | null
}

export interface TaskProgress {
  completed: number
  running: number
  failed: number
  pending: number
  total: number
  percent_complete: number
}

// Epic types for task list management
export interface Epic {
  id: string
  name: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress_percent: number
  user_stories: string[]
  requirements: string[]
  entities: string[]
  api_endpoints: string[]
  last_run_at: string | null
  run_count: number
}

export interface EpicTask {
  id: string
  epic_id: string
  type: 'schema' | 'api' | 'frontend' | 'test' | 'integration'
  title: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  dependencies: string[]
  estimated_minutes: number
  actual_minutes: number | null
  error_message: string | null
  output_files: string[]
  related_requirements: string[]
  related_user_stories: string[]
  tested: boolean
  user_fix_instructions: string | null
}

export interface EpicTaskList {
  epic_id: string
  epic_name: string
  tasks: EpicTask[]
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  progress_percent: number
  run_count: number
  last_run_at: string | null
  created_at: string
  estimated_total_minutes: number
}

// Toast notification for task failures / success
export interface Toast {
  id: string
  type: 'error' | 'success' | 'warning'
  title: string
  message: string
  taskId?: string
  epicId?: string
  timestamp: number
}

// Project profile detected by SoM bridge (universal tech stack info)
export interface ProjectProfile {
  project_type: string
  technologies: string[]
  platforms: string[]
  primary_language: string
  has_backend: boolean
  has_frontend: boolean
  has_database: boolean
  complexity: string
}

interface EngineState {
  // Engine status
  engineRunning: boolean
  engineServices: string[]

  // WebSocket
  wsConnected: boolean
  wsEvents: EngineEvent[]

  // Generation progress
  generationProgress: number
  generationPhase: string
  agentActivity: AgentActivityItem[]
  logs: string[]

  // Task visibility (chunk-level progress)
  taskChunks: TaskChunk[]
  taskProgress: TaskProgress

  // Clarifications linked to tasks (via WebSocket)
  taskClarifications: QueuedClarification[]

  // Epic-based task management
  epics: Epic[]
  selectedEpic: string | null
  epicTaskLists: Record<string, EpicTaskList>
  loadEpicsLoading: boolean
  currentProjectPath: string | null

  // SoM Bridge: VNC preview + project profile
  vncUrl: string | null
  vncPort: number | null
  projectProfile: ProjectProfile | null

  // Toast notifications
  toasts: Toast[]

  // API URL
  apiUrl: string

  // Actions
  checkEngineStatus: () => Promise<void>
  startEngine: () => Promise<boolean>
  stopEngine: () => Promise<boolean>
  connectWebSocket: () => void
  disconnectWebSocket: () => void
  addEvent: (event: EngineEvent) => void
  clearEvents: () => void

  // Epic actions
  loadEpics: (projectPath: string) => Promise<void>
  selectEpic: (epicId: string | null) => void
  loadEpicTasks: (epicId: string) => Promise<void>
  runEpic: (epicId: string) => Promise<void>
  rerunEpic: (epicId: string) => Promise<void>
  rerunTask: (epicId: string, taskId: string, fixInstructions?: string) => Promise<void>
  generateAllTaskLists: () => Promise<void>
  updateEpicStatus: (epicId: string, status: Epic['status'], progress?: number) => void
  updateEpicTaskStatus: (epicId: string, taskId: string, status: EpicTask['status'], error?: string) => void

  // Toast actions
  addToast: (toast: Omit<Toast, 'id' | 'timestamp'>) => void
  removeToast: (id: string) => void
}

let ws: WebSocket | null = null

export const useEngineStore = create<EngineState>((set, get) => ({
  // Initial state
  engineRunning: false,
  engineServices: [],
  wsConnected: false,
  wsEvents: [],
  generationProgress: 0,
  generationPhase: 'idle',
  agentActivity: [],
  logs: [],
  taskChunks: [],
  taskProgress: { completed: 0, running: 0, failed: 0, pending: 0, total: 0, percent_complete: 0 },
  taskClarifications: [],
  epics: [],
  selectedEpic: null,
  epicTaskLists: {},
  loadEpicsLoading: false,
  currentProjectPath: null,
  vncUrl: null,
  vncPort: null,
  projectProfile: null,
  toasts: [],
  apiUrl: 'http://localhost:8000',

  // Check engine status via IPC
  checkEngineStatus: async () => {
    try {
      const status = await window.electronAPI.docker.getEngineStatus()
      set({
        engineRunning: status.running,
        engineServices: status.services
      })
    } catch (error) {
      console.error('Failed to check engine status:', error)
    }
  },

  // Start engine
  startEngine: async () => {
    try {
      const result = await window.electronAPI.docker.startEngine()
      if (result.success) {
        set({ engineRunning: true })
        // Reconnect WebSocket after engine starts
        setTimeout(() => get().connectWebSocket(), 2000)
      }
      return result.success
    } catch (error) {
      console.error('Failed to start engine:', error)
      return false
    }
  },

  // Stop engine
  stopEngine: async () => {
    try {
      get().disconnectWebSocket()
      const result = await window.electronAPI.docker.stopEngine()
      if (result.success) {
        set({ engineRunning: false, engineServices: [] })
      }
      return result.success
    } catch (error) {
      console.error('Failed to stop engine:', error)
      return false
    }
  },

  // Connect to Engine WebSocket
  connectWebSocket: () => {
    const { wsConnected, apiUrl } = get()

    if (wsConnected || ws) return

    try {
      // Convert HTTP URL to WebSocket URL
      // apiUrl is like 'http://localhost:8000', convert to 'ws://localhost:8000/api/v1/ws'
      const wsUrl = apiUrl.replace(/^http/, 'ws') + '/api/v1/ws'
      console.log('Connecting to WebSocket:', wsUrl)
      ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('WebSocket connected')
        set({ wsConnected: true })
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          get().addEvent({
            type: data.type,
            data: data.data,
            timestamp: data.timestamp || new Date().toISOString()
          })

          // Handle specific event types
          if (data.type === 'CONVERGENCE_UPDATE') {
            set({
              generationProgress: data.data?.progress || 0,
              generationPhase: data.data?.phase || 'unknown'
            })
          } else if (data.type === 'AGENT_STATUS') {
            const activity = get().agentActivity
            const newEntry = {
              agent: data.data?.agent || data.data?.source || 'Unknown',
              action: data.data?.action || data.data?.message || '',
              timestamp: data.timestamp || new Date().toISOString(),
              status: (data.data?.status as 'running' | 'completed' | 'failed') || 'running',
            }
            set({
              agentActivity: [...activity.slice(-49), newEntry]
            })
          } else if (data.type === 'REVIEW_PAUSED' || data.type === 'review_paused') {
            // Update project status to paused
            const projectId = data.data?.project_id
            if (projectId) {
              useProjectStore.getState().updateProject(projectId, {
                status: 'paused',
                reviewPaused: true
              })
            }
            console.log('[WebSocket] Generation paused for review:', projectId)
          } else if (data.type === 'REVIEW_RESUMED' || data.type === 'review_resumed') {
            // Update project status back to generating
            const projectId = data.data?.project_id
            if (projectId) {
              useProjectStore.getState().updateProject(projectId, {
                status: 'generating',
                reviewPaused: false
              })
            }
            console.log('[WebSocket] Generation resumed:', projectId)
          }

          // Handle VNC preview ready from SoM bridge
          if (data.type === 'vnc_preview_ready') {
            const payload = data.data || data
            set({
              vncUrl: payload.url || null,
              vncPort: payload.port || null,
              projectProfile: payload.project_profile || null,
            })
            console.log('[WebSocket] VNC preview ready:', payload.url, 'profile:', payload.project_profile?.project_type)
          }

          // Handle task progress updates (forwarded by WebSocketBridge)
          const eventType = data.data?.event_type || data.data?.type || data.type
          if (eventType === 'task_progress_update') {
            const payload = data.data?.data || data.data
            if (payload?.type === 'plan_created' && payload.plan?.chunks) {
              set({
                taskChunks: payload.plan.chunks.map((c: any) => ({
                  chunk_id: c.chunk_id || c.id || '',
                  requirements: c.requirements || [],
                  service_group: c.service_group || '',
                  complexity: c.complexity || 'medium',
                  status: c.status || 'pending',
                  wave_id: c.wave_id ?? null,
                  estimated_minutes: c.estimated_minutes || 0,
                  error_message: c.error_message || null,
                })),
                taskProgress: payload.progress || { completed: 0, running: 0, failed: 0, pending: 0, total: 0, percent_complete: 0 },
              })
            } else if (payload?.type === 'batch_started' && payload.slice_ids) {
              set((state) => ({
                taskChunks: state.taskChunks.map((c) =>
                  payload.slice_ids.includes(c.chunk_id)
                    ? { ...c, status: 'running' as const }
                    : c
                ),
              }))
            } else if (payload?.type === 'batch_completed') {
              set((state) => ({
                taskChunks: state.taskChunks.map((c) => {
                  if (payload.completed_slices?.includes(c.chunk_id)) return { ...c, status: 'completed' as const }
                  if (payload.failed_slices?.includes(c.chunk_id)) return { ...c, status: 'failed' as const }
                  return c
                }),
              }))
            } else if (payload?.type === 'task_status_changed') {
              // Handle individual task status changes from Epic Orchestrator
              const { epic_id, task_id, status, error, tested } = payload
              if (epic_id && task_id && status) {
                get().updateEpicTaskStatus(epic_id, task_id, status, error)

                // Update tested flag if present
                if (tested !== undefined) {
                  set((state) => {
                    const taskList = state.epicTaskLists[epic_id]
                    if (!taskList) return state
                    return {
                      epicTaskLists: {
                        ...state.epicTaskLists,
                        [epic_id]: {
                          ...taskList,
                          tasks: taskList.tasks.map((t) =>
                            t.id === task_id ? { ...t, tested: !!tested } : t
                          ),
                        },
                      },
                    }
                  })
                }

                // Toast on failure
                if (status === 'failed') {
                  const taskList = get().epicTaskLists[epic_id]
                  const task = taskList?.tasks.find((t) => t.id === task_id)
                  get().addToast({
                    type: 'error',
                    title: `Task Failed: ${task?.title || task_id}`,
                    message: error || 'Task execution failed',
                    taskId: task_id,
                    epicId: epic_id,
                  })
                }
              }
            } else if (payload?.type === 'epic_status_changed') {
              // Handle epic-level status changes
              const { epic_id, status, progress } = payload
              if (epic_id && status) {
                get().updateEpicStatus(epic_id, status, progress)
                // Update generation progress from epic progress
                if (typeof progress === 'number') {
                  set({ generationProgress: progress })
                }
                // Map epic status to generation phase
                if (status === 'running') {
                  set({ generationPhase: 'Generating Code' })
                } else if (status === 'completed') {
                  set({ generationProgress: 100, generationPhase: 'Complete' })
                  // Mark project as completed
                  useProjectStore.getState().projects.forEach((p) => {
                    if (p.status === 'generating') {
                      useProjectStore.getState().updateProject(p.id, { status: 'running', progress: 100 })
                    }
                  })
                } else if (status === 'failed') {
                  set({ generationPhase: 'Failed' })
                }
              }
            } else if (payload?.type === 'pipeline_progress') {
              // Real-time pipeline progress from Epic Orchestrator
              const { completed, failed, total, running_ids, skipped } = payload
              const pctComplete = total > 0 ? Math.round((completed / total) * 100) : 0
              set({
                generationProgress: pctComplete,
                generationPhase: `Generating Code (${completed}/${total} tasks)`,
                taskProgress: {
                  completed: completed || 0,
                  running: running_ids?.length || 0,
                  failed: failed || 0,
                  pending: Math.max(0, (total || 0) - (completed || 0) - (failed || 0) - (skipped || 0) - (running_ids?.length || 0)),
                  total: total || 0,
                  percent_complete: pctComplete,
                },
              })
            } else if (payload?.type === 'epic_execution_started') {
              // Epic started generating
              set({
                generationProgress: 1,
                generationPhase: `Starting Epic: ${payload.epic_id} (${payload.total_tasks} tasks)`,
              })
            } else if (payload?.type === 'epic_execution_completed') {
              // Epic finished
              const result = payload.result || {}
              const pct = result.success ? 100 : get().generationProgress
              set({
                generationProgress: pct,
                generationPhase: result.success ? 'Complete' : `Done (${result.failed_tasks || 0} failures)`,
              })
              // Update project status
              useProjectStore.getState().projects.forEach((p) => {
                if (p.status === 'generating') {
                  useProjectStore.getState().updateProject(p.id, {
                    status: result.success ? 'running' : 'error',
                    progress: pct,
                  })
                }
              })
            } else if (payload?.type === 'log_entry') {
              // Log line from engine (forwarded via EventBus → WebSocket)
              const logMsg = payload.message || ''
              if (logMsg) {
                set((state) => ({
                  logs: [...state.logs.slice(-999), logMsg]
                }))
              }
            }
            // Recalculate progress from chunks
            const chunks = get().taskChunks
            if (chunks.length > 0) {
              const completed = chunks.filter((c) => c.status === 'completed').length
              set({
                taskProgress: {
                  completed,
                  running: chunks.filter((c) => c.status === 'running').length,
                  failed: chunks.filter((c) => c.status === 'failed').length,
                  pending: chunks.filter((c) => c.status === 'pending').length,
                  total: chunks.length,
                  percent_complete: (completed / chunks.length) * 100,
                },
              })
            }
          }

          // Handle clarification events linked to tasks
          if (eventType === 'clarification_requested') {
            const payload = data.data?.data || data.data
            if (payload?.action === 'enqueued' && payload.clarification) {
              set((state) => ({
                taskClarifications: [...state.taskClarifications, payload.clarification],
              }))
            }
          }
          if (eventType === 'clarification_choice_submitted') {
            const payload = data.data?.data || data.data
            if (payload?.action === 'resolved' && payload.clarification_id) {
              set((state) => ({
                taskClarifications: state.taskClarifications.filter(
                  (c) => c.id !== payload.clarification_id
                ),
              }))
            }
          }
          if (eventType === 'clarification_timeout') {
            const payload = data.data?.data || data.data
            if (payload?.clarification_id) {
              set((state) => ({
                taskClarifications: state.taskClarifications.filter(
                  (c) => c.id !== payload.clarification_id
                ),
              }))
            }
          }

          // Handle checkpoint events from Epic Orchestrator
          if (data.type === 'CHECKPOINT_REACHED' || eventType === 'CHECKPOINT_REACHED') {
            const payload = data.data || data
            console.log('[WebSocket] Checkpoint reached:', payload)
            // Could set a currentCheckpoint state here for a checkpoint modal
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        set({ wsConnected: false })
        ws = null

        // Attempt reconnect if engine is running
        if (get().engineRunning) {
          setTimeout(() => get().connectWebSocket(), 5000)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }
    } catch (error) {
      console.error('Failed to connect WebSocket:', error)
    }
  },

  // Disconnect WebSocket
  disconnectWebSocket: () => {
    if (ws) {
      ws.close()
      ws = null
    }
    set({ wsConnected: false })
  },

  // Add event to history
  addEvent: (event) => {
    set((state) => ({
      wsEvents: [...state.wsEvents.slice(-99), event]
    }))
  },

  // Clear events
  clearEvents: () => {
    set({ wsEvents: [] })
  },

  // Load epics from project
  loadEpics: async (projectPath: string) => {
    console.log(`[EngineStore:loadEpics] Called with projectPath=${projectPath}`)
    // Don't set currentProjectPath until we have actual data — prevents skipping retries on failure
    set({ loadEpicsLoading: true })
    try {
      let epics: any[] = []

      // Try via IPC first (Electron)
      const hasIPC = !!window.electronAPI?.engine?.getEpics
      console.log(`[EngineStore:loadEpics] IPC available=${hasIPC}`)
      if (hasIPC) {
        const result = await window.electronAPI.engine.getEpics(projectPath)
        console.log(`[EngineStore:loadEpics] IPC result:`, {
          epicCount: result?.epics?.length ?? 0,
          keys: result ? Object.keys(result) : 'null',
          totalEpics: result?.total_epics ?? 'N/A'
        })
        if (result?.epics?.length > 0) {
          epics = result.epics
        }
      }

      // Fallback to direct API if IPC returned no epics
      if (epics.length === 0) {
        const { apiUrl } = get()
        console.log(`[EngineStore:loadEpics] Trying direct API: ${apiUrl}/api/v1/dashboard/epics`)
        const response = await fetch(`${apiUrl}/api/v1/dashboard/epics?project_path=${encodeURIComponent(projectPath)}`)
        if (response.ok) {
          const data = await response.json()
          console.log(`[EngineStore:loadEpics] API result: ${data.epics?.length ?? 0} epics`)
          epics = data.epics || []
        } else {
          console.warn(`[EngineStore:loadEpics] API returned HTTP ${response.status}`)
        }
      }

      // Only mark path as loaded if we actually got epics
      if (epics.length > 0) {
        set({ epics, currentProjectPath: projectPath, loadEpicsLoading: false })
        console.log(`[EngineStore:loadEpics] ✓ Loaded ${epics.length} epics, set currentProjectPath`)
      } else {
        // Don't set currentProjectPath so retries are allowed
        set({ epics: [], loadEpicsLoading: false })
        console.warn(`[EngineStore:loadEpics] ✗ No epics found for ${projectPath} (will retry on next trigger)`)
      }
    } catch (error) {
      console.error('[EngineStore:loadEpics] Failed:', error)
      set({ loadEpicsLoading: false })
    }
  },

  // Select an epic
  selectEpic: (epicId: string | null) => {
    set({ selectedEpic: epicId })

    // Load tasks for selected epic if not already loaded
    if (epicId && !get().epicTaskLists[epicId]) {
      get().loadEpicTasks(epicId)
    }
  },

  // Load tasks for a specific epic
  loadEpicTasks: async (epicId: string) => {
    const { currentProjectPath, apiUrl } = get()
    if (!currentProjectPath) return

    try {
      // Try via IPC first
      if (window.electronAPI?.engine?.getEpicTasks) {
        const result = await window.electronAPI.engine.getEpicTasks(epicId, currentProjectPath)
        if (result.tasks) {
          set((state) => ({
            epicTaskLists: {
              ...state.epicTaskLists,
              [epicId]: result,
            },
          }))
          return
        }
      }

      // Fallback to API
      const response = await fetch(
        `${apiUrl}/api/v1/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(currentProjectPath)}`
      )
      if (response.ok) {
        const data = await response.json()
        set((state) => ({
          epicTaskLists: {
            ...state.epicTaskLists,
            [epicId]: data,
          },
        }))
      }
    } catch (error) {
      console.error(`Failed to load tasks for ${epicId}:`, error)
    }
  },

  // Run an epic
  runEpic: async (epicId: string) => {
    const { currentProjectPath, apiUrl } = get()
    if (!currentProjectPath) return

    // Update status immediately
    get().updateEpicStatus(epicId, 'running', 0)

    try {
      // Try via IPC first
      if (window.electronAPI?.engine?.runEpic) {
        await window.electronAPI.engine.runEpic(epicId, currentProjectPath)
        return
      }

      // Fallback to API
      await fetch(`${apiUrl}/api/v1/dashboard/epic/${epicId}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: currentProjectPath }),
      })
    } catch (error) {
      console.error(`Failed to run ${epicId}:`, error)
      get().updateEpicStatus(epicId, 'failed', 0)
    }
  },

  // Rerun an epic (reset all tasks and run again)
  rerunEpic: async (epicId: string) => {
    const { currentProjectPath, apiUrl } = get()
    if (!currentProjectPath) return

    // Update status immediately
    get().updateEpicStatus(epicId, 'running', 0)

    // Reset task list progress
    set((state) => {
      const taskList = state.epicTaskLists[epicId]
      if (taskList) {
        const resetTasks = taskList.tasks.map((t) => ({
          ...t,
          status: 'pending' as const,
          actual_minutes: null,
          error_message: null,
        }))
        return {
          epicTaskLists: {
            ...state.epicTaskLists,
            [epicId]: {
              ...taskList,
              tasks: resetTasks,
              completed_tasks: 0,
              failed_tasks: 0,
              progress_percent: 0,
              run_count: taskList.run_count + 1,
              last_run_at: new Date().toISOString(),
            },
          },
        }
      }
      return state
    })

    try {
      // Try via IPC first
      if (window.electronAPI?.engine?.rerunEpic) {
        await window.electronAPI.engine.rerunEpic(epicId, currentProjectPath)
        return
      }

      // Fallback to API
      await fetch(`${apiUrl}/api/v1/dashboard/epic/${epicId}/rerun`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: currentProjectPath }),
      })
    } catch (error) {
      console.error(`Failed to rerun ${epicId}:`, error)
      get().updateEpicStatus(epicId, 'failed', 0)
    }
  },

  // Generate all task lists
  generateAllTaskLists: async () => {
    const { epics, currentProjectPath, apiUrl } = get()
    if (!currentProjectPath) return

    set({ loadEpicsLoading: true })

    try {
      // Try via IPC first
      if (window.electronAPI?.engine?.generateTaskLists) {
        await window.electronAPI.engine.generateTaskLists(currentProjectPath)
        // Reload epics to get updated task lists
        await get().loadEpics(currentProjectPath)
        return
      }

      // Fallback to API
      await fetch(`${apiUrl}/api/v1/dashboard/generate-task-lists`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: currentProjectPath }),
      })

      // Reload epics
      await get().loadEpics(currentProjectPath)
    } catch (error) {
      console.error('Failed to generate task lists:', error)
    } finally {
      set({ loadEpicsLoading: false })
    }
  },

  // Update epic status (called from WebSocket events)
  updateEpicStatus: (epicId: string, status: Epic['status'], progress?: number) => {
    set((state) => ({
      epics: state.epics.map((e) =>
        e.id === epicId
          ? {
              ...e,
              status,
              progress_percent: progress !== undefined ? progress : e.progress_percent,
              last_run_at: status === 'running' ? new Date().toISOString() : e.last_run_at,
              run_count: status === 'running' ? e.run_count + 1 : e.run_count,
            }
          : e
      ),
    }))
  },

  // Rerun a single task (with optional fix instructions)
  rerunTask: async (epicId: string, taskId: string, fixInstructions?: string) => {
    const { currentProjectPath } = get()
    if (!currentProjectPath) return

    // Optimistically mark task as running
    get().updateEpicTaskStatus(epicId, taskId, 'running')

    try {
      if (window.electronAPI?.engine?.rerunTask) {
        const result = await window.electronAPI.engine.rerunTask(
          epicId, taskId, currentProjectPath, fixInstructions
        )
        if (!result.success) {
          get().updateEpicTaskStatus(epicId, taskId, 'failed', result.error)
          get().addToast({
            type: 'error',
            title: 'Rerun Failed',
            message: result.error || 'Failed to rerun task',
            taskId,
            epicId,
          })
        }
        return
      }

      // Fallback to API
      const { apiUrl } = get()
      const response = await fetch(
        `${apiUrl}/api/v1/dashboard/epic/${epicId}/task/${taskId}/rerun`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_path: currentProjectPath,
            fix_instructions: fixInstructions || null,
          }),
        }
      )
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Rerun request failed')
      }
    } catch (error: any) {
      console.error(`Failed to rerun task ${taskId}:`, error)
      get().updateEpicTaskStatus(epicId, taskId, 'failed', error.message)
      get().addToast({
        type: 'error',
        title: 'Rerun Failed',
        message: error.message || 'Failed to rerun task',
        taskId,
        epicId,
      })
    }
  },

  // Update epic task status (called from WebSocket events)
  updateEpicTaskStatus: (epicId: string, taskId: string, status: EpicTask['status'], error?: string) => {
    set((state) => {
      const taskList = state.epicTaskLists[epicId]
      if (!taskList) return state

      const updatedTasks = taskList.tasks.map((t) =>
        t.id === taskId ? { ...t, status, error_message: error || null } : t
      )

      const completed = updatedTasks.filter((t) => t.status === 'completed').length
      const failed = updatedTasks.filter((t) => t.status === 'failed').length
      const total = updatedTasks.length

      return {
        epicTaskLists: {
          ...state.epicTaskLists,
          [epicId]: {
            ...taskList,
            tasks: updatedTasks,
            completed_tasks: completed,
            failed_tasks: failed,
            progress_percent: total > 0 ? (completed / total) * 100 : 0,
          },
        },
        // Also update epic progress
        epics: state.epics.map((e) =>
          e.id === epicId
            ? {
                ...e,
                progress_percent: total > 0 ? (completed / total) * 100 : 0,
                status:
                  completed === total
                    ? 'completed'
                    : failed > 0 && completed + failed === total
                    ? 'failed'
                    : e.status,
              }
            : e
        ),
      }
    })
  },

  // Add a toast notification (max 3, auto-dismiss after 8s)
  addToast: (toast) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const newToast: Toast = { ...toast, id, timestamp: Date.now() }
    set((state) => ({
      toasts: [...state.toasts.slice(-2), newToast],
    }))
    // Auto-dismiss after 8 seconds
    setTimeout(() => {
      get().removeToast(id)
    }, 8000)
  },

  // Remove a toast by id
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }))
  },
}))
