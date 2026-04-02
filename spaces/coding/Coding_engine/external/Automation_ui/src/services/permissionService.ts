/**
 * Permission Service für lokale PC-Zugriffe
 * 
 * Verwaltet Benutzerberechtigungen für Desktop-Streaming und Screen-Capture
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

// ============================================================================
// INTERFACES & TYPES
// ============================================================================

export interface PermissionRequest {
  id: string;
  type: 'screen_capture' | 'desktop_access' | 'dual_screen' | 'system_control';
  description: string;
  requiredBy: string;
  timestamp: string;
  status: 'pending' | 'granted' | 'denied' | 'expired';
}

export interface PermissionStatus {
  granted: boolean;
  timestamp: string;
  expiresAt?: string;
  scope: string[];
}

// ============================================================================
// PERMISSION SERVICE CLASS
// ============================================================================

class PermissionService {
  private permissions: Map<string, PermissionStatus> = new Map();
  private pendingRequests: Map<string, PermissionRequest> = new Map();
  private listeners: Map<string, (status: PermissionStatus) => void> = new Map();

  // ============================================================================
  // PERMISSION REQUEST METHODS
  // ============================================================================

  /**
   * Fordert Berechtigung für Desktop-Streaming an
   */
  async requestDesktopStreamingPermission(clientId: string): Promise<boolean> {
    const permissionId = `desktop_stream_${clientId}_${Date.now()}`;
    
    const request: PermissionRequest = {
      id: permissionId,
      type: 'screen_capture',
      description: 'Berechtigung für Desktop-Screen-Capture und Streaming',
      requiredBy: clientId,
      timestamp: new Date().toISOString(),
      status: 'pending'
    };

    this.pendingRequests.set(permissionId, request);

    // Zeige Permission-Dialog
    const granted = await this.showPermissionDialog(request);
    
    if (granted) {
      const permission: PermissionStatus = {
        granted: true,
        timestamp: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), // 24h
        scope: ['screen_capture', 'desktop_streaming']
      };
      
      this.permissions.set(`desktop_${clientId}`, permission);
      this.pendingRequests.delete(permissionId);
      
      // Benachrichtige Listener
      this.notifyListeners(`desktop_${clientId}`, permission);
      
      return true;
    } else {
      this.pendingRequests.delete(permissionId);
      return false;
    }
  }

  /**
   * Fordert Berechtigung für Dual-Screen-Capture an
   */
  async requestDualScreenPermission(clientId: string): Promise<boolean> {
    const permissionId = `dual_screen_${clientId}_${Date.now()}`;
    
    const request: PermissionRequest = {
      id: permissionId,
      type: 'dual_screen',
      description: 'Berechtigung für Dual-Screen-Capture und erweiterte Monitor-Kontrolle',
      requiredBy: clientId,
      timestamp: new Date().toISOString(),
      status: 'pending'
    };

    this.pendingRequests.set(permissionId, request);

    // Zeige erweiterten Permission-Dialog
    const granted = await this.showPermissionDialog(request);
    
    if (granted) {
      const permission: PermissionStatus = {
        granted: true,
        timestamp: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), // 24h
        scope: ['dual_screen_capture', 'multi_monitor_access', 'system_control']
      };
      
      this.permissions.set(`dual_screen_${clientId}`, permission);
      this.pendingRequests.delete(permissionId);
      
      // Benachrichtige Listener
      this.notifyListeners(`dual_screen_${clientId}`, permission);
      
      return true;
    } else {
      this.pendingRequests.delete(permissionId);
      return false;
    }
  }

  // ============================================================================
  // PERMISSION CHECK METHODS
  // ============================================================================

  /**
   * Überprüft ob Desktop-Streaming-Berechtigung vorhanden ist
   */
  hasDesktopStreamingPermission(clientId: string): boolean {
    const permission = this.permissions.get(`desktop_${clientId}`);
    
    if (!permission || !permission.granted) {
      return false;
    }

    // Überprüfe Ablaufzeit
    if (permission.expiresAt && new Date(permission.expiresAt) < new Date()) {
      this.permissions.delete(`desktop_${clientId}`);
      return false;
    }

    return true;
  }

  /**
   * Überprüft ob Dual-Screen-Berechtigung vorhanden ist
   */
  hasDualScreenPermission(clientId: string): boolean {
    const permission = this.permissions.get(`dual_screen_${clientId}`);
    
    if (!permission || !permission.granted) {
      return false;
    }

    // Überprüfe Ablaufzeit
    if (permission.expiresAt && new Date(permission.expiresAt) < new Date()) {
      this.permissions.delete(`dual_screen_${clientId}`);
      return false;
    }

    return true;
  }

  // ============================================================================
  // PERMISSION MANAGEMENT
  // ============================================================================

  /**
   * Widerruft Berechtigung für einen Client
   */
  revokePermission(clientId: string, type: 'desktop' | 'dual_screen' | 'all'): void {
    if (type === 'all') {
      this.permissions.delete(`desktop_${clientId}`);
      this.permissions.delete(`dual_screen_${clientId}`);
    } else {
      this.permissions.delete(`${type}_${clientId}`);
    }

    console.log(`🔒 Berechtigung widerrufen für Client ${clientId} (${type})`);
  }

  /**
   * Erneuert Berechtigung für einen Client
   */
  renewPermission(clientId: string, type: 'desktop' | 'dual_screen'): void {
    const permission = this.permissions.get(`${type}_${clientId}`);
    
    if (permission && permission.granted) {
      permission.expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
      this.permissions.set(`${type}_${clientId}`, permission);
      
      console.log(`🔄 Berechtigung erneuert für Client ${clientId} (${type})`);
    }
  }

  // ============================================================================
  // LISTENER MANAGEMENT
  // ============================================================================

  /**
   * Registriert Listener für Permission-Änderungen
   */
  addPermissionListener(key: string, callback: (status: PermissionStatus) => void): void {
    this.listeners.set(key, callback);
  }

  /**
   * Entfernt Permission-Listener
   */
  removePermissionListener(key: string): void {
    this.listeners.delete(key);
  }

  /**
   * Benachrichtigt alle Listener über Permission-Änderungen
   */
  private notifyListeners(permissionKey: string, status: PermissionStatus): void {
    this.listeners.forEach((callback, key) => {
      if (key.includes(permissionKey)) {
        try {
          callback(status);
        } catch (error) {
          console.error(`Fehler beim Benachrichtigen des Listeners ${key}:`, error);
        }
      }
    });
  }

  // ============================================================================
  // PERMISSION DIALOG
  // ============================================================================

  /**
   * Zeigt Permission-Dialog für Benutzer-Bestätigung
   */
  private async showPermissionDialog(request: PermissionRequest): Promise<boolean> {
    return new Promise((resolve) => {
      // Erstelle Permission-Dialog
      const dialog = document.createElement('div');
      dialog.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
      dialog.innerHTML = `
        <div class="bg-white rounded-lg p-6 max-w-md mx-4 shadow-xl">
          <div class="flex items-center gap-3 mb-4">
            <div class="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
              <svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-gray-900">Berechtigung erforderlich</h3>
              <p class="text-sm text-gray-500">Client: ${request.requiredBy}</p>
            </div>
          </div>
          
          <div class="mb-6">
            <p class="text-gray-700 mb-2">${request.description}</p>
            <div class="bg-yellow-50 border border-yellow-200 rounded-md p-3">
              <p class="text-sm text-yellow-800">
                <strong>Hinweis:</strong> Diese Berechtigung ermöglicht es der Anwendung, 
                auf Ihren Desktop zuzugreifen und Bildschirminhalte zu erfassen.
              </p>
            </div>
          </div>
          
          <div class="flex gap-3 justify-end">
            <button id="deny-permission" class="px-4 py-2 text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors">
              Ablehnen
            </button>
            <button id="grant-permission" class="px-4 py-2 text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors">
              Berechtigung erteilen
            </button>
          </div>
        </div>
      `;

      document.body.appendChild(dialog);

      // Event-Listener für Buttons
      const denyButton = dialog.querySelector('#deny-permission');
      const grantButton = dialog.querySelector('#grant-permission');

      denyButton?.addEventListener('click', () => {
        document.body.removeChild(dialog);
        resolve(false);
      });

      grantButton?.addEventListener('click', () => {
        document.body.removeChild(dialog);
        resolve(true);
      });

      // Auto-Ablauf nach 30 Sekunden
      setTimeout(() => {
        if (document.body.contains(dialog)) {
          document.body.removeChild(dialog);
          resolve(false);
        }
      }, 30000);
    });
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  /**
   * Gibt alle aktiven Berechtigungen zurück
   */
  getAllPermissions(): Map<string, PermissionStatus> {
    return new Map(this.permissions);
  }

  /**
   * Gibt alle ausstehenden Anfragen zurück
   */
  getPendingRequests(): Map<string, PermissionRequest> {
    return new Map(this.pendingRequests);
  }

  /**
   * Bereinigt abgelaufene Berechtigungen
   */
  cleanupExpiredPermissions(): void {
    const now = new Date();
    
    this.permissions.forEach((permission, key) => {
      if (permission.expiresAt && new Date(permission.expiresAt) < now) {
        this.permissions.delete(key);
        console.log(`🧹 Abgelaufene Berechtigung entfernt: ${key}`);
      }
    });
  }
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

export const permissionService = new PermissionService();

// Automatische Bereinigung alle 5 Minuten
setInterval(() => {
  permissionService.cleanupExpiredPermissions();
}, 5 * 60 * 1000);

export default permissionService;