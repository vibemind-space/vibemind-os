/**
 * Live Desktop Stream Component
 * Enhanced streaming component with robust WebSocket reconnection
 * Uses useWebSocketReconnect hook for stable connections
 * 
 * UPDATED: Now uses centralized WebSocket reconnection logic
 */

import React, { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  Play, 
  Pause, 
  Square, 
  Wifi, 
  WifiOff, 
  Monitor, 
  Maximize,
  RefreshCw,
  AlertTriangle,
  Clock,
  Activity,
  Zap,
  Target
} from 'lucide-react';
import { LiveDesktopConfig, LiveDesktopStatus, OCRRegion } from '@/types/liveDesktop';
import { 
  createWebClientUrl, 
  createHandshakeMessage,
  WEBSOCKET_CONFIG 
} from '@/config/websocketConfig';
import { useWebSocketReconnect, ConnectionStatus, CircuitBreakerState } from '@/hooks/useWebSocketReconnect';
import { useToast } from '@/hooks/use-toast';

interface LiveDesktopStreamProps {
  config: LiveDesktopConfig;
  onStatusChange: (status: LiveDesktopStatus) => void;
  onFrameReceived?: (frameData: any) => void;
  showControls?: boolean;
  enableFullscreen?: boolean;
  className?: string;
  /** OCR regions to display as overlay on the stream */
  ocrRegions?: OCRRegion[];
  /** Whether to show OCR zone overlay */
  showOCROverlay?: boolean;
  /** OCR results for confidence display */
  ocrResults?: Array<{ zone_id: string; confidence: number; text: string }>;
  /** Callback when user clicks on an OCR region */
  onRegionClick?: (region: OCRRegion) => void;
  /** Currently selected region ID */
  selectedRegionId?: string | null;
}

/**
 * Get status badge variant and text based on connection state
 */
const getStatusBadge = (
  status: ConnectionStatus, 
  circuitState: CircuitBreakerState
): { variant: 'default' | 'secondary' | 'destructive' | 'outline'; text: string; icon: React.ReactNode } => {
  if (circuitState === 'open') {
    return { variant: 'destructive', text: 'Circuit Open', icon: <AlertTriangle className="w-3 h-3 mr-1" /> };
  }
  if (circuitState === 'half_open') {
    return { variant: 'outline', text: 'Testing...', icon: <Activity className="w-3 h-3 mr-1" /> };
  }
  
  switch (status) {
    case 'connected':
      return { variant: 'default', text: 'Connected', icon: <Wifi className="w-3 h-3 mr-1" /> };
    case 'connecting':
      return { variant: 'secondary', text: 'Connecting...', icon: <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> };
    case 'reconnecting':
      return { variant: 'outline', text: 'Reconnecting...', icon: <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> };
    case 'error':
      return { variant: 'destructive', text: 'Error', icon: <AlertTriangle className="w-3 h-3 mr-1" /> };
    case 'circuit_open':
      return { variant: 'destructive', text: 'Circuit Open', icon: <AlertTriangle className="w-3 h-3 mr-1" /> };
    default:
      return { variant: 'secondary', text: 'Disconnected', icon: <WifiOff className="w-3 h-3 mr-1" /> };
  }
};

export const LiveDesktopStream: React.FC<LiveDesktopStreamProps> = ({
  config,
  onStatusChange,
  onFrameReceived,
  showControls = true,
  enableFullscreen = true,
  className = '',
  ocrRegions = [],
  showOCROverlay = true,
  ocrResults = [],
  onRegionClick,
  selectedRegionId = null
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null); // New overlay canvas for OCR zones
  const lastFrameRef = useRef<string | null>(null); // Cache last frame for graceful degradation
  const lastFrameInfoRef = useRef<{ width: number; height: number; monitorId?: string; sourceClientId?: string } | null>(null);
  
  const [internalStatus, setInternalStatus] = useState<LiveDesktopStatus>({
    connected: false,
    streaming: false,
    connectionName: null,
    latency: 0,
    fpsActual: 0,
    bytesReceived: 0,
    lastFrameTime: null
  });
  const [frameCount, setFrameCount] = useState(0);
  const [lastFrameTimestamp, setLastFrameTimestamp] = useState<number | null>(null);
  
  const { toast } = useToast();

  // Create WebSocket URL and handshake message
  const { url: wsUrl, clientId, handshakeMessage } = useMemo(() => {
    return createWebClientUrl(`live_desktop_${config.id}`);
  }, [config.id]);

  // Handle incoming WebSocket message
  const handleMessage = useCallback((event: MessageEvent, ws: WebSocket) => {
    try {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'handshake_ack':
          console.log('✅ Handshake acknowledged:', data);
          setInternalStatus(prev => ({
            ...prev,
            connected: true,
            connectionName: config.name
          }));
          break;

        case 'connection_established':
          console.log('✅ Connection established:', data);
          setInternalStatus(prev => ({
            ...prev,
            connected: true,
            connectionName: config.name
          }));
          break;

        case 'frame_data':
          if (data.frameData) {
            // Track last frame meta info for click mapping
            lastFrameInfoRef.current = {
              width: Number(data.width) || 0,
              height: Number(data.height) || 0,
              monitorId: data.monitorId || data.routingInfo?.monitorId,
              sourceClientId: data.routingInfo?.sourceClientId || data.metadata?.clientId || undefined,
            };

            // Cache frame for graceful degradation
            lastFrameRef.current = data.frameData;
            
            drawFrame(data.frameData);
            
            const now = Date.now();
            const fps = lastFrameTimestamp ? Math.round(1000 / (now - lastFrameTimestamp)) : 0;
            setLastFrameTimestamp(now);
            
            setInternalStatus(prev => ({
              ...prev,
              streaming: true,
              fpsActual: fps,
              bytesReceived: prev.bytesReceived + (event.data.length || 0),
              lastFrameTime: new Date().toISOString()
            }));
          }
          break;

        case 'desktop_status':
          console.log('📊 Desktop status:', data);
          setInternalStatus(prev => ({
            ...prev,
            streaming: data.isStreaming,
            latency: data.latency || prev.latency
          }));
          break;

        case 'desktop_disconnected':
          console.log('🔌 Desktop disconnected:', data.desktopClientId);
          setInternalStatus(prev => ({
            ...prev,
            streaming: false,
          }));
          toast({
            title: "Desktop Disconnected",
            description: "Desktop client has disconnected. Using cached frame.",
            variant: "destructive",
          });
          break;

        case 'error':
          console.error('❌ Server error:', data.error);
          toast({
            title: "Server Error",
            description: data.error,
            variant: "destructive",
          });
          break;
          
        case 'pong':
          // Handled by useWebSocketReconnect hook
          break;
          
        default:
          console.log('📨 Unknown message type:', data.type, data);
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }, [config.name, lastFrameTimestamp, toast]);

  // Handle WebSocket connection open
  const handleOpen = useCallback((ws: WebSocket) => {
    console.log('✅ WebSocket connected - LiveDesktopStream');
    
    // Subscribe to desktop streams after connection
    setTimeout(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'subscribe_desktop_stream',
          desktopClientId: null // Subscribe to all available streams
        }));
      }
    }, 500);
    
    toast({
      title: "Connected",
      description: `Connected to ${config.name}`,
    });
  }, [config.name, toast]);

  // Handle WebSocket close
  const handleClose = useCallback((event: CloseEvent) => {
    console.log('🔌 WebSocket closed - LiveDesktopStream:', event.code, event.reason);
    setInternalStatus(prev => ({
      ...prev,
      connected: false,
      streaming: false,
    }));
  }, []);

  // Handle reconnecting callback
  const handleReconnecting = useCallback((attempt: number, maxAttempts: number) => {
    toast({
      title: "Reconnecting...",
      description: `Attempt ${attempt} of ${maxAttempts}`,
      duration: 2000,
    });
  }, [toast]);

  // Handle circuit breaker state change
  const handleCircuitBreakerChange = useCallback((state: CircuitBreakerState) => {
    if (state === 'open') {
      toast({
        title: "Connection Issues",
        description: "Too many failures. Will retry automatically in 30 seconds.",
        variant: "destructive",
        duration: 5000,
      });
    } else if (state === 'closed') {
      toast({
        title: "Connection Restored",
        description: "Connection is now stable.",
        duration: 3000,
      });
    }
  }, [toast]);

  // Use the robust WebSocket reconnection hook
  const {
    websocket,
    status: wsStatus,
    reconnectAttempt,
    reconnect,
    disconnect,
    sendMessage,
    isConnected,
    lastError,
    circuitBreakerState,
    resetCircuitBreaker,
    nextReconnectIn,
    connectionUptime,
  } = useWebSocketReconnect({
    url: wsUrl,
    handshakeMessage,
    onOpen: handleOpen,
    onMessage: handleMessage,
    onClose: handleClose,
    onReconnecting: handleReconnecting,
    onCircuitBreakerChange: handleCircuitBreakerChange,
    autoReconnect: true,
    healthCheckUrl: `${window.location.protocol}//${window.location.hostname}:8007/api/health/health`,
  });

  // Update parent with status changes
  useEffect(() => {
    onStatusChange({
      ...internalStatus,
      connected: isConnected,
    });
  }, [internalStatus, isConnected, onStatusChange]);

  // Draw OCR zones overlay
  const drawOCROverlay = useCallback(() => {
    const overlayCanvas = overlayCanvasRef.current;
    const mainCanvas = canvasRef.current;
    if (!overlayCanvas || !mainCanvas || !showOCROverlay || ocrRegions.length === 0) return;

    const ctx = overlayCanvas.getContext('2d');
    if (!ctx) return;

    // Sync overlay canvas size with main canvas
    if (overlayCanvas.width !== mainCanvas.width || overlayCanvas.height !== mainCanvas.height) {
      overlayCanvas.width = mainCanvas.width;
      overlayCanvas.height = mainCanvas.height;
    }

    // Clear overlay
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    // Get frame dimensions for scaling
    const frameInfo = lastFrameInfoRef.current;
    const scaleX = frameInfo?.width ? overlayCanvas.width / frameInfo.width : 1;
    const scaleY = frameInfo?.height ? overlayCanvas.height / frameInfo.height : 1;

    // Draw each OCR region
    ocrRegions.forEach((region) => {
      const isSelected = selectedRegionId === region.id;
      const isActive = region.isActive;
      
      // Find OCR result for this region to get confidence
      const ocrResult = ocrResults.find(r => r.zone_id === region.id);
      const confidence = ocrResult?.confidence ?? 0;
      
      // Get confidence-based colors
      let strokeColor = '#6b7280'; // Gray
      let fillColor = 'rgba(107, 114, 128, 0.15)';
      let labelBg = 'rgba(107, 114, 128, 0.9)';
      
      if (isSelected) {
        strokeColor = '#8b5cf6'; // Purple
        fillColor = 'rgba(139, 92, 246, 0.2)';
        labelBg = 'rgba(139, 92, 246, 0.9)';
      } else if (confidence > 0) {
        if (confidence >= 0.9) {
          strokeColor = '#10b981'; // Green
          fillColor = 'rgba(16, 185, 129, 0.15)';
          labelBg = 'rgba(16, 185, 129, 0.9)';
        } else if (confidence >= 0.7) {
          strokeColor = '#f59e0b'; // Yellow/Orange
          fillColor = 'rgba(245, 158, 11, 0.15)';
          labelBg = 'rgba(245, 158, 11, 0.9)';
        } else {
          strokeColor = '#ef4444'; // Red
          fillColor = 'rgba(239, 68, 68, 0.15)';
          labelBg = 'rgba(239, 68, 68, 0.9)';
        }
      } else if (isActive) {
        strokeColor = '#3b82f6'; // Blue
        fillColor = 'rgba(59, 130, 246, 0.15)';
        labelBg = 'rgba(59, 130, 246, 0.9)';
      }

      // Scale coordinates to canvas size
      const x = region.x * scaleX;
      const y = region.y * scaleY;
      const width = region.width * scaleX;
      const height = region.height * scaleY;

      // Set styles
      ctx.strokeStyle = strokeColor;
      ctx.fillStyle = fillColor;
      ctx.lineWidth = isSelected ? 3 : 2;

      // Draw region rectangle
      ctx.fillRect(x, y, width, height);
      ctx.strokeRect(x, y, width, height);

      // Draw label background
      const labelText = region.label;
      ctx.font = '500 11px Inter, system-ui, sans-serif';
      const textMetrics = ctx.measureText(labelText);
      const labelHeight = 18;
      const labelWidth = textMetrics.width + 12;
      const labelY = y > 22 ? y - labelHeight - 3 : y + height + 3;
      
      ctx.fillStyle = labelBg;
      ctx.fillRect(x, labelY, labelWidth, labelHeight);

      // Draw label text
      ctx.fillStyle = '#ffffff';
      ctx.fillText(labelText, x + 6, labelY + 13);

      // Draw confidence badge if OCR result exists
      if (ocrResult && confidence > 0) {
        const confidenceText = `${(confidence * 100).toFixed(0)}%`;
        ctx.font = 'bold 10px Inter, system-ui, sans-serif';
        const badgeWidth = ctx.measureText(confidenceText).width + 10;
        const badgeX = x + width - badgeWidth - 3;
        const badgeY = y + 3;
        
        // Badge background
        ctx.fillStyle = confidence >= 0.9 ? 'rgba(16, 185, 129, 0.95)' : 
                        confidence >= 0.7 ? 'rgba(245, 158, 11, 0.95)' : 
                        'rgba(239, 68, 68, 0.95)';
        ctx.fillRect(badgeX, badgeY, badgeWidth, 16);
        
        // Badge text
        ctx.fillStyle = '#ffffff';
        ctx.fillText(confidenceText, badgeX + 5, badgeY + 12);
      }

      // Draw active indicator dot
      if (isActive && !ocrResult) {
        ctx.fillStyle = '#10b981';
        ctx.beginPath();
        ctx.arc(x + width - 6, y + 6, 4, 0, 2 * Math.PI);
        ctx.fill();
      }
    });
  }, [ocrRegions, ocrResults, showOCROverlay, selectedRegionId]);

  // Redraw overlay when regions or results change
  useEffect(() => {
    drawOCROverlay();
  }, [drawOCROverlay, internalStatus.streaming]);

  // Draw frame to canvas
  const drawFrame = useCallback((imageData: string) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Clear canvas and draw frame
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      
      setFrameCount(prev => prev + 1);
      
      // Redraw OCR overlay after frame update
      drawOCROverlay();
      
      // Notify parent of new frame
      onFrameReceived?.({ 
        imageData, 
        timestamp: Date.now(), 
        frameNumber: frameCount 
      });
    };
    img.src = imageData.startsWith('data:') ? imageData : `data:image/jpeg;base64,${imageData}`;
  }, [frameCount, onFrameReceived, drawOCROverlay]);

  // Handle click on overlay canvas to detect region clicks
  const handleOverlayClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onRegionClick || ocrRegions.length === 0) return;

    const canvas = overlayCanvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Scale click coordinates
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = clickX * scaleX;
    const y = clickY * scaleY;

    // Get frame dimensions for region scaling
    const frameInfo = lastFrameInfoRef.current;
    const regionScaleX = frameInfo?.width ? canvas.width / frameInfo.width : 1;
    const regionScaleY = frameInfo?.height ? canvas.height / frameInfo.height : 1;

    // Find clicked region
    const clickedRegion = ocrRegions.find(region => {
      const rx = region.x * regionScaleX;
      const ry = region.y * regionScaleY;
      const rw = region.width * regionScaleX;
      const rh = region.height * regionScaleY;
      return x >= rx && x <= rx + rw && y >= ry && y <= ry + rh;
    });

    if (clickedRegion) {
      onRegionClick(clickedRegion);
    }
  }, [ocrRegions, onRegionClick]);

  // Draw cached frame (graceful degradation)
  const drawCachedFrame = useCallback(() => {
    if (lastFrameRef.current) {
      drawFrame(lastFrameRef.current);
    }
  }, [drawFrame]);

  // Redraw cached frame when circuit breaker opens
  useEffect(() => {
    if (circuitBreakerState === 'open' && lastFrameRef.current) {
      // Draw cached frame with overlay
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx) {
          drawCachedFrame();
          // Add "Cached" overlay
          ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
          ctx.fillRect(0, canvas.height - 30, canvas.width, 30);
          ctx.fillStyle = '#ff9800';
          ctx.font = '14px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText('⚠️ Showing cached frame - Reconnecting...', canvas.width / 2, canvas.height - 10);
        }
      }
    }
  }, [circuitBreakerState, drawCachedFrame]);

  // Map canvas click to remote desktop coordinates and send via WS
  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    try {
      const canvas = canvasRef.current;
      const frameInfo = lastFrameInfoRef.current;
      if (!canvas || !isConnected || !frameInfo) {
        console.warn('Click ignored: missing canvas/connection/frameInfo');
        return;
      }

      const rect = canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      // Use canvas width/height as the actual drawing buffer dims
      const canvasW = canvas.width;
      const canvasH = canvas.height;
      if (!canvasW || !canvasH || !frameInfo.width || !frameInfo.height) {
        console.warn('Click ignored: invalid dimensions', { canvasW, canvasH, frameInfo });
        return;
      }

      // Normalize from canvas space to original frame pixel space
      const normX = Math.max(0, Math.min(1, clickX / canvasW));
      const normY = Math.max(0, Math.min(1, clickY / canvasH));
      const remoteX = Math.round(normX * frameInfo.width);
      const remoteY = Math.round(normY * frameInfo.height);

      const targetClientId = frameInfo.sourceClientId;
      if (!targetClientId) {
        console.warn('No sourceClientId on last frame; cannot route click');
        return;
      }

      const payload = {
        type: 'desktop_click',
        clientId: targetClientId,
        monitorId: frameInfo.monitorId || 'monitor_0',
        x: remoteX,
        y: remoteY,
        button: 'left',
        double: false,
        timestamp: new Date().toISOString(),
      };

      console.log('📤 Sending desktop_click', payload);
      sendMessage(payload);

      // Optional UX feedback
      toast({ title: 'Click sent', description: `(${remoteX}, ${remoteY}) → ${payload.monitorId}`, duration: 1500 });
    } catch (err) {
      console.error('Error handling canvas click:', err);
    }
  }, [isConnected, sendMessage, toast]);

  // Enable fullscreen
  const enterFullscreen = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (canvas.requestFullscreen) {
      canvas.requestFullscreen();
    }
  }, []);

  // Get status badge info
  const statusBadge = getStatusBadge(wsStatus, circuitBreakerState);

  // Format connection uptime
  const formatUptime = (ms: number): string => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  };

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Stream Display */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Monitor className="w-5 h-5" />
              {config.name}
            </CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant={statusBadge.variant}>
                {statusBadge.icon}
                {statusBadge.text}
              </Badge>
              {internalStatus.streaming && (
                <Badge variant="outline">
                  <Zap className="w-3 h-3 mr-1" />
                  {internalStatus.fpsActual} FPS
                </Badge>
              )}
              {isConnected && connectionUptime > 0 && (
                <Badge variant="outline" className="text-xs">
                  <Clock className="w-3 h-3 mr-1" />
                  {formatUptime(connectionUptime)}
                </Badge>
              )}
              {/* OCR Zones indicator */}
              {ocrRegions.length > 0 && showOCROverlay && (
                <Badge variant="outline" className="text-xs">
                  <Target className="w-3 h-3 mr-1" />
                  {ocrRegions.length} Zone{ocrRegions.length !== 1 ? 'n' : ''}
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="relative">
            {/* Main video canvas */}
            <canvas
              ref={canvasRef}
              width={800}
              height={600}
              className="w-full bg-muted border rounded-lg"
              style={{ aspectRatio: '4/3' }}
            />
            
            {/* OCR Zones Overlay Canvas */}
            {showOCROverlay && ocrRegions.length > 0 && (
              <canvas
                ref={overlayCanvasRef}
                width={800}
                height={600}
                className="absolute inset-0 w-full h-full rounded-lg cursor-pointer"
                style={{ aspectRatio: '4/3' }}
                onClick={handleOverlayClick}
              />
            )}
            
            {/* Click handler for main canvas when no overlay */}
            {(!showOCROverlay || ocrRegions.length === 0) && (
              <div 
                className="absolute inset-0 cursor-pointer" 
                onClick={handleCanvasClick}
              />
            )}
            
            {/* Overlay for non-streaming states */}
            {!internalStatus.streaming && (
              <div className="absolute inset-0 flex items-center justify-center bg-muted/80 rounded-lg">
                <div className="text-center space-y-2">
                  <Monitor className="w-12 h-12 mx-auto text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    {wsStatus === 'connecting' ? 'Connecting...' :
                     wsStatus === 'reconnecting' ? `Reconnecting (${reconnectAttempt}/${WEBSOCKET_CONFIG.RECONNECT.MAX_ATTEMPTS})...` :
                     circuitBreakerState === 'open' ? 'Connection issues - will retry automatically' :
                     isConnected ? 'Stream stopped' : 'Not connected'}
                  </p>
                  
                  {/* Reconnect countdown */}
                  {nextReconnectIn !== null && nextReconnectIn > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Next attempt in {Math.ceil(nextReconnectIn / 1000)}s
                      </p>
                      <Progress 
                        value={100 - (nextReconnectIn / WEBSOCKET_CONFIG.RECONNECT.MAX_DELAY) * 100} 
                        className="w-48 mx-auto h-1"
                      />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Error indicator */}
            {lastError && (
              <div className="absolute bottom-2 left-2 right-2">
                <div className="bg-destructive/90 text-destructive-foreground text-xs px-2 py-1 rounded">
                  {lastError}
                </div>
              </div>
            )}
          </div>

          {/* Stream Info */}
          {internalStatus.streaming && (
            <div className="mt-4 grid grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Latency:</span>
                <span className="ml-1 font-mono">{internalStatus.latency}ms</span>
              </div>
              <div>
                <span className="text-muted-foreground">Frames:</span>
                <span className="ml-1 font-mono">{frameCount}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Data:</span>
                <span className="ml-1 font-mono">
                  {Math.round(internalStatus.bytesReceived / 1024)}KB
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Last Frame:</span>
                <span className="ml-1 font-mono">
                  {internalStatus.lastFrameTime ? new Date(internalStatus.lastFrameTime).toLocaleTimeString() : 'None'}
                </span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Controls */}
      {showControls && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {wsStatus === 'disconnected' || wsStatus === 'error' || circuitBreakerState === 'open' ? (
                  <Button onClick={reconnect} disabled={wsStatus === 'connecting'}>
                    <RefreshCw className={`w-4 h-4 mr-2 ${wsStatus === 'connecting' ? 'animate-spin' : ''}`} />
                    {circuitBreakerState === 'open' ? 'Force Reconnect' : 'Reconnect'}
                  </Button>
                ) : (
                  <>
                    <Button 
                      onClick={() => {
                        if (websocket?.readyState === WebSocket.OPEN) {
                          sendMessage({
                            type: internalStatus.streaming ? 'stop_stream' : 'start_stream',
                            config: {
                              fps: config.streaming.fps,
                              quality: config.streaming.quality,
                              scale: config.streaming.scale
                            }
                          });
                        }
                      }} 
                      disabled={!isConnected}
                    >
                      {internalStatus.streaming ? (
                        <><Pause className="w-4 h-4 mr-2" /> Pause</>
                      ) : (
                        <><Play className="w-4 h-4 mr-2" /> Stream</>
                      )}
                    </Button>
                    <Button variant="outline" onClick={disconnect}>
                      <Square className="w-4 h-4 mr-2" />
                      Disconnect
                    </Button>
                  </>
                )}
                
                {/* Circuit breaker reset button */}
                {circuitBreakerState !== 'closed' && (
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={resetCircuitBreaker}
                    className="ml-2"
                  >
                    <RefreshCw className="w-4 h-4 mr-1" />
                    Reset Circuit
                  </Button>
                )}
              </div>

              <div className="flex items-center gap-2">
                {/* Connection health indicator */}
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Activity className="w-3 h-3" />
                  <span>Reconnects: {reconnectAttempt}</span>
                </div>

                {enableFullscreen && internalStatus.streaming && (
                  <Button variant="outline" onClick={enterFullscreen}>
                    <Maximize className="w-4 h-4 mr-2" />
                    Fullscreen
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};