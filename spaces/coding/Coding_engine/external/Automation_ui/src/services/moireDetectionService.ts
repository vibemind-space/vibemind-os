// Moire Detection Service - Stub implementation
// This service handles communication with the Moire detection server

export interface DetectionResult {
  boxes: DetectionBox[];
  timestamp: number;
  confidence: number;
}

export interface DetectionBox {
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  confidence: number;
}

export interface MoireServerConfig {
  url: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export class MoireDetectionService {
  private ws: WebSocket | null = null;
  private config: MoireServerConfig;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private onDetectionCallback: ((result: DetectionResult) => void) | null =
    null;
  private onConnectionChangeCallback: ((connected: boolean) => void) | null =
    null;

  constructor(config: MoireServerConfig) {
    this.config = {
      reconnectInterval: 5000,
      maxReconnectAttempts: 10,
      ...config,
    };
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      this.ws = new WebSocket(this.config.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.onConnectionChangeCallback?.(true);
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.onConnectionChangeCallback?.(false);
        this.attemptReconnect();
      };

      this.ws.onerror = () => {
        this.isConnected = false;
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "detection_result" && this.onDetectionCallback) {
            this.onDetectionCallback(data.result);
          }
        } catch {
          // Ignore parse errors
        }
      };
    } catch {
      this.attemptReconnect();
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= (this.config.maxReconnectAttempts || 10)) {
      return;
    }

    this.reconnectAttempts++;
    setTimeout(() => {
      this.connect();
    }, this.config.reconnectInterval);
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnected = false;
  }

  sendFrame(frameData: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          type: "analyze_frame",
          frame: frameData,
          timestamp: Date.now(),
        }),
      );
    }
  }

  onDetection(callback: (result: DetectionResult) => void): void {
    this.onDetectionCallback = callback;
  }

  onConnectionChange(callback: (connected: boolean) => void): void {
    this.onConnectionChangeCallback = callback;
  }

  getIsConnected(): boolean {
    return this.isConnected;
  }
}

// Default export for convenience
export default MoireDetectionService;
