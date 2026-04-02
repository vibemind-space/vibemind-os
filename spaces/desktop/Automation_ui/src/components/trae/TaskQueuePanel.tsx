/**
 * Task Queue Panel
 *
 * Displays real-time task queue events from Voice → MCP integration.
 * Receives updates via WebSocket from Redis task channels.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Brain,
  Zap,
  Eye,
  GraduationCap,
  RefreshCw,
  Trash2,
  Activity
} from 'lucide-react';

// ============================================
// Types
// ============================================

export type TaskStatus =
  | 'created'
  | 'running'
  | 'validating'
  | 'completed'
  | 'failed'
  | 'learned';

export type TaskRoute =
  | 'LEARNED_PATTERN'
  | 'DIRECT'
  | 'LLM_PLANNER'
  | 'CLAUDE_CLI'
  | 'UNKNOWN'
  | 'ERROR';

export interface TaskValidation {
  success: boolean;
  confidence: number;
  method: string;
  reason?: string;
  observed_changes?: string[];
}

export interface Task {
  id: string;
  text: string;
  source: string;
  status: TaskStatus;
  route?: TaskRoute;
  validation?: TaskValidation;
  learned?: boolean;
  duration_ms?: number;
  error?: string;
  created_at: Date;
  updated_at: Date;
}

export interface TaskEvent {
  type: 'task_event';
  event: string;
  data: {
    task_id: string;
    status: TaskStatus;
    text?: string;
    source?: string;
    route?: TaskRoute;
    success?: boolean;
    validation?: TaskValidation;
    learned?: boolean;
    duration_ms?: number;
    error?: string;
    [key: string]: unknown;
  };
}

interface TaskQueuePanelProps {
  websocket?: WebSocket | null;
  maxTasks?: number;
  className?: string;
}

// ============================================
// Status Badge Component
// ============================================

const StatusBadge: React.FC<{ status: TaskStatus }> = ({ status }) => {
  const config: Record<TaskStatus, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: React.ReactNode; label: string }> = {
    created: { variant: 'outline', icon: <Clock className="w-3 h-3" />, label: 'Erstellt' },
    running: { variant: 'default', icon: <Loader2 className="w-3 h-3 animate-spin" />, label: 'Läuft' },
    validating: { variant: 'secondary', icon: <Eye className="w-3 h-3" />, label: 'Validiert' },
    completed: { variant: 'default', icon: <CheckCircle2 className="w-3 h-3" />, label: 'Fertig' },
    failed: { variant: 'destructive', icon: <XCircle className="w-3 h-3" />, label: 'Fehler' },
    learned: { variant: 'secondary', icon: <GraduationCap className="w-3 h-3" />, label: 'Gelernt' }
  };

  const { variant, icon, label } = config[status] || config.created;

  return (
    <Badge variant={variant} className="flex items-center gap-1">
      {icon}
      <span>{label}</span>
    </Badge>
  );
};

// ============================================
// Route Badge Component
// ============================================

const RouteBadge: React.FC<{ route?: TaskRoute }> = ({ route }) => {
  if (!route || route === 'UNKNOWN') return null;

  const config: Record<TaskRoute, { color: string; icon: React.ReactNode; label: string }> = {
    LEARNED_PATTERN: { color: 'bg-purple-500', icon: <Brain className="w-3 h-3" />, label: 'Gelernt' },
    DIRECT: { color: 'bg-green-500', icon: <Zap className="w-3 h-3" />, label: 'Direkt' },
    LLM_PLANNER: { color: 'bg-blue-500', icon: <Brain className="w-3 h-3" />, label: 'LLM Planner' },
    CLAUDE_CLI: { color: 'bg-orange-500', icon: <Activity className="w-3 h-3" />, label: 'Claude CLI' },
    UNKNOWN: { color: 'bg-gray-500', icon: null, label: 'Unbekannt' },
    ERROR: { color: 'bg-red-500', icon: <XCircle className="w-3 h-3" />, label: 'Fehler' }
  };

  const { color, icon, label } = config[route] || config.UNKNOWN;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs text-white ${color}`}>
      {icon}
      {label}
    </span>
  );
};

// ============================================
// Task Item Component
// ============================================

const TaskItem: React.FC<{ task: Task }> = ({ task }) => {
  const isActive = task.status === 'running' || task.status === 'validating';

  return (
    <div className={`p-3 rounded-lg border ${isActive ? 'bg-blue-50 border-blue-200' : 'bg-white border-gray-200'}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate" title={task.text}>
            {task.text}
          </p>
          <p className="text-xs text-muted-foreground">
            {task.source} • {task.created_at.toLocaleTimeString()}
          </p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <RouteBadge route={task.route} />
          <StatusBadge status={task.status} />
        </div>
      </div>

      {/* Validation Result */}
      {task.validation && (
        <div className={`mt-2 p-2 rounded text-xs ${task.validation.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Eye className="w-3 h-3" />
              {task.validation.method}
            </span>
            <span>{Math.round(task.validation.confidence * 100)}% Confidence</span>
          </div>
          {task.validation.reason && (
            <p className="mt-1 text-xs opacity-75">{task.validation.reason}</p>
          )}
        </div>
      )}

      {/* Error */}
      {task.error && (
        <div className="mt-2 p-2 rounded bg-red-50 text-red-700 text-xs">
          <XCircle className="w-3 h-3 inline mr-1" />
          {task.error}
        </div>
      )}

      {/* Learning Indicator */}
      {task.learned && (
        <div className="mt-2 p-2 rounded bg-purple-50 text-purple-700 text-xs flex items-center gap-1">
          <GraduationCap className="w-3 h-3" />
          Neues Pattern gelernt!
        </div>
      )}

      {/* Duration */}
      {task.duration_ms !== undefined && task.status === 'completed' && (
        <p className="mt-2 text-xs text-muted-foreground text-right">
          {(task.duration_ms / 1000).toFixed(2)}s
        </p>
      )}
    </div>
  );
};

// ============================================
// Main Component
// ============================================

export const TaskQueuePanel: React.FC<TaskQueuePanelProps> = ({
  websocket,
  maxTasks = 50,
  className = ''
}) => {
  const [tasks, setTasks] = useState<Map<string, Task>>(new Map());
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Subscribe to task queue events
  const subscribe = useCallback(() => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: 'subscribe_task_queue' }));
      setIsSubscribed(true);
    }
  }, [websocket]);

  // Unsubscribe from task queue events
  const unsubscribe = useCallback(() => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: 'unsubscribe_task_queue' }));
      setIsSubscribed(false);
    }
  }, [websocket]);

  // Handle incoming WebSocket messages
  useEffect(() => {
    if (!websocket) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data);

        // Handle task events
        if (message.type === 'task_event') {
          const taskEvent = message as TaskEvent;
          const { task_id, status, ...eventData } = taskEvent.data;

          setTasks(prev => {
            const newTasks = new Map(prev);
            const existingTask = newTasks.get(task_id);

            const updatedTask: Task = {
              id: task_id,
              text: eventData.text || existingTask?.text || 'Unknown',
              source: eventData.source || existingTask?.source || 'voice',
              status,
              route: eventData.route || existingTask?.route,
              validation: eventData.validation || existingTask?.validation,
              learned: eventData.learned || existingTask?.learned,
              duration_ms: eventData.duration_ms || existingTask?.duration_ms,
              error: eventData.error || existingTask?.error,
              created_at: existingTask?.created_at || new Date(),
              updated_at: new Date()
            };

            newTasks.set(task_id, updatedTask);

            // Limit number of tasks
            if (newTasks.size > maxTasks) {
              const oldestKey = newTasks.keys().next().value;
              if (oldestKey) {
                newTasks.delete(oldestKey);
              }
            }

            return newTasks;
          });
        }

        // Handle subscription confirmation
        if (message.type === 'task_queue_subscribed') {
          setIsSubscribed(true);
        }

        if (message.type === 'task_queue_unsubscribed') {
          setIsSubscribed(false);
        }

        // Handle handshake ack
        if (message.type === 'handshake_ack') {
          setIsConnected(true);
          // Auto-subscribe after handshake
          subscribe();
        }
      } catch (e) {
        console.error('TaskQueuePanel: Failed to parse message', e);
      }
    };

    const handleOpen = () => setIsConnected(true);
    const handleClose = () => {
      setIsConnected(false);
      setIsSubscribed(false);
    };

    websocket.addEventListener('message', handleMessage);
    websocket.addEventListener('open', handleOpen);
    websocket.addEventListener('close', handleClose);

    // Check current state
    if (websocket.readyState === WebSocket.OPEN) {
      setIsConnected(true);
    }

    return () => {
      websocket.removeEventListener('message', handleMessage);
      websocket.removeEventListener('open', handleOpen);
      websocket.removeEventListener('close', handleClose);
    };
  }, [websocket, subscribe, maxTasks]);

  // Auto-scroll when new tasks arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0; // Scroll to top (newest first)
    }
  }, [tasks]);

  // Convert tasks to sorted array (newest first)
  const taskList = Array.from(tasks.values()).sort(
    (a, b) => b.updated_at.getTime() - a.updated_at.getTime()
  );

  // Stats
  const runningCount = taskList.filter(t => t.status === 'running' || t.status === 'validating').length;
  const completedCount = taskList.filter(t => t.status === 'completed').length;
  const failedCount = taskList.filter(t => t.status === 'failed').length;

  // Clear tasks
  const clearTasks = () => setTasks(new Map());

  return (
    <Card className={`flex flex-col ${className}`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Activity className="w-5 h-5" />
            Task Queue
          </CardTitle>
          <div className="flex items-center gap-2">
            {/* Connection Status */}
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />

            {/* Subscribe/Unsubscribe Toggle */}
            <Button
              variant={isSubscribed ? 'secondary' : 'outline'}
              size="sm"
              onClick={() => isSubscribed ? unsubscribe() : subscribe()}
              disabled={!isConnected}
            >
              {isSubscribed ? 'Live' : 'Pausiert'}
            </Button>

            {/* Clear Button */}
            <Button variant="ghost" size="sm" onClick={clearTasks}>
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Stats Bar */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-2">
          <span className="flex items-center gap-1">
            <Loader2 className="w-3 h-3" />
            {runningCount} aktiv
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-green-500" />
            {completedCount} fertig
          </span>
          <span className="flex items-center gap-1">
            <XCircle className="w-3 h-3 text-red-500" />
            {failedCount} fehler
          </span>
        </div>
      </CardHeader>

      <CardContent className="flex-1 p-2">
        <ScrollArea className="h-[400px]" ref={scrollRef}>
          {taskList.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <Activity className="w-12 h-12 mb-2 opacity-50" />
              <p className="text-sm">Keine Tasks</p>
              <p className="text-xs">Voice Commands werden hier angezeigt</p>
            </div>
          ) : (
            <div className="space-y-2 p-1">
              {taskList.map(task => (
                <TaskItem key={task.id} task={task} />
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
};

export default TaskQueuePanel;
