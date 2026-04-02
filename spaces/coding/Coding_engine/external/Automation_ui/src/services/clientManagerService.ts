/**
 * Client Manager Service für TRAE Frontend
 * 
 * Kommuniziert mit dem Backend API um den Desktop Capture Client zu steuern:
 * - Start/Stop des Python-Clients
 * - Status-Abfragen
 * - Restart-Funktionalität
 * 
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

// Backend API Base URL
const BACKEND_API_URL = 'http://localhost:8007/api/client';

/**
 * Status-Enum für den Desktop Capture Client
 */
export enum ClientStatus {
  STOPPED = 'stopped',
  STARTING = 'starting',
  RUNNING = 'running',
  STOPPING = 'stopping',
  ERROR = 'error',
  RESTARTING = 'restarting'
}

/**
 * Response-Interface für Client-Status
 */
export interface ClientStatusResponse {
  success: boolean;
  status: ClientStatus;
  is_running: boolean;
  pid: number | null;
  start_time: string | null;
  uptime_seconds: number;
  last_heartbeat: string | null;
  last_heartbeat_ago_seconds: number | null;
  restart_count: number;
  script_path: string;
  script_exists: boolean;
  watchdog_active: boolean;
  stats: {
    total_starts: number;
    total_stops: number;
    total_restarts: number;
    total_heartbeats: number;
    uptime_seconds: number;
  };
}

/**
 * Response-Interface für Start/Stop/Restart Operationen
 */
export interface ClientOperationResponse {
  success: boolean;
  message?: string;
  error?: string;
  status: ClientStatus;
  pid?: number;
}

/**
 * Request-Interface für Start-Operation
 */
export interface StartClientRequest {
  auto_restart?: boolean;
  server_url?: string;
}

/**
 * Request-Interface für Stop-Operation
 */
export interface StopClientRequest {
  force?: boolean;
}

/**
 * Client Manager Service
 * Singleton-Pattern für konsistente API-Kommunikation
 */
class ClientManagerServiceClass {
  private baseUrl: string;
  private pollingInterval: NodeJS.Timeout | null = null;
  private statusListeners: ((status: ClientStatusResponse) => void)[] = [];

  constructor(baseUrl: string = BACKEND_API_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Setzt die Base-URL für die API
   */
  setBaseUrl(url: string): void {
    this.baseUrl = url;
  }

  /**
   * Startet den Desktop Capture Client
   */
  async startClient(options: StartClientRequest = {}): Promise<ClientOperationResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          auto_restart: options.auto_restart ?? true,
          server_url: options.server_url ?? null,
        }),
      });

      const data = await response.json();
      
      if (!response.ok) {
        console.error('[ClientManager] Start fehlgeschlagen:', data);
      } else {
        console.log('[ClientManager] Start erfolgreich:', data);
      }

      return data as ClientOperationResponse;
    } catch (error) {
      console.error('[ClientManager] Start-Fehler:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unbekannter Fehler',
        status: ClientStatus.ERROR,
      };
    }
  }

  /**
   * Stoppt den Desktop Capture Client
   */
  async stopClient(options: StopClientRequest = {}): Promise<ClientOperationResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/stop`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          force: options.force ?? false,
        }),
      });

      const data = await response.json();
      
      if (!response.ok) {
        console.error('[ClientManager] Stop fehlgeschlagen:', data);
      } else {
        console.log('[ClientManager] Stop erfolgreich:', data);
      }

      return data as ClientOperationResponse;
    } catch (error) {
      console.error('[ClientManager] Stop-Fehler:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unbekannter Fehler',
        status: ClientStatus.ERROR,
      };
    }
  }

  /**
   * Startet den Desktop Capture Client neu
   */
  async restartClient(): Promise<ClientOperationResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/restart`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data = await response.json();
      
      if (!response.ok) {
        console.error('[ClientManager] Restart fehlgeschlagen:', data);
      } else {
        console.log('[ClientManager] Restart erfolgreich:', data);
      }

      return data as ClientOperationResponse;
    } catch (error) {
      console.error('[ClientManager] Restart-Fehler:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unbekannter Fehler',
        status: ClientStatus.ERROR,
      };
    }
  }

  /**
   * Ruft den aktuellen Status des Clients ab
   */
  async getStatus(): Promise<ClientStatusResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/status`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });

      const data = await response.json();
      
      return data as ClientStatusResponse;
    } catch (error) {
      console.error('[ClientManager] Status-Abruf Fehler:', error);
      return {
        success: false,
        status: ClientStatus.ERROR,
        is_running: false,
        pid: null,
        start_time: null,
        uptime_seconds: 0,
        last_heartbeat: null,
        last_heartbeat_ago_seconds: null,
        restart_count: 0,
        script_path: '',
        script_exists: false,
        watchdog_active: false,
        stats: {
          total_starts: 0,
          total_stops: 0,
          total_restarts: 0,
          total_heartbeats: 0,
          uptime_seconds: 0,
        },
      };
    }
  }

  /**
   * Prüft ob der Client läuft
   */
  async isRunning(): Promise<boolean> {
    const status = await this.getStatus();
    return status.is_running;
  }

  /**
   * Registriert einen Listener für Status-Updates
   */
  onStatusChange(callback: (status: ClientStatusResponse) => void): () => void {
    this.statusListeners.push(callback);
    
    // Rückgabe einer Cleanup-Funktion
    return () => {
      const index = this.statusListeners.indexOf(callback);
      if (index > -1) {
        this.statusListeners.splice(index, 1);
      }
    };
  }

  /**
   * Startet Polling für Status-Updates
   */
  startStatusPolling(intervalMs: number = 5000): void {
    if (this.pollingInterval) {
      this.stopStatusPolling();
    }

    console.log(`[ClientManager] Status-Polling gestartet (${intervalMs}ms)`);

    const poll = async () => {
      const status = await this.getStatus();
      this.statusListeners.forEach(listener => listener(status));
    };

    // Initial poll
    poll();

    // Start interval
    this.pollingInterval = setInterval(poll, intervalMs);
  }

  /**
   * Stoppt das Status-Polling
   */
  stopStatusPolling(): void {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
      console.log('[ClientManager] Status-Polling gestoppt');
    }
  }

  /**
   * Startet den Client und wartet bis er läuft
   */
  async startAndWait(timeoutMs: number = 10000): Promise<boolean> {
    const startResult = await this.startClient({ auto_restart: true });
    
    if (!startResult.success) {
      return false;
    }

    // Warte auf Status "running"
    const startTime = Date.now();
    while (Date.now() - startTime < timeoutMs) {
      const status = await this.getStatus();
      if (status.is_running) {
        return true;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    return false;
  }

  /**
   * Stoppt den Client und wartet bis er gestoppt ist
   */
  async stopAndWait(timeoutMs: number = 10000): Promise<boolean> {
    const stopResult = await this.stopClient({ force: false });
    
    if (!stopResult.success && stopResult.status !== ClientStatus.STOPPED) {
      return false;
    }

    // Warte auf Status "stopped"
    const startTime = Date.now();
    while (Date.now() - startTime < timeoutMs) {
      const status = await this.getStatus();
      if (!status.is_running) {
        return true;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    // Force stop als Fallback
    await this.stopClient({ force: true });
    return true;
  }
}

// Singleton-Export
export const ClientManagerService = new ClientManagerServiceClass();
export default ClientManagerService;