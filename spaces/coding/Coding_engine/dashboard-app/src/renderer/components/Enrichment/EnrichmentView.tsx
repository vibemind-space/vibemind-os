import { useEffect, useState } from 'react'
import {
  useEnrichmentStore,
  COVERAGE_META,
  type EnrichedTaskSummary,
} from '../../stores/enrichmentStore'
import { useEngineStore } from '../../stores/engineStore'
import {
  BookOpen,
  Loader2,
  XCircle,
  ChevronRight,
  BarChart3,
  Search,
  Filter,
  ArrowLeft,
  CheckCircle,
  AlertTriangle,
  FileText,
  Database,
  Map,
} from 'lucide-react'

type SubTab = 'overview' | 'tasks' | 'schema' | 'mapping'

export function EnrichmentView() {
  const {
    overview,
    tasks,
    selectedTask,
    schema,
    mapping,
    isLoading,
    error,
    activeEpicId,
    projectPath,
    filterType,
    setProjectPath,
    fetchOverview,
    fetchTasks,
    fetchTaskDetail,
    fetchSchema,
    fetchMapping,
    setFilterType,
    clearSelection,
  } = useEnrichmentStore()

  const { epics, currentProjectPath } = useEngineStore()
  const [subTab, setSubTab] = useState<SubTab>('overview')
  const [epicInput, setEpicInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Sync project path from engine store
  useEffect(() => {
    if (currentProjectPath && currentProjectPath !== projectPath) {
      setProjectPath(currentProjectPath)
    }
  }, [currentProjectPath, projectPath, setProjectPath])

  // Auto-load first epic if available
  useEffect(() => {
    if (epics.length > 0 && !activeEpicId && projectPath) {
      const firstEpicId = epics[0]?.id
      if (firstEpicId) {
        handleLoadEpic(firstEpicId)
      }
    }
  }, [epics, activeEpicId, projectPath])

  const handleLoadEpic = async (epicId: string) => {
    await fetchOverview(epicId)
    await fetchTasks(epicId)
    fetchSchema()
    fetchMapping()
  }

  const handleEpicSubmit = () => {
    if (epicInput.trim()) {
      handleLoadEpic(epicInput.trim())
    }
  }

  // Filtered tasks
  const filteredTasks = tasks.filter((t) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return t.title.toLowerCase().includes(q) || t.id.toLowerCase().includes(q)
    }
    return true
  })

  // No project path
  if (!projectPath) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
        <BookOpen className="w-8 h-8 text-gray-500" />
        <p>Select a project to view enrichment data</p>
        <p className="text-xs text-gray-600">Load a project in the Epics tab first</p>
      </div>
    )
  }

  // Task detail view
  if (selectedTask) {
    return (
      <div className="h-full flex flex-col bg-engine-dark">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
          <button
            onClick={clearSelection}
            className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h3 className="text-sm font-semibold truncate">{selectedTask.title}</h3>
          <span className="text-xs px-2 py-0.5 bg-gray-700 text-gray-300 rounded ml-auto">
            {selectedTask.type}
          </span>
        </div>
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {/* Task Info */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="bg-engine-darker rounded-lg p-3">
              <span className="text-gray-500">ID</span>
              <p className="font-mono text-gray-300 mt-0.5">{selectedTask.id}</p>
            </div>
            <div className="bg-engine-darker rounded-lg p-3">
              <span className="text-gray-500">Status</span>
              <p className="text-gray-300 mt-0.5 capitalize">{selectedTask.status}</p>
            </div>
          </div>

          {/* Description */}
          <div className="bg-engine-darker rounded-lg p-3">
            <span className="text-xs text-gray-500">Description</span>
            <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">
              {selectedTask.description || 'No description'}
            </p>
          </div>

          {/* Dependencies */}
          {selectedTask.dependencies.length > 0 && (
            <div className="bg-engine-darker rounded-lg p-3">
              <span className="text-xs text-gray-500">Dependencies ({selectedTask.dependencies.length})</span>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {selectedTask.dependencies.map((dep) => (
                  <span key={dep} className="text-xs font-mono px-2 py-0.5 bg-gray-700 text-gray-300 rounded">
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Requirements */}
          {selectedTask.related_requirements.length > 0 && (
            <div className="bg-engine-darker rounded-lg p-3">
              <span className="text-xs text-gray-500">
                Related Requirements ({selectedTask.related_requirements.length})
              </span>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {selectedTask.related_requirements.map((req) => (
                  <span key={req} className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded">
                    {req}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* User Stories */}
          {selectedTask.related_user_stories.length > 0 && (
            <div className="bg-engine-darker rounded-lg p-3">
              <span className="text-xs text-gray-500">
                User Stories ({selectedTask.related_user_stories.length})
              </span>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {selectedTask.related_user_stories.map((us) => (
                  <span key={us} className="text-xs px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded">
                    {us}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Success Criteria */}
          {selectedTask.success_criteria && (
            <div className="bg-engine-darker rounded-lg p-3">
              <span className="text-xs text-gray-500">Success Criteria</span>
              <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">
                {selectedTask.success_criteria}
              </p>
            </div>
          )}

          {/* Enrichment Context (raw JSON) */}
          {selectedTask.enrichment_context && Object.keys(selectedTask.enrichment_context).length > 0 && (
            <div className="bg-engine-darker rounded-lg p-3">
              <span className="text-xs text-gray-500">Enrichment Context</span>
              <pre className="text-xs text-gray-400 mt-1 overflow-auto max-h-60 font-mono">
                {JSON.stringify(selectedTask.enrichment_context, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-engine-dark">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-semibold">Enrichment Pipeline</h2>
          {activeEpicId && (
            <span className="text-xs px-2 py-0.5 bg-cyan-500/20 text-cyan-400 rounded">
              {activeEpicId}
            </span>
          )}
        </div>

        {/* Epic selector */}
        <div className="flex items-center gap-2">
          {epics.length > 0 ? (
            <select
              value={activeEpicId || ''}
              onChange={(e) => e.target.value && handleLoadEpic(e.target.value)}
              className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 focus:border-cyan-500 focus:outline-none"
            >
              <option value="">Select Epic...</option>
              {epics.map((epic) => (
                <option key={epic.id} value={epic.id}>
                  {epic.name || epic.id}
                </option>
              ))}
            </select>
          ) : (
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={epicInput}
                onChange={(e) => setEpicInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleEpicSubmit()}
                placeholder="Epic ID..."
                className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 w-32 focus:border-cyan-500 focus:outline-none"
              />
              <button
                onClick={handleEpicSubmit}
                disabled={!epicInput.trim()}
                className="px-2 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs text-white transition"
              >
                Load
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Sub-tabs */}
      {activeEpicId && (
        <div className="flex border-b border-gray-700/50 px-4">
          <SubTabButton active={subTab === 'overview'} onClick={() => setSubTab('overview')} icon={<BarChart3 className="w-3.5 h-3.5" />} label="Overview" />
          <SubTabButton active={subTab === 'tasks'} onClick={() => setSubTab('tasks')} icon={<FileText className="w-3.5 h-3.5" />} label={`Tasks${tasks.length > 0 ? ` (${tasks.length})` : ''}`} />
          <SubTabButton active={subTab === 'schema'} onClick={() => setSubTab('schema')} icon={<Database className="w-3.5 h-3.5" />} label="Schema" />
          <SubTabButton active={subTab === 'mapping'} onClick={() => setSubTab('mapping')} icon={<Map className="w-3.5 h-3.5" />} label="Mapping" />
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="mx-4 mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span className="text-xs text-red-400 truncate">{error}</span>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-8 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          Loading enrichment data...
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {!activeEpicId && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-2">
            <BarChart3 className="w-8 h-8" />
            <p className="text-sm">Select an epic to view enrichment</p>
          </div>
        )}

        {activeEpicId && !isLoading && subTab === 'overview' && overview && (
          <OverviewPanel overview={overview} />
        )}

        {activeEpicId && !isLoading && subTab === 'tasks' && (
          <TasksPanel
            tasks={filteredTasks}
            filterType={filterType}
            searchQuery={searchQuery}
            typeDistribution={overview?.task_type_distribution || {}}
            onFilterType={setFilterType}
            onSearchChange={setSearchQuery}
            onSelectTask={(t) => fetchTaskDetail(activeEpicId, t.id)}
          />
        )}

        {activeEpicId && !isLoading && subTab === 'schema' && (
          <SchemaPanel schema={schema} />
        )}

        {activeEpicId && !isLoading && subTab === 'mapping' && (
          <MappingPanel mapping={mapping} />
        )}
      </div>
    </div>
  )
}

// ── Sub-components ───────────────────────────────────────────────────────

function SubTabButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition border-b-2 ${
        active ? 'text-cyan-400 border-cyan-400' : 'text-gray-500 border-transparent hover:text-gray-300'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}

function OverviewPanel({ overview }: { overview: import('../../stores/enrichmentStore').EnrichmentOverview }) {
  const coverageEntries = Object.entries(overview.enrichment_coverage).filter(
    ([key]) => key in COVERAGE_META
  )

  const avgCoverage = coverageEntries.length > 0
    ? coverageEntries.reduce((sum, [, v]) => sum + v, 0) / coverageEntries.length
    : 0

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Total Tasks" value={overview.stats.total_tasks} />
        <StatCard
          label="Avg Coverage"
          value={`${(avgCoverage * 100).toFixed(0)}%`}
          color={avgCoverage >= 0.7 ? 'text-green-400' : avgCoverage >= 0.4 ? 'text-yellow-400' : 'text-red-400'}
        />
        <StatCard
          label="Enriched"
          value={overview.enrichment_timestamp
            ? new Date(overview.enrichment_timestamp).toLocaleDateString()
            : 'N/A'}
        />
      </div>

      {/* Coverage Bars */}
      <div className="bg-engine-darker rounded-lg p-4">
        <h3 className="text-xs font-medium text-gray-400 mb-3">Enrichment Coverage</h3>
        <div className="space-y-2.5">
          {coverageEntries.map(([key, value]) => {
            const meta = COVERAGE_META[key]
            if (!meta) return null
            const pct = Math.round(value * 100)
            return (
              <div key={key} className="flex items-center gap-3">
                <span className="text-sm w-5 text-center">{meta.icon}</span>
                <span className="text-xs text-gray-400 w-28 truncate">{meta.label}</span>
                <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${meta.color} rounded-full transition-all duration-300`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className={`text-xs font-mono w-10 text-right ${
                  pct >= 70 ? 'text-green-400' : pct >= 40 ? 'text-yellow-400' : 'text-gray-500'
                }`}>
                  {pct}%
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Task Type Distribution */}
      {Object.keys(overview.task_type_distribution).length > 0 && (
        <div className="bg-engine-darker rounded-lg p-4">
          <h3 className="text-xs font-medium text-gray-400 mb-3">Task Type Distribution</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(overview.task_type_distribution)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <span
                  key={type}
                  className="text-xs px-2.5 py-1 bg-gray-700 text-gray-300 rounded-full"
                >
                  {type} <span className="text-gray-500 ml-1">{count}</span>
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-engine-darker rounded-lg p-3 text-center">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-semibold mt-0.5 ${color || 'text-gray-200'}`}>{value}</p>
    </div>
  )
}

function TasksPanel({
  tasks,
  filterType,
  searchQuery,
  typeDistribution,
  onFilterType,
  onSearchChange,
  onSelectTask,
}: {
  tasks: EnrichedTaskSummary[]
  filterType: string | null
  searchQuery: string
  typeDistribution: Record<string, number>
  onFilterType: (type: string | null) => void
  onSearchChange: (q: string) => void
  onSelectTask: (t: EnrichedTaskSummary) => void
}) {
  const types = Object.keys(typeDistribution)

  return (
    <div className="space-y-3">
      {/* Search + Filter */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search tasks..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 focus:border-cyan-500 focus:outline-none"
          />
        </div>
        {types.length > 0 && (
          <div className="flex items-center gap-1">
            <Filter className="w-3.5 h-3.5 text-gray-500" />
            <select
              value={filterType || ''}
              onChange={(e) => onFilterType(e.target.value || null)}
              className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-gray-300 focus:border-cyan-500 focus:outline-none"
            >
              <option value="">All types</option>
              {types.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Task List */}
      {tasks.length === 0 ? (
        <div className="text-center text-gray-500 text-sm py-8">
          No tasks found
        </div>
      ) : (
        <div className="space-y-1.5">
          {tasks.map((task) => (
            <button
              key={task.id}
              onClick={() => onSelectTask(task)}
              className="w-full flex items-center gap-3 px-3 py-2.5 bg-engine-darker hover:bg-gray-700/50 rounded-lg transition text-left group"
            >
              {/* Score indicator */}
              <div className="relative w-8 h-8 flex-shrink-0">
                <svg className="w-8 h-8 -rotate-90" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="14" fill="none" stroke="#374151" strokeWidth="3" />
                  <circle
                    cx="18" cy="18" r="14"
                    fill="none"
                    stroke={task.enrichment_score >= 0.7 ? '#22c55e' : task.enrichment_score >= 0.4 ? '#eab308' : '#6b7280'}
                    strokeWidth="3"
                    strokeDasharray={`${task.enrichment_score * 88} 88`}
                    strokeLinecap="round"
                  />
                </svg>
                <span className="absolute inset-0 flex items-center justify-center text-[9px] font-mono text-gray-400">
                  {Math.round(task.enrichment_score * 100)}
                </span>
              </div>

              {/* Task info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-200 truncate">{task.title}</span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] font-mono text-gray-600">{task.id}</span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded">{task.type}</span>
                  {task.has_warnings && (
                    <AlertTriangle className="w-3 h-3 text-yellow-500" />
                  )}
                </div>
              </div>

              {/* Enrichment badges (compact) */}
              <div className="flex items-center gap-1 flex-shrink-0">
                {task.has_requirements && <span className="text-[10px]" title="Requirements">📋</span>}
                {task.has_user_stories && <span className="text-[10px]" title="User Stories">👤</span>}
                {task.has_diagrams && <span className="text-[10px]" title="Diagrams">📊</span>}
                {task.has_test_scenarios && <span className="text-[10px]" title="Tests">🧪</span>}
                {task.has_component_spec && <span className="text-[10px]" title="Component">🧩</span>}
                {task.has_accessibility && <span className="text-[10px]" title="A11y">♿</span>}
                {task.has_design_tokens && <span className="text-[10px]" title="Tokens">🎨</span>}
              </div>

              <ChevronRight className="w-4 h-4 text-gray-600 group-hover:text-gray-400 flex-shrink-0" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function SchemaPanel({ schema }: { schema: import('../../stores/enrichmentStore').SchemaOverview | null }) {
  if (!schema || schema.source_count === 0) {
    return (
      <div className="text-center text-gray-500 text-sm py-8">
        <Database className="w-6 h-6 mx-auto mb-2 text-gray-600" />
        No schema discovery data available
        <p className="text-xs text-gray-600 mt-1">Run enrichment pipeline first</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Schema Info */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-engine-darker rounded-lg p-3">
          <span className="text-xs text-gray-500">Project</span>
          <p className="text-sm text-gray-200 mt-0.5">{schema.project_name || 'Unknown'}</p>
        </div>
        <div className="bg-engine-darker rounded-lg p-3">
          <span className="text-xs text-gray-500">Language</span>
          <p className="text-sm text-gray-200 mt-0.5">{schema.language || 'Unknown'}</p>
        </div>
        <div className="bg-engine-darker rounded-lg p-3">
          <span className="text-xs text-gray-500">Requirement Pattern</span>
          <p className="text-sm text-gray-200 font-mono mt-0.5">{schema.requirement_id_pattern || 'N/A'}</p>
        </div>
        <div className="bg-engine-darker rounded-lg p-3">
          <span className="text-xs text-gray-500">Sources Discovered</span>
          <p className="text-sm text-gray-200 mt-0.5">{schema.source_count}</p>
        </div>
      </div>

      {/* Sources */}
      {Object.keys(schema.sources).length > 0 && (
        <div className="bg-engine-darker rounded-lg p-4">
          <h3 className="text-xs font-medium text-gray-400 mb-3">Discovered Sources</h3>
          <div className="space-y-2">
            {Object.entries(schema.sources).map(([key, value]) => (
              <div key={key} className="flex items-start gap-2">
                <CheckCircle className="w-3.5 h-3.5 text-green-500 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <span className="text-xs font-medium text-gray-300">{key}</span>
                  {typeof value === 'object' && value !== null && (
                    <pre className="text-[10px] text-gray-500 mt-0.5 truncate">
                      {JSON.stringify(value).slice(0, 120)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hash */}
      {schema.schema_hash && (
        <div className="text-[10px] text-gray-600 font-mono px-1">
          Schema hash: {schema.schema_hash}
        </div>
      )}
    </div>
  )
}

function MappingPanel({ mapping }: { mapping: import('../../stores/enrichmentStore').MappingOverview | null }) {
  if (!mapping || mapping.total_mappings === 0) {
    return (
      <div className="text-center text-gray-500 text-sm py-8">
        <Map className="w-6 h-6 mx-auto mb-2 text-gray-600" />
        No task mapping data available
        <p className="text-xs text-gray-600 mt-1">Run enrichment pipeline first</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Mapping Stats */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard label="Total Mappings" value={mapping.total_mappings} />
        <StatCard
          label="LLM-Assisted"
          value={mapping.llm_used ? 'Yes' : 'Heuristic'}
          color={mapping.llm_used ? 'text-cyan-400' : 'text-gray-400'}
        />
        <StatCard label="With Types" value={mapping.tasks_with_types} />
        <StatCard label="With Requirements" value={mapping.tasks_with_requirements} />
      </div>

      {/* Type Distribution */}
      {Object.keys(mapping.type_distribution).length > 0 && (
        <div className="bg-engine-darker rounded-lg p-4">
          <h3 className="text-xs font-medium text-gray-400 mb-3">Inferred Type Distribution</h3>
          <div className="space-y-2">
            {Object.entries(mapping.type_distribution)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => {
                const maxCount = Math.max(...Object.values(mapping.type_distribution))
                const pct = Math.round((count / maxCount) * 100)
                return (
                  <div key={type} className="flex items-center gap-2">
                    <span className="text-xs text-gray-400 w-28 truncate font-mono">{type}</span>
                    <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-cyan-500 rounded-full transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-gray-500 w-8 text-right">{count}</span>
                  </div>
                )
              })}
          </div>
        </div>
      )}
    </div>
  )
}
