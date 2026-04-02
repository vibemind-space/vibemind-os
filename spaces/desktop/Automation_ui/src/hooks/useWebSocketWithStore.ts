/**
 * Hook to integrate WebSocket connections with Connection Store
 * 
 * This hook wraps useWebSocketReconnect and automatically syncs
 * connection state with the centralized connection store.
 */

import { useEffect, useRef } from 'react';
import { useWebSocketReconnect, type UseWebSocketReconnectOptions } from '@/hooks/useWebSocketReconnect';
import { useConnectionStore, type ConnectionType } from '@/stores/connectionStore';

export interface UseWebSocketWithStoreOptions extends UseWebSocketReconnectOptions {
  /** Unique connection ID */
  connectionId: string;
  /** Connection type */
  connectionType: ConnectionType;
  /** Client ID for this connection */
  clientId: string;
  /** Custom metadata */
  metadata?: Record<string, any>;
}

/**
 * Hook that integrates WebSocket reconnection with the connection store
 */
export const useWebSocketWithStore = (options: UseWebSocketWithStoreOptions) => {
  const {
    connectionId,
    connectionType,
    clientId,
    metadata,
    url,
    handshakeMessage,
    ...reconnectOptions
  } = options;

  const store = useConnectionStore();
  const wsRef = useRef<WebSocket | null>(null);

  // Register connection in store
  useEffect(() => {
    if (!store.hasConnection(connectionId)) {
      store.registerConnection(
        connectionId,
        connectionType,
        clientId,
        url,
        metadata
      );
    }

    return () => {
      // Cleanup: remove connection when component unmounts
      store.removeConnection(connectionId);
    };
  }, [connectionId, connectionType, clientId, url, metadata, store]);

  // Use the reconnection hook
  const websocketHook = useWebSocketReconnect({
    url,
    handshakeMessage,
    ...reconnectOptions,
    onOpen: (ws) => {
      wsRef.current = ws;
      store.updateConnectionStatus(connectionId, 'connected');
      options.onOpen?.(ws);
    },
    onMessage: (event, ws) => {
      // Record message received
      const bytes = typeof event.data === 'string' 
        ? new Blob([event.data]).size 
        : event.data instanceof Blob 
          ? event.data.size 
          : 0;
      store.recordMessageReceived(connectionId, bytes);
      options.onMessage?.(event, ws);
    },
    onClose: (event) => {
      const status: 'disconnected' | 'error' = event.wasClean ? 'disconnected' : 'error';
      store.updateConnectionStatus(
        connectionId,
        status,
        `Connection closed: ${event.code} ${event.reason}`
      );
      options.onClose?.(event);
    },
    onError: (event) => {
      store.recordError(connectionId, 'WebSocket error occurred');
      store.updateConnectionStatus(connectionId, 'error', 'WebSocket error');
      options.onError?.(event);
    },
  });

  // Sync status changes with store
  useEffect(() => {
    store.updateConnectionStatus(connectionId, websocketHook.status, websocketHook.lastError || undefined);
  }, [connectionId, websocketHook.status, websocketHook.lastError, store]);

  // Sync circuit breaker state
  useEffect(() => {
    store.updateCircuitBreakerState(connectionId, websocketHook.circuitBreakerState);
  }, [connectionId, websocketHook.circuitBreakerState, store]);

  // Track reconnection attempts
  useEffect(() => {
    if (websocketHook.reconnectAttempt > 0) {
      store.recordReconnectionAttempt(connectionId);
    }
  }, [connectionId, websocketHook.reconnectAttempt, store]);

  // Wrapper for sendMessage that records metrics
  const sendMessage = (message: any): boolean => {
    const result = websocketHook.sendMessage(message);
    if (result) {
      const bytes = typeof message === 'string' 
        ? new Blob([message]).size 
        : JSON.stringify(message).length;
      store.recordMessageSent(connectionId, bytes);
    }
    return result;
  };

  return {
    ...websocketHook,
    sendMessage,
    connectionId,
    connectionType,
    clientId,
  };
};






