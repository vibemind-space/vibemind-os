import { useState, useMemo } from 'react'
import { useEngineStore, TaskChunk, EpicTask, EpicTaskList } from '../../stores/engineStore'
import { useClarificationStore } from '../../stores/clarificationStore'
import type { QueuedClarification } from '../../api/clarificationAPI'
import {
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  Layers,
  ChevronDown,
  ChevronRight,
  Filter,
  HelpCircle,
  SkipForward,
  Database,
  Server,
  Monitor,
  TestTube,
  Link2,
} from 'lucide-react'

type StatusFilter = 'all' | 'running' | 'failed' | 'pending' | 'completed' | 'skipped'

function getEpicTaskStatusIcon(status: EpicTask['status']) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="w-3.5 h-3.5 text-green-500" />
    case 'failed':
      return <XCircle className="w-3.5 h-3.5 text-red-500" />
    case 'running':
      return <Loader2 className="w-3.5 h-3.5 text-yellow-500 animate-spin" />
    case 'skipped':
      return <SkipForward className="w-3.5 h-3.5 text-gray-400" />
    case 'pending':
    default:
      return <Clock className="w-3.5 h-3.5 text-gray-500" />
  }
}

function getTaskTypeIcon(type: string) {
  switch (type) {
    case 'schema':
      return <Database className="w-3 h-3" />
    case 'api':
      return <Server className="w-3 h-3" />
    case 'frontend':
      return <Monitor className="w-3 h-3" />
    case 'test':
      return <TestTube className="w-3 h-3" />
    case 'integration':
      return <Link2 className="w-3 h-3" />
    default:
      return <Layers className="w-3 h-3" />
  }
}

function getTaskTypeBadge(type: string) {
  const colors: Record<string, string> = {
    schema: 'bg-purple-500/20 text-purple-400',
    api: 'bg-blue-500/20 text-blue-400',
    frontend: 'bg-cyan-500/20 text-cyan-400',
    test: 'bg-green-500/20 text-green-400',
    integration: 'bg-orange-500/20 text-orange-400',
  }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1 ${colors[type] || 'bg-gray-500/20 text-gray-400'}`}>
      {getTaskTypeIcon(type)}
      {type}
    </span>
  )
}

// ── EpicTaskListView ─────────────────────────────────────────────────
// Renders epic tasks when taskChunks is empty (CLI-started engine)
function EpicTaskListView({ taskList }: { taskList: EpicTaskList }) {
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  const tasks = taskList.tasks
  const progress = useMemo(() => {
    const total = tasks.length
    const completed = tasks.filter(t => t.status === 'completed').length
    const running = tasks.filter(t => t.status === 'running').length
    const failed = tasks.filter(t => t.status === 'failed').length
    const skipped = tasks.filter(t => t.status === 'skipped').length
    const pending = total - completed - running - failed - skipped
    return {
      total,
      completed,
      running,
      failed,
      skipped,
      pending,
      percent_complete: total > 0 ? (completed / total) * 100 : 0,
    }
  }, [tasks])

  // Group by task type
  const grouped = useMemo(() => {
    const filtered = filter === 'all'
      ? tasks
      : tasks.filter(t => t.status === filter)
    const groups: Record<string, EpicTask[]> = {}
    for (const task of filtered) {
      const group = task.type || 'other'
      if (!groups[group]) groups[group] = []
      groups[group].push(task)
    }
    return groups
  }, [tasks, filter])

  const toggleGroup = (group: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  const filterOptions: { key: StatusFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: progress.total },
    { key: 'running', label: 'Running', count: progress.running },
    { key: 'failed', label: 'Failed', count: progress.failed },
    { key: 'pending', label: 'Pending', count: progress.pending },
    { key: 'completed', label: 'Done', count: progress.completed },
  ]

  return (
    <div className="flex flex-col h-full gap-2">
      {/* Epic name + summary bar */}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span>
          <span className="text-engine-primary font-medium">{taskList.epic_name}</span>
          {' — '}
          <span className="text-white font-medium">{progress.completed}</span>/{progress.total} completed
          {progress.running > 0 && (
            <>, <span className="text-yellow-400">{progress.running} running</span></>
          )}
          {progress.failed > 0 && (
            <>, <span className="text-red-400">{progress.failed} failed</span></>
          )}
        </span>
        <span className="font-mono">{progress.percent_complete.toFixed(0)}%</span>
      </div>

      {/* Segmented progress bar */}
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden flex">
        {progress.total > 0 && (
          <>
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
          </>
        )}
      </div>

      {/* Filter chips */}
      <div className="flex gap-1 items-center">
        <Filter className="w-3 h-3 text-gray-500" />
        {filterOptions.map(opt => (
          <button
            key={opt.key}
            onClick={() => setFilter(opt.key)}
            className={`text-[11px] px-2 py-0.5 rounded-full transition ${
              filter === opt.key
                ? 'bg-engine-primary/20 text-engine-primary'
                : 'bg-gray-700/50 text-gray-400 hover:text-white'
            }`}
          >
            {opt.label}
            {opt.count > 0 && <span className="ml-1 opacity-70">{opt.count}</span>}
          </button>
        ))}
      </div>

      {/* Grouped task list by type */}
      <div className="flex-1 overflow-auto space-y-1">
        {Object.entries(grouped).map(([group, groupTasks]) => {
          const isCollapsed = collapsedGroups.has(group)
          const groupCompleted = groupTasks.filter(t => t.status === 'completed').length
          const groupTotal = groupTasks.length

          return (
            <div key={group}>
              <button
                onClick={() => toggleGroup(group)}
                className="flex items-center gap-1.5 w-full text-left text-xs py-1 px-1 rounded hover:bg-gray-700/30 transition"
              >
                {isCollapsed ? (
                  <ChevronRight className="w-3 h-3 text-gray-500" />
                ) : (
                  <ChevronDown className="w-3 h-3 text-gray-500" />
                )}
                {getTaskTypeIcon(group)}
                <span className="text-gray-300 font-medium capitalize">{group}</span>
                <span className="text-gray-500 ml-auto">
                  {groupCompleted}/{groupTotal}
                </span>
              </button>

              {!isCollapsed && (
                <div className="ml-4 space-y-0.5">
                  {groupTasks.map(task => (
                    <div
                      key={task.id}
                      className={`flex items-center gap-2 text-xs py-1 px-2 rounded ${
                        task.status === 'running'
                          ? 'bg-yellow-500/5'
                          : task.status === 'failed'
                          ? 'bg-red-500/5'
                          : ''
                      }`}
                    >
                      {getEpicTaskStatusIcon(task.status)}
                      <span className="text-gray-300 truncate flex-1" title={`${task.id}: ${task.description}`}>
                        {task.title}
                      </span>
                      {getTaskTypeBadge(task.type)}
                      {task.error_message && (
                        <span className="text-red-400 truncate max-w-[150px]" title={task.error_message}>
                          {task.error_message}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function getStatusIcon(status: TaskChunk['status']) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="w-3.5 h-3.5 text-green-500" />
    case 'failed':
      return <XCircle className="w-3.5 h-3.5 text-red-500" />
    case 'running':
      return <Loader2 className="w-3.5 h-3.5 text-yellow-500 animate-spin" />
    case 'pending':
    default:
      return <Clock className="w-3.5 h-3.5 text-gray-500" />
  }
}

function getComplexityBadge(complexity: string) {
  const colors: Record<string, string> = {
    simple: 'bg-green-500/20 text-green-400',
    medium: 'bg-yellow-500/20 text-yellow-400',
    complex: 'bg-red-500/20 text-red-400',
  }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded ${colors[complexity] || colors.medium}`}>
      {complexity}
    </span>
  )
}

export function TaskList() {
  const { taskChunks, taskProgress, taskClarifications, epicTaskLists, selectedEpic, epics } = useEngineStore()
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  // Derive epic task list as fallback when taskChunks is empty
  const epicTaskList = useMemo((): EpicTaskList | null => {
    if (taskChunks.length > 0) return null // Use taskChunks when available

    // Find task list from selected epic, or first epic with tasks
    const epicId = selectedEpic || epics.find(e => epicTaskLists[e.id]?.tasks?.length > 0)?.id
    if (!epicId || !epicTaskLists[epicId] || !epicTaskLists[epicId].tasks?.length) return null

    return epicTaskLists[epicId]
  }, [taskChunks.length, epicTaskLists, selectedEpic, epics])

  // Map: chunk_id -> related pending clarifications
  const chunkClarifications = useMemo(() => {
    const map = new Map<string, QueuedClarification[]>()
    for (const chunk of taskChunks) {
      const related = taskClarifications.filter(
        (c) => c.requirement_id && chunk.requirements.includes(c.requirement_id)
      )
      if (related.length > 0) {
        map.set(chunk.chunk_id, related)
      }
    }
    return map
  }, [taskChunks, taskClarifications])

  // Group chunks by service_group
  const grouped = useMemo(() => {
    const filtered = filter === 'all' ? taskChunks : taskChunks.filter((c) => c.status === filter)
    const groups: Record<string, TaskChunk[]> = {}
    for (const chunk of filtered) {
      const group = chunk.service_group || 'ungrouped'
      if (!groups[group]) groups[group] = []
      groups[group].push(chunk)
    }
    return groups
  }, [taskChunks, filter])

  const toggleGroup = (group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  // If we have epic tasks (CLI-started engine), render them instead
  // This check is placed AFTER all hooks to satisfy React's Rules of Hooks
  if (epicTaskList) {
    return <EpicTaskListView taskList={epicTaskList} />
  }

  if (taskChunks.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center">
          <Layers className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No tasks yet</p>
          <p className="text-xs mt-1">Tasks appear when generation starts</p>
        </div>
      </div>
    )
  }

  const filterOptions: { key: StatusFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: taskProgress.total },
    { key: 'running', label: 'Running', count: taskProgress.running },
    { key: 'failed', label: 'Failed', count: taskProgress.failed },
    { key: 'pending', label: 'Pending', count: taskProgress.pending },
    { key: 'completed', label: 'Done', count: taskProgress.completed },
  ]

  return (
    <div className="flex flex-col h-full gap-2">
      {/* Summary bar */}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span>
          <span className="text-white font-medium">{taskProgress.completed}</span>/{taskProgress.total} completed
          {taskProgress.running > 0 && (
            <>, <span className="text-yellow-400">{taskProgress.running} running</span></>
          )}
          {taskProgress.failed > 0 && (
            <>, <span className="text-red-400">{taskProgress.failed} failed</span></>
          )}
        </span>
        <span className="font-mono">{taskProgress.percent_complete.toFixed(0)}%</span>
      </div>

      {/* Segmented progress bar */}
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden flex">
        {taskProgress.total > 0 && (
          <>
            <div
              className="bg-green-500 transition-all duration-300"
              style={{ width: `${(taskProgress.completed / taskProgress.total) * 100}%` }}
            />
            <div
              className="bg-yellow-500 transition-all duration-300"
              style={{ width: `${(taskProgress.running / taskProgress.total) * 100}%` }}
            />
            <div
              className="bg-red-500 transition-all duration-300"
              style={{ width: `${(taskProgress.failed / taskProgress.total) * 100}%` }}
            />
          </>
        )}
      </div>

      {/* Filter chips */}
      <div className="flex gap-1 items-center">
        <Filter className="w-3 h-3 text-gray-500" />
        {filterOptions.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setFilter(opt.key)}
            className={`text-[11px] px-2 py-0.5 rounded-full transition ${
              filter === opt.key
                ? 'bg-engine-primary/20 text-engine-primary'
                : 'bg-gray-700/50 text-gray-400 hover:text-white'
            }`}
          >
            {opt.label}
            {opt.count > 0 && <span className="ml-1 opacity-70">{opt.count}</span>}
          </button>
        ))}
      </div>

      {/* Grouped task list */}
      <div className="flex-1 overflow-auto space-y-1">
        {Object.entries(grouped).map(([group, chunks]) => {
          const isCollapsed = collapsedGroups.has(group)
          const groupCompleted = chunks.filter((c) => c.status === 'completed').length
          const groupTotal = chunks.length

          return (
            <div key={group}>
              {/* Group header */}
              <button
                onClick={() => toggleGroup(group)}
                className="flex items-center gap-1.5 w-full text-left text-xs py-1 px-1 rounded hover:bg-gray-700/30 transition"
              >
                {isCollapsed ? (
                  <ChevronRight className="w-3 h-3 text-gray-500" />
                ) : (
                  <ChevronDown className="w-3 h-3 text-gray-500" />
                )}
                <Layers className="w-3 h-3 text-engine-primary" />
                <span className="text-gray-300 font-medium">{group}</span>
                <span className="text-gray-500 ml-auto">
                  {groupCompleted}/{groupTotal}
                </span>
              </button>

              {/* Chunk items */}
              {!isCollapsed && (
                <div className="ml-4 space-y-0.5">
                  {chunks.map((chunk) => (
                    <div
                      key={chunk.chunk_id}
                      className={`flex items-center gap-2 text-xs py-1 px-2 rounded ${
                        chunk.status === 'running'
                          ? 'bg-yellow-500/5'
                          : chunk.status === 'failed'
                          ? 'bg-red-500/5'
                          : ''
                      }`}
                    >
                      {getStatusIcon(chunk.status)}
                      <span className="text-gray-300 truncate flex-1" title={chunk.chunk_id}>
                        {chunk.chunk_id}
                      </span>
                      {getComplexityBadge(chunk.complexity)}
                      {chunkClarifications.has(chunk.chunk_id) && (
                        <button
                          onClick={async (e) => {
                            e.stopPropagation()
                            const clars = chunkClarifications.get(chunk.chunk_id)!
                            // Ensure clarificationStore is fresh before opening editor
                            await useClarificationStore.getState().refreshPending()
                            useClarificationStore.getState().selectClarification(clars[0].id)
                          }}
                          className="text-amber-400 hover:text-amber-300 transition"
                          title={`${chunkClarifications.get(chunk.chunk_id)!.length} clarification(s)`}
                        >
                          <HelpCircle className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {chunk.error_message && (
                        <span className="text-red-400 truncate max-w-[120px]" title={chunk.error_message}>
                          {chunk.error_message}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
