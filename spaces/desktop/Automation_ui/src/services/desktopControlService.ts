/**
 * Desktop Control Service für Python-Script-Steuerung
 * 
 * Verwaltet die Kommunikation mit Desktop-Clients und Python-Scripten
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import { permissionService } from './permissionService';
// Import centralized WebSocket config utilities for consistent URLs and handshakes
import { WEBSOCKET_CONFIG, createHandshakeMessage } from '@/config/websocketConfig';

// ============================================================================
// INTERFACES & TYPES
// ============================================================================

export interface DesktopClientInfo {
  id: string;
  type: 'desktop' | 'dual_screen' | 'multi_monitor';
  connected: boolean;
  streaming: boolean;
  capabilities: string[];
  lastSeen: string;
  permissions: {
    granted: boolean;
    scope: string[];
    expiresAt?: string;
  };
}

export interface StreamConfig {
  fps: number;
  quality: number;
  scale: number;
  format: 'jpeg' | 'png' | 'webp';
  dualScreen?: boolean;
  monitors?: number[];
}

export interface ControlCommand {
  type: 'start_stream' | 'stop_stream' | 'restart_client' | 'update_config';
  clientId: string;
  config?: StreamConfig;
  timestamp: string;
}

// ============================================================================
// DESKTOP CONTROL SERVICE CLASS
// ============================================================================

class DesktopControlService {
  private websocket: WebSocket | null = null;
  private clients: Map<string, DesktopClientInfo> = new Map();
  private listeners: Map<string, (clients: Map<string, DesktopClientInfo>) => void> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  // ============================================================================
  // WEBSOCKET CONNECTION MANAGEMENT
  // ============================================================================

  /**
   * Initialisiert WebSocket-Verbindung
   */
  async initializeWebSocket(url: string = WEBSOCKET_CONFIG.BASE_URL): Promise<boolean> {
    try {
      console.log('🔌 Initialisiere Desktop Control WebSocket-Verbindung...');
      
      this.websocket = new WebSocket(url);
      
      this.websocket.onopen = () => {
        console.log('✅ Desktop Control WebSocket-Verbindung hergestellt');
        this.reconnectAttempts = 0;
        
        // Sende Handshake
        this.sendHandshake();
      };

      this.websocket.onmessage = (event) => {
        this.handleWebSocketMessage(event);
      };

      this.websocket.onclose = () => {
        console.log('🔌 Desktop Control WebSocket-Verbindung geschlossen');
        this.handleReconnect();
      };

      this.websocket.onerror = (error) => {
        console.error('❌ Desktop Control WebSocket-Fehler:', error);
      };

      return true;
    } catch (error) {
      console.error('❌ Fehler beim Initialisieren der WebSocket-Verbindung:', error);
      return false;
    }
  }

  /**
   * Sendet Handshake-Nachricht
   */
  private sendHandshake(): void {
    if (this.websocket?.readyState === WebSocket.OPEN) {
      // Build standardized handshake via centralized utility
      const handshake = createHandshakeMessage(
        WEBSOCKET_CONFIG.CLIENT_TYPES.WEB,
        `desktop_control_${Date.now()}`,
        ['desktop_control', 'stream_management', 'permission_handling'],
        { timestamp: new Date().toISOString() }
      );
      
      this.websocket.send(JSON.stringify(handshake));
      console.log('📤 Desktop Control Handshake gesendet');
    }
  }

  /**
   * Behandelt WebSocket-Nachrichten
   */
  private handleWebSocketMessage(event: MessageEvent): void {
    try {
      const message = JSON.parse(event.data);
      
      switch (message.type) {
        case 'handshake_ack':
          console.log('✅ Desktop Control Handshake bestätigt');
          break;
          
        case 'desktop_connected':
        case 'dual_screen_connected':
        case 'multi_monitor_desktop_connected':
          this.handleClientConnected(message);
          break;
          
        case 'desktop_disconnected':
          this.handleClientDisconnected(message);
          break;
          
        case 'desktop_stream_status':
        case 'stream_status':
          this.handleStreamStatus(message);
          break;
          
        case 'frame_data':
        case 'dual_screen_frame':
          // Frame-Daten werden von anderen Komponenten behandelt
          break;
          
        default:
          console.log('🔍 Unbekannte Desktop Control Nachricht:', message.type);
      }
    } catch (error) {
      console.error('❌ Fehler beim Verarbeiten der WebSocket-Nachricht:', error);
    }
  }

  /**
   * Behandelt Client-Verbindungen
   */
  private handleClientConnected(message: any): void {
    const clientId = message.desktopClientId || message.clientId;
    
    if (!clientId) return;

    const clientInfo: DesktopClientInfo = {
      id: clientId,
      type: this.getClientType(message),
      connected: true,
      streaming: false,
      capabilities: message.capabilities || [],
      lastSeen: new Date().toISOString(),
      permissions: {
        granted: false,
        scope: []
      }
    };

    this.clients.set(clientId, clientInfo);
    this.notifyListeners();
    
    console.log(`🖥️ Desktop-Client verbunden: ${clientId} (${clientInfo.type})`);
  }

  /**
   * Behandelt Client-Trennungen
   */
  private handleClientDisconnected(message: any): void {
    const clientId = message.desktopClientId || message.clientId;
    
    if (clientId && this.clients.has(clientId)) {
      const client = this.clients.get(clientId)!;
      client.connected = false;
      client.streaming = false;
      
      this.clients.set(clientId, client);
      this.notifyListeners();
      
      console.log(`🔌 Desktop-Client getrennt: ${clientId}`);
    }
  }

  /**
   * Behandelt Stream-Status-Updates
   */
  private handleStreamStatus(message: any): void {
    const clientId = message.desktopClientId || message.clientId;
    
    if (clientId && this.clients.has(clientId)) {
      const client = this.clients.get(clientId)!;
      client.streaming = message.streaming || message.active || false;
      client.lastSeen = new Date().toISOString();
      
      this.clients.set(clientId, client);
      this.notifyListeners();
      
      console.log(`📊 Stream-Status Update: ${clientId} -> ${client.streaming ? 'aktiv' : 'inaktiv'}`);
    }
  }

  /**
   * Bestimmt Client-Typ basierend auf Nachricht
   */
  private getClientType(message: any): 'desktop' | 'dual_screen' | 'multi_monitor' {
    if (message.type === 'dual_screen_connected') return 'dual_screen';
    if (message.type === 'multi_monitor_desktop_connected') return 'multi_monitor';
    return 'desktop';
  }

  /**
   * Behandelt Wiederverbindung
   */
  private handleReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
      
      console.log(`🔄 Wiederverbindungsversuch ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms...`);
      
      setTimeout(() => {
        this.initializeWebSocket();
      }, delay);
    } else {
      console.error('❌ Maximale Wiederverbindungsversuche erreicht');
    }
  }

  // ============================================================================
  // STREAM CONTROL METHODS
  // ============================================================================

  /**
   * Startet Desktop-Stream mit Permission-Check
   */
  async startDesktopStream(clientId: string, config?: StreamConfig): Promise<boolean> {
    const client = this.clients.get(clientId);
    
    if (!client || !client.connected) {
      console.error(`❌ Client ${clientId} nicht verbunden`);
      return false;
    }

    // Überprüfe Berechtigungen
    const hasPermission = client.type === 'dual_screen' 
      ? permissionService.hasDualScreenPermission(clientId)
      : permissionService.hasDesktopStreamingPermission(clientId);

    if (!hasPermission) {
      console.log(`🔒 Fordere Berechtigung für Client ${clientId} an...`);
      
      const granted = client.type === 'dual_screen'
        ? await permissionService.requestDualScreenPermission(clientId)
        : await permissionService.requestDesktopStreamingPermission(clientId);

      if (!granted) {
        console.error(`❌ Berechtigung für Client ${clientId} verweigert`);
        return false;
      }

      // Update Client-Permissions
      client.permissions.granted = true;
      client.permissions.scope = client.type === 'dual_screen' 
        ? ['dual_screen_capture', 'multi_monitor_access']
        : ['screen_capture', 'desktop_streaming'];
      
      this.clients.set(clientId, client);
    }

    // Sende Start-Kommando
    return this.sendStreamCommand('start_desktop_stream', clientId, config);
  }

  /**
   * Stoppt Desktop-Stream
   */
  async stopDesktopStream(clientId: string): Promise<boolean> {
    const client = this.clients.get(clientId);
    
    if (!client) {
      console.error(`❌ Client ${clientId} nicht gefunden`);
      return false;
    }

    return this.sendStreamCommand('stop_desktop_stream', clientId);
  }

  /**
   * Startet/Stoppt Stream (Toggle)
   */
  async toggleDesktopStream(clientId: string, config?: StreamConfig): Promise<boolean> {
    const client = this.clients.get(clientId);
    
    if (!client) {
      console.error(`❌ Client ${clientId} nicht gefunden`);
      return false;
    }

    if (client.streaming) {
      return this.stopDesktopStream(clientId);
    } else {
      return this.startDesktopStream(clientId, config);
    }
  }

  /**
   * Sendet Stream-Kommando an WebSocket-Server
   */
  private sendStreamCommand(type: string, clientId: string, config?: StreamConfig): boolean {
    if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
      console.error('❌ WebSocket-Verbindung nicht verfügbar');
      return false;
    }

    const command = {
      type,
      desktopClientId: clientId,
      config: config || {
        fps: 15,
        quality: 85,
        scale: 1.0,
        format: 'jpeg' as const
      },
      timestamp: new Date().toISOString()
    };

    try {
      this.websocket.send(JSON.stringify(command));
      console.log(`📤 Stream-Kommando gesendet: ${type} für Client ${clientId}`);
      return true;
    } catch (error) {
      console.error(`❌ Fehler beim Senden des Stream-Kommandos:`, error);
      return false;
    }
  }

  // ============================================================================
  // CLIENT MANAGEMENT
  // ============================================================================

  /**
   * Gibt alle verbundenen Clients zurück
   */
  getConnectedClients(): Map<string, DesktopClientInfo> {
    return new Map(this.clients);
  }

  /**
   * Gibt Client-Info zurück
   */
  getClientInfo(clientId: string): DesktopClientInfo | null {
    return this.clients.get(clientId) || null;
  }

  /**
   * Entfernt Client aus der Liste
   */
  removeClient(clientId: string): void {
    if (this.clients.has(clientId)) {
      // Stoppe Stream falls aktiv
      const client = this.clients.get(clientId)!;
      if (client.streaming) {
        this.stopDesktopStream(clientId);
      }

      // Widerrufe Berechtigungen
      permissionService.revokePermission(clientId, 'all');

      // Entferne Client
      this.clients.delete(clientId);
      this.notifyListeners();
      
      console.log(`🗑️ Client entfernt: ${clientId}`);
    }
  }

  // ============================================================================
  // LISTENER MANAGEMENT
  // ============================================================================

  /**
   * Registriert Listener für Client-Updates
   */
  addClientUpdateListener(key: string, callback: (clients: Map<string, DesktopClientInfo>) => void): void {
    this.listeners.set(key, callback);
  }

  /**
   * Entfernt Client-Update-Listener
   */
  removeClientUpdateListener(key: string): void {
    this.listeners.delete(key);
  }

  /**
   * Benachrichtigt alle Listener über Client-Updates
   */
  private notifyListeners(): void {
    this.listeners.forEach((callback, key) => {
      try {
        callback(new Map(this.clients));
      } catch (error) {
        console.error(`❌ Fehler beim Benachrichtigen des Listeners ${key}:`, error);
      }
    });
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  /**
   * Überprüft WebSocket-Verbindungsstatus
   */
  isConnected(): boolean {
    return this.websocket?.readyState === WebSocket.OPEN;
  }

  /**
   * Schließt WebSocket-Verbindung
   */
  disconnect(): void {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
    
    this.clients.clear();
    this.notifyListeners();
    
    console.log('🔌 Desktop Control Service getrennt');
  }

  /**
   * Bereinigt inaktive Clients
   */
  cleanupInactiveClients(): void {
    const now = new Date();
    const timeout = 5 * 60 * 1000; // 5 Minuten
    
    this.clients.forEach((client, clientId) => {
      const lastSeen = new Date(client.lastSeen);
      if (now.getTime() - lastSeen.getTime() > timeout) {
        console.log(`🧹 Bereinige inaktiven Client: ${clientId}`);
        this.removeClient(clientId);
      }
    });
  }
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

export const desktopControlService = new DesktopControlService();

// Automatische Bereinigung alle 2 Minuten
setInterval(() => {
  desktopControlService.cleanupInactiveClients();
}, 2 * 60 * 1000);

export default desktopControlService;