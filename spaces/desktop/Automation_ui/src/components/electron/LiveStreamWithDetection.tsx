/**
 * Live Stream With Detection Overlay
 *
 * Simplified stream display with real-time detection boxes,
 * OCR region drawing, and click position tracking.
 *
 * Designed for Electron Desktop Automation - minimal UI, maximum functionality.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Badge } from '@/components/ui/badge';
import { Monitor } from 'lucide-react';

// ============================================
// Types
// ============================================

export interface DetectionBox {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
  type?: 'element' | 'text' | 'click_target' | 'ocr_region';
}

export interface OCRRegion {
  id: string;
  name?: string;
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FrameData {
  data: string; // Base64 image
  timestamp: number;
  width: number;
  height: number;
  monitorId?: number;
}

interface LiveStreamWithDetectionProps {
  frame: FrameData | null;
  detectionBoxes?: DetectionBox[];
  ocrRegions?: OCRRegion[];
  clickTarget?: { x: number; y: number } | null;
  isConnected?: boolean;
  fps?: number;
  onRefresh?: () => void;
  onClickPosition?: (x: number, y: number) => void;
  onOCRRegionDraw?: (region: Omit<OCRRegion, 'id' | 'text'>) => void;
  enableOCRDrawing?: boolean;
  className?: string;
}

// ============================================
// Component
// ============================================

export const LiveStreamWithDetection: React.FC<LiveStreamWithDetectionProps> = ({
  frame,
  detectionBoxes = [],
  ocrRegions = [],
  clickTarget = null,
  isConnected: _isConnected = false,
  fps: _fps = 0,
  onClickPosition,
  onOCRRegionDraw,
  enableOCRDrawing = false,
  className = ''
}) => {
  // Note: isConnected and fps are kept in props for API compatibility but displayed externally
  void _isConnected;
  void _fps;
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [scale, setScale] = useState({ scaleX: 1, scaleY: 1 });

  // OCR region drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawCurrent, setDrawCurrent] = useState<{ x: number; y: number } | null>(null);

  // Calculate scale factor for overlay positioning
  const updateScale = useCallback(() => {
    if (!frame || !containerRef.current || !imageRef.current) {return;}

    const imgRect = imageRef.current.getBoundingClientRect();
    const scaleX = imgRect.width / frame.width;
    const scaleY = imgRect.height / frame.height;

    setScale({ scaleX, scaleY });
  }, [frame]);

  // Update scale on resize and when image loads
  useEffect(() => {
    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, [updateScale]);

  // Convert screen coords to image coords
  const screenToImageCoords = useCallback((clientX: number, clientY: number) => {
    if (!imageRef.current || !frame) {return { x: 0, y: 0 };}

    const rect = imageRef.current.getBoundingClientRect();
    const x = Math.round((clientX - rect.left) / scale.scaleX);
    const y = Math.round((clientY - rect.top) / scale.scaleY);

    return {
      x: Math.max(0, Math.min(x, frame.width)),
      y: Math.max(0, Math.min(y, frame.height))
    };
  }, [frame, scale]);

  // Handle mouse down - start drawing or click
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!frame) {return;}

    const coords = screenToImageCoords(e.clientX, e.clientY);

    if (enableOCRDrawing && onOCRRegionDraw) {
      setIsDrawing(true);
      setDrawStart(coords);
      setDrawCurrent(coords);
    } else if (onClickPosition) {
      onClickPosition(coords.x, coords.y);
    }
  }, [frame, enableOCRDrawing, onOCRRegionDraw, onClickPosition, screenToImageCoords]);

  // Handle mouse move - update drawing
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDrawing || !frame) {return;}

    const coords = screenToImageCoords(e.clientX, e.clientY);
    setDrawCurrent(coords);
  }, [isDrawing, frame, screenToImageCoords]);

  // Handle mouse up - finish drawing
  const handleMouseUp = useCallback(() => {
    if (isDrawing && drawStart && drawCurrent && onOCRRegionDraw) {
      const x = Math.min(drawStart.x, drawCurrent.x);
      const y = Math.min(drawStart.y, drawCurrent.y);
      const width = Math.abs(drawCurrent.x - drawStart.x);
      const height = Math.abs(drawCurrent.y - drawStart.y);

      // Only create region if it's larger than 10x10 pixels
      if (width > 10 && height > 10) {
        onOCRRegionDraw({ x, y, width, height });
      }
    }

    setIsDrawing(false);
    setDrawStart(null);
    setDrawCurrent(null);
  }, [isDrawing, drawStart, drawCurrent, onOCRRegionDraw]);

  // Get box color based on type
  const getBoxColor = (type?: string) => {
    switch (type) {
      case 'click_target': return { border: '#22c55e', bg: 'rgba(34, 197, 94, 0.15)' };
      case 'text': return { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)' };
      case 'ocr_region': return { border: '#a855f7', bg: 'rgba(168, 85, 247, 0.15)' };
      default: return { border: '#3b82f6', bg: 'rgba(59, 130, 246, 0.15)' };
    }
  };

  // Render detection box
  const renderDetectionBox = (box: DetectionBox) => {
    const colors = getBoxColor(box.type);

    return (
      <div
        key={box.id}
        className="absolute pointer-events-none"
        style={{
          left: box.x * scale.scaleX,
          top: box.y * scale.scaleY,
          width: box.width * scale.scaleX,
          height: box.height * scale.scaleY,
          border: `2px solid ${colors.border}`,
          backgroundColor: colors.bg,
          zIndex: 10
        }}
      >
        <div
          className="absolute -top-5 left-0 px-1 py-0.5 text-xs font-medium rounded whitespace-nowrap"
          style={{ backgroundColor: colors.border, color: 'white' }}
        >
          {box.label} {box.confidence > 0 && `(${Math.round(box.confidence * 100)}%)`}
        </div>
      </div>
    );
  };

  // Render OCR region
  const renderOCRRegion = (region: OCRRegion) => (
    <div
      key={region.id}
      className="absolute pointer-events-none"
      style={{
        left: region.x * scale.scaleX,
        top: region.y * scale.scaleY,
        width: region.width * scale.scaleX,
        height: region.height * scale.scaleY,
        border: '2px dashed #a855f7',
        backgroundColor: 'rgba(168, 85, 247, 0.1)',
        zIndex: 5
      }}
    >
      {(region.name || region.text) && (
        <div
          className="absolute -top-5 left-0 px-1 py-0.5 text-xs font-medium bg-purple-600 text-white rounded whitespace-nowrap max-w-[200px] truncate"
          title={region.text || region.name}
        >
          {region.name || region.text.substring(0, 30)}
        </div>
      )}
    </div>
  );

  // Render click target crosshair
  const renderClickTarget = () => {
    if (!clickTarget) {return null;}

    const x = clickTarget.x * scale.scaleX;
    const y = clickTarget.y * scale.scaleY;

    return (
      <div
        className="absolute pointer-events-none z-20"
        style={{ left: x - 12, top: y - 12 }}
      >
        <div className="relative w-6 h-6">
          <div className="absolute w-full h-0.5 bg-red-500 top-1/2 -translate-y-1/2" />
          <div className="absolute h-full w-0.5 bg-red-500 left-1/2 -translate-x-1/2" />
          <div className="absolute w-4 h-4 border-2 border-red-500 rounded-full top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 animate-pulse" />
        </div>
        <Badge
          variant="destructive"
          className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-xs whitespace-nowrap"
        >
          ({clickTarget.x}, {clickTarget.y})
        </Badge>
      </div>
    );
  };

  // Render drawing rectangle preview
  const renderDrawingPreview = () => {
    if (!isDrawing || !drawStart || !drawCurrent) {return null;}

    const x = Math.min(drawStart.x, drawCurrent.x) * scale.scaleX;
    const y = Math.min(drawStart.y, drawCurrent.y) * scale.scaleY;
    const width = Math.abs(drawCurrent.x - drawStart.x) * scale.scaleX;
    const height = Math.abs(drawCurrent.y - drawStart.y) * scale.scaleY;

    return (
      <div
        className="absolute pointer-events-none z-30 border-2 border-dashed border-cyan-400 bg-cyan-400/20"
        style={{ left: x, top: y, width, height }}
      />
    );
  };

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full bg-gray-900 overflow-hidden ${className}`}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{ cursor: enableOCRDrawing ? 'crosshair' : (onClickPosition ? 'pointer' : 'default') }}
    >
      {frame ? (
        <>
          {/* Main image - fills container while maintaining aspect ratio */}
          <img
            ref={imageRef}
            src={frame.data.startsWith('data:') ? frame.data : `data:image/jpeg;base64,${frame.data}`}
            alt="Live Stream"
            className="w-full h-full object-contain"
            draggable={false}
            onLoad={updateScale}
          />

          {/* Overlay container - matches image position */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div
              className="relative"
              style={{
                width: frame.width * scale.scaleX,
                height: frame.height * scale.scaleY
              }}
            >
              {detectionBoxes.map(renderDetectionBox)}
              {ocrRegions.map(renderOCRRegion)}
              {renderClickTarget()}
              {renderDrawingPreview()}
            </div>
          </div>

          {/* Minimal status overlay */}
          <div className="absolute top-2 left-2 flex gap-1">
            {enableOCRDrawing && (
              <Badge variant="secondary" className="text-xs bg-cyan-900/80">
                Draw OCR Region
              </Badge>
            )}
          </div>
        </>
      ) : (
        <div className="flex items-center justify-center h-full">
          <div className="text-center text-gray-500">
            <Monitor className="w-12 h-12 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No stream</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default LiveStreamWithDetection;
