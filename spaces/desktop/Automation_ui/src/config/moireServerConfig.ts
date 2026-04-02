/**
 * MoireServer WebSocket Configuration
 *
 * Centralized configuration for connecting to the MoireServer
 * which handles UI detection, OCR, and CNN classification.
 */

// MoireServer WebSocket URL (MoireTracker submodule)
export const MOIRE_SERVER_URL = 'ws://localhost:8765';

// Message types for MoireServer communication
export const MOIRE_MESSAGE_TYPES = {
  // Commands (send to server)
  SCAN_DESKTOP: 'scan_desktop',
  SCAN_WINDOW: 'scan_window',
  RUN_OCR: 'run_ocr',
  RUN_CNN: 'run_cnn',
  ANALYZE_FRAME: 'analyze_frame',
  GET_STATUS: 'get_status',

  // Events (receive from server)
  DETECTION_RESULT: 'moire_detection_result',
  OCR_RESULT: 'ocr_result',
  CNN_RESULT: 'cnn_result',
  STATUS: 'status',
  ERROR: 'error',
  CONNECTED: 'connected',
} as const;

// Detection box interface matching MoireServer output
export interface MoireDetectionBox {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  text?: string;
  confidence?: number;
  category?: string;
  ocrText?: string;
}

// Detection result from MoireServer
export interface MoireDetectionResult {
  type: string;
  timestamp: number;
  boxes: MoireDetectionBox[];
  imageWidth: number;
  imageHeight: number;
  detectionMode: 'simple' | 'advanced';
  processingTime?: number;
}

// OCR result from MoireServer
export interface MoireOCRResult {
  type: string;
  boxes: Array<{
    id: string;
    text: string;
    confidence: number;
    x: number;
    y: number;
    width: number;
    height: number;
  }>;
}

// CNN classification result
export interface MoireCNNResult {
  type: string;
  classifications: Array<{
    boxId: string;
    category: string;
    confidence: number;
  }>;
}

// Create WebSocket message for frame analysis
export function createAnalyzeFrameMessage(
  imageData: string, // base64 encoded image
  options?: {
    runOCR?: boolean;
    runCNN?: boolean;
    detectionMode?: 'simple' | 'advanced';
  }
): string {
  return JSON.stringify({
    type: MOIRE_MESSAGE_TYPES.ANALYZE_FRAME,
    imageData,
    options: {
      runOCR: options?.runOCR ?? false,
      runCNN: options?.runCNN ?? false,
      detectionMode: options?.detectionMode ?? 'advanced',
    },
    timestamp: Date.now(),
  });
}

// Create WebSocket connection to MoireServer
export function createMoireServerConnection(
  onMessage?: (data: MoireDetectionResult | MoireOCRResult | MoireCNNResult) => void,
  onError?: (error: Event) => void,
  onOpen?: () => void,
  onClose?: () => void
): WebSocket {
  const ws = new WebSocket(MOIRE_SERVER_URL);

  ws.onopen = () => {
    console.log('[MoireServer] Connected to', MOIRE_SERVER_URL);
    onOpen?.();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      console.log('[MoireServer] Received:', data.type);
      onMessage?.(data);
    } catch (e) {
      console.error('[MoireServer] Parse error:', e);
    }
  };

  ws.onerror = (error) => {
    console.error('[MoireServer] Error:', error);
    onError?.(error);
  };

  ws.onclose = () => {
    console.log('[MoireServer] Disconnected');
    onClose?.();
  };

  return ws;
}
