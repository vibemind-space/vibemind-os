/**
 * useMoireServer Hook
 *
 * React hook for connecting to MoireServer and managing detection state.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  MoireDetectionService,
  MoireDetectionResult,
  MoireDetectionBox,
  ConnectionStatus,
} from '@/services/moireDetectionService';

export interface UseMoireServerOptions {
  autoConnect?: boolean;
  onDetectionResult?: (result: MoireDetectionResult) => void;
}

export interface UseMoireServerReturn {
  // Connection state
  status: ConnectionStatus;
  isConnected: boolean;

  // Detection state
  detectionBoxes: MoireDetectionBox[];
  lastResult: MoireDetectionResult | null;
  isAnalyzing: boolean;

  // Actions
  connect: () => Promise<boolean>;
  disconnect: () => void;
  analyzeFrame: (imageData: string, options?: AnalyzeOptions) => boolean;
  scanDesktop: () => boolean;
  runOCR: (boxIds?: string[]) => boolean;
  runCNN: (boxIds?: string[]) => boolean;
  clearBoxes: () => void;
}

export interface AnalyzeOptions {
  runOCR?: boolean;
  runCNN?: boolean;
  detectionMode?: 'simple' | 'advanced';
}

export function useMoireServer(options: UseMoireServerOptions = {}): UseMoireServerReturn {
  const { autoConnect = false, onDetectionResult } = options;

  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [detectionBoxes, setDetectionBoxes] = useState<MoireDetectionBox[]>([]);
  const [lastResult, setLastResult] = useState<MoireDetectionResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const onDetectionResultRef = useRef(onDetectionResult);
  onDetectionResultRef.current = onDetectionResult;

  // Handle detection results
  const handleDetectionResult = useCallback((result: MoireDetectionResult) => {
    setLastResult(result);
    setDetectionBoxes(result.boxes || []);
    setIsAnalyzing(false);
    onDetectionResultRef.current?.(result);
  }, []);

  // Handle connection status changes
  const handleConnectionChange = useCallback((newStatus: ConnectionStatus) => {
    setStatus(newStatus);
  }, []);

  // Handle errors
  const handleError = useCallback((error: string) => {
    console.error('[useMoireServer] Error:', error);
    setIsAnalyzing(false);
  }, []);

  // Connect to MoireServer
  const connect = useCallback(async (): Promise<boolean> => {
    return MoireDetectionService.connect({
      onDetectionResult: handleDetectionResult,
      onConnectionChange: handleConnectionChange,
      onError: handleError,
    });
  }, [handleDetectionResult, handleConnectionChange, handleError]);

  // Disconnect from MoireServer
  const disconnect = useCallback(() => {
    MoireDetectionService.disconnect();
  }, []);

  // Analyze a frame
  const analyzeFrame = useCallback(
    (imageData: string, analyzeOptions?: AnalyzeOptions): boolean => {
      setIsAnalyzing(true);
      return MoireDetectionService.analyzeFrame(imageData, analyzeOptions);
    },
    []
  );

  // Scan desktop
  const scanDesktop = useCallback((): boolean => {
    setIsAnalyzing(true);
    return MoireDetectionService.scanDesktop();
  }, []);

  // Run OCR
  const runOCR = useCallback((boxIds?: string[]): boolean => {
    return MoireDetectionService.runOCR(boxIds);
  }, []);

  // Run CNN
  const runCNN = useCallback((boxIds?: string[]): boolean => {
    return MoireDetectionService.runCNN(boxIds);
  }, []);

  // Clear detection boxes
  const clearBoxes = useCallback(() => {
    setDetectionBoxes([]);
    setLastResult(null);
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      // Don't disconnect on unmount - keep connection alive
    };
  }, [autoConnect, connect]);

  return {
    status,
    isConnected: status === 'connected',
    detectionBoxes,
    lastResult,
    isAnalyzing,
    connect,
    disconnect,
    analyzeFrame,
    scanDesktop,
    runOCR,
    runCNN,
    clearBoxes,
  };
}

export default useMoireServer;
