import { useState } from 'react'
import { Folder, FileText, ListTodo, GitBranch, AlertTriangle, Play, Loader2 } from 'lucide-react'
import type { REProjectSummary } from '../../stores/projectStore'

interface REProjectCardProps {
  project: REProjectSummary
  onSelect: (path: string) => void
  onGenerate: (path: string) => Promise<boolean>
}

export function REProjectCard({ project, onSelect, onGenerate }: REProjectCardProps) {
  const [generating, setGenerating] = useState(false)
  const totalIssues = project.quality_issues.critical + project.quality_issues.high + project.quality_issues.medium

  const handleGenerate = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setGenerating(true)
    try {
      await onGenerate(project.project_path)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div
      className="bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-blue-500/50 transition-colors cursor-pointer"
      onClick={() => onSelect(project.project_path)}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Folder className="w-5 h-5 text-blue-400 shrink-0" />
          <h3 className="font-medium text-white truncate">{project.project_name}</h3>
        </div>
        {project.architecture_pattern && (
          <span className="text-xs px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded shrink-0 ml-2">
            {project.architecture_pattern}
          </span>
        )}
      </div>

      {/* Tech Stack Tags */}
      {project.tech_stack_tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {project.tech_stack_tags.map((tag) => (
            <span key={tag} className="text-xs px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded">
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-2 mb-3 text-xs text-gray-400">
        <div className="flex items-center gap-1" title="Requirements">
          <FileText className="w-3 h-3" />
          <span>{project.requirements_count}</span>
        </div>
        <div className="flex items-center gap-1" title="Tasks">
          <ListTodo className="w-3 h-3" />
          <span>{project.tasks_count}</span>
        </div>
        <div className="flex items-center gap-1" title="Diagrams">
          <GitBranch className="w-3 h-3" />
          <span>{project.diagram_count}</span>
        </div>
        {totalIssues > 0 && (
          <div className="flex items-center gap-1" title={`Quality Issues: ${project.quality_issues.critical} critical, ${project.quality_issues.high} high`}>
            <AlertTriangle className={`w-3 h-3 ${project.quality_issues.critical > 0 ? 'text-red-400' : 'text-yellow-400'}`} />
            <span>{totalIssues}</span>
          </div>
        )}
      </div>

      {/* Indicators */}
      <div className="flex items-center gap-2 mb-3">
        {project.has_api_spec && (
          <span className="text-xs px-1.5 py-0.5 bg-green-500/20 text-green-300 rounded">API Spec</span>
        )}
        {project.has_master_document && (
          <span className="text-xs px-1.5 py-0.5 bg-blue-500/20 text-blue-300 rounded">Master Doc</span>
        )}
      </div>

      {/* Generate Button */}
      <button
        onClick={handleGenerate}
        disabled={generating}
        className={`w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded text-sm font-medium text-white transition-colors ${
          generating
            ? 'bg-blue-600/50 cursor-wait'
            : 'bg-blue-600 hover:bg-blue-500'
        }`}
      >
        {generating ? (
          <>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Starting Generation...
          </>
        ) : (
          <>
            <Play className="w-3.5 h-3.5" />
            Generate Code
          </>
        )}
      </button>
    </div>
  )
}
