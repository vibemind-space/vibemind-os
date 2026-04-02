import { useState, useMemo } from 'react'
import { useEngineStore } from '../../stores/engineStore'
import {
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  Play,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  Layers,
  ListChecks,
  Zap,
} from 'lucide-react'

export interface Epic {
  id: string
  name: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress_percent: number
  user_stories: string[]
  requirements: string[]
  entities: string[]
  api_endpoints: string[]
  last_run_at: string | null
  run_count: number
}

export interface EpicTaskList {
  epic_id: string
  epic_name: string
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  progress_percent: number
  estimated_total_minutes: number
}

function getStatusIcon(status: Epic['status'], size: string = 'w-4 h-4') {
  switch (status) {
    case 'completed':
      return <CheckCircle className={`${size} text-green-500`} />
    case 'failed':
      return <XCircle className={`${size} text-red-500`} />
    case 'running':
      return <Loader2 className={`${size} text-yellow-500 animate-spin`} />
    case 'pending':
    default:
      return <Clock className={`${size} text-gray-500`} />
  }
}

function getEpicNumber(epicId: string): string {
  // "EPIC-001" -> "01"
  return epicId.replace('EPIC-', '').replace(/^0+/, '') || '0'
}

interface EpicSelectorProps {
  onRunEpic?: (epicId: string) => void
  onRerunEpic?: (epicId: string) => void
  onGenerateTaskList?: () => void
}

export function EpicSelector({ onRunEpic, onRerunEpic, onGenerateTaskList }: EpicSelectorProps) {
  const { epics, selectedEpic, epicTaskLists, selectEpic, loadEpicsLoading } = useEngineStore()
  const [showDetails, setShowDetails] = useState(false)

  // Current epic data
  const currentEpic = useMemo(() => {
    return epics.find((e) => e.id === selectedEpic)
  }, [epics, selectedEpic])

  // Current epic task list
  const currentTaskList = useMemo(() => {
    return selectedEpic ? epicTaskLists[selectedEpic] : null
  }, [selectedEpic, epicTaskLists])

  // Summary stats
  const stats = useMemo(() => {
    const total = epics.length
    const completed = epics.filter((e) => e.status === 'completed').length
    const running = epics.filter((e) => e.status === 'running').length
    const failed = epics.filter((e) => e.status === 'failed').length
    const pending = epics.filter((e) => e.status === 'pending').length
    return { total, completed, running, failed, pending }
  }, [epics])

  // No epics loaded yet
  if (epics.length === 0) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <Layers className="w-4 h-4 text-engine-primary" />
            Epics
          </h3>
        </div>

        <div className="text-center py-6 text-gray-500">
          <ListChecks className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">No epics loaded</p>
          <p className="text-xs mt-1">Select a project to load epics</p>
          {onGenerateTaskList && (
            <button
              onClick={onGenerateTaskList}
              disabled={loadEpicsLoading}
              className="mt-3 px-4 py-2 bg-engine-primary hover:bg-engine-primary/90 disabled:bg-gray-600 text-white rounded text-sm flex items-center gap-2 mx-auto transition"
            >
              {loadEpicsLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Zap className="w-4 h-4" />
              )}
              Generate Task List
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <Layers className="w-4 h-4 text-engine-primary" />
          Epics ({stats.total})
        </h3>
        <div className="flex items-center gap-1 text-[11px]">
          {stats.completed > 0 && (
            <span className="text-green-400">{stats.completed} done</span>
          )}
          {stats.running > 0 && (
            <span className="text-yellow-400 ml-1">{stats.running} running</span>
          )}
          {stats.failed > 0 && (
            <span className="text-red-400 ml-1">{stats.failed} failed</span>
          )}
        </div>
      </div>

      {/* Epic Grid */}
      <div className="grid grid-cols-5 gap-1.5">
        {epics.map((epic) => (
          <button
            key={epic.id}
            onClick={() => selectEpic(epic.id)}
            className={`relative p-2 rounded border transition-all ${
              selectedEpic === epic.id
                ? 'border-engine-primary bg-engine-primary/10 ring-1 ring-engine-primary/50'
                : 'border-gray-700 hover:border-gray-600 bg-gray-800/50'
            }`}
          >
            {/* Epic Number */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                {getStatusIcon(epic.status, 'w-3 h-3')}
                <span className="text-xs font-mono font-medium text-white">
                  {getEpicNumber(epic.id)}
                </span>
              </div>
              {epic.run_count > 0 && (
                <span className="text-[9px] text-gray-500">#{epic.run_count}</span>
              )}
            </div>

            {/* Progress bar */}
            <div className="h-1 bg-gray-700 rounded-full mt-1.5 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  epic.status === 'failed'
                    ? 'bg-red-500'
                    : epic.status === 'completed'
                    ? 'bg-green-500'
                    : epic.status === 'running'
                    ? 'bg-yellow-500'
                    : 'bg-gray-600'
                }`}
                style={{ width: `${epic.progress_percent}%` }}
              />
            </div>

            {/* Epic name tooltip on hover */}
            <div className="absolute inset-0 opacity-0 hover:opacity-100 transition-opacity">
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-gray-900 border border-gray-700 rounded text-[10px] text-white whitespace-nowrap z-10 pointer-events-none">
                {epic.name}
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Selected Epic Details */}
      {currentEpic && (
        <div className="border border-gray-700 rounded-lg bg-gray-800/30 overflow-hidden">
          {/* Epic Header */}
          <div className="flex items-center justify-between p-2 border-b border-gray-700/50">
            <div className="flex items-center gap-2">
              {getStatusIcon(currentEpic.status)}
              <div>
                <span className="text-sm font-medium text-white">{currentEpic.id}</span>
                <span className="text-gray-400 mx-1">-</span>
                <span className="text-sm text-gray-300">{currentEpic.name}</span>
              </div>
            </div>
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="text-gray-400 hover:text-white transition"
            >
              {showDetails ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
          </div>

          {/* Stats Row */}
          <div className="flex items-center gap-4 px-3 py-2 text-xs text-gray-400">
            <span>
              <span className="text-white font-medium">{currentEpic.user_stories.length}</span> User Stories
            </span>
            <span>
              <span className="text-white font-medium">{currentEpic.entities.length}</span> Entities
            </span>
            <span>
              <span className="text-white font-medium">{currentEpic.requirements.length}</span> Requirements
            </span>
            {currentTaskList && (
              <span className="ml-auto">
                <span className="text-white font-medium">{currentTaskList.total_tasks}</span> Tasks
                <span className="text-gray-500 ml-1">
                  (~{currentTaskList.estimated_total_minutes} min)
                </span>
              </span>
            )}
          </div>

          {/* Task Progress (if available) */}
          {currentTaskList && currentTaskList.total_tasks > 0 && (
            <div className="px-3 pb-2">
              <div className="flex items-center gap-2 text-[11px] text-gray-400 mb-1">
                <span>{currentTaskList.completed_tasks}/{currentTaskList.total_tasks} tasks</span>
                <span className="ml-auto font-mono">{currentTaskList.progress_percent.toFixed(0)}%</span>
              </div>
              <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden flex">
                <div
                  className="bg-green-500 transition-all duration-300"
                  style={{ width: `${(currentTaskList.completed_tasks / currentTaskList.total_tasks) * 100}%` }}
                />
                {currentTaskList.failed_tasks > 0 && (
                  <div
                    className="bg-red-500 transition-all duration-300"
                    style={{ width: `${(currentTaskList.failed_tasks / currentTaskList.total_tasks) * 100}%` }}
                  />
                )}
              </div>
            </div>
          )}

          {/* Expanded Details */}
          {showDetails && (
            <div className="px-3 py-2 border-t border-gray-700/50 text-xs text-gray-400 space-y-2">
              <p>{currentEpic.description}</p>
              {currentEpic.last_run_at && (
                <p className="text-gray-500">
                  Last run: {new Date(currentEpic.last_run_at).toLocaleString()}
                </p>
              )}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 p-2 border-t border-gray-700/50">
            <button
              onClick={() => onRunEpic?.(currentEpic.id)}
              disabled={currentEpic.status === 'running'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition ${
                currentEpic.status === 'running'
                  ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  : 'bg-engine-primary hover:bg-engine-primary/90 text-white'
              }`}
            >
              {currentEpic.status === 'running' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              {currentEpic.status === 'running' ? 'Running...' : 'Run'}
            </button>

            {(currentEpic.status === 'completed' || currentEpic.status === 'failed') && (
              <button
                onClick={() => onRerunEpic?.(currentEpic.id)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-xs font-medium transition"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Rerun
              </button>
            )}
          </div>
        </div>
      )}

      {/* Generate Task List Button (when epics loaded but no tasks) */}
      {epics.length > 0 && onGenerateTaskList && !Object.keys(epicTaskLists).length && (
        <button
          onClick={onGenerateTaskList}
          disabled={loadEpicsLoading}
          className="w-full px-4 py-2 bg-engine-primary/20 hover:bg-engine-primary/30 border border-engine-primary/50 text-engine-primary rounded text-sm flex items-center justify-center gap-2 transition"
        >
          <Zap className="w-4 h-4" />
          Generate All Task Lists
        </button>
      )}
    </div>
  )
}
