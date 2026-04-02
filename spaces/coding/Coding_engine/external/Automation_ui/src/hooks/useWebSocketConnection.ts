/**
 * Enhanced WebSocket hook for TRAE Unity AI Platform
 * Provides robust WebSocket connection management with auto-reconnect
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { WEBSOCKET_CONFIG, createHandshakeMessage, isWebSocketConnected, sendWebSocketMessage } from '@/config/websocketConfig';

interface UseWebSocketOptions {
  url?: string;
  clientType: string;
  clientId?: string;
  capabilities?: string[];
  autoConnect?: boolean;
  autoReconnect?: boolean;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
  onOpen?: (event: Event) => void;
  onMessage?: (event: MessageEvent) => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
}

export const useWebSocketConnection = ({
  url,
  clientType,
  clientId: providedClientId,
  capabilities = [],
  autoConnect = true,
  autoReconnect = true,
  reconnectDelay = WEBSOCKET_CONFIG.CONNECTION.RECONNECT_DELAY,
  maxReconnectAttempts = WEBSOCKET_CONFIG.CONNECTION.MAX_RECONNECT_ATTEMPTS,
  onOpen,
  onMessage,
  onClose,
  onError,
}: UseWebSocketOptions) => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const clientIdRef = useRef(providedClientId || `${clientType}_${Date.now()}`);

  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Build WebSocket URL
  const wsUrl = url || `${WEBSOCKET_CONFIG.BASE_URL}${WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP}`;

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[useWebSocketConnection] Already connected');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[useWebSocketConnection] Connection in progress');
      return;
    }

    try {
      setIsConnecting(true);
      setConnectionError(null);
      
      console.log('[useWebSocketConnection] Connecting to:', wsUrl);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = (event) => {
        console.log('[useWebSocketConnection] Connected');
        setIsConnected(true);
        setIsConnecting(false);
        setConnectionError(null);
        reconnectAttemptsRef.current = 0;

        // Send handshake
        const handshake = createHandshakeMessage(
          clientType,
          clientIdRef.current,
          capabilities
        );
        sendWebSocketMessage(ws, handshake);

        onOpen?.(event);
      };

      ws.onmessage = (event) => {
        onMessage?.(event);
      };

      ws.onclose = (event) => {
        console.log('[useWebSocketConnection] Disconnected', event.code, event.reason);
        setIsConnected(false);
        setIsConnecting(false);
        wsRef.current = null;

        onClose?.(event);

        // Auto-reconnect logic
        if (autoReconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = reconnectDelay * Math.pow(2, reconnectAttemptsRef.current);
          console.log(`[useWebSocketConnection] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1}/${maxReconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current++;
            connect();
          }, delay);
        } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          setConnectionError('Maximum reconnection attempts reached');
        }
      };

      ws.onerror = (event) => {
        console.error('[useWebSocketConnection] Error:', event);
        setConnectionError('WebSocket connection error');
        onError?.(event);
      };
    } catch (error: any) {
      console.error('[useWebSocketConnection] Failed to connect:', error);
      setIsConnecting(false);
      setConnectionError(error.message);
    }
  }, [wsUrl, clientType, capabilities, autoReconnect, reconnectDelay, maxReconnectAttempts, onOpen, onMessage, onClose, onError]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
    setIsConnecting(false);
  }, []);

  // Send message
  const sendMessage = useCallback((message: any) => {
    if (wsRef.current && isWebSocketConnected(wsRef.current)) {
      return sendWebSocketMessage(wsRef.current, message);
    }
    console.warn('[useWebSocketConnection] Cannot send message - not connected');
    return false;
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect]);

  return {
    websocket: wsRef.current,
    isConnected,
    isConnecting,
    connectionError,
    connect,
    disconnect,
    sendMessage,
    clientId: clientIdRef.current,
  };
};
