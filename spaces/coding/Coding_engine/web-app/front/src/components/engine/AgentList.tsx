// front/src/components/engine/AgentList.tsx
import type { AgentInfo } from '@/services/engineApi';

interface AgentListProps {
  agents: AgentInfo[];
}

export function AgentList({ agents }: AgentListProps) {
  return (
    <div className="flex-1 p-3 overflow-y-auto">
      {agents.map((agent) => (
        <div key={agent.name} className="flex items-center gap-2 py-1.5 text-xs border-b border-border/10 last:border-0">
          <span className={`w-2 h-2 rounded-full shrink-0 ${
            agent.status === 'running' ? 'bg-green-500 animate-pulse'
            : agent.status === 'done' ? 'bg-primary'
            : agent.status === 'failed' ? 'bg-red-500'
            : 'bg-muted-foreground/30'
          }`} />
          <span className="font-medium text-foreground w-32 shrink-0">{agent.name}</span>
          <span className="text-muted-foreground flex-1 truncate">{agent.task}</span>
          <span className="text-muted-foreground/60 shrink-0">
            {agent.elapsed_seconds > 0 ? `${Math.floor(agent.elapsed_seconds / 60)}m ${Math.floor(agent.elapsed_seconds % 60)}s` : '—'}
          </span>
        </div>
      ))}
      {agents.length === 0 && (
        <div className="text-center text-muted-foreground text-sm py-8">
          No agents running. Start generation to see activity.
        </div>
      )}
    </div>
  );
}
