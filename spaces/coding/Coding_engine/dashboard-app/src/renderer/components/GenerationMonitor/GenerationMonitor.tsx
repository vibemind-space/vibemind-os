import { useEngineStore } from '../../stores/engineStore'
import { useProjectStore } from '../../stores/projectStore'
import { Activity, Terminal, CheckCircle, XCircle, Clock, Loader2, ListChecks, Layers, Cpu, BookOpen, GitBranch, Zap } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { TaskList } from './TaskList'
import { EpicSelector } from './EpicSelector'
import { LLMConfigEditor } from '../Settings/LLMConfigEditor'
import { EnrichmentView } from '../Enrichment/EnrichmentView'
import { TaskDependencyBoard } from '../TaskBoard/TaskDependencyBoard'
import { VibeChat } from '../VibeChat'

export function GenerationMonitor() {
  const { generationProgress, agentActivity, logs, epics, runEpic, rerunEpic, generateAllTaskLists, loadEpics, currentProjectPath, wsConnected, taskProgress, epicTaskLists, selectedEpic } = useEngineStore()
  const { activeProjectId, getProject } = useProjectStore()
  const [activeTab, setActiveTab] = useState<'progress' | 'agents' | 'epics' | 'tasks' | 'deps' | 'logs' | 'enrichment' | 'llm-config' | 'vibe'>('progress')
  const logsEndRef = useRef<HTMLDivElement>(null)

  const activeProject = activeProjectId ? getProject(activeProjectId) : null

  // Debug: Log tab switches
  useEffect(() => {
    console.log(`[Monitor] Tab switched to: ${activeTab}`)
    console.log(`[Monitor] State snapshot:`, {
      activeProjectId,
      activeProjectName: activeProject?.name || 'none',
      activeProjectStatus: activeProject?.status || 'none',
      wsConnected,
      generationProgress,
      agentCount: agentActivity.length,
      epicCount: epics.length,
      logCount: logs.length,
      currentProjectPath,
      taskProgress,
      selectedEpic,
    })
  }, [activeTab])

  // Debug: Log data changes per tab
  useEffect(() => {
    if (activeTab === 'progress') {
      console.log(`[Monitor:Progress] progress=${generationProgress}% | project=${activeProject?.name || 'none'} | status=${activeProject?.status || 'idle'}`)
    }
  }, [activeTab, generationProgress, activeProject?.status])

  useEffect(() => {
    if (activeTab === 'agents') {
      console.log(`[Monitor:Agents] ${agentActivity.length} agents active:`, agentActivity.slice(-5).map(a => `${a.agent}:${a.status}`))
    }
  }, [activeTab, agentActivity.length])

  useEffect(() => {
    if (activeTab === 'epics') {
      console.log(`[Monitor:Epics] ${epics.length} epics loaded:`, epics.map(e => `${e.id}:${e.status}(${e.progress_percent}%)`))
    }
  }, [activeTab, epics.length])

  useEffect(() => {
    if (activeTab === 'tasks') {
      const taskListKeys = Object.keys(epicTaskLists)
      const totalTasks = taskListKeys.reduce((sum, k) => sum + (epicTaskLists[k]?.tasks?.length || 0), 0)
      console.log(`[Monitor:Tasks] ${totalTasks} tasks across ${taskListKeys.length} epics | progress:`, taskProgress)
    }
  }, [activeTab, taskProgress, Object.keys(epicTaskLists).length])

  useEffect(() => {
    if (activeTab === 'logs') {
      console.log(`[Monitor:Logs] ${logs.length} log entries (showing last 3):`, logs.slice(-3))
    }
  }, [activeTab, logs.length])

  // Load epics when project changes (use requirementsPath for RE projects, outputDir for legacy)
  useEffect(() => {
    if (activeProject) {
      const epicPath = activeProject.requirementsPath || activeProject.outputDir
      const pathMatch = epicPath === currentProjectPath
      console.log(`[Monitor] Project changed: ${activeProject.name}`)
      console.log(`[Monitor]   requirementsPath=${activeProject.requirementsPath || '(empty)'}`)
      console.log(`[Monitor]   outputDir=${activeProject.outputDir || '(empty)'}`)
      console.log(`[Monitor]   epicPath=${epicPath || '(empty)'}`)
      console.log(`[Monitor]   currentProjectPath=${currentProjectPath || '(empty)'}`)
      console.log(`[Monitor]   pathMatch=${pathMatch} | epicCount=${epics.length}`)
      // Always load if path changed, or if path matches but epics are empty (store was reset)
      const shouldLoad = epicPath && (!pathMatch || epics.length === 0)
      console.log(`[Monitor]   shouldLoad=${shouldLoad} (reason: ${!pathMatch ? 'path changed' : epics.length === 0 ? 'epics empty despite path match' : 'already loaded'})`)
      if (shouldLoad) {
        console.log(`[Monitor] >>> Loading epics from: ${epicPath}`)
        loadEpics(epicPath)
      }
    } else {
      console.log(`[Monitor] No active project selected (activeProjectId=${activeProjectId})`)
    }
  }, [activeProject?.id, activeProject?.requirementsPath, activeProject?.outputDir, currentProjectPath, loadEpics])

  useEffect(() => {
    if (activeTab === 'logs') {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, activeTab])

  return (
    <div className="h-full flex flex-col bg-engine-dark">
      {/* Tabs */}
      <div className="flex border-b border-gray-700">
        <TabButton
          active={activeTab === 'progress'}
          onClick={() => setActiveTab('progress')}
          icon={<Activity className="w-4 h-4" />}
          label="Progress"
        />
        <TabButton
          active={activeTab === 'agents'}
          onClick={() => setActiveTab('agents')}
          icon={<Loader2 className="w-4 h-4" />}
          label="Agents"
        />
        <TabButton
          active={activeTab === 'epics'}
          onClick={() => setActiveTab('epics')}
          icon={<Layers className="w-4 h-4" />}
          label={`Epics${epics.length > 0 ? ` (${epics.length})` : ''}`}
        />
        <TabButton
          active={activeTab === 'tasks'}
          onClick={() => setActiveTab('tasks')}
          icon={<ListChecks className="w-4 h-4" />}
          label="Tasks"
        />
        <TabButton
          active={activeTab === 'deps'}
          onClick={() => setActiveTab('deps')}
          icon={<GitBranch className="w-4 h-4" />}
          label="Dependencies"
        />
        <TabButton
          active={activeTab === 'logs'}
          onClick={() => setActiveTab('logs')}
          icon={<Terminal className="w-4 h-4" />}
          label="Logs"
        />
        <TabButton
          active={activeTab === 'enrichment'}
          onClick={() => setActiveTab('enrichment')}
          icon={<BookOpen className="w-4 h-4" />}
          label="Enrichment"
        />
        <TabButton
          active={activeTab === 'llm-config'}
          onClick={() => setActiveTab('llm-config')}
          icon={<Cpu className="w-4 h-4" />}
          label="LLM Config"
        />
        <TabButton
          active={activeTab === 'vibe'}
          onClick={() => setActiveTab('vibe')}
          icon={<Zap className="w-4 h-4" />}
          label="Vibe"
        />
      </div>

      {/* Content */}
      {activeTab === 'vibe' ? (
        <div className="flex-1 overflow-hidden">
          <VibeChat
            projectId={activeProject?.id || 'default'}
            outputDir={activeProject?.outputDir || '.'}
          />
        </div>
      ) : activeTab === 'llm-config' ? (
        <div className="flex-1 overflow-hidden">
          <LLMConfigEditor />
        </div>
      ) : activeTab === 'enrichment' ? (
        <div className="flex-1 overflow-hidden">
          <EnrichmentView />
        </div>
      ) : activeTab === 'deps' ? (
        <div className="flex-1 overflow-hidden">
          <TaskDependencyBoard />
        </div>
      ) : (
      <div className="flex-1 overflow-auto p-4">
        {activeTab === 'progress' && (
          <ProgressView
            progress={activeProject?.progress ?? generationProgress}
            status={activeProject?.status}
          />
        )}
        {activeTab === 'agents' && <AgentActivityView activity={agentActivity} />}
        {activeTab === 'epics' && (
          <EpicSelector
            onRunEpic={runEpic}
            onRerunEpic={rerunEpic}
            onGenerateTaskList={generateAllTaskLists}
          />
        )}
        {activeTab === 'tasks' && <TaskList />}
        {activeTab === 'logs' && <LogsView logs={logs} logsEndRef={logsEndRef} />}
      </div>
      )}
    </div>
  )
}

interface TabButtonProps {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}

function TabButton({ active, onClick, icon, label }: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition ${
        active
          ? 'text-engine-primary border-b-2 border-engine-primary'
          : 'text-gray-400 hover:text-white'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}

interface ProgressViewProps {
  progress: number
  status?: string
}

function ProgressView({ progress, status }: ProgressViewProps) {
  console.log(`[Monitor:Progress] Rendering: progress=${progress}% status=${status || 'undefined'}`)
  const stages = [
    { name: 'Analyzing Requirements', threshold: 10 },
    { name: 'Generating Code', threshold: 40 },
    { name: 'Running Validators', threshold: 60 },
    { name: 'Building Project', threshold: 80 },
    { name: 'Running Tests', threshold: 95 },
    { name: 'Complete', threshold: 100 }
  ]

  const currentStage = stages.find((s) => progress < s.threshold) || stages[stages.length - 1]

  return (
    <div className="space-y-6">
      {/* Overall Progress */}
      <div>
        <div className="flex justify-between text-sm mb-2">
          <span className="text-gray-400">Overall Progress</span>
          <span className="font-mono">{progress}%</span>
        </div>
        <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-engine-primary to-engine-secondary transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Current Stage */}
      <div className="flex items-center gap-3 p-4 bg-engine-darker rounded-lg">
        {status === 'generating' ? (
          <Loader2 className="w-6 h-6 text-yellow-500 animate-spin" />
        ) : progress === 100 ? (
          <CheckCircle className="w-6 h-6 text-green-500" />
        ) : (
          <Clock className="w-6 h-6 text-gray-500" />
        )}
        <div>
          <p className="font-medium">{currentStage.name}</p>
          <p className="text-sm text-gray-400">
            {status === 'generating' ? 'In progress...' : status === 'idle' ? 'Waiting to start' : status}
          </p>
        </div>
      </div>

      {/* Stage Checklist */}
      <div className="space-y-2">
        {stages.slice(0, -1).map((stage, index) => {
          const isComplete = progress >= stage.threshold
          const isCurrent = currentStage === stage

          return (
            <div
              key={stage.name}
              className={`flex items-center gap-3 p-2 rounded ${
                isCurrent ? 'bg-engine-primary/10' : ''
              }`}
            >
              {isComplete ? (
                <CheckCircle className="w-4 h-4 text-green-500" />
              ) : isCurrent ? (
                <Loader2 className="w-4 h-4 text-yellow-500 animate-spin" />
              ) : (
                <div className="w-4 h-4 rounded-full border border-gray-600" />
              )}
              <span className={isComplete ? 'text-gray-300' : 'text-gray-500'}>
                {stage.name}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface AgentActivityViewProps {
  activity: Array<{
    agent: string
    action: string
    timestamp: string
    status: 'running' | 'completed' | 'failed'
  }>
}

function AgentActivityView({ activity }: AgentActivityViewProps) {
  if (activity.length === 0) {
    console.log('[Monitor:Agents] Empty state — no agent activity received via WebSocket')
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>No agent activity yet. Start a generation to see agents.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {activity.map((item, index) => (
        <div
          key={index}
          className="flex items-start gap-3 p-3 bg-engine-darker rounded-lg"
        >
          {item.status === 'running' ? (
            <Loader2 className="w-4 h-4 text-yellow-500 animate-spin mt-0.5" />
          ) : item.status === 'completed' ? (
            <CheckCircle className="w-4 h-4 text-green-500 mt-0.5" />
          ) : (
            <XCircle className="w-4 h-4 text-red-500 mt-0.5" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <span className="font-medium text-sm">{item.agent}</span>
              <span className="text-xs text-gray-500">{item.timestamp}</span>
            </div>
            <p className="text-sm text-gray-400 truncate">{item.action}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

interface LogsViewProps {
  logs: string[]
  logsEndRef: React.RefObject<HTMLDivElement>
}

function LogsView({ logs, logsEndRef }: LogsViewProps) {
  if (logs.length === 0) {
    console.log('[Monitor:Logs] Empty state — no logs received via WebSocket')
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>No logs yet. Start a generation to see logs.</p>
      </div>
    )
  }

  return (
    <div className="font-mono text-xs space-y-1">
      {logs.map((log, index) => (
        <div
          key={index}
          className={`p-1 rounded ${
            log.includes('ERROR') || log.includes('FAILED')
              ? 'bg-red-500/10 text-red-400'
              : log.includes('SUCCESS') || log.includes('PASSED')
              ? 'bg-green-500/10 text-green-400'
              : log.includes('WARN')
              ? 'bg-yellow-500/10 text-yellow-400'
              : 'text-gray-400'
          }`}
        >
          {log}
        </div>
      ))}
      <div ref={logsEndRef} />
    </div>
  )
}
