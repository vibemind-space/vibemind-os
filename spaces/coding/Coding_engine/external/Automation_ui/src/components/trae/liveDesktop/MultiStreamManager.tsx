import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LiveDesktopConfig, LiveDesktopStatus } from '@/types/liveDesktop';
import { WEBSOCKET_CONFIG, createHandshakeMessage } from '@/config/websocketConfig';

/**
 * Enhanced Multi-Stream Manager for TRAE Unity AI Platform
 * Manages multiple WebSocket connections for individual display streams
 * Follows TRAE naming conventions and coding standards
 */

// ============================================================================
// INTERFACES AND TYPES
// ============================================================================

interface DisplayStream {
  /** Unique stream identifier */
  streamId: string;
  /** Client ID this stream belongs to */
  clientId: string;
  /** Monitor/display identifier */
  monitorId: string;
  /** Display name for UI */
  displayName: string;
  /** WebSocket connection for this specific stream */
  websocket: WebSocket | null;
  /** Canvas reference for rendering */
  canvasRef: React.RefObject<HTMLCanvasElement>;
  /** Current stream status */
  status: LiveDesktopStatus;
  /** Stream configuration */
  config: LiveDesktopConfig;
  /** Connection state */
  isConnected: boolean;
  /** Streaming state */
  isStreaming: boolean;
  /** Last frame timestamp */
  lastFrameTime: Date | null;
  /** Frame count for performance monitoring */
  frameCount: number;
  /** Connection retry count */
  retryCount: number;
}

interface MultiStreamManagerProps {
  /** Base WebSocket server URL */
  serverUrl?: string;
  /** Selected clients with their monitors */
  selectedClients: Array<{
    clientId: string;
    monitors: Array<{
      monitorId: string;
      name: string;
      resolution: { width: number; height: number };
    }>;
  }>;
  /** Maximum concurrent streams */
  maxStreams?: number;
  /** Stream configuration */
  streamConfig?: Partial<LiveDesktopConfig>;
  /** Callback when stream status changes */
  onStreamStatusChange?: (streamId: string, status: LiveDesktopStatus) => void;
  /** Callback when frame is received */
  onFrameReceived?: (streamId: string, frameData: any) => void;
  /** Callback when stream connects */
  onStreamConnected?: (streamId: string) => void;
  /** Callback when stream disconnects */
  onStreamDisconnected?: (streamId: string) => void;
  /** Enable auto-reconnection */
  enableAutoReconnect?: boolean;
  /** CSS class name */
  className?: string;
}

// ============================================================================
// MULTI-STREAM MANAGER COMPONENT
// ============================================================================

export const useMultiStreamManager = ({
  serverUrl = WEBSOCKET_CONFIG.BASE_URL,
  selectedClients = [],
  maxStreams = 4,
  streamConfig = {},
  onStreamStatusChange,
  onFrameReceived,
  onStreamConnected,
  onStreamDisconnected,
  enableAutoReconnect = true,
  className = ''
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const [displayStreams, setDisplayStreams] = useState<Map<string, DisplayStream>>(new Map());
  const [globalStatus, setGlobalStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const [connectionCount, setConnectionCount] = useState(0);
  const [streamingCount, setStreamingCount] = useState(0);

  // Refs for managing connections
  const streamsRef = useRef<Map<string, DisplayStream>>(new Map());
  const reconnectTimeouts = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // Default stream configuration following TRAE standards
  const defaultConfig = {
    fps: 15,
    quality: 85,
    scale: 1.0,
    format: 'jpeg',
    enableMouse: true,
    enableKeyboard: true,
    ...streamConfig
  };

  // ============================================================================
  // STREAM LIFECYCLE MANAGEMENT
  // ============================================================================

  /**
   * Create a new display stream for a specific monitor
   */
  const createDisplayStream = useCallback((clientId: string, monitorId: string, displayName: string): DisplayStream => {
    const streamId = `${clientId}_${monitorId}`;
    
    const stream: DisplayStream = {
      streamId,
      clientId,
      monitorId,
      displayName,
      websocket: null,
      canvasRef: React.createRef<HTMLCanvasElement>(),
      status: {
        connected: false,
        streaming: false,
        connectionName: null,
        latency: 0,
        fpsActual: 0,
        bytesReceived: 0,
        lastFrameTime: null
      },
      config: {
        id: streamId,
        name: displayName,
        description: `Stream for ${displayName}`,
        websocketUrl: serverUrl,
        streaming: {
          fps: defaultConfig.fps,
          quality: defaultConfig.quality,
          scale: defaultConfig.scale,
          format: defaultConfig.format
        },
        connection: {
          timeout: 30000,
          maxReconnectAttempts: 5,
          reconnectInterval: 3000,
          autoReconnect: true
        },
        ocr: {
          enabled: false,
          extractionInterval: 5,
          autoSend: false
        },
        ocrRegions: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      },
      isConnected: false,
      isStreaming: false,
      lastFrameTime: null,
      frameCount: 0,
      retryCount: 0
    };

    console.log(`[MultiStreamManager] Created display stream: ${streamId} for ${displayName}`);
    return stream;
  }, [defaultConfig]);

  /**
   * Connect a specific display stream
   */
  const connectDisplayStream = useCallback(async (stream: DisplayStream): Promise<boolean> => {
    try {
      console.log(`[MultiStreamManager] Connecting stream: ${stream.streamId}`);
      
      // Create WebSocket connection with stream-specific parameters
      const wsUrl = `${serverUrl}?client_type=web_stream&stream_id=${stream.streamId}&client_id=${stream.clientId}&monitor_id=${stream.monitorId}`;
      const websocket = new WebSocket(wsUrl);

      // Set up connection handlers
      websocket.onopen = () => {
        console.log(`[MultiStreamManager] Stream connected: ${stream.streamId}`);
        
        // Update stream state
        stream.websocket = websocket;
        stream.isConnected = true;
        stream.status = {
          connected: true,
          streaming: false,
          connectionName: stream.displayName,
          latency: 0,
          fpsActual: 0,
          bytesReceived: 0,
          lastFrameTime: null
        };
        stream.retryCount = 0;

        // Send handshake for this specific stream
        const handshake = createHandshakeMessage(
          'web_display_stream',
          stream.clientId,
          ['frame_display', 'stream_control'],
          { streamId: stream.streamId, monitorId: stream.monitorId }
        );
        websocket.send(JSON.stringify(handshake));

        // Notify callbacks
        onStreamConnected?.(stream.streamId);
        onStreamStatusChange?.(stream.streamId, stream.status);

        // Update global state
        setConnectionCount(prev => prev + 1);
      };

      websocket.onmessage = (event) => {
        handleStreamMessage(stream, event);
      };

      websocket.onclose = () => {
        console.log(`[MultiStreamManager] Stream disconnected: ${stream.streamId}`);
        handleStreamDisconnection(stream);
      };

      websocket.onerror = (error) => {
        console.error(`[MultiStreamManager] Stream error: ${stream.streamId}`, error);
        handleStreamError(stream);
      };

      return true;
    } catch (error) {
      console.error(`[MultiStreamManager] Failed to connect stream: ${stream.streamId}`, error);
      handleStreamError(stream);
      return false;
    }
  }, [serverUrl, onStreamConnected, onStreamStatusChange]);

  /**
   * Handle incoming messages for a specific stream
   */
  const handleStreamMessage = useCallback((stream: DisplayStream, event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'handshake_ack':
          console.log(`[MultiStreamManager] Handshake acknowledged for stream: ${stream.streamId}`);
          break;

        case 'frame_data':
          handleFrameData(stream, data);
          break;

        case 'stream_status':
          handleStreamStatus(stream, data);
          break;

        case 'pong':
          // Heartbeat response - stream is alive
          break;

        default:
          console.warn(`[MultiStreamManager] Unknown message type for stream ${stream.streamId}:`, data.type);
      }
    } catch (error) {
      console.error(`[MultiStreamManager] Error parsing message for stream ${stream.streamId}:`, error);
    }
  }, []);

  /**
   * Handle frame data for a specific stream
   */
  const handleFrameData = useCallback((stream: DisplayStream, data: any) => {
    try {
      const canvas = stream.canvasRef.current;
      if (!canvas) return;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Create image from base64 data
      const img = new Image();
      img.onload = () => {
        // Update canvas size if needed
        if (canvas.width !== img.width || canvas.height !== img.height) {
          canvas.width = img.width;
          canvas.height = img.height;
        }

        // Draw frame
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);

        // Update stream statistics
        stream.frameCount++;
        stream.lastFrameTime = new Date();

        // Notify callback
        onFrameReceived?.(stream.streamId, data);
      };

      img.src = `data:image/jpeg;base64,${data.frameData}`;
      
      console.log(`[MultiStreamManager] Frame received for stream: ${stream.streamId}, size: ${data.frameData?.length || 0} bytes`);
    } catch (error) {
      console.error(`[MultiStreamManager] Error handling frame data for stream ${stream.streamId}:`, error);
    }
  }, [onFrameReceived]);

  /**
   * Handle stream status updates
   */
  const handleStreamStatus = useCallback((stream: DisplayStream, data: any) => {
    const newStatus: LiveDesktopStatus = {
      connected: true,
      streaming: data.streaming || false,
      connectionName: stream.displayName,
      latency: data.latency || 0,
      fpsActual: data.fps || 0,
      bytesReceived: stream.frameCount * (data.frameSize || 0),
      lastFrameTime: stream.lastFrameTime?.toISOString() || null
    };
    
    stream.status = newStatus;
    stream.isStreaming = data.streaming;
    
    onStreamStatusChange?.(stream.streamId, newStatus);
    
    // Update global streaming count
    setStreamingCount(prev => {
      const currentStreaming = Array.from(streamsRef.current.values()).filter(s => s.isStreaming).length;
      return currentStreaming;
    });
  }, [onStreamStatusChange]);

  /**
   * Handle stream disconnection
   */
  const handleStreamDisconnection = useCallback((stream: DisplayStream) => {
    stream.isConnected = false;
    stream.isStreaming = false;
    stream.status = {
      connected: false,
      streaming: false,
      connectionName: null,
      latency: 0,
      fpsActual: 0,
      bytesReceived: 0,
      lastFrameTime: null
    };
    stream.websocket = null;

    onStreamDisconnected?.(stream.streamId);
    onStreamStatusChange?.(stream.streamId, stream.status);

    setConnectionCount(prev => Math.max(0, prev - 1));
    setStreamingCount(prev => Math.max(0, prev - 1));

    // Auto-reconnect if enabled
    if (enableAutoReconnect && stream.retryCount < 5) {
      const timeout = setTimeout(() => {
        stream.retryCount++;
        console.log(`[MultiStreamManager] Auto-reconnecting stream: ${stream.streamId} (attempt ${stream.retryCount})`);
        connectDisplayStream(stream);
      }, 2000 * Math.pow(2, stream.retryCount)); // Exponential backoff

      reconnectTimeouts.current.set(stream.streamId, timeout);
    }
  }, [enableAutoReconnect, connectDisplayStream, onStreamDisconnected, onStreamStatusChange]);

  /**
   * Handle stream errors
   */
  const handleStreamError = useCallback((stream: DisplayStream) => {
    stream.status = {
      connected: false,
      streaming: false,
      connectionName: stream.displayName,
      latency: 0,
      fpsActual: 0,
      bytesReceived: 0,
      lastFrameTime: null
    };
    onStreamStatusChange?.(stream.streamId, stream.status);
  }, [onStreamStatusChange]);

  // ============================================================================
  // STREAM CONTROL FUNCTIONS
  // ============================================================================

  /**
   * Start streaming for a specific display stream
   */
  const startStream = useCallback((streamId: string) => {
    const stream = streamsRef.current.get(streamId);
    if (!stream || !stream.websocket || !stream.isConnected) {
      console.warn(`[MultiStreamManager] Cannot start stream: ${streamId} - not connected`);
      return;
    }

    const startMessage = {
      type: 'start_desktop_stream',
      desktopClientId: stream.clientId,
      monitorId: stream.monitorId,
      config: stream.config,
      timestamp: new Date().toISOString()
    };

    stream.websocket.send(JSON.stringify(startMessage));
    console.log(`[MultiStreamManager] Started stream: ${streamId}`);
  }, []);

  /**
   * Stop streaming for a specific display stream
   */
  const stopStream = useCallback((streamId: string) => {
    const stream = streamsRef.current.get(streamId);
    if (!stream || !stream.websocket || !stream.isConnected) {
      console.warn(`[MultiStreamManager] Cannot stop stream: ${streamId} - not connected`);
      return;
    }

    const stopMessage = {
      type: 'stop_desktop_stream',
      desktopClientId: stream.clientId,
      monitorId: stream.monitorId,
      timestamp: new Date().toISOString()
    };

    stream.websocket.send(JSON.stringify(stopMessage));
    console.log(`[MultiStreamManager] Stopped stream: ${streamId}`);
  }, []);

  /**
   * Start all streams
   */
  const startAllStreams = useCallback(() => {
    streamsRef.current.forEach((stream) => {
      if (stream.isConnected && !stream.isStreaming) {
        startStream(stream.streamId);
      }
    });
  }, [startStream]);

  /**
   * Stop all streams
   */
  const stopAllStreams = useCallback(() => {
    streamsRef.current.forEach((stream) => {
      if (stream.isConnected && stream.isStreaming) {
        stopStream(stream.streamId);
      }
    });
  }, [stopStream]);

  /**
   * Connect all streams
   */
  const connectAllStreams = useCallback(async () => {
    setGlobalStatus('connecting');
    
    const connectionPromises = Array.from(streamsRef.current.values()).map(stream => 
      connectDisplayStream(stream)
    );

    try {
      await Promise.all(connectionPromises);
      setGlobalStatus('connected');
      console.log(`[MultiStreamManager] All streams connected successfully`);
    } catch (error) {
      console.error(`[MultiStreamManager] Failed to connect all streams:`, error);
      setGlobalStatus('error');
    }
  }, [connectDisplayStream]);

  /**
   * Disconnect all streams
   */
  const disconnectAllStreams = useCallback(() => {
    // Clear reconnect timeouts
    reconnectTimeouts.current.forEach(timeout => clearTimeout(timeout));
    reconnectTimeouts.current.clear();

    // Close all WebSocket connections
    streamsRef.current.forEach((stream) => {
      if (stream.websocket) {
        stream.websocket.close();
      }
    });

    // Reset state
    setDisplayStreams(new Map());
    streamsRef.current.clear();
    setConnectionCount(0);
    setStreamingCount(0);
    setGlobalStatus('disconnected');

    console.log(`[MultiStreamManager] All streams disconnected`);
  }, []);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  /**
   * Update streams when selected clients change
   */
  useEffect(() => {
    console.log(`[MultiStreamManager] Updating streams for ${selectedClients.length} clients`);
    
    // Disconnect existing streams
    disconnectAllStreams();

    // Create new streams for selected clients
    const newStreams = new Map<string, DisplayStream>();
    let streamCount = 0;

    selectedClients.forEach(client => {
      client.monitors.forEach(monitor => {
        if (streamCount >= maxStreams) return;

        const stream = createDisplayStream(
          client.clientId,
          monitor.monitorId,
          `${client.clientId} - ${monitor.name}`
        );

        newStreams.set(stream.streamId, stream);
        streamCount++;
      });
    });

    setDisplayStreams(newStreams);
    streamsRef.current = newStreams;

    console.log(`[MultiStreamManager] Created ${newStreams.size} display streams`);
  }, [selectedClients, maxStreams, createDisplayStream, disconnectAllStreams]);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      disconnectAllStreams();
    };
  }, [disconnectAllStreams]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return {
    // Stream management functions
    connectAllStreams,
    disconnectAllStreams,
    startAllStreams,
    stopAllStreams,
    startStream,
    stopStream,
    
    // Stream data
    displayStreams,
    globalStatus,
    connectionCount,
    streamingCount,
    
    // Individual stream access
    getStream: (streamId: string) => streamsRef.current.get(streamId),
    getAllStreams: () => Array.from(streamsRef.current.values())
  };
};

// Export a placeholder component for compatibility
export const MultiStreamManager: React.FC<MultiStreamManagerProps> = (props) => {
  useMultiStreamManager({
    ...props,
    onFrameReceived: props.onFrameReceived || (() => {}),
    onStreamConnected: props.onStreamConnected || (() => {}),
    onStreamDisconnected: props.onStreamDisconnected || (() => {}),
    onStreamStatusChange: props.onStreamStatusChange || (() => {})
  });
  return null;
};

export default MultiStreamManager;