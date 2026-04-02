/**
 * useTaskQueue Hook
 *
 * Manages WebSocket connection for Task Queue events.
 * Provides task state and subscription management.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { createWebClient, sendWebSocketMessage } from '@/config/websocketConfig';

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

interface UseTaskQueueOptions {
  autoConnect?: boolean;
  autoSubscribe?: boolean;
  maxTasks?: number;
  onTaskEvent?: (task: Task, event: string) => void;
}

interface UseTaskQueueReturn {
  tasks: Task[];
  isConnected: boolean;
  isSubscribed: boolean;
  connect: () => void;
  disconnect: () => void;
  subscribe: () => void;
  unsubscribe: () => void;
  clearTasks: () => void;
  websocket: WebSocket | null;
  runningTasks: Task[];
  completedTasks: Task[];
  failedTasks: Task[];
}

// ============================================
// Hook
// ============================================

export function useTaskQueue(options: UseTaskQueueOptions = {}): UseTaskQueueReturn {
  const {
    autoConnect = true,
    autoSubscribe = true,
    maxTasks = 50,
    onTaskEvent
  } = options;

  const [tasks, setTasks] = useState<Map<string, Task>>(new Map());
  const [isConnected, setIsConnected] = useState(false);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onTaskEventRef = useRef(onTaskEvent);

  // Keep callback ref up to date
  useEffect(() => {
    onTaskEventRef.current = onTaskEvent;
  }, [onTaskEvent]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const { websocket, handshakeMessage, clientId } = createWebClient('TaskQueue');
      wsRef.current = websocket;

      websocket.onopen = () => {
        sendWebSocketMessage(websocket, handshakeMessage);
        setIsConnected(true);
      };

      websocket.onclose = () => {
        setIsConnected(false);
        setIsSubscribed(false);
      };

      websocket.onerror = (error) => {
        console.error('TaskQueue WebSocket error:', error);
      };

      websocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          // Handle handshake ack
          if (message.type === 'handshake_ack') {
            setIsConnected(true);
            if (autoSubscribe) {
              websocket.send(JSON.stringify({ type: 'subscribe_task_queue' }));
            }
          }

          // Handle subscription confirmation
          if (message.type === 'task_queue_subscribed') {
            setIsSubscribed(true);
          }

          if (message.type === 'task_queue_unsubscribed') {
            setIsSubscribed(false);
          }

          // Handle task events
          if (message.type === 'task_event') {
            const { task_id, status, ...eventData } = message.data;

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

              // Call event handler
              if (onTaskEventRef.current) {
                onTaskEventRef.current(updatedTask, message.event);
              }

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
        } catch (e) {
          console.error('TaskQueue: Failed to parse message', e);
        }
      };
    } catch (error) {
      console.error('TaskQueue: Failed to connect', error);
    }
  }, [autoSubscribe, maxTasks]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsSubscribed(false);
  }, []);

  // Subscribe to task events
  const subscribe = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe_task_queue' }));
    }
  }, []);

  // Unsubscribe from task events
  const unsubscribe = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'unsubscribe_task_queue' }));
    }
  }, []);

  // Clear tasks
  const clearTasks = useCallback(() => {
    setTasks(new Map());
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  // Convert tasks to arrays
  const taskList = Array.from(tasks.values());
  const runningTasks = taskList.filter(t => t.status === 'running' || t.status === 'validating');
  const completedTasks = taskList.filter(t => t.status === 'completed');
  const failedTasks = taskList.filter(t => t.status === 'failed');

  return {
    tasks: taskList.sort((a, b) => b.updated_at.getTime() - a.updated_at.getTime()),
    isConnected,
    isSubscribed,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    clearTasks,
    websocket: wsRef.current,
    runningTasks,
    completedTasks,
    failedTasks
  };
}

export default useTaskQueue;
