/**
 * Multi-Desktop OCR Zone Designer Component
 * Advanced OCR zone design and testing interface for multiple desktop configurations
 * Follows TRAE Unity AI Platform naming conventions and coding standards
 * 
 * Features:
 * - Multi-desktop layout support (horizontal, vertical, grid)
 * - Interactive OCR zone design with snap-to-grid
 * - Live preview and testing capabilities
 * - Template management and versioning
 * - Zone validation and performance metrics
 * - Export configurations for workflow integration
 * 
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import React, { useRef, useCallback, useState, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { 
  Monitor, 
  Layout, 
  Grid, 
  Target, 
  Play, 
  Pause, 
  Save, 
  Download, 
  Upload,
  Settings,
  Eye,
  EyeOff,
  Trash2,
  Copy,
  RotateCcw,
  CheckCircle,
  AlertCircle,
  Info,
  Zap
} from 'lucide-react';
import { OCRRegion, LiveDesktopConfig } from '@/types/liveDesktop';
import { useToast } from '@/hooks/use-toast';

// ============================================================================
// INTERFACES & TYPES
// ============================================================================

interface DesktopConfiguration {
  id: string;
  name: string;
  resolution: { width: number; height: number };
  position: { x: number; y: number };
  isActive: boolean;
  streamUrl?: string;
  ocrZones: OCRRegion[];
}

interface OCRTemplate {
  id: string;
  name: string;
  description: string;
  version: string;
  created: string;
  desktops: DesktopConfiguration[];
  metadata: {
    totalZones: number;
    avgConfidence: number;
    lastTested: string;
  };
}

interface TestResult {
  zoneId: string;
  desktopId: string;
  confidence: number;
  extractedText: string;
  timestamp: string;
  success: boolean;
  error?: string;
}

interface MultiDesktopOCRZoneDesignerProps {
  config?: any;
  onConfigChange?: (config: any) => void;
  className?: string;
  desktopStreams?: { [desktopId: string]: string };
  isConnected?: boolean;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export const MultiDesktopOCRZoneDesigner: React.FC<MultiDesktopOCRZoneDesignerProps> = ({
  config,
  onConfigChange,
  className = "",
  desktopStreams = {},
  isConnected = false,
  onConnect,
  onDisconnect
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  // Desktop configuration state
  const [desktops, setDesktops] = useState<DesktopConfiguration[]>([
    {
      id: 'desktop-1',
      name: 'Primary Desktop',
      resolution: { width: 1920, height: 1080 },
      position: { x: 0, y: 0 },
      isActive: true,
      ocrZones: []
    },
    {
      id: 'desktop-2',
      name: 'Secondary Desktop',
      resolution: { width: 1920, height: 1080 },
      position: { x: 1920, y: 0 },
      isActive: true,
      ocrZones: []
    }
  ]);

  // Design state
  const [selectedDesktop, setSelectedDesktop] = useState<string>('desktop-1');
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [isDrawingEnabled, setIsDrawingEnabled] = useState(false);
  const [currentDrawing, setCurrentDrawing] = useState<Partial<OCRRegion> | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);

  // Configuration state
  const [designConfig, setDesignConfig] = useState({
    layout: 'horizontal' as 'horizontal' | 'vertical' | 'grid_2x2' | 'custom',
    snapToGrid: true,
    gridSize: 10,
    minZoneSize: 20,
    showGrid: true,
    showRulers: true
  });

  // Testing state
  const [isTestingEnabled, setIsTestingEnabled] = useState(false);
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [isRunningTests, setIsRunningTests] = useState(false);

  // Template state
  const [templates, setTemplates] = useState<OCRTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);

  // Canvas references
  const canvasRefs = useRef<{ [desktopId: string]: HTMLCanvasElement | null }>({});
  const overlayCanvasRefs = useRef<{ [desktopId: string]: HTMLCanvasElement | null }>({});

  const { toast } = useToast();

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  // Calculate canvas dimensions based on layout
  const canvasDimensions = useMemo(() => {
    const baseWidth = 800;
    const baseHeight = 450;
    
    switch (designConfig.layout) {
      case 'horizontal':
        return { width: baseWidth, height: baseHeight };
      case 'vertical':
        return { width: baseWidth * 0.7, height: baseHeight };
      case 'grid_2x2':
        return { width: baseWidth * 0.6, height: baseHeight * 0.6 };
      default:
        return { width: baseWidth, height: baseHeight };
    }
  }, [designConfig.layout]);

  // Get current desktop configuration
  const currentDesktop = useMemo(() => 
    desktops.find(d => d.id === selectedDesktop),
    [desktops, selectedDesktop]
  );

  // Calculate total zones across all desktops
  const totalZones = useMemo(() => 
    desktops.reduce((total, desktop) => total + desktop.ocrZones.length, 0),
    [desktops]
  );

  // ============================================================================
  // CANVAS DRAWING FUNCTIONS
  // ============================================================================

  // Draw desktop background and stream
  const drawDesktopBackground = useCallback((desktopId: string) => {
    const canvas = canvasRefs.current[desktopId];
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const desktop = desktops.find(d => d.id === desktopId);
    if (!desktop) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw stream if available
    const streamUrl = desktopStreams[desktopId];
    if (streamUrl) {
      const img = new Image();
      img.onload = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      };
      img.src = streamUrl.startsWith('data:') ? streamUrl : `data:image/jpeg;base64,${streamUrl}`;
    } else {
      // Draw placeholder background
      const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
      gradient.addColorStop(0, desktop.id === 'desktop-1' ? '#1e40af' : '#7c3aed');
      gradient.addColorStop(1, desktop.id === 'desktop-1' ? '#3b82f6' : '#a855f7');
      
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Add desktop label
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 24px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(desktop.name, canvas.width / 2, canvas.height / 2);
      ctx.textAlign = 'left';
    }

    // Draw grid if enabled
    if (designConfig.showGrid && designConfig.snapToGrid) {
      drawGrid(ctx, canvas.width, canvas.height, designConfig.gridSize);
    }
  }, [desktops, desktopStreams, designConfig]);

  // Draw grid overlay
  const drawGrid = useCallback((ctx: CanvasRenderingContext2D, width: number, height: number, gridSize: number) => {
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);

    // Vertical lines
    for (let x = 0; x <= width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // Horizontal lines
    for (let y = 0; y <= height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    ctx.setLineDash([]);
  }, []);

  // Draw OCR zones overlay
  const drawOCRZones = useCallback((desktopId: string) => {
    const canvas = overlayCanvasRefs.current[desktopId];
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const desktop = desktops.find(d => d.id === desktopId);
    if (!desktop) return;

    // Clear overlay
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw existing zones
    desktop.ocrZones.forEach((zone) => {
      const isSelected = selectedZone === zone.id;
      const isActive = zone.isActive;
      
      // Zone styling
      ctx.strokeStyle = isSelected ? '#ef4444' : isActive ? '#10b981' : '#6b7280';
      ctx.fillStyle = isSelected ? 'rgba(239, 68, 68, 0.15)' : isActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(107, 114, 128, 0.15)';
      ctx.lineWidth = isSelected ? 3 : 2;

      // Scale coordinates to canvas size
      const scaleX = canvas.width / desktop.resolution.width;
      const scaleY = canvas.height / desktop.resolution.height;
      
      const x = zone.x * scaleX;
      const y = zone.y * scaleY;
      const width = zone.width * scaleX;
      const height = zone.height * scaleY;

      // Draw zone rectangle
      ctx.fillRect(x, y, width, height);
      ctx.strokeRect(x, y, width, height);

      // Draw zone label
      ctx.fillStyle = isSelected ? '#ef4444' : isActive ? '#10b981' : '#6b7280';
      ctx.font = '500 11px Inter, sans-serif';
      const labelY = y > 20 ? y - 4 : y + height + 14;
      ctx.fillText(zone.label, x, labelY);

      // Draw status indicator
      if (isActive) {
        ctx.fillStyle = '#10b981';
        ctx.beginPath();
        ctx.arc(x + width - 6, y + 6, 3, 0, 2 * Math.PI);
        ctx.fill();
      }

      // Draw test result indicator if available
      const testResult = testResults.find(r => r.zoneId === zone.id && r.desktopId === desktopId);
      if (testResult) {
        ctx.fillStyle = testResult.success ? '#10b981' : '#ef4444';
        ctx.beginPath();
        ctx.arc(x + 6, y + 6, 3, 0, 2 * Math.PI);
        ctx.fill();
      }
    });

    // Draw current drawing zone
    if (currentDrawing && desktopId === selectedDesktop) {
      ctx.strokeStyle = '#f59e0b';
      ctx.fillStyle = 'rgba(245, 158, 11, 0.2)';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);

      const scaleX = canvas.width / desktop.resolution.width;
      const scaleY = canvas.height / desktop.resolution.height;
      
      const x = (currentDrawing.x || 0) * scaleX;
      const y = (currentDrawing.y || 0) * scaleY;
      const width = (currentDrawing.width || 0) * scaleX;
      const height = (currentDrawing.height || 0) * scaleY;

      ctx.fillRect(x, y, width, height);
      ctx.strokeRect(x, y, width, height);
      ctx.setLineDash([]);
    }
  }, [desktops, selectedZone, selectedDesktop, currentDrawing, testResults]);

  // ============================================================================
  // MOUSE EVENT HANDLERS
  // ============================================================================

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>, desktopId: string) => {
    if (!isDrawingEnabled || desktopId !== selectedDesktop) return;

    const canvas = overlayCanvasRefs.current[desktopId];
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const desktop = desktops.find(d => d.id === desktopId);
    if (!desktop) return;

    // Convert canvas coordinates to desktop coordinates
    const scaleX = desktop.resolution.width / canvas.width;
    const scaleY = desktop.resolution.height / canvas.height;
    const desktopX = x * scaleX;
    const desktopY = y * scaleY;

    // Snap to grid if enabled
    const finalX = designConfig.snapToGrid ? Math.round(desktopX / designConfig.gridSize) * designConfig.gridSize : desktopX;
    const finalY = designConfig.snapToGrid ? Math.round(desktopY / designConfig.gridSize) * designConfig.gridSize : desktopY;

    // Check if clicking on existing zone
    const clickedZone = desktop.ocrZones.find(zone =>
      finalX >= zone.x && finalX <= zone.x + zone.width &&
      finalY >= zone.y && finalY <= zone.y + zone.height
    );

    if (clickedZone) {
      setSelectedZone(clickedZone.id);
      return;
    }

    // Start drawing new zone
    setIsDrawing(true);
    setSelectedZone(null);
    setCurrentDrawing({ x: finalX, y: finalY, width: 0, height: 0 });
  }, [isDrawingEnabled, selectedDesktop, desktops, designConfig]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>, desktopId: string) => {
    if (!isDrawing || !currentDrawing || desktopId !== selectedDesktop) return;

    const canvas = overlayCanvasRefs.current[desktopId];
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const desktop = desktops.find(d => d.id === desktopId);
    if (!desktop) return;

    // Convert canvas coordinates to desktop coordinates
    const scaleX = desktop.resolution.width / canvas.width;
    const scaleY = desktop.resolution.height / canvas.height;
    const desktopX = x * scaleX;
    const desktopY = y * scaleY;

    // Snap to grid if enabled
    const finalX = designConfig.snapToGrid ? Math.round(desktopX / designConfig.gridSize) * designConfig.gridSize : desktopX;
    const finalY = designConfig.snapToGrid ? Math.round(desktopY / designConfig.gridSize) * designConfig.gridSize : desktopY;

    setCurrentDrawing(prev => ({
      ...prev,
      width: finalX - (prev?.x || 0),
      height: finalY - (prev?.y || 0)
    }));
  }, [isDrawing, currentDrawing, selectedDesktop, desktops, designConfig]);

  const handleMouseUp = useCallback(() => {
    if (!isDrawing || !currentDrawing) return;

    const desktop = desktops.find(d => d.id === selectedDesktop);
    if (!desktop) return;

    // Create new zone if large enough
    const width = Math.abs(currentDrawing.width || 0);
    const height = Math.abs(currentDrawing.height || 0);

    if (width >= designConfig.minZoneSize && height >= designConfig.minZoneSize) {
      const newZone: OCRRegion = {
        id: `zone-${Date.now()}`,
        label: `Zone ${desktop.ocrZones.length + 1}`,
        x: Math.min(currentDrawing.x || 0, (currentDrawing.x || 0) + (currentDrawing.width || 0)),
        y: Math.min(currentDrawing.y || 0, (currentDrawing.y || 0) + (currentDrawing.height || 0)),
        width,
        height,
        isActive: true,
        lastExtractedText: '',
        extractionHistory: []
      };

      // Update desktop with new zone
      setDesktops(prev => prev.map(d => 
        d.id === selectedDesktop 
          ? { ...d, ocrZones: [...d.ocrZones, newZone] }
          : d
      ));

      setSelectedZone(newZone.id);

      toast({
        title: "OCR Zone Created",
        description: `Zone "${newZone.label}" added to ${desktop.name}`,
      });
    }

    setIsDrawing(false);
    setCurrentDrawing(null);
  }, [isDrawing, currentDrawing, selectedDesktop, desktops, designConfig, toast]);

  // ============================================================================
  // ZONE MANAGEMENT FUNCTIONS
  // ============================================================================

  const updateZone = useCallback((zoneId: string, updates: Partial<OCRRegion>) => {
    setDesktops(prev => prev.map(desktop => ({
      ...desktop,
      ocrZones: desktop.ocrZones.map(zone =>
        zone.id === zoneId ? { ...zone, ...updates } : zone
      )
    })));
  }, []);

  const deleteZone = useCallback((zoneId: string) => {
    setDesktops(prev => prev.map(desktop => ({
      ...desktop,
      ocrZones: desktop.ocrZones.filter(zone => zone.id !== zoneId)
    })));

    if (selectedZone === zoneId) {
      setSelectedZone(null);
    }

    toast({
      title: "Zone Deleted",
      description: "OCR zone has been removed",
    });
  }, [selectedZone, toast]);

  const duplicateZone = useCallback((zoneId: string) => {
    const desktop = desktops.find(d => d.ocrZones.some(z => z.id === zoneId));
    const zone = desktop?.ocrZones.find(z => z.id === zoneId);
    
    if (!desktop || !zone) return;

    const newZone: OCRRegion = {
      ...zone,
      id: `zone-${Date.now()}`,
      label: `${zone.label} Copy`,
      x: zone.x + 20,
      y: zone.y + 20
    };

    setDesktops(prev => prev.map(d => 
      d.id === desktop.id 
        ? { ...d, ocrZones: [...d.ocrZones, newZone] }
        : d
    ));

    toast({
      title: "Zone Duplicated",
      description: `Zone "${newZone.label}" created`,
    });
  }, [desktops, toast]);

  // ============================================================================
  // TESTING FUNCTIONS
  // ============================================================================

  const runOCRTests = useCallback(async () => {
    setIsRunningTests(true);
    const newTestResults: TestResult[] = [];

    try {
      for (const desktop of desktops) {
        if (!desktop.isActive) continue;

        for (const zone of desktop.ocrZones) {
          if (!zone.isActive) continue;

          // Simulate OCR test (replace with actual OCR service call)
          const testResult: TestResult = {
            zoneId: zone.id,
            desktopId: desktop.id,
            confidence: Math.random() * 0.4 + 0.6, // Random confidence 0.6-1.0
            extractedText: `Sample text from ${zone.label}`,
            timestamp: new Date().toISOString(),
            success: Math.random() > 0.2 // 80% success rate
          };

          newTestResults.push(testResult);

          // Add delay to simulate processing
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }

      setTestResults(newTestResults);

      const successCount = newTestResults.filter(r => r.success).length;
      const totalCount = newTestResults.length;

      toast({
        title: "OCR Tests Completed",
        description: `${successCount}/${totalCount} zones passed validation`,
      });

    } catch (error) {
      console.error('OCR testing error:', error);
      toast({
        title: "Test Error",
        description: "Failed to complete OCR tests",
        variant: "destructive"
      });
    } finally {
      setIsRunningTests(false);
    }
  }, [desktops, toast]);

  // ============================================================================
  // TEMPLATE MANAGEMENT
  // ============================================================================

  const saveTemplate = useCallback(() => {
    const template: OCRTemplate = {
      id: `template-${Date.now()}`,
      name: `Template ${templates.length + 1}`,
      description: `Multi-desktop OCR configuration with ${totalZones} zones`,
      version: '1.0.0',
      created: new Date().toISOString(),
      desktops: desktops,
      metadata: {
        totalZones,
        avgConfidence: testResults.length > 0 
          ? testResults.reduce((sum, r) => sum + r.confidence, 0) / testResults.length 
          : 0,
        lastTested: testResults.length > 0 ? testResults[0].timestamp : ''
      }
    };

    setTemplates(prev => [...prev, template]);

    toast({
      title: "Template Saved",
      description: `Template "${template.name}" has been saved`,
    });
  }, [desktops, totalZones, testResults, templates.length, toast]);

  const loadTemplate = useCallback((templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    if (!template) return;

    setDesktops(template.desktops);
    setSelectedTemplate(templateId);

    toast({
      title: "Template Loaded",
      description: `Template "${template.name}" has been loaded`,
    });
  }, [templates, toast]);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Redraw canvases when data changes
  useEffect(() => {
    desktops.forEach(desktop => {
      drawDesktopBackground(desktop.id);
      drawOCRZones(desktop.id);
    });
  }, [desktops, drawDesktopBackground, drawOCRZones]);

  // Update canvas references
  useEffect(() => {
    desktops.forEach(desktop => {
      const canvas = canvasRefs.current[desktop.id];
      const overlayCanvas = overlayCanvasRefs.current[desktop.id];
      
      if (canvas) {
        canvas.width = canvasDimensions.width;
        canvas.height = canvasDimensions.height;
      }
      
      if (overlayCanvas) {
        overlayCanvas.width = canvasDimensions.width;
        overlayCanvas.height = canvasDimensions.height;
      }
    });
  }, [desktops, canvasDimensions]);

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const renderDesktopCanvas = (desktop: DesktopConfiguration) => (
    <div key={desktop.id} className="relative border rounded-lg overflow-hidden">
      {/* Desktop Header */}
      <div className="absolute top-0 left-0 right-0 z-10 bg-black/50 text-white p-2 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Monitor className="w-4 h-4" />
          <span className="text-sm font-medium">{desktop.name}</span>
          <Badge variant={desktop.isActive ? "default" : "secondary"} className="text-xs">
            {desktop.isActive ? "Active" : "Inactive"}
          </Badge>
        </div>
        <div className="flex items-center space-x-1">
          <Badge variant="outline" className="text-xs">
            {desktop.ocrZones.length} zones
          </Badge>
          {selectedDesktop === desktop.id && (
            <Badge variant="default" className="text-xs">
              Selected
            </Badge>
          )}
        </div>
      </div>

      {/* Canvas Container */}
      <div className="relative">
        {/* Background Canvas (Desktop Stream) */}
        <canvas
          ref={el => canvasRefs.current[desktop.id] = el}
          className="absolute inset-0"
          style={{ 
            width: canvasDimensions.width, 
            height: canvasDimensions.height 
          }}
        />
        
        {/* Overlay Canvas (OCR Zones) */}
        <canvas
          ref={el => overlayCanvasRefs.current[desktop.id] = el}
          className="absolute inset-0 cursor-crosshair"
          style={{ 
            width: canvasDimensions.width, 
            height: canvasDimensions.height 
          }}
          onMouseDown={(e) => handleMouseDown(e, desktop.id)}
          onMouseMove={(e) => handleMouseMove(e, desktop.id)}
          onMouseUp={handleMouseUp}
          onClick={() => setSelectedDesktop(desktop.id)}
        />
      </div>

      {/* Zone Count Indicator */}
      <div className="absolute bottom-2 right-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
        {desktop.ocrZones.filter(z => z.isActive).length} active zones
      </div>
    </div>
  );

  const renderZoneList = () => {
    const currentDesktopZones = currentDesktop?.ocrZones || [];
    
    return (
      <div className="space-y-2">
        {currentDesktopZones.map((zone) => (
          <Card 
            key={zone.id} 
            className={`p-3 cursor-pointer transition-colors ${
              selectedZone === zone.id ? 'ring-2 ring-blue-500' : ''
            }`}
            onClick={() => setSelectedZone(zone.id)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Target className="w-4 h-4" />
                <span className="font-medium">{zone.label}</span>
                <Badge variant={zone.isActive ? "default" : "secondary"}>
                  {zone.isActive ? "Active" : "Inactive"}
                </Badge>
              </div>
              <div className="flex items-center space-x-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    duplicateZone(zone.id);
                  }}
                >
                  <Copy className="w-3 h-3" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteZone(zone.id);
                  }}
                >
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
            </div>
            
            <div className="mt-2 text-sm text-muted-foreground">
              Position: {Math.round(zone.x)}, {Math.round(zone.y)} | 
              Size: {Math.round(zone.width)} × {Math.round(zone.height)}
            </div>
            
            {/* Test Result Indicator */}
            {testResults.find(r => r.zoneId === zone.id) && (
              <div className="mt-2 flex items-center space-x-2">
                {testResults.find(r => r.zoneId === zone.id)?.success ? (
                  <CheckCircle className="w-4 h-4 text-green-500" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-500" />
                )}
                <span className="text-xs">
                  Confidence: {(testResults.find(r => r.zoneId === zone.id)?.confidence || 0).toFixed(2)}
                </span>
              </div>
            )}
          </Card>
        ))}
        
        {currentDesktopZones.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <Target className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No OCR zones defined</p>
            <p className="text-sm">Enable drawing mode to create zones</p>
          </div>
        )}
      </div>
    );
  };

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Header */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Layout className="w-5 h-5" />
            <span>Multi-Desktop OCR Zone Designer</span>
            <Badge variant="outline">
              {totalZones} total zones
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Switch
                  checked={isDrawingEnabled}
                  onCheckedChange={setIsDrawingEnabled}
                />
                <Label>Drawing Mode</Label>
              </div>
              
              <div className="flex items-center space-x-2">
                <Switch
                  checked={designConfig.snapToGrid}
                  onCheckedChange={(checked) => 
                    setDesignConfig(prev => ({ ...prev, snapToGrid: checked }))
                  }
                />
                <Label>Snap to Grid</Label>
              </div>
              
              <div className="flex items-center space-x-2">
                <Switch
                  checked={designConfig.showGrid}
                  onCheckedChange={(checked) => 
                    setDesignConfig(prev => ({ ...prev, showGrid: checked }))
                  }
                />
                <Label>Show Grid</Label>
              </div>
            </div>
            
            <div className="flex items-center space-x-2">
              <Button
                variant="outline"
                size="sm"
                onClick={runOCRTests}
                disabled={isRunningTests || totalZones === 0}
              >
                {isRunningTests ? (
                  <>
                    <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-2" />
                    Testing...
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4 mr-2" />
                    Test Zones
                  </>
                )}
              </Button>
              
              <Button
                variant="outline"
                size="sm"
                onClick={saveTemplate}
                disabled={totalZones === 0}
              >
                <Save className="w-4 h-4 mr-2" />
                Save Template
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Desktop Canvases */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Desktop Layout</span>
                <Select
                  value={designConfig.layout}
                  onValueChange={(value: any) => 
                    setDesignConfig(prev => ({ ...prev, layout: value }))
                  }
                >
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="horizontal">Horizontal</SelectItem>
                    <SelectItem value="vertical">Vertical</SelectItem>
                    <SelectItem value="grid_2x2">Grid 2×2</SelectItem>
                    <SelectItem value="custom">Custom</SelectItem>
                  </SelectContent>
                </Select>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className={`grid gap-4 ${
                designConfig.layout === 'horizontal' ? 'grid-cols-2' :
                designConfig.layout === 'vertical' ? 'grid-cols-1' :
                designConfig.layout === 'grid_2x2' ? 'grid-cols-2' :
                'grid-cols-2'
              }`}>
                {desktops.map(renderDesktopCanvas)}
              </div>
              
              {isDrawingEnabled && (
                <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-950 rounded-lg">
                  <div className="flex items-center space-x-2 text-blue-700 dark:text-blue-300">
                    <Info className="w-4 h-4" />
                    <span className="text-sm font-medium">Drawing Mode Active</span>
                  </div>
                  <ul className="mt-2 text-sm text-blue-600 dark:text-blue-400 space-y-1">
                    <li>• Click and drag on any desktop to create OCR zones</li>
                    <li>• Click on existing zones to select and configure them</li>
                    <li>• Use the zone list panel to manage your zones</li>
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Control Panel */}
        <div className="space-y-6">
          {/* Desktop Selection */}
          <Card>
            <CardHeader>
              <CardTitle>Desktop Selection</CardTitle>
            </CardHeader>
            <CardContent>
              <Select value={selectedDesktop} onValueChange={setSelectedDesktop}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {desktops.map((desktop) => (
                    <SelectItem key={desktop.id} value={desktop.id}>
                      {desktop.name} ({desktop.ocrZones.length} zones)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardContent>
          </Card>

          {/* Zone Management */}
          <Card>
            <CardHeader>
              <CardTitle>OCR Zones</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-96 overflow-y-auto">
                {renderZoneList()}
              </div>
            </CardContent>
          </Card>

          {/* Test Results */}
          {testResults.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Test Results</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {testResults.map((result, index) => (
                    <div key={index} className="flex items-center justify-between p-2 bg-muted rounded">
                      <div className="flex items-center space-x-2">
                        {result.success ? (
                          <CheckCircle className="w-4 h-4 text-green-500" />
                        ) : (
                          <AlertCircle className="w-4 h-4 text-red-500" />
                        )}
                        <span className="text-sm">Zone {result.zoneId.split('-')[1]}</span>
                      </div>
                      <Badge variant={result.success ? "default" : "destructive"}>
                        {(result.confidence * 100).toFixed(0)}%
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

export default MultiDesktopOCRZoneDesigner;