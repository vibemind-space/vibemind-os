/**
 * MoireDetectionOverlay
 *
 * Renders detection boxes from MoireServer over a canvas or image.
 * Supports click-to-select and category color coding.
 */

import React, { useCallback, useMemo } from 'react';
import { MoireDetectionBox } from '@/services/moireDetectionService';

export interface MoireDetectionOverlayProps {
  boxes: MoireDetectionBox[];
  containerWidth: number;
  containerHeight: number;
  imageWidth?: number;
  imageHeight?: number;
  selectedBoxId?: string | null;
  onBoxClick?: (box: MoireDetectionBox) => void;
  onBoxHover?: (box: MoireDetectionBox | null) => void;
  showLabels?: boolean;
  showConfidence?: boolean;
  opacity?: number;
}

// Category colors for visual distinction
const CATEGORY_COLORS: Record<string, string> = {
  button: '#22c55e', // green
  input: '#3b82f6', // blue
  text: '#f59e0b', // amber
  icon: '#8b5cf6', // violet
  image: '#ec4899', // pink
  link: '#06b6d4', // cyan
  checkbox: '#84cc16', // lime
  dropdown: '#f97316', // orange
  default: '#6b7280', // gray
};

function getCategoryColor(category?: string): string {
  if (!category) return CATEGORY_COLORS.default;
  return CATEGORY_COLORS[category.toLowerCase()] || CATEGORY_COLORS.default;
}

export const MoireDetectionOverlay: React.FC<MoireDetectionOverlayProps> = ({
  boxes,
  containerWidth,
  containerHeight,
  imageWidth,
  imageHeight,
  selectedBoxId,
  onBoxClick,
  onBoxHover,
  showLabels = true,
  showConfidence = true,
  opacity = 0.8,
}) => {
  // Calculate scale factors for positioning
  const scaleX = useMemo(() => {
    if (!imageWidth || imageWidth === 0) return 1;
    return containerWidth / imageWidth;
  }, [containerWidth, imageWidth]);

  const scaleY = useMemo(() => {
    if (!imageHeight || imageHeight === 0) return 1;
    return containerHeight / imageHeight;
  }, [containerHeight, imageHeight]);

  // Scale a box to container coordinates
  const scaleBox = useCallback(
    (box: MoireDetectionBox) => ({
      ...box,
      x: box.x * scaleX,
      y: box.y * scaleY,
      width: box.width * scaleX,
      height: box.height * scaleY,
    }),
    [scaleX, scaleY]
  );

  const handleBoxClick = useCallback(
    (box: MoireDetectionBox, e: React.MouseEvent) => {
      e.stopPropagation();
      onBoxClick?.(box);
    },
    [onBoxClick]
  );

  const handleBoxMouseEnter = useCallback(
    (box: MoireDetectionBox) => {
      onBoxHover?.(box);
    },
    [onBoxHover]
  );

  const handleBoxMouseLeave = useCallback(() => {
    onBoxHover?.(null);
  }, [onBoxHover]);

  if (boxes.length === 0) {
    return null;
  }

  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{ width: containerWidth, height: containerHeight }}
    >
      {boxes.map((box) => {
        const scaledBox = scaleBox(box);
        const color = getCategoryColor(box.category);
        const isSelected = box.id === selectedBoxId;

        return (
          <div
            key={box.id}
            className="absolute pointer-events-auto cursor-pointer transition-all duration-150"
            style={{
              left: scaledBox.x,
              top: scaledBox.y,
              width: scaledBox.width,
              height: scaledBox.height,
              border: `2px solid ${color}`,
              backgroundColor: isSelected
                ? `${color}33`
                : `${color}11`,
              opacity,
              boxShadow: isSelected
                ? `0 0 0 2px ${color}, 0 0 10px ${color}66`
                : 'none',
            }}
            onClick={(e) => handleBoxClick(box, e)}
            onMouseEnter={() => handleBoxMouseEnter(box)}
            onMouseLeave={handleBoxMouseLeave}
          >
            {/* Label */}
            {showLabels && (box.category || box.text || box.ocrText) && (
              <div
                className="absolute -top-6 left-0 px-1.5 py-0.5 text-xs font-medium text-white rounded whitespace-nowrap"
                style={{
                  backgroundColor: color,
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {box.category && <span>{box.category}</span>}
                {box.ocrText && (
                  <span className="ml-1 opacity-80">
                    "{box.ocrText.slice(0, 20)}
                    {box.ocrText.length > 20 ? '...' : ''}"
                  </span>
                )}
              </div>
            )}

            {/* Confidence badge */}
            {showConfidence && box.confidence !== undefined && (
              <div
                className="absolute -bottom-5 left-0 px-1 py-0.5 text-xs text-white rounded"
                style={{ backgroundColor: color }}
              >
                {Math.round(box.confidence * 100)}%
              </div>
            )}

            {/* Box ID (for debugging) */}
            <div
              className="absolute bottom-0 right-0 px-1 text-[10px] text-white/60 bg-black/40 rounded-tl"
            >
              {box.id.slice(0, 6)}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default MoireDetectionOverlay;
