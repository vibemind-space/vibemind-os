/**
 * Multi-Desktop Stream Grid Component
 * 
 * Restored basic functionality for dual monitor streaming
 * Author: TRAE Development Team
 * Version: 2.1.0
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';

// ============================================================================
// INTERFACES AND TYPES
// ============================================================================

interface StreamState {
  streamId: string;
  clientId: string;
  monitorId: string;
  canvasRef: React.RefObject<HTMLCanvasElement>;
  isConnected: boolean;
  isStreaming: boolean;
  frameCount: number;
  lastFrameTime: Date | null;
}

interface MultiDesktopStreamGridProps {
  /** Selected clients with their streams */
  selectedClients?: Array<{
    clientId: string;
    clientName: string;
    monitors: Array<{
      monitorId: string;
      name: string;
      resolution: { width: number; height: number };
    }>;
  }>;
  /** WebSocket server URL */
  serverUrl?: string;
  /** Maximum number of concurrent streams */
  maxStreams?: number;
  /** Grid layout configuration */
  gridLayout?: 'auto' | '1x1' | '2x2' | '3x3' | '4x4';
  /** Stream configuration */
  streamConfig?: any;
  /** Enable fullscreen mode for individual streams */
  enableFullscreen?: boolean;
  /** Enable stream controls */
  enableControls?: boolean;
  /** CSS class name */
  className?: string;
  /** Latest screenshots from parent component */
  latestScreenshots?: Record<string, string>;
  /** WebSocket instance from parent component */
  websocketInstance?: WebSocket | null;
  /** Callback when stream status changes */
  onStreamStatusChange?: (streamId: string, status: any) => void;
  /** Callback when stream is selected */
  onStreamSelect?: (streamId: string) => void;
  /** Callback when client disconnected */
  onClientDisconnected?: (clientId: string) => void;
  /** Callback when frame received */
  onFrameReceived?: (streamId: string, frameData: any) => void;
}

// ============================================================================
// MULTI-DESKTOP STREAM GRID COMPONENT
// ============================================================================

export const MultiDesktopStreamGrid: React.FC<MultiDesktopStreamGridProps> = ({
  selectedClients = [],
  serverUrl = WEBSOCKET_CONFIG.BASE_URL,
  maxStreams = 4,
  gridLayout = 'auto',
  streamConfig = {},
  enableFullscreen = true,
  enableControls = true,
  className = '',
  latestScreenshots = {},
  websocketInstance = null,
  onStreamStatusChange,
  onStreamSelect,
  onClientDisconnected,
  onFrameReceived
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================
  
  const [streamStates, setStreamStates] = useState<Map<string, StreamState>>(new Map());

  // ============================================================================
  // SCREENSHOT PROCESSING AND RENDERING
  // ============================================================================

  // Process screenshots from parent component and update canvas
  const processScreenshots = useCallback(() => {
    if (!latestScreenshots || Object.keys(latestScreenshots).length === 0) {
      console.log('[DEBUG] [MultiDesktopStreamGrid] No screenshots to process');
      return;
    }

    console.log('[DEBUG] [MultiDesktopStreamGrid] Processing screenshots:', Object.keys(latestScreenshots));
    console.log('[DEBUG] [MultiDesktopStreamGrid] Screenshot data:', latestScreenshots);

    setStreamStates(prevStreams => {
      const newStreams = new Map(prevStreams);
      
      // Process each screenshot
      Object.entries(latestScreenshots).forEach(([streamKey, imageUrl]) => {
        // Skip if this is just a client key without monitor info
        if (!streamKey.includes('_monitor_')) {
          console.log('[DEBUG] [MultiDesktopStreamGrid] Skipping non-monitor key:', streamKey);
          return;
        }
        
        console.log('[DEBUG] [MultiDesktopStreamGrid] Processing monitor stream:', streamKey);
        
        // Extract clientId and monitorId from streamKey (format: clientId_monitor_X)
        const parts = streamKey.split('_');
        if (parts.length < 3) return;
        
        const monitorIndex = parts[parts.length - 1]; // Last part is monitor index
        const clientId = parts.slice(0, -2).join('_'); // Everything before _monitor_X
        const streamId = `${clientId}_${monitorIndex}`;
        
        let stream = newStreams.get(streamId);
        
        if (!stream) {
          // Create new stream dynamically
          const canvasRef = React.createRef<HTMLCanvasElement>();
          stream = {
            streamId,
            clientId,
            monitorId: monitorIndex,
            canvasRef,
            isConnected: true,
            isStreaming: true,
            frameCount: 0,
            lastFrameTime: null
          };
          
          newStreams.set(streamId, stream);
          console.log(`[DEBUG] [MultiDesktopStreamGrid] Created stream for: ${streamId}`);
          console.log(`[DEBUG] [MultiDesktopStreamGrid] Stream details:`, { streamId, clientId, monitorId: monitorIndex });
        }
        
        // Update stream state
        stream.frameCount += 1;
        stream.lastFrameTime = new Date();
        stream.isStreaming = true;
        stream.isConnected = true;
        
        // Render frame to canvas
        setTimeout(() => {
          if (stream && stream.canvasRef.current) {
            renderImageToCanvas(stream, imageUrl);
            
            // Notify parent about frame received
            if (onFrameReceived) {
              onFrameReceived(streamId, { imageUrl, timestamp: new Date() });
            }
          }
        }, 0);
      });
      
      return newStreams;
    });
  }, [latestScreenshots, onFrameReceived]);

  // Debug: Log when latestScreenshots changes
  useEffect(() => {
    console.log('[DEBUG] [MultiDesktopStreamGrid] latestScreenshots changed:', Object.keys(latestScreenshots || {}));
    if (latestScreenshots && Object.keys(latestScreenshots).length > 0) {
      console.log('[DEBUG] [MultiDesktopStreamGrid] Calling processScreenshots...');
      processScreenshots();
    }
  }, [latestScreenshots, processScreenshots]);

  // ============================================================================
  // IMAGE RENDERING
  // ============================================================================

  // Render image data to canvas with proper aspect ratio handling
  const renderImageToCanvas = useCallback((stream: StreamState, imageUrl: string) => {
    const canvas = stream.canvasRef.current;
    if (!canvas) {
      console.warn(`[MultiDesktopStreamGrid] Canvas not found for stream: ${stream.streamId}`);
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      console.warn(`[MultiDesktopStreamGrid] Canvas context not available for stream: ${stream.streamId}`);
      return;
    }

    const img = new Image();
    
    img.onload = () => {
      try {
        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Calculate aspect ratio preserving dimensions
        const canvasAspect = canvas.width / canvas.height;
        const imgAspect = img.width / img.height;
        
        let drawWidth, drawHeight, drawX, drawY;
        
        if (imgAspect > canvasAspect) {
          // Image is wider than canvas
          drawWidth = canvas.width;
          drawHeight = canvas.width / imgAspect;
          drawX = 0;
          drawY = (canvas.height - drawHeight) / 2;
        } else {
          // Image is taller than canvas
          drawHeight = canvas.height;
          drawWidth = canvas.height * imgAspect;
          drawX = (canvas.width - drawWidth) / 2;
          drawY = 0;
        }
        
        // Draw image with calculated dimensions
        ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight);
        
        console.log(`[MultiDesktopStreamGrid] Rendered frame for ${stream.streamId}: ${img.width}x${img.height} -> ${Math.round(drawWidth)}x${Math.round(drawHeight)}`);
        
        // Update stream status
        if (onStreamStatusChange) {
          onStreamStatusChange(stream.streamId, {
            isConnected: true,
            isStreaming: true,
            frameCount: stream.frameCount,
            lastFrameTime: stream.lastFrameTime
          });
        }
        
      } catch (error) {
        console.error(`[MultiDesktopStreamGrid] Error rendering frame for ${stream.streamId}:`, error);
      }
    };
    
    img.onerror = (error) => {
      console.error(`[MultiDesktopStreamGrid] Error loading image for ${stream.streamId}:`, error);
    };
    
    // Set image source - handle both data URLs and base64 strings
    if (imageUrl.startsWith('data:')) {
      img.src = imageUrl;
    } else {
      img.src = `data:image/jpeg;base64,${imageUrl}`;
    }
  }, [onStreamStatusChange]);

  // ============================================================================
  // STREAM INITIALIZATION
  // ============================================================================

  useEffect(() => {
    console.log(`[MultiDesktopStreamGrid] Initializing streams for ${selectedClients.length} clients`);
    
    // Create streams based on selected clients
    const newStreams = new Map<string, StreamState>();
    
    if (selectedClients.length > 0) {
      selectedClients.forEach(client => {
        client.monitors.forEach(monitor => {
          const streamId = `${client.clientId}_${monitor.monitorId}`;
          const canvasRef = React.createRef<HTMLCanvasElement>();

          const stream: StreamState = {
            streamId,
            clientId: client.clientId,
            monitorId: monitor.monitorId,
            canvasRef,
            isConnected: false,
            isStreaming: false,
            frameCount: 0,
            lastFrameTime: null
          };

          newStreams.set(streamId, stream);
          console.log(`[MultiDesktopStreamGrid] Created stream: ${streamId} for ${monitor.name}`);
        });
      });
    }

    setStreamStates(newStreams);
  }, [selectedClients]);

  // ============================================================================
  // SCREENSHOT PROCESSING
  // ============================================================================

  useEffect(() => {
    if (!latestScreenshots || Object.keys(latestScreenshots).length === 0) {
      console.log('[MultiDesktopStreamGrid] No screenshots available');
      return;
    }

    // STRICT FILTER: Only process dual screen monitors (monitor_0 and monitor_1)
    const filteredScreenshots = Object.entries(latestScreenshots).filter(([streamKey]) => {
      return streamKey.includes('_monitor_0') || streamKey.includes('_monitor_1');
    });

    console.log(`[MultiDesktopStreamGrid] Processing ${filteredScreenshots.length} screenshots (filtered from ${Object.keys(latestScreenshots).length})`);

    setStreamStates(prevStreams => {
      const newStreams = new Map(prevStreams);

      // Process each screenshot
      filteredScreenshots.forEach(([streamKey, imageUrl]) => {
        // Skip pure client keys without monitor information
        if (!streamKey.includes('_monitor_') && !streamKey.match(/_\d+$/)) {
          // This is likely just a client key, skip it silently
          return;
        }
        
        // FILTER: Only process monitor_0 and monitor_1 for dual screen setup
        if (streamKey.includes('_monitor_') && !streamKey.includes('_monitor_0') && !streamKey.includes('_monitor_1')) {
          console.log(`[MultiDesktopStreamGrid] Skipping non-dual-screen monitor: ${streamKey}`);
          return;
        }
        
        // Parse stream key to extract clientId and monitorId
        // Expected formats: 
        // - clientId_monitor_X (old format)
        // - dual_screen_client_XXXX_monitor_X (new dual screen format)
        // - clientId_X (simplified format)
        const parts = streamKey.split('_');
        
        // Handle different stream key formats
        let clientId: string;
        let monitorId: string;
        
        if (streamKey.includes('_monitor_')) {
          // Format: clientId_monitor_X or dual_screen_client_XXXX_monitor_X
          const monitorIndex = parts.findIndex(part => part === 'monitor');
          if (monitorIndex === -1 || monitorIndex + 1 >= parts.length) {
            console.warn(`[MultiDesktopStreamGrid] Invalid monitor stream key format: ${streamKey}`);
            return;
          }
          
          // Extract clientId (everything before '_monitor_')
          clientId = parts.slice(0, monitorIndex).join('_');
          monitorId = parts[monitorIndex + 1];
          
          // For dual_screen_client format, use a shorter display name
          if (clientId.startsWith('dual_screen_client_')) {
            // Keep the original clientId for stream identification but create a display version
            // clientId remains: dual_screen_client_c7705943
            // This ensures proper stream matching
          }
        } else if (parts.length >= 2 && /^\d+$/.test(parts[parts.length - 1])) {
          // Format: clientId_X (where X is a number)
          monitorId = parts[parts.length - 1];
          clientId = parts.slice(0, -1).join('_');
        } else {
          console.warn(`[MultiDesktopStreamGrid] Invalid stream key format: ${streamKey}`);
          return;
        }
        
        const streamId = `${clientId}_${monitorId}`;
        console.log(`[MultiDesktopStreamGrid] Processing stream: ${streamKey} -> ${streamId} (Client: ${clientId.substring(0, 8)}..., Monitor: ${monitorId})`);

        let stream = newStreams.get(streamId);

        // Create stream dynamically if it doesn't exist
        if (!stream) {
          const canvasRef = React.createRef<HTMLCanvasElement>();
          stream = {
            streamId,
            clientId,
            monitorId,
            canvasRef,
            isConnected: true,
            isStreaming: true,
            frameCount: 0,
            lastFrameTime: null
          };
          newStreams.set(streamId, stream);
          console.log(`[MultiDesktopStreamGrid] Created dynamic stream: ${streamId}`);
        }

        // Update stream state
        stream.frameCount += 1;
        stream.lastFrameTime = new Date();
        stream.isStreaming = true;
        stream.isConnected = true;

        // Render screenshot to canvas
        if (imageUrl) {
          setTimeout(() => {
            renderImageToCanvas(stream!, imageUrl);
          }, 10);
        }

        newStreams.set(streamId, stream);
      });

      return newStreams;
    });
  }, [latestScreenshots, renderImageToCanvas]);

  // ============================================================================
  // RENDER - MINIMAL STRUCTURE WITH NO WRAPPER DIVS
  // ============================================================================

  return (
    <>
      {Array.from(streamStates.values())
        .filter(stream => stream.monitorId === '0' || stream.monitorId === '1') // Only show monitor 0 and 1
        .slice(0, 2) // Ensure maximum 2 monitors
        .map((stream) => {
        // Extract monitor information for better display
        const getMonitorDisplayInfo = (clientId: string, monitorId: string) => {
          // Handle different client ID formats
          let displayClientId: string;
          if (clientId.startsWith('dual_screen_client_')) {
            // Extract the unique part from dual_screen_client_c7705943
            const uniquePart = clientId.replace('dual_screen_client_', '');
            displayClientId = uniquePart.substring(0, 8);
          } else {
            displayClientId = clientId.substring(0, 8);
          }
          
          const monitorNumber = parseInt(monitorId) || 0;
          const isPrimary = monitorId === '0';
          
          return {
            title: `Monitor ${monitorNumber} ${isPrimary ? '(Primary)' : '(Secondary)'}`,
            subtitle: `Client: ${displayClientId}...`,
            position: isPrimary ? 'Left Display' : 'Right Display'
          };
        };
        
        const displayInfo = getMonitorDisplayInfo(stream.clientId, stream.monitorId);
        
        return (
          <canvas
            key={stream.streamId}
            ref={stream.canvasRef}
            width={800}
            height={600}
            className={`w-full bg-black border rounded ${className}`}
            style={{ aspectRatio: '4/3' }}
            title={`${displayInfo.title} - ${displayInfo.subtitle} • ${displayInfo.position} - Status: ${stream.isStreaming ? 'Streaming' : stream.isConnected ? 'Connected' : 'Disconnected'} | Frames: ${stream.frameCount} | Stream: ${stream.streamId}`}
          />
        );
      })}
      
      {streamStates.size === 0 && (
        <p className={`text-center py-8 text-gray-600 ${className}`}>
          No Streams Available - Waiting for desktop clients to connect...
        </p>
      )}
    </>
  );
};