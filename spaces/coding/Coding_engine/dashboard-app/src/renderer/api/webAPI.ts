/**
 * Web API adapter - replaces Electron IPC with HTTP calls
 * This enables the dashboard to run as a standalone web app
 */

// Use empty base to leverage Vite proxy - requests go to /api/v1/* which proxy routes to localhost:8000
const API_BASE = ''
// Actual Coding Engine URL for req-orchestrator (Docker) to use - host.docker.internal reaches host machine
// Must include full path to /api/v1/jobs endpoint
const CODING_ENGINE_URL = 'http://host.docker.internal:8000/api/v1/jobs'
// Use Vite proxy path to avoid CORS issues (proxied to http://localhost:8087/api/v1)
const REQ_ORCHESTRATOR_PROXY = '/orchestrator'

// ============================================================================
// Types for req-orchestrator projects
// ============================================================================

export interface OrchestratorProject {
  project_id: string
  project_name: string
  project_path: string
  template_id: string
  template_name: string
  template_category: string
  tech_stack: string[]
  requirements_count: number
  source_file: string | null
  validation_summary: {
    total: number
    passed: number
    failed: number
    avg_score: number
  }
  created_at: string
  updated_at: string
}

interface DockerStatus {
  running: boolean
  services: string[]
}

interface ProjectResult {
  success: boolean
  error?: string
  vncPort?: number
  appPort?: number
}

interface ProjectStatus {
  running: boolean
  vncPort?: number
  appPort?: number
  health?: string
}

// Port tracking for web mode (mirrors electron port allocator)
const portAllocations = new Map<string, { vncPort: number; appPort: number }>()
let nextVncPort = 6081
let nextAppPort = 3001

/**
 * Web-based implementation of the Electron API
 */
export const webAPI = {
  // ============================================================================
  // Docker Management (via FastAPI backend)
  // ============================================================================
  docker: {
    startEngine: async (): Promise<{ success: boolean; error?: string }> => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/docker/start`, {
          method: 'POST',
        })
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` }
        }
        return await response.json()
      } catch (error) {
        return { success: false, error: String(error) }
      }
    },

    stopEngine: async (): Promise<{ success: boolean; error?: string }> => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/docker/stop`, {
          method: 'POST',
        })
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` }
        }
        return await response.json()
      } catch (error) {
        return { success: false, error: String(error) }
      }
    },

    getEngineStatus: async (): Promise<DockerStatus> => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/docker/status`)
        if (!response.ok) {
          return { running: false, services: [] }
        }
        return await response.json()
      } catch {
        // If API is not reachable, check if we can ping it
        return { running: false, services: [] }
      }
    },

    startProject: async (projectId: string, outputDir: string): Promise<ProjectResult> => {
      try {
        // Allocate ports
        let allocation = portAllocations.get(projectId)
        if (!allocation) {
          allocation = { vncPort: nextVncPort++, appPort: nextAppPort++ }
          portAllocations.set(projectId, allocation)
        }

        const response = await fetch(`${API_BASE}/api/v1/dashboard/project/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            projectId,
            outputDir,
            vncPort: allocation.vncPort,
            appPort: allocation.appPort,
          }),
        })

        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` }
        }

        return { success: true, ...allocation }
      } catch (error) {
        return { success: false, error: String(error) }
      }
    },

    stopProject: async (projectId: string): Promise<ProjectResult> => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/project/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ projectId }),
        })

        portAllocations.delete(projectId)

        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` }
        }
        return { success: true }
      } catch (error) {
        return { success: false, error: String(error) }
      }
    },

    getProjectStatus: async (projectId: string): Promise<ProjectStatus> => {
      try {
        const response = await fetch(
          `${API_BASE}/api/v1/dashboard/project/status?projectId=${encodeURIComponent(projectId)}`
        )
        if (!response.ok) {
          return { running: false }
        }
        const status = await response.json()
        const allocation = portAllocations.get(projectId)
        return {
          ...status,
          vncPort: allocation?.vncPort,
          appPort: allocation?.appPort,
        }
      } catch {
        return { running: false }
      }
    },

    getProjectLogs: async (projectId: string, tail = 100): Promise<string> => {
      try {
        const response = await fetch(
          `${API_BASE}/api/v1/dashboard/project/logs?projectId=${encodeURIComponent(
            projectId
          )}&tail=${tail}`
        )
        if (!response.ok) {
          return `Error: HTTP ${response.status}`
        }
        const data = await response.json()
        return data.logs || ''
      } catch (error) {
        return `Error fetching logs: ${error}`
      }
    },
  },

  // ============================================================================
  // Port Allocation
  // ============================================================================
  ports: {
    getVncPort: (projectId: string): number | undefined => {
      return portAllocations.get(projectId)?.vncPort
    },

    getAppPort: (projectId: string): number | undefined => {
      return portAllocations.get(projectId)?.appPort
    },

    getAll: (): Map<string, { vncPort: number; appPort: number }> => {
      return new Map(portAllocations)
    },
  },

  // ============================================================================
  // Engine API
  // ============================================================================
  engine: {
    startGeneration: async (
      requirementsPath: string,
      outputDir: string
    ): Promise<{ success: boolean; error?: string }> => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/generate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ requirementsPath, outputDir }),
        })
        if (!response.ok) {
          return { success: false, error: `HTTP ${response.status}` }
        }
        return await response.json()
      } catch (error) {
        return { success: false, error: String(error) }
      }
    },

    getApiUrl: (): string => API_BASE,
  },

  // ============================================================================
  // File System (limited in web mode)
  // ============================================================================
  fs: {
    openFolder: async (path: string): Promise<void> => {
      // In web mode, we can only show an alert with the path
      alert(`Open folder: ${path}\n\nThis requires the desktop app or manual navigation.`)
    },

    showInExplorer: async (path: string): Promise<void> => {
      alert(`Show in explorer: ${path}\n\nThis requires the desktop app or manual navigation.`)
    },
  },

  // ============================================================================
  // req-orchestrator Projects (with tech stacks)
  // ============================================================================
  projects: {
    /**
     * Get all projects from req-orchestrator with tech stack info
     */
    getAll: async (): Promise<OrchestratorProject[]> => {
      try {
        const response = await fetch(`${REQ_ORCHESTRATOR_PROXY}/techstack/projects`)
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = await response.json()
        return data.projects || []
      } catch (error) {
        console.error('Failed to fetch projects from orchestrator:', error)
        return []
      }
    },

    /**
     * Get requirements for a specific project
     */
    getRequirements: async (projectId: string): Promise<any[]> => {
      try {
        const response = await fetch(
          `${REQ_ORCHESTRATOR_PROXY}/techstack/projects/${projectId}/requirements`
        )
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        return await response.json()
      } catch (error) {
        console.error('Failed to fetch requirements:', error)
        return []
      }
    },

    /**
     * Send project(s) from req-orchestrator to Coding Engine for generation
     * This is the main integration point between the two systems
     */
    sendToEngine: async (
      projectIds: string[],
      outputDir?: string
    ): Promise<{ success: boolean; message?: string; error?: string }> => {
      try {
        const response = await fetch(`${REQ_ORCHESTRATOR_PROXY}/techstack/send-to-engine`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_ids: projectIds,
            coding_engine_url: CODING_ENGINE_URL, // Connect to Coding Engine
            include_failed: true, // Include all requirements (validation may not be complete)
          }),
        })

        if (!response.ok) {
          const errorText = await response.text()
          return { success: false, error: `HTTP ${response.status}: ${errorText}` }
        }

        return await response.json()
      } catch (error) {
        return { success: false, error: String(error) }
      }
    },

    /**
     * Scan local directories for RE projects (web fallback via FastAPI /local-projects)
     */
    scanLocalDirs: async (_paths?: string[]): Promise<any[]> => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/dashboard/local-projects`)
        if (!response.ok) return []
        const data = await response.json()
        // Map LocalProjectResponse → REProjectSummary shape
        return (data.projects || []).map((p: any) => ({
          project_id: p.project_id,
          project_name: p.project_name,
          project_path: p.project_path,
          source: 'local_re' as const,
          tech_stack_tags: [],
          architecture_pattern: '',
          requirements_count: 0,
          user_stories_count: p.user_story_count || 0,
          tasks_count: 0,
          diagram_count: 0,
          quality_issues: { critical: 0, high: 0, medium: 0 },
          has_api_spec: p.has_api_docs || false,
          has_master_document: true,
        }))
      } catch (error) {
        console.error('[WebAPI] Failed to scan local projects:', error)
        return []
      }
    },

    /**
     * Get RE project detail (web fallback - returns null, detail requires Electron IPC)
     */
    getREDetail: async (_projectPath: string): Promise<any> => {
      // Full detail parsing requires filesystem access (Electron only)
      // Return null so the UI gracefully degrades
      return null
    },
  },
}

/**
 * Initialize the web API on window object
 * This makes it compatible with code expecting window.electronAPI
 */
export function initWebAPI() {
  if (typeof window !== 'undefined' && !window.electronAPI) {
    ;(window as any).electronAPI = webAPI
    console.log('[WebAPI] Initialized web-based API adapter')
  }
}

// Type augmentation for window.electronAPI
declare global {
  interface Window {
    electronAPI?: typeof webAPI
  }
}
