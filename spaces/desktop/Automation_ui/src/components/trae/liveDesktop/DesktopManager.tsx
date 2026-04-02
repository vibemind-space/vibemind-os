import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Monitor, Plus, Play, Square, Trash2, Settings } from 'lucide-react';
import { createDesktopManagerClient, sendWebSocketMessage } from '@/config/websocketConfig';

interface DesktopInstance {
  id: string;
  name: string;
  screen1: {
    clientId: string;
    connected: boolean;
    streaming: boolean;
    thumbnail?: string;
  };
  screen2: {
    clientId: string;
    connected: boolean;
    streaming: boolean;
    thumbnail?: string;
  };
  created: string;
  status: 'initializing' | 'connected' | 'streaming' | 'error';
}

interface DesktopManagerProps {
  onDesktopCreated?: (desktop: DesktopInstance) => void;
  onDesktopRemoved?: (desktopId: string) => void;
  onDesktopStatusChange?: (desktopId: string, status: string) => void;
}

export const DesktopManager: React.FC<DesktopManagerProps> = ({
  onDesktopCreated,
  onDesktopRemoved,
  onDesktopStatusChange
}) => {
  const [desktops, setDesktops] = useState<DesktopInstance[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  // WebSocket connection management
  useEffect(() => {
    connectToServer();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectToServer = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const { clientId, websocket, handshakeMessage } = createDesktopManagerClient();
    wsRef.current = websocket;

    websocket.onopen = () => {
      console.log('Desktop Manager connected to WebSocket server');
      setIsConnected(true);
      
      // Register as desktop manager using standardized handshake
      sendWebSocketMessage(websocket, handshakeMessage);
    };

    websocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        handleServerMessage(message);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    websocket.onclose = () => {
      console.log('Desktop Manager WebSocket disconnected');
      setIsConnected(false);
    };

    websocket.onerror = (error) => {
      console.error('Desktop Manager WebSocket error:', error);
    };
  };

  const handleServerMessage = (message: any) => {
    switch (message.type) {
      case 'desktop_instance_status':
        console.log('Desktop instance status update:', message);
        if (message.desktopId) {
          updateDesktopStatus(message.desktopId, message.status);
        }
        break;
        
      case 'desktop_connected':
        console.log('Desktop client connected:', message);
        if (message.desktopId && message.screenId) {
          updateClientConnection(message.desktopId, message.screenId, true);
        }
        break;
        
      case 'desktop_disconnected':
        console.log('Desktop client disconnected:', message);
        if (message.desktopId && message.screenId) {
          updateClientConnection(message.desktopId, message.screenId, false);
        }
        break;
        
      case 'frame_data':
        // Update thumbnails for desktop instances
        if (message.routingInfo?.desktopId && message.routingInfo?.screenId) {
          updateDesktopThumbnail(
            message.routingInfo.desktopId,
            message.routingInfo.screenId,
            `data:image/jpeg;base64,${message.frameData}`
          );
        }
        break;
        
      case 'desktop_instances_list':
        console.log('Received desktop instances list:', message.instances);
        // Sync with server state if needed
        break;
        
      case 'connection_established':
        console.log('Connection established:', message);
        break;
        
      case 'desktop_stream_status':
            console.log('Desktop stream status:', message);
            break;
            
          case 'ping':
            // Handle ping messages silently - these are keep-alive messages
            break;
            
          default:
            console.log('Unhandled message type:', message.type);
    }
  };

  const updateDesktopStatus = (desktopId: string, status: DesktopInstance['status']) => {
    setDesktops(prev => prev.map(desktop => 
      desktop.id === desktopId 
        ? { ...desktop, status }
        : desktop
    ));
    onDesktopStatusChange?.(desktopId, status);
  };

  const updateClientConnection = (desktopId: string, screenId: string, connected: boolean) => {
    setDesktops(prev => prev.map(desktop => {
      if (desktop.id === desktopId) {
        if (screenId === 'screen1') {
          return { ...desktop, screen1: { ...desktop.screen1, connected } };
        } else if (screenId === 'screen2') {
          return { ...desktop, screen2: { ...desktop.screen2, connected } };
        }
      }
      return desktop;
    }));
  };

  const updateDesktopThumbnail = (desktopId: string, screenId: string, thumbnail: string) => {
    setDesktops(prev => prev.map(desktop => {
      if (desktop.id === desktopId) {
        if (screenId === 'screen1') {
          return { ...desktop, screen1: { ...desktop.screen1, thumbnail } };
        } else if (screenId === 'screen2') {
          return { ...desktop, screen2: { ...desktop.screen2, thumbnail } };
        }
      }
      return desktop;
    }));
  };

  const createNewDesktop = async () => {
    if (!isConnected || isCreating) return;

    setIsCreating(true);
    
    try {
      const desktopId = `desktop_${Date.now()}`;
      const newDesktop: DesktopInstance = {
        id: desktopId,
        name: `Desktop ${desktops.length + 1}`,
        screen1: {
          clientId: `${desktopId}_screen1`,
          connected: false,
          streaming: false
        },
        screen2: {
          clientId: `${desktopId}_screen2`,
          connected: false,
          streaming: false
        },
        created: new Date().toISOString(),
        status: 'initializing'
      };

      // Add to local state
      setDesktops(prev => [...prev, newDesktop]);
      onDesktopCreated?.(newDesktop);

      // Request server to spawn new desktop instances
      if (wsRef.current) {
        wsRef.current.send(JSON.stringify({
          type: 'create_desktop_instance',
          desktopId: desktopId,
          config: {
            screens: [
              { screenId: 'screen1', monitorIndex: 0, name: 'Screen 1' },
              { screenId: 'screen2', monitorIndex: 1, name: 'Screen 2' }
            ],
            captureConfig: {
              fps: 10,
              quality: 80,
              scale: 1.0,
              format: 'jpeg'
            }
          },
          timestamp: new Date().toISOString()
        }));
      }

      console.log(`Created new desktop instance: ${desktopId}`);
      
    } catch (error) {
      console.error('Error creating desktop:', error);
    } finally {
      setIsCreating(false);
    }
  };

  const removeDesktop = (desktopId: string) => {
    // Stop streaming for this desktop
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({
        type: 'remove_desktop_instance',
        desktopId: desktopId,
        timestamp: new Date().toISOString()
      }));
    }

    // Remove from local state
    setDesktops(prev => prev.filter(desktop => desktop.id !== desktopId));
    onDesktopRemoved?.(desktopId);
  };

  const toggleDesktopStreaming = (desktopId: string) => {
    const desktop = desktops.find(d => d.id === desktopId);
    if (!desktop || !wsRef.current) return;

    const isStreaming = desktop.status === 'streaming';
    
    wsRef.current.send(JSON.stringify({
      type: isStreaming ? 'stop_desktop_instance' : 'start_desktop_instance',
      desktopId: desktopId,
      timestamp: new Date().toISOString()
    }));

    updateDesktopStatus(desktopId, isStreaming ? 'connected' : 'streaming');
  };

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="flex items-center space-x-2">
          <Monitor className="w-6 h-6" />
          <span>Desktop Manager</span>
        </CardTitle>
        <CardDescription>
          Create and manage dynamic desktop instances with dual screen capture
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Create New Desktop Button */}
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-lg font-medium">Desktop Instances ({desktops.length})</h3>
              <p className="text-sm text-muted-foreground">
                Each desktop captures Screen 1 and Screen 2 simultaneously
              </p>
            </div>
            <Button 
              onClick={createNewDesktop} 
              disabled={!isConnected || isCreating}
              className="flex items-center space-x-2"
            >
              <Plus className="w-4 h-4" />
              <span>{isCreating ? 'Creating...' : 'New Desktop'}</span>
            </Button>
          </div>

          {/* Desktop Instances Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {desktops.map((desktop) => (
              <Card key={desktop.id} className="overflow-hidden">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{desktop.name}</CardTitle>
                    <div className="flex items-center space-x-1">
                      <div className={`w-2 h-2 rounded-full ${
                        desktop.status === 'streaming' ? 'bg-green-500' :
                        desktop.status === 'connected' ? 'bg-blue-500' :
                        desktop.status === 'initializing' ? 'bg-yellow-500' :
                        'bg-red-500'
                      }`} />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeDesktop(desktop.id)}
                        className="h-6 w-6 p-0"
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                  <CardDescription className="text-xs">
                    Created: {new Date(desktop.created).toLocaleTimeString()}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0">
                  {/* Screen Previews */}
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    {/* Screen 1 */}
                    <div className="relative">
                      <div className="aspect-video bg-muted rounded overflow-hidden">
                        {desktop.screen1.thumbnail ? (
                          <img 
                            src={desktop.screen1.thumbnail} 
                            alt="Screen 1"
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Monitor className="w-6 h-6 text-muted-foreground" />
                          </div>
                        )}
                      </div>
                      <div className="absolute top-1 left-1 text-xs bg-black/50 text-white px-1 rounded">
                        Screen 1
                      </div>
                      <div className={`absolute top-1 right-1 w-2 h-2 rounded-full ${
                        desktop.screen1.connected ? 'bg-green-500' : 'bg-red-500'
                      }`} />
                    </div>

                    {/* Screen 2 */}
                    <div className="relative">
                      <div className="aspect-video bg-muted rounded overflow-hidden">
                        {desktop.screen2.thumbnail ? (
                          <img 
                            src={desktop.screen2.thumbnail} 
                            alt="Screen 2"
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Monitor className="w-6 h-6 text-muted-foreground" />
                          </div>
                        )}
                      </div>
                      <div className="absolute top-1 left-1 text-xs bg-black/50 text-white px-1 rounded">
                        Screen 2
                      </div>
                      <div className={`absolute top-1 right-1 w-2 h-2 rounded-full ${
                        desktop.screen2.connected ? 'bg-green-500' : 'bg-red-500'
                      }`} />
                    </div>
                  </div>

                  {/* Controls */}
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-muted-foreground capitalize">
                      {desktop.status}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleDesktopStreaming(desktop.id)}
                      disabled={desktop.status === 'initializing'}
                      className="h-7 px-2"
                    >
                      {desktop.status === 'streaming' ? (
                        <>
                          <Square className="w-3 h-3 mr-1" />
                          Stop
                        </>
                      ) : (
                        <>
                          <Play className="w-3 h-3 mr-1" />
                          Start
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Connection Status */}
          <div className="flex items-center justify-between pt-4 border-t">
            <div className="flex items-center space-x-2">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-sm">
                {isConnected ? 'Connected to Server' : 'Disconnected'}
              </span>
            </div>
            <div className="text-sm text-muted-foreground">
              Total Screens: {desktops.length * 2}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};