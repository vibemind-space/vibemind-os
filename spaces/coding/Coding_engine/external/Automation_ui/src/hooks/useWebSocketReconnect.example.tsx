/**
 * Usage Examples for useWebSocketReconnect Hook
 *
 * This file demonstrates how to use the WebSocket reconnection hook
 * with automatic reconnection, exponential backoff, and connection status UI
 */

import React, { useState, useCallback } from 'react';
import { useWebSocketReconnect } from './useWebSocketReconnect';
import { createMultiDesktopClientUrl } from '@/config/websocketConfig';
import { ConnectionStatusIndicator } from '@/components/ui/connection-status';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// ============================================================================
// EXAMPLE 1: Basic Usage with Multi-Desktop Stream
// ============================================================================

export const BasicWebSocketExample: React.FC = () => {
  const [messages, setMessages] = useState<any[]>([]);

  // Create WebSocket configuration
  const { url, clientId, handshakeMessage } = createMultiDesktopClientUrl('example_component');

  // Use the reconnection hook
  const {
    websocket,
    status,
    reconnectAttempt,
    isConnected,
    lastError,
    sendMessage,
    reconnect,
    disconnect,
  } = useWebSocketReconnect({
    url,
    handshakeMessage,

    // Connection established
    onOpen: (ws) => {
      console.log('✅ Connected!', { clientId });

      // Request desktop clients after connection
      setTimeout(() => {
        sendMessage({
          type: 'get_desktop_clients',
          timestamp: new Date().toISOString(),
        });
      }, 500);
    },

    // Message received
    onMessage: (event, ws) => {
      const message = JSON.parse(event.data);
      console.log('📥 Message received:', message);
      setMessages(prev => [...prev, message]);

      // Handle specific message types
      switch (message.type) {
        case 'desktop_clients_list':
          console.log('Available desktop clients:', message.clients);
          break;
        case 'frame_data':
          console.log('Frame received from:', message.desktopClientId);
          break;
      }
    },

    // Connection closed
    onClose: (event) => {
      console.log('🔌 Connection closed:', event.reason);
    },

    // Connection error
    onError: (event) => {
      console.error('❌ WebSocket error:', event);
    },
  });

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle>WebSocket Reconnection Example</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Connection Status */}
        <ConnectionStatusIndicator
          status={status}
          reconnectAttempt={reconnectAttempt}
          lastError={lastError}
          onReconnect={reconnect}
        />

        {/* Manual Controls */}
        <div className="flex gap-2">
          <Button
            onClick={reconnect}
            disabled={status === 'connecting' || status === 'connected'}
          >
            Connect
          </Button>
          <Button
            onClick={disconnect}
            disabled={status === 'disconnected'}
            variant="outline"
          >
            Disconnect
          </Button>
          <Button
            onClick={() => sendMessage({ type: 'ping', timestamp: new Date().toISOString() })}
            disabled={!isConnected}
            variant="outline"
          >
            Send Ping
          </Button>
        </div>

        {/* Message Log */}
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Recent Messages ({messages.length})</h3>
          <div className="max-h-40 overflow-y-auto rounded-md border p-2 text-xs font-mono">
            {messages.slice(-10).map((msg, i) => (
              <div key={i} className="mb-1">
                {JSON.stringify(msg, null, 2)}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// ============================================================================
// EXAMPLE 2: Advanced Usage with Custom Settings
// ============================================================================

export const AdvancedWebSocketExample: React.FC = () => {
  const { url, handshakeMessage } = createMultiDesktopClientUrl('advanced_component');
  const [desktopClients, setDesktopClients] = useState<any[]>([]);

  const {
    status,
    reconnectAttempt,
    lastError,
    sendMessage,
    reconnect,
    isConnected,
  } = useWebSocketReconnect({
    url,
    handshakeMessage,

    // Custom reconnection settings
    maxReconnectAttempts: 15,        // Try more times
    reconnectDelay: 3000,            // Start with 3 second delay
    exponentialBackoff: true,        // Enable exponential backoff
    maxReconnectDelay: 120000,       // Max 2 minutes between attempts

    onOpen: (ws) => {
      console.log('Advanced WebSocket connected');
      sendMessage({
        type: 'get_desktop_clients',
        timestamp: new Date().toISOString(),
      });
    },

    onMessage: (event) => {
      const message = JSON.parse(event.data);

      if (message.type === 'desktop_clients_list') {
        setDesktopClients(message.clients || []);

        // Auto-start streaming for all connected clients
        message.clients?.forEach((client: any) => {
          if (client.connected) {
            client.monitors?.forEach((monitor: any) => {
              sendMessage({
                type: 'start_stream',
                desktopClientId: client.id,
                monitorId: monitor.id || 'monitor_0',
                timestamp: new Date().toISOString(),
              });
            });
          }
        });
      }
    },
  });

  const startStreaming = useCallback((clientId: string, monitorId: string) => {
    sendMessage({
      type: 'start_stream',
      desktopClientId: clientId,
      monitorId: monitorId,
      timestamp: new Date().toISOString(),
    });
  }, [sendMessage]);

  const stopStreaming = useCallback((clientId: string, monitorId: string) => {
    sendMessage({
      type: 'stop_stream',
      desktopClientId: clientId,
      monitorId: monitorId,
      timestamp: new Date().toISOString(),
    });
  }, [sendMessage]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Advanced WebSocket Example</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ConnectionStatusIndicator
          status={status}
          reconnectAttempt={reconnectAttempt}
          lastError={lastError}
          onReconnect={reconnect}
        />

        <div>
          <h3 className="text-sm font-medium mb-2">
            Desktop Clients ({desktopClients.length})
          </h3>
          {desktopClients.map((client) => (
            <div key={client.id} className="border rounded p-2 mb-2">
              <div className="flex items-center justify-between">
                <span className="font-medium">{client.id}</span>
                <span className="text-xs text-muted-foreground">
                  {client.connected ? '🟢 Connected' : '🔴 Disconnected'}
                </span>
              </div>
              {client.monitors?.map((monitor: any) => (
                <div key={monitor.id} className="mt-2 flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => startStreaming(client.id, monitor.id)}
                    disabled={!isConnected}
                  >
                    Start {monitor.id}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => stopStreaming(client.id, monitor.id)}
                    disabled={!isConnected}
                  >
                    Stop
                  </Button>
                </div>
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

// ============================================================================
// EXAMPLE 3: Minimal Usage with Just Connection Status
// ============================================================================

export const MinimalWebSocketExample: React.FC = () => {
  const { url, handshakeMessage } = createMultiDesktopClientUrl('minimal_component');

  const { status, reconnectAttempt, lastError, reconnect } = useWebSocketReconnect({
    url,
    handshakeMessage,
    onOpen: () => console.log('Connected'),
    onMessage: (event) => console.log('Message:', event.data),
  });

  return (
    <div className="p-4">
      <ConnectionStatusIndicator
        status={status}
        reconnectAttempt={reconnectAttempt}
        lastError={lastError}
        onReconnect={reconnect}
        compact
      />
    </div>
  );
};

// ============================================================================
// EXAMPLE 4: Migrating from Manual WebSocket Management
// ============================================================================

// BEFORE (manual management):
/*
const wsRef = useRef<WebSocket | null>(null);
const [isConnected, setIsConnected] = useState(false);

const connectWebSocket = () => {
  const { websocket, handshakeMessage } = createMultiDesktopClient('component');
  wsRef.current = websocket;

  websocket.onopen = () => {
    setIsConnected(true);
    sendWebSocketMessage(websocket, handshakeMessage);
  };

  websocket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    // Handle message
  };

  websocket.onclose = () => {
    setIsConnected(false);
    // Manual reconnection logic needed here
  };
};

useEffect(() => {
  connectWebSocket();
  return () => {
    wsRef.current?.close();
  };
}, []);
*/

// AFTER (using reconnection hook):
export const MigratedWebSocketExample: React.FC = () => {
  const { url, handshakeMessage } = createMultiDesktopClientUrl('migrated_component');

  const { websocket, status, isConnected, sendMessage } = useWebSocketReconnect({
    url,
    handshakeMessage,
    onOpen: () => {
      // Automatically handles handshake
      console.log('Connected!');
    },
    onMessage: (event) => {
      const message = JSON.parse(event.data);
      // Handle message (same as before)
    },
    // Automatic reconnection - no manual logic needed!
  });

  return (
    <div>
      {/* Your existing component UI */}
      <p>Connection status: {isConnected ? 'Connected' : 'Disconnected'}</p>
      <Button onClick={() => sendMessage({ type: 'ping' })} disabled={!isConnected}>
        Ping
      </Button>
    </div>
  );
};
