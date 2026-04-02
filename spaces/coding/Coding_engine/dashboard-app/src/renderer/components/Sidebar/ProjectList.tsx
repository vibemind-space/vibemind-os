import { useState, useEffect } from 'react'
import { useProjectStore, OrchestratorProject } from '../../stores/projectStore'
import type { REProjectSummary } from '../../stores/projectStore'
import { CreateProjectModal } from '../ProjectSpace/CreateProjectModal'
import {
  Plus,
  Folder,
  RefreshCw,
  Check,
  Loader2,
  ChevronDown,
  ChevronRight,
  FileText,
} from 'lucide-react'

export function ProjectList() {
  const {
    orchestratorProjects,
    selectedOrchestratorIds,
    orchestratorLoading,
    toggleOrchestratorSelection,
    loadFromOrchestrator,
    setActiveProject,
    // RE projects
    reProjects,
    reProjectsLoading,
    loadLocalREProjects,
    selectREProject,
    selectedREProject,
  } = useProjectStore()

  const [showCreateModal, setShowCreateModal] = useState(false)
  const [reExpanded, setReExpanded] = useState(true)
  const [orchExpanded, setOrchExpanded] = useState(true)

  // Load projects on mount
  useEffect(() => {
    loadLocalREProjects()
    loadFromOrchestrator()
  }, [loadLocalREProjects, loadFromOrchestrator])

  const handleProjectClick = (project: OrchestratorProject) => {
    setActiveProject(project.project_id)
  }

  const handleREProjectClick = (project: REProjectSummary) => {
    selectREProject(project.project_path)
  }

  const handleSelectToggle = (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation()
    toggleOrchestratorSelection(projectId)
  }

  const isSelected = (projectId: string) => selectedOrchestratorIds.includes(projectId)
  const isLoading = reProjectsLoading || orchestratorLoading

  const handleRefresh = () => {
    loadLocalREProjects()
    loadFromOrchestrator()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-gray-700 flex items-center justify-between">
        <h2 className="font-semibold text-sm text-gray-300">Projects</h2>
        <div className="flex items-center gap-1">
          <button
            onClick={handleRefresh}
            className="p-1.5 hover:bg-gray-700 rounded transition"
            title="Refresh Projects"
            disabled={isLoading}
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="p-1.5 hover:bg-gray-700 rounded transition"
            title="New Project"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Project List - Two Sections */}
      <div className="flex-1 overflow-auto">

        {/* Section: LOCAL (RE) */}
        <div>
          <button
            onClick={() => setReExpanded(!reExpanded)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:bg-gray-800/50 transition"
          >
            <div className="flex items-center gap-1">
              {reExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              <span>Local (RE)</span>
            </div>
            {reProjects.length > 0 && (
              <span className="text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded">
                {reProjects.length}
              </span>
            )}
          </button>

          {reExpanded && (
            <div>
              {reProjectsLoading && reProjects.length === 0 ? (
                <div className="px-4 py-2 text-center text-gray-500 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin mx-auto mb-1" />
                  Scanning...
                </div>
              ) : reProjects.length === 0 ? (
                <div className="px-4 py-2 text-gray-500 text-xs">
                  No RE projects in Data/all_services/
                </div>
              ) : (
                <ul className="px-2 pb-1 space-y-0.5">
                  {reProjects.map((project) => (
                    <li
                      key={project.project_id}
                      onClick={() => handleREProjectClick(project)}
                      className={`
                        group flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition text-sm
                        ${selectedREProject?.project_path === project.project_path
                          ? 'bg-blue-500/20 border border-blue-500/50'
                          : 'hover:bg-gray-700/50'
                        }
                      `}
                    >
                      <FileText className="w-4 h-4 text-blue-400 shrink-0" />
                      <span className="flex-1 truncate">{project.project_name}</span>
                      <span className="text-xs bg-gray-700 px-1.5 py-0.5 rounded text-gray-400">
                        {project.requirements_count}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Section: ORCHESTRATOR */}
        <div>
          <button
            onClick={() => setOrchExpanded(!orchExpanded)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:bg-gray-800/50 transition"
          >
            <div className="flex items-center gap-1">
              {orchExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              <span>Orchestrator</span>
            </div>
            {orchestratorProjects.length > 0 && (
              <span className="text-xs bg-gray-600 text-gray-300 px-1.5 py-0.5 rounded">
                {orchestratorProjects.length}
              </span>
            )}
          </button>

          {orchExpanded && (
            <div>
              {orchestratorLoading && orchestratorProjects.length === 0 ? (
                <div className="px-4 py-2 text-center text-gray-500 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin mx-auto mb-1" />
                  Connecting...
                </div>
              ) : orchestratorProjects.length === 0 ? (
                <div className="px-4 py-2 text-gray-500 text-xs">
                  Not connected (port 8087)
                </div>
              ) : (
                <ul className="px-2 pb-1 space-y-0.5">
                  {orchestratorProjects.map((project) => (
                    <li
                      key={project.project_id}
                      onClick={() => handleProjectClick(project)}
                      className={`
                        group flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition text-sm
                        ${isSelected(project.project_id)
                          ? 'bg-engine-primary/20 border border-engine-primary/50'
                          : 'hover:bg-gray-700/50'
                        }
                      `}
                    >
                      <button
                        onClick={(e) => handleSelectToggle(e, project.project_id)}
                        className={`
                          w-4 h-4 rounded border shrink-0 flex items-center justify-center transition
                          ${isSelected(project.project_id)
                            ? 'bg-engine-primary border-engine-primary'
                            : 'border-gray-500 hover:border-gray-400'
                          }
                        `}
                      >
                        {isSelected(project.project_id) && (
                          <Check className="w-3 h-3 text-white" />
                        )}
                      </button>

                      <Folder className="w-4 h-4 text-gray-400 shrink-0" />

                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{project.project_name}</p>
                        <p className="text-xs text-gray-500 truncate">{project.template_name}</p>
                      </div>

                      <span className="text-xs bg-gray-700 px-1.5 py-0.5 rounded text-gray-400">
                        {project.requirements_count}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Selected count */}
      {selectedOrchestratorIds.length > 0 && (
        <div className="p-2 border-t border-gray-700 text-xs text-gray-400">
          {selectedOrchestratorIds.length} selected
        </div>
      )}

      {/* Create Project Modal */}
      {showCreateModal && (
        <CreateProjectModal onClose={() => setShowCreateModal(false)} />
      )}
    </div>
  )
}
