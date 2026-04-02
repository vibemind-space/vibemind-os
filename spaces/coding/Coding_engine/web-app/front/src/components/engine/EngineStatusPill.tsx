// front/src/components/engine/EngineStatusPill.tsx
import { useEngineStore } from '@/stores/engineStore';

export function EngineStatusPill() {
  const { connected, phase, progressPct, activeProject } = useEngineStore();

  if (phase === 'idle' || !activeProject) return null;

  const isRunning = !['idle', 'complete', 'failed'].includes(phase);

  return (
    <div className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-full border ${
      isRunning
        ? 'bg-green-500/10 text-green-400 border-green-500/25'
        : phase === 'complete'
        ? 'bg-blue-500/10 text-blue-400 border-blue-500/25'
        : 'bg-red-500/10 text-red-400 border-red-500/25'
    }`}>
      {isRunning && (
        <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
      )}
      <span>Engine · {progressPct}% · {phase}</span>
    </div>
  );
}
