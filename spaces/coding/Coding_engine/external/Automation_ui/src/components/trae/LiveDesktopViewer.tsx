/**
 * TRAE Live Desktop Viewer Component
 * 
 * Universelle Live-Desktop-Anzeige für firmenweite Nutzung
 * Optimiert für Docker-Deployment und Skalierbarkeit
 * Enhanced with OCR capabilities and N8N integration
 * Author: TRAE Development Team
 * Version: 2.1.0
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  Monitor, 
  Play, 
  Pause, 
  Square, 
  Settings, 
  Maximize, 
  RefreshCw,
  Wifi,
  WifiOff,
  AlertCircle,
  CheckCircle,
  Crop,
  Type,
  Send,
  Clock,
  Target
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { createLiveDesktopClient, WEBSOCKET_CONFIG } from '@/config/websocketConfig';

// ============================================================================
// INTERFACES
// ============================================================================

interface LiveDesktopConfig {
  /** Frame rate für das Streaming (1-30 FPS) */
  fps: number;
  /** Skalierungsfaktor für die Anzeige (0.1-2.0) */
  scale_factor: number;
  /** Bildqualität (10-100%) */
  quality: number;
  /** Screenshot-Methode */
  screenshot_method: 'powershell' | 'vnc' | 'rdp';
  /** Verbindungs-Timeout in Sekunden */
  connection_timeout: number;
  /** Automatische Wiederverbindung */
  auto_reconnect: boolean;
  /** Kompression aktivieren */
  compression: boolean;
}

interface ConnectionStatus {
  connected: boolean;
  streaming: boolean;
  connection_name: string | null;
  latency: number;
  fps_actual: number;
  bytes_received: number;
  last_frame_time: string | null;
}

interface OCRRegion {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  lastExtractedText: string;
  isActive: boolean;
}

interface OCRConfig {
  enabled: boolean;
  extractionInterval: number; // minutes
  n8nWebhookUrl: string;
  autoSend: boolean;
}

interface LiveDesktopViewerProps {
  /** Eindeutige ID für den Viewer */
  viewerId?: string;
  /** Breite des Viewers */
  width?: number;
  /** Höhe des Viewers */
  height?: number;
  /** Initiale Konfiguration */
  initialConfig?: Partial<LiveDesktopConfig>;
  /** Callback bei Verbindungsänderungen */
  onConnectionChange?: (status: ConnectionStatus) => void;
  /** Callback bei Fehlern */
  onError?: (error: string) => void;
  /** Vollbild-Modus verfügbar */
  allowFullscreen?: boolean;
  /** Steuerungsleiste anzeigen */
  showControls?: boolean;
  /** Automatisch starten */
  autoStart?: boolean;
  /** CSS-Klassen */
  className?: string;
  /** OCR functionality enabled */
  enableOCR?: boolean;
}

// ============================================================================
// DEFAULT CONFIG
// ============================================================================

const DEFAULT_CONFIG: LiveDesktopConfig = {
  fps: 10,
  scale_factor: 0.8,
  quality: 75,
  screenshot_method: 'powershell',
  connection_timeout: 30,
  auto_reconnect: true,
  compression: true
};

const DEFAULT_OCR_CONFIG: OCRConfig = {
  enabled: false,
  extractionInterval: 5, // minutes
  n8nWebhookUrl: '',
  autoSend: true
};

// ============================================================================
// LIVE DESKTOP VIEWER COMPONENT
// ============================================================================

export const LiveDesktopViewer: React.FC<LiveDesktopViewerProps> = ({
  viewerId = 'live-desktop-viewer',
  width = 800,
  height = 600,
  initialConfig = {},
  onConnectionChange,
  onError,
  allowFullscreen = true,
  showControls = true,
  autoStart = false,
  className = '',
  enableOCR = false
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const [config, setConfig] = useState<LiveDesktopConfig>({
    ...DEFAULT_CONFIG,
    ...initialConfig
  });

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    connected: false,
    streaming: false,
    connection_name: null,
    latency: 0,
    fps_actual: 0,
    bytes_received: 0,
    last_frame_time: null
  });

  const [isLoading, setIsLoading] = useState(false);
  const [ocrConfig, setOcrConfig] = useState<OCRConfig>(DEFAULT_OCR_CONFIG);
  const [ocrRegions, setOcrRegions] = useState<OCRRegion[]>([]);
  const [isDrawingRegion, setIsDrawingRegion] = useState(false);
  const [currentRegion, setCurrentRegion] = useState<Partial<OCRRegion> | null>(null);
  const [showOCRPanel, setShowOCRPanel] = useState(false);
  const [lastExtractionTime, setLastExtractionTime] = useState<Date | null>(null);
  const [nextExtractionTime, setNextExtractionTime] = useState<Date | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const extractionIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const { toast } = useToast();

  // ============================================================================
  // OCR FUNCTIONALITY
  // ============================================================================

  const startRegionDrawing = useCallback(() => {
    setIsDrawingRegion(true);
    setCurrentRegion(null);
  }, []);

  const handleCanvasMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawingRegion) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * width;
    const y = ((e.clientY - rect.top) / rect.height) * height;

    setCurrentRegion({
      x,
      y,
      width: 0,
      height: 0
    });
  }, [isDrawingRegion, width, height]);

  const handleCanvasMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawingRegion || !currentRegion) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const currentX = ((e.clientX - rect.left) / rect.width) * width;
    const currentY = ((e.clientY - rect.top) / rect.height) * height;

    setCurrentRegion(prev => ({
      ...prev,
      width: currentX - (prev?.x || 0),
      height: currentY - (prev?.y || 0)
    }));

    drawRegionOverlay();
  }, [isDrawingRegion, currentRegion, width, height]);

  const handleCanvasMouseUp = useCallback(() => {
    if (!isDrawingRegion || !currentRegion) return;

    const newRegion: OCRRegion = {
      id: `region-${Date.now()}`,
      x: currentRegion.x || 0,
      y: currentRegion.y || 0,
      width: Math.abs(currentRegion.width || 0),
      height: Math.abs(currentRegion.height || 0),
      label: `Region ${ocrRegions.length + 1}`,
      lastExtractedText: '',
      isActive: true
    };

    if (newRegion.width > 10 && newRegion.height > 10) {
      setOcrRegions(prev => [...prev, newRegion]);
      toast({
        title: "OCR Region Created",
        description: `Region "${newRegion.label}" added for text extraction`,
      });
    }

    setIsDrawingRegion(false);
    setCurrentRegion(null);
    drawRegionOverlay();
  }, [isDrawingRegion, currentRegion, ocrRegions.length, toast]);

  const drawRegionOverlay = useCallback(() => {
    const overlayCanvas = overlayCanvasRef.current;
    if (!overlayCanvas) return;

    const ctx = overlayCanvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    // Draw existing regions
    ocrRegions.forEach((region, index) => {
      const scaleX = overlayCanvas.width / width;
      const scaleY = overlayCanvas.height / height;
      
      ctx.strokeStyle = region.isActive ? '#3b82f6' : '#6b7280';
      ctx.fillStyle = region.isActive ? 'rgba(59, 130, 246, 0.1)' : 'rgba(107, 114, 128, 0.1)';
      ctx.lineWidth = 2;
      
      const x = region.x * scaleX;
      const y = region.y * scaleY;
      const w = region.width * scaleX;
      const h = region.height * scaleY;
      
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
      
      // Draw label
      ctx.fillStyle = region.isActive ? '#3b82f6' : '#6b7280';
      ctx.font = '12px sans-serif';
      ctx.fillText(region.label, x + 4, y + 16);
    });

    // Draw current region being drawn
    if (currentRegion && currentRegion.x !== undefined && currentRegion.y !== undefined) {
      const scaleX = overlayCanvas.width / width;
      const scaleY = overlayCanvas.height / height;
      
      ctx.strokeStyle = '#ef4444';
      ctx.fillStyle = 'rgba(239, 68, 68, 0.1)';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      
      const x = currentRegion.x * scaleX;
      const y = currentRegion.y * scaleY;
      const w = (currentRegion.width || 0) * scaleX;
      const h = (currentRegion.height || 0) * scaleY;
      
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);
    }
  }, [ocrRegions, currentRegion, width, height]);

  const extractTextFromRegions = useCallback(async () => {
    if (!connectionStatus.streaming || ocrRegions.length === 0) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    try {
      const extractedData = [];

      for (const region of ocrRegions.filter(r => r.isActive)) {
        // Create a temporary canvas for the region
        const regionCanvas = document.createElement('canvas');
        regionCanvas.width = region.width;
        regionCanvas.height = region.height;
        const regionCtx = regionCanvas.getContext('2d');
        
        if (regionCtx) {
          // Extract the region from the main canvas
          regionCtx.drawImage(
            canvas,
            region.x, region.y, region.width, region.height,
            0, 0, region.width, region.height
          );
          
          // Convert to base64 for OCR processing
          const imageData = regionCanvas.toDataURL('image/png');
          
          // Simulate OCR extraction (in production, use actual OCR service)
          const extractedText = await simulateOCR(imageData);
          
          // Update region with extracted text
          setOcrRegions(prev => prev.map(r => 
            r.id === region.id 
              ? { ...r, lastExtractedText: extractedText }
              : r
          ));

          extractedData.push({
            regionId: region.id,
            regionLabel: region.label,
            extractedText,
            timestamp: new Date().toISOString(),
            coordinates: {
              x: region.x,
              y: region.y,
              width: region.width,
              height: region.height
            }
          });
        }
      }

      if (extractedData.length > 0 && ocrConfig.autoSend) {
        await sendToN8NWebhook(extractedData);
      }

      setLastExtractionTime(new Date());
      
      toast({
        title: "Text Extracted",
        description: `Extracted text from ${extractedData.length} regions`,
      });

    } catch (error) {
      console.error('OCR extraction failed:', error);
      toast({
        title: "Extraction Failed",
        description: "Failed to extract text from regions",
        variant: "destructive",
      });
    }
  }, [connectionStatus.streaming, ocrRegions, ocrConfig.autoSend, toast]);

  const simulateOCR = async (imageData: string): Promise<string> => {
    // Simulate OCR processing delay
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // In production, replace with actual OCR service call
    const sampleTexts = [
      "Sample extracted text from region",
      "Document title: Important Report",
      "Status: Processing",
      "Date: " + new Date().toLocaleDateString(),
      "User: John Doe",
      "Amount: $1,234.56"
    ];
    
    return sampleTexts[Math.floor(Math.random() * sampleTexts.length)];
  };

  const sendToN8NWebhook = async (extractedData: any[]) => {
    if (!ocrConfig.n8nWebhookUrl) return;

    try {
      const payload = {
        viewerId,
        timestamp: new Date().toISOString(),
        extractedData,
        metadata: {
          connectionStatus,
          config
        }
      };

      const response = await fetch(ocrConfig.n8nWebhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        toast({
          title: "Data Sent",
          description: "Extracted data sent to N8N webhook successfully",
        });
      } else {
        throw new Error(`HTTP ${response.status}`);
      }
    } catch (error) {
      console.error('Failed to send to N8N webhook:', error);
      toast({
        title: "Send Failed",
        description: "Failed to send data to N8N webhook",
        variant: "destructive",
      });
    }
  };

  // ============================================================================
  // WEBSOCKET CONNECTION
  // ============================================================================

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      setIsLoading(true);
      // Use centralized WebSocket client creation for consistency
      const { websocket } = createLiveDesktopClient(viewerId);
      wsRef.current = websocket;

      wsRef.current.onopen = () => {
        console.log(`[${viewerId}] WebSocket connected`);
        setConnectionStatus(prev => ({ ...prev, connected: true }));
        onConnectionChange?.({ ...connectionStatus, connected: true });
        setIsLoading(false);
        
        toast({
          title: "Connected",
          description: "Live desktop connection established",
        });
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'frame' && data.image) {
            drawFrame(data.image);
            setConnectionStatus(prev => ({
              ...prev,
              streaming: true,
              fps_actual: data.fps || prev.fps_actual,
              latency: data.latency || prev.latency,
              bytes_received: prev.bytes_received + (event.data.length || 0),
              last_frame_time: new Date().toISOString()
            }));
          }
        } catch (error) {
          console.error(`[${viewerId}] Failed to parse WebSocket message:`, error);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error(`[${viewerId}] WebSocket error:`, error);
        const errorMessage = 'WebSocket connection failed';
        onError?.(errorMessage);
        toast({
          title: "Connection Error",
          description: errorMessage,
          variant: "destructive",
        });
      };

      wsRef.current.onclose = () => {
        console.log(`[${viewerId}] WebSocket disconnected`);
        setConnectionStatus(prev => ({ 
          ...prev, 
          connected: false, 
          streaming: false 
        }));
        onConnectionChange?.({ ...connectionStatus, connected: false, streaming: false });
        setIsLoading(false);
      };

    } catch (error) {
      console.error(`[${viewerId}] Failed to create WebSocket:`, error);
      setIsLoading(false);
      onError?.('Failed to establish connection');
    }
  }, [viewerId, connectionStatus, onConnectionChange, onError, toast]);

  // ============================================================================
  // CANVAS DRAWING
  // ============================================================================

  const drawFrame = useCallback((imageData: string) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      
      // Redraw OCR regions overlay
      setTimeout(() => drawRegionOverlay(), 0);
    };
    img.src = `data:image/png;base64,${imageData}`;
  }, [drawRegionOverlay]);

  // ============================================================================
  // CONTROL HANDLERS
  // ============================================================================

  const handleStart = useCallback(() => {
    connectWebSocket();
  }, [connectWebSocket]);

  const handleStop = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionStatus(prev => ({ 
      ...prev, 
      connected: false, 
      streaming: false 
    }));
  }, []);

  const handleReconnect = useCallback(() => {
    handleStop();
    setTimeout(() => {
      handleStart();
    }, 1000);
  }, [handleStart, handleStop]);

  const toggleOCRExtraction = useCallback(() => {
    if (ocrConfig.enabled) {
      // Stop extraction
      if (extractionIntervalRef.current) {
        clearInterval(extractionIntervalRef.current);
        extractionIntervalRef.current = null;
      }
      setOcrConfig(prev => ({ ...prev, enabled: false }));
      setNextExtractionTime(null);
    } else {
      // Start extraction
      setOcrConfig(prev => ({ ...prev, enabled: true }));
      
      const intervalMs = ocrConfig.extractionInterval * 60 * 1000;
      extractionIntervalRef.current = setInterval(extractTextFromRegions, intervalMs);
      
      const nextTime = new Date();
      nextTime.setMinutes(nextTime.getMinutes() + ocrConfig.extractionInterval);
      setNextExtractionTime(nextTime);
    }
  }, [ocrConfig.enabled, ocrConfig.extractionInterval, extractTextFromRegions]);

  // ============================================================================
  // LIFECYCLE
  // ============================================================================

  useEffect(() => {
    if (autoStart) {
      handleStart();
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (extractionIntervalRef.current) {
        clearInterval(extractionIntervalRef.current);
      }
    };
  }, [autoStart, handleStart]);

  useEffect(() => {
    drawRegionOverlay();
  }, [ocrRegions, drawRegionOverlay]);

  // ============================================================================
  // RENDER COMPONENTS
  // ============================================================================

  const renderOCRPanel = () => {
    if (!enableOCR || !showOCRPanel) return null;

    return (
      <Card className="mt-4">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center space-x-2">
            <Type className="w-5 h-5" />
            <span>OCR Configuration</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="extraction-interval">Extraction Interval (minutes)</Label>
              <Input
                id="extraction-interval"
                type="number"
                min="1"
                max="60"
                value={ocrConfig.extractionInterval}
                onChange={(e) => setOcrConfig(prev => ({ 
                  ...prev,
                  extractionInterval: parseInt(e.target.value) || 4 
                }))}
              />
            </div>
            <div>
              <Label htmlFor="auto-send">Auto Send</Label>
              <div className="flex items-center space-x-2 mt-2">
                <input
                  id="auto-send"
                  type="checkbox"
                  checked={ocrConfig.autoSend}
                  onChange={(e) => setOcrConfig(prev => ({ 
                    ...prev,
                    autoSend: e.target.checked 
                  }))}
                />
                <span className="text-sm">Automatically send to webhooks</span>
              </div>
            </div>
          </div>
          
          <div>
            <Label htmlFor="n8n-webhook">N8N Webhook URL</Label>
            <Input
              id="n8n-webhook"
              type="url"
              placeholder="https://your-n8n-instance.com/webhook/..."
              value={ocrConfig.n8nWebhookUrl}
              onChange={(e) => setOcrConfig(prev => ({ 
                ...prev,
                n8nWebhookUrl: e.target.value 
              }))}
            />
          </div>

          {ocrRegions.length > 0 && (
            <div>
              <Label>OCR Regions ({ocrRegions.length})</Label>
              <div className="space-y-2 mt-2">
                {ocrRegions.map((region) => (
                  <div key={region.id} className="flex items-center justify-between p-2 bg-muted rounded">
                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={region.isActive}
                        onChange={(e) => setOcrRegions(prev => prev.map(r => 
                          r.id === region.id ? { ...r, isActive: e.target.checked } : r
                        ))}
                      />
                      <span className="text-sm font-medium">{region.label}</span>
                      <Badge variant="outline" className="text-xs">
                        {Math.round(region.width)}×{Math.round(region.height)}
                      </Badge>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setOcrRegions(prev => prev.filter(r => r.id !== region.id))}
                    >
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  const renderControls = () => {
    if (!showControls) return null;

    return (
      <div className="flex items-center space-x-2 p-3 bg-muted/50 border-t">
        <Button
          onClick={connectionStatus.connected ? handleStop : handleStart}
          variant={connectionStatus.connected ? "destructive" : "default"}
          size="sm"
          disabled={isLoading}
        >
          {isLoading ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : connectionStatus.connected ? (
            <Square className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          <span className="ml-2">
            {isLoading ? 'Connecting...' : connectionStatus.connected ? 'Stop' : 'Start'}
          </span>
        </Button>

        <Button
          onClick={handleReconnect}
          variant="outline"
          size="sm"
          disabled={isLoading}
        >
          <RefreshCw className="w-4 h-4" />
          <span className="ml-2">Reconnect</span>
        </Button>

        {enableOCR && (
          <>
            <Button
              onClick={startRegionDrawing}
              variant={isDrawingRegion ? "default" : "outline"}
              size="sm"
              disabled={!connectionStatus.streaming}
            >
              <Crop className="w-4 h-4" />
              <span className="ml-2">
                {isDrawingRegion ? 'Drawing...' : 'Add Region'}
              </span>
            </Button>

            <Button
              onClick={toggleOCRExtraction}
              variant={ocrConfig.enabled ? "default" : "outline"}
              size="sm"
              disabled={ocrRegions.length === 0}
            >
              <Clock className="w-4 h-4" />
              <span className="ml-2">
                {ocrConfig.enabled ? 'Stop OCR' : 'Start OCR'}
              </span>
            </Button>

            <Button
              onClick={extractTextFromRegions}
              variant="outline"
              size="sm"
              disabled={!connectionStatus.streaming || ocrRegions.length === 0}
            >
              <Type className="w-4 h-4" />
              <span className="ml-2">Extract Now</span>
            </Button>

            <Button
              onClick={() => setShowOCRPanel(!showOCRPanel)}
              variant="outline"
              size="sm"
            >
              <Settings className="w-4 h-4" />
              <span className="ml-2">OCR Settings</span>
            </Button>
          </>
        )}

        <div className="flex items-center space-x-2 text-sm text-muted-foreground">
          {connectionStatus.connected ? (
            <CheckCircle className="w-4 h-4 text-green-500" />
          ) : (
            <AlertCircle className="w-4 h-4 text-red-500" />
          )}
          <span>
            {connectionStatus.connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>

        {connectionStatus.streaming && (
          <div className="flex items-center space-x-4 text-xs text-muted-foreground">
            <span>FPS: {connectionStatus.fps_actual}</span>
            <span>Latency: {connectionStatus.latency}ms</span>
            {enableOCR && ocrRegions.length > 0 && (
              <span>Regions: {ocrRegions.filter(r => r.isActive).length}/{ocrRegions.length}</span>
            )}
          </div>
        )}

        {enableOCR && ocrConfig.enabled && nextExtractionTime && (
          <div className="flex items-center space-x-2 text-xs text-muted-foreground">
            <Clock className="w-3 h-3" />
            <span>Next: {nextExtractionTime.toLocaleTimeString()}</span>
          </div>
        )}
      </div>
    );
  };

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <div>
      <Card className={`overflow-hidden ${className}`}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center space-x-2">
            <Monitor className="w-5 h-5" />
            <span>Live Desktop - {viewerId}</span>
            {enableOCR && (
              <Badge variant="secondary" className="ml-2">
                <Type className="w-3 h-3 mr-1" />
                OCR Enabled
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="relative">
            <canvas
              ref={canvasRef}
              width={width}
              height={height}
              className="w-full h-auto bg-muted"
              style={{ aspectRatio: `${width}/${height}` }}
            />
            
            {enableOCR && (
              <canvas
                ref={overlayCanvasRef}
                width={width}
                height={height}
                className="absolute inset-0 w-full h-auto pointer-events-none"
                onMouseDown={handleCanvasMouseDown}
                onMouseMove={handleCanvasMouseMove}
                onMouseUp={handleCanvasMouseUp}
                style={{
                  aspectRatio: `${width}/${height}`,
                  pointerEvents: isDrawingRegion ? 'auto' : 'none',
                  cursor: isDrawingRegion ? 'crosshair' : 'default'
                }}
              />
            )}
            
            {!connectionStatus.connected && !isLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-muted/80">
                <div className="text-center">
                  <WifiOff className="w-12 h-12 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Not connected</p>
                  <Button
                    onClick={handleStart}
                    variant="outline"
                    size="sm"
                    className="mt-2"
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Connect
                  </Button>
                </div>
              </div>
            )}

            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-muted/80">
                <div className="text-center">
                  <RefreshCw className="w-8 h-8 mx-auto mb-2 text-primary animate-spin" />
                  <p className="text-sm text-muted-foreground">Connecting...</p>
                </div>
              </div>
            )}

            {isDrawingRegion && (
              <div className="absolute top-2 left-2 bg-blue-500 text-white px-2 py-1 rounded text-xs">
                <Target className="w-3 h-3 inline mr-1" />
                Click and drag to create OCR region
              </div>
            )}
          </div>

          {renderControls()}
        </CardContent>
      </Card>

      {renderOCRPanel()}
    </div>
  );
};

export default LiveDesktopViewer;