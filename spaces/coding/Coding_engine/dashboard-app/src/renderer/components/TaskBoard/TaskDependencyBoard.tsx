import { useState, useMemo, useCallback } from 'react'
import { useEngineStore, type EpicTask, type EpicTaskList } from '../../stores/engineStore'
import {
  GitBranch,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Search,
  Filter,
  ArrowRight,
  Lock,
  Unlock,
  SkipForward,
  Zap,
} from 'lucide-react'

type ViewMode = 'board' | 'graph' | 'list'
type StatusFilter = 'all' | 'pending' | 'running' | 'completed' | 'failed' | 'blocked'

interface TaskNode {
  task: EpicTask
  depth: number
  blocked: boolean
  blockedBy: string[]
  blocks: string[]
  criticalPath: boolean
}

// ── Dependency Analysis Helpers ────────────────────────────────────────

function buildDependencyGraph(tasks: EpicTask[]): Map<string, TaskNode> {
  const taskMap = new Map<string, EpicTask>()
  tasks.forEach((t) => taskMap.set(t.id, t))

  // Build reverse dependency map (who blocks whom)
  const blocksMap = new Map<string, string[]>()
  tasks.forEach((t) => {
    t.dependencies.forEach((depId) => {
      if (!blocksMap.has(depId)) blocksMap.set(depId, [])
      blocksMap.get(depId)!.push(t.id)
    })
  })

  // Calculate depths via BFS (topological layers)
  const depths = new Map<string, number>()
  const queue: string[] = []

  // Start with root tasks (no dependencies)
  tasks.forEach((t) => {
    if (t.dependencies.length === 0) {
      depths.set(t.id, 0)
      queue.push(t.id)
    }
  })

  while (queue.length > 0) {
    const current = queue.shift()!
    const currentDepth = depths.get(current) || 0
    const children = blocksMap.get(current) || []
    children.forEach((childId) => {
      const existingDepth = depths.get(childId) || 0
      if (currentDepth + 1 > existingDepth) {
        depths.set(childId, currentDepth + 1)
      }
      if (!queue.includes(childId)) {
        queue.push(childId)
      }
    })
  }

  // Tasks without resolved depth (possible circular or orphan) get max depth
  const maxDepth = Math.max(0, ...Array.from(depths.values()))
  tasks.forEach((t) => {
    if (!depths.has(t.id)) depths.set(t.id, maxDepth + 1)
  })

  // Determine blocked status
  const isBlocked = (task: EpicTask): string[] => {
    return task.dependencies.filter((depId) => {
      const dep = taskMap.get(depId)
      return dep && dep.status !== 'completed' && dep.status !== 'skipped'
    })
  }

  // Find critical path (longest chain)
  const criticalPathIds = findCriticalPath(tasks, taskMap, blocksMap)

  const nodes = new Map<string, TaskNode>()
  tasks.forEach((t) => {
    const blockedByIds = isBlocked(t)
    nodes.set(t.id, {
      task: t,
      depth: depths.get(t.id) || 0,
      blocked: blockedByIds.length > 0 && t.status === 'pending',
      blockedBy: blockedByIds,
      blocks: blocksMap.get(t.id) || [],
      criticalPath: criticalPathIds.has(t.id),
    })
  })

  return nodes
}

function findCriticalPath(
  tasks: EpicTask[],
  taskMap: Map<string, EpicTask>,
  blocksMap: Map<string, string[]>
): Set<string> {
  // Find the longest path through the dependency graph
  const memo = new Map<string, number>()

  function longestPath(taskId: string): number {
    if (memo.has(taskId)) return memo.get(taskId)!
    const children = blocksMap.get(taskId) || []
    if (children.length === 0) {
      memo.set(taskId, 1)
      return 1
    }
    const max = 1 + Math.max(...children.map((c) => longestPath(c)))
    memo.set(taskId, max)
    return max
  }

  // Find root tasks and compute longest paths
  const roots = tasks.filter((t) => t.dependencies.length === 0)
  let maxLen = 0
  let bestRoot = ''
  roots.forEach((r) => {
    const len = longestPath(r.id)
    if (len > maxLen) {
      maxLen = len
      bestRoot = r.id
    }
  })

  // Trace the critical path
  const path = new Set<string>()
  function trace(id: string) {
    path.add(id)
    const children = blocksMap.get(id) || []
    if (children.length === 0) return
    // Follow the child with the longest sub-path
    let bestChild = children[0]
    let bestLen = 0
    children.forEach((c) => {
      const len = memo.get(c) || 0
      if (len > bestLen) {
        bestLen = len
        bestChild = c
      }
    })
    if (bestChild) trace(bestChild)
  }

  if (bestRoot) trace(bestRoot)
  return path
}

// ── Status Helpers ─────────────────────────────────────────────────────

function getStatusIcon(status: string, blocked: boolean) {
  if (blocked) return <Lock className="w-3.5 h-3.5 text-orange-500" />
  switch (status) {
    case 'completed':
      return <CheckCircle className="w-3.5 h-3.5 text-green-500" />
    case 'failed':
      return <XCircle className="w-3.5 h-3.5 text-red-500" />
    case 'running':
      return <Loader2 className="w-3.5 h-3.5 text-yellow-500 animate-spin" />
    case 'skipped':
      return <SkipForward className="w-3.5 h-3.5 text-gray-500" />
    default:
      return <Clock className="w-3.5 h-3.5 text-gray-500" />
  }
}

function getStatusColor(status: string, blocked: boolean): string {
  if (blocked) return 'border-orange-500/40 bg-orange-500/5'
  switch (status) {
    case 'completed': return 'border-green-500/40 bg-green-500/5'
    case 'failed': return 'border-red-500/40 bg-red-500/5'
    case 'running': return 'border-yellow-500/40 bg-yellow-500/5'
    case 'skipped': return 'border-gray-600 bg-gray-800'
    default: return 'border-gray-700 bg-engine-darker'
  }
}

const TYPE_COLORS: Record<string, string> = {
  schema: 'bg-blue-500/20 text-blue-400',
  schema_migration: 'bg-blue-500/20 text-blue-400',
  api: 'bg-green-500/20 text-green-400',
  api_endpoint: 'bg-green-500/20 text-green-400',
  frontend: 'bg-purple-500/20 text-purple-400',
  fe_component: 'bg-purple-500/20 text-purple-400',
  fe_page: 'bg-purple-500/20 text-purple-400',
  test: 'bg-yellow-500/20 text-yellow-400',
  test_e2e: 'bg-yellow-500/20 text-yellow-400',
  integration: 'bg-cyan-500/20 text-cyan-400',
  verify: 'bg-orange-500/20 text-orange-400',
  docker: 'bg-pink-500/20 text-pink-400',
  config: 'bg-gray-500/20 text-gray-400',
}

// ── Main Component ─────────────────────────────────────────────────────

export function TaskDependencyBoard() {
  const { epicTaskLists, epics } = useEngineStore()
  const [selectedEpicId, setSelectedEpicId] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('board')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [hoveredTaskId, setHoveredTaskId] = useState<string | null>(null)

  // Auto-select first epic with tasks
  const activeEpicId = selectedEpicId || Object.keys(epicTaskLists)[0] || null
  const taskList = activeEpicId ? epicTaskLists[activeEpicId] : null
  const tasks = taskList?.tasks || []

  // Build dependency graph
  const graph = useMemo(() => buildDependencyGraph(tasks), [tasks])

  // Compute stats
  const stats = useMemo(() => {
    const nodes = Array.from(graph.values())
    return {
      total: nodes.length,
      completed: nodes.filter((n) => n.task.status === 'completed').length,
      running: nodes.filter((n) => n.task.status === 'running').length,
      failed: nodes.filter((n) => n.task.status === 'failed').length,
      blocked: nodes.filter((n) => n.blocked).length,
      pending: nodes.filter((n) => n.task.status === 'pending' && !n.blocked).length,
      maxDepth: Math.max(0, ...nodes.map((n) => n.depth)),
      criticalPathLen: nodes.filter((n) => n.criticalPath).length,
    }
  }, [graph])

  // Filter tasks
  const filteredNodes = useMemo(() => {
    let nodes = Array.from(graph.values())

    // Status filter
    if (statusFilter === 'blocked') {
      nodes = nodes.filter((n) => n.blocked)
    } else if (statusFilter !== 'all') {
      nodes = nodes.filter((n) => n.task.status === statusFilter)
    }

    // Search
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      nodes = nodes.filter(
        (n) => n.task.title.toLowerCase().includes(q) || n.task.id.toLowerCase().includes(q)
      )
    }

    return nodes
  }, [graph, statusFilter, searchQuery])

  // Get highlighted connections for hovered task
  const highlightedIds = useMemo(() => {
    if (!hoveredTaskId) return new Set<string>()
    const node = graph.get(hoveredTaskId)
    if (!node) return new Set<string>()
    const ids = new Set<string>([hoveredTaskId])
    node.task.dependencies.forEach((d) => ids.add(d))
    node.blocks.forEach((b) => ids.add(b))
    return ids
  }, [hoveredTaskId, graph])

  if (tasks.length === 0) {
    return (
      <div className="h-full flex flex-col bg-engine-dark">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
          <GitBranch className="w-5 h-5 text-indigo-400" />
          <h2 className="text-sm font-semibold">Task Board</h2>
        </div>
        <div className="flex-1 flex items-center justify-center text-gray-500">
          <div className="text-center">
            <GitBranch className="w-8 h-8 mx-auto mb-2 text-gray-600" />
            <p className="text-sm">No task data loaded</p>
            <p className="text-xs text-gray-600 mt-1">Load an epic in the Epics tab to see tasks</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-engine-dark">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-indigo-400" />
          <h2 className="text-sm font-semibold">Task Board</h2>
          {activeEpicId && (
            <span className="text-xs px-2 py-0.5 bg-indigo-500/20 text-indigo-400 rounded">
              {taskList?.epic_name || activeEpicId}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Epic selector */}
          {Object.keys(epicTaskLists).length > 1 && (
            <select
              value={activeEpicId || ''}
              onChange={(e) => setSelectedEpicId(e.target.value || null)}
              className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 focus:border-indigo-500 focus:outline-none"
            >
              {Object.entries(epicTaskLists).map(([id, tl]) => (
                <option key={id} value={id}>
                  {tl.epic_name || id}
                </option>
              ))}
            </select>
          )}

          {/* View mode */}
          <div className="flex bg-gray-800 rounded border border-gray-700">
            {(['board', 'graph', 'list'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`px-2.5 py-1 text-xs capitalize transition ${
                  viewMode === mode
                    ? 'bg-indigo-500/20 text-indigo-400'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-700/50 text-[10px]">
        <StatPill label="Total" value={stats.total} color="text-gray-300" />
        <StatPill label="Done" value={stats.completed} color="text-green-400" />
        <StatPill label="Running" value={stats.running} color="text-yellow-400" />
        <StatPill label="Pending" value={stats.pending} color="text-gray-400" />
        <StatPill label="Blocked" value={stats.blocked} color="text-orange-400" />
        <StatPill label="Failed" value={stats.failed} color="text-red-400" />
        <div className="ml-auto flex items-center gap-1 text-gray-500">
          <Zap className="w-3 h-3 text-indigo-400" />
          Critical path: {stats.criticalPathLen} tasks, {stats.maxDepth + 1} layers
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-700/50">
        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tasks..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1">
          <Filter className="w-3.5 h-3.5 text-gray-500" />
          {(['all', 'pending', 'running', 'completed', 'failed', 'blocked'] as StatusFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setStatusFilter(f)}
              className={`px-2 py-1 text-[10px] rounded capitalize transition ${
                statusFilter === f
                  ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/40'
                  : 'text-gray-500 hover:text-gray-300 border border-transparent'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {viewMode === 'board' && (
          <BoardView
            nodes={filteredNodes}
            graph={graph}
            highlightedIds={highlightedIds}
            selectedTaskId={selectedTaskId}
            onSelectTask={setSelectedTaskId}
            onHoverTask={setHoveredTaskId}
            maxDepth={stats.maxDepth}
          />
        )}
        {viewMode === 'graph' && (
          <GraphView
            nodes={Array.from(graph.values())}
            highlightedIds={highlightedIds}
            onHoverTask={setHoveredTaskId}
            onSelectTask={setSelectedTaskId}
          />
        )}
        {viewMode === 'list' && (
          <ListView
            nodes={filteredNodes}
            highlightedIds={highlightedIds}
            selectedTaskId={selectedTaskId}
            onSelectTask={setSelectedTaskId}
            onHoverTask={setHoveredTaskId}
          />
        )}
      </div>

      {/* Detail Panel */}
      {selectedTaskId && graph.has(selectedTaskId) && (
        <TaskDetailPanel
          node={graph.get(selectedTaskId)!}
          graph={graph}
          onClose={() => setSelectedTaskId(null)}
          onNavigate={setSelectedTaskId}
        />
      )}
    </div>
  )
}

// ── Sub-Components ─────────────────────────────────────────────────────

function StatPill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono font-medium ${color}`}>{value}</span>
    </span>
  )
}

function BoardView({
  nodes,
  graph,
  highlightedIds,
  selectedTaskId,
  onSelectTask,
  onHoverTask,
  maxDepth,
}: {
  nodes: TaskNode[]
  graph: Map<string, TaskNode>
  highlightedIds: Set<string>
  selectedTaskId: string | null
  onSelectTask: (id: string | null) => void
  onHoverTask: (id: string | null) => void
  maxDepth: number
}) {
  // Group by depth (layer)
  const layers = useMemo(() => {
    const layerMap = new Map<number, TaskNode[]>()
    nodes.forEach((n) => {
      if (!layerMap.has(n.depth)) layerMap.set(n.depth, [])
      layerMap.get(n.depth)!.push(n)
    })
    return Array.from(layerMap.entries()).sort(([a], [b]) => a - b)
  }, [nodes])

  return (
    <div className="space-y-4">
      {layers.map(([depth, layerNodes]) => (
        <div key={depth}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-medium text-gray-500 uppercase">Layer {depth}</span>
            <span className="text-[10px] text-gray-600">{layerNodes.length} tasks</span>
            <div className="flex-1 h-px bg-gray-700/50" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {layerNodes.map((node) => (
              <TaskCard
                key={node.task.id}
                node={node}
                isHighlighted={highlightedIds.has(node.task.id)}
                isSelected={selectedTaskId === node.task.id}
                isDimmed={highlightedIds.size > 0 && !highlightedIds.has(node.task.id)}
                onClick={() => onSelectTask(selectedTaskId === node.task.id ? null : node.task.id)}
                onMouseEnter={() => onHoverTask(node.task.id)}
                onMouseLeave={() => onHoverTask(null)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function GraphView({
  nodes,
  highlightedIds,
  onHoverTask,
  onSelectTask,
}: {
  nodes: TaskNode[]
  highlightedIds: Set<string>
  onHoverTask: (id: string | null) => void
  onSelectTask: (id: string | null) => void
}) {
  // Simplified DAG layout as text-based graph
  const layers = useMemo(() => {
    const layerMap = new Map<number, TaskNode[]>()
    nodes.forEach((n) => {
      if (!layerMap.has(n.depth)) layerMap.set(n.depth, [])
      layerMap.get(n.depth)!.push(n)
    })
    return Array.from(layerMap.entries()).sort(([a], [b]) => a - b)
  }, [nodes])

  return (
    <div className="overflow-auto">
      <div className="flex gap-6 min-w-max pb-4">
        {layers.map(([depth, layerNodes], layerIdx) => (
          <div key={depth} className="flex flex-col items-center gap-2 min-w-[180px]">
            <div className="text-[10px] font-medium text-gray-500 uppercase mb-1">
              Layer {depth}
            </div>
            {layerNodes.map((node) => {
              const isHL = highlightedIds.has(node.task.id)
              const isDim = highlightedIds.size > 0 && !isHL
              return (
                <div
                  key={node.task.id}
                  className={`relative w-full px-3 py-2 rounded-lg border text-xs cursor-pointer transition ${
                    getStatusColor(node.task.status, node.blocked)
                  } ${node.criticalPath ? 'ring-1 ring-indigo-500/40' : ''} ${
                    isDim ? 'opacity-30' : ''
                  } ${isHL ? 'ring-2 ring-indigo-400' : ''}`}
                  onMouseEnter={() => onHoverTask(node.task.id)}
                  onMouseLeave={() => onHoverTask(null)}
                  onClick={() => onSelectTask(node.task.id)}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    {getStatusIcon(node.task.status, node.blocked)}
                    <span className="font-mono text-[9px] text-gray-500">{node.task.id}</span>
                  </div>
                  <p className="text-gray-300 truncate">{node.task.title}</p>
                  <div className="flex items-center gap-1 mt-1">
                    <span className={`text-[9px] px-1 py-0.5 rounded ${TYPE_COLORS[node.task.type] || 'bg-gray-700 text-gray-400'}`}>
                      {node.task.type}
                    </span>
                    {node.task.dependencies.length > 0 && (
                      <span className="text-[9px] text-gray-600">
                        ← {node.task.dependencies.length} deps
                      </span>
                    )}
                    {node.blocks.length > 0 && (
                      <span className="text-[9px] text-gray-600">
                        → {node.blocks.length} blocks
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
            {/* Arrow to next layer */}
            {layerIdx < layers.length - 1 && layerNodes.length > 0 && (
              <ArrowRight className="w-4 h-4 text-gray-600 mt-2" />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function ListView({
  nodes,
  highlightedIds,
  selectedTaskId,
  onSelectTask,
  onHoverTask,
}: {
  nodes: TaskNode[]
  highlightedIds: Set<string>
  selectedTaskId: string | null
  onSelectTask: (id: string | null) => void
  onHoverTask: (id: string | null) => void
}) {
  // Sort: running first, then blocked, then pending, then completed, then failed
  const sorted = useMemo(() => {
    const priority: Record<string, number> = {
      running: 0,
      failed: 1,
      pending: 2,
      completed: 3,
      skipped: 4,
    }
    return [...nodes].sort((a, b) => {
      // Blocked items between running and pending
      const aP = a.blocked ? 1.5 : (priority[a.task.status] ?? 5)
      const bP = b.blocked ? 1.5 : (priority[b.task.status] ?? 5)
      return aP - bP
    })
  }, [nodes])

  return (
    <div className="space-y-1">
      {sorted.map((node) => (
        <TaskCard
          key={node.task.id}
          node={node}
          isHighlighted={highlightedIds.has(node.task.id)}
          isSelected={selectedTaskId === node.task.id}
          isDimmed={highlightedIds.size > 0 && !highlightedIds.has(node.task.id)}
          onClick={() => onSelectTask(selectedTaskId === node.task.id ? null : node.task.id)}
          onMouseEnter={() => onHoverTask(node.task.id)}
          onMouseLeave={() => onHoverTask(null)}
        />
      ))}
    </div>
  )
}

function TaskCard({
  node,
  isHighlighted,
  isSelected,
  isDimmed,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: {
  node: TaskNode
  isHighlighted: boolean
  isSelected: boolean
  isDimmed: boolean
  onClick: () => void
  onMouseEnter: () => void
  onMouseLeave: () => void
}) {
  const { task, blocked, blockedBy, blocks, criticalPath } = node

  return (
    <button
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={`w-full text-left px-3 py-2.5 rounded-lg border transition ${
        getStatusColor(task.status, blocked)
      } ${criticalPath ? 'ring-1 ring-indigo-500/30' : ''} ${
        isSelected ? 'ring-2 ring-indigo-400' : ''
      } ${isHighlighted ? 'ring-2 ring-indigo-400/60' : ''} ${
        isDimmed ? 'opacity-30' : ''
      } hover:bg-white/5`}
    >
      <div className="flex items-center gap-2">
        {getStatusIcon(task.status, blocked)}
        <span className="text-sm text-gray-200 truncate flex-1">{task.title}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${TYPE_COLORS[task.type] || 'bg-gray-700 text-gray-400'}`}>
          {task.type}
        </span>
      </div>
      <div className="flex items-center gap-2 mt-1 text-[10px]">
        <span className="font-mono text-gray-600">{task.id}</span>
        {blocked && blockedBy.length > 0 && (
          <span className="text-orange-400 flex items-center gap-0.5">
            <Lock className="w-2.5 h-2.5" />
            Blocked by {blockedBy.length}
          </span>
        )}
        {blocks.length > 0 && (
          <span className="text-gray-500 flex items-center gap-0.5">
            <Unlock className="w-2.5 h-2.5" />
            Blocks {blocks.length}
          </span>
        )}
        {criticalPath && (
          <span className="text-indigo-400 flex items-center gap-0.5">
            <Zap className="w-2.5 h-2.5" />
            Critical
          </span>
        )}
        {task.error_message && (
          <span className="text-red-400 truncate ml-auto max-w-[200px]">
            {task.error_message}
          </span>
        )}
      </div>
    </button>
  )
}

function TaskDetailPanel({
  node,
  graph,
  onClose,
  onNavigate,
}: {
  node: TaskNode
  graph: Map<string, TaskNode>
  onClose: () => void
  onNavigate: (id: string) => void
}) {
  const { task, blocked, blockedBy, blocks, depth, criticalPath } = node

  return (
    <div className="border-t border-gray-700 bg-engine-darker px-4 py-3 max-h-72 overflow-auto">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {getStatusIcon(task.status, blocked)}
          <h3 className="text-sm font-medium text-gray-200">{task.title}</h3>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xs">
          ✕
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs mb-3">
        <div>
          <span className="text-gray-500">ID</span>
          <p className="font-mono text-gray-300">{task.id}</p>
        </div>
        <div>
          <span className="text-gray-500">Type</span>
          <p className="text-gray-300">{task.type}</p>
        </div>
        <div>
          <span className="text-gray-500">Layer</span>
          <p className="text-gray-300">{depth} {criticalPath ? '(critical path)' : ''}</p>
        </div>
      </div>

      {task.description && (
        <p className="text-xs text-gray-400 mb-3 line-clamp-2">{task.description}</p>
      )}

      {/* Dependencies */}
      {task.dependencies.length > 0 && (
        <div className="mb-2">
          <span className="text-[10px] text-gray-500 uppercase">Depends on ({task.dependencies.length})</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {task.dependencies.map((depId) => {
              const depNode = graph.get(depId)
              return (
                <button
                  key={depId}
                  onClick={() => onNavigate(depId)}
                  className={`text-[10px] font-mono px-2 py-0.5 rounded border transition hover:bg-white/5 ${
                    depNode?.task.status === 'completed'
                      ? 'border-green-500/30 text-green-400'
                      : 'border-orange-500/30 text-orange-400'
                  }`}
                >
                  {depId} {depNode ? (depNode.task.status === 'completed' ? '✓' : '⏳') : '?'}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Blocks */}
      {blocks.length > 0 && (
        <div className="mb-2">
          <span className="text-[10px] text-gray-500 uppercase">Blocks ({blocks.length})</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {blocks.map((blockId) => (
              <button
                key={blockId}
                onClick={() => onNavigate(blockId)}
                className="text-[10px] font-mono px-2 py-0.5 rounded border border-gray-600 text-gray-400 hover:bg-white/5 transition"
              >
                {blockId}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {task.error_message && (
        <div className="mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400">
          <AlertTriangle className="w-3 h-3 inline mr-1" />
          {task.error_message}
        </div>
      )}
    </div>
  )
}
