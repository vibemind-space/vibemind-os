import { useProjectStore } from '../../stores/projectStore'
import { OrchestratorProjectCard } from './OrchestratorProjectCard'
import {
  RefreshCw,
  Rocket,
  Loader2,
  AlertCircle,
  Package,
  CheckSquare
} from 'lucide-react'

export function OrchestratorProjectsPanel() {
  const {
    orchestratorProjects,
    selectedOrchestratorIds,
    orchestratorLoading,
    orchestratorError,
    loadFromOrchestrator,
    toggleOrchestratorSelection,
    clearOrchestratorSelection,
    generateFromOrchestrator
  } = useProjectStore()

  const selectedCount = selectedOrchestratorIds.length
  const hasSelection = selectedCount > 0

  const handleGenerateSelected = async () => {
    const success = await generateFromOrchestrator()
    if (success) {
      // Optionally show success notification
      console.log('Generation started for selected projects')
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Package className="w-5 h-5 text-engine-primary" />
          <h2 className="text-lg font-semibold">Orchestrator Projects</h2>
          <span className="px-2 py-0.5 bg-gray-700 rounded text-sm text-gray-400">
            {orchestratorProjects.length} projects
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Selection Actions */}
          {hasSelection && (
            <>
              <button
                onClick={clearOrchestratorSelection}
                className="text-sm text-gray-400 hover:text-white transition"
              >
                Clear Selection
              </button>
              <span className="text-gray-600">|</span>
              <span className="text-sm text-engine-primary flex items-center gap-1">
                <CheckSquare className="w-4 h-4" />
                {selectedCount} selected
              </span>
            </>
          )}

          {/* Refresh Button */}
          <button
            onClick={() => loadFromOrchestrator()}
            disabled={orchestratorLoading}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${orchestratorLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          {/* Generate Button */}
          <button
            onClick={handleGenerateSelected}
            disabled={!hasSelection || orchestratorLoading}
            className="flex items-center gap-2 px-4 py-1.5 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Rocket className="w-4 h-4" />
            Generate {hasSelection ? `(${selectedCount})` : ''}
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {orchestratorError && (
        <div className="mx-4 mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
          <div className="flex-1">
            <p className="text-sm text-red-400">{orchestratorError}</p>
          </div>
          <button
            onClick={() => loadFromOrchestrator()}
            className="text-sm text-red-400 hover:text-red-300 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading State */}
      {orchestratorLoading && orchestratorProjects.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Loader2 className="w-12 h-12 mx-auto mb-4 text-engine-primary animate-spin" />
            <p className="text-gray-400">Loading projects from orchestrator...</p>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!orchestratorLoading && orchestratorProjects.length === 0 && !orchestratorError && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Package className="w-16 h-16 mx-auto mb-4 text-gray-600" />
            <p className="text-lg text-gray-400">No projects found</p>
            <p className="text-sm text-gray-500 mt-2">
              Make sure req-orchestrator is running on port 8087
            </p>
            <button
              onClick={() => loadFromOrchestrator()}
              className="mt-4 px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm transition"
            >
              Load Projects
            </button>
          </div>
        </div>
      )}

      {/* Projects Grid */}
      {orchestratorProjects.length > 0 && (
        <div className="flex-1 overflow-auto p-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {orchestratorProjects.map((project) => (
              <OrchestratorProjectCard
                key={project.project_id}
                project={project}
                isSelected={selectedOrchestratorIds.includes(project.project_id)}
                onToggleSelect={() => toggleOrchestratorSelection(project.project_id)}
                onGenerate={handleGenerateSelected}
              />
            ))}
          </div>
        </div>
      )}

      {/* Footer with help text */}
      {orchestratorProjects.length > 0 && (
        <div className="p-3 border-t border-gray-700 text-center text-sm text-gray-500">
          Select projects and click "Generate" to send them to the Coding Engine for code generation
        </div>
      )}
    </div>
  )
}
