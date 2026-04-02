// front/src/components/engine/WorkTabs.tsx
import { useState } from 'react';
import { useEngineStore } from '@/stores/engineStore';

interface WorkTabsProps {
  children: {
    vibeCoder: React.ReactNode;
    generationMonitor: React.ReactNode;
  };
}

export function WorkTabs({ children }: WorkTabsProps) {
  const [activeTab, setActiveTab] = useState<'vibe' | 'monitor'>('vibe');
  const { phase, agents } = useEngineStore();
  const isRunning = !['idle', 'complete', 'failed'].includes(phase);

  return (
    <div className="flex flex-col h-full">
      <div className="h-8 bg-background flex items-center px-2 gap-1 border-b border-border/30 shrink-0">
        <button
          onClick={() => setActiveTab('vibe')}
          className={`px-3 py-1 rounded text-xs transition-colors ${
            activeTab === 'vibe'
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          Vibe Coder
        </button>
        <button
          onClick={() => setActiveTab('monitor')}
          className={`px-3 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
            activeTab === 'monitor'
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />}
          Generation Monitor
          {agents.length > 0 && (
            <span className="text-[9px] bg-primary/10 text-primary px-1.5 rounded">
              {agents.length}
            </span>
          )}
        </button>
      </div>
      <div className="flex-1 overflow-hidden">
        <div className={activeTab === 'vibe' ? 'h-full' : 'hidden'}>
          {children.vibeCoder}
        </div>
        <div className={activeTab === 'monitor' ? 'h-full' : 'hidden'}>
          {children.generationMonitor}
        </div>
      </div>
    </div>
  );
}
