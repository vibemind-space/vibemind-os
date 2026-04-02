import { cn } from '@/lib/utils';

interface Epic {
  epic_id: string;
  name: string;
  description?: string;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  status: string;
}

interface EpicCardProps {
  epic: Epic;
  selected?: boolean;
  onClick?: () => void;
}

export function EpicCard({ epic, selected, onClick }: EpicCardProps) {
  const pending = epic.total_tasks - epic.completed_tasks - epic.failed_tasks;
  const pct = epic.total_tasks > 0 ? Math.round((epic.completed_tasks / epic.total_tasks) * 100) : 0;

  const statusColor = {
    completed: 'border-green-500/40 bg-green-500/5',
    running: 'border-blue-500/40 bg-blue-500/5',
    failed: 'border-red-500/40 bg-red-500/5',
    pending: 'border-gray-500/20 bg-gray-500/5',
  }[epic.status] || 'border-gray-500/20 bg-gray-500/5';

  const statusDot = {
    completed: 'bg-green-500',
    running: 'bg-blue-500 animate-pulse',
    failed: 'bg-red-500',
    pending: 'bg-gray-500',
  }[epic.status] || 'bg-gray-500';

  return (
    <div
      onClick={onClick}
      className={cn(
        'rounded-lg border p-3 cursor-pointer transition-all hover:scale-[1.02] hover:shadow-md',
        statusColor,
        selected && 'ring-2 ring-primary shadow-lg',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono text-muted-foreground">{epic.epic_id}</span>
        <span className={cn('w-2 h-2 rounded-full', statusDot)} />
      </div>

      {/* Name */}
      <h4 className="text-xs font-medium text-foreground truncate mb-2" title={epic.name}>
        {epic.name}
      </h4>

      {/* Progress Bar */}
      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden mb-2">
        <div
          className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-green-500 to-emerald-400"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Stats */}
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-muted-foreground">{pct}%</span>
        <div className="flex gap-2">
          <span className="text-green-400">✓{epic.completed_tasks}</span>
          {epic.failed_tasks > 0 && <span className="text-red-400">✗{epic.failed_tasks}</span>}
          {pending > 0 && <span className="text-gray-400">◻{pending}</span>}
        </div>
      </div>

      {/* Total */}
      <div className="text-[9px] text-muted-foreground mt-1 text-right">
        {epic.total_tasks} tasks
      </div>
    </div>
  );
}
