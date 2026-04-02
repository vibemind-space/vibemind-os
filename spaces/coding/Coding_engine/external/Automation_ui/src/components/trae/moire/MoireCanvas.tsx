import React, { useRef, useEffect, useCallback, useState, memo } from 'react';
import type { CanvasData, DetectionBox, LayerVisibility, CanvasCommand } from './types';

interface MoireCanvasProps {
  /** Detection data to display */
  data?: CanvasData;
  /** Background image URL (live frame) */
  backgroundImage?: string;
  /** Whether auto-refresh is enabled */
  autoRefresh?: boolean;
  /** Auto-refresh interval in ms */
  autoRefreshInterval?: number;
  /** Called when refresh is requested */
  onRefreshRequest?: () => void;
  /** Called when a box is clicked */
  onBoxClick?: (box: DetectionBox) => void;
  /** Called when moiré toggle changes */
  onMoireToggle?: (enabled: boolean) => void;
  /** Called for any command */
  onCommand?: (command: CanvasCommand) => void;
  /** Height of the canvas container */
  height?: string | number;
  /** Whether moiré detection is enabled */
  moireEnabled?: boolean;
  /** Connection status */
  isConnected?: boolean;
}

/**
 * MoireCanvas React Component
 * 
 * Displays detection boxes overlaid on a live stream frame.
 * Supports pan, zoom, layer visibility, and auto-refresh.
 */
export const MoireCanvas: React.FC<MoireCanvasProps> = memo(({
  data,
  backgroundImage,
  autoRefresh = false,
  autoRefreshInterval = 5000,
  onRefreshRequest,
  onBoxClick,
  onMoireToggle,
  onCommand,
  height = '600px',
  moireEnabled = false,
  isConnected = false
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  
  // Canvas state
  const [zoom, setZoom] = useState(1);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [lastPos, setLastPos] = useState({ x: 0, y: 0 });
  const [highlightedBoxes, setHighlightedBoxes] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [status, setStatus] = useState('Ready');
  
  // Layer visibility
  const [layers, setLayers] = useState<LayerVisibility>({
    components: true,
    icons: true,
    texts: true,
    regions: false
  });
  
  // Local auto-refresh state
  const [localAutoRefresh, setLocalAutoRefresh] = useState(autoRefresh);
  const autoRefreshTimerRef = useRef<number | null>(null);

  // Sync auto-refresh with props
  useEffect(() => {
    setLocalAutoRefresh(autoRefresh);
  }, [autoRefresh]);

  // Auto-refresh logic
  useEffect(() => {
    if (autoRefreshTimerRef.current) {
      clearInterval(autoRefreshTimerRef.current);
      autoRefreshTimerRef.current = null;
    }

    if (localAutoRefresh && onRefreshRequest) {
      autoRefreshTimerRef.current = window.setInterval(() => {
        onRefreshRequest();
        setStatus('Auto-refreshing...');
      }, autoRefreshInterval);
    }

    return () => {
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, [localAutoRefresh, autoRefreshInterval, onRefreshRequest]);

  // Fit to content
  const fitToContent = useCallback(() => {
    if (!data?.boxes.length || !containerRef.current) return;

    let minX = Infinity, minY = Infinity, maxX = 0, maxY = 0;
    data.boxes.forEach(b => {
      minX = Math.min(minX, b.x);
      minY = Math.min(minY, b.y);
      maxX = Math.max(maxX, b.x + b.width);
      maxY = Math.max(maxY, b.y + b.height);
    });

    const contentW = maxX - minX;
    const contentH = maxY - minY;
    const viewW = containerRef.current.clientWidth;
    const viewH = containerRef.current.clientHeight;

    const newZoom = Math.min(viewW / contentW, viewH / contentH) * 0.9;
    setZoom(newZoom);
    setPanX((viewW - contentW * newZoom) / 2 - minX * newZoom);
    setPanY((viewH - contentH * newZoom) / 2 - minY * newZoom);
    setStatus('Fitted to content');
  }, [data]);

  // Search functionality
  const handleSearch = useCallback(() => {
    if (!searchQuery || !data?.boxes) {
      setHighlightedBoxes(new Set());
      return;
    }

    const lower = searchQuery.toLowerCase();
    const matchingIds = new Set<number>();
    data.boxes.forEach(box => {
      if (box.text && box.text.toLowerCase().includes(lower)) {
        matchingIds.add(box.id);
      }
    });

    setHighlightedBoxes(matchingIds);
    setStatus(`Found ${matchingIds.size} matches`);

    // Pan to first match
    if (matchingIds.size > 0 && containerRef.current) {
      const firstId = Array.from(matchingIds)[0];
      const firstBox = data.boxes.find(b => b.id === firstId);
      if (firstBox) {
        setPanX(containerRef.current.clientWidth / 2 - (firstBox.x + firstBox.width / 2) * zoom);
        setPanY(containerRef.current.clientHeight / 2 - (firstBox.y + firstBox.height / 2) * zoom);
      }
    }
  }, [searchQuery, data, zoom]);

  // Mouse handlers for pan
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.target === containerRef.current || e.target === canvasRef.current) {
      setIsDragging(true);
      setLastPos({ x: e.clientX, y: e.clientY });
    }
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging) {
      setPanX(prev => prev + e.clientX - lastPos.x);
      setPanY(prev => prev + e.clientY - lastPos.y);
      setLastPos({ x: e.clientX, y: e.clientY });
    }
  }, [isDragging, lastPos]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Wheel handler for zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.max(0.1, Math.min(10, zoom * delta));

    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setPanX(x - (x - panX) * (newZoom / zoom));
    setPanY(y - (y - panY) * (newZoom / zoom));
    setZoom(newZoom);
  }, [zoom, panX, panY]);

  // Toggle layer
  const toggleLayer = useCallback((layer: keyof LayerVisibility) => {
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }));
    setStatus(`Layer ${layer}: ${!layers[layer] ? 'visible' : 'hidden'}`);
  }, [layers]);

  // Handle moiré toggle
  const handleMoireToggle = useCallback(() => {
    onMoireToggle?.(!moireEnabled);
    onCommand?.({ action: 'toggle_moire' });
    setStatus(`Moiré: ${!moireEnabled ? 'ON' : 'OFF'}`);
  }, [moireEnabled, onMoireToggle, onCommand]);

  // Handle auto-refresh toggle
  const handleAutoRefreshToggle = useCallback(() => {
    const newValue = !localAutoRefresh;
    setLocalAutoRefresh(newValue);
    setStatus(`Auto-refresh: ${newValue ? 'ON' : 'OFF'}`);
  }, [localAutoRefresh]);

  // Handle manual refresh
  const handleRefresh = useCallback(() => {
    onRefreshRequest?.();
    onCommand?.({ action: 'refresh_canvas' });
    setStatus('Refreshing...');
  }, [onRefreshRequest, onCommand]);

  // Tooltip handlers
  const showTooltip = useCallback((e: React.MouseEvent, box: DetectionBox) => {
    if (!tooltipRef.current) return;
    tooltipRef.current.innerHTML = `
      <strong>Box #${box.id}</strong><br/>
      Position: (${box.x}, ${box.y})<br/>
      Size: ${box.width} x ${box.height}<br/>
      ${box.text ? `Text: ${box.text}<br/>` : '<em>No OCR text</em><br/>'}
      Confidence: ${(box.confidence * 100).toFixed(1)}%
    `;
    tooltipRef.current.style.display = 'block';
    tooltipRef.current.style.left = `${e.clientX + 15}px`;
    tooltipRef.current.style.top = `${e.clientY + 15}px`;
  }, []);

  const hideTooltip = useCallback(() => {
    if (tooltipRef.current) {
      tooltipRef.current.style.display = 'none';
    }
  }, []);

  // Handle box click
  const handleBoxClick = useCallback((box: DetectionBox) => {
    onBoxClick?.(box);
    setStatus(`Selected box #${box.id}`);
  }, [onBoxClick]);

  // Calculate stats
  const stats = data ? {
    boxes: data.boxes.length,
    ocr: data.boxes.filter(b => b.text).length,
    zoom: Math.round(zoom * 100)
  } : { boxes: 0, ocr: 0, zoom: 100 };

  return (
    <div className="flex flex-col h-full bg-slate-900 text-white font-sans">
      {/* Toolbar */}
      <div className="h-10 bg-slate-800 flex items-center px-3 gap-3 border-b border-slate-700 flex-shrink-0">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="Search text..."
          className="px-3 py-1 border border-slate-600 rounded bg-slate-900 text-white w-48"
        />
        <button
          onClick={handleSearch}
          className="px-4 py-1 bg-rose-500 hover:bg-rose-400 rounded text-white"
        >
          Search
        </button>
        <button
          onClick={fitToContent}
          className="px-4 py-1 bg-rose-500 hover:bg-rose-400 rounded text-white"
        >
          Fit
        </button>
        <span className="ml-auto text-xs text-slate-400">
          Boxes: {stats.boxes} | OCR: {stats.ocr} | Zoom: {stats.zoom}%
          {!isConnected && <span className="text-red-400 ml-2">● Disconnected</span>}
          {isConnected && <span className="text-green-400 ml-2">● Connected</span>}
        </span>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto flex-shrink-0">
          <h3 className="text-teal-400 text-xs uppercase tracking-wide mb-2">Options</h3>
          
          <label className="flex items-center mb-2 cursor-pointer text-sm">
            <input
              type="checkbox"
              checked={localAutoRefresh}
              onChange={handleAutoRefreshToggle}
              className="mr-2"
            />
            Auto Refresh ({autoRefreshInterval / 1000}s)
          </label>
          
          <label className="flex items-center mb-2 cursor-pointer text-sm">
            <input
              type="checkbox"
              checked={moireEnabled}
              onChange={handleMoireToggle}
              className="mr-2"
            />
            Toggle Moiré
          </label>

          <h3 className="text-teal-400 text-xs uppercase tracking-wide mt-4 mb-2">Layers</h3>
          
          {(['components', 'icons', 'texts', 'regions'] as const).map(layer => (
            <label key={layer} className="flex items-center mb-2 cursor-pointer text-sm">
              <input
                type="checkbox"
                checked={layers[layer]}
                onChange={() => toggleLayer(layer)}
                className="mr-2"
              />
              {layer.charAt(0).toUpperCase() + layer.slice(1)}
            </label>
          ))}

          <h3 className="text-teal-400 text-xs uppercase tracking-wide mt-4 mb-2">Actions</h3>
          
          <button
            onClick={handleRefresh}
            className="w-full px-3 py-2 bg-rose-500 hover:bg-rose-400 rounded text-white text-sm mb-2"
          >
            Refresh Canvas
          </button>

          <h3 className="text-teal-400 text-xs uppercase tracking-wide mt-4 mb-2">Status</h3>
          <div className="text-xs text-slate-400 p-2 bg-slate-900 rounded min-h-[40px]">
            {status}
          </div>
        </div>

        {/* Canvas Container */}
        <div
          ref={containerRef}
          className="flex-1 overflow-hidden cursor-grab active:cursor-grabbing relative"
          style={{ height }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
        >
          <div
            ref={canvasRef}
            className="absolute origin-top-left"
            style={{
              transform: `translate(${panX}px, ${panY}px) scale(${zoom})`
            }}
          >
            {/* Background image */}
            {backgroundImage && (
              <img
                src={backgroundImage}
                alt="Stream frame"
                className="absolute left-0 top-0 -z-10 pointer-events-none opacity-80"
              />
            )}

            {/* Regions */}
            {layers.regions && data?.regions?.map(region => (
              <div
                key={region.id}
                className="absolute border-2 border-dashed border-rose-400 bg-rose-500/5 pointer-events-none -z-10"
                style={{
                  left: region.min_x,
                  top: region.min_y,
                  width: region.max_x - region.min_x,
                  height: region.max_y - region.min_y
                }}
              />
            ))}

            {/* Boxes */}
            {data?.boxes.map(box => {
              const isHighlighted = highlightedBoxes.has(box.id);
              
              return (
                <div
                  key={box.id}
                  onClick={() => handleBoxClick(box)}
                  onMouseEnter={(e) => showTooltip(e, box)}
                  onMouseLeave={hideTooltip}
                  className={`
                    absolute border-2 cursor-pointer transition-all duration-150
                    ${layers.components ? '' : 'border-transparent bg-transparent'}
                    ${isHighlighted 
                      ? 'border-yellow-400 bg-yellow-400/30 shadow-[0_0_10px_#ffe66d]' 
                      : 'border-teal-400 bg-teal-400/10 hover:border-rose-400 hover:bg-rose-400/20 hover:scale-[1.02] hover:z-50'
                    }
                  `}
                  style={{
                    left: box.x,
                    top: box.y,
                    width: box.width,
                    height: box.height
                  }}
                >
                  {/* Icon */}
                  {box.icon_file && layers.icons && (
                    <img
                      src={box.icon_file}
                      alt=""
                      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 max-w-[90%] max-h-[90%] object-contain pointer-events-none"
                    />
                  )}
                  
                  {/* Text label */}
                  {box.text && layers.texts && (
                    <div className="absolute -bottom-5 left-0 text-[10px] text-teal-400 whitespace-nowrap max-w-[150px] overflow-hidden text-ellipsis drop-shadow-[1px_1px_2px_#000]">
                      {box.text}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Minimap */}
          <div className="absolute bottom-3 right-3 w-44 h-28 bg-slate-800 border border-slate-700 rounded overflow-hidden">
            <div 
              className="absolute border-2 border-rose-500 bg-rose-500/20"
              style={{
                width: containerRef.current ? (containerRef.current.clientWidth / zoom) * 0.1 : 50,
                height: containerRef.current ? (containerRef.current.clientHeight / zoom) * 0.1 : 30,
                left: -panX / zoom * 0.1,
                top: -panY / zoom * 0.1
              }}
            />
          </div>
        </div>
      </div>

      {/* Tooltip */}
      <div
        ref={tooltipRef}
        className="fixed bg-slate-800 border border-slate-700 p-3 rounded-md text-xs pointer-events-none z-[2000] max-w-[300px] hidden"
      />
    </div>
  );
});

MoireCanvas.displayName = 'MoireCanvas';

export default MoireCanvas;