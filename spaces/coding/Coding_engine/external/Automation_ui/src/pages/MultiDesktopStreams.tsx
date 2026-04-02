import React, { useState, useEffect, useRef, useMemo, memo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { ScanLine } from 'lucide-react';
import { DualCanvasOCRDesigner } from '@/components/trae/liveDesktop/DualCanvasOCRDesigner';
import { ConnectionStatusCard } from '@/components/trae/liveDesktop/ConnectionStatusCard';
import { StreamControlsCard } from '@/components/trae/liveDesktop/StreamControlsCard';
import { ClientSelectorCard, type DesktopClient as ClientSelectorDesktopClient } from '@/components/trae/liveDesktop/ClientSelectorCard';
import { DesktopScreensGrid, type DesktopScreen as DesktopScreensGridDesktopScreen } from '@/components/trae/liveDesktop/DesktopScreensGrid';
import { DesktopAutomationPanel } from '@/components/trae/liveDesktop/DesktopAutomationPanel';
import { DualMonitorWorkflow } from '@/components/trae/liveDesktop/DualMonitorWorkflow';
import { WEBSOCKET_CONFIG, sendWebSocketMessage } from '@/config/websocketConfig';
import { useWebSocketReconnect, type ConnectionStatus, type CircuitBreakerState } from '@/hooks/useWebSocketReconnect';
import { isElectron, onScreenFrame, type ScreenCaptureFrame } from '@/services/electronBridge';

// Use imported types for compatibility
type DesktopClient = ClientSelectorDesktopClient;

interface DesktopScreen {
  id: string;
  name: string;
  thumbnail?: string;
  isActive: boolean;
  resolution: {
    width: number;
    height: number;
  };
  connected: boolean;
}

const MultiDesktopStreams: React.FC = () => {
  const navigate = useNavigate();
  
  const [availableClients, setAvailableClients] = useState<DesktopClient[]>([]);
  const [selectedClients, setSelectedClients] = useState<string[]>([]);
  
  // Stream control state
  const [isStreamingActive, setIsStreamingActive] = useState(false);
  
  // Real desktop clients state
  const [desktopClients, setDesktopClients] = useState<any[]>([]);
  const [desktopScreens, setDesktopScreens] = useState<DesktopScreen[]>([]);
  const [latestScreenshots, setLatestScreenshots] = useState<{[clientId: string]: string}>({});

  // State for OCR configuration
  const [ocrConfig, setOcrConfig] = useState({
    regions: [],
    isActive: false,
    extractionInterval: 5000,
    confidenceThreshold: 0.8
  });

  // Electron mode detection - check both on mount and after a delay
  const [isElectronMode, setIsElectronMode] = useState(() => isElectron());

  // Re-check Electron mode after mount (in case preload script loaded late)
  useEffect(() => {
    const checkElectron = () => {
      const electronDetected = isElectron();
      if (electronDetected && !isElectronMode) {
        console.warn('[MultiDesktopStreams] Electron mode detected after mount!');
        setIsElectronMode(true);
      }
    };

    // Check immediately and after short delays
    checkElectron();
    const timer1 = setTimeout(checkElectron, 100);
    const timer2 = setTimeout(checkElectron, 500);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, [isElectronMode]);

  // Generate unique client ID for this session
  const clientIdRef = useRef<string>(`web_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`);

  // ============================================
  // ELECTRON NATIVE SCREEN CAPTURE
  // ============================================
  useEffect(() => {
    console.warn('[Electron] Screen capture effect running, isElectronMode:', isElectronMode);

    if (!isElectronMode) {
      console.warn('[Electron] NOT in Electron mode - skipping native screen capture');
      return;
    }

    console.warn('[Electron] Running in Electron mode - using native screen capture');

    // Set streaming as active immediately in Electron mode
    setIsStreamingActive(true);

    // Subscribe to native screen capture frames
    const unsubscribe = onScreenFrame((frame: ScreenCaptureFrame) => {
      console.warn('[Electron] Frame received:', {
        displayIndex: frame.displayIndex,
        displayName: frame.displayName,
        width: frame.width,
        height: frame.height,
        dataLength: frame.data?.length || 0
      });

      const screenshotKey = `electron_${frame.displayIndex}`;
      const clientId = `electron_display_${frame.displayIndex}`;

      // Store frame in latestScreenshots (same format as WebSocket frames)
      setLatestScreenshots(prev => ({
        ...prev,
        [screenshotKey]: frame.data,
        [clientId]: frame.data,
        [`${clientId}_monitor_0`]: frame.data
      }));

      // Update desktop screens if not already present
      setDesktopScreens(prev => {
        const screenId = `electron_display_${frame.displayIndex}`;
        const exists = prev.some(s => s.id === screenId);
        if (!exists) {
          return [...prev, {
            id: screenId,
            name: frame.displayName || `Display ${frame.displayIndex + 1}`,
            isActive: true,
            resolution: { width: frame.width, height: frame.height },
            connected: true
          }];
        }
        return prev;
      });

      // Update available clients AND auto-select them (using clientId from line 106)
      setAvailableClients(prev => {
        const exists = prev.some(c => c.id === clientId);
        if (!exists) {
          const newClient: DesktopClient = {
            id: clientId,
            connected: true,
            monitors: ['monitor_0'],
            timestamp: new Date().toISOString()
          };
          return [...prev, newClient];
        }
        return prev;
      });

      // Auto-select Electron clients for display
      setSelectedClients(prev => {
        if (!prev.includes(clientId)) {
          console.warn('[Electron] Auto-selecting client:', clientId);
          return [...prev, clientId];
        }
        return prev;
      });
    });

    return () => {
      unsubscribe();
    };
  }, [isElectronMode]);

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((event: MessageEvent, ws: WebSocket) => {
    console.log('📨 [DEBUG] Received message from server:', event.data);
    try {
      const message = JSON.parse(event.data);
      console.log('📥 [DEBUG] WebSocket message received - TYPE:', message.type);
      console.log('📥 [DEBUG] WebSocket message received - FULL MESSAGE:', message);
      
      switch (message.type) {
        case 'handshake_ack':
          console.log('Handshake acknowledged:', message);
          break;
          
        case 'desktop_clients_list': {
          console.log('🔍 [DEBUG] Received desktop clients list:', message.clients);
          console.log('🔍 [DEBUG] Message object:', message);
          
          // Map clients to include 'id' field from 'clientId' for compatibility
          const mappedClients = (message.clients || []).map((client: any) => ({
            ...client,
            id: client.clientId || client.id // Ensure id field exists
          }));
          
          setAvailableClients(mappedClients);
          setDesktopClients(mappedClients);
          
          // ============================================================================
          // AUTOMATIC STREAMING FOR ALL AVAILABLE DESKTOPS
          // ============================================================================

          // Auto-select all connected clients for streaming (no limit)
          const connectedClients = mappedClients.filter((client: any) => client.connected);
          console.log('🔍 [DEBUG] All clients from message:', message.clients);
          console.log('🔍 [DEBUG] Connected clients filtered:', connectedClients);
          console.log(`🖥️ Starting automatic streaming for ${connectedClients.length} available desktop clients...`);
          
          if (connectedClients.length > 0) {
            // Select all available clients (no limit)
            const clientIds = connectedClients.map((client: any) => client.id);
            setSelectedClients(clientIds);
            
            // Stream als aktiv markieren
            setIsStreamingActive(true);

            // CRITICAL: Subscribe to desktop streams to receive frame_data messages
            // This must happen BEFORE start_stream to ensure we receive frames
            setTimeout(() => {
              console.log('📺 [SUBSCRIBE] Subscribing to desktop streams for frame receiving...');
              clientIds.forEach((clientId) => {
                sendWebSocketMessage(ws, {
                  type: 'subscribe_desktop_stream',
                  desktopClientId: clientId,
                  timestamp: new Date().toISOString()
                });
                console.log(`📺 [SUBSCRIBE] Subscribed to stream from ${clientId}`);
              });
            }, 200);

            // Auto-start streaming for all available clients with dynamic monitor support
            setTimeout(() => {
              console.log('🔍 [DEBUG] setTimeout executed - starting auto streaming for clients:', clientIds);
              clientIds.forEach((clientId, index) => {
                console.log(`🚀 Starting automatic streaming for client ${index + 1}/${clientIds.length}: ${clientId}`);

                // Find the corresponding client in the response to determine available monitors
                const clientData = connectedClients.find((c: any) => c.id === clientId);
                const availableMonitors = clientData?.monitors || clientData?.availableMonitors || [];

                // Convert monitor objects to monitor IDs
                const monitorIds = availableMonitors.length > 0
                  ? availableMonitors.map((m: any, monitorIndex: number) => {
                      if (typeof m === 'object' && m !== null && 'index' in m) {
                        return `monitor_${m.index}`;
                      }
                      if (typeof m === 'string') {
                        return m;
                      }
                      return `monitor_${monitorIndex}`;
                    })
                  : ['monitor_0', 'monitor_1']; // Default fallback

                console.log(`📺 Client ${clientId} has ${monitorIds.length} available monitors:`, monitorIds);

                // Start streaming only for available monitors
                monitorIds.forEach((monitorId: string) => {
                  const streamMessage = {
                    type: 'start_stream', // Changed from start_desktop_stream
                    desktopClientId: clientId,
                    monitorId: monitorId,
                    timestamp: new Date().toISOString(),
                    autoStart: true // Flag for automatic start
                  };
                  console.log('🔍 [DEBUG] Sending WebSocket message:', streamMessage);
                  sendWebSocketMessage(ws, streamMessage);
                });
              });

              console.log(`✅ Automatic streaming initialized for all ${clientIds.length} desktop clients`);
            }, 1000);
          } else {
            console.log('⚠️ No connected desktop clients found for automatic streaming');
          }
          
          // Request screenshots from all connected clients
          (message.clients || []).forEach((client: any) => {
            if (client.connected) {
              requestScreenshot(client.id, ws);
            }
          });
          break;
        }
          
        case 'desktop_connected':
          console.log('🔗 New desktop client connected:', message.desktopClientId);

          // Automatically add the new client to selection
          setSelectedClients(prev => {
            if (!prev.includes(message.desktopClientId)) {
              const newSelection = [...prev, message.desktopClientId];

              // Start automatic streaming for the new client
              setTimeout(() => {
                console.log(`🚀 Starting automatic streaming for new client: ${message.desktopClientId}`);

                // Convert monitor objects to monitor IDs
                const availableMonitors = message.availableMonitors || message.monitors || ['monitor_0', 'monitor_1'];
                const monitorIds = availableMonitors.map((m: any, index: number) => {
                  // If monitor is an object with index field, use monitor_<index>
                  if (typeof m === 'object' && m !== null && 'index' in m) {
                    return `monitor_${m.index}`;
                  }
                  // If monitor is already a string, use it as-is
                  if (typeof m === 'string') {
                    return m;
                  }
                  // Default: use array index
                  return `monitor_${index}`;
                });
                console.log(`📺 New client ${message.desktopClientId} has ${monitorIds.length} available monitors:`, monitorIds);

                monitorIds.forEach((monitorId: string) => {
                  sendWebSocketMessage(ws, {
                    type: 'start_stream', // Changed from start_desktop_stream
                    desktopClientId: message.desktopClientId,
                    monitorId: monitorId,
                    timestamp: new Date().toISOString(),
                    autoStart: true
                  });
                });

                console.log(`✅ Automatic streaming started for new client ${message.desktopClientId}`);
              }, 500);
              
              return newSelection;
            }
            return prev;
          });
          
          // Refresh client list
          sendWebSocketMessage(ws, {
            type: 'get_desktop_clients',
            timestamp: new Date().toISOString()
          });
          break;
          
        case 'desktop_disconnected':
          console.log('Desktop client disconnected:', message.desktopClientId);
          setAvailableClients(prev => 
            prev.filter(client => client.id !== message.desktopClientId)
          );
          setSelectedClients(prev => 
            prev.filter(id => id !== message.desktopClientId)
          );
          setDesktopClients(prev => prev.filter(client => client.id !== message.desktopClientId));
          setDesktopScreens(prev => prev.filter(screen => screen.id !== message.desktopClientId));
          
          // Remove screenshot from cache
          setLatestScreenshots(prev => {
            const updated = { ...prev };
            delete (updated as any)[message.desktopClientId];
            return updated;
          });
          break;
          
        case 'analysis_result':
          console.log('🤖 [DEBUG] Analysis result received:', message);
          // AutoGen analysis removed - placeholder for future implementation
          break;
          
        case 'autogen_connected':
          console.log('🤖 AutoGen service connected');
          // AutoGen state removed - placeholder for future implementation
          break;
          
        case 'autogen_disconnected':
          console.log('🤖 AutoGen service disconnected');
          // AutoGen state removed - placeholder for future implementation
          break;

        case 'frame_data':
          console.log('📸 Frame data received:', {
            desktopClientId: message.desktopClientId,
            monitorId: message.monitorId,
            dimensions: message.metadata ? `${message.metadata.width}x${message.metadata.height}` : 'N/A',
            format: message.metadata?.format,
            frameNumber: message.frameNumber,
            frameDataLength: message.frameData ? message.frameData.length : 0
          });

          // CRITICAL FIX: Store frame data in latestScreenshots for display
          if (message.frameData) {
            const clientId = message.desktopClientId || message.metadata?.clientId || message.clientId;
            const monitorId = message.monitorId || 'monitor_0';
            const format = message.metadata?.format || 'jpeg';
            
            // Create data URL from base64 frame data
            const imageUrl = `data:image/${format};base64,${message.frameData}`;
            
            // Store with clientId_monitorId key
            const screenshotKey = `${clientId}_${monitorId}`;
            
            console.log(`📷 [FRAME STORE] Key: ${screenshotKey}, Size: ${message.frameData.length} bytes`);
            
            setLatestScreenshots(prev => {
              const updated = {
                ...prev,
                [screenshotKey]: imageUrl,
                // Also store without monitor suffix for fallback
                [clientId]: imageUrl
              };
              console.log(`📷 [FRAME STORE] Total stored keys:`, Object.keys(updated).length);
              return updated;
            });
          }

          // Log frame metrics (processFrame removed)
          console.log('Frame metrics:', {
            desktopClientId: message.desktopClientId,
            monitorId: message.monitorId || 'monitor_0',
            frameNumber: message.frameNumber || 0,
            timestamp: message.timestamp || new Date().toISOString()
          });

          break;

        case 'dual_screen_frame':
          console.log('🔄 [DEBUG] Dual-screen frame received - RAW MESSAGE:', message);
          // Process dual-screen frame data (simplified)
          if (message.client_id && message.image_data) {
            const format = message.metadata?.format || 'jpeg';
            const isSvg = format.toLowerCase().includes('svg');
            const imageUrl = isSvg
              ? `data:image/svg+xml;base64,${message.image_data}`
              : `data:image/${format};base64,${message.image_data}`;

            const clientId = message.client_id;
            let monitorId = 'monitor_0';
            if (typeof message.screen_id === 'number') {
              monitorId = `monitor_${message.screen_id}`;
            } else if (message.screen_id === 'screen1') {
              monitorId = 'monitor_0';
            } else if (message.screen_id === 'screen2') {
              monitorId = 'monitor_1';
            }

            const screenshotKey = `${clientId}_${monitorId}`;
            setLatestScreenshots(prev => ({
              ...prev,
              [screenshotKey]: imageUrl,
              [clientId]: imageUrl
            }));
          }
          break;

        case 'connection_established':
          console.log('Connection established:', message);
          break;
          
        case 'desktop_stream_status':
          console.log('Desktop stream status:', message);
          break;
          
        case 'start_capture':
          console.log('🎬 Start capture message received:', message);
          if (message.config) {
            console.log('📋 Capture configuration:', message.config);
          }
          break;
          
        case 'capture_screenshot':
          console.log('📸 Capture screenshot message received:', message);
          break;
          
        case 'screenshot_error':
          console.log('❌ Screenshot error received:', message);
          if (message.clientId && message.error) {
            console.log(`❌ Error for client ${message.clientId}: ${message.error}`);
          }
          break;
          
        case 'stop_desktop_stream':
          console.log('⏹️ Stop desktop stream message received:', message);
          if (message.reason) {
            console.log(`⏹️ Stop reason: ${message.reason}`);
          }
          break;
          
        case 'start_desktop_stream':
          console.log('▶️ Start desktop stream message received:', message);
          if (message.fps || message.quality || message.scale || message.format) {
            console.log('📋 Stream configuration:', {
              fps: message.fps,
              quality: message.quality,
              scale: message.scale,
              format: message.format
            });
          }
          break;
          
        case 'stream_started':
          console.log('✅ Stream started acknowledgment:', message);
          console.log(`✅ Desktop client ${message.desktopClientId} started streaming ${message.monitorId ? 'monitor: ' + JSON.stringify(message.monitorId) : ''}`);
          console.log(`📡 Stream initiated via: ${message.viaDatabase ? 'Database Command' : message.viaBroadcast ? 'Realtime Broadcast' : 'Direct Message'}`);
          break;

        case 'error':
          console.error('❌ Server error:', message.error);
          if (message.desktopClientId) {
            console.error(`❌ Error for desktop client: ${message.desktopClientId}`);

            // If error is "Desktop client not found", remove it from state
            if (message.error && message.error.includes('not found')) {
              console.log(`🧹 Removing non-existent client from state: ${message.desktopClientId}`);
              setSelectedClients(prev => prev.filter(id => id !== message.desktopClientId));
              setAvailableClients(prev => prev.filter(client => client.id !== message.desktopClientId));
              setDesktopClients(prev => prev.filter(client => client.id !== message.desktopClientId));
              setDesktopScreens(prev => prev.filter(screen => !screen.id.startsWith(message.desktopClientId)));
              setLatestScreenshots(prev => {
                const updated = { ...prev };
                Object.keys(updated).forEach(key => {
                  if (key.startsWith(message.desktopClientId)) {
                    delete updated[key];
                  }
                });
                return updated;
              });
            }
          }
          break;

        default:
          console.log('Unhandled message type:', message.type);
      }
    } catch (error) {
      console.error('Error processing WebSocket message:', error);
    }
  }, []);

  // Handshake message for WebSocket connection
  const handshakeMessage = useMemo(() => ({
    type: 'handshake',
    clientId: clientIdRef.current,
    clientType: 'web',
    subType: 'multi_desktop_streams',
    timestamp: new Date().toISOString()
  }), []);

  // WebSocket URL
  const wsUrl = useMemo(() => 
    `${WEBSOCKET_CONFIG.BASE_URL}${WEBSOCKET_CONFIG.ENDPOINTS.MULTI_DESKTOP}`,
    []
  );

  // Handle WebSocket open - request desktop clients
  const handleWebSocketOpen = useCallback((ws: WebSocket) => {
    console.log('✅ Connected to Supabase Edge Function');
    
    // Request available desktop clients after handshake
    setTimeout(() => {
      if (ws.readyState === WebSocket.OPEN) {
        sendWebSocketMessage(ws, {
          type: 'get_desktop_clients',
          timestamp: new Date().toISOString()
        });
      }
    }, 500);
  }, []);

  // Handle WebSocket close - cleanup state
  const handleWebSocketClose = useCallback((event: CloseEvent) => {
    console.log('🔌 [DEBUG] WebSocket connection closed:', event.code, event.reason);
    
    // Only clear state on intentional disconnect
    if (event.code === 1000) {
      setAvailableClients([]);
      setSelectedClients([]);
      setDesktopScreens([]);
      setLatestScreenshots({});
    }
  }, []);

  // Use the WebSocket reconnect hook
  const {
    websocket,
    status,
    reconnectAttempt,
    reconnect,
    disconnect,
    sendMessage,
    isConnected,
    lastError,
    circuitBreakerState,
    resetCircuitBreaker
  } = useWebSocketReconnect({
    url: wsUrl,
    handshakeMessage,
    onOpen: handleWebSocketOpen,
    onMessage: handleWebSocketMessage,
    onClose: handleWebSocketClose,
    autoReconnect: true,
    maxReconnectAttempts: WEBSOCKET_CONFIG.CONNECTION.MAX_RECONNECT_ATTEMPTS,
    reconnectDelay: WEBSOCKET_CONFIG.CONNECTION.RECONNECT_DELAY,
    exponentialBackoff: true,
    circuitBreakerThreshold: 5,
    circuitBreakerTimeout: 30000
  });

  // Helper function to request screenshot
  const requestScreenshot = useCallback((clientId: string, ws?: WebSocket) => {
    const targetWs = ws || websocket;
    if (targetWs?.readyState === WebSocket.OPEN) {
      targetWs.send(JSON.stringify({
        type: 'request_screenshot',
        desktopClientId: clientId,
        timestamp: new Date().toISOString()
      }));
    }
  }, [websocket]);

  const generatePlaceholderThumbnail = (index: number) => {
    const colors = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'];
    const color = colors[index % colors.length];
    return `data:image/svg+xml;base64,${btoa(`<svg width="320" height="180" viewBox="0 0 320 180" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="320" height="180" fill="${color}"/><rect x="20" y="20" width="280" height="140" fill="#FFFFFF" rx="8"/><rect x="40" y="40" width="240" height="100" fill="#F9FAFB"/></svg>`)}`;
  };

  const refreshClientList = useCallback(() => {
    if (websocket?.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({
        type: 'get_desktop_clients',
        timestamp: new Date().toISOString()
      }));
    }
  }, [websocket]);

  const toggleClientSelection = useCallback((clientId: string) => {
    setSelectedClients(prev => {
      const isCurrentlySelected = prev.includes(clientId);
      const newSelection = isCurrentlySelected
        ? prev.filter(id => id !== clientId)
        : [...prev, clientId];

      console.log(`🖥️ Client ${clientId} ${newSelection.includes(clientId) ? 'selected' : 'deselected'}`);
      return newSelection;
    });
  }, []);

  const selectAllClients = useCallback(() => {
    const connectableClients = availableClients
      .filter(client => client.connected)
      .map(client => client.id);

    console.log(`🖥️ Selecting all available desktop clients: ${connectableClients.length} clients`);
    setSelectedClients(connectableClients);

    // Auto-start streaming for ALL selected clients with dynamic monitor support
    if (websocket && connectableClients.length > 0) {
      setTimeout(() => {
        connectableClients.forEach((clientId, index) => {
          console.log(`🚀 Starting streaming for client ${index + 1}/${connectableClients.length}: ${clientId}`);

          const clientData = availableClients.find(client => client.id === clientId);
          const availableMonitors = clientData?.monitors || clientData?.availableMonitors || [];

          const monitorIds = availableMonitors.length > 0
            ? availableMonitors.map((m: any, mIndex: number) => {
                if (typeof m === 'object' && m !== null && 'index' in m) {
                  return `monitor_${m.index}`;
                }
                if (typeof m === 'string') {
                  return m;
                }
                return `monitor_${mIndex}`;
              })
            : ['monitor_0', 'monitor_1'];

          console.log(`📺 Client ${clientId} has ${monitorIds.length} available monitors:`, monitorIds);

          monitorIds.forEach((monitorId: string) => {
            websocket?.send(JSON.stringify({
              type: 'start_stream',
              desktopClientId: clientId,
              monitorId: monitorId,
              timestamp: new Date().toISOString(),
              manualStart: true
            }));
          });
        });

        console.log(`✅ Streaming started for all ${connectableClients.length} desktop clients`);
      }, 500);
    } else {
      console.log('⚠️ No connected desktop clients available for streaming');
    }
  }, [availableClients, websocket]);

  const clearSelection = useCallback(() => {
    // Stop streaming for all currently selected clients
    if (websocket && selectedClients.length > 0) {
      console.log(`🛑 Stopping streaming for all ${selectedClients.length} selected clients`);

      selectedClients.forEach((clientId, index) => {
        console.log(`🛑 Stopping streaming for client ${index + 1}/${selectedClients.length}: ${clientId}`);

        const clientData = availableClients.find(client => client.id === clientId);
        const availableMonitors = clientData?.monitors || clientData?.availableMonitors || [];

        const monitorIds = availableMonitors.length > 0
          ? availableMonitors.map((m: any, mIndex: number) => {
              if (typeof m === 'object' && m !== null && 'index' in m) {
                return `monitor_${m.index}`;
              }
              if (typeof m === 'string') {
                return m;
              }
              return `monitor_${mIndex}`;
            })
          : ['monitor_0', 'monitor_1'];

        monitorIds.forEach((monitorId: string) => {
          websocket?.send(JSON.stringify({
            type: 'stop_stream',
            desktopClientId: clientId,
            monitorId: monitorId,
            timestamp: new Date().toISOString(),
            manualStop: true
          }));
        });
      });

      console.log('✅ Streaming stopped for all clients');
    }

    setSelectedClients([]);
  }, [selectedClients, availableClients, websocket]);

  // Stream control functions
  const startLiveStream = useCallback(() => {
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
      console.error('❌ WebSocket not connected - cannot start streaming');
      return;
    }

    // Select all connected clients if none are currently selected
    if (selectedClients.length === 0) {
      const connectableClients = availableClients.filter(client => client.connected);
      if (connectableClients.length > 0) {
        setSelectedClients(connectableClients.map(client => client.id));
      } else {
        console.warn('⚠️ No clients selected - cannot start streaming');
        return;
      }
    }

    setIsStreamingActive(true);

    // Start streaming for each selected client
    selectedClients.forEach((clientId) => {
      const client = availableClients.find(c => c.id === clientId);
      if (!client) return;

      client.monitors && client.monitors.forEach((monitor: any, index: number) => {
        const monitorId = monitor.monitorId || `monitor_${index}`;
        console.log(`🚀 Starting streaming for ${clientId} monitor ${index + 1}: ${monitorId}`);

        const startMessage = {
          type: 'start_stream',
          desktopClientId: clientId,
          monitorId: monitorId,
          timestamp: new Date().toISOString(),
          manualStart: true
        };
        websocket?.send(JSON.stringify(startMessage));
      });
    });

    console.log(`✅ Live streaming started for ${selectedClients.length} clients`);
  }, [selectedClients, availableClients, websocket]);

  const stopLiveStream = useCallback(() => {
    if (websocket && websocket.readyState === WebSocket.OPEN) { 
      // Stop streaming for each client
      selectedClients.forEach((clientId: string) => {
        console.log(`HALTING Stream for desktop id=${clientId}`);
        websocket?.send(JSON.stringify([
          "stop_desktop_stream",
          true,
          clientId,
          "halting stream",
          clientId,
        ]));
      });

      console.log(`✅ Live streaming stopped for ${selectedClients.length} clients`);
    }

    setIsStreamingActive(false);
  }, [selectedClients, websocket]);

  const switchToDesktop = useCallback((desktopId: string) => {
    setDesktopScreens(prev => 
      prev.map(desktop => ({
        ...desktop,
        isActive: desktop.id === desktopId
      }))
    );
    console.log(`Switched to desktop: ${desktopId}`);
  }, []);

  const createNewDesktop = useCallback(() => {
    const newDesktopId = `desktop_${desktopScreens.length + 1}`;
    const newDesktop: DesktopScreen = {
      id: newDesktopId,
      name: `Desktop ${desktopScreens.length + 1}`,
      isActive: false,
      resolution: { width: 1920, height: 1080 },
      connected: true,
      thumbnail: generatePlaceholderThumbnail(desktopScreens.length)
    };
    
    setDesktopScreens(prev => [...prev, newDesktop]);
    console.log(`Created new desktop: ${newDesktopId}`);
  }, [desktopScreens.length]);

  // Memoized desktop screens grid render
  const renderDesktopScreensGrid = useCallback(() => (
    <DesktopScreensGrid
      desktopScreens={desktopScreens}
      latestScreenshots={latestScreenshots}
      onSwitchDesktop={switchToDesktop}
      onCreateNewDesktop={createNewDesktop}
    />
  ), [desktopScreens, latestScreenshots, switchToDesktop, createNewDesktop]);

  // Memoized connection status render with enhanced UI
  const renderConnectionStatus = useCallback(() => (
    <ConnectionStatusCard
      status={status}
      isConnected={isConnected}
      isLoading={status === 'connecting' || status === 'reconnecting'}
      lastError={lastError}
      reconnectAttempt={reconnectAttempt}
      maxReconnectAttempts={WEBSOCKET_CONFIG.CONNECTION.MAX_RECONNECT_ATTEMPTS}
      circuitBreakerState={circuitBreakerState}
      onConnect={reconnect}
      onDisconnect={disconnect}
      onRetry={reconnect}
      onResetCircuitBreaker={resetCircuitBreaker}
    />
  ), [status, isConnected, lastError, reconnectAttempt, circuitBreakerState, reconnect, disconnect, resetCircuitBreaker]);

  // Memoized stream controls render
  const renderStreamControls = useCallback(() => (
    <StreamControlsCard
      isStreamingActive={isStreamingActive}
      isConnected={isConnected}
      selectedClientsCount={selectedClients.length}
      onStartStream={startLiveStream}
      onStopStream={stopLiveStream}
    />
  ), [isStreamingActive, isConnected, selectedClients.length]);

  // Memoized client selector render
  const renderClientSelector = useCallback(() => (
    <ClientSelectorCard
      availableClients={availableClients}
      selectedClients={selectedClients}
      isConnected={isConnected}
      onToggleClient={toggleClientSelection}
      onSelectAll={selectAllClients}
      onClearSelection={clearSelection}
      onRefresh={refreshClientList}
    />
  ), [availableClients, selectedClients, isConnected, toggleClientSelection, selectAllClients, clearSelection, refreshClientList]);

  // Memoize selectedClientsWithMonitors to prevent infinite re-renders
  const selectedClientsWithMonitors = useMemo(() => {
    return selectedClients.map(clientId => {
      return {
        clientId,
        clientName: `Desktop ${clientId.substring(0, 8)}`,
        monitors: [
          { 
            monitorId: 'monitor_0', 
            name: 'Primary Display',
            resolution: { width: 1920, height: 1080 }
          },
          { 
            monitorId: 'monitor_1', 
            name: 'Secondary Display',
            resolution: { width: 1920, height: 1080 }
          }
        ]
      };
    });
  }, [selectedClients]); 

  const renderDualCanvasOCRDesigner = () => {
    // Get primary and secondary monitor streams from selected clients
    const primaryStreamUrl = selectedClients.length > 0
      ? latestScreenshots[`${selectedClients[0]}_monitor_0`] || latestScreenshots[selectedClients[0]]
      : null;

    const secondaryStreamUrl = selectedClients.length > 0
      ? latestScreenshots[`${selectedClients[0]}_monitor_1`] ||
        (selectedClients.length > 1 ? latestScreenshots[`${selectedClients[1]}_monitor_0`] || latestScreenshots[selectedClients[1]] : null)
      : null;

    // Debug logging for OCR Designer streams
    console.log('[MultiDesktopStreams] OCR Designer stream URLs:', {
      selectedClients,
      primaryStreamUrl: primaryStreamUrl ? `${primaryStreamUrl.substring(0, 50)}...` : 'NULL',
      secondaryStreamUrl: secondaryStreamUrl ? `${secondaryStreamUrl.substring(0, 50)}...` : 'NULL',
      latestScreenshotsKeys: Object.keys(latestScreenshots)
    });

    // Workflow execution handlers
    const handleWorkflowExecute = (nodeConfig: any) => {
      console.log('🚀 Executing workflow for node:', nodeConfig.id);
      console.log('Actions to execute:', nodeConfig.actions);
      
      // Send workflow execution command via WebSocket
      if (websocket?.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
          type: 'execute_workflow',
          nodeConfig: nodeConfig,
          timestamp: new Date().toISOString()
        }));
      }
    };

    const handleWorkflowStop = (nodeId: string) => {
      console.log('🛑 Stopping workflow for node:', nodeId);
      
      // Send workflow stop command via WebSocket
      if (websocket?.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
          type: 'stop_workflow',
          nodeId: nodeId,
          timestamp: new Date().toISOString()
        }));
      }
    };

    const handleNodeConfigSave = (nodeConfig: any) => {
      console.log('💾 Saving node configuration:', nodeConfig);
      
      // Save node configuration (could be to localStorage or backend)
      localStorage.setItem(`node_config_${nodeConfig.id}`, JSON.stringify(nodeConfig));
      
      // Optionally send to backend via WebSocket
      if (websocket?.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
          type: 'save_node_config',
          nodeConfig: nodeConfig,
          timestamp: new Date().toISOString()
        }));
      }
    };

    return (
      <DualCanvasOCRDesigner
        ocrConfig={ocrConfig}
        setOcrConfig={setOcrConfig}
        primaryStreamUrl={primaryStreamUrl}
        secondaryStreamUrl={secondaryStreamUrl}
        isConnected={isConnected}
        selectedClients={selectedClients}
        onConnect={reconnect}
        onDisconnect={disconnect}
        onWorkflowExecute={handleWorkflowExecute}
        onWorkflowStop={handleWorkflowStop}
        onNodeConfigSave={handleNodeConfigSave}
      />
    );
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-7xl mx-auto">
        {/* Minimalistischer Header */}
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ScanLine className="w-6 h-6 text-primary" />
            <h1 className="text-xl font-semibold text-foreground">
              OCR Designer
            </h1>
          </div>
        </div>

        {/* Connection Status - kompakt */}
        {renderConnectionStatus()}

        {/* ClientSelectorCard AUSGEBLENDET - Auto-Select beim Connect */}
        {/* {renderClientSelector()} */}

        {/* Stream Controls - NUR Stop-Button wenn Stream aktiv */}
        {isStreamingActive && renderStreamControls()}

        {/* Desktop Automation Panel - Remote Steuerung */}
        {selectedClients.length > 0 && isConnected && (
          <div className="mt-4">
            <DesktopAutomationPanel
              desktopClientId={selectedClients[0]}
              monitorId="monitor_0"
              wsConnection={websocket}
              isConnected={isConnected}
              streamWidth={1920}
              streamHeight={1080}
            />
          </div>
        )}

        {/* Dual Canvas OCR Designer */}
        {renderDualCanvasOCRDesigner()}

        {/* Dual Monitor Workflows - MCP Integration */}
        {isConnected && selectedClients.length > 0 && (
          <div className="mt-6">
            <DualMonitorWorkflow
              primaryStreamUrl={
                selectedClients.length > 0
                  ? latestScreenshots[`${selectedClients[0]}_monitor_0`] || latestScreenshots[selectedClients[0]]
                  : null
              }
              secondaryStreamUrl={
                selectedClients.length > 0
                  ? latestScreenshots[`${selectedClients[0]}_monitor_1`] ||
                    (selectedClients.length > 1
                      ? latestScreenshots[`${selectedClients[1]}_monitor_0`] || latestScreenshots[selectedClients[1]]
                      : null)
                  : null
              }
              isConnected={isConnected}
              websocket={websocket}
              onWorkflowExecute={(monitorId, steps) => {
                console.log(`[Workflow] Executing workflow on monitor ${monitorId}:`, steps);
              }}
              onWorkflowStop={(monitorId) => {
                console.log(`[Workflow] Stopped workflow on monitor ${monitorId}`);
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default memo(MultiDesktopStreams);