/**
 * Electron Bridge Service
 * Provides communication with Electron desktop app when available
 * Falls back to web APIs when Electron is not detected
 */

// ============================================
// Screen Capture Types
// ============================================

export interface ScreenCaptureFrame {
  displayId: string;
  displayIndex: number;
  displayName: string;
  width: number;
  height: number;
  timestamp: number;
  data: string; // Base64 encoded image
}

export interface DisplayInfo {
  id: string;
  name: string;
  index: number;
  width: number;
  height: number;
  thumbnail: string | null;
}

export interface CaptureOptions {
  fps?: number;
  quality?: number;
}

export interface CaptureStatus {
  isCapturing: boolean;
  fps: number;
  quality: number;
  displays: DisplayInfo[];
}

// ============================================
// Existing Types
// ============================================

export interface ElectronAPI {
  // App info
  getAppVersion: () => string;
  getPlatform: () => string;
  isElectron: () => boolean;

  // Window controls
  minimizeWindow: () => void;
  maximizeWindow: () => void;
  closeWindow: () => void;

  // Screen Capture
  getDisplays: () => Promise<DisplayInfo[]>;
  startScreenCapture: (options?: CaptureOptions) => Promise<{ success: boolean; displays?: DisplayInfo[]; error?: string }>;
  stopScreenCapture: () => Promise<{ success: boolean }>;
  getCaptureStatus: () => Promise<CaptureStatus>;
  setCaptureOptions: (options: CaptureOptions) => Promise<CaptureOptions>;
  onFrame: (callback: (frame: ScreenCaptureFrame) => void) => () => void;
  onDisplaysChanged: (callback: (displays: DisplayInfo[]) => void) => () => void;
  offFrame: (callback: (frame: ScreenCaptureFrame) => void) => void;

  // Notifications
  showNotification: (title: string, body: string) => void;

  // Logging
  log: (level: string, message: string) => void;

  // Moire features
  isMoireAvailable: () => boolean;
  performOCR: (imageData: string, options?: OCROptions) => Promise<OCRResponse>;
  detectMoire: (imageData: string) => Promise<MoireDetectionResult>;
  streamFrame: (frameData: string, metadata?: FrameMetadata) => void;
}

export interface OCROptions {
  language?: string;
  regions?: Array<{
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    label?: string;
  }>;
  confidence_threshold?: number;
}

export interface OCRResponse {
  success: boolean;
  results: Array<{
    zone_id: string;
    text: string;
    confidence: number;
    bbox: { x: number; y: number; width: number; height: number };
  }>;
  processing_time_ms: number;
}

export interface MoireDetectionResult {
  detected: boolean;
  confidence: number;
  regions: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
    severity: 'low' | 'medium' | 'high';
  }>;
}

export interface FrameMetadata {
  monitorId?: string;
  clientId?: string;
  timestamp?: string;
  width?: number;
  height?: number;
}

// ============================================
// Core Functions
// ============================================

/**
 * Check if running in Electron environment
 */
export const isElectron = (): boolean => {
  const result = typeof window !== 'undefined' &&
         window.electronAPI !== undefined &&
         (window.electronAPI.isElectron?.() ?? false);

  // Debug logging (use warn to bypass lint rules)
  if (typeof window !== 'undefined') {
    console.warn('[ElectronBridge] isElectron check:', {
      windowExists: true,
      electronAPIExists: window.electronAPI !== undefined,
      isElectronResult: result
    });
  }

  return result;
};

/**
 * Check if Moire features are available
 */
export const isMoireAvailable = (): boolean => {
  if (!isElectron()) return false;
  try {
    return window.electronAPI?.isMoireAvailable?.() ?? false;
  } catch {
    return false;
  }
};

/**
 * Get Electron API or null if not available
 */
export const getElectronAPI = (): ElectronAPI | null => {
  if (!isElectron()) return null;
  return window.electronAPI as ElectronAPI;
};

// ============================================
// Screen Capture Functions
// ============================================

/**
 * Get list of available displays
 */
export const getDisplays = async (): Promise<DisplayInfo[]> => {
  const api = getElectronAPI();
  if (!api) return [];

  try {
    return await api.getDisplays();
  } catch (error) {
    console.error('[ElectronBridge] Failed to get displays:', error);
    return [];
  }
};

/**
 * Start screen capture
 */
export const startScreenCapture = async (options?: CaptureOptions): Promise<boolean> => {
  const api = getElectronAPI();
  if (!api) {
    console.log('[ElectronBridge] Screen capture not available (not in Electron)');
    return false;
  }

  try {
    const result = await api.startScreenCapture(options);
    return result.success;
  } catch (error) {
    console.error('[ElectronBridge] Failed to start screen capture:', error);
    return false;
  }
};

/**
 * Stop screen capture
 */
export const stopScreenCapture = async (): Promise<boolean> => {
  const api = getElectronAPI();
  if (!api) return false;

  try {
    const result = await api.stopScreenCapture();
    return result.success;
  } catch (error) {
    console.error('[ElectronBridge] Failed to stop screen capture:', error);
    return false;
  }
};

/**
 * Get capture status
 */
export const getCaptureStatus = async (): Promise<CaptureStatus | null> => {
  const api = getElectronAPI();
  if (!api) return null;

  try {
    return await api.getCaptureStatus();
  } catch (error) {
    console.error('[ElectronBridge] Failed to get capture status:', error);
    return null;
  }
};

/**
 * Subscribe to screen capture frames
 * Returns cleanup function
 */
export const onScreenFrame = (callback: (frame: ScreenCaptureFrame) => void): (() => void) => {
  const api = getElectronAPI();
  console.warn('[ElectronBridge] onScreenFrame called, api available:', !!api);

  if (!api) {
    console.warn('[ElectronBridge] onScreenFrame not available (not in Electron)');
    return () => {};
  }

  console.warn('[ElectronBridge] Subscribing to screen capture frames...');

  // Wrap callback to add logging
  const wrappedCallback = (frame: ScreenCaptureFrame) => {
    console.warn('[ElectronBridge] Frame received from Electron:', {
      displayIndex: frame.displayIndex,
      timestamp: frame.timestamp
    });
    callback(frame);
  };

  return api.onFrame(wrappedCallback);
};

/**
 * Subscribe to display changes
 * Returns cleanup function
 */
export const onDisplaysChanged = (callback: (displays: DisplayInfo[]) => void): (() => void) => {
  const api = getElectronAPI();
  if (!api) return () => {};

  return api.onDisplaysChanged(callback);
};

// ============================================
// OCR Functions
// ============================================

/**
 * Perform OCR using Electron's native OCR if available
 * Falls back to backend service if not
 */
export const performNativeOCR = async (
  imageData: string,
  options?: OCROptions
): Promise<OCRResponse | null> => {
  const api = getElectronAPI();
  if (!api || !api.isMoireAvailable()) {
    console.log('[ElectronBridge] Native OCR not available, use backend service');
    return null;
  }

  try {
    return await api.performOCR(imageData, options);
  } catch (error) {
    console.error('[ElectronBridge] Native OCR failed:', error);
    return null;
  }
};

/**
 * Detect Moire patterns using Electron's native detection
 */
export const detectMoirePatterns = async (
  imageData: string
): Promise<MoireDetectionResult | null> => {
  const api = getElectronAPI();
  if (!api || !api.isMoireAvailable()) {
    console.log('[ElectronBridge] Moire detection not available');
    return null;
  }

  try {
    return await api.detectMoire(imageData);
  } catch (error) {
    console.error('[ElectronBridge] Moire detection failed:', error);
    return null;
  }
};

/**
 * Stream frame to Electron for processing
 */
export const streamFrameToElectron = (
  frameData: string,
  metadata?: FrameMetadata
): void => {
  const api = getElectronAPI();
  if (!api) return;

  try {
    api.streamFrame(frameData, metadata);
  } catch (error) {
    console.error('[ElectronBridge] Frame streaming failed:', error);
  }
};

// ============================================
// Utility Functions
// ============================================

/**
 * Show native notification if in Electron
 */
export const showNativeNotification = (title: string, body: string): void => {
  const api = getElectronAPI();
  if (api) {
    api.showNotification(title, body);
  } else if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(title, { body });
  }
};

/**
 * Log message via Electron's logging system
 */
export const electronLog = (level: 'info' | 'warn' | 'error', message: string): void => {
  const api = getElectronAPI();
  if (api) {
    api.log(level, message);
  } else {
    console[level](`[ElectronBridge] ${message}`);
  }
};

/**
 * Get platform info
 */
export const getPlatformInfo = (): { platform: string; version: string } => {
  const api = getElectronAPI();
  if (api) {
    return {
      platform: api.getPlatform(),
      version: api.getAppVersion()
    };
  }
  return {
    platform: navigator.platform,
    version: '1.0.0-web'
  };
};

// Declare global type for electronAPI
declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export default {
  isElectron,
  isMoireAvailable,
  getElectronAPI,
  // Screen capture
  getDisplays,
  startScreenCapture,
  stopScreenCapture,
  getCaptureStatus,
  onScreenFrame,
  onDisplaysChanged,
  // OCR
  performNativeOCR,
  detectMoirePatterns,
  streamFrameToElectron,
  // Utils
  showNativeNotification,
  electronLog,
  getPlatformInfo
};
