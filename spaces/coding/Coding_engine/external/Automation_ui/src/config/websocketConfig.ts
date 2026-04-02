/**
 * Centralized WebSocket Configuration for TRAE Unity AI Platform
 * Ensures consistent WebSocket URLs across all frontend components
 * 
 * IMPORTANT: This centralizes all WebSocket connections to prevent
 * hardcoded URLs throughout the codebase.
 */

// ============================================================================
// ENVIRONMENT CONFIGURATION
// ============================================================================

/**
 * Get WebSocket base URL from environment variables
 * MIGRATED: Now uses local FastAPI backend exclusively (no Supabase)
 * Priority: VITE_WS_URL > Default localhost
 */
const getWebSocketBaseUrl = (): string => {
  // Check for WebSocket URL in environment
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }

  // Build WebSocket URL from backend URL if available
  if (import.meta.env.VITE_BACKEND_URL) {
    const backendUrl = import.meta.env.VITE_BACKEND_URL;
    // Convert http(s) to ws(s)
    return backendUrl.replace(/^http/, 'ws') + '/ws';
  }

  // Default to local FastAPI backend
  return 'ws://localhost:8007/ws';
};

// ============================================================================
// WEBSOCKET ENDPOINTS
// ============================================================================

export const WEBSOCKET_CONFIG = {
  // Base WebSocket server URL
  BASE_URL: getWebSocketBaseUrl(),
  
  // FastAPI WebSocket endpoint paths
  ENDPOINTS: {
    LIVE_DESKTOP: '/live-desktop',
    MULTI_DESKTOP: '/live-desktop',
    FILESYSTEM_BRIDGE: '/live-desktop',
    WORKFLOW: '/live-desktop',
    CLAWDBOT: '/clawdbot',
    DEFAULT: '/live-desktop'
  },
  
  // Connection settings - UPDATED for consistency
  CONNECTION: {
    PING_INTERVAL: 30000,        // 30 seconds - consistent ping interval
    PING_TIMEOUT: 10000,         // 10 seconds - time to wait for pong
    PONG_GRACE_PERIOD: 5000,     // 5 seconds - additional tolerance
    CLOSE_TIMEOUT: 10000,        // 10 seconds
    RECONNECT_DELAY: 1000,       // 1 second initial delay (was 5000)
    MAX_RECONNECT_ATTEMPTS: 10,  // Maximum reconnection attempts
    CONNECTION_TIMEOUT: 30000,   // 30 seconds connection timeout
    MAX_MISSED_PONGS: 3,         // Number of missed pongs before disconnect
  },
  
  // Reconnect settings - NEW centralized configuration
  RECONNECT: {
    INITIAL_DELAY: 1000,         // 1 second initial delay
    MAX_DELAY: 30000,            // 30 seconds maximum delay
    MAX_ATTEMPTS: 10,             // Maximum reconnection attempts
    BACKOFF_MULTIPLIER: 2,       // Exponential backoff multiplier
    JITTER: true,                 // Add random jitter to prevent thundering herd
    JITTER_FACTOR: 0.3,           // 30% jitter
  },
  
  // Circuit breaker settings - NEW
  CIRCUIT_BREAKER: {
    THRESHOLD: 5,                 // Failures before opening circuit
    TIMEOUT: 30000,               // Time to wait before half-open (30s)
    HEALTH_CHECK_INTERVAL: 10000, // Health check interval when circuit is open
  },
  
  // Client types for handshake identification
  CLIENT_TYPES: {
    WEB: 'web',
    DESKTOP_MANAGER: 'desktop_manager',
    DUAL_SCREEN_DESKTOP: 'dual_screen_desktop',
    MULTI_MONITOR_DESKTOP: 'multi_monitor_desktop_capture',
    DESKTOP_CAPTURE: 'desktop_capture',
    VIRTUAL_DESKTOP: 'virtual_desktop',
    FILESYSTEM_BRIDGE: 'filesystem_bridge',
    CLAWDBOT: 'clawdbot',
    CLAWDBOT_PLUGIN: 'clawdbot_plugin',
  },
  
  // Capability definitions
  CAPABILITIES: {
    MULTI_STREAM_VIEWING: 'multi_stream_viewing',
    DESKTOP_SPAWNING: 'desktop_spawning',
    MULTI_INSTANCE_MANAGEMENT: 'multi_instance_management',
    FILE_OPERATIONS: 'file_operations',
    ACTION_COMMANDS: 'action_commands',
    WORKFLOW_DATA: 'workflow_data',
    DESKTOP_STREAM: 'desktop_stream',
    OCR_PROCESSING: 'ocr_processing',
    // Clawdbot messaging integration
    MESSAGING_BRIDGE: 'messaging_bridge',
    AUTOMATION_COMMANDS: 'automation_commands',
    NOTIFICATIONS: 'notifications',
  }
} as const;

// ============================================================================
// CLIENT FACTORY FUNCTIONS
// ============================================================================

/**
 * Create WebSocket connection with standardized settings
 * @param clientType - Type of client connecting
 * @param clientId - Unique client identifier
 * @param capabilities - Array of client capabilities
 * @param endpoint - WebSocket endpoint path (optional, defaults to live desktop)
 * @returns WebSocket - Configured WebSocket connection
 */
export const createWebSocketConnection = (
  clientType: string,
  clientId: string,
  capabilities: string[] = [],
  endpoint: string = WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP
): WebSocket => {
  // Add query parameters required by Edge Function
  const params = new URLSearchParams({
    client_type: clientType,
    client_id: clientId
  });

  const fullUrl = `${WEBSOCKET_CONFIG.BASE_URL}${endpoint}?${params.toString()}`;
  console.log('🔗 Creating WebSocket connection:', fullUrl);

  const ws = new WebSocket(fullUrl);

  // Set standard connection properties
  (ws as any).clientType = clientType;
  (ws as any).clientId = clientId;
  (ws as any).capabilities = capabilities;
  (ws as any).endpoint = endpoint;

  return ws;
};

/**
 * Create handshake message with standardized format
 * @param clientType - Type of client
 * @param clientId - Unique client identifier  
 * @param capabilities - Array of client capabilities
 * @param additionalInfo - Optional additional client information
 * @returns Handshake message object
 */
export const createHandshakeMessage = (
  clientType: string,
  clientId: string,
  capabilities: string[] = [],
  additionalInfo: Record<string, any> = {}
) => ({
  type: 'handshake',
  clientInfo: {
    clientType,
    clientId,
    capabilities,
    ...additionalInfo
  },
  timestamp: new Date().toISOString()
});

// ============================================================================
// PREDEFINED CLIENT CONFIGURATIONS
// ============================================================================

/**
 * Web client configuration for frontend components
 * @param componentName - Name of the component creating the connection
 * @param endpoint - Optional WebSocket endpoint (defaults to live desktop)
 */
export const createWebClient = (
  componentName: string, 
  endpoint: string = WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP
) => {
  const clientId = `web_${componentName}_${Date.now()}`;
  return {
    clientId,
    websocket: createWebSocketConnection(
      WEBSOCKET_CONFIG.CLIENT_TYPES.WEB, 
      clientId,
      [WEBSOCKET_CONFIG.CAPABILITIES.MULTI_STREAM_VIEWING],
      endpoint
    ),
    handshakeMessage: createHandshakeMessage(
      WEBSOCKET_CONFIG.CLIENT_TYPES.WEB,
      clientId,
      [WEBSOCKET_CONFIG.CAPABILITIES.MULTI_STREAM_VIEWING]
    )
  };
};

/**
 * Desktop manager client configuration
 */
export const createDesktopManagerClient = () => {
  const clientId = `desktop_manager_${Date.now()}`;
  return {
    clientId,
    websocket: createWebSocketConnection(
      WEBSOCKET_CONFIG.CLIENT_TYPES.DESKTOP_MANAGER,
      clientId,
      [
        WEBSOCKET_CONFIG.CAPABILITIES.DESKTOP_SPAWNING,
        WEBSOCKET_CONFIG.CAPABILITIES.MULTI_INSTANCE_MANAGEMENT
      ]
    ),
    handshakeMessage: createHandshakeMessage(
      WEBSOCKET_CONFIG.CLIENT_TYPES.DESKTOP_MANAGER,
      clientId,
      [
        WEBSOCKET_CONFIG.CAPABILITIES.DESKTOP_SPAWNING,
        WEBSOCKET_CONFIG.CAPABILITIES.MULTI_INSTANCE_MANAGEMENT
      ]
    )
  };
};

/**
 * Filesystem bridge client configuration
 */
export const createFilesystemBridgeClient = () => {
  const clientId = `filesystem_bridge_${Date.now()}`;
  return {
    clientId,
    websocket: createWebSocketConnection(
      WEBSOCKET_CONFIG.CLIENT_TYPES.FILESYSTEM_BRIDGE,
      clientId,
      [
        WEBSOCKET_CONFIG.CAPABILITIES.FILE_OPERATIONS,
        WEBSOCKET_CONFIG.CAPABILITIES.ACTION_COMMANDS,
        WEBSOCKET_CONFIG.CAPABILITIES.WORKFLOW_DATA
      ],
      WEBSOCKET_CONFIG.ENDPOINTS.FILESYSTEM_BRIDGE
    ),
    handshakeMessage: createHandshakeMessage(
      WEBSOCKET_CONFIG.CLIENT_TYPES.FILESYSTEM_BRIDGE,
      clientId,
      [
        WEBSOCKET_CONFIG.CAPABILITIES.FILE_OPERATIONS,
        WEBSOCKET_CONFIG.CAPABILITIES.ACTION_COMMANDS,
        WEBSOCKET_CONFIG.CAPABILITIES.WORKFLOW_DATA
      ]
    )
  };
};

/**
 * Multi-desktop streams client configuration
 * IMPORTANT: Uses 'web' client type to ensure proper registration as web client
 * and receive dual_screen_frame messages from the WebSocket server
 */
export const createMultiDesktopClient = (componentName: string) => {
  const clientId = `multi_desktop_${componentName}_${Date.now()}`;
  return {
    clientId,
    websocket: createWebSocketConnection(
      WEBSOCKET_CONFIG.CLIENT_TYPES.WEB, // Changed from MULTI_MONITOR_DESKTOP to WEB
      clientId,
      [WEBSOCKET_CONFIG.CAPABILITIES.MULTI_STREAM_VIEWING],
      WEBSOCKET_CONFIG.ENDPOINTS.MULTI_DESKTOP
    ),
    handshakeMessage: createHandshakeMessage(
      WEBSOCKET_CONFIG.CLIENT_TYPES.WEB, // Changed from MULTI_MONITOR_DESKTOP to WEB
      clientId,
      [WEBSOCKET_CONFIG.CAPABILITIES.MULTI_STREAM_VIEWING]
    )
  };
};

/**
 * Live desktop client configuration
 */
export const createLiveDesktopClient = (componentName: string) => {
  const clientId = `live_desktop_${componentName}_${Date.now()}`;
  return {
    clientId,
    websocket: createWebSocketConnection(
      WEBSOCKET_CONFIG.CLIENT_TYPES.DUAL_SCREEN_DESKTOP,
      clientId,
      [WEBSOCKET_CONFIG.CAPABILITIES.DESKTOP_STREAM],
      WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP
    ),
    handshakeMessage: createHandshakeMessage(
      WEBSOCKET_CONFIG.CLIENT_TYPES.DUAL_SCREEN_DESKTOP,
      clientId,
      [WEBSOCKET_CONFIG.CAPABILITIES.DESKTOP_STREAM]
    )
  };
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Check if WebSocket is in a connected state
 */
export const isWebSocketConnected = (ws: WebSocket): boolean => {
  return ws.readyState === WebSocket.OPEN;
};

/**
 * Safe WebSocket message sending with error handling
 */
export const sendWebSocketMessage = (ws: WebSocket, message: any): boolean => {
  try {
    if (isWebSocketConnected(ws)) {
      ws.send(JSON.stringify(message));
      return true;
    }
    console.warn('WebSocket not connected, message not sent:', message.type);
    return false;
  } catch (error) {
    console.error('Error sending WebSocket message:', error);
    return false;
  }
};

/**
 * Get current WebSocket configuration summary
 */
export const getWebSocketConfigSummary = () => ({
  baseUrl: WEBSOCKET_CONFIG.BASE_URL,
  environment: {
    VITE_WS_URL: import.meta.env.VITE_WS_URL,
    VITE_WS_HOST: import.meta.env.VITE_WS_HOST,
    VITE_WS_PORT: import.meta.env.VITE_WS_PORT,
  },
  isProduction: import.meta.env.PROD,
  isDevelopment: import.meta.env.DEV,
});

// ============================================================================
// DEVELOPER UTILITIES
// ============================================================================

/**
 * Log WebSocket configuration (development only)
 */
export const logWebSocketConfig = () => {
  if (import.meta.env.DEV) {
    console.group('🔌 WebSocket Configuration');
    console.log('Base URL:', WEBSOCKET_CONFIG.BASE_URL);
    console.log('Environment:', getWebSocketConfigSummary().environment);
    console.log('Client Types:', WEBSOCKET_CONFIG.CLIENT_TYPES);
    console.log('Capabilities:', WEBSOCKET_CONFIG.CAPABILITIES);
    console.groupEnd();
  }
};

// ============================================================================
// RECONNECTION HELPERS
// ============================================================================

/**
 * Create WebSocket URL for reconnection hook
 * @param clientType - Type of client connecting
 * @param clientId - Unique client identifier
 * @param endpoint - WebSocket endpoint path (optional, defaults to live desktop)
 * @returns Full WebSocket URL with query parameters
 */
export const createWebSocketUrl = (
  clientType: string,
  clientId: string,
  endpoint: string = WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP
): string => {
  const params = new URLSearchParams({
    client_type: clientType,
    client_id: clientId
  });

  return `${WEBSOCKET_CONFIG.BASE_URL}${endpoint}?${params.toString()}`;
};

/**
 * Create WebSocket URL for web client
 * @param componentName - Name of the component creating the connection
 * @param endpoint - Optional WebSocket endpoint (defaults to live desktop)
 */
export const createWebClientUrl = (
  componentName: string,
  endpoint: string = WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP
): { url: string; clientId: string; handshakeMessage: any } => {
  const clientId = `web_${componentName}_${Date.now()}`;
  const url = createWebSocketUrl(
    WEBSOCKET_CONFIG.CLIENT_TYPES.WEB,
    clientId,
    endpoint
  );
  const handshakeMessage = createHandshakeMessage(
    WEBSOCKET_CONFIG.CLIENT_TYPES.WEB,
    clientId,
    [WEBSOCKET_CONFIG.CAPABILITIES.MULTI_STREAM_VIEWING]
  );

  return { url, clientId, handshakeMessage };
};

/**
 * Create WebSocket URL for multi-desktop client
 * @param componentName - Name of the component creating the connection
 */
export const createMultiDesktopClientUrl = (
  componentName: string
): { url: string; clientId: string; handshakeMessage: any } => {
  const clientId = `multi_desktop_${componentName}_${Date.now()}`;
  const url = createWebSocketUrl(
    WEBSOCKET_CONFIG.CLIENT_TYPES.WEB,
    clientId,
    WEBSOCKET_CONFIG.ENDPOINTS.MULTI_DESKTOP
  );
  const handshakeMessage = createHandshakeMessage(
    WEBSOCKET_CONFIG.CLIENT_TYPES.WEB,
    clientId,
    [WEBSOCKET_CONFIG.CAPABILITIES.MULTI_STREAM_VIEWING]
  );

  return { url, clientId, handshakeMessage };
};

// Log configuration on import in development
if (import.meta.env.DEV) {
  logWebSocketConfig();
}

export default WEBSOCKET_CONFIG;