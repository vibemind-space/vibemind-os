/**
 * Live Desktop Interface Component
 * 
 * Interface node that connects WebSocket config, triggers, and actions
 * Integrates with filesystem bridge for data persistence and communication
 * Author: TRAE Development Team
 * Version: 3.0.0
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
  Database,
  FileText,
  Activity,
  Link,
  Zap,
  Clock
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FilesystemBridge, FilesystemBridgeConfig, WorkflowData, ActionCommand, ActionResult } from '@/services/filesystemBridge';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';

// ============================================================================
// INTERFACES
// ============================================================================

interface WebSocketConfig {
  url: string;
  port: number;
  autoReconnect: boolean;
  reconnectInterval: number;
  maxReconnectAttempts: number;
  enableFilesystemBridge: boolean;
  dataDirectory: string;
  fileFormat: 'json' | 'xml' | 'csv';
  watchInterval: number;
}

interface TriggerConfig {
  type: 'manual' | 'webhook' | 'schedule' | 'filesystem';
  enabled: boolean;
  parameters: any;
}

interface ActionConfig {
  type: 'click' | 'type' | 'http' | 'ocr' | 'custom';
  enabled: boolean;
  parameters: any;
  outputToFilesystem: boolean;
}

interface InterfaceStatus {
  websocketConnected: boolean;
  filesystemBridgeActive: boolean;
  triggersActive: number;
  actionsActive: number;
  lastDataTransfer: Date | null;
  dataTransferCount: number;
}

interface LiveDesktopInterfaceProps {
  /** Unique interface ID */
  interfaceId?: string;
  /** WebSocket configuration */
  websocketConfig?: Partial<WebSocketConfig>;
  /** Trigger configurations */
  triggers?: TriggerConfig[];
  /** Action configurations */
  actions?: ActionConfig[];
  /** Filesystem bridge configuration */
  filesystemConfig?: Partial<FilesystemBridgeConfig>;
  /** Callback for status changes */
  onStatusChange?: (status: InterfaceStatus) => void;
  /** Callback for data output */
  onDataOutput?: (data: WorkflowData) => void;
  /** Callback for errors */
  onError?: (error: string) => void;
  /** Enable auto-start */
  autoStart?: boolean;
  /** CSS classes */
  className?: string;
}

// ============================================================================
// DEFAULT CONFIGURATIONS
// ============================================================================

const DEFAULT_WEBSOCKET_CONFIG: WebSocketConfig = {
  url: WEBSOCKET_CONFIG.BASE_URL,
  port: 8007, // Legacy support - extracted from BASE_URL in practice
  autoReconnect: true,
  reconnectInterval: WEBSOCKET_CONFIG.CONNECTION.RECONNECT_DELAY,
  maxReconnectAttempts: WEBSOCKET_CONFIG.CONNECTION.MAX_RECONNECT_ATTEMPTS,
  enableFilesystemBridge: true,
  dataDirectory: './workflow-data',
  fileFormat: 'json',
  watchInterval: 1000
};

const DEFAULT_FILESYSTEM_CONFIG: FilesystemBridgeConfig = {
  baseDataPath: './workflow-data',
  websocketUrl: WEBSOCKET_CONFIG.BASE_URL,
  websocketPort: 8007, // Legacy support - extracted from BASE_URL in practice
  watchInterval: 1000,
  autoCleanup: true,
  maxFileAge: 3600000 // 1 hour
};

// ============================================================================
// LIVE DESKTOP INTERFACE COMPONENT
// ============================================================================

export const LiveDesktopInterface: React.FC<LiveDesktopInterfaceProps> = ({
  interfaceId = 'live-desktop-interface',
  websocketConfig = {},
  triggers = [],
  actions = [],
  filesystemConfig = {},
  onStatusChange,
  onDataOutput,
  onError,
  autoStart = false,
  className = ''
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const [wsConfig, setWsConfig] = useState<WebSocketConfig>({
    ...DEFAULT_WEBSOCKET_CONFIG,
    ...websocketConfig
  });

  const [fsConfig, setFsConfig] = useState<FilesystemBridgeConfig>({
    ...DEFAULT_FILESYSTEM_CONFIG,
    ...filesystemConfig
  });

  const [interfaceStatus, setInterfaceStatus] = useState<InterfaceStatus>({
    websocketConnected: false,
    filesystemBridgeActive: false,
    triggersActive: 0,
    actionsActive: 0,
    lastDataTransfer: null,
    dataTransferCount: 0
  });

  const [activeTriggers, setActiveTriggers] = useState<TriggerConfig[]>(triggers);
  const [activeActions, setActiveActions] = useState<ActionConfig[]>(actions);
  const [isLoading, setIsLoading] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [recentData, setRecentData] = useState<WorkflowData[]>([]);

  // Desktop streaming state
  const [desktopStreamActive, setDesktopStreamActive] = useState(false);
  const [desktopConnected, setDesktopConnected] = useState(false);
  const [streamQuality, setStreamQuality] = useState<'low' | 'medium' | 'high'>('medium');
  const [frameRate, setFrameRate] = useState(30);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const filesystemBridgeRef = useRef<FilesystemBridge | null>(null);
  // Store latest frame metadata for click coordinate mapping and routing
  const lastFrameInfoRef = useRef<{ width: number; height: number; monitorId?: string; sourceClientId?: string } | null>(null);
  const { toast } = useToast();

  // ============================================================================
  // FILESYSTEM BRIDGE INTEGRATION
  // ============================================================================

  const initializeFilesystemBridge = useCallback(async () => {
    try {
      setIsLoading(true);
      
      if (filesystemBridgeRef.current) {
        filesystemBridgeRef.current.disconnect();
      }

      const bridge = new FilesystemBridge(fsConfig);
      filesystemBridgeRef.current = bridge;

      // Set up event listeners
      bridge.on('connected', (data) => {
        setInterfaceStatus(prev => ({
          ...prev,
          websocketConnected: true,
          filesystemBridgeActive: true
        }));
        
        toast({
          title: "Filesystem Bridge Connected",
          description: `Connected to ${data.url}`,
        });

        if (onStatusChange) {
          onStatusChange({
            websocketConnected: true,
            filesystemBridgeActive: true,
            triggersActive: 0,
            actionsActive: 0,
            lastDataTransfer: null,
            dataTransferCount: 0
          });
        }
      });

      bridge.on('disconnected', () => {
        setInterfaceStatus(prev => ({
          ...prev,
          websocketConnected: false,
          filesystemBridgeActive: false
        }));

        toast({
          title: "Filesystem Bridge Disconnected",
          description: "Connection lost, attempting to reconnect...",
          variant: "destructive"
        });
      });

      bridge.on('fileWritten', (data) => {
        setInterfaceStatus(prev => ({
          ...prev,
          lastDataTransfer: new Date(),
          dataTransferCount: prev.dataTransferCount + 1
        }));

        setRecentData(prev => [data.data, ...prev.slice(0, 9)]);

        if (onDataOutput) {
          onDataOutput(data.data);
        }
      });

      bridge.on('actionResult', (result: ActionResult) => {
        toast({
          title: "Action Completed",
          description: `${result.nodeId}: ${result.status}`,
          variant: result.status === 'success' ? 'default' : 'destructive'
        });
      });

      bridge.on('error', (error) => {
        const errorMessage = `Filesystem Bridge Error: ${error.error}`;
        console.warn('Filesystem Bridge Error:', error);
        
        // Only show toast for non-connection errors to reduce noise
        if (error.context !== 'websocket') {
          toast({
            title: "Bridge Error",
            description: errorMessage,
            variant: "destructive"
          });
        }

        if (onError) {
          onError(errorMessage);
        }
      });

      // Desktop streaming event handlers
      bridge.on('desktop_connected', (data) => {
        setDesktopConnected(true);
        toast({
          title: "Desktop Client Connected",
          description: "Desktop capture client is now connected",
        });
      });

      bridge.on('desktop_disconnected', (data) => {
        setDesktopConnected(false);
        setDesktopStreamActive(false);
        
        // Clear canvas
        if (canvasRef.current) {
          const ctx = canvasRef.current.getContext('2d');
          if (ctx) {
            ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
          }
        }

        toast({
          title: "Desktop Client Disconnected",
          description: "Desktop capture client has disconnected",
          variant: "destructive"
        });
      });

      bridge.on('frame_data', (data) => {
        // Capture routing and sizing info for click routing before rendering
        try {
          const sourceClientId = data?.routingInfo?.sourceClientId || data?.metadata?.clientId || data?.clientId;
          const monitorId = data?.routingInfo?.monitorId || data?.monitorId || data?.metadata?.monitorId;
          if (data?.width && data?.height) {
            lastFrameInfoRef.current = {
              width: data.width,
              height: data.height,
              sourceClientId: sourceClientId || undefined,
              monitorId: monitorId || undefined
            };
          }
        } catch (e) {
          // Safe-guard: do not break frame rendering on metadata issues
          console.warn('[LiveDesktopInterface] Failed to capture frame routing info:', e);
        }

        if (data.frameData) {
          handleFrameData(data.frameData, data.width, data.height);
        }
      });

      bridge.on('stream_status', (data) => {
        if (data.status === 'started') {
          setDesktopStreamActive(true);
        } else if (data.status === 'stopped') {
          setDesktopStreamActive(false);
        }
      });

      // Connect to WebSocket
      await bridge.connect();

    } catch (error) {
      const errorMessage = `Failed to initialize filesystem bridge: ${error}`;
      console.warn('Filesystem bridge initialization failed:', error);
      
      // Show a more user-friendly message
      toast({
        title: "Desktop Interface Unavailable",
        description: "Desktop streaming service is not available. Some features may be limited.",
        variant: "default"
      });

      if (onError) {
        onError(errorMessage);
      }
    } finally {
      setIsLoading(false);
    }
  }, [fsConfig, onStatusChange, onDataOutput, onError]);

  // ============================================================================
  // TRIGGER MANAGEMENT
  // ============================================================================

  const activateTrigger = useCallback(async (trigger: TriggerConfig) => {
    if (!filesystemBridgeRef.current) {
      toast({
        title: "Bridge Not Ready",
        description: "Filesystem bridge must be connected first",
        variant: "destructive"
      });
      return;
    }

    try {
      const triggerData: WorkflowData = {
        id: `trigger_${Date.now()}`,
        timestamp: Date.now(),
        nodeId: `trigger_${trigger.type}`,
        nodeType: 'trigger',
        data: {
          type: trigger.type,
          parameters: trigger.parameters,
          activated: true
        },
        metadata: {
          executionId: `exec_${Date.now()}`,
          workflowId: interfaceId,
          status: 'completed'
        }
      };

      // Send trigger activation via filesystem bridge
      filesystemBridgeRef.current.sendWebSocketData('trigger_activated', triggerData);

      setActiveTriggers(prev => 
        prev.map(t => t.type === trigger.type ? { ...t, enabled: true } : t)
      );

      setInterfaceStatus(prev => ({
        ...prev,
        triggersActive: prev.triggersActive + 1
      }));

      toast({
        title: "Trigger Activated",
        description: `${trigger.type} trigger is now active`,
      });

    } catch (error) {
      toast({
        title: "Trigger Activation Failed",
        description: `Failed to activate ${trigger.type} trigger`,
        variant: "destructive"
      });
    }
  }, [interfaceId]);

  // ============================================================================
  // ACTION MANAGEMENT
  // ============================================================================

  const executeAction = useCallback(async (action: ActionConfig) => {
    if (!filesystemBridgeRef.current) {
      toast({
        title: "Bridge Not Ready",
        description: "Filesystem bridge must be connected first",
        variant: "destructive"
      });
      return;
    }

    try {
      const actionCommand: ActionCommand = {
        id: `action_${Date.now()}`,
        type: action.type as any,
        timestamp: Date.now(),
        nodeId: `action_${action.type}`,
        parameters: action.parameters,
        executionTimeout: 30000,
        waitForExecution: true
      };

      await filesystemBridgeRef.current.writeActionCommand(actionCommand);

      setActiveActions(prev => 
        prev.map(a => a.type === action.type ? { ...a, enabled: true } : a)
      );

      setInterfaceStatus(prev => ({
        ...prev,
        actionsActive: prev.actionsActive + 1
      }));

      toast({
        title: "Action Executed",
        description: `${action.type} action has been queued`,
      });

    } catch (error) {
      toast({
        title: "Action Execution Failed",
        description: `Failed to execute ${action.type} action`,
        variant: "destructive"
      });
    }
  }, []);

  // ============================================================================
  // DESKTOP STREAMING MANAGEMENT
  // ============================================================================

  const startDesktopStream = useCallback(async () => {
    if (!filesystemBridgeRef.current) {
      toast({
        title: "Bridge Not Ready",
        description: "Filesystem bridge must be connected first",
        variant: "destructive"
      });
      return;
    }

    try {
      // Send start desktop stream command
      const streamCommand = {
        type: 'start_desktop_stream',
        quality: streamQuality,
        frameRate: frameRate,
        timestamp: Date.now()
      };

      filesystemBridgeRef.current.sendWebSocketData('start_desktop_stream', streamCommand);
      setDesktopStreamActive(true);

      toast({
        title: "Desktop Stream Started",
        description: "Waiting for desktop client connection...",
      });

    } catch (error) {
      toast({
        title: "Stream Start Failed",
        description: "Failed to start desktop stream",
        variant: "destructive"
      });
    }
  }, [streamQuality, frameRate]);

  const stopDesktopStream = useCallback(async () => {
    if (!filesystemBridgeRef.current) return;

    try {
      const streamCommand = {
        type: 'stop_desktop_stream',
        timestamp: Date.now()
      };

      filesystemBridgeRef.current.sendWebSocketData('stop_desktop_stream', streamCommand);
      setDesktopStreamActive(false);
      setDesktopConnected(false);

      // Clear canvas
      if (canvasRef.current) {
        const ctx = canvasRef.current.getContext('2d');
        if (ctx) {
          ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
        }
      }

      toast({
        title: "Desktop Stream Stopped",
        description: "Stream has been disconnected",
      });

    } catch (error) {
      toast({
        title: "Stream Stop Failed",
        description: "Failed to stop desktop stream",
        variant: "destructive"
      });
    }
  }, []);

  const handleFrameData = useCallback((frameData: string, width?: number, height?: number) => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Use provided dimensions or fall back to image natural dimensions
      const imageWidth = width || img.naturalWidth;
      const imageHeight = height || img.naturalHeight;
      
      // Update canvas dimensions to match the image
      canvas.width = imageWidth;
      canvas.height = imageHeight;
      
      // Clear canvas and draw the new frame
      ctx.clearRect(0, 0, imageWidth, imageHeight);
      ctx.drawImage(img, 0, 0, imageWidth, imageHeight);
    };
    img.src = `data:image/jpeg;base64,${frameData}`;
  }, []);

  const handleCanvasClick = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!filesystemBridgeRef.current || !desktopStreamActive) {
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const offsetX = event.clientX - rect.left;
    const offsetY = event.clientY - rect.top;

    const last = lastFrameInfoRef.current;
    let nativeX = Math.round(offsetX);
    let nativeY = Math.round(offsetY);

    // Map click coordinates to the original frame resolution if available
    const displayedWidth = canvas.clientWidth || rect.width;
    const displayedHeight = canvas.clientHeight || rect.height;

    if (last && displayedWidth > 0 && displayedHeight > 0) {
      const scaleX = last.width / displayedWidth;
      const scaleY = last.height / displayedHeight;
      nativeX = Math.round(offsetX * scaleX);
      nativeY = Math.round(offsetY * scaleY);
    }

    const clickData = {
      type: 'desktop_click',
      x: nativeX,
      y: nativeY,
      canvasX: Math.round(offsetX),
      canvasY: Math.round(offsetY),
      frame: last ? { width: last.width, height: last.height, monitorId: last.monitorId, sourceClientId: last.sourceClientId } : undefined,
      timestamp: Date.now()
    };

    try {
      filesystemBridgeRef.current.sendWebSocketData('desktop_click', clickData);
      toast({
        title: 'Click Sent',
        description: `Sent click at (${nativeX}, ${nativeY})`,
      });
    } catch (err) {
      toast({
        title: 'Click Failed',
        description: 'Unable to send click event to desktop client',
        variant: 'destructive'
      });
    }
  }, [desktopStreamActive, toast]);

  // ============================================================================
  // LIFECYCLE EFFECTS
  // ============================================================================

  useEffect(() => {
    if (autoStart) {
      initializeFilesystemBridge();
    }

    return () => {
      if (filesystemBridgeRef.current) {
        filesystemBridgeRef.current.disconnect();
      }
    };
  }, [autoStart]); // eslint-disable-line react-hooks/exhaustive-deps

  // ============================================================================
  // RENDER COMPONENT
  // ============================================================================

  return (
    <div className={`live-desktop-interface ${className}`}>
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Monitor className="h-5 w-5" />
              Live Desktop Interface
            </CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant={interfaceStatus.websocketConnected ? "default" : "destructive"}>
                {interfaceStatus.websocketConnected ? (
                  <><Wifi className="h-3 w-3 mr-1" /> Connected</>
                ) : (
                  <><WifiOff className="h-3 w-3 mr-1" /> Disconnected</>
                )}
              </Badge>
              <Badge variant={interfaceStatus.filesystemBridgeActive ? "default" : "secondary"} data-testid="bridge-status-badge">
                <Database className="h-3 w-3 mr-1" />
                Bridge {interfaceStatus.filesystemBridgeActive ? 'Active' : 'Inactive'}
              </Badge>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="stream">Desktop Stream</TabsTrigger>
              <TabsTrigger value="triggers">Triggers</TabsTrigger>
              <TabsTrigger value="actions">Actions</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>

            {/* Overview Tab */}
            <TabsContent value="overview" className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-blue-500" />
                      <div>
                        <p className="text-sm font-medium">Active Triggers</p>
                        <p className="text-2xl font-bold">{interfaceStatus.triggersActive}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <Activity className="h-4 w-4 text-green-500" />
                      <div>
                        <p className="text-sm font-medium">Active Actions</p>
                        <p className="text-2xl font-bold">{interfaceStatus.actionsActive}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-purple-500" />
                      <div>
                        <p className="text-sm font-medium">Data Transfers</p>
                        <p className="text-2xl font-bold">{interfaceStatus.dataTransferCount}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-orange-500" />
                      <div>
                        <p className="text-sm font-medium">Last Transfer</p>
                        <p className="text-sm">
                          {interfaceStatus.lastDataTransfer 
                            ? interfaceStatus.lastDataTransfer.toLocaleTimeString()
                            : 'Never'
                          }
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="flex gap-2">
                <Button 
                  onClick={initializeFilesystemBridge}
                  disabled={isLoading || interfaceStatus.filesystemBridgeActive}
                  className="flex items-center gap-2"
                  data-testid="start-bridge-button"
                >
                  {isLoading ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {interfaceStatus.filesystemBridgeActive ? 'Bridge Active' : 'Start Bridge'}
                </Button>

                <Button 
                  variant="outline"
                  onClick={() => {
                    if (filesystemBridgeRef.current) {
                      filesystemBridgeRef.current.disconnect();
                      
                      // Clear desktop states
                      setDesktopConnected(false);
                      setDesktopStreamActive(false);
                      
                      // Clear canvas
                      if (canvasRef.current) {
                        const ctx = canvasRef.current.getContext('2d');
                        if (ctx) {
                          ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
                        }
                      }
                    }
                  }}
                  disabled={!interfaceStatus.filesystemBridgeActive}
                  className="flex items-center gap-2"
                  data-testid="stop-bridge-button"
                >
                  <Square className="h-4 w-4" />
                  Stop Bridge
                </Button>

                <Button 
                  variant="outline"
                  onClick={() => {
                    if (filesystemBridgeRef.current) {
                      // First disconnect if connected
                      filesystemBridgeRef.current.disconnect();
                      
                      // Clear states
                      setDesktopConnected(false);
                      setDesktopStreamActive(false);
                      
                      // Clear canvas
                      if (canvasRef.current) {
                        const ctx = canvasRef.current.getContext('2d');
                        if (ctx) {
                          ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
                        }
                      }
                      
                      // Wait a moment then reconnect
                      setTimeout(() => {
                        initializeFilesystemBridge();
                      }, 1000);
                    }
                  }}
                  disabled={isLoading}
                  className="flex items-center gap-2"
                >
                  <RefreshCw className="h-4 w-4" />
                  Reconnect
                </Button>
              </div>

              {/* Recent Data */}
              {recentData.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Recent Data Transfers</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2 max-h-40 overflow-y-auto">
                      {recentData.map((data, index) => (
                        <div key={index} className="flex items-center justify-between text-sm p-2 bg-muted rounded">
                          <span>{data.nodeType}</span>
                          <span className="text-muted-foreground">
                            {new Date(data.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            {/* Desktop Stream Tab */}
            <TabsContent value="stream" className="space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Stream Controls */}
                <div className="lg:col-span-1 space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Monitor className="h-4 w-4" />
                        Stream Controls
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex flex-col gap-2">
                        <Button 
                          onClick={startDesktopStream}
                          disabled={!interfaceStatus.filesystemBridgeActive || desktopStreamActive}
                          className="flex items-center gap-2"
                          data-testid="start-stream-button"
                        >
                          <Play className="h-4 w-4" />
                          {desktopStreamActive ? 'Stream Active' : 'Start Stream'}
                        </Button>

                        <Button 
                          variant="outline"
                          onClick={stopDesktopStream}
                          disabled={!desktopStreamActive}
                          className="flex items-center gap-2"
                          data-testid="stop-stream-button"
                        >
                          <Square className="h-4 w-4" />
                          Stop Stream
                        </Button>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="stream-quality">Stream Quality</Label>
                        <select
                          id="stream-quality"
                          value={streamQuality}
                          onChange={(e) => setStreamQuality(e.target.value as 'low' | 'medium' | 'high')}
                          className="w-full p-2 border rounded"
                          disabled={desktopStreamActive}
                        >
                          <option value="low">Low (Fast)</option>
                          <option value="medium">Medium</option>
                          <option value="high">High (Quality)</option>
                        </select>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="frame-rate">Frame Rate: {frameRate} FPS</Label>
                        <input
                          id="frame-rate"
                          type="range"
                          min="5"
                          max="60"
                          step="5"
                          value={frameRate}
                          onChange={(e) => setFrameRate(parseInt(e.target.value))}
                          className="w-full"
                          disabled={desktopStreamActive}
                        />
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm">Stream Status</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Desktop Client:</span>
                        <Badge variant={desktopConnected ? "default" : "destructive"} data-testid="desktop-client-status-badge">
                          {desktopConnected ? 'Connected' : 'Disconnected'}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Stream:</span>
                        <Badge variant={desktopStreamActive ? "default" : "secondary"} data-testid="stream-status-badge">
                          {desktopStreamActive ? 'Active' : 'Inactive'}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Quality:</span>
                        <span className="text-sm capitalize">{streamQuality}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Frame Rate:</span>
                        <span className="text-sm">{frameRate} FPS</span>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Stream Display */}
                <div className="lg:col-span-2">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Monitor className="h-4 w-4" />
                        Live Desktop Stream
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: '16/9' }}>
                        <canvas
                          ref={canvasRef}
                          className="w-full h-full object-contain"
                          style={{ maxHeight: '400px' }}
                          onClick={handleCanvasClick}
                          data-testid="live-desktop-canvas"
                        />
                        {!desktopStreamActive && (
                          <div className="absolute inset-0 flex items-center justify-center text-white">
                            <div className="text-center">
                              <Monitor className="h-12 w-12 mx-auto mb-2 opacity-50" />
                              <p className="text-sm opacity-75">
                                {!interfaceStatus.filesystemBridgeActive 
                                  ? 'Connect bridge first' 
                                  : !desktopConnected 
                                    ? 'Waiting for desktop client...' 
                                    : 'Click Start Stream to begin'
                                }
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </TabsContent>

            {/* Triggers Tab */}
            <TabsContent value="triggers" className="space-y-4">
              <div className="space-y-4">
                {activeTriggers.map((trigger, index) => (
                  <Card key={index}>
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-medium">{trigger.type} Trigger</h4>
                          <p className="text-sm text-muted-foreground">
                            Status: {trigger.enabled ? 'Active' : 'Inactive'}
                          </p>
                        </div>
                        <Button
                          onClick={() => activateTrigger(trigger)}
                          disabled={trigger.enabled}
                          size="sm"
                        >
                          {trigger.enabled ? 'Active' : 'Activate'}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>

            {/* Actions Tab */}
            <TabsContent value="actions" className="space-y-4">
              <div className="space-y-4">
                {activeActions.map((action, index) => (
                  <Card key={index}>
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-medium">{action.type} Action</h4>
                          <p className="text-sm text-muted-foreground">
                            Output to filesystem: {action.outputToFilesystem ? 'Yes' : 'No'}
                          </p>
                        </div>
                        <Button
                          onClick={() => executeAction(action)}
                          size="sm"
                        >
                          Execute
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>

            {/* Settings Tab */}
            <TabsContent value="settings" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">WebSocket Configuration</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="ws-url">WebSocket URL</Label>
                      <Input
                        id="ws-url"
                        value={wsConfig.url}
                        onChange={(e) => setWsConfig(prev => ({ ...prev, url: e.target.value }))}
                      />
                    </div>
                    <div>
                      <Label htmlFor="ws-port">Port</Label>
                      <Input
                        id="ws-port"
                        type="number"
                        value={wsConfig.port}
                        onChange={(e) => setWsConfig(prev => ({ ...prev, port: parseInt(e.target.value) }))}
                      />
                    </div>
                  </div>
                  
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="auto-reconnect"
                      checked={wsConfig.autoReconnect}
                      onCheckedChange={(checked) => setWsConfig(prev => ({ ...prev, autoReconnect: checked }))}
                    />
                    <Label htmlFor="auto-reconnect">Auto Reconnect</Label>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Filesystem Configuration</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label htmlFor="data-path">Data Directory</Label>
                    <Input
                      id="data-path"
                      value={fsConfig.baseDataPath}
                      onChange={(e) => setFsConfig(prev => ({ ...prev, baseDataPath: e.target.value }))}
                    />
                  </div>
                  
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="auto-cleanup"
                      checked={fsConfig.autoCleanup}
                      onCheckedChange={(checked) => setFsConfig(prev => ({ ...prev, autoCleanup: checked }))}
                    />
                    <Label htmlFor="auto-cleanup">Auto Cleanup Old Files</Label>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
};

export default LiveDesktopInterface;