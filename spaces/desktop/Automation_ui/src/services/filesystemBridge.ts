/**
 * ============================================================================
 * FILESYSTEM BRIDGE SERVICE
 * ============================================================================
 * 
 * Browser-compatible service for handling filesystem operations in the workflow system.
 * This service provides a bridge between the workflow interface and filesystem storage,
 * using browser-compatible APIs and event handling.
 * 
 * Features:
 * - WebSocket-based filesystem operations
 * - Browser-compatible event system
 * - File upload/download capabilities
 * - Directory management
 * - Real-time status monitoring
 * 
 * @author Autonomous Programmer Project
 * @version 1.0.0
 */

// Import centralized WebSocket configuration
import { WEBSOCKET_CONFIG, createFilesystemBridgeClient, createHandshakeMessage } from '@/config/websocketConfig';

// Browser-compatible event emitter implementation
type EventCallback = (...args: unknown[]) => void;

class SimpleEventEmitter {
  private events: { [key: string]: EventCallback[] } = {};

  on(event: string, callback: EventCallback) {
    if (!this.events[event]) {
      this.events[event] = [];
    }
    this.events[event].push(callback);
  }

  emit(event: string, ...args: unknown[]) {
    if (this.events[event]) {
      this.events[event].forEach(callback => callback(...args));
    }
  }

  off(event: string, callback: EventCallback) {
    if (this.events[event]) {
      this.events[event] = this.events[event].filter(cb => cb !== callback);
    }
  }
}

export interface FilesystemBridgeConfig {
  baseDataPath: string;
  websocketUrl: string;
  websocketPort: number;
  watchInterval: number;
  autoCleanup: boolean;
  maxFileAge: number;
}

export interface WorkflowData {
  id: string;
  timestamp: number;
  nodeId: string;
  nodeType: string;
  data: any;
  metadata: {
    executionId: string;
    workflowId: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    retryCount?: number;
  };
}

export interface ActionCommand {
  id: string;
  type: 'click' | 'type' | 'http' | 'ocr' | 'custom';
  timestamp: number;
  nodeId: string;
  parameters: any;
  executionTimeout: number;
  waitForExecution: boolean;
}

export interface ActionResult {
  commandId: string;
  nodeId: string;
  timestamp: number;
  status: 'success' | 'failed' | 'timeout';
  result: any;
  error?: string;
  executionTime: number;
}

export class FilesystemBridge extends SimpleEventEmitter {
  private config: FilesystemBridgeConfig;
  private websocket: WebSocket | null = null;
  private fileWatchers: Map<string, NodeJS.Timeout> = new Map();
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;

  constructor(config: FilesystemBridgeConfig) {
    super();
    this.config = config;
    this.initializeDirectories();
  }

  /**
   * Initialize required directories for filesystem operations
   */
  private async initializeDirectories(): Promise<void> {
    const directories = [
      this.config.baseDataPath,
      `${this.config.baseDataPath}/websocket`,
      `${this.config.baseDataPath}/desktop`,
      `${this.config.baseDataPath}/actions`,
      `${this.config.baseDataPath}/actions/click`,
      `${this.config.baseDataPath}/actions/type`,
      `${this.config.baseDataPath}/actions/http`,
      `${this.config.baseDataPath}/actions/ocr`,
      `${this.config.baseDataPath}/results`,
      `${this.config.baseDataPath}/temp`
    ];

    // In a real implementation, you would create these directories
    // For now, we'll emit events to indicate directory creation
    directories.forEach(dir => {
      this.emit('directoryCreated', { path: dir });
    });
  }

  /**
   * Connect to WebSocket service
   */
  public async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        // Use centralized WebSocket configuration
        const wsUrl = WEBSOCKET_CONFIG.BASE_URL;
        console.log(`Attempting to connect to WebSocket: ${wsUrl}`);
        
        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = () => {
          console.log(`WebSocket connected to ${wsUrl}`);
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.emit('connected', { url: wsUrl });
          this.startFileWatching();
          // Note: Handshake will be sent after receiving connection_established message
          this.processQueuedCommands(); // Process any queued commands
          resolve();
        };

        this.websocket.onmessage = (event) => {
          this.handleWebSocketMessage(event.data);
        };

        this.websocket.onclose = (event) => {
          console.log('WebSocket closed:', event.code, event.reason);
          
          this.isConnected = false;
          this.websocket = null;
          this.emit('disconnected', { code: event.code, reason: event.reason });
          
          // Only attempt reconnection for abnormal closures and if not manually closed
          if (event.code !== 1000 && event.code !== 1001 && this.reconnectAttempts < this.maxReconnectAttempts) {
            console.log('Connection lost, will attempt to reconnect...');
            this.attemptReconnect();
          }
        };

        this.websocket.onerror = (error) => {
          console.warn('WebSocket connection failed - service may not be available');
          // Don't emit error for connection failures to reduce console noise
          // this.emit('error', { error, context: 'websocket' });
          
          // Resolve with a "graceful failure" instead of rejecting
          this.isConnected = false;
          this.websocket = null;
          resolve(); // Allow the app to continue without WebSocket
        };

        // Connection timeout
        setTimeout(() => {
          if (this.websocket?.readyState !== WebSocket.OPEN) {
            this.websocket?.close();
            reject(new Error('WebSocket connection timeout'));
          }
        }, this.config.maxFileAge || 10000);

      } catch (error) {
        console.error('WebSocket connection setup failed:', error);
        this.emit('error', { error, context: 'connection' });
        reject(error);
      }
    });
  }

  /**
   * Send initial handshake to establish connection
   */
  private sendInitialHandshake(): void {
    if (this.isConnected && this.websocket) {
      console.log('About to send handshake - WebSocket state:', this.websocket.readyState);
      console.log('WebSocket ready states: CONNECTING=0, OPEN=1, CLOSING=2, CLOSED=3');
      
      const handshake = {
        type: 'handshake',
        data: {
          clientType: 'workflow_engine',
          version: '1.0.0',
          timestamp: Date.now(),
          capabilities: [
            'action_commands',
            'desktop_stream',
            'file_operations'
          ]
        }
      };
      
      try {
        this.websocket.send(JSON.stringify(handshake));
        console.log('Handshake sent to WebSocket server');
        console.log('WebSocket state after sending handshake:', this.websocket.readyState);
        
        // Check connection state after a short delay
        setTimeout(() => {
          if (this.websocket) {
            console.log('WebSocket state 10ms after handshake:', this.websocket.readyState);
          }
        }, 10);
        
        setTimeout(() => {
          if (this.websocket) {
            console.log('WebSocket state 100ms after handshake:', this.websocket.readyState);
          }
        }, 100);
      } catch (error) {
        console.error('Error sending handshake:', error);
      }
    } else {
      console.error('Cannot send handshake - WebSocket not connected or not available');
      console.log('isConnected:', this.isConnected);
      console.log('websocket:', this.websocket);
    }
  }

  /**
   * Disconnect from WebSocket service
   */
  public disconnect(): void {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
    this.stopFileWatching();
    this.isConnected = false;
  }

  /**
   * Attempt to reconnect to WebSocket service
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.pow(2, this.reconnectAttempts) * 1000; // Exponential backoff
      
      setTimeout(() => {
        this.emit('reconnecting', { attempt: this.reconnectAttempts });
        this.connect();
      }, delay);
    } else {
      this.emit('reconnectFailed', { maxAttempts: this.maxReconnectAttempts });
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleWebSocketMessage(data: string): void {
    try {
      const message = JSON.parse(data);
      
      switch (message.type) {
        case 'connection_established':
          this.handleConnectionEstablished(message);
          break;
        case 'handshake_ack':
          this.handleHandshakeAcknowledgment(message);
          break;
        case 'desktop_stream':
          this.writeDesktopData(message.data);
          break;
        case 'desktop_connected':
          this.emit('desktop_connected', message.data);
          break;
        case 'desktop_disconnected':
          this.emit('desktop_disconnected', message.data);
          break;
        case 'frame_data':
          this.emit('frame_data', message);
          break;
        case 'stream_status':
          this.emit('stream_status', message.data);
          break;
        case 'action_result':
          this.writeActionResult(message.data);
          break;
        case 'action_status':
          this.handleActionStatus(message.data);
          break;
        case 'system_status':
          this.writeSystemStatus(message.data);
          break;
        case 'error':
          this.handleServerError(message.data);
          break;
        case 'ping':
          this.sendPong();
          break;
        case 'pong':
          this.handlePong(message);
          break;
        default:
          console.warn('Unknown message type:', message.type);
          this.emit('unknownMessage', message);
      }
    } catch (error) {
      console.error('Error parsing or handling WebSocket message:', error);
      console.error('Raw message data:', data);
      this.emit('error', { error, context: 'message_parsing' });
    }
  }

  /**
   * Handle connection established message
   */
  private handleConnectionEstablished(message: any): void {
    this.isConnected = true;
    
    // Emit connected event with WebSocket URL data
    const connectionData = {
      url: WEBSOCKET_CONFIG.BASE_URL,
      serverInfo: message.serverInfo || {},
      timestamp: new Date().toISOString()
    };
    
    this.emit('connected', connectionData);
    
    // Send handshake
    this.sendHandshake();
  }

  /**
   * Send handshake to server
   */
  private sendHandshake(): void {
    if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
      console.error('Cannot send handshake: WebSocket not connected');
      return;
    }

    // Use centralized handshake message creation
    const handshake = createHandshakeMessage(
      WEBSOCKET_CONFIG.CLIENT_TYPES.FILESYSTEM_BRIDGE,
      `filesystem_bridge_${Date.now()}`,
      [
        WEBSOCKET_CONFIG.CAPABILITIES.FILE_OPERATIONS,
        WEBSOCKET_CONFIG.CAPABILITIES.ACTION_COMMANDS,
        WEBSOCKET_CONFIG.CAPABILITIES.WORKFLOW_DATA
      ],
      {
        version: '1.0.0',
        timestamp: Date.now()
      }
    );

    this.websocket.send(JSON.stringify(handshake));
  }

  /**
   * Handle pong response from server
   */
  private handlePong(message: any): void {
    console.log('Received pong from server');
    this.emit('pong', message);
  }

  /**
   * Test WebSocket connection with minimal setup
   */
  public testConnection(): Promise<void> {
    return new Promise((resolve, reject) => {
      console.log('Testing WebSocket connection...');
      // Use centralized WebSocket configuration for testing
      const testWs = new WebSocket(WEBSOCKET_CONFIG.BASE_URL);
      
      testWs.onopen = () => {
        console.log('Test WebSocket connected successfully');
        testWs.close();
        resolve();
      };
      
      testWs.onclose = (event) => {
        console.log('Test WebSocket closed:', event.code, event.reason);
      };
      
      testWs.onerror = (error) => {
        console.error('Test WebSocket error:', error);
        reject(error);
      };
      
      setTimeout(() => {
        if (testWs.readyState !== WebSocket.OPEN) {
          testWs.close();
          reject(new Error('Test connection timeout'));
        }
      }, 5000);
    });
  }
  private handleHandshakeAcknowledgment(message: any): void {
    this.emit('handshakeComplete', message);
  }

  /**
   * Handle action status updates
   */
  private handleActionStatus(data: any): void {
    console.log('Action status update:', data);
    this.emit('actionStatus', data);
  }

  /**
   * Handle server errors
   */
  private handleServerError(data: any): void {
    console.error('Server error:', data);
    this.emit('serverError', data);
  }

  /**
   * Send pong response to ping
   */
  private sendPong(): void {
    if (this.isConnected && this.websocket) {
      this.websocket.send(JSON.stringify({ type: 'pong', timestamp: Date.now() }));
    }
  }

  /**
   * Write action command to filesystem for execution
   */
  public async writeActionCommand(command: ActionCommand): Promise<void> {
    const filePath = `${this.config.baseDataPath}/actions/${command.type}/${command.id}.json`;
    const data: WorkflowData = {
      id: command.id,
      timestamp: Date.now(),
      nodeId: command.nodeId,
      nodeType: command.type,
      data: command,
      metadata: {
        executionId: `exec_${Date.now()}`,
        workflowId: `workflow_${command.nodeId}`,
        status: 'pending'
      }
    };

    console.log(`Writing action command: ${command.type} (${command.id})`);
    
    // Emit local event for monitoring
    this.emit('fileWritten', { path: filePath, data });
    this.emit('actionQueued', { commandId: command.id, nodeId: command.nodeId, type: command.type });
    
    // Send via WebSocket if connected
    if (this.isConnected && this.websocket) {
      const message = {
        type: 'action_command',
        data: data,
        timestamp: Date.now()
      };
      
      this.websocket.send(JSON.stringify(message));
      console.log(`Action command sent via WebSocket: ${command.id}`);
    } else {
      console.warn(`WebSocket not connected - action command queued locally: ${command.id}`);
      // Queue command for later transmission
      this.queueCommand(command);
    }
  }

  /**
   * Queue commands for later transmission when connection is restored
   */
  private queuedCommands: ActionCommand[] = [];
  
  private queueCommand(command: ActionCommand): void {
    this.queuedCommands.push(command);
    this.emit('commandQueued', { commandId: command.id, queueLength: this.queuedCommands.length });
  }

  /**
   * Process queued commands when connection is restored
   */
  private async processQueuedCommands(): Promise<void> {
    if (this.queuedCommands.length === 0) return;
    
    console.log(`Processing ${this.queuedCommands.length} queued commands`);
    
    const commands = [...this.queuedCommands];
    this.queuedCommands = [];
    
    for (const command of commands) {
      try {
        await this.writeActionCommand(command);
      } catch (error) {
        console.error(`Failed to process queued command ${command.id}:`, error);
        this.queueCommand(command); // Re-queue failed command
      }
    }
  }

  /**
   * Write desktop stream data to filesystem
   */
  private async writeDesktopData(data: any): Promise<void> {
    const filePath = `${this.config.baseDataPath}/desktop/stream_${Date.now()}.json`;
    const workflowData: WorkflowData = {
      id: `desktop_${Date.now()}`,
      timestamp: Date.now(),
      nodeId: 'live_desktop',
      nodeType: 'desktop_stream',
      data: data,
      metadata: {
        executionId: `exec_${Date.now()}`,
        workflowId: 'desktop_interface',
        status: 'completed'
      }
    };

    this.emit('fileWritten', { path: filePath, data: workflowData });
  }

  /**
   * Write action result to filesystem
   */
  private async writeActionResult(result: ActionResult): Promise<void> {
    const filePath = `${this.config.baseDataPath}/results/${result.commandId}_result.json`;
    const workflowData: WorkflowData = {
      id: result.commandId,
      timestamp: Date.now(),
      nodeId: result.nodeId,
      nodeType: 'action_result',
      data: result,
      metadata: {
        executionId: `exec_${Date.now()}`,
        workflowId: `workflow_${result.nodeId}`,
        status: result.status === 'success' ? 'completed' : 'failed'
      }
    };

    this.emit('fileWritten', { path: filePath, data: workflowData });
    this.emit('actionResult', result);
  }

  /**
   * Write system status to filesystem
   */
  private async writeSystemStatus(status: any): Promise<void> {
    const filePath = `${this.config.baseDataPath}/websocket/status.json`;
    const workflowData: WorkflowData = {
      id: `status_${Date.now()}`,
      timestamp: Date.now(),
      nodeId: 'websocket_config',
      nodeType: 'system_status',
      data: status,
      metadata: {
        executionId: `exec_${Date.now()}`,
        workflowId: 'system_monitoring',
        status: 'completed'
      }
    };

    this.emit('fileWritten', { path: filePath, data: workflowData });
  }

  /**
   * Read workflow data from filesystem
   */
  public async readWorkflowData(nodeId: string, dataType?: string): Promise<WorkflowData[]> {
    // In a real implementation, you would read from the actual filesystem
    // For now, we'll emit events and return mock data
    const mockData: WorkflowData[] = [{
      id: `${nodeId}_${Date.now()}`,
      timestamp: Date.now(),
      nodeId: nodeId,
      nodeType: dataType || 'unknown',
      data: { mock: true, nodeId },
      metadata: {
        executionId: `exec_${Date.now()}`,
        workflowId: `workflow_${nodeId}`,
        status: 'completed'
      }
    }];

    this.emit('dataRead', { nodeId, dataType, results: mockData });
    return mockData;
  }

  /**
   * Start file watching for changes
   */
  private startFileWatching(): void {
    const watchPaths = [
      `${this.config.baseDataPath}/actions`,
      `${this.config.baseDataPath}/results`,
      `${this.config.baseDataPath}/desktop`
    ];

    watchPaths.forEach(path => {
      const watcherId = setInterval(() => {
        this.checkForFileChanges(path);
      }, this.config.watchInterval);

      this.fileWatchers.set(path, watcherId);
    });

    this.emit('fileWatchingStarted', { paths: watchPaths });
  }

  /**
   * Stop file watching
   */
  private stopFileWatching(): void {
    this.fileWatchers.forEach((watcherId, path) => {
      clearInterval(watcherId);
    });
    this.fileWatchers.clear();
    this.emit('fileWatchingStopped');
  }

  /**
   * Check for file changes in a directory
   */
  private checkForFileChanges(path: string): void {
    // In a real implementation, you would check the actual filesystem
    // For now, we'll emit periodic events to simulate file changes
    this.emit('fileChanged', { 
      path, 
      timestamp: Date.now(),
      changeType: 'modified'
    });
  }

  /**
   * Cleanup old files based on age
   */
  public async cleanupOldFiles(): Promise<void> {
    if (!this.config.autoCleanup) return;

    const cutoffTime = Date.now() - this.config.maxFileAge;
    
    // In a real implementation, you would scan and delete old files
    // For now, we'll emit cleanup events
    this.emit('filesCleanedUp', { 
      cutoffTime, 
      maxAge: this.config.maxFileAge 
    });
  }

  /**
   * Get connection status
   */
  public getStatus(): { connected: boolean; reconnectAttempts: number } {
    return {
      connected: this.isConnected,
      reconnectAttempts: this.reconnectAttempts
    };
  }

  /**
   * Send data via WebSocket
   */
  public sendWebSocketData(type: string, data: any): void {
    if (this.isConnected && this.websocket) {
      this.websocket.send(JSON.stringify({ type, data }));
    } else {
      this.emit('error', { 
        error: 'WebSocket not connected', 
        context: 'send_data' 
      });
    }
  }
}

// Export default configuration
export const defaultFilesystemBridgeConfig: FilesystemBridgeConfig = {
  baseDataPath: './workflow-data',
  websocketUrl: WEBSOCKET_CONFIG.BASE_URL,
  websocketPort: 8007,
  watchInterval: 1000,
  autoCleanup: true,
  maxFileAge: 3600000 // 1 hour
};