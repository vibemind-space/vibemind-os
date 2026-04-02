/**
 * Fixed Size OCR Region Designer for Live Desktop
 * Interactive canvas overlay with 1200x900 fixed dimensions
 */

import React, { useRef, useCallback, useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Trash2, Eye, EyeOff, Target, Save, Settings } from 'lucide-react';
import { OCRRegion, LiveDesktopConfig } from '@/types/liveDesktop';
import { useToast } from '@/hooks/use-toast';

interface FixedSizeOCRDesignerProps {
  config?: LiveDesktopConfig;
  onConfigChange?: (config: LiveDesktopConfig) => void;
  className?: string;
}

export const FixedSizeOCRDesigner: React.FC<FixedSizeOCRDesignerProps> = ({
  config,
  onConfigChange,
  className = ""
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamCanvasRef = useRef<HTMLCanvasElement>(null);
  const [regions, setRegions] = useState<OCRRegion[]>(config?.ocrRegions || []);
  const [currentRegion, setCurrentRegion] = useState<Partial<OCRRegion> | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [isDrawingEnabled, setIsDrawingEnabled] = useState(false);
  const { toast } = useToast();

  // Fixed canvas dimensions as requested
  const CANVAS_WIDTH = 1200;
  const CANVAS_HEIGHT = 900;

  // Mock desktop stream for visualization
  useEffect(() => {
    const streamCanvas = streamCanvasRef.current;
    if (!streamCanvas) return;

    const ctx = streamCanvas.getContext('2d');
    if (!ctx) return;

    // Create a simple mock desktop background
    const gradient = ctx.createLinearGradient(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    gradient.addColorStop(0, '#1e40af');
    gradient.addColorStop(1, '#3b82f6');
    
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    // Add some mock UI elements
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(100, 100, 300, 200);
    ctx.fillStyle = '#ef4444';
    ctx.fillRect(500, 150, 200, 100);
    ctx.fillStyle = '#10b981';
    ctx.fillRect(200, 400, 400, 150);

    // Add mock text
    ctx.fillStyle = '#000000';
    ctx.font = '16px Arial';
    ctx.fillText('Mock Desktop Application', 120, 140);
    ctx.fillText('Button Area', 520, 190);
    ctx.fillText('Data Section', 220, 460);
  }, []);

  // Draw all regions on overlay canvas
  const drawRegions = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw existing regions
    regions.forEach((region) => {
      const isSelected = selectedRegion === region.id;
      const isActive = region.isActive;
      
      // Region colors using design system
      ctx.strokeStyle = isSelected ? '#ef4444' : isActive ? '#3b82f6' : '#6b7280';
      ctx.fillStyle = isSelected ? 'rgba(239, 68, 68, 0.1)' : isActive ? 'rgba(59, 130, 246, 0.1)' : 'rgba(107, 114, 128, 0.1)';
      ctx.lineWidth = isSelected ? 3 : 2;

      // Draw region rectangle
      ctx.fillRect(region.x, region.y, region.width, region.height);
      ctx.strokeRect(region.x, region.y, region.width, region.height);

      // Draw label
      ctx.fillStyle = isSelected ? '#ef4444' : isActive ? '#3b82f6' : '#6b7280';
      ctx.font = '500 12px Inter, sans-serif';
      const labelY = region.y > 20 ? region.y - 4 : region.y + region.height + 16;
      ctx.fillText(region.label, region.x, labelY);

      // Draw status indicator
      if (isActive) {
        ctx.fillStyle = '#10b981';
        ctx.beginPath();
        ctx.arc(region.x + region.width - 8, region.y + 8, 4, 0, 2 * Math.PI);
        ctx.fill();
      }
    });

    // Draw current region being drawn
    if (currentRegion && currentRegion.x !== undefined && currentRegion.y !== undefined) {
      ctx.strokeStyle = '#f59e0b';
      ctx.fillStyle = 'rgba(245, 158, 11, 0.1)';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);

      const x = currentRegion.x;
      const y = currentRegion.y;
      const w = currentRegion.width || 0;
      const h = currentRegion.height || 0;

      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);
    }
  }, [regions, selectedRegion, currentRegion]);

  // Handle mouse events for drawing regions
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawingEnabled) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Check if clicking on existing region
    const clickedRegion = regions.find(region =>
      x >= region.x && x <= region.x + region.width &&
      y >= region.y && y <= region.y + region.height
    );

    if (clickedRegion) {
      setSelectedRegion(clickedRegion.id);
      return;
    }

    // Start drawing new region
    setIsDrawing(true);
    setSelectedRegion(null);
    setCurrentRegion({ x, y, width: 0, height: 0 });
  }, [isDrawingEnabled, regions]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || !currentRegion) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const currentX = e.clientX - rect.left;
    const currentY = e.clientY - rect.top;

    setCurrentRegion(prev => ({
      ...prev,
      width: currentX - (prev?.x || 0),
      height: currentY - (prev?.y || 0)
    }));

    drawRegions();
  }, [isDrawing, currentRegion, drawRegions]);

  const handleMouseUp = useCallback(() => {
    if (!isDrawing || !currentRegion) return;

    const newRegion: OCRRegion = {
      id: `region-${Date.now()}`,
      label: `OCR Zone ${regions.length + 1}`,
      x: Math.min(currentRegion.x || 0, (currentRegion.x || 0) + (currentRegion.width || 0)),
      y: Math.min(currentRegion.y || 0, (currentRegion.y || 0) + (currentRegion.height || 0)),
      width: Math.abs(currentRegion.width || 0),
      height: Math.abs(currentRegion.height || 0),
      isActive: true,
      lastExtractedText: '',
      extractionHistory: []
    };

    // Only add if region is large enough
    if (newRegion.width > 10 && newRegion.height > 10) {
      const updatedRegions = [...regions, newRegion];
      setRegions(updatedRegions);
      
      // Update config if provided
      if (config && onConfigChange) {
        onConfigChange({
          ...config,
          ocrRegions: updatedRegions,
          updatedAt: new Date().toISOString()
        });
      }

      toast({
        title: "OCR Zone Created",
        description: `Zone "${newRegion.label}" added at ${Math.round(newRegion.x)},${Math.round(newRegion.y)}`,
      });
    }

    setIsDrawing(false);
    setCurrentRegion(null);
  }, [isDrawing, currentRegion, regions, config, onConfigChange, toast]);

  const updateRegion = useCallback((regionId: string, updates: Partial<OCRRegion>) => {
    const updatedRegions = regions.map(region =>
      region.id === regionId ? { ...region, ...updates } : region
    );
    setRegions(updatedRegions);
    
    if (config && onConfigChange) {
      onConfigChange({
        ...config,
        ocrRegions: updatedRegions,
        updatedAt: new Date().toISOString()
      });
    }
  }, [regions, config, onConfigChange]);

  const deleteRegion = useCallback((regionId: string) => {
    const updatedRegions = regions.filter(region => region.id !== regionId);
    setRegions(updatedRegions);
    
    if (selectedRegion === regionId) {
      setSelectedRegion(null);
    }
    
    if (config && onConfigChange) {
      onConfigChange({
        ...config,
        ocrRegions: updatedRegions,
        updatedAt: new Date().toISOString()
      });
    }

    toast({
      title: "OCR Zone Deleted",
      description: "Zone has been removed from configuration",
    });
  }, [regions, selectedRegion, config, onConfigChange, toast]);

  // Redraw when regions change
  useEffect(() => {
    drawRegions();
  }, [drawRegions]);

  // Update regions when config changes
  useEffect(() => {
    if (config?.ocrRegions) {
      setRegions(config.ocrRegions);
    }
  }, [config?.ocrRegions]);

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Header */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-xl flex items-center gap-2">
            <Target className="w-6 h-6" />
            OCR Zone Designer (1200×900)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Switch
                checked={isDrawingEnabled}
                onCheckedChange={setIsDrawingEnabled}
              />
              <span className="font-medium">Enable Zone Drawing</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={isDrawingEnabled ? "default" : "secondary"}>
                {isDrawingEnabled ? "Drawing Mode" : "View Mode"}
              </Badge>
              <Badge variant="outline">
                {regions.length} zones
              </Badge>
            </div>
          </div>

          {isDrawingEnabled && (
            <div className="text-sm text-muted-foreground p-3 bg-muted rounded-lg">
              <p>• Click and drag on the desktop preview to create OCR zones</p>
              <p>• Click on existing zones to select and configure them</p>
              <p>• Each zone will be tracked independently for text extraction</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Fixed Size Desktop Canvas */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-lg flex items-center justify-between">
            Live Desktop Preview
            <div className="text-sm font-normal text-muted-foreground">
              {CANVAS_WIDTH} × {CANVAS_HEIGHT}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative border rounded-lg overflow-hidden bg-muted">
            {/* Background desktop stream */}
            <canvas
              ref={streamCanvasRef}
              width={CANVAS_WIDTH}
              height={CANVAS_HEIGHT}
              className="block"
              style={{ width: '100%', height: 'auto', maxWidth: '100%' }}
            />
            
            {/* OCR regions overlay */}
            <canvas
              ref={canvasRef}
              width={CANVAS_WIDTH}
              height={CANVAS_HEIGHT}
              className={`absolute inset-0 ${isDrawingEnabled ? 'cursor-crosshair' : 'cursor-default'}`}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              style={{ 
                pointerEvents: isDrawingEnabled ? 'auto' : 'none',
                width: '100%', 
                height: 'auto', 
                maxWidth: '100%' 
              }}
            />
          </div>
        </CardContent>
      </Card>

      {/* OCR Zones Management */}
      {regions.length > 0 && (
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-lg flex items-center justify-between">
              OCR Zones ({regions.length})
              <Button variant="outline" size="sm">
                <Save className="w-4 h-4 mr-2" />
                Save Config
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {regions.map((region) => (
                <div
                  key={region.id}
                  className={`p-4 border rounded-lg transition-colors ${
                    selectedRegion === region.id ? 'border-primary bg-primary/5' : 'border-border'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => updateRegion(region.id, { isActive: !region.isActive })}
                      >
                        {region.isActive ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                      </Button>
                      
                      <div className="space-y-1 flex-1">
                        <Input
                          value={region.label}
                          onChange={(e) => updateRegion(region.id, { label: e.target.value })}
                          className="h-8 text-sm font-medium"
                        />
                        <div className="text-xs text-muted-foreground">
                          Position: {Math.round(region.x)}, {Math.round(region.y)} • 
                          Size: {Math.round(region.width)} × {Math.round(region.height)}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2">
                      <Badge variant={region.isActive ? "default" : "secondary"}>
                        {region.isActive ? "Active" : "Inactive"}
                      </Badge>
                      
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedRegion(region.id === selectedRegion ? null : region.id)}
                      >
                        <Settings className="w-4 h-4" />
                      </Button>
                      
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => deleteRegion(region.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>

                  {region.lastExtractedText && (
                    <div className="mt-3 p-2 bg-muted rounded text-sm">
                      <span className="font-medium">Last extracted:</span> {region.lastExtractedText}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};