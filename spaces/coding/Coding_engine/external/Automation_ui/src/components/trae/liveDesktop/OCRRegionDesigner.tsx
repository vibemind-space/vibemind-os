/**
 * OCR Region Designer Component
 * Interactive canvas overlay for drawing and managing OCR regions
 */

import React, { useRef, useCallback, useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Trash2, Edit2, Eye, EyeOff, Plus, Target } from 'lucide-react';
import { OCRRegion } from '@/types/liveDesktop';
import { useToast } from '@/hooks/use-toast';

interface OCRRegionDesignerProps {
  width: number;
  height: number;
  regions: OCRRegion[];
  onRegionsChange: (regions: OCRRegion[]) => void;
  isDrawingEnabled: boolean;
  onDrawingToggle: (enabled: boolean) => void;
}

export const OCRRegionDesigner: React.FC<OCRRegionDesignerProps> = ({
  width,
  height,
  regions,
  onRegionsChange,
  isDrawingEnabled,
  onDrawingToggle
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [currentRegion, setCurrentRegion] = useState<Partial<OCRRegion> | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const { toast } = useToast();

  // Draw all regions on canvas
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
      
      // Region colors
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
      label: `Region ${regions.length + 1}`,
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
      onRegionsChange([...regions, newRegion]);
      toast({
        title: "Region Created",
        description: `OCR region "${newRegion.label}" has been added`,
      });
    }

    setIsDrawing(false);
    setCurrentRegion(null);
  }, [isDrawing, currentRegion, regions, onRegionsChange, toast]);

  const updateRegion = useCallback((regionId: string, updates: Partial<OCRRegion>) => {
    const updatedRegions = regions.map(region =>
      region.id === regionId ? { ...region, ...updates } : region
    );
    onRegionsChange(updatedRegions);
  }, [regions, onRegionsChange]);

  const deleteRegion = useCallback((regionId: string) => {
    const updatedRegions = regions.filter(region => region.id !== regionId);
    onRegionsChange(updatedRegions);
    if (selectedRegion === regionId) {
      setSelectedRegion(null);
    }
    toast({
      title: "Region Deleted",
      description: "OCR region has been removed",
    });
  }, [regions, onRegionsChange, selectedRegion, toast]);

  // Redraw when regions change
  useEffect(() => {
    drawRegions();
  }, [drawRegions]);

  return (
    <div className="space-y-4">
      {/* Drawing Controls */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-lg flex items-center gap-2">
            <Target className="w-5 h-5" />
            OCR Region Designer
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Switch
                checked={isDrawingEnabled}
                onCheckedChange={onDrawingToggle}
              />
              <Label>Enable Region Drawing</Label>
            </div>
            <Badge variant={isDrawingEnabled ? "default" : "secondary"}>
              {isDrawingEnabled ? "Drawing Mode" : "View Mode"}
            </Badge>
          </div>

          {isDrawingEnabled && (
            <div className="text-sm text-muted-foreground p-3 bg-muted rounded-lg">
              <p>• Click and drag on the live desktop to create OCR regions</p>
              <p>• Click on existing regions to select them</p>
              <p>• Use the region list below to manage your regions</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Canvas Overlay */}
      <div className="relative">
        <canvas
          ref={canvasRef}
          width={width}
          height={height}
          className={`absolute inset-0 z-10 ${isDrawingEnabled ? 'cursor-crosshair' : 'cursor-default'}`}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          style={{ pointerEvents: isDrawingEnabled ? 'auto' : 'none' }}
        />
      </div>

      {/* Region Management */}
      {regions.length > 0 && (
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">OCR Regions ({regions.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {regions.map((region) => (
                <div
                  key={region.id}
                  className={`p-3 border rounded-lg transition-colors ${
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
                      
                      <div className="space-y-1">
                        <Input
                          value={region.label}
                          onChange={(e) => updateRegion(region.id, { label: e.target.value })}
                          className="h-8 text-sm font-medium"
                        />
                        <div className="text-xs text-muted-foreground">
                          {Math.round(region.x)}, {Math.round(region.y)} • {Math.round(region.width)} × {Math.round(region.height)}
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
                        <Edit2 className="w-4 h-4" />
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
                    <div className="mt-2 p-2 bg-muted rounded text-sm">
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