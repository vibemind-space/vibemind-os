import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { OrchestratorProject } from '../api/webAPI'

// Re-export the type for consumers
export type { OrchestratorProject }

// RE (Requirements Engineer) project types
export interface REProjectSummary {
  project_id: string
  project_name: string
  project_path: string
  source: 'local_re'
  tech_stack_tags: string[]
  architecture_pattern: string
  requirements_count: number
  user_stories_count: number
  tasks_count: number
  diagram_count: number
  quality_issues: { critical: number; high: number; medium: number }
  has_api_spec: boolean
  has_master_document: boolean
}

export interface REProjectDetail extends REProjectSummary {
  tech_stack_full: Record<string, string>
  tasks_by_feature: Record<string, Array<{
    id: string
    title: string
    task_type: string
    complexity: string
    estimated_hours: number
  }>>
  quality_issues_list: Array<{
    id: string
    category: string
    severity: string
    title: string
  }>
  master_document_excerpt: string
  feature_breakdown: Array<{
    feature_id: string
    feature_name: string
    requirements: string[]
  }>
}

export interface Project {
  id: string
  name: string
  description: string
  requirementsPath: string
  outputDir: string
  status: 'idle' | 'generating' | 'paused' | 'running' | 'stopped' | 'error'
  progress: number
  vncPort?: number
  appPort?: number
  createdAt: string
  lastRunAt?: string
  error?: string
  // Review Gate state
  reviewPaused?: boolean
  reviewFeedback?: string
}

interface ProjectState {
  projects: Project[]
  activeProjectId: string | null
  previewProjectId: string | null

  // Orchestrator projects (from req-orchestrator)
  orchestratorProjects: OrchestratorProject[]
  selectedOrchestratorIds: string[]
  orchestratorLoading: boolean
  orchestratorError: string | null

  // Local RE (Requirements Engineer) projects
  reProjects: REProjectSummary[]
  reProjectsLoading: boolean
  selectedREProject: REProjectDetail | null

  // Actions
  addProject: (project: Omit<Project, 'id' | 'status' | 'progress' | 'createdAt'>) => string
  updateProject: (id: string, updates: Partial<Project>) => void
  removeProject: (id: string) => void
  setActiveProject: (id: string | null) => Promise<void>
  setPreviewProject: (id: string | null) => void
  getProject: (id: string) => Project | undefined

  // Docker actions
  startProject: (id: string) => Promise<boolean>
  stopProject: (id: string) => Promise<boolean>
  startGeneration: (id: string, forceGenerate?: boolean) => Promise<boolean>
  stopGeneration: (id: string) => Promise<boolean>
  startPreviewOnly: (id: string) => Promise<boolean>

  // Orchestrator actions
  loadFromOrchestrator: () => Promise<boolean>
  toggleOrchestratorSelection: (projectId: string) => void
  clearOrchestratorSelection: () => void
  generateFromOrchestrator: () => Promise<boolean>

  // RE project actions
  loadLocalREProjects: (paths?: string[]) => Promise<boolean>
  selectREProject: (path: string | null) => Promise<void>
  generateFromREProject: (projectPath: string) => Promise<boolean>

  // Review Gate actions
  pauseForReview: (id: string) => Promise<boolean>
  resumeWithFeedback: (id: string, feedback?: string) => Promise<boolean>
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set, get) => ({
      projects: [],
      activeProjectId: null,
      previewProjectId: null,

      // Orchestrator state
      orchestratorProjects: [],
      selectedOrchestratorIds: [],
      orchestratorLoading: false,
      orchestratorError: null,

      // RE projects state
      reProjects: [],
      reProjectsLoading: false,
      selectedREProject: null,

      addProject: (projectData) => {
        const id = crypto.randomUUID()
        const project: Project = {
          ...projectData,
          id,
          status: 'idle',
          progress: 0,
          createdAt: new Date().toISOString()
        }

        set((state) => ({
          projects: [...state.projects, project],
          activeProjectId: id
        }))

        return id
      },

      updateProject: (id, updates) => {
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === id ? { ...p, ...updates } : p
          )
        }))
      },

      removeProject: (id) => {
        const { stopProject, activeProjectId, previewProjectId } = get()

        // Stop container if running
        stopProject(id)

        set((state) => ({
          projects: state.projects.filter((p) => p.id !== id),
          activeProjectId: activeProjectId === id ? null : activeProjectId,
          previewProjectId: previewProjectId === id ? null : previewProjectId
        }))
      },

      setActiveProject: async (id) => {
        set({ activeProjectId: id })

        // Auto-start preview if project has existing code and no preview is running
        if (id) {
          const project = get().projects.find((p) => p.id === id)
          if (project?.outputDir && !get().previewProjectId) {
            try {
              const hasCode = await window.electronAPI.fs.exists(
                `${project.outputDir}/package.json`
              )
              if (hasCode) {
                console.log('[ProjectStore] Auto-starting preview for project with existing code:', id)
                get().startPreviewOnly(id)
              }
            } catch (error) {
              console.warn('[ProjectStore] Could not check for existing code:', error)
            }
          }
        }
      },

      setPreviewProject: (id) => {
        set({ previewProjectId: id })
      },

      getProject: (id) => {
        return get().projects.find((p) => p.id === id)
      },

      // Start project container for live preview
      startProject: async (id) => {
        const project = get().getProject(id)
        if (!project) return false

        try {
          set((state) => ({
            projects: state.projects.map((p) =>
              p.id === id ? { ...p, status: 'running' } : p
            )
          }))

          const result = await window.electronAPI.docker.startProject(
            id,
            project.requirementsPath,
            project.outputDir
          )

          if (result.success) {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === id
                  ? {
                      ...p,
                      vncPort: result.vncPort,
                      appPort: result.appPort,
                      status: 'running',
                      lastRunAt: new Date().toISOString()
                    }
                  : p
              ),
              previewProjectId: id
            }))
            return true
          } else {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === id
                  ? { ...p, status: 'error', error: result.error }
                  : p
              )
            }))
            return false
          }
        } catch (error: any) {
          set((state) => ({
            projects: state.projects.map((p) =>
              p.id === id
                ? { ...p, status: 'error', error: error.message }
                : p
            )
          }))
          return false
        }
      },

      // Stop project container
      stopProject: async (id) => {
        try {
          await window.electronAPI.docker.stopProject(id)

          set((state) => ({
            projects: state.projects.map((p) =>
              p.id === id
                ? { ...p, status: 'stopped', vncPort: undefined, appPort: undefined }
                : p
            ),
            previewProjectId:
              state.previewProjectId === id ? null : state.previewProjectId
          }))

          return true
        } catch (error) {
          console.error('Failed to stop project:', error)
          return false
        }
      },

      // Start code generation WITH live VNC preview
      // forceGenerate: if true, always run generation even if project files exist
      startGeneration: async (id, forceGenerate = false) => {
        const project = get().getProject(id)
        if (!project) return false

        try {
          set((state) => ({
            projects: state.projects.map((p) =>
              p.id === id ? { ...p, status: 'generating', progress: 0 } : p
            )
          }))

          // Use the new method that starts VNC container + generation
          const result = await window.electronAPI.engine.startGenerationWithPreview(
            id,
            project.requirementsPath,
            project.outputDir,
            forceGenerate
          )

          if (result.success) {
            // Update project with VNC and app ports, set as preview
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === id
                  ? {
                      ...p,
                      status: 'generating',
                      vncPort: result.vncPort,
                      appPort: result.appPort,
                      lastRunAt: new Date().toISOString()
                    }
                  : p
              ),
              // Automatically show the live preview
              previewProjectId: id
            }))
          } else {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === id
                  ? { ...p, status: 'error', error: result.error }
                  : p
              )
            }))
          }

          return result.success
        } catch (error: any) {
          set((state) => ({
            projects: state.projects.map((p) =>
              p.id === id
                ? { ...p, status: 'error', error: error.message }
                : p
            )
          }))
          return false
        }
      },

      // Stop a running generation (graceful: pauses epic orchestrator first, then kills container)
      stopGeneration: async (id) => {
        try {
          // 1. Gracefully pause any running epic orchestrator via FastAPI
          try {
            await fetch('http://localhost:8000/api/v1/dashboard/stop-generation', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ project_id: id }),
            })
          } catch (apiErr) {
            console.warn('[ProjectStore] Could not call stop-generation API (non-fatal):', apiErr)
          }

          // 2. Kill Docker container and Python process via Electron IPC
          await window.electronAPI.engine.stopGeneration(id)

          // 3. Reset generation progress in engineStore
          try {
            const { useEngineStore } = await import('./engineStore')
            useEngineStore.getState().generationProgress // trigger import
            useEngineStore.setState({
              generationPhase: 'Stopped',
            })
          } catch (_) { /* non-fatal */ }

          set((state) => ({
            projects: state.projects.map((p) =>
              p.id === id
                ? { ...p, status: 'stopped', vncPort: undefined, appPort: undefined }
                : p
            ),
            previewProjectId:
              state.previewProjectId === id ? null : state.previewProjectId
          }))

          return true
        } catch (error) {
          console.error('Failed to stop generation:', error)
          return false
        }
      },

      // Start preview only (no generation) - for projects with existing code
      startPreviewOnly: async (id) => {
        const project = get().projects.find((p) => p.id === id)
        if (!project?.outputDir) {
          console.warn('[ProjectStore] Cannot start preview: no outputDir for project', id)
          return false
        }

        try {
          console.log('[ProjectStore] Starting preview-only for:', id)

          const result = await window.electronAPI.docker.startProject(
            id,
            project.requirementsPath || project.outputDir,
            project.outputDir
          )

          if (result.success) {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === id
                  ? {
                      ...p,
                      status: 'running',
                      vncPort: result.vncPort,
                      appPort: result.appPort,
                      lastRunAt: new Date().toISOString()
                    }
                  : p
              ),
              previewProjectId: id
            }))
            console.log('[ProjectStore] Preview started on VNC port:', result.vncPort)
            return true
          } else {
            console.error('[ProjectStore] Failed to start preview:', result.error)
            return false
          }
        } catch (error: any) {
          console.error('[ProjectStore] Preview start error:', error)
          return false
        }
      },

      // ========================================================================
      // Orchestrator Actions
      // ========================================================================

      /**
       * Load projects from req-orchestrator (port 8087)
       */
      loadFromOrchestrator: async () => {
        set({ orchestratorLoading: true, orchestratorError: null })

        try {
          const projects = await window.electronAPI.projects.getAll()
          set({
            orchestratorProjects: projects,
            orchestratorLoading: false,
          })
          console.log(`[ProjectStore] Loaded ${projects.length} projects from orchestrator`)
          return true
        } catch (error: any) {
          // Silently handle connection errors (orchestrator not running is normal)
          set({ orchestratorLoading: false })
          console.log('[ProjectStore] Orchestrator not available:', error.message)
          return false
        }
      },

      /**
       * Toggle selection of an orchestrator project
       */
      toggleOrchestratorSelection: (projectId: string) => {
        set((state) => {
          const isSelected = state.selectedOrchestratorIds.includes(projectId)
          return {
            selectedOrchestratorIds: isSelected
              ? state.selectedOrchestratorIds.filter((id) => id !== projectId)
              : [...state.selectedOrchestratorIds, projectId],
          }
        })
      },

      /**
       * Clear all orchestrator selections
       */
      clearOrchestratorSelection: () => {
        set({ selectedOrchestratorIds: [] })
      },

      /**
       * Generate from selected orchestrator projects WITH VNC preview
       * Starts VNC container for each project and shows live preview
       */
      generateFromOrchestrator: async () => {
        const { selectedOrchestratorIds, orchestratorProjects } = get()

        if (selectedOrchestratorIds.length === 0) {
          console.warn('[ProjectStore] No projects selected for generation')
          return false
        }

        try {
          console.log(
            `[ProjectStore] Starting generation with VNC for ${selectedOrchestratorIds.length} projects:`,
            selectedOrchestratorIds
          )

          // Process each selected project
          let firstSuccessfulProjectId: string | null = null

          for (const projectId of selectedOrchestratorIds) {
            const orchestratorProject = orchestratorProjects.find(
              (p) => p.project_id === projectId
            )
            if (!orchestratorProject) {
              console.warn(`[ProjectStore] Orchestrator project not found: ${projectId}`)
              continue
            }

            // Create output directory path
            const outputDir = `./output_${projectId}`

            console.log(
              `[ProjectStore] Starting generation for "${orchestratorProject.project_name}"`,
              { projectPath: orchestratorProject.project_path, outputDir }
            )

            // Start VNC container + generation via the new IPC handler
            const result = await window.electronAPI.engine.startOrchestratorGenerationWithPreview(
              projectId,
              orchestratorProject.project_path,
              outputDir
            )

            if (result.success) {
              console.log(
                `[ProjectStore] VNC started for ${projectId} on port ${result.vncPort}`
              )

              // Create a local Project entry for VNC preview
              const newProject: Project = {
                id: projectId,
                name: orchestratorProject.project_name,
                description: `Generated from orchestrator: ${orchestratorProject.template_name}`,
                requirementsPath: orchestratorProject.project_path,
                outputDir: outputDir,
                status: 'generating',
                progress: 0,
                vncPort: result.vncPort,
                appPort: result.appPort,
                createdAt: new Date().toISOString(),
                lastRunAt: new Date().toISOString()
              }

              // Add project to local state and set as preview
              set((state) => ({
                projects: [
                  ...state.projects.filter((p) => p.id !== projectId), // Remove if exists
                  newProject
                ],
                previewProjectId: state.previewProjectId || projectId // Show first project's preview
              }))

              if (!firstSuccessfulProjectId) {
                firstSuccessfulProjectId = projectId
              }
            } else {
              console.error(
                `[ProjectStore] Failed to start generation for ${projectId}:`,
                result.error
              )
              set({ orchestratorError: result.error || 'Generation failed' })
            }
          }

          // Clear selection after processing
          set({ selectedOrchestratorIds: [] })

          // Set the first successful project as active preview
          if (firstSuccessfulProjectId) {
            set({ previewProjectId: firstSuccessfulProjectId })
            console.log(
              `[ProjectStore] Generation started successfully, preview: ${firstSuccessfulProjectId}`
            )
            return true
          }

          return false
        } catch (error: any) {
          console.error('[ProjectStore] Generation error:', error)
          set({ orchestratorError: error.message || 'Generation error' })
          return false
        }
      },

      // =========================================================================
      // RE (Requirements Engineer) Project Actions
      // =========================================================================

      loadLocalREProjects: async (paths?: string[]) => {
        set({ reProjectsLoading: true })
        try {
          const projects = await window.electronAPI.projects.scanLocalDirs(paths)
          set({ reProjects: projects, reProjectsLoading: false })
          console.log(`[ProjectStore] Loaded ${projects.length} local RE projects`)
          return true
        } catch (error: any) {
          console.error('[ProjectStore] Failed to load RE projects:', error)
          set({ reProjectsLoading: false })
          return false
        }
      },

      selectREProject: async (path: string | null) => {
        if (!path) {
          set({ selectedREProject: null })
          return
        }
        try {
          const detail = await window.electronAPI.projects.getREDetail(path)
          set({ selectedREProject: detail })
        } catch (error: any) {
          console.error('[ProjectStore] Failed to load RE project detail:', error)
        }
      },

      generateFromREProject: async (projectPath: string) => {
        const { reProjects } = get()
        const reProject = reProjects.find((p) => p.project_path === projectPath)
        if (!reProject) return false

        const projectId = `re-${reProject.project_id}`
        const outputDir = `./output_${reProject.project_id}`

        try {
          // Create local Project entry
          const newProject: Project = {
            id: projectId,
            name: reProject.project_name,
            description: `RE Project: ${reProject.requirements_count} requirements, ${reProject.tasks_count} tasks`,
            requirementsPath: projectPath,
            outputDir: outputDir,
            status: 'generating',
            progress: 0,
            createdAt: new Date().toISOString(),
            lastRunAt: new Date().toISOString(),
          }

          set((state) => ({
            projects: [
              ...state.projects.filter((p) => p.id !== projectId),
              newProject,
            ],
            // Keep RE selection so REProjectDetailView stays visible with progress panel
            activeProjectId: projectId,
          }))

          // Route: Epic path for projects with user stories, legacy path otherwise
          let result: { success: boolean; vncPort?: number; appPort?: number; error?: string }

          if (reProject.user_stories_count > 0) {
            // EPIC PATH: Route through EpicOrchestrator (task-by-task with real-time progress)
            result = await window.electronAPI.engine.startEpicGeneration(
              projectId,
              projectPath,
              outputDir,
            )
            // Load epics into engineStore for EpicSelector display
            if (result.success) {
              try {
                const { useEngineStore } = await import('./engineStore')
                useEngineStore.getState().loadEpics(projectPath)
              } catch (e) {
                console.warn('[ProjectStore] Could not load epics into engineStore:', e)
              }
            }
          } else {
            // LEGACY PATH: No user stories, use run_society_hybrid.py in Docker
            result = await window.electronAPI.engine.startGenerationWithPreview(
              projectId,
              projectPath,
              outputDir,
              true  // forceGenerate
            )
          }

          if (result.success) {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === projectId
                  ? { ...p, vncPort: result.vncPort, appPort: result.appPort }
                  : p
              ),
              previewProjectId: projectId,
              activeProjectId: projectId,
            }))
            console.log(`[ProjectStore] RE generation started: ${reProject.project_name} on VNC port ${result.vncPort}`)
            return true
          } else {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === projectId
                  ? { ...p, status: 'error', error: result.error }
                  : p
              ),
            }))
            return false
          }
        } catch (error: any) {
          console.error('[ProjectStore] RE generation error:', error)
          return false
        }
      },

      // =========================================================================
      // Review Gate Actions (Pause/Resume for User Review)
      // =========================================================================

      pauseForReview: async (id: string) => {
        try {
          const response = await fetch(
            `http://localhost:8000/api/v1/dashboard/generation/${id}/pause`,
            { method: 'POST' }
          )

          if (response.ok) {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === id ? { ...p, status: 'paused', reviewPaused: true } : p
              )
            }))
            console.log('[ProjectStore] Generation paused for review:', id)
            return true
          }
          return false
        } catch (error) {
          console.error('[ProjectStore] Failed to pause for review:', error)
          return false
        }
      },

      resumeWithFeedback: async (id: string, feedback?: string) => {
        try {
          const response = await fetch(
            `http://localhost:8000/api/v1/dashboard/generation/${id}/resume`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ feedback })
            }
          )

          if (response.ok) {
            set((state) => ({
              projects: state.projects.map((p) =>
                p.id === id
                  ? { ...p, status: 'generating', reviewPaused: false, reviewFeedback: undefined }
                  : p
              )
            }))
            console.log('[ProjectStore] Generation resumed:', id, feedback ? 'with feedback' : '')
            return true
          }
          return false
        } catch (error) {
          console.error('[ProjectStore] Failed to resume:', error)
          return false
        }
      },
    }),
    {
      name: 'coding-engine-projects',
      partialize: (state) => ({
        projects: state.projects,
        activeProjectId: state.activeProjectId
      }),
      // Custom storage to reset stuck "generating" states on load
      storage: {
        getItem: (name) => {
          const str = localStorage.getItem(name)
          if (!str) return null
          try {
            const data = JSON.parse(str)
            // Reset stuck generating/paused states BEFORE hydration
            if (data.state?.projects) {
              data.state.projects = data.state.projects.map((p: Project) =>
                p.status === 'generating' || p.status === 'paused'
                  ? { ...p, status: 'idle' as const, vncPort: undefined, appPort: undefined, progress: 0, reviewPaused: false }
                  : p
              )
              console.log('[ProjectStore] Reset stuck generating/paused states on load')
            }
            return data
          } catch {
            return null
          }
        },
        setItem: (name, value) => localStorage.setItem(name, JSON.stringify(value)),
        removeItem: (name) => localStorage.removeItem(name)
      }
    }
  )
)
