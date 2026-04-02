
import React, { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  Search, 
  Filter, 
  Trash2, 
  Download, 
  Play, 
  Pause,
  AlertCircle,
  Info,
  AlertTriangle,
  Bug,
  Zap
} from 'lucide-react';
import type { ConsoleLog, LogLevel, ConsoleFilters } from '@/types/console';

// Mock data for demonstration
const mockLogs: ConsoleLog[] = [
  {
    id: 'log-1',
    timestamp: new Date().toISOString(),
    level: 'execution',
    message: 'Workflow execution started',
    source: 'Execution Engine',
    executionId: 'exec-1'
  },
  {
    id: 'log-2',
    timestamp: new Date(Date.now() - 1000).toISOString(),
    level: 'info',
    message: 'Node "Webhook Trigger" executed successfully',
    source: 'Node Engine',
    nodeId: 'node-1',
    executionId: 'exec-1'
  },
  {
    id: 'log-3',
    timestamp: new Date(Date.now() - 2000).toISOString(),
    level: 'debug',
    message: 'Processing webhook payload: {"user_id": 123, "action": "login"}',
    source: 'Webhook Node',
    nodeId: 'node-1'
  },
  {
    id: 'log-4',
    timestamp: new Date(Date.now() - 3000).toISOString(),
    level: 'warn',
    message: 'Rate limit approaching for API endpoint',
    source: 'HTTP Node',
    nodeId: 'node-2'
  },
  {
    id: 'log-5',
    timestamp: new Date(Date.now() - 4000).toISOString(),
    level: 'error',
    message: 'Failed to connect to database: Connection timeout',
    source: 'Database Node',
    nodeId: 'node-3'
  }
];

const LogLevelBadge: React.FC<{ level: LogLevel }> = ({ level }) => {
  const getConfig = (level: LogLevel) => {
    switch (level) {
      case 'debug':
        return { 
          icon: Bug, 
          className: 'bg-gray-500/10 text-gray-600 border-gray-500/20' 
        };
      case 'info':
        return { 
          icon: Info, 
          className: 'bg-blue-500/10 text-blue-600 border-blue-500/20' 
        };
      case 'warn':
        return { 
          icon: AlertTriangle, 
          className: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20' 
        };
      case 'error':
        return { 
          icon: AlertCircle, 
          className: 'bg-red-500/10 text-red-600 border-red-500/20' 
        };
      case 'execution':
        return { 
          icon: Zap, 
          className: 'bg-purple-500/10 text-purple-600 border-purple-500/20' 
        };
    }
  };

  const config = getConfig(level);
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={`${config.className} gap-1 text-xs`}>
      <Icon className="h-3 w-3" />
      {level}
    </Badge>
  );
};

const ConsoleLog: React.FC = () => {
  const [logs, setLogs] = useState<ConsoleLog[]>(mockLogs);
  const [filters, setFilters] = useState<ConsoleFilters>({
    levels: ['debug', 'info', 'warn', 'error', 'execution'],
    search: ''
  });
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const filteredLogs = logs.filter(log => {
    const matchesLevel = filters.levels.includes(log.level);
    const matchesSearch = !filters.search || 
      log.message.toLowerCase().includes(filters.search.toLowerCase()) ||
      log.source?.toLowerCase().includes(filters.search.toLowerCase());
    return matchesLevel && matchesSearch;
  });

  const toggleLevel = (level: LogLevel) => {
    setFilters(prev => ({
      ...prev,
      levels: prev.levels.includes(level)
        ? prev.levels.filter(l => l !== level)
        : [...prev.levels, level]
    }));
  };

  const clearLogs = () => {
    setLogs([]);
  };

  const exportLogs = () => {
    const logText = filteredLogs.map(log => 
      `[${new Date(log.timestamp).toLocaleString()}] ${log.level.toUpperCase()}: ${log.message} (${log.source})`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `console-logs-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-medium text-foreground">Debug Console</h3>
          <p className="text-xs text-muted-foreground">
            {filteredLogs.length} logs ({logs.length} total)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAutoScroll(!autoScroll)}
            className={autoScroll ? 'bg-primary/10 text-primary' : ''}
          >
            {autoScroll ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            Auto-scroll
          </Button>
          <Button variant="ghost" size="sm" onClick={exportLogs}>
            <Download className="h-3 w-3" />
          </Button>
          <Button variant="ghost" size="sm" onClick={clearLogs}>
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <Input
            placeholder="Search logs..."
            value={filters.search}
            onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
            className="pl-9 h-8 text-xs"
          />
        </div>
        <div className="flex items-center gap-1">
          <Filter className="h-3 w-3 text-muted-foreground" />
          {(['debug', 'info', 'warn', 'error', 'execution'] as LogLevel[]).map(level => (
            <Button
              key={level}
              variant="ghost"
              size="sm"
              onClick={() => toggleLevel(level)}
              className={`h-6 px-2 text-xs ${
                filters.levels.includes(level) ? 'bg-primary/10 text-primary' : 'text-muted-foreground'
              }`}
            >
              {level}
            </Button>
          ))}
        </div>
      </div>

      {/* Log Stream */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-auto space-y-1 font-mono text-xs bg-muted/20 rounded border p-2"
      >
        {filteredLogs.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Bug className="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
            <p>No logs to display</p>
            <p className="text-xs mt-1">Debug output will appear here during workflow execution</p>
          </div>
        ) : (
          filteredLogs.map(log => (
            <div key={log.id} className="flex items-start gap-2 py-1 hover:bg-muted/30 rounded px-1">
              <span className="text-muted-foreground text-xs shrink-0 w-16">
                {formatTimestamp(log.timestamp)}
              </span>
              <LogLevelBadge level={log.level} />
              <div className="flex-1 min-w-0">
                <div className="text-foreground">{log.message}</div>
                {log.source && (
                  <div className="text-muted-foreground text-xs">
                    {log.source}
                    {log.nodeId && ` • Node: ${log.nodeId}`}
                    {log.executionId && ` • Execution: ${log.executionId}`}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ConsoleLog;
