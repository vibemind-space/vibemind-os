/**
 * Live Desktop Configuration and OCR Types
 * Defines types for Live Desktop streaming and OCR region management
 */

export interface LiveDesktopConfig {
  id: string;
  name: string;
  description: string;
  websocketUrl: string;
  streaming: {
    fps: number;
    quality: number;
    scale: number;
    format?: string;
  };
  connection: {
    timeout: number;
    maxReconnectAttempts: number;
    reconnectInterval: number;
    autoReconnect?: boolean;
  };
  ocr: {
    enabled: boolean;
    extractionInterval: number; // seconds
    n8nWebhookUrl?: string;
    autoSend: boolean;
    regions?: OCRRegion[];
  };
  ocrRegions: OCRRegion[];
  createdAt: string;
  updatedAt: string;
  category?: string;
}

export interface OCRRegion {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  isActive: boolean;
  lastExtractedText: string;
  extractionHistory: OCRExtraction[];
}

export interface OCRExtraction {
  timestamp: string;
  text: string;
  confidence: number;
}

export interface LiveDesktopStatus {
  connected: boolean;
  streaming: boolean;
  connectionName: string | null;
  latency: number;
  fpsActual: number;
  bytesReceived: number;
  lastFrameTime: string | null;
}

export interface LiveDesktopTemplate {
  id: string;
  name: string;
  description: string;
  category: 'monitoring' | 'automation' | 'data-extraction' | 'custom';
  config: Partial<LiveDesktopConfig>;
  thumbnail?: string;
}