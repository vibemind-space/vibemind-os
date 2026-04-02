import { useState, useEffect, useRef, useMemo } from 'react'
import { useEngineStore, EpicTask, EpicTaskList } from '../../stores/engineStore'
import {
  X,
  Minimize2,
  Maximize2,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Filter,
  Pause,
  Play,
  ShieldCheck,
  RotateCcw,
} from 'lucide-react'

type StatusFilter = 'all' | 'running' | 'failed' | 'pending' | 'completed' | 'tested' | 'untested'

interface TaskBoardModalProps {
  epicId: string
  isOpen: boolean
  onClose: () => void
  onPause?: () => void
  onResume?: () => void
  isPaused?: boolean
}

function getTaskStatusIcon(task: EpicTask) {
  switch (task.status) {
    case 'completed':
      return task.tested
        ? <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
        : <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
    case 'failed':
      return <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
    case 'running':
      return <Loader2 className="w-4 h-4 text-yellow-500 animate-spin flex-shrink-0" />
    case 'skipped':
      return <AlertTriangle className="w-4 h-4 text-gray-500 flex-shrink-0" />
    case 'pending':
    default:
      return <Clock className="w-4 h-4 text-gray-500 flex-shrink-0" />
  }
}

function getTaskTypeBadge(type: EpicTask['type']) {
  const colors: Record<string, string> = {
    schema: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    api: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    frontend: 'bg-green-500/20 text-green-400 border-green-500/30',
    test: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    integration: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  }
  return colors[type] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
}

export function TaskBoardModal({
  epicId,
  isOpen,
  onClose,
  onPause,
  onResume,
  isPaused = false,
}: TaskBoardModalProps) {
  const { epicTaskLists, epics, rerunTask } = useEngineStore()
  const [isMinimized, setIsMinimized] = useState(false)
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set())
  const [fixInstructions, setFixInstructions] = useState<Record<string, string>>({})
  const [rerunningTasks, setRerunningTasks] = useState<Set<string>>(new Set())
  const runningTaskRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const taskList = epicTaskLists[epicId]
  const epic = epics.find((e) => e.id === epicId)

  // Auto-scroll to running task
  useEffect(() => {
    if (runningTaskRef.current && scrollContainerRef.current) {
      runningTaskRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    }
  }, [taskList?.tasks])

  // Group tasks by type
  const groupedTasks = useMemo(() => {
    if (!taskList?.tasks) return {}

    const filtered =
      filter === 'all'
        ? taskList.tasks
        : filter === 'tested'
        ? taskList.tasks.filter((t) => t.status === 'completed' && t.tested)
        : filter === 'untested'
        ? taskList.tasks.filter((t) => t.status === 'completed' && !t.tested)
        : taskList.tasks.filter((t) => t.status === filter)

    const groups: Record<string, EpicTask[]> = {
      setup: [],
      schema: [],
      api: [],
      frontend: [],
      test: [],
      verify: [],
      docker: [],
      checkpoint: [],
      other: [],
    }

    for (const task of filtered) {
      const taskType = task.type.toLowerCase()
      if (taskType.startsWith('setup')) groups.setup.push(task)
      else if (taskType.startsWith('schema')) groups.schema.push(task)
      else if (taskType.startsWith('api')) groups.api.push(task)
      else if (taskType.startsWith('fe_') || taskType.startsWith('frontend')) groups.frontend.push(task)
      else if (taskType.startsWith('test') || taskType.startsWith('verify')) groups.test.push(task)
      else if (taskType.startsWith('verify')) groups.verify.push(task)
      else if (taskType.startsWith('docker')) groups.docker.push(task)
      else if (taskType.startsWith('checkpoint')) groups.checkpoint.push(task)
      else groups.other.push(task)
    }

    // Remove empty groups
    return Object.fromEntries(Object.entries(groups).filter(([_, tasks]) => tasks.length > 0))
  }, [taskList?.tasks, filter])

  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  if (!isOpen) return null

  // Calculate progress
  const progress = taskList
    ? {
        completed: taskList.completed_tasks,
        failed: taskList.failed_tasks,
        total: taskList.total_tasks,
        percent: taskList.progress_percent,
        running: taskList.tasks.filter((t) => t.status === 'running').length,
        pending: taskList.tasks.filter((t) => t.status === 'pending').length,
      }
    : { completed: 0, failed: 0, total: 0, percent: 0, running: 0, pending: 0 }

  // Minimized view
  if (isMinimized) {
    return (
      <div className="fixed bottom-4 right-4 bg-engine-dark border border-gray-700 rounded-lg shadow-xl z-50 p-3 min-w-[200px]">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {progress.running > 0 ? (
              <Loader2 className="w-4 h-4 text-yellow-500 animate-spin" />
            ) : progress.failed > 0 ? (
              <XCircle className="w-4 h-4 text-red-500" />
            ) : (
              <CheckCircle className="w-4 h-4 text-green-500" />
            )}
            <span className="text-sm text-white font-medium">{epicId}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">{progress.percent.toFixed(0)}%</span>
            <button
              onClick={() => setIsMinimized(false)}
              className="text-gray-400 hover:text-white transition"
            >
              <Maximize2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="h-1.5 bg-gray-700 rounded-full mt-2 overflow-hidden flex">
          <div
            className="bg-green-500 transition-all duration-300"
            style={{ width: `${(progress.completed / progress.total) * 100}%` }}
          />
          <div
            className="bg-yellow-500 transition-all duration-300"
            style={{ width: `${(progress.running / progress.total) * 100}%` }}
          />
          <div
            className="bg-red-500 transition-all duration-300"
            style={{ width: `${(progress.failed / progress.total) * 100}%` }}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-y-4 right-4 w-96 bg-engine-dark border border-gray-700 rounded-lg shadow-xl z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          {progress.running > 0 ? (
            <Loader2 className="w-5 h-5 text-yellow-500 animate-spin" />
          ) : progress.failed > 0 ? (
            <XCircle className="w-5 h-5 text-red-500" />
          ) : progress.completed === progress.total ? (
            <CheckCircle className="w-5 h-5 text-green-500" />
          ) : (
            <Clock className="w-5 h-5 text-gray-400" />
          )}
          <div>
            <h3 className="text-white font-medium">{epicId}</h3>
            <p className="text-xs text-gray-400">{epic?.name}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isPaused ? (
            <button
              onClick={onResume}
              className="p-1.5 text-green-400 hover:bg-green-500/10 rounded transition"
              title="Resume"
            >
              <Play className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={onPause}
              className="p-1.5 text-yellow-400 hover:bg-yellow-500/10 rounded transition"
              title="Pause"
            >
              <Pause className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => setIsMinimized(true)}
            className="p-1.5 text-gray-400 hover:text-white transition"
          >
            <Minimize2 className="w-4 h-4" />
          </button>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white transition">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="px-4 py-2 border-b border-gray-700/50">
        <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
          <span>
            {progress.completed}/{progress.total} completed
            {progress.running > 0 && (
              <span className="text-yellow-400 ml-2">{progress.running} running</span>
            )}
            {progress.failed > 0 && (
              <span className="text-red-400 ml-2">{progress.failed} failed</span>
            )}
          </span>
          <span className="font-mono">{progress.percent.toFixed(0)}%</span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden flex">
          <div
            className="bg-green-500 transition-all duration-300"
            style={{ width: `${(progress.completed / progress.total) * 100}%` }}
          />
          <div
            className="bg-yellow-500 transition-all duration-300"
            style={{ width: `${(progress.running / progress.total) * 100}%` }}
          />
          <div
            className="bg-red-500 transition-all duration-300"
            style={{ width: `${(progress.failed / progress.total) * 100}%` }}
          />
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-gray-700/50">
        <Filter className="w-3 h-3 text-gray-500" />
        {(['all', 'running', 'pending', 'completed', 'tested', 'untested', 'failed'] as StatusFilter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-[10px] px-2 py-0.5 rounded-full transition ${
              filter === f
                ? 'bg-engine-primary/20 text-engine-primary'
                : 'bg-gray-700/50 text-gray-400 hover:text-white'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Task List */}
      <div ref={scrollContainerRef} className="flex-1 overflow-auto px-2 py-2">
        {Object.entries(groupedTasks).map(([group, tasks]) => (
          <div key={group} className="mb-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider px-2 py-1">
              {group} ({tasks.length})
            </div>
            {tasks.map((task) => {
              const isRunning = task.status === 'running'
              const isExpanded = expandedTasks.has(task.id)

              return (
                <div
                  key={task.id}
                  ref={isRunning ? runningTaskRef : undefined}
                  className={`rounded mb-0.5 transition ${
                    isRunning
                      ? 'bg-yellow-500/10 border-l-2 border-yellow-500'
                      : task.status === 'failed'
                      ? 'bg-red-500/5'
                      : ''
                  }`}
                >
                  <button
                    onClick={() => toggleTask(task.id)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 text-left hover:bg-gray-700/30 transition rounded"
                  >
                    {getTaskStatusIcon(task)}
                    <span className="flex-1 text-xs text-gray-300 truncate">{task.title}</span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded border ${getTaskTypeBadge(
                        task.type
                      )}`}
                    >
                      {task.type.replace('_', ' ')}
                    </span>
                    {task.dependencies.length > 0 && (
                      <span className="text-[9px] text-gray-500">+{task.dependencies.length}</span>
                    )}
                    {isExpanded ? (
                      <ChevronDown className="w-3 h-3 text-gray-500" />
                    ) : (
                      <ChevronRight className="w-3 h-3 text-gray-500" />
                    )}
                  </button>

                  {isExpanded && (
                    <div className="px-8 pb-2 text-[11px] text-gray-400 space-y-1.5">
                      <p>{task.description}</p>

                      {/* Tested / Untested badge for completed tasks */}
                      {task.status === 'completed' && (
                        task.tested ? (
                          <div className="flex items-center gap-1.5 bg-emerald-500/10 text-emerald-400 px-2 py-1 rounded text-[10px]">
                            <ShieldCheck className="w-3 h-3" />
                            Verified by tests
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 bg-yellow-500/10 text-yellow-400 px-2 py-1 rounded text-[10px]">
                            <AlertTriangle className="w-3 h-3" />
                            Not yet tested
                          </div>
                        )
                      )}

                      {task.error_message && (
                        <p className="text-red-400 bg-red-500/10 p-1.5 rounded">
                          {task.error_message}
                        </p>
                      )}

                      {/* Fix instructions form for failed tasks */}
                      {task.status === 'failed' && (
                        <div className="space-y-1.5 mt-1">
                          <textarea
                            className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-[11px] text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-engine-primary"
                            rows={3}
                            placeholder="Describe how to fix this task..."
                            value={fixInstructions[task.id] || ''}
                            onChange={(e) =>
                              setFixInstructions((prev) => ({
                                ...prev,
                                [task.id]: e.target.value,
                              }))
                            }
                          />
                          <button
                            disabled={rerunningTasks.has(task.id)}
                            onClick={async () => {
                              setRerunningTasks((prev) => new Set(prev).add(task.id))
                              await rerunTask(epicId, task.id, fixInstructions[task.id] || undefined)
                              setRerunningTasks((prev) => {
                                const next = new Set(prev)
                                next.delete(task.id)
                                return next
                              })
                              setFixInstructions((prev) => {
                                const next = { ...prev }
                                delete next[task.id]
                                return next
                              })
                            }}
                            className="flex items-center gap-1.5 px-2.5 py-1 bg-engine-primary/20 text-engine-primary hover:bg-engine-primary/30 rounded text-[10px] font-medium transition disabled:opacity-50"
                          >
                            {rerunningTasks.has(task.id) ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <RotateCcw className="w-3 h-3" />
                            )}
                            Rerun with Fix
                          </button>
                        </div>
                      )}

                      {/* Simple rerun button for completed/skipped tasks */}
                      {(task.status === 'completed' || task.status === 'skipped') && (
                        <button
                          disabled={rerunningTasks.has(task.id)}
                          onClick={async () => {
                            setRerunningTasks((prev) => new Set(prev).add(task.id))
                            await rerunTask(epicId, task.id)
                            setRerunningTasks((prev) => {
                              const next = new Set(prev)
                              next.delete(task.id)
                              return next
                            })
                          }}
                          className="flex items-center gap-1.5 px-2.5 py-1 bg-gray-700/50 text-gray-300 hover:bg-gray-700 rounded text-[10px] transition disabled:opacity-50"
                        >
                          {rerunningTasks.has(task.id) ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <RotateCcw className="w-3 h-3" />
                          )}
                          Rerun
                        </button>
                      )}

                      {task.output_files.length > 0 && (
                        <p className="text-gray-500">
                          Output: {task.output_files.join(', ')}
                        </p>
                      )}
                      <p className="text-gray-500">
                        Est: {task.estimated_minutes} min
                        {task.actual_minutes && ` | Actual: ${task.actual_minutes} min`}
                      </p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}

        {Object.keys(groupedTasks).length === 0 && (
          <div className="text-center py-8 text-gray-500">
            <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No tasks match filter</p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-gray-700 text-xs text-gray-500">
        {taskList?.estimated_total_minutes && (
          <span>Est. total: {taskList.estimated_total_minutes} min</span>
        )}
        {taskList?.run_count > 0 && (
          <span className="ml-2">Run #{taskList.run_count}</span>
        )}
      </div>
    </div>
  )
}
