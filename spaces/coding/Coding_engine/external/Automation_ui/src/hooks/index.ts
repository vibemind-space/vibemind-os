/**
 * Hooks Index
 * Centralized export for all custom hooks
 */

export { useIsMobile } from './use-mobile';
export { useToast, toast } from './use-toast';
export { useLiveDesktopConfig } from './useLiveDesktopConfig';
export { useWebSocketConnection } from './useWebSocketConnection';
export { 
  useWebSocketReconnect, 
  type ConnectionStatus, 
  type CircuitBreakerState,
  type UseWebSocketReconnectOptions,
  type UseWebSocketReconnectReturn
} from './useWebSocketReconnect';
export { useWebSocketWithStore } from './useWebSocketWithStore';
