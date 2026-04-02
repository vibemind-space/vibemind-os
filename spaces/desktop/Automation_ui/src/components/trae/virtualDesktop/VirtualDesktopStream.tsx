/**
 * Virtual Desktop Stream Component
 * Real-time streaming view of virtual desktop with interaction capabilities
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { 
  Play, 
  Pause, 
  Square, 
  Volume2, 
  VolumeX,
  Maximize,
  Minimize,
  RotateCcw,
  Settings,
  Monitor,
  Wifi,
  WifiOff,
  MousePointer,
  Keyboard,
  Camera,
  Download
} from 'lucide-react';
import { VirtualDesktop, VirtualDesktopStreamConfig } from '@/types/virtualDesktop';
import { getVirtualDesktopManager } from '@/services/virtualDesktopManager';
import { useToast } from '@/hooks/use-toast';

interface VirtualDesktopStreamProps {
  /** Virtual desktop to stream */
  desktop: VirtualDesktop;
  /** Stream configuration */
  streamConfig?: VirtualDesktopStreamConfig;
  /** Whether to show controls */
  showControls?: boolean;
  /** Whether to allow interaction */
  allowInteraction?: boolean;
  /** Called when stream status changes */
  onStreamStatusChange?: (isStreaming: boolean) => void;
}

export const VirtualDesktopStream: React.FC<VirtualDesktopStreamProps> = ({
  desktop,
  streamConfig,
  showControls = true,
  allowInteraction = true,
  onStreamStatusChange
}) => {
  // ============================================================================
  // REFS AND STATE
  // ============================================================================

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const [isStreaming, setIsStreaming] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState([50]);
  const [quality, setQuality] = useState([streamConfig?.quality || 80]);
  const [frameRate, setFrameRate] = useState([streamConfig?.frameRate || 30]);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [streamStats, setStreamStats] = useState({
    bitrate: 0,
    fps: 0,
    latency: 0,
    packetsLost: 0
  });

  const { toast } = useToast();
  const virtualDesktopManager = getVirtualDesktopManager();

  // ============================================================================
  // STREAM MANAGEMENT
  // ============================================================================

  const startStream = useCallback(async () => {
    if (isStreaming) return;

    setIsConnecting(true);
    setConnectionStatus('connecting');

    try {
      // Start the stream on the virtual desktop
      await virtualDesktopManager.startStream(desktop.id), {
        quality: quality[0] || streamConfig?.quality || 80,
        frameRate: frameRate[0] || streamConfig?.frameRate || 30,
        format: streamConfig?.format || 'webrtc',
        compression: streamConfig?.compression || 'h264',
        bitrate: streamConfig?.bitrate || 2000,
        resolution: desktop.resolution || { width: 1920, height: 1080 }
      };
      // Connect WebSocket for real-time communication
      const wsUrl = `${WEBSOCKET_CONFIG.BASE_URL}/desktop/${desktop.id}/stream`;
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        setConnectionStatus('connected');
        setIsStreaming(true);
        setIsConnecting(false);
        onStreamStatusChange?.(true);
        
        toast({
          title: "Stream Started",
          description: `Connected to ${desktop.name}`,
        });
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'frame') {
            // Handle video frame data
            displayFrame(data.frame);
          } else if (data.type === 'stats') {
            // Update stream statistics
            setStreamStats(data.stats);
          } else if (data.type === 'audio') {
            // Handle audio data
            playAudio(data.audio);
          }
        } catch (error) {
          console.error('Error processing stream data:', error);
        }
      };

      wsRef.current.onerror = (error) => {
        console.warn('Virtual desktop stream connection failed - service may not be available');
        // Only show toast if user explicitly tried to connect
        if (isConnecting) {
          toast({
            title: "Stream Error",
            description: "Connection error occurred",
            variant: "destructive"
          });
        }
      };

      wsRef.current.onclose = () => {
        setConnectionStatus('disconnected');
        setIsStreaming(false);
        onStreamStatusChange?.(false);
      };

    } catch (error) {
      console.error('Error starting stream:', error);
      setIsConnecting(false);
      setConnectionStatus('disconnected');
      
      toast({
        title: "Stream Failed",
        description: "Failed to start desktop stream",
        variant: "destructive"
      });
    }
  }, [desktop.id, quality, frameRate, streamConfig, isStreaming, onStreamStatusChange, toast, virtualDesktopManager]);

  const stopStream = useCallback(async () => {
    try {
      // Close WebSocket connection
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      // Stop the stream on the virtual desktop
      await virtualDesktopManager.stopStream(desktop.id);

      setIsStreaming(false);
      setConnectionStatus('disconnected');
      onStreamStatusChange?.(false);
      
      toast({
        title: "Stream Stopped",
        description: `Disconnected from ${desktop.name}`,
      });
    } catch (error) {
      console.error('Error stopping stream:', error);
      toast({
        title: "Stop Failed",
        description: "Failed to stop stream",
        variant: "destructive"
      });
    }
  }, [desktop.id, onStreamStatusChange, toast, virtualDesktopManager]);

  // ============================================================================
  // FRAME HANDLING
  // ============================================================================

  const displayFrame = useCallback((frameData: string) => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Set canvas size to match desktop resolution
      canvas.width = desktop.resolution?.width || 1920;
      canvas.height = desktop.resolution?.height || 1080;
      
      // Draw the frame
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
    
    // Assume frameData is base64 encoded image
    img.src = `data:image/jpeg;base64,${frameData}`;
  }, [desktop.resolution]);

  const playAudio = useCallback((audioData: string) => {
    if (isMuted) return;

    try {
      // In a real implementation, this would handle audio streaming
      // For now, we'll just log that audio data was received
      console.log('Audio data received:', audioData.length, 'bytes');
    } catch (error) {
      console.error('Error playing audio:', error);
    }
  }, [isMuted]);

  // ============================================================================
  // INTERACTION HANDLING
  // ============================================================================

  const handleMouseEvent = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!allowInteraction || !isStreaming || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    
    // Calculate relative coordinates
    const x = ((event.clientX - rect.left) / rect.width) * (desktop.resolution?.width || 1920);
      const y = ((event.clientY - rect.top) / rect.height) * (desktop.resolution?.height || 1080);

    const mouseData = {
      x: Math.round(x),
      y: Math.round(y),
      button: event.button,
      type: event.type
    };

    // Send mouse event to virtual desktop
    virtualDesktopManager.sendInput(desktop.id, 'mouse', mouseData).catch(error => {
      console.error('Error sending mouse input:', error);
    });
  }, [allowInteraction, isStreaming, desktop.id, desktop.resolution, virtualDesktopManager]);

  const handleKeyboardEvent = useCallback((event: React.KeyboardEvent) => {
    if (!allowInteraction || !isStreaming) return;

    event.preventDefault();

    const keyData = {
      key: event.key,
      code: event.code,
      ctrlKey: event.ctrlKey,
      altKey: event.altKey,
      shiftKey: event.shiftKey,
      type: event.type
    };

    // Send keyboard event to virtual desktop
    virtualDesktopManager.sendInput(desktop.id, 'keyboard', keyData).catch(error => {
      console.error('Error sending keyboard input:', error);
    });
  }, [allowInteraction, isStreaming, desktop.id, virtualDesktopManager]);

  // ============================================================================
  // FULLSCREEN HANDLING
  // ============================================================================

  const toggleFullscreen = useCallback(() => {
    if (!canvasRef.current) return;

    if (!isFullscreen) {
      canvasRef.current.requestFullscreen().then(() => {
        setIsFullscreen(true);
      }).catch(error => {
        console.error('Error entering fullscreen:', error);
      });
    } else {
      document.exitFullscreen().then(() => {
        setIsFullscreen(false);
      }).catch(error => {
        console.error('Error exiting fullscreen:', error);
      });
    }
  }, [isFullscreen]);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  useEffect(() => {
    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    // Handle fullscreen change events
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const renderStreamControls = () => (
    <div className="flex items-center justify-between p-4 bg-gray-50 border-t">
      <div className="flex items-center space-x-2">
        <Button
          size="sm"
          onClick={isStreaming ? stopStream : startStream}
          disabled={isConnecting}
          variant={isStreaming ? "destructive" : "default"}
        >
          {isConnecting ? (
            <>
              <RotateCcw className="h-4 w-4 mr-2 animate-spin" />
              Connecting...
            </>
          ) : isStreaming ? (
            <>
              <Square className="h-4 w-4 mr-2" />
              Stop
            </>
          ) : (
            <>
              <Play className="h-4 w-4 mr-2" />
              Start
            </>
          )}
        </Button>

        <Badge variant={connectionStatus === 'connected' ? 'default' : 'secondary'}>
          {connectionStatus === 'connected' ? (
            <Wifi className="h-3 w-3 mr-1" />
          ) : (
            <WifiOff className="h-3 w-3 mr-1" />
          )}
          {connectionStatus}
        </Badge>
      </div>

      <div className="flex items-center space-x-4">
        {/* Audio Controls */}
        <div className="flex items-center space-x-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setIsMuted(!isMuted)}
          >
            {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </Button>
          <div className="w-20">
            <Slider
              value={volume}
              onValueChange={setVolume}
              max={100}
              step={1}
              disabled={isMuted}
            />
          </div>
        </div>

        {/* Quality Controls */}
        <div className="flex items-center space-x-2">
          <Label className="text-sm">Quality:</Label>
          <div className="w-20">
            <Slider
              value={quality}
              onValueChange={setQuality}
              min={10}
              max={100}
              step={10}
              disabled={isStreaming}
            />
          </div>
          <span className="text-sm text-gray-500">{quality[0]}%</span>
        </div>

        {/* Fullscreen */}
        <Button
          size="sm"
          variant="outline"
          onClick={toggleFullscreen}
          disabled={!isStreaming}
        >
          {isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );

  const renderStreamStats = () => (
    <div className="absolute top-4 right-4 bg-black bg-opacity-75 text-white p-2 rounded text-xs space-y-1">
      <div>FPS: {streamStats.fps}</div>
      <div>Bitrate: {(streamStats.bitrate / 1000).toFixed(1)}k</div>
      <div>Latency: {streamStats.latency}ms</div>
      {streamStats.packetsLost > 0 && (
        <div className="text-red-400">Lost: {streamStats.packetsLost}</div>
      )}
    </div>
  );

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center">
            <Monitor className="h-5 w-5 mr-2" />
            {desktop.name} Stream
          </div>
          <div className="flex items-center space-x-2">
            {allowInteraction && (
              <>
                <MousePointer className="h-4 w-4 text-gray-400" />
                <Keyboard className="h-4 w-4 text-gray-400" />
              </>
            )}
          </div>
        </CardTitle>
      </CardHeader>
      
      <CardContent className="p-0">
        <div className="relative bg-black">
          <canvas
            ref={canvasRef}
            className="w-full h-auto max-h-96 cursor-crosshair"
            onClick={handleMouseEvent}
            onMouseDown={handleMouseEvent}
            onMouseUp={handleMouseEvent}
            onMouseMove={handleMouseEvent}
            onKeyDown={handleKeyboardEvent}
            onKeyUp={handleKeyboardEvent}
            tabIndex={0}
            style={{
              aspectRatio: `${desktop.resolution?.width || 1920}/${desktop.resolution?.height || 1080}`
            }}
          />
          
          {!isStreaming && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-900 bg-opacity-50">
              <div className="text-center text-white">
                <Monitor className="h-16 w-16 mx-auto mb-4 text-gray-400" />
                <p className="text-lg font-medium">Stream Not Active</p>
                <p className="text-sm text-gray-300">Click Start to begin streaming</p>
              </div>
            </div>
          )}
          
          {isStreaming && renderStreamStats()}
        </div>
        
        {showControls && renderStreamControls()}
      </CardContent>
    </Card>
  );
};