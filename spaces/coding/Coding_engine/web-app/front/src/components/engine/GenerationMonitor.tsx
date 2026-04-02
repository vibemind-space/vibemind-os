// front/src/components/engine/GenerationMonitor.tsx
import { useState, useRef, useEffect, useMemo } from 'react';
import { useGenerationStatus, useEpics } from '@/hooks/useEngine';
import { ProgressHeader } from './ProgressHeader';
import { AgentList } from './AgentList';
import { EpicSidebar } from './EpicSidebar';
import { EpicCard } from './EpicCard';
import { QualityScore } from './QualityScore';
import { TaskBoard } from './TaskBoard';
import { ReviewChat } from './ReviewChat';
import { ClarificationPanel } from './ClarificationPanel';
import { SettingsPanel } from './SettingsPanel';
import { EngineSettingsTabs } from './EngineSettingsTabs';
import { useEngineStore } from '@/stores/engineStore';
import { API_URL } from '@/services/api';
import type { EpicInfo } from '@/services/engineApi';

function LogViewer({ projectName }: { projectName: string }) {
  const wsLogs = useEngineStore(state => state.logs);
  const [polledLogs, setPolledLogs] = useState<string[]>([]);
  const [containerLogs, setContainerLogs] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [logFilter, setLogFilter] = useState<'all' | 'error' | 'warn'>('all');
  const [searchTerm, setSearchTerm] = useState('');

  // Poll backend status + container logs
  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        // Fetch generation status for summary lines
        const res = await fetch(`${API_URL}/dashboard/status?projectId=${encodeURIComponent(projectName)}`);
        if (res.ok) {
          const data = await res.json();
          const lines: string[] = [];
          if (data.phase) lines.push(`[Phase] ${data.phase}`);
          if (data.completed !== undefined) lines.push(`[Progress] ${data.completed}/${data.total} tasks completed (${data.progress_pct || 0}%)`);
          if (data.failed > 0) lines.push(`[Warning] ${data.failed} tasks failed`);
          if (data.last_activity) lines.push(`[Activity] ${data.last_activity}`);
          if (active) setPolledLogs(lines);
        }
      } catch { /* ignore */ }

      // Fetch real container logs
      try {
        const logRes = await fetch(`${API_URL}/engine/docker/project/${encodeURIComponent(projectName)}/logs?tail=200`);
        if (logRes.ok) {
          const logData = await logRes.json();
          const logLines = typeof logData === 'string'
            ? logData.split('\n').filter(Boolean)
            : Array.isArray(logData) ? logData : logData.logs ? logData.logs.split('\n').filter(Boolean) : [];
          if (active && logLines.length > 0) setContainerLogs(logLines);
        }
      } catch { /* container logs not available is fine */ }
    };
    poll();
    const interval = setInterval(poll, 5000);
    return () => { active = false; clearInterval(interval); };
  }, [projectName]);

  // Merge logs: WS logs take priority, then container logs, then polled status
  const displayLogs = wsLogs.length > 0
    ? wsLogs
    : containerLogs.length > 0
      ? containerLogs
      : polledLogs;

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (containerRef.current && autoScroll) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [displayLogs.length, autoScroll]);

  // Detect manual scroll to pause auto-scroll
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 50);
  };

  // Filter logs
  const filteredLogs = useMemo(() => {
    let logs = displayLogs;
    if (logFilter === 'error') logs = logs.filter(l => /error|fail|exception/i.test(l));
    else if (logFilter === 'warn') logs = logs.filter(l => /error|fail|exception|warn/i.test(l));
    if (searchTerm) logs = logs.filter(l => l.toLowerCase().includes(searchTerm.toLowerCase()));
    return logs;
  }, [displayLogs, logFilter, searchTerm]);

  return (
    <div className="flex flex-col h-full flex-1">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-white/5 shrink-0">
        {/* Filter buttons */}
        <div className="flex gap-1">
          {(['all', 'warn', 'error'] as const).map(f => (
            <button key={f} onClick={() => setLogFilter(f)}
              className={`text-[9px] px-2 py-0.5 rounded transition-colors ${logFilter === f ? 'bg-primary/30 text-primary' : 'text-white/40 hover:text-white/60'}`}>
              {f.toUpperCase()}
            </button>
          ))}
        </div>
        {/* Search */}
        <input
          type="text" placeholder="Search logs..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
          className="text-[10px] px-2 py-0.5 bg-white/5 border border-white/10 rounded w-32 text-white/70 placeholder-white/30 focus:outline-none focus:border-primary/50"
        />
        <span className="text-[10px] text-white/40 ml-auto">
          {filteredLogs.length}/{displayLogs.length} lines
          {wsLogs.length > 0 ? ' (live)' : containerLogs.length > 0 ? ' (container)' : ' (status)'}
        </span>
        {!autoScroll && (
          <button
            onClick={() => { setAutoScroll(true); }}
            className="text-[10px] px-2 py-0.5 bg-primary/20 text-primary rounded hover:bg-primary/30"
          >
            Resume auto-scroll
          </button>
        )}
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto font-mono text-xs p-4 bg-black/30 rounded-lg"
      >
        {filteredLogs.length === 0 ? (
          <div className="text-white/30">No logs yet. Start generation to see output.</div>
        ) : (
          filteredLogs.map((log, i) => {
            // Color-code log lines
            const isError = /error|fail|exception/i.test(log);
            const isWarning = /warn|warning/i.test(log);
            const isPhase = /^\[Phase\]/.test(log);
            const colorClass = isError ? 'text-red-400' : isWarning ? 'text-yellow-400' : isPhase ? 'text-blue-400' : 'text-white/70';
            return (
              <div key={i} className={`${colorClass} py-0.5 border-b border-white/5 whitespace-pre-wrap break-all`}>{log}</div>
            );
          })
        )}
      </div>
    </div>
  );
}

function EpicList({ epics }: { epics: EpicInfo[] }) {
  return (
    <div className="flex-1 overflow-y-auto p-4">
      <h3 className="text-sm font-semibold text-white/70 mb-4">Epics ({epics.length})</h3>
      {epics.length === 0 ? (
        <div className="text-white/30 text-sm">No epics loaded yet. Start generation to see epics.</div>
      ) : (
        <div className="space-y-3">
          {epics.map(epic => (
            <div key={epic.id} className="p-4 bg-white/5 rounded-lg border border-white/10">
              <div className="flex justify-between items-center mb-2">
                <div className="font-medium text-white text-sm">{epic.id}</div>
                <span className="text-xs text-green-400 font-semibold">{epic.progress_pct}%</span>
              </div>
              <p className="text-xs text-white/60 mb-3">{epic.name}</p>
              <div className="flex items-center gap-2 mb-1">
                <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-green-500 rounded-full transition-all"
                    style={{ width: `${epic.progress_pct}%` }}
                  />
                </div>
              </div>
              <div className="text-[10px] text-white/40">
                {epic.tasks_complete}/{epic.tasks_total} tasks
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface GenerationMonitorProps {
  projectName: string;
  parallelism: number;
  onParallelismChange: (v: number) => void;
}

const SUB_TABS = ['Agents', 'Epics', 'Tasks', 'Logs', 'Validation', 'Settings'] as const;

export function GenerationMonitor({ projectName, parallelism, onParallelismChange }: GenerationMonitorProps) {
  const { data: status } = useGenerationStatus(projectName);
  const [activeTab, setActiveTab] = useState<string>('Epics');
  const [selectedEpic, setSelectedEpic] = useState<string>('');
  const reviewPaused = useEngineStore(state => state.reviewPaused);
  const taskProgress = useEngineStore(state => state.taskProgress);

  // Resolve project path for epics API via local-projects endpoint
  const [projectPath, setProjectPath] = useState<string | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/v1/dashboard/local-projects');
        if (res.ok) {
          const data = await res.json();
          const match = (data.projects || []).find((p: any) =>
            p.project_id?.includes(projectName) || p.project_name?.toLowerCase().includes(projectName.toLowerCase())
          );
          if (match?.project_path) {
            setProjectPath(match.project_path);
            return;
          }
        }
      } catch { /* ignore */ }
      // Fallback: scan for matching dir name
      setProjectPath(`/app/Data/all_services/${projectName}`);
    })();
  }, [projectName]);

  // Epics from JSON files (via project_path query param)
  const { data: dbEpics } = useEpics(projectPath);
  // Merge JSON epics with live status progress data
  const rawEpics = dbEpics?.epics || [];
  const statusEpics = status?.epics || [];
  const epicsList = rawEpics.map((epic: any) => {
    const live = statusEpics.find((s: any) => s.id === epic.id);
    if (live) {
      return {
        ...epic,
        epic_id: epic.id,
        // EpicCard expects these field names:
        total_tasks: live.tasks_total ?? 0,
        completed_tasks: live.tasks_complete ?? 0,
        failed_tasks: live.tasks_failed ?? 0,
        progress_pct: live.progress_pct ?? 0,
        status: live.progress_pct >= 100 ? 'completed' : live.tasks_failed > 0 ? 'failed' : live.tasks_complete > 0 ? 'running' : 'pending',
      };
    }
    return { ...epic, epic_id: epic.id, total_tasks: 0, completed_tasks: 0, failed_tasks: 0, status: 'pending' };
  });

  // Sync epics from status endpoint into zustand store
  useEffect(() => {
    if (status?.epics && status.epics.length > 0) {
      useEngineStore.setState({ epics: status.epics });
    }
  }, [status?.epics]);

  if (!status) return null;

  // Quality stats — use status data with fallback to taskProgress
  const completed = status.completed || taskProgress.completed || 0;
  const failed = status.failed || taskProgress.failed || 0;
  const total = status.total || taskProgress.total || 0;
  const pending = total - completed - failed;

  return (
    <div className="flex flex-col h-full">
      {/* Header: Progress + Quality Score side by side */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-border/30">
        <div className="flex-1">
          <ProgressHeader
            projectName={projectName}
            phase={status.phase}
            progressPct={status.progress_pct}
            serviceCount={epicsList.length}
            endpointCount={completed}
          />
        </div>
        {total > 0 && (
          <QualityScore completed={completed} failed={failed} pending={pending} total={total} size="sm" />
        )}
      </div>

      {reviewPaused && <ReviewChat projectId={projectName} />}

      {/* Tab Bar */}
      <div className="flex border-b border-border/30 px-2">
        {SUB_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 text-[11px] border-b-2 transition-colors ${
              activeTab === tab
                ? 'text-primary border-primary'
                : 'text-muted-foreground border-transparent hover:text-foreground'
            }`}
          >
            {tab}
            {tab === 'Agents' && status.agents.length > 0 && (
              <span className="ml-1 text-[9px] bg-primary/10 text-primary px-1.5 rounded">
                {status.agents.length}
              </span>
            )}
            {tab === 'Epics' && epicsList.length > 0 && (
              <span className="ml-1 text-[9px] bg-indigo-500/10 text-indigo-400 px-1.5 rounded">
                {epicsList.length}
              </span>
            )}
            {tab === 'Tasks' && failed > 0 && (
              <span className="ml-1 text-[9px] bg-red-500/10 text-red-400 px-1.5 rounded">
                {failed} failed
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'Agents' && <AgentList agents={status.agents} />}
        {activeTab === 'Epics' && (
          <div className="flex flex-1 overflow-hidden">
            <div className="flex-1 overflow-y-auto p-3">
              {epicsList.length === 0 ? (
                <div className="text-white/30 text-sm p-4">No epics loaded. Run import or start generation.</div>
              ) : (
                <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                  {epicsList.map((epic: any) => (
                    <EpicCard
                      key={epic.epic_id}
                      epic={epic}
                      selected={selectedEpic === epic.epic_id}
                      onClick={() => setSelectedEpic(selectedEpic === epic.epic_id ? '' : epic.epic_id)}
                    />
                  ))}
                </div>
              )}
            </div>
            {selectedEpic && <EpicSidebar epics={status.epics} />}
          </div>
        )}
        {activeTab === 'Tasks' && <TaskBoard projectPath={projectName} />}
        {activeTab === 'Validation' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <E2ETestPanel projectPath={projectPath} appUrl="http://localhost:3100" />
            <ClarificationPanel />
          </div>
        )}
        {activeTab === 'Logs' && <LogViewer projectName={projectName} />}
        {activeTab === 'Settings' && (
          <div className="flex-1 overflow-hidden flex">
            <div className="w-1/2 border-r border-border/20">
              <SettingsPanel
                projectName={projectName}
                parallelism={parallelism}
                onParallelismChange={onParallelismChange}
              />
            </div>
            <div className="w-1/2">
              <EngineSettingsTabs />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// ── E2E Test Panel ──────────────────────────────────────────────

function E2ETestPanel({ projectPath, appUrl }: { projectPath: string | null; appUrl: string }) {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const runTests = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8007/api/v1/e2e/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_path: projectPath || '/app/Data/all_services/whatsapp-messaging-service_20260211_025459',
          app_url: appUrl,
          max_tests: 15,
        }),
      });
      const data = await res.json();
      if (data.success) pollStatus();
    } catch (e) {
      console.error('E2E run failed:', e);
    } finally {
      setLoading(false);
    }
  };

  const pollStatus = () => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch('http://localhost:8007/api/v1/e2e/status');
        const data = await res.json();
        setStatus(data);
        if (!data.running) clearInterval(interval);
      } catch { clearInterval(interval); }
    }, 3000);
  };

  return (
    <div className="bg-white/5 rounded-lg border border-white/10 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">E2E Tests (Autonomous)</h3>
        <button
          onClick={runTests}
          disabled={loading || status?.running}
          className="px-3 py-1 text-xs rounded bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white transition-colors"
        >
          {status?.running ? `Running ${status.completed}/${status.total_tests}...` : loading ? 'Starting...' : 'Run E2E Tests'}
        </button>
      </div>
      {status && (
        <div className="space-y-2 text-xs">
          <div className="flex gap-4 text-muted-foreground">
            <span className="text-green-400">{status.passed} passed</span>
            <span className="text-red-400">{status.failed} failed</span>
            <span>{status.total_tests} total</span>
          </div>
          {status.current_test && (
            <div className="text-muted-foreground truncate">Current: {status.current_test}</div>
          )}
          {status.report?.results && (
            <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
              {status.report.results.map((r: any, i: number) => (
                <div key={i} className={`flex gap-2 ${r.passed ? 'text-green-400' : 'text-red-400'}`}>
                  <span>{r.passed ? '+' : '-'}</span>
                  <span className="truncate">{r.test_case?.story_id}: {r.test_case?.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
