// front/src/components/engine/ProgressHeader.tsx
import type { GenerationPhase } from '@/services/engineApi';

interface ProgressHeaderProps {
  projectName: string;
  phase: GenerationPhase;
  progressPct: number;
  serviceCount: number;
  endpointCount: number;
}

export function ProgressHeader({ projectName, phase, progressPct, serviceCount, endpointCount }: ProgressHeaderProps) {
  return (
    <div className="h-9 bg-background/50 border-b border-border/30 flex items-center px-4 gap-3 shrink-0">
      <span className="text-sm font-semibold text-primary">{projectName}</span>
      <span className="text-xs text-muted-foreground capitalize">Phase: {phase}</span>
      <div className="flex items-center gap-2">
        <div className="w-32 h-1 bg-muted rounded-full">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-green-500 transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <span className="text-xs font-semibold text-green-400">{progressPct}%</span>
      </div>
      <span className="ml-auto text-xs text-muted-foreground">
        {serviceCount} epics · {endpointCount} tasks done
      </span>
    </div>
  );
}
