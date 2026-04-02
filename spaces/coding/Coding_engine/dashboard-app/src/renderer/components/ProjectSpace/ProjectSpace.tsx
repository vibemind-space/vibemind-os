import { useProjectStore } from '../../stores/projectStore'
import { ProjectCard } from './ProjectCard'
import { OrchestratorProjectsPanel } from './OrchestratorProjectsPanel'
import { REProjectDetailView } from './REProjectDetailView'
import { REProjectCard } from './REProjectCard'

export function ProjectSpace() {
  const {
    activeProjectId, getProject, startGeneration, stopProject,
    selectedREProject, reProjects, selectREProject, generateFromREProject,
  } = useProjectStore()

  const activeProject = activeProjectId ? getProject(activeProjectId) : null

  // Priority 1: RE project detail (selected or generating RE project) — has progress panel
  if (selectedREProject) {
    return <REProjectDetailView />
  }

  // Priority 2: Active generating/running project (non-RE path)
  if (activeProject && (activeProject.status === 'generating' || activeProject.status === 'running')) {
    return (
      <div className="h-full p-6 overflow-auto">
        <ProjectCard
          project={activeProject}
          onStartGeneration={() => startGeneration(activeProject.id, true)}
          onStartPreview={() => startGeneration(activeProject.id, false)}
          onStopPreview={() => stopProject(activeProject.id)}
        />
      </div>
    )
  }

  // Priority 3: Show active project card (idle, paused, error, etc.)
  if (activeProject) {
    return (
      <div className="h-full p-6 overflow-auto">
        <ProjectCard
          project={activeProject}
          onStartGeneration={() => startGeneration(activeProject.id, true)}
          onStartPreview={() => startGeneration(activeProject.id, false)}
          onStopPreview={() => stopProject(activeProject.id)}
        />
      </div>
    )
  }

  // Priority 4: Show RE projects grid if available, else orchestrator panel
  if (reProjects.length > 0) {
    return (
      <div className="h-full p-6 overflow-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Local RE Projects</h2>
          <span className="text-xs px-2 py-1 bg-gray-700 text-gray-400 rounded">
            {reProjects.length} projects
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {reProjects.map((project) => (
            <REProjectCard
              key={project.project_id}
              project={project}
              onSelect={selectREProject}
              onGenerate={generateFromREProject}
            />
          ))}
        </div>
      </div>
    )
  }

  return <OrchestratorProjectsPanel />
}
