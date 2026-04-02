/**
 * Centralized Connection Store
 * 
 * Manages all WebSocket connections across the application:
 * - Tracks active connections and their states
 * - Provides centralized connection management
 * - Supports multiple connection types (live desktop, multi desktop, etc.)
 * - Exposes connection statistics and metrics
 * - Enables connection state synchronization across components
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';
import type { ConnectionStatus, CircuitBreakerState } from '@/hooks/useWebSocketReconnect';

export type ConnectionType = 
  | 'live_desktop'
  | 'multi_desktop'
  | 'desktop_manager'
  | 'web_stream'
  | 'workflow'
  | 'custom';

export interface ConnectionMetrics {
  /** Timestamp when connection was established */
  connectedAt: number | null;
  /** Timestamp of last message received */
  lastMessageAt: number | null;
  /** Timestamp of last ping */
  lastPingAt: number | null;
  /** Total messages received */
  messagesReceived: number;
  /** Total messages sent */
  messagesSent: number;
  /** Total bytes received */
  bytesReceived: number;
  /** Total bytes sent */
  bytesSent: number;
  /** Current latency in ms */
  latency: number;
  /** Average FPS for streaming connections */
  fps: number;
  /** Number of reconnection attempts */
  reconnectAttempts: number;
  /** Number of errors encountered */
  errorCount: number;
}

export interface ConnectionInfo {
  /** Unique connection ID */
  id: string;
  /** Connection type */
  type: ConnectionType;
  /** Client ID */
  clientId: string;
  /** Connection URL */
  url: string;
  /** Current status */
  status: ConnectionStatus;
  /** Circuit breaker state */
  circuitBreakerState: CircuitBreakerState;
  /** Connection metrics */
  metrics: ConnectionMetrics;
  /** Last error message */
  lastError: string | null;
  /** Whether connection is active */
  isActive: boolean;
  /** Custom metadata */
  metadata?: Record<string, any>;
  /** Timestamp when connection was created */
  createdAt: number;
  /** Timestamp when connection was last updated */
  updatedAt: number;
}

interface ConnectionStoreState {
  /** Map of connection ID to connection info - stored as Record for Zustand compatibility */
  connections: Record<string, ConnectionInfo>;
  /** Active connection IDs - stored as array for Zustand compatibility */
  activeConnectionIds: string[];
  /** Global connection statistics */
  globalStats: {
    totalConnections: number;
    activeConnections: number;
    totalBytesReceived: number;
    totalBytesSent: number;
    totalMessagesReceived: number;
    totalMessagesSent: number;
    averageLatency: number;
  };
}

interface ConnectionStoreActions {
  /** Register a new connection */
  registerConnection: (
    id: string,
    type: ConnectionType,
    clientId: string,
    url: string,
    metadata?: Record<string, any>
  ) => void;
  
  /** Update connection status */
  updateConnectionStatus: (
    id: string,
    status: ConnectionStatus,
    error?: string
  ) => void;
  
  /** Update connection metrics */
  updateConnectionMetrics: (
    id: string,
    updates: Partial<ConnectionMetrics>
  ) => void;
  
  /** Update circuit breaker state */
  updateCircuitBreakerState: (
    id: string,
    state: CircuitBreakerState
  ) => void;
  
  /** Record a message sent */
  recordMessageSent: (id: string, bytes: number) => void;
  
  /** Record a message received */
  recordMessageReceived: (id: string, bytes: number) => void;
  
  /** Record a ping */
  recordPing: (id: string) => void;
  
  /** Record a pong */
  recordPong: (id: string, latency: number) => void;
  
  /** Record an error */
  recordError: (id: string, error: string) => void;
  
  /** Record a reconnection attempt */
  recordReconnectionAttempt: (id: string) => void;
  
  /** Remove a connection */
  removeConnection: (id: string) => void;
  
  /** Get connection by ID */
  getConnection: (id: string) => ConnectionInfo | undefined;
  
  /** Get all connections of a specific type */
  getConnectionsByType: (type: ConnectionType) => ConnectionInfo[];
  
  /** Get active connections */
  getActiveConnections: () => ConnectionInfo[];
  
  /** Check if connection exists */
  hasConnection: (id: string) => boolean;
  
  /** Reset all connections */
  resetAllConnections: () => void;
  
  /** Update global statistics */
  updateGlobalStats: () => void;
}

type ConnectionStore = ConnectionStoreState & ConnectionStoreActions;

const initialState: ConnectionStoreState = {
  connections: {},
  activeConnectionIds: [],
  globalStats: {
    totalConnections: 0,
    activeConnections: 0,
    totalBytesReceived: 0,
    totalBytesSent: 0,
    totalMessagesReceived: 0,
    totalMessagesSent: 0,
    averageLatency: 0,
  },
};

export const useConnectionStore = create<ConnectionStore>()(
  devtools((set, get) => ({
      ...initialState,

      registerConnection: (id, type, clientId, url, metadata) => {
        const now = Date.now();
        const connection: ConnectionInfo = {
          id,
          type,
          clientId,
          url,
          status: 'disconnected',
          circuitBreakerState: 'closed',
          metrics: {
            connectedAt: null,
            lastMessageAt: null,
            lastPingAt: null,
            messagesReceived: 0,
            messagesSent: 0,
            bytesReceived: 0,
            bytesSent: 0,
            latency: 0,
            fps: 0,
            reconnectAttempts: 0,
            errorCount: 0,
          },
          lastError: null,
          isActive: false,
          metadata,
          createdAt: now,
          updatedAt: now,
        };

        set((state) => {
          const newConnections = {
            ...state.connections,
            [id]: connection,
          };
          
          return {
            connections: newConnections,
            globalStats: {
              ...state.globalStats,
              totalConnections: Object.keys(newConnections).length,
            },
          };
        });

        // Update global stats
        get().updateGlobalStats();
      },

      updateConnectionStatus: (id, status, error) => {
        set((state) => {
          const connection = state.connections[id];
          if (!connection) return state;

          const updatedConnection: ConnectionInfo = {
            ...connection,
            status,
            lastError: error || connection.lastError,
            isActive: status === 'connected',
            updatedAt: Date.now(),
            metrics: {
              ...connection.metrics,
              connectedAt: status === 'connected' 
                ? (connection.metrics.connectedAt || Date.now())
                : connection.metrics.connectedAt,
            },
          };

          const newConnections = {
            ...state.connections,
            [id]: updatedConnection,
          };

          const newActiveIds = status === 'connected'
            ? state.activeConnectionIds.includes(id)
              ? state.activeConnectionIds
              : [...state.activeConnectionIds, id]
            : state.activeConnectionIds.filter((cid) => cid !== id);

          return {
            connections: newConnections,
            activeConnectionIds: newActiveIds,
          };
        });

        // Update global stats
        get().updateGlobalStats();
      },

      updateConnectionMetrics: (id, updates) => {
        set((state) => {
          const connection = state.connections[id];
          if (!connection) return state;

          const updatedConnection: ConnectionInfo = {
            ...connection,
            metrics: {
              ...connection.metrics,
              ...updates,
            },
            updatedAt: Date.now(),
          };

          const newConnections = {
            ...state.connections,
            [id]: updatedConnection,
          };

          return {
            connections: newConnections,
          };
        });

        // Update global stats
        get().updateGlobalStats();
      },

      updateCircuitBreakerState: (id, state) => {
        set((storeState) => {
          const connection = storeState.connections[id];
          if (!connection) return storeState;

          const updatedConnection: ConnectionInfo = {
            ...connection,
            circuitBreakerState: state,
            updatedAt: Date.now(),
          };

          const newConnections = {
            ...storeState.connections,
            [id]: updatedConnection,
          };

          return {
            connections: newConnections,
          };
        });
      },

      recordMessageSent: (id, bytes) => {
        set((state) => {
          const connection = state.connections[id];
          if (!connection) return state;

          const updatedConnection: ConnectionInfo = {
            ...connection,
            metrics: {
              ...connection.metrics,
              messagesSent: connection.metrics.messagesSent + 1,
              bytesSent: connection.metrics.bytesSent + bytes,
            },
            updatedAt: Date.now(),
          };

          const newConnections = {
            ...state.connections,
            [id]: updatedConnection,
          };

          return {
            connections: newConnections,
          };
        });

        get().updateGlobalStats();
      },

      recordMessageReceived: (id, bytes) => {
        set((state) => {
          const connection = state.connections[id];
          if (!connection) return state;

          const updatedConnection: ConnectionInfo = {
            ...connection,
            metrics: {
              ...connection.metrics,
              messagesReceived: connection.metrics.messagesReceived + 1,
              bytesReceived: connection.metrics.bytesReceived + bytes,
              lastMessageAt: Date.now(),
            },
            updatedAt: Date.now(),
          };

          const newConnections = {
            ...state.connections,
            [id]: updatedConnection,
          };

          return {
            connections: newConnections,
          };
        });

        get().updateGlobalStats();
      },

      recordPing: (id) => {
        get().updateConnectionMetrics(id, {
          lastPingAt: Date.now(),
        });
      },

      recordPong: (id, latency) => {
        get().updateConnectionMetrics(id, {
          latency,
          lastPingAt: Date.now(),
        });
      },

      recordError: (id, error) => {
        set((state) => {
          const connection = state.connections[id];
          if (!connection) return state;

          const updatedConnection: ConnectionInfo = {
            ...connection,
            metrics: {
              ...connection.metrics,
              errorCount: connection.metrics.errorCount + 1,
            },
            lastError: error,
            updatedAt: Date.now(),
          };

          const newConnections = {
            ...state.connections,
            [id]: updatedConnection,
          };

          return {
            connections: newConnections,
          };
        });
      },

      recordReconnectionAttempt: (id) => {
        const connection = get().connections[id];
        if (!connection) return;

        get().updateConnectionMetrics(id, {
          reconnectAttempts: connection.metrics.reconnectAttempts + 1,
        });
      },

      removeConnection: (id) => {
        set((state) => {
          const { [id]: removed, ...newConnections } = state.connections;
          const newActiveIds = state.activeConnectionIds.filter((cid) => cid !== id);

          return {
            connections: newConnections,
            activeConnectionIds: newActiveIds,
            globalStats: {
              ...state.globalStats,
              totalConnections: Object.keys(newConnections).length,
              activeConnections: newActiveIds.length,
            },
          };
        });

        get().updateGlobalStats();
      },

      getConnection: (id) => {
        return get().connections[id];
      },

      getConnectionsByType: (type) => {
        const connections = Object.values(get().connections);
        return connections.filter((conn) => conn.type === type);
      },

      getActiveConnections: () => {
        const state = get();
        return state.activeConnectionIds
          .map((id) => state.connections[id])
          .filter((conn): conn is ConnectionInfo => conn !== undefined);
      },

      hasConnection: (id) => {
        return id in get().connections;
      },

      resetAllConnections: () => {
        set(initialState);
      },

      updateGlobalStats: () => {
        const state = get();
        const connections = Object.values(state.connections);
        const activeConnections = connections.filter((conn) => conn.isActive);

        const totalBytesReceived = connections.reduce(
          (sum, conn) => sum + conn.metrics.bytesReceived,
          0
        );
        const totalBytesSent = connections.reduce(
          (sum, conn) => sum + conn.metrics.bytesSent,
          0
        );
        const totalMessagesReceived = connections.reduce(
          (sum, conn) => sum + conn.metrics.messagesReceived,
          0
        );
        const totalMessagesSent = connections.reduce(
          (sum, conn) => sum + conn.metrics.messagesSent,
          0
        );

        const activeWithLatency = activeConnections.filter(
          (conn) => conn.metrics.latency > 0
        );
        const averageLatency =
          activeWithLatency.length > 0
            ? activeWithLatency.reduce(
                (sum, conn) => sum + conn.metrics.latency,
                0
              ) / activeWithLatency.length
            : 0;

        set({
          globalStats: {
            totalConnections: connections.length,
            activeConnections: activeConnections.length,
            totalBytesReceived,
            totalBytesSent,
            totalMessagesReceived,
            totalMessagesSent,
            averageLatency,
          },
        });
      },
    }),
    { name: 'ConnectionStore' }
  )
);

// Selectors for common use cases
export const useActiveConnections = () => {
  return useConnectionStore((state) => state.getActiveConnections());
};

export const useConnectionStats = () => {
  return useConnectionStore((state) => state.globalStats);
};

export const useConnectionById = (id: string) => {
  return useConnectionStore((state) => state.getConnection(id));
};

export const useConnectionsByType = (type: ConnectionType) => {
  return useConnectionStore((state) => state.getConnectionsByType(type));
};

