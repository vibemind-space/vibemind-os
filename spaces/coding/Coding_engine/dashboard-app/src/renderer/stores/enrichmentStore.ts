import { create } from 'zustand'

// ── Types ────────────────────────────────────────────────────────────────

export interface EnrichmentStats {
  total_tasks: number
  tasks_with_requirements: number
  tasks_with_user_stories: number
  tasks_with_diagrams: number
  tasks_with_warnings: number
  tasks_with_dtos: number
  tasks_with_success_criteria: number
  tasks_with_test_scenarios: number
  tasks_with_component_specs: number
  tasks_with_screen_specs: number
  tasks_with_accessibility: number
  tasks_with_routes: number
  tasks_with_design_tokens: number
}

export interface EnrichmentOverview {
  epic_id: string
  epic_name: string
  enrichment_timestamp: string | null
  stats: EnrichmentStats
  task_type_distribution: Record<string, number>
  enrichment_coverage: Record<string, number>
}

export interface EnrichedTaskSummary {
  id: string
  epic_id: string
  type: string
  title: string
  status: string
  has_requirements: boolean
  has_user_stories: boolean
  has_diagrams: boolean
  has_warnings: boolean
  has_dtos: boolean
  has_success_criteria: boolean
  has_test_scenarios: boolean
  has_component_spec: boolean
  has_screen_spec: boolean
  has_accessibility: boolean
  has_design_tokens: boolean
  enrichment_score: number
}

export interface EnrichedTaskDetail {
  id: string
  epic_id: string
  type: string
  title: string
  description: string
  status: string
  dependencies: string[]
  related_requirements: string[]
  related_user_stories: string[]
  success_criteria: string | null
  enrichment_context: Record<string, unknown> | null
}

export interface SchemaOverview {
  project_name: string | null
  language: string | null
  requirement_id_pattern: string | null
  source_count: number
  sources: Record<string, unknown>
  schema_hash: string | null
}

export interface MappingOverview {
  llm_used: boolean
  total_mappings: number
  tasks_with_types: number
  tasks_with_requirements: number
  tasks_with_stories: number
  type_distribution: Record<string, number>
}

// Coverage dimension metadata for UI
export const COVERAGE_META: Record<string, { label: string; icon: string; color: string }> = {
  requirements: { label: 'Requirements', icon: '📋', color: 'bg-blue-500' },
  user_stories: { label: 'User Stories', icon: '👤', color: 'bg-purple-500' },
  diagrams: { label: 'Diagrams', icon: '📊', color: 'bg-cyan-500' },
  dtos: { label: 'DTOs', icon: '📦', color: 'bg-green-500' },
  success_criteria: { label: 'Success Criteria', icon: '✅', color: 'bg-emerald-500' },
  test_scenarios: { label: 'Test Scenarios', icon: '🧪', color: 'bg-yellow-500' },
  component_specs: { label: 'Component Specs', icon: '🧩', color: 'bg-orange-500' },
  screen_specs: { label: 'Screen Specs', icon: '🖥️', color: 'bg-pink-500' },
  accessibility: { label: 'Accessibility', icon: '♿', color: 'bg-indigo-500' },
  design_tokens: { label: 'Design Tokens', icon: '🎨', color: 'bg-rose-500' },
  warnings: { label: 'Warnings', icon: '⚠️', color: 'bg-amber-500' },
}

interface EnrichmentState {
  // Data
  overview: EnrichmentOverview | null
  tasks: EnrichedTaskSummary[]
  selectedTask: EnrichedTaskDetail | null
  schema: SchemaOverview | null
  mapping: MappingOverview | null

  // UI State
  isLoading: boolean
  error: string | null
  activeEpicId: string | null
  projectPath: string | null
  filterType: string | null

  // Actions
  setProjectPath: (path: string) => void
  fetchOverview: (epicId: string) => Promise<void>
  fetchTasks: (epicId: string, taskType?: string) => Promise<void>
  fetchTaskDetail: (epicId: string, taskId: string) => Promise<void>
  fetchSchema: () => Promise<void>
  fetchMapping: () => Promise<void>
  setFilterType: (type: string | null) => void
  clearSelection: () => void
}

const API_BASE = ''

export const useEnrichmentStore = create<EnrichmentState>((set, get) => ({
  overview: null,
  tasks: [],
  selectedTask: null,
  schema: null,
  mapping: null,
  isLoading: false,
  error: null,
  activeEpicId: null,
  projectPath: null,
  filterType: null,

  setProjectPath: (path: string) => {
    set({ projectPath: path, overview: null, tasks: [], selectedTask: null, schema: null, mapping: null })
  },

  fetchOverview: async (epicId: string) => {
    const { projectPath } = get()
    if (!projectPath) {
      set({ error: 'No project path set' })
      return
    }
    set({ isLoading: true, error: null, activeEpicId: epicId })
    try {
      const params = new URLSearchParams({ project_path: projectPath })
      const response = await fetch(`${API_BASE}/api/v1/enrichment/overview/${epicId}?${params}`)
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
        throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
      }
      const data: EnrichmentOverview = await response.json()
      set({ overview: data, isLoading: false })
    } catch (error) {
      set({ isLoading: false, error: String(error) })
    }
  },

  fetchTasks: async (epicId: string, taskType?: string) => {
    const { projectPath } = get()
    if (!projectPath) return
    set({ isLoading: true, error: null })
    try {
      const params = new URLSearchParams({ project_path: projectPath })
      if (taskType) params.set('task_type', taskType)
      const response = await fetch(`${API_BASE}/api/v1/enrichment/tasks/${epicId}?${params}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const data: EnrichedTaskSummary[] = await response.json()
      set({ tasks: data, isLoading: false })
    } catch (error) {
      set({ isLoading: false, error: String(error) })
    }
  },

  fetchTaskDetail: async (epicId: string, taskId: string) => {
    const { projectPath } = get()
    if (!projectPath) return
    set({ isLoading: true, error: null })
    try {
      const params = new URLSearchParams({ project_path: projectPath })
      const response = await fetch(`${API_BASE}/api/v1/enrichment/task/${epicId}/${taskId}?${params}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const data: EnrichedTaskDetail = await response.json()
      set({ selectedTask: data, isLoading: false })
    } catch (error) {
      set({ isLoading: false, error: String(error) })
    }
  },

  fetchSchema: async () => {
    const { projectPath } = get()
    if (!projectPath) return
    try {
      const params = new URLSearchParams({ project_path: projectPath })
      const response = await fetch(`${API_BASE}/api/v1/enrichment/schema?${params}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data: SchemaOverview = await response.json()
      set({ schema: data })
    } catch (error) {
      set({ error: String(error) })
    }
  },

  fetchMapping: async () => {
    const { projectPath } = get()
    if (!projectPath) return
    try {
      const params = new URLSearchParams({ project_path: projectPath })
      const response = await fetch(`${API_BASE}/api/v1/enrichment/mapping?${params}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data: MappingOverview = await response.json()
      set({ mapping: data })
    } catch (error) {
      set({ error: String(error) })
    }
  },

  setFilterType: (type: string | null) => {
    const { activeEpicId } = get()
    set({ filterType: type })
    if (activeEpicId) {
      get().fetchTasks(activeEpicId, type || undefined)
    }
  },

  clearSelection: () => {
    set({ selectedTask: null })
  },
}))
