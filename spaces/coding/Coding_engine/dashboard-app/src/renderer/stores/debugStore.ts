/**
 * Debug Store - Zustand store for debug session management.
 *
 * Tracks user interactions (clicks on VNC preview), browser errors,
 * docker logs, and generates fix tasks from the recorded session.
 */

import { create } from 'zustand'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DebugInteraction {
  id: string
  timestamp: number
  type: 'click' | 'error' | 'log'
  // Click data
  x?: number
  y?: number
  screenshotUrl?: string
  componentInfo?: string
  // Error data
  errorType?: string
  errorMessage?: string
  sourceFile?: string
  lineNumber?: number
  // Log data
  logSource?: 'browser' | 'docker'
  logContent?: string
}

export interface DebugFixTask {
  id: string
  title: string
  description: string
  errorType: string
  affectedFiles: string[]
  suggestedFix: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  sourceInteractions: string[]
}

interface DebugState {
  // Session
  sessionId: string | null
  recording: boolean
  startedAt: number | null
  interactions: DebugInteraction[]
  fixTasks: DebugFixTask[]
  analyzing: boolean
  // Project context
  projectId: string | null
  outputDir: string | null
}

interface DebugActions {
  startSession: (projectId: string, outputDir: string) => void
  stopSession: () => void
  addInteraction: (interaction: Omit<DebugInteraction, 'id' | 'timestamp'>) => void
  analyzeAndCreateTasks: () => Promise<void>
  clearSession: () => void
  pollBrowserErrors: () => Promise<void>
  pollDockerLogs: (projectId: string) => Promise<void>
}

type DebugStore = DebugState & DebugActions

// ─── Store ────────────────────────────────────────────────────────────────────

export const useDebugStore = create<DebugStore>((set, get) => ({
  // State
  sessionId: null,
  recording: false,
  startedAt: null,
  interactions: [],
  fixTasks: [],
  analyzing: false,
  projectId: null,
  outputDir: null,

  // Actions
  startSession: (projectId: string, outputDir: string) => {
    set({
      sessionId: crypto.randomUUID(),
      recording: true,
      startedAt: Date.now(),
      interactions: [],
      fixTasks: [],
      analyzing: false,
      projectId,
      outputDir,
    })
    console.log('[DebugStore] Session started for', projectId)
  },

  stopSession: () => {
    set({ recording: false })
    console.log('[DebugStore] Session stopped,', get().interactions.length, 'interactions recorded')
  },

  addInteraction: (partial) => {
    const interaction: DebugInteraction = {
      ...partial,
      id: crypto.randomUUID(),
      timestamp: Date.now(),
    }
    set((state) => ({
      interactions: [...state.interactions, interaction],
    }))
  },

  analyzeAndCreateTasks: async () => {
    const { interactions, projectId, outputDir } = get()
    if (!projectId || !outputDir || interactions.length === 0) return

    set({ analyzing: true })

    try {
      const api = (window as any).electronAPI
      const apiUrl = await api?.engine?.getApiUrl?.() || 'http://localhost:8000'

      const response = await fetch(`${apiUrl}/api/v1/dashboard/debug/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          output_dir: outputDir,
          interactions: interactions.map((i) => ({
            type: i.type,
            timestamp: i.timestamp,
            x: i.x,
            y: i.y,
            errorType: i.errorType,
            errorMessage: i.errorMessage,
            sourceFile: i.sourceFile,
            lineNumber: i.lineNumber,
            logSource: i.logSource,
            logContent: i.logContent,
            componentInfo: i.componentInfo,
          })),
        }),
      })

      if (response.ok) {
        const data = await response.json()
        set({ fixTasks: data.fix_tasks || [] })
        console.log('[DebugStore] Analysis complete,', (data.fix_tasks || []).length, 'fix tasks')
      } else {
        console.error('[DebugStore] Analysis failed:', response.statusText)
      }
    } catch (error) {
      console.error('[DebugStore] Analysis error:', error)
    } finally {
      set({ analyzing: false })
    }
  },

  clearSession: () => {
    set({
      sessionId: null,
      recording: false,
      startedAt: null,
      interactions: [],
      fixTasks: [],
      analyzing: false,
      projectId: null,
      outputDir: null,
    })
  },

  pollBrowserErrors: async () => {
    if (!get().recording) return

    try {
      const api = (window as any).electronAPI
      if (!api?.debug?.getBrowserErrors) return

      const errors = await api.debug.getBrowserErrors()
      if (!Array.isArray(errors) || errors.length === 0) return

      // Deduplicate: only add errors we haven't seen
      const existing = new Set(
        get()
          .interactions.filter((i) => i.type === 'error')
          .map((i) => i.errorMessage)
      )

      for (const err of errors) {
        const msg = err.message || err.errorMessage || String(err)
        if (existing.has(msg)) continue
        existing.add(msg)

        get().addInteraction({
          type: 'error',
          errorType: err.type || err.error_type || 'runtime_error',
          errorMessage: msg,
          sourceFile: err.filename || err.source_file,
          lineNumber: err.lineno || err.line_number,
          logSource: 'browser',
        })
      }
    } catch (error) {
      // Silently ignore - error server may not be running
    }
  },

  pollDockerLogs: async (projectId: string) => {
    if (!get().recording) return

    try {
      const api = (window as any).electronAPI
      if (!api?.debug?.getDockerLogs) return

      const logs = await api.debug.getDockerLogs(projectId, 50)
      if (!logs || typeof logs !== 'string') return

      // Extract error lines from logs
      const errorLines = logs
        .split('\n')
        .filter((line: string) => /error|ERR|FATAL|panic|exception/i.test(line))
        .slice(-5) // Last 5 error lines

      if (errorLines.length === 0) return

      // Deduplicate
      const existing = new Set(
        get()
          .interactions.filter((i) => i.type === 'log' && i.logSource === 'docker')
          .map((i) => i.logContent)
      )

      const combined = errorLines.join('\n')
      if (existing.has(combined)) return

      get().addInteraction({
        type: 'log',
        logSource: 'docker',
        logContent: combined,
        errorMessage: errorLines[0],
      })
    } catch (error) {
      // Silently ignore
    }
  },
}))
