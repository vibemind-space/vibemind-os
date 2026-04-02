/**
 * WebSocket Reconnection Hook
 * Provides automatic reconnection with exponential backoff and circuit breaker pattern
 * Preserves state and handles connection lifecycle
 * 
 * UPDATED: Uses centralized WEBSOCKET_CONFIG for all timing values
 */

import { useRef, useEffect, useCallback, useState } from 'react';
import { WEBSOCKET_CONFIG, sendWebSocketMessage } from '@/config/websocketConfig';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error' | 'circuit_open';

export type CircuitBreakerState = 'closed' | 'open' | 'half_open';

export interface UseWebSocketReconnectOptions {
  /** WebSocket URL */
  url: string;
  /** Initial handshake message to send on connection */
  handshakeMessage: any;
  /** Callback when connection is established */
  onOpen?: (ws: WebSocket) => void;
  /** Callback when message is received */
  onMessage?: (event: MessageEvent, ws: WebSocket) => void;
  /** Callback when connection is closed */
  onClose?: (event: CloseEvent) => void;
  /** Callback when error occurs */
  onError?: (event: Event) => void;
  /** Enable automatic reconnection (default: true) */
  autoReconnect?: boolean;
  /** Maximum reconnection attempts (default: from config) */
  maxReconnectAttempts?: number;
  /** Initial reconnection delay in ms (default: from config) */
  reconnectDelay?: number;
  /** Enable exponential backoff (default: true) */
  exponentialBackoff?: boolean;
  /** Maximum reconnection delay in ms (default: from config) */
  maxReconnectDelay?: number;
  /** Circuit breaker: failures before opening circuit (default: from config) */
  circuitBreakerThreshold?: number;
  /** Circuit breaker: time to wait before trying half-open (default: from config) */
  circuitBreakerTimeout?: number;
  /** Circuit breaker: enable health check endpoint (optional) */
  healthCheckUrl?: string;
  /** Callback when reconnecting (optional) */
  onReconnecting?: (attempt: number, maxAttempts: number) => void;
  /** Callback on circuit breaker state change (optional) */
  onCircuitBreakerChange?: (state: CircuitBreakerState) => void;
}

export interface UseWebSocketReconnectReturn {
  /** Current WebSocket instance */
  websocket: WebSocket | null;
  /** Connection status */
  status: ConnectionStatus;
  /** Current reconnection attempt number */
  reconnectAttempt: number;
  /** Manually trigger reconnection */
  reconnect: () => void;
  /** Manually disconnect */
  disconnect: () => void;
  /** Send message through WebSocket */
  sendMessage: (message: any) => boolean;
  /** Check if connected */
  isConnected: boolean;
  /** Last error message */
  lastError: string | null;
  /** Circuit breaker state */
  circuitBreakerState: CircuitBreakerState;
  /** Reset circuit breaker */
  resetCircuitBreaker: () => void;
  /** Time until next reconnect attempt (ms) */
  nextReconnectIn: number | null;
  /** Total connection uptime (ms) */
  connectionUptime: number;
}

/**
 * Calculate reconnect delay with jitter to prevent thundering herd
 */
const calculateDelayWithJitter = (baseDelay: number, jitter: boolean, jitterFactor: number): number => {
  if (!jitter) return baseDelay;
  
  const jitterAmount = baseDelay * jitterFactor;
  const randomJitter = (Math.random() - 0.5) * 2 * jitterAmount;
  return Math.max(100, baseDelay + randomJitter);
};

export const useWebSocketReconnect = (
  options: UseWebSocketReconnectOptions
): UseWebSocketReconnectReturn => {
  const {
    url,
    handshakeMessage,
    onOpen,
    onMessage,
    onClose,
    onError,
    onReconnecting,
    onCircuitBreakerChange,
    autoReconnect = true,
    maxReconnectAttempts = WEBSOCKET_CONFIG.RECONNECT.MAX_ATTEMPTS,
    reconnectDelay = WEBSOCKET_CONFIG.RECONNECT.INITIAL_DELAY,
    exponentialBackoff = true,
    maxReconnectDelay = WEBSOCKET_CONFIG.RECONNECT.MAX_DELAY,
    circuitBreakerThreshold = WEBSOCKET_CONFIG.CIRCUIT_BREAKER.THRESHOLD,
    circuitBreakerTimeout = WEBSOCKET_CONFIG.CIRCUIT_BREAKER.TIMEOUT,
    healthCheckUrl,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnectRef = useRef<boolean>(true);
  const reconnectAttemptRef = useRef<number>(0);
  const manualDisconnectRef = useRef<boolean>(false);
  const connectionStartTimeRef = useRef<number | null>(null);

  // Circuit breaker state
  const circuitBreakerStateRef = useRef<CircuitBreakerState>('closed');
  const failureCountRef = useRef<number>(0);
  const lastFailureTimeRef = useRef<number>(0);
  const circuitBreakerTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const healthCheckIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Heartbeat refs for detecting dead connections
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const pongTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastPongRef = useRef<number>(Date.now());
  const missedPongsRef = useRef<number>(0);

  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);
  const [circuitBreakerState, setCircuitBreakerState] = useState<CircuitBreakerState>('closed');
  const [nextReconnectIn, setNextReconnectIn] = useState<number | null>(null);
  const [connectionUptime, setConnectionUptime] = useState<number>(0);

  // Update uptime periodically when connected
  useEffect(() => {
    let uptimeInterval: NodeJS.Timeout | null = null;
    
    if (status === 'connected' && connectionStartTimeRef.current) {
      uptimeInterval = setInterval(() => {
        setConnectionUptime(Date.now() - (connectionStartTimeRef.current || Date.now()));
      }, 1000);
    }
    
    return () => {
      if (uptimeInterval) clearInterval(uptimeInterval);
    };
  }, [status]);

  // Circuit breaker: Record failure
  const recordFailure = useCallback(() => {
    failureCountRef.current += 1;
    lastFailureTimeRef.current = Date.now();

    console.log(`❌ Circuit breaker: failure count ${failureCountRef.current}/${circuitBreakerThreshold}`);

    // Open circuit if threshold reached
    if (failureCountRef.current >= circuitBreakerThreshold && circuitBreakerStateRef.current === 'closed') {
      console.error(`🚨 Circuit breaker OPENED after ${failureCountRef.current} failures`);
      circuitBreakerStateRef.current = 'open';
      setCircuitBreakerState('open');
      setStatus('circuit_open');
      setLastError(`Circuit breaker opened: Too many connection failures (${failureCountRef.current})`);
      onCircuitBreakerChange?.('open');

      // Schedule half-open attempt
      if (circuitBreakerTimeoutRef.current) {
        clearTimeout(circuitBreakerTimeoutRef.current);
      }
      circuitBreakerTimeoutRef.current = setTimeout(() => {
        console.log('🔄 Circuit breaker: Attempting half-open state');
        circuitBreakerStateRef.current = 'half_open';
        setCircuitBreakerState('half_open');
        failureCountRef.current = 0; // Reset count for half-open test
        onCircuitBreakerChange?.('half_open');
      }, circuitBreakerTimeout);
    }
  }, [circuitBreakerThreshold, circuitBreakerTimeout, onCircuitBreakerChange]);

  // Circuit breaker: Record success
  const recordSuccess = useCallback(() => {
    failureCountRef.current = 0;
    lastFailureTimeRef.current = 0;

    // Close circuit if it was open or half-open
    if (circuitBreakerStateRef.current !== 'closed') {
      console.log('✅ Circuit breaker CLOSED: Connection successful');
      circuitBreakerStateRef.current = 'closed';
      setCircuitBreakerState('closed');
      onCircuitBreakerChange?.('closed');

      // Clear timeout
      if (circuitBreakerTimeoutRef.current) {
        clearTimeout(circuitBreakerTimeoutRef.current);
        circuitBreakerTimeoutRef.current = null;
      }
    }
  }, [onCircuitBreakerChange]);

  // Circuit breaker: Health check
  const performHealthCheck = useCallback(async (): Promise<boolean> => {
    if (!healthCheckUrl) {
      // No health check URL provided, assume healthy after timeout
      return true;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

      const response = await fetch(healthCheckUrl, {
        method: 'GET',
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      return response.ok;
    } catch (error) {
      console.warn('Health check failed:', error);
      return false;
    }
  }, [healthCheckUrl]);

  // Circuit breaker: Reset
  const resetCircuitBreaker = useCallback(() => {
    console.log('🔄 Resetting circuit breaker');
    failureCountRef.current = 0;
    lastFailureTimeRef.current = 0;
    circuitBreakerStateRef.current = 'closed';
    setCircuitBreakerState('closed');
    onCircuitBreakerChange?.('closed');

    if (circuitBreakerTimeoutRef.current) {
      clearTimeout(circuitBreakerTimeoutRef.current);
      circuitBreakerTimeoutRef.current = null;
    }

    if (healthCheckIntervalRef.current) {
      clearInterval(healthCheckIntervalRef.current);
      healthCheckIntervalRef.current = null;
    }
  }, [onCircuitBreakerChange]);

  const calculateReconnectDelay = useCallback((attempt: number): number => {
    if (!exponentialBackoff) {
      return calculateDelayWithJitter(
        reconnectDelay, 
        WEBSOCKET_CONFIG.RECONNECT.JITTER, 
        WEBSOCKET_CONFIG.RECONNECT.JITTER_FACTOR
      );
    }

    // Exponential backoff: delay * (multiplier ^ attempt)
    const baseDelay = Math.min(
      reconnectDelay * Math.pow(WEBSOCKET_CONFIG.RECONNECT.BACKOFF_MULTIPLIER, attempt),
      maxReconnectDelay
    );

    const finalDelay = calculateDelayWithJitter(
      baseDelay,
      WEBSOCKET_CONFIG.RECONNECT.JITTER,
      WEBSOCKET_CONFIG.RECONNECT.JITTER_FACTOR
    );

    console.log(`🔄 Reconnect attempt ${attempt + 1}: delay ${Math.round(finalDelay)}ms (base: ${baseDelay}ms)`);
    return finalDelay;
  }, [reconnectDelay, exponentialBackoff, maxReconnectDelay]);

  // Stop heartbeat mechanism
  const stopHeartbeat = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    if (pongTimeoutRef.current) {
      clearTimeout(pongTimeoutRef.current);
      pongTimeoutRef.current = null;
    }
    missedPongsRef.current = 0;
  }, []);

  // Start heartbeat mechanism - UPDATED with correct timing
  const startHeartbeat = useCallback((ws: WebSocket) => {
    // Clear any existing heartbeat
    stopHeartbeat();

    console.log('💓 Starting heartbeat mechanism');
    lastPongRef.current = Date.now();
    missedPongsRef.current = 0;

    const pingInterval = WEBSOCKET_CONFIG.CONNECTION.PING_INTERVAL;
    const pingTimeout = WEBSOCKET_CONFIG.CONNECTION.PING_TIMEOUT;
    const gracePeriod = WEBSOCKET_CONFIG.CONNECTION.PONG_GRACE_PERIOD;
    const maxMissedPongs = WEBSOCKET_CONFIG.CONNECTION.MAX_MISSED_PONGS;

    // Send ping at configured interval
    pingIntervalRef.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        const now = Date.now();
        const timeSinceLastPong = now - lastPongRef.current;

        // CORRECTED: Use proper timeout calculation
        const totalTimeout = pingInterval + pingTimeout + gracePeriod;
        
        if (timeSinceLastPong > totalTimeout) {
          missedPongsRef.current += 1;
          console.warn(`⚠️ Missed pong ${missedPongsRef.current}/${maxMissedPongs} (${timeSinceLastPong}ms since last pong)`);

          // After configured missed pongs, consider connection dead
          if (missedPongsRef.current >= maxMissedPongs) {
            console.error(`❌ Connection appears dead (${maxMissedPongs} missed pongs), forcing reconnection`);
            setLastError('Connection timeout - no heartbeat response');
            stopHeartbeat();
            ws.close(1000, 'Heartbeat timeout');
            return;
          }
        }

        // Send ping
        try {
          sendWebSocketMessage(ws, {
            type: 'ping',
            timestamp: now,
            clientId: (ws as any).clientId
          });
          console.log('📤 Ping sent');
        } catch (error) {
          console.error('Failed to send ping:', error);
          missedPongsRef.current += 1;
        }
      } else {
        console.warn('⚠️ WebSocket not open, stopping heartbeat');
        stopHeartbeat();
      }
    }, pingInterval);

  }, [stopHeartbeat]);

  // Handle pong message
  const handlePongMessage = useCallback((message: any) => {
    if (message.type === 'pong') {
      const now = Date.now();
      const latency = message.timestamp ? now - message.timestamp : 0;
      lastPongRef.current = now;
      missedPongsRef.current = 0; // Reset missed pong counter
      console.log(`📥 Pong received (latency: ${latency}ms)`);
    }
  }, []);

  const connect = useCallback(async () => {
    // Check circuit breaker state
    if (circuitBreakerStateRef.current === 'open') {
      console.warn('🚨 Circuit breaker is OPEN: Skipping connection attempt');
      setLastError('Circuit breaker is open. Service may be unavailable.');
      
      // Perform health check if URL is provided
      if (healthCheckUrl) {
        const isHealthy = await performHealthCheck();
        if (isHealthy) {
          console.log('✅ Health check passed: Moving to half-open state');
          circuitBreakerStateRef.current = 'half_open';
          setCircuitBreakerState('half_open');
          onCircuitBreakerChange?.('half_open');
        }
      }
      
      return;
    }

    // In half-open state, do a quick health check first
    if (circuitBreakerStateRef.current === 'half_open' && healthCheckUrl) {
      const isHealthy = await performHealthCheck();
      if (!isHealthy) {
        console.warn('⚠️ Health check failed: Keeping circuit open');
        recordFailure();
        return;
      }
    }

    // Clear any pending reconnection timeouts
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setNextReconnectIn(null);

    // Close existing connection if any
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (error) {
        console.warn('Error closing existing WebSocket:', error);
      }
      wsRef.current = null;
    }

    console.log('🔗 Connecting to WebSocket:', url);
    setStatus('connecting');
    setLastError(null);

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      // Connection timeout
      const connectionTimeout = setTimeout(() => {
        if (ws.readyState === WebSocket.CONNECTING) {
          console.warn('⏰ Connection timeout');
          ws.close();
          recordFailure();
        }
      }, WEBSOCKET_CONFIG.CONNECTION.CONNECTION_TIMEOUT);

      ws.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log('✅ WebSocket connected');
        setStatus('connected');
        setLastError(null);
        reconnectAttemptRef.current = 0;
        setReconnectAttempt(0);
        manualDisconnectRef.current = false;
        connectionStartTimeRef.current = Date.now();
        setConnectionUptime(0);

        // Record success for circuit breaker
        recordSuccess();

        // Send handshake message
        if (ws.readyState === WebSocket.OPEN) {
          sendWebSocketMessage(ws, handshakeMessage);
        }

        // Start heartbeat mechanism
        startHeartbeat(ws);

        // Call user-provided onOpen callback
        onOpen?.(ws);
      };

      ws.onmessage = (event) => {
        // Try to parse message to check for pong
        try {
          const message = JSON.parse(event.data);
          handlePongMessage(message);
        } catch (error) {
          // Not JSON or parsing error, ignore for heartbeat purposes
        }

        // Call user-provided onMessage callback
        onMessage?.(event, ws);
      };

      ws.onerror = (event) => {
        clearTimeout(connectionTimeout);
        console.error('❌ WebSocket error:', event);
        setStatus('error');
        setLastError('WebSocket connection error');
        
        // Record failure for circuit breaker
        recordFailure();
        
        onError?.(event);
      };

      ws.onclose = (event) => {
        clearTimeout(connectionTimeout);
        console.log('🔌 WebSocket closed:', {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
          manualDisconnect: manualDisconnectRef.current,
        });

        wsRef.current = null;
        connectionStartTimeRef.current = null;
        setConnectionUptime(0);

        // Stop heartbeat
        stopHeartbeat();

        // Record failure only if not a clean close or manual disconnect
        if (!event.wasClean && !manualDisconnectRef.current) {
          recordFailure();
        }

        // Call user-provided onClose callback
        onClose?.(event);

        // Attempt reconnection if not manually disconnected and circuit is not open
        if (
          autoReconnect &&
          shouldReconnectRef.current &&
          !manualDisconnectRef.current &&
          circuitBreakerStateRef.current !== 'open' &&
          reconnectAttemptRef.current < maxReconnectAttempts
        ) {
          setStatus('reconnecting');
          const delay = calculateReconnectDelay(reconnectAttemptRef.current);

          console.log(
            `🔄 Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttemptRef.current + 1}/${maxReconnectAttempts})`
          );

          // Notify callback
          onReconnecting?.(reconnectAttemptRef.current + 1, maxReconnectAttempts);
          
          // Start countdown
          setNextReconnectIn(delay);
          const countdownStart = Date.now();
          const countdownInterval = setInterval(() => {
            const elapsed = Date.now() - countdownStart;
            const remaining = Math.max(0, delay - elapsed);
            setNextReconnectIn(remaining);
            if (remaining <= 0) {
              clearInterval(countdownInterval);
            }
          }, 100);

          reconnectTimeoutRef.current = setTimeout(() => {
            clearInterval(countdownInterval);
            setNextReconnectIn(null);
            reconnectAttemptRef.current += 1;
            setReconnectAttempt(reconnectAttemptRef.current);
            connect();
          }, delay);
        } else {
          if (circuitBreakerStateRef.current === 'open') {
            console.error('🚨 Circuit breaker is open: Stopping reconnection attempts');
            setStatus('circuit_open');
            setLastError('Circuit breaker opened: Too many failures');
          } else if (reconnectAttemptRef.current >= maxReconnectAttempts) {
            console.error('❌ Max reconnection attempts reached');
            setStatus('error');
            setLastError(`Failed to reconnect after ${maxReconnectAttempts} attempts`);
          } else {
            setStatus('disconnected');
          }
        }
      };
    } catch (error) {
      console.error('❌ Failed to create WebSocket:', error);
      setStatus('error');
      setLastError(error instanceof Error ? error.message : 'Failed to create WebSocket');
      
      // Record failure for circuit breaker
      recordFailure();
    }
  }, [
    url,
    handshakeMessage,
    autoReconnect,
    maxReconnectAttempts,
    calculateReconnectDelay,
    onOpen,
    onMessage,
    onClose,
    onError,
    onReconnecting,
    onCircuitBreakerChange,
    recordFailure,
    recordSuccess,
    performHealthCheck,
    healthCheckUrl,
    startHeartbeat,
    stopHeartbeat,
    handlePongMessage,
  ]);

  const disconnect = useCallback(() => {
    console.log('🛑 Manually disconnecting WebSocket');
    manualDisconnectRef.current = true;
    shouldReconnectRef.current = false;

    // Stop heartbeat
    stopHeartbeat();

    // Clear reconnection timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setNextReconnectIn(null);

    // Close WebSocket
    if (wsRef.current) {
      try {
        wsRef.current.close(1000, 'Manual disconnect');
      } catch (error) {
        console.warn('Error closing WebSocket:', error);
      }
      wsRef.current = null;
    }

    setStatus('disconnected');
    reconnectAttemptRef.current = 0;
    setReconnectAttempt(0);
    connectionStartTimeRef.current = null;
    setConnectionUptime(0);
  }, [stopHeartbeat]);

  const reconnect = useCallback(() => {
    console.log('🔄 Manual reconnect triggered');
    reconnectAttemptRef.current = 0;
    setReconnectAttempt(0);
    manualDisconnectRef.current = false;
    shouldReconnectRef.current = true;
    
    // Reset circuit breaker on manual reconnect
    resetCircuitBreaker();
    
    connect();
  }, [connect, resetCircuitBreaker]);

  const sendMessage = useCallback((message: any): boolean => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return sendWebSocketMessage(wsRef.current, message);
    }
    console.warn('Cannot send message: WebSocket not connected');
    return false;
  }, []);

  // Initial connection
  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();

    // Cleanup on unmount
    return () => {
      shouldReconnectRef.current = false;
      manualDisconnectRef.current = true;

      // Stop heartbeat
      stopHeartbeat();

      // Clear circuit breaker timeouts
      if (circuitBreakerTimeoutRef.current) {
        clearTimeout(circuitBreakerTimeoutRef.current);
        circuitBreakerTimeoutRef.current = null;
      }

      if (healthCheckIntervalRef.current) {
        clearInterval(healthCheckIntervalRef.current);
        healthCheckIntervalRef.current = null;
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      if (wsRef.current) {
        try {
          wsRef.current.close(1000, 'Component unmount');
        } catch (error) {
          console.warn('Error closing WebSocket on unmount:', error);
        }
        wsRef.current = null;
      }
    };
  }, [connect, stopHeartbeat]);

  return {
    websocket: wsRef.current,
    status,
    reconnectAttempt,
    reconnect,
    disconnect,
    sendMessage,
    isConnected: status === 'connected',
    lastError,
    circuitBreakerState,
    resetCircuitBreaker,
    nextReconnectIn,
    connectionUptime,
  };
};
