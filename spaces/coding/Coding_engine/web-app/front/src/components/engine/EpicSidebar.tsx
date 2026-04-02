// front/src/components/engine/EpicSidebar.tsx
import type { EpicInfo } from '@/services/engineApi';

interface EpicSidebarProps {
  epics: EpicInfo[];
}

export function EpicSidebar({ epics }: EpicSidebarProps) {
  return (
    <div className="w-60 border-l border-border/30 p-3 overflow-y-auto">
      {epics.map((epic) => (
        <div key={epic.id} className="bg-muted/30 rounded-lg p-2.5 mb-2">
          <div className="flex justify-between text-xs">
            <span className="font-medium text-foreground">{epic.name}</span>
            <span className="font-semibold text-green-400">{epic.progress_pct}%</span>
          </div>
          <div className="h-0.5 bg-background rounded-full mt-1.5">
            <div
              className="h-full rounded-full bg-gradient-to-r from-primary to-green-500"
              style={{ width: `${epic.progress_pct}%` }}
            />
          </div>
          <div className="text-[10px] text-muted-foreground mt-1">
            {epic.tasks_complete}/{epic.tasks_total} tasks
          </div>
        </div>
      ))}
      {epics.length === 0 && (
        <div className="text-center text-muted-foreground text-xs py-4">
          No epics loaded yet.
        </div>
      )}
    </div>
  );
}
