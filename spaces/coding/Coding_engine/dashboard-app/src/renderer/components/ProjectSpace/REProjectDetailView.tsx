import { useState, useEffect } from 'react'
import {
  ArrowLeft, Play, Square, RotateCcw, FolderOpen, FileText, ListTodo,
  GitBranch, AlertTriangle, ChevronDown, ChevronRight, Loader2,
  CheckCircle2, XCircle, Clock
} from 'lucide-react'
import { useProjectStore } from '../../stores/projectStore'
import { useEngineStore } from '../../stores/engineStore'
import type { REProjectDetail } from '../../stores/projectStore'

export function REProjectDetailView() {
  const {
    selectedREProject, selectREProject, generateFromREProject,
    stopGeneration, resumeWithFeedback, projects,
  } = useProjectStore()
  const {
    generationProgress, generationPhase, taskProgress, agentActivity,
  } = useEngineStore()

  const [activeTab, setActiveTab] = useState<'overview' | 'tasks' | 'quality'>('overview')
  const [expandedFeatures, setExpandedFeatures] = useState<Set<string>>(new Set())
  const [actionPending, setActionPending] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  if (!selectedREProject) return null

  const project = selectedREProject
  const projectId = `re-${project.project_id}`
  const liveProject = projects.find((p) => p.id === projectId)
  const status = liveProject?.status || 'idle'
  const isGenerating = status === 'generating'
  const isPaused = status === 'paused'
  const isStopped = status === 'stopped'
  const isError = status === 'error'

  const totalIssues = project.quality_issues.critical + project.quality_issues.high + project.quality_issues.medium

  // Elapsed timer during generation
  useEffect(() => {
    if (!isGenerating) { setElapsed(0); return }
    const start = Date.now()
    const interval = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(interval)
  }, [isGenerating])

  const formatElapsed = (secs: number) => {
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}m ${s.toString().padStart(2, '0')}s`
  }

  const toggleFeature = (featureId: string) => {
    setExpandedFeatures((prev) => {
      const next = new Set(prev)
      if (next.has(featureId)) next.delete(featureId)
      else next.add(featureId)
      return next
    })
  }

  const handleGenerate = async () => {
    setActionPending(true)
    try { await generateFromREProject(project.project_path) }
    finally { setActionPending(false) }
  }

  const handleStop = async () => {
    setActionPending(true)
    try { await stopGeneration(projectId) }
    finally { setActionPending(false) }
  }

  const handleResume = async () => {
    setActionPending(true)
    try { await resumeWithFeedback(projectId) }
    finally { setActionPending(false) }
  }

  // Unified button config based on status
  const buttonConfig = (() => {
    if (actionPending) return { label: 'Please wait...', icon: Loader2, color: 'bg-gray-600', action: () => {}, disabled: true, spin: true }
    if (isGenerating) return { label: 'Stop Generation', icon: Square, color: 'bg-red-600 hover:bg-red-500', action: handleStop, disabled: false, spin: false }
    if (isPaused) return { label: 'Resume Generation', icon: Play, color: 'bg-green-600 hover:bg-green-500', action: handleResume, disabled: false, spin: false }
    if (isStopped) return { label: 'Resume from Checkpoint', icon: RotateCcw, color: 'bg-orange-600 hover:bg-orange-500', action: handleGenerate, disabled: false, spin: false }
    if (isError) return { label: 'Retry Generation', icon: RotateCcw, color: 'bg-yellow-600 hover:bg-yellow-500', action: handleGenerate, disabled: false, spin: false }
    return { label: 'Generate Code', icon: Play, color: 'bg-blue-600 hover:bg-blue-500', action: handleGenerate, disabled: false, spin: false }
  })()

  return (
    <div className="h-full flex flex-col bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-700 p-4">
        <div className="flex items-center gap-3 mb-2">
          <button
            onClick={() => selectREProject(null)}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
            title="Back to projects"
          >
            <ArrowLeft className="w-4 h-4 text-gray-400" />
          </button>
          <h2 className="text-lg font-semibold text-white">{project.project_name}</h2>
          {project.architecture_pattern && (
            <span className="text-xs px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded">
              {project.architecture_pattern}
            </span>
          )}
          {isGenerating && (
            <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded animate-pulse">
              Generating {generationProgress}%
            </span>
          )}
        </div>

        {/* Tech Stack Tags */}
        <div className="flex flex-wrap gap-1 mb-3 ml-8">
          {project.tech_stack_tags.map((tag) => (
            <span key={tag} className="text-xs px-2 py-0.5 bg-gray-700 text-gray-300 rounded">
              {tag}
            </span>
          ))}
        </div>

        {/* Stats Bar */}
        <div className="flex items-center gap-4 ml-8 text-sm text-gray-400">
          <div className="flex items-center gap-1">
            <FileText className="w-4 h-4" />
            <span>{project.requirements_count} requirements</span>
          </div>
          <div className="flex items-center gap-1">
            <ListTodo className="w-4 h-4" />
            <span>{project.tasks_count} tasks</span>
          </div>
          <div className="flex items-center gap-1">
            <GitBranch className="w-4 h-4" />
            <span>{project.diagram_count} diagrams</span>
          </div>
          {totalIssues > 0 && (
            <div className="flex items-center gap-1">
              <AlertTriangle className={`w-4 h-4 ${project.quality_issues.critical > 0 ? 'text-red-400' : 'text-yellow-400'}`} />
              <span>{totalIssues} issues</span>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2 mt-3 ml-8">
          <button
            onClick={buttonConfig.action}
            disabled={buttonConfig.disabled}
            className={`flex items-center gap-2 px-4 py-2 rounded text-sm font-medium text-white transition-colors ${buttonConfig.color} ${buttonConfig.disabled ? 'opacity-50 cursor-wait' : ''}`}
          >
            <buttonConfig.icon className={`w-4 h-4 ${buttonConfig.spin ? 'animate-spin' : ''}`} />
            {buttonConfig.label}
          </button>
          <button
            onClick={() => window.electronAPI?.fs?.showInExplorer(project.project_path)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium text-gray-300 transition-colors"
          >
            <FolderOpen className="w-4 h-4" />
            Open in Explorer
          </button>
        </div>

        {/* Live Generation Progress Panel */}
        {(isGenerating || isPaused) && (
          <div className="mt-4 ml-8 bg-gray-800 rounded-lg p-4 border border-gray-700">
            {/* Progress Bar */}
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-300">
                {isPaused ? 'Generation Paused' : generationPhase || 'Starting...'}
              </span>
              <span className="text-sm text-gray-400">{generationProgress}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2 mb-3">
              <div
                className={`h-2 rounded-full transition-all duration-500 ${isPaused ? 'bg-yellow-500' : 'bg-blue-500'}`}
                style={{ width: `${Math.max(1, generationProgress)}%` }}
              />
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-4 gap-3 mb-3 text-xs">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
                <span className="text-gray-400">Completed:</span>
                <span className="text-green-300 font-medium">{taskProgress.completed}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
                <span className="text-gray-400">Running:</span>
                <span className="text-blue-300 font-medium">{taskProgress.running}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <XCircle className="w-3.5 h-3.5 text-red-400" />
                <span className="text-gray-400">Failed:</span>
                <span className="text-red-300 font-medium">{taskProgress.failed}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-gray-400" />
                <span className="text-gray-400">Elapsed:</span>
                <span className="text-gray-300 font-medium">{formatElapsed(elapsed)}</span>
              </div>
            </div>

            {/* Latest Activity */}
            {agentActivity.length > 0 && (
              <div className="border-t border-gray-700 pt-2">
                <span className="text-xs text-gray-500 mb-1 block">Latest Activity</span>
                <div className="space-y-0.5 max-h-20 overflow-auto">
                  {agentActivity.slice(-5).reverse().map((item, i) => (
                    <div key={i} className="text-xs flex items-center gap-1.5">
                      {typeof item === 'string' ? (
                        <span className="text-gray-400 truncate">{item}</span>
                      ) : (
                        <>
                          <span className={
                            item.status === 'completed' ? 'text-green-400' :
                            item.status === 'failed' ? 'text-red-400' :
                            'text-blue-400'
                          }>
                            {item.status === 'completed' ? '\u2705' : item.status === 'failed' ? '\u274C' : '\u23F3'}
                          </span>
                          <span className="text-gray-400 truncate">{item.agent}: {item.action}</span>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700 flex">
        {(['overview', 'tasks', 'quality'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab}
            {tab === 'quality' && totalIssues > 0 && (
              <span className="ml-1.5 text-xs px-1.5 py-0.5 bg-yellow-500/20 text-yellow-300 rounded">
                {totalIssues}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto p-4">
        {activeTab === 'overview' && (
          <OverviewTab project={project} />
        )}
        {activeTab === 'tasks' && (
          <TasksTab project={project} expandedFeatures={expandedFeatures} toggleFeature={toggleFeature} />
        )}
        {activeTab === 'quality' && (
          <QualityTab project={project} />
        )}
      </div>
    </div>
  )
}

function OverviewTab({ project }: { project: REProjectDetail }) {
  return (
    <div className="space-y-6">
      {/* Master Document Excerpt */}
      {project.master_document_excerpt && (
        <div>
          <h3 className="text-sm font-medium text-gray-300 mb-2">Master Document</h3>
          <div className="bg-gray-800 rounded p-3 text-sm text-gray-400 whitespace-pre-wrap max-h-64 overflow-auto">
            {project.master_document_excerpt}
          </div>
        </div>
      )}

      {/* Tech Stack Details */}
      {Object.keys(project.tech_stack_full).length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-300 mb-2">Tech Stack</h3>
          <div className="bg-gray-800 rounded p-3">
            <div className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(project.tech_stack_full)
                .filter(([, val]) => val && val !== 'none' && val !== '')
                .map(([key, val]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-gray-500">{key.replace(/_/g, ' ')}</span>
                    <span className="text-gray-300">{val}</span>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* Feature Breakdown Summary */}
      {project.feature_breakdown.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-300 mb-2">Features ({project.feature_breakdown.length})</h3>
          <div className="space-y-1">
            {project.feature_breakdown.map((feat) => (
              <div key={feat.feature_id} className="bg-gray-800 rounded px-3 py-2 flex items-center justify-between text-sm">
                <span className="text-gray-300">{feat.feature_name || feat.feature_id}</span>
                <span className="text-xs text-gray-500">{feat.requirements.length} reqs</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TasksTab({
  project,
  expandedFeatures,
  toggleFeature,
}: {
  project: REProjectDetail
  expandedFeatures: Set<string>
  toggleFeature: (id: string) => void
}) {
  const featureEntries = Object.entries(project.tasks_by_feature)

  if (featureEntries.length === 0) {
    return <p className="text-gray-500 text-sm">No tasks found.</p>
  }

  return (
    <div className="space-y-2">
      {featureEntries.map(([featureId, tasks]) => {
        const isExpanded = expandedFeatures.has(featureId)
        return (
          <div key={featureId} className="bg-gray-800 rounded">
            <button
              onClick={() => toggleFeature(featureId)}
              className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-gray-750 transition-colors"
            >
              <div className="flex items-center gap-2">
                {isExpanded ? (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                )}
                <span className="font-medium text-gray-300">{featureId}</span>
              </div>
              <span className="text-xs text-gray-500">{tasks.length} tasks</span>
            </button>

            {isExpanded && (
              <div className="px-3 pb-2 space-y-1">
                {tasks.map((task) => (
                  <div key={task.id} className="flex items-center justify-between px-3 py-1.5 bg-gray-900/50 rounded text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-gray-500 shrink-0">{task.id}</span>
                      <span className="text-gray-300 truncate">{task.title}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      <span className={`px-1.5 py-0.5 rounded ${
                        task.complexity === 'complex' ? 'bg-red-500/20 text-red-300' :
                        task.complexity === 'medium' ? 'bg-yellow-500/20 text-yellow-300' :
                        'bg-green-500/20 text-green-300'
                      }`}>
                        {task.complexity}
                      </span>
                      <span className="text-gray-500">{task.estimated_hours}h</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function QualityTab({ project }: { project: REProjectDetail }) {
  if (project.quality_issues_list.length === 0) {
    return <p className="text-green-400 text-sm">No quality issues found.</p>
  }

  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
  const sorted = [...project.quality_issues_list].sort(
    (a, b) => (severityOrder[a.severity as keyof typeof severityOrder] ?? 3) - (severityOrder[b.severity as keyof typeof severityOrder] ?? 3)
  )

  return (
    <div className="space-y-2">
      {/* Summary */}
      <div className="flex gap-3 mb-4 text-sm">
        {project.quality_issues.critical > 0 && (
          <span className="px-2 py-1 bg-red-500/20 text-red-300 rounded">
            {project.quality_issues.critical} critical
          </span>
        )}
        {project.quality_issues.high > 0 && (
          <span className="px-2 py-1 bg-orange-500/20 text-orange-300 rounded">
            {project.quality_issues.high} high
          </span>
        )}
        {project.quality_issues.medium > 0 && (
          <span className="px-2 py-1 bg-yellow-500/20 text-yellow-300 rounded">
            {project.quality_issues.medium} medium
          </span>
        )}
      </div>

      {/* Issues List */}
      {sorted.map((issue) => (
        <div key={issue.id} className="bg-gray-800 rounded px-3 py-2 flex items-start gap-3 text-sm">
          <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${
            issue.severity === 'critical' ? 'text-red-400' :
            issue.severity === 'high' ? 'text-orange-400' :
            'text-yellow-400'
          }`} />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-gray-300 font-medium">{issue.title}</span>
              <span className="text-xs text-gray-500">{issue.category}</span>
            </div>
            <span className="text-xs text-gray-500">{issue.id}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
