// front/src/pages/EngineEditor.tsx
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useEngineProject, useGenerationStatus, useStartGeneration, useStopGeneration } from '@/hooks/useEngine';
import { useEngineStore } from '@/stores/engineStore';
import { WorkTabs } from '@/components/engine/WorkTabs';
import { VncPreview } from '@/components/engine/VncPreview';
import { GenerationMonitor } from '@/components/engine/GenerationMonitor';
import { useEngineSettings } from '@/services/engineSettingsApi';
import { Play, Square, ArrowLeft, ChevronDown } from 'lucide-react';
import { Link } from 'react-router-dom';

const EngineEditor = () => {
  const { projectName } = useParams<{ projectName: string }>();
  const { data: project, isLoading } = useEngineProject(projectName || '');
  const { data: status } = useGenerationStatus(projectName || '');
  const startGen = useStartGeneration();
  const stopGen = useStopGeneration();
  const [parallelism, setParallelism] = useState(1);
  const { connect, disconnect, setActiveProject, connected } = useEngineStore();

  // Auto-connect WebSocket and set active project on mount
  useEffect(() => {
    if (projectName) {
      setActiveProject(projectName);
      connect();
    }
    return () => {
      disconnect();
      setActiveProject(null);
    };
  }, [projectName]);

  if (!projectName) return <div>No project selected</div>;
  if (isLoading) return <div className="flex items-center justify-center h-screen text-muted-foreground">Loading project...</div>;

  const phase = status?.phase || 'idle';
  const isRunning = phase !== 'idle' && phase !== 'complete' && phase !== 'failed';
  const cleanName = projectName
    .replace(/_\d{8}_\d{6}$/, '')
    .replace(/[-_]/g, ' ');

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Top Bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border/30 bg-background/80 backdrop-blur">
        <Link to="/projects" className="text-muted-foreground hover:text-foreground transition">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-semibold truncate capitalize">{cleanName}</h1>
          <p className="text-[10px] text-muted-foreground">
            {project?.has_user_stories && 'User Stories'}{project?.has_api_docs && ' · API Docs'}{project?.has_data_dictionary && ' · Data Dict'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* WS connection indicator */}
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} title={connected ? 'WebSocket connected' : 'WebSocket disconnected'} />
          {/* Parallelism indicator */}
          {parallelism > 1 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border bg-yellow-500/10 text-yellow-400 border-yellow-500/25">
              {parallelism}x parallel
            </span>
          )}
          {/* Phase Badge */}
          <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
            phase === 'idle' ? 'bg-gray-500/10 text-gray-400 border-gray-500/25' :
            phase === 'complete' ? 'bg-green-500/10 text-green-400 border-green-500/25' :
            phase === 'failed' ? 'bg-red-500/10 text-red-400 border-red-500/25' :
            'bg-blue-500/10 text-blue-400 border-blue-500/25 animate-pulse'
          }`}>
            {phase}
          </span>
          {/* Start/Stop Button */}
          {isRunning ? (
            <button
              onClick={() => stopGen.mutate(projectName)}
              disabled={stopGen.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-500 rounded text-xs font-medium text-white transition disabled:opacity-50"
            >
              <Square className="w-3 h-3" />
              Stop
            </button>
          ) : (
            <button
              onClick={() => startGen.mutate({
                name: projectName,
                projectPath: project?.path,
                parallelism,
              })}
              disabled={startGen.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded text-xs font-medium text-white transition disabled:opacity-50"
            >
              <Play className="w-3 h-3" />
              {startGen.isPending ? 'Starting...' : 'Start Generation'}
            </button>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {startGen.isError && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/25 text-xs text-red-400">
          {(startGen.error as Error).message}
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Work Area (70%) */}
        <div className="flex-[7] min-w-0">
          <WorkTabs>
            {{
              vibeCoder: (
                <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                  <p className="text-lg mb-2">Vibe Coder</p>
                  <p className="text-sm">Chat + Code Editor for live adjustments</p>
                  {phase === 'idle' && (
                    <p className="text-xs mt-4 text-muted-foreground/60">
                      Press "Start Generation" above to begin building
                    </p>
                  )}
                </div>
              ),
              generationMonitor: (
                <GenerationMonitor
                  projectName={projectName}
                  parallelism={parallelism}
                  onParallelismChange={setParallelism}
                />
              ),
            }}
          </WorkTabs>
        </div>

        {/* Right: VNC Preview (Always Visible, 30%) */}
        <div className="flex-[3] min-w-0">
          <VncPreview projectName={projectName} />
        </div>
      </div>
    </div>
  );
};

export default EngineEditor;
