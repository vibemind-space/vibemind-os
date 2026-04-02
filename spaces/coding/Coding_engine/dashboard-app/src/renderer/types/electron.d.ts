/**
 * Type definitions for Electron API exposed via preload
 */

interface DockerAPI {
  startEngine: () => Promise<{ success: boolean; error?: string }>
  stopEngine: () => Promise<{ success: boolean; error?: string }>
  getEngineStatus: () => Promise<{ running: boolean; services: string[] }>
  startProject: (projectId: string, requirementsPath: string, outputDir: string) => Promise<{
    success: boolean
    vncPort?: number
    appPort?: number
    error?: string
  }>
  stopProject: (projectId: string) => Promise<{ success: boolean; error?: string }>
  getProjectStatus: (projectId: string) => Promise<{
    running: boolean
    vncPort?: number
    appPort?: number
    health?: string
  }>
  getProjectLogs: (projectId: string, tail?: number) => Promise<string>
}

interface PortsAPI {
  getVncPort: (projectId: string) => Promise<number | undefined>
  getAppPort: (projectId: string) => Promise<number | undefined>
  getAll: () => Promise<Map<string, { vncPort: number; appPort: number }>>
}

interface EngineAPI {
  startGeneration: (requirementsPath: string, outputDir: string) => Promise<{
    success: boolean
    error?: string
  }>

  // Start generation WITH VNC preview (for live preview in dashboard)
  // forceGenerate: if true, always run generation even if project files exist
  startGenerationWithPreview: (
    projectId: string,
    requirementsPath: string,
    outputDir: string,
    forceGenerate?: boolean
  ) => Promise<{
    success: boolean
    vncPort?: number
    appPort?: number
    generationPid?: number
    error?: string
  }>

  // Start generation for orchestrator project WITH VNC preview
  startOrchestratorGenerationWithPreview: (
    projectId: string,
    projectPath: string,
    outputDir: string
  ) => Promise<{
    success: boolean
    vncPort?: number
    appPort?: number
    generationPid?: number
    error?: string
  }>

  // Stop a running generation
  stopGeneration: (projectId: string) => Promise<{
    success: boolean
    error?: string
  }>

  // Start epic-based generation (routes through EpicOrchestrator)
  startEpicGeneration: (projectId: string, projectPath: string, outputDir: string) => Promise<{
    success: boolean
    vncPort?: number
    appPort?: number
    error?: string
  }>

  // Epic-based task management
  getEpics: (projectPath: string) => Promise<any>
  getEpicTasks: (epicId: string, projectPath: string) => Promise<any>
  runEpic: (epicId: string, projectPath: string) => Promise<any>
  rerunEpic: (epicId: string, projectPath: string) => Promise<any>
  rerunTask: (epicId: string, taskId: string, projectPath: string, fixInstructions?: string) => Promise<{
    success: boolean
    error?: string
  }>
  generateTaskLists: (projectPath: string) => Promise<any>

  getApiUrl: () => Promise<string>
}

interface FileSystemAPI {
  openFolder: (path: string) => Promise<string>
  showInExplorer: (path: string) => void
  exists: (path: string) => Promise<boolean>
}

interface OrchestratorProject {
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

interface ClaudeChatPayload {
  message: string
  projectPath: string
  outputDir: string
  conversationHistory?: Array<{ role: string; content: string }>
}

interface ClaudeChatResponse {
  success: boolean
  response: string
  files_modified: string[]
  files_created: string[]
  error?: string
}

interface ClaudeAPI {
  chat: (payload: ClaudeChatPayload) => Promise<ClaudeChatResponse>
}

interface DebugAPI {
  getBrowserErrors: () => Promise<any[]>
  getDockerLogs: (projectId: string, tail?: number) => Promise<string>
  captureScreenshot: (projectId: string) => Promise<{
    success: boolean
    screenshot?: string
    error?: string
  }>
}

interface REProjectSummary {
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

interface REProjectDetail extends REProjectSummary {
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

interface ProjectsAPI {
  getAll: () => Promise<OrchestratorProject[]>
  get: (id: string) => Promise<OrchestratorProject | null>
  create: (data: any) => Promise<OrchestratorProject>
  delete: (id: string) => Promise<{ success: boolean }>
  getStatus: (id: string) => Promise<any>
  sendToEngine: (projectIds: string[]) => Promise<{
    success: boolean
    message?: string
    error?: string
  }>
  scanLocalDirs: (paths?: string[]) => Promise<REProjectSummary[]>
  getREDetail: (projectPath: string) => Promise<REProjectDetail>
}

interface ServiceStatus {
  name: string
  status: 'stopped' | 'starting' | 'running' | 'error'
  url?: string
  pid?: number
  error?: string
  upSince?: string
}

interface AllServiceStatus {
  fastapi: ServiceStatus
  docker: ServiceStatus
  python: ServiceStatus
}

interface ServicesAPI {
  getStatus: () => Promise<AllServiceStatus>
  restartFastAPI: () => Promise<AllServiceStatus>
  onStatusUpdate: (callback: (status: AllServiceStatus) => void) => () => void
}

interface ElectronAPI {
  services: ServicesAPI
  docker: DockerAPI
  ports: PortsAPI
  engine: EngineAPI
  claude: ClaudeAPI
  debug: DebugAPI
  fs: FileSystemAPI
  projects: ProjectsAPI
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}

export { OrchestratorProject, REProjectSummary, REProjectDetail }
