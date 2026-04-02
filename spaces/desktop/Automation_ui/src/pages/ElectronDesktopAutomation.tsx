/**
 * Electron Desktop Automation Page
 *
 * Main page for the Electron app combining:
 * - Live desktop stream with detection overlay
 * - Chat panel for intent processing via MCP tools
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Monitor,
  Settings,
  Play,
  Pause,
  RefreshCw,
  Wifi,
  WifiOff,
  Zap
} from 'lucide-react';
// IntentChatPanel replaced by vapi_web.html iframe (Voice Control)
import type { StreamEvent } from '@/components/electron/IntentChatPanel';
import { LiveStreamWithDetection, DetectionBox, FrameData } from '@/components/electron/LiveStreamWithDetection';
import {
  isElectron,
  onScreenFrame,
  startScreenCapture,
  stopScreenCapture,
  ScreenCaptureFrame
} from '@/services/electronBridge';
import { createMultiDesktopClientUrl, sendWebSocketMessage } from '@/config/websocketConfig';

// ============================================
// Types
// ============================================

interface MCPResult {
  success: boolean;
  text?: string;
  location?: { x: number; y: number };
  confidence?: number;
  error?: string;
}

// ============================================
// MCP Tool Hooks
// ============================================

const useMCPTools = (websocket: WebSocket | null) => {
  const [pendingRequests] = useState(new Map<string, (result: MCPResult) => void>());

  // Handle MCP responses
  useEffect(() => {
    if (!websocket) {return;}

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);

        // Handle MCP tool responses
        if (data.type === 'mcp_result' && data.requestId) {
          const resolver = pendingRequests.get(data.requestId);
          if (resolver) {
            resolver(data.result);
            pendingRequests.delete(data.requestId);
          }
        }
      } catch {
        // Ignore non-JSON messages
      }
    };

    websocket.addEventListener('message', handleMessage);
    return () => websocket.removeEventListener('message', handleMessage);
  }, [websocket, pendingRequests]);

  // Generic MCP tool call
  const callMCPTool = useCallback(async (
    tool: string,
    params: Record<string, unknown>
  ): Promise<MCPResult> => {
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
      return { success: false, error: 'WebSocket not connected' };
    }

    const requestId = `mcp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    return new Promise((resolve) => {
      // Set timeout
      const timeout = setTimeout(() => {
        pendingRequests.delete(requestId);
        resolve({ success: false, error: 'Request timeout' });
      }, 30000);

      pendingRequests.set(requestId, (result) => {
        clearTimeout(timeout);
        resolve(result);
      });

      sendWebSocketMessage(websocket, {
        type: 'mcp_call',
        requestId,
        tool,
        params
      });
    });
  }, [websocket, pendingRequests]);

  // Read screen
  const readScreen = useCallback(async (monitorId = 0) => {
    return callMCPTool('handoff_read_screen', { monitor_id: monitorId });
  }, [callMCPTool]);

  // Validate element
  const validateElement = useCallback(async (target: string) => {
    return callMCPTool('handoff_validate', { target });
  }, [callMCPTool]);

  // Execute action
  const executeAction = useCallback(async (
    actionType: string,
    params: Record<string, unknown>
  ) => {
    return callMCPTool('handoff_action', { action_type: actionType, params });
  }, [callMCPTool]);

  return { callMCPTool, readScreen, validateElement, executeAction };
};

// ============================================
// Main Component
// ============================================

export const ElectronDesktopAutomation: React.FC = () => {
  // Connection state
  const [isConnected, setIsConnected] = useState(false);
  const [websocket, setWebsocket] = useState<WebSocket | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);

  // Stream state - support dual monitors
  const [frames, setFrames] = useState<{ [monitorId: number]: FrameData }>({});
  const [activeMonitor, setActiveMonitor] = useState<number>(0);
  const [isCapturing, setIsCapturing] = useState(false);
  const [fps, setFps] = useState<{ [monitorId: number]: number }>({});
  const lastFrameTime = useRef<{ [monitorId: number]: number }>({});
  const frameCount = useRef<{ [monitorId: number]: number }>({});

  // Detection state
  const [detectionBoxes, setDetectionBoxes] = useState<DetectionBox[]>([]);
  const [clickTarget, setClickTarget] = useState<{ x: number; y: number } | null>(null);
  const [lastOCRText, setLastOCRText] = useState('');

  // MCP tools
  const { readScreen, validateElement, executeAction } = useMCPTools(websocket);

  // Check if running in Electron
  const inElectron = isElectron();

  // ============================================
  // WebSocket Connection
  // ============================================

  // Track connected desktop client with ref to avoid useEffect re-trigger
  const connectedDesktopClientRef = useRef<string | null>(null);

  useEffect(() => {
    const { url, handshakeMessage } = createMultiDesktopClientUrl('electron_automation');

    const ws = new WebSocket(url);
    websocketRef.current = ws;

    ws.onopen = () => {
      sendWebSocketMessage(ws, handshakeMessage);
      setIsConnected(true);

      // Auto-request desktop clients list after handshake
      setTimeout(() => {
        sendWebSocketMessage(ws, { type: 'get_desktop_clients' });
      }, 500);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle desktop clients list - auto-start stream with first available client
        if (data.type === 'desktop_clients_list' || data.type === 'desktop_clients') {
          const clients = data.clients || data.desktop_clients || [];
          if (clients.length > 0 && !connectedDesktopClientRef.current) {
            const firstClient = clients[0];
            const clientId = firstClient.client_id || firstClient.id;
            const monitorCount = firstClient.monitor_count || firstClient.monitors?.length || 2;

            connectedDesktopClientRef.current = clientId;
            setIsCapturing(true);

            // Send start_stream for all monitors (dual-monitor support)
            for (let monitorId = 0; monitorId < monitorCount; monitorId++) {
              sendWebSocketMessage(ws, {
                type: 'start_stream',
                desktop_client_id: clientId,
                monitor_id: monitorId
              });
            }
          }
        }

        // Handle frame data - store per monitor
        if (data.type === 'frame_data') {
          // Parse monitor ID - handle both 'monitor_0' string format and numeric 0 format
          const rawMonitorId = data.monitor_id ?? data.monitorId ?? 0;
          const monitorId = typeof rawMonitorId === 'string'
            ? parseInt(rawMonitorId.replace(/\D/g, ''), 10) || 0
            : rawMonitorId;

          const frameData: FrameData = {
            data: data.frame_data || data.data || data.frameData,
            timestamp: data.timestamp || Date.now(),
            width: data.width || 1920,
            height: data.height || 1080,
            monitorId: monitorId
          };

          setFrames(prev => ({
            ...prev,
            [monitorId]: frameData
          }));

          // Calculate FPS per monitor
          if (!frameCount.current[monitorId]) {frameCount.current[monitorId] = 0;}
          if (!lastFrameTime.current[monitorId]) {lastFrameTime.current[monitorId] = Date.now();}

          frameCount.current[monitorId]++;
          const now = Date.now();
          if (now - lastFrameTime.current[monitorId] >= 1000) {
            setFps(prev => ({
              ...prev,
              [monitorId]: frameCount.current[monitorId]
            }));
            frameCount.current[monitorId] = 0;
            lastFrameTime.current[monitorId] = now;
          }
        }

        // Handle detection results
        if (data.type === 'detection_result') {
          const boxes: DetectionBox[] = (data.boxes || []).map((box: {
            label: string;
            x: number;
            y: number;
            width: number;
            height: number;
            confidence: number;
          }, idx: number) => ({
            id: `box_${idx}`,
            label: box.label,
            x: box.x,
            y: box.y,
            width: box.width || 100,
            height: box.height || 30,
            confidence: box.confidence || 0.8,
            type: 'element' as const
          }));
          setDetectionBoxes(boxes);
        }

        // Handle OCR results
        if (data.type === 'ocr_result') {
          setLastOCRText(data.text || '');
        }
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      connectedDesktopClientRef.current = null;
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    setWebsocket(ws);

    return () => {
      ws.close();
    };
  }, []); // Empty dependency array - only run once on mount

  // ============================================
  // Electron Screen Capture
  // ============================================

  useEffect(() => {
    if (!inElectron) {return;}

    const cleanup = onScreenFrame((electronFrame: ScreenCaptureFrame) => {
      // Parse monitor ID - handle both 'monitor_0' string format and numeric 0 format
      const rawMonitorId = electronFrame.displayIndex ?? 0;
      const monitorId = typeof rawMonitorId === 'string'
        ? parseInt(rawMonitorId.replace(/\D/g, ''), 10) || 0
        : rawMonitorId;
      const frameData: FrameData = {
        data: electronFrame.data,
        timestamp: electronFrame.timestamp,
        width: electronFrame.width,
        height: electronFrame.height,
        monitorId: monitorId
      };

      setFrames(prev => ({
        ...prev,
        [monitorId]: frameData
      }));

      // Calculate FPS per monitor
      if (!frameCount.current[monitorId]) {frameCount.current[monitorId] = 0;}
      if (!lastFrameTime.current[monitorId]) {lastFrameTime.current[monitorId] = Date.now();}

      frameCount.current[monitorId]++;
      const now = Date.now();
      if (now - lastFrameTime.current[monitorId] >= 1000) {
        setFps(prev => ({
          ...prev,
          [monitorId]: frameCount.current[monitorId]
        }));
        frameCount.current[monitorId] = 0;
        lastFrameTime.current[monitorId] = now;
      }
    });

    return cleanup;
  }, [inElectron]);

  // ============================================
  // Control Handlers
  // ============================================

  const handleStartCapture = useCallback(async () => {
    if (inElectron) {
      const success = await startScreenCapture({ fps: 15, quality: 80 });
      setIsCapturing(success);
    } else {
      // Check if desktop client process is running, start if needed
      const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8007';
      try {
        const statusRes = await fetch(`${backendUrl}/api/client/status`);
        const status = await statusRes.json();

        if (!status.is_running) {
          // Start desktop client process via backend
          await fetch(`${backendUrl}/api/client/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_restart: true })
          });
          // Wait for client to connect to WebSocket
          await new Promise(resolve => setTimeout(resolve, 3000));
          // Re-request desktop clients list to trigger auto-subscription
          if (websocket) {
            sendWebSocketMessage(websocket, { type: 'get_desktop_clients' });
          }
        } else if (websocket) {
          // Client already running, just send start_capture
          sendWebSocketMessage(websocket, { type: 'start_capture' });
        }
        setIsCapturing(true);
      } catch (err) {
        console.error('Failed to start desktop client:', err);
        // Fallback: try sending start_capture anyway
        if (websocket) {
          sendWebSocketMessage(websocket, { type: 'start_capture' });
          setIsCapturing(true);
        }
      }
    }
  }, [inElectron, websocket]);

  const handleStopCapture = useCallback(async () => {
    if (inElectron) {
      await stopScreenCapture();
      setIsCapturing(false);
    } else if (websocket) {
      sendWebSocketMessage(websocket, { type: 'stop_capture' });
      setIsCapturing(false);
    }
  }, [inElectron, websocket]);

  const handleRefresh = useCallback(async () => {
    // Trigger a new screen read
    const result = await readScreen(0);
    if (result.success && result.text) {
      setLastOCRText(result.text);
    }
  }, [readScreen]);

  // ============================================
  // Intent Processing Handlers
  // ============================================

  const handleReadScreen = useCallback(async () => {
    const result = await readScreen(0);
    if (result.success) {
      return {
        text: result.text || '',
        elements: [] // TODO: Parse detected elements from result
      };
    }
    return null;
  }, [readScreen]);

  const handleValidate = useCallback(async (target: string) => {
    const result = await validateElement(target);
    if (result.success && result.location) {
      const loc = result.location;
      // Set click target for visualization
      setClickTarget(loc);

      // Add detection box
      setDetectionBoxes(prev => [
        ...prev.filter(b => b.type !== 'click_target'),
        {
          id: `target_${Date.now()}`,
          label: target,
          x: loc.x - 50,
          y: loc.y - 15,
          width: 100,
          height: 30,
          confidence: result.confidence || 0.8,
          type: 'click_target'
        }
      ]);

      return {
        found: true,
        x: loc.x,
        y: loc.y,
        confidence: result.confidence
      };
    }
    return { found: false };
  }, [validateElement]);

  const handleAction = useCallback(async (action: string, params: Record<string, unknown>) => {
    const result = await executeAction(action, params);
    return result;
  }, [executeAction]);

  // LLM-powered intent processing via Claude Opus 4.6
  const handleIntent = useCallback(async (text: string) => {
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8007';
    try {
      const response = await fetch(`${backendUrl}/api/llm/intent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      if (!response.ok) {
        const errText = await response.text();
        return { success: false, action: 'error', error: `API ${response.status}: ${errText.substring(0, 200)}` };
      }
      const data = await response.json();
      return {
        success: data.success,
        action: data.steps?.length ? data.steps.map((s: { tool: string }) => s.tool).join(' → ') : text,
        ocrText: data.summary || ''
      };
    } catch (err) {
      return { success: false, action: 'error', error: String(err) };
    }
  }, []);

  // Persistent conversation ID for intervention system (approve/deny)
  const conversationIdRef = useRef(`conv_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`);

  // LLM-powered intent processing with SSE streaming
  const handleIntentStream = useCallback(async (
    text: string,
    onEvent: (event: StreamEvent) => void
  ): Promise<void> => {
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8007';
    try {
      const response = await fetch(`${backendUrl}/api/llm/intent/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, conversation_id: conversationIdRef.current })
      });

      if (!response.ok) {
        const errText = await response.text();
        onEvent({ type: 'error', message: `API ${response.status}: ${errText.substring(0, 200)}` });
        onEvent({ type: 'done', success: false, total_steps: 0, iterations: 0, duration_ms: 0 });
        return;
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        onEvent({ type: 'error', message: 'No response body reader' });
        onEvent({ type: 'done', success: false, total_steps: 0, iterations: 0, duration_ms: 0 });
        return;
      }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: StreamEvent = JSON.parse(line.substring(6));
              onEvent(event);
            } catch {
              // Ignore parse errors
            }
          }
        }
      }

      // Process remaining buffer
      if (buffer.startsWith('data: ')) {
        try {
          const event: StreamEvent = JSON.parse(buffer.substring(6));
          onEvent(event);
        } catch {
          // Ignore
        }
      }
    } catch (err) {
      onEvent({ type: 'error', message: String(err) });
      onEvent({ type: 'done', success: false, total_steps: 0, iterations: 0, duration_ms: 0 });
    }
  }, []);

  const handleClickPosition = useCallback((x: number, y: number) => {
    setClickTarget({ x, y });
  }, []);

  // Listen for action_visual events from voice iframe (PostMessage)
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'action_visual') {
        setClickTarget({ x: event.data.x, y: event.data.y });
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  // ============================================
  // Render
  // ============================================

  return (
    <div className="h-screen bg-gray-950 text-gray-100 flex flex-col">
      {/* Header */}
      <header className="h-12 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <Zap className="w-5 h-5 text-blue-500" />
          <span className="font-semibold">Desktop Automation</span>
          <Badge variant={inElectron ? 'default' : 'secondary'} className="text-xs">
            {inElectron ? 'Electron' : 'Web'}
          </Badge>
        </div>

        <div className="flex items-center gap-3">
          {/* Connection Status */}
          <Badge variant={isConnected ? 'default' : 'destructive'} className="flex items-center gap-1">
            {isConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {isConnected ? 'Connected' : 'Disconnected'}
          </Badge>

          {/* Capture Controls */}
          {isCapturing ? (
            <Button variant="destructive" size="sm" onClick={handleStopCapture}>
              <Pause className="w-4 h-4 mr-1" />
              Stop
            </Button>
          ) : (
            <Button variant="default" size="sm" onClick={handleStartCapture}>
              <Play className="w-4 h-4 mr-1" />
              Start
            </Button>
          )}

          <Button variant="ghost" size="sm" onClick={handleRefresh}>
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Live Streams (Dual Monitor) */}
        <div className="flex-1 p-2 min-w-0 flex flex-col">
          {/* Monitor Tabs */}
          <div className="flex gap-2 mb-2 shrink-0">
            {Object.keys(frames).length > 0 ? (
              Object.keys(frames).map((monitorIdStr) => {
                const monitorId = parseInt(monitorIdStr);
                return (
                  <Button
                    key={monitorId}
                    variant={activeMonitor === monitorId ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setActiveMonitor(monitorId)}
                    className="flex items-center gap-1"
                  >
                    <Monitor className="w-3 h-3" />
                    Monitor {monitorId}
                    <Badge variant="secondary" className="text-xs ml-1">
                      {fps[monitorId] || 0} FPS
                    </Badge>
                  </Button>
                );
              })
            ) : (
              <Badge variant="outline" className="text-gray-400">
                Waiting for streams...
              </Badge>
            )}
          </div>

          {/* Dual Monitor Grid View */}
          <div className="flex-1 grid grid-cols-2 gap-2 min-h-0">
            {/* Monitor 0 */}
            <div
              className={`relative rounded-lg overflow-hidden cursor-pointer ${activeMonitor === 0 ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-700'}`}
              onClick={() => setActiveMonitor(0)}
            >
              <div className="absolute top-2 left-2 z-10 flex gap-1">
                <Badge variant="secondary" className="text-xs bg-black/60">
                  Monitor 0
                </Badge>
                <Badge variant="outline" className="text-xs bg-black/60">
                  {fps[0] || 0} FPS
                </Badge>
              </div>
              <LiveStreamWithDetection
                frame={frames[0] || null}
                detectionBoxes={activeMonitor === 0 ? detectionBoxes : []}
                clickTarget={activeMonitor === 0 ? clickTarget : null}
                onClickPosition={activeMonitor === 0 ? handleClickPosition : undefined}
                className="h-full"
              />
            </div>

            {/* Monitor 1 */}
            <div
              className={`relative rounded-lg overflow-hidden cursor-pointer ${activeMonitor === 1 ? 'ring-2 ring-blue-500' : 'ring-1 ring-gray-700'}`}
              onClick={() => setActiveMonitor(1)}
            >
              <div className="absolute top-2 left-2 z-10 flex gap-1">
                <Badge variant="secondary" className="text-xs bg-black/60">
                  Monitor 1
                </Badge>
                <Badge variant="outline" className="text-xs bg-black/60">
                  {fps[1] || 0} FPS
                </Badge>
              </div>
              <LiveStreamWithDetection
                frame={frames[1] || null}
                detectionBoxes={activeMonitor === 1 ? detectionBoxes : []}
                clickTarget={activeMonitor === 1 ? clickTarget : null}
                onClickPosition={activeMonitor === 1 ? handleClickPosition : undefined}
                className="h-full"
              />
            </div>
          </div>
        </div>

        {/* Right: Chat Panel */}
        <div className="w-[400px] p-2 border-l border-gray-800 shrink-0">
          <Tabs defaultValue="chat" className="h-full flex flex-col">
            <TabsList className="bg-gray-800 shrink-0">
              <TabsTrigger value="chat" className="flex items-center gap-1">
                <Zap className="w-4 h-4" />
                Voice
              </TabsTrigger>
              <TabsTrigger value="info" className="flex items-center gap-1">
                <Monitor className="w-4 h-4" />
                Info
              </TabsTrigger>
              <TabsTrigger value="settings" className="flex items-center gap-1">
                <Settings className="w-4 h-4" />
                Settings
              </TabsTrigger>
            </TabsList>

            <TabsContent value="chat" className="flex-1 mt-2 overflow-hidden">
              <iframe
                src="http://localhost:8765"
                className="w-full h-full border-0 rounded-lg"
                title="Voice Control"
                allow="microphone"
              />
            </TabsContent>

            <TabsContent value="info" className="flex-1 mt-2">
              <Card className="h-full bg-gray-900 border-gray-800">
                <CardHeader className="py-3 px-4 border-b border-gray-800">
                  <CardTitle className="text-sm font-medium text-gray-200">
                    Detection Info
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 space-y-4">
                  {/* Frame Info - Dual Monitor */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-400 mb-2">
                      Streams ({Object.keys(frames).length} monitors)
                    </h4>
                    {Object.keys(frames).length > 0 ? (
                      <div className="space-y-2">
                        {Object.entries(frames).map(([monitorId, frame]) => (
                          <div key={monitorId} className={`text-sm text-gray-300 p-2 rounded ${activeMonitor === parseInt(monitorId) ? 'bg-blue-900/30 border border-blue-700' : 'bg-gray-800'}`}>
                            <p className="font-medium">Monitor {monitorId}</p>
                            <p className="text-xs text-gray-400">
                              {frame.width} x {frame.height} @ {fps[parseInt(monitorId)] || 0} FPS
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500">No streams</p>
                    )}
                  </div>

                  {/* Detection Boxes */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-400 mb-2">
                      Detected Elements ({detectionBoxes.length})
                    </h4>
                    <div className="space-y-1 max-h-40 overflow-auto">
                      {detectionBoxes.map((box) => (
                        <div
                          key={box.id}
                          className="text-xs bg-gray-800 px-2 py-1 rounded flex justify-between"
                        >
                          <span>{box.label}</span>
                          <span className="text-gray-500">
                            ({box.x}, {box.y})
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Click Target */}
                  {clickTarget && (
                    <div>
                      <h4 className="text-xs font-medium text-gray-400 mb-2">Click Target</h4>
                      <p className="text-sm text-green-400">
                        ({clickTarget.x}, {clickTarget.y})
                      </p>
                    </div>
                  )}

                  {/* Last OCR */}
                  {lastOCRText && (
                    <div>
                      <h4 className="text-xs font-medium text-gray-400 mb-2">Last OCR</h4>
                      <p className="text-xs text-gray-300 max-h-20 overflow-auto whitespace-pre-wrap bg-gray-800 p-2 rounded">
                        {lastOCRText.substring(0, 500)}
                        {lastOCRText.length > 500 && '...'}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="settings" className="flex-1 mt-2">
              <Card className="h-full bg-gray-900 border-gray-800">
                <CardHeader className="py-3 px-4 border-b border-gray-800">
                  <CardTitle className="text-sm font-medium text-gray-200">
                    Settings
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 space-y-4">
                  <div className="text-sm text-gray-400">
                    <p>Connection: {isConnected ? 'Active' : 'Inactive'}</p>
                    <p>Mode: {inElectron ? 'Electron Native' : 'WebSocket'}</p>
                    <p>Capture: {isCapturing ? 'Running' : 'Stopped'}</p>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
};

export default ElectronDesktopAutomation;
