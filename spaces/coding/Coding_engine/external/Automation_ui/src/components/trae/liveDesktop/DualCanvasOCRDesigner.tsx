/**
 * Dual Canvas OCR Designer for Live Desktop
 * Interactive dual-canvas workflow designer with OCR capabilities
 * Optimized for TRAE autonomous programming project
 * Author: TRAE Development Team
 * Version: 2.1.0
 */

import React, { useRef, useCallback, useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Trash2,
  Eye,
  EyeOff,
  Target,
  Save,
  Settings,
  Play,
  Square,
  Wifi,
  WifiOff,
  Monitor,
  Grid,
  Plus,
  Download,
  Upload,
  Maximize2,
  X,
  ScanText,
  Loader2
} from 'lucide-react';
import { OCRRegion, LiveDesktopConfig } from '@/types/liveDesktop';
import { useToast } from '@/hooks/use-toast';
import { OCRBackendService } from '@/services/ocrBackendService';
import {
  isElectron,
  isMoireAvailable,
  performNativeOCR,
  showNativeNotification,
  electronLog
} from '@/services/electronBridge';
import type { OCRResult } from '@/types/ocr';
// MoireServer Detection Integration
import { useMoireServer } from '@/components/trae/moire/hooks/useMoireServer';
import { MoireDetectionOverlay } from '@/components/trae/moire/MoireDetectionOverlay';

/**
 * Props interface for DualCanvasOCRDesigner component
 * Follows TRAE naming conventions and coding standards
 */
interface DualCanvasOCRDesignerProps {
  /** OCR configuration object */
  ocrConfig?: any;
  /** Function to update OCR configuration */
  setOcrConfig?: (config: any) => void;
  /** Primary monitor stream URL */
  primaryStreamUrl?: string | null;
  /** Secondary monitor stream URL */
  secondaryStreamUrl?: string | null;
  /** Connection status indicator */
  isConnected?: boolean;
  /** List of selected desktop clients */
  selectedClients?: string[];
  /** Function to handle connection */
  onConnect?: () => void;
  /** Function to handle disconnection */
  onDisconnect?: () => void;
  /** Function to handle workflow execution */
  onWorkflowExecute?: (nodeConfig: any) => void;
  /** Function to handle workflow stop */
  onWorkflowStop?: (nodeId: string) => void;
  /** Function to handle node configuration save */
  onNodeConfigSave?: (nodeConfig: any) => void;
  /** Live desktop configuration (for compatibility) */
  config?: LiveDesktopConfig;
  /** Function to handle config changes (for compatibility) */
  onConfigChange?: (config: LiveDesktopConfig) => void;
  /** CSS class name */
  className?: string;
}

/**
 * Internal state interfaces following TRAE conventions
 */
interface WorkflowNode {
  id: string;
  type: 'action' | 'interface' | 'trigger' | 'config' | 'results';
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  config: any;
  isActive: boolean;
  isExecutable: boolean;
}

interface CanvasState {
  scale: number;
  offsetX: number;
  offsetY: number;
  selectedNode: string | null;
  isDrawing: boolean;
  isPanning: boolean;
  drawStartX: number;
  drawStartY: number;
  drawCurrentX: number;
  drawCurrentY: number;
}

/**
 * DualCanvasOCRDesigner Component
 * Provides dual-canvas OCR design capabilities with workflow integration
 */
export const DualCanvasOCRDesigner: React.FC<DualCanvasOCRDesignerProps> = ({
  ocrConfig,
  setOcrConfig,
  primaryStreamUrl,
  secondaryStreamUrl,
  isConnected = false,
  selectedClients = [],
  onConnect,
  onDisconnect,
  onWorkflowExecute,
  onWorkflowStop,
  onNodeConfigSave,
  config,
  onConfigChange,
  className = ""
}) => {
  // ============================================================================
  // REFS AND STATE MANAGEMENT 
  // ============================================================================ 
  
  const primaryCanvasRef = useRef<HTMLCanvasElement>(null);
  const secondaryCanvasRef = useRef<HTMLCanvasElement>(null);
  const primaryOverlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const secondaryOverlayCanvasRef = useRef<HTMLCanvasElement>(null);
  
  // Image loading refs to prevent race conditions
  const primaryImageRef = useRef<HTMLImageElement | null>(null);
  const secondaryImageRef = useRef<HTMLImageElement | null>(null);
  const primaryStreamUrlRef = useRef<string | null>(null);
  const secondaryStreamUrlRef = useRef<string | null>(null);
  const loadingCounterRef = useRef<{ primary: number; secondary: number }>({ primary: 0, secondary: 0 });

  const [regions, setRegions] = useState<OCRRegion[]>(config?.ocrRegions || []);
  const [workflowNodes, setWorkflowNodes] = useState<WorkflowNode[]>([]);
  const [canvasState, setCanvasState] = useState<CanvasState>({
    scale: 1.0,
    offsetX: 0,
    offsetY: 0,
    selectedNode: null,
    isDrawing: false,
    isPanning: false,
    drawStartX: 0,
    drawStartY: 0,
    drawCurrentX: 0,
    drawCurrentY: 0
  });
  
  const [activeCanvas, setActiveCanvas] = useState<'primary' | 'secondary'>('primary');
  const [expandedMonitor, setExpandedMonitor] = useState<'primary' | 'secondary' | null>(null);

  // OCR extraction state
  const [isExtracting, setIsExtracting] = useState(false);
  const [autoOCREnabled, setAutoOCREnabled] = useState(false);
  const [ocrResults, setOcrResults] = useState<OCRResult[]>([]);
  const [previousOcrResults, setPreviousOcrResults] = useState<OCRResult[]>([]);
  const [textChanges, setTextChanges] = useState<Map<string, { previous: string; current: string; timestamp: string }>>(new Map());
  const [backendHealthy, setBackendHealthy] = useState(false);
  const [isWorkflowRunning, setIsWorkflowRunning] = useState(false);

  // Frame version counter to trigger overlay redraws after frame updates
  const [frameVersion, setFrameVersion] = useState(0);
  
  // Check if native Electron OCR is available
  const [useNativeOCR, setUseNativeOCR] = useState(false);

  // MoireServer Detection Integration
  const [moireEnabled, setMoireEnabled] = useState(false);
  const [selectedMoireBox, setSelectedMoireBox] = useState<string | null>(null);
  const [autoMoireDetection, setAutoMoireDetection] = useState(false);
  const autoMoireIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const {
    isConnected: moireConnected,
    detectionBoxes,
    isAnalyzing: moireAnalyzing,
    connect: connectMoire,
    analyzeFrame: analyzeMoireFrame,
  } = useMoireServer({
    autoConnect: false,
    onDetectionResult: (result) => {
      console.log('[MoireDetection] Result:', result.boxes?.length, 'boxes');
    },
  });

  const { toast } = useToast();

  // Fixed canvas dimensions for consistent layout
  const CANVAS_WIDTH = 1200;
  const CANVAS_HEIGHT = 900;

  // Auto-OCR interval reference
  const autoOCRIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // ============================================================================
  // CANVAS INITIALIZATION AND DRAWING 
  // ============================================================================ 

  /**
   * Draw fallback mock canvas when stream is unavailable
   * Maintains TRAE design consistency
   */
  const drawFallbackCanvas = useCallback((ctx: CanvasRenderingContext2D, gradientColors: string[]) => {
    // Create gradient background
    const gradient = ctx.createLinearGradient(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    gradient.addColorStop(0, gradientColors[0]);
    gradient.addColorStop(1, gradientColors[1]);
    
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    
    // Add "No Stream" indicator
    ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
    ctx.fillRect(CANVAS_WIDTH / 2 - 150, CANVAS_HEIGHT / 2 - 50, 300, 100);
    
    ctx.fillStyle = '#374151';
    ctx.font = 'bold 18px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No Stream Available', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 - 10);
    
    ctx.font = '14px Inter, sans-serif';
    ctx.fillText('Waiting for desktop stream...', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 + 15);
    
    // Reset text alignment
    ctx.textAlign = 'left';
  }, []);

  /**
   * Load and display stream image on canvas with proper error handling and race condition prevention
   * Uses loading counters to ensure only the most recent frame is drawn
   */
  const loadStreamImage = useCallback((
    canvas: HTMLCanvasElement,
    imageUrl: string,
    fallbackGradient: string[],
    canvasType: 'primary' | 'secondary'
  ) => {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (imageUrl && imageUrl.trim() !== '') {
      // Increment loading counter for this canvas type
      const currentLoadId = ++loadingCounterRef.current[canvasType];
      
      console.log(`[DualCanvasOCRDesigner] Loading ${canvasType} stream image (load #${currentLoadId}): ${imageUrl.substring(0, 50)}...`);
      
      const img = new Image();
      
      img.onload = () => {
        // Check if this is still the most recent load - cancel if outdated
        if (loadingCounterRef.current[canvasType] !== currentLoadId) {
          console.log(`[DualCanvasOCRDesigner] Skipping outdated ${canvasType} frame (load #${currentLoadId}, current: #${loadingCounterRef.current[canvasType]})`);
          return;
        }
        
        console.log(`[DualCanvasOCRDesigner] ${canvasType} stream image loaded successfully (load #${currentLoadId}), size: ${img.width}x${img.height}`);
        
        // Store the image ref for later use
        if (canvasType === 'primary') {
          primaryImageRef.current = img;
        } else {
          secondaryImageRef.current = img;
        }
        
        // Clear canvas first
        ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
        
        // Calculate aspect ratio to fit image properly
        const aspectRatio = img.width / img.height;
        const canvasAspectRatio = CANVAS_WIDTH / CANVAS_HEIGHT;
        
        let drawWidth = CANVAS_WIDTH;
        let drawHeight = CANVAS_HEIGHT;
        let offsetX = 0;
        let offsetY = 0;
        
        if (aspectRatio > canvasAspectRatio) {
          // Image is wider than canvas
          drawHeight = CANVAS_WIDTH / aspectRatio;
          offsetY = (CANVAS_HEIGHT - drawHeight) / 2;
        } else {
          // Image is taller than canvas
          drawWidth = CANVAS_HEIGHT * aspectRatio;
          offsetX = (CANVAS_WIDTH - drawWidth) / 2;
        }
        
        // Draw the stream image
        ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
        
        // Increment frame version to trigger overlay redraw
        setFrameVersion(prev => prev + 1);
        
        // Note: Overlay is redrawn automatically via useEffect when state changes
        // We don't call drawRegionsOverlay here to avoid circular dependency
      };
      
      img.onerror = () => {
        // Check if this is still the most recent load
        if (loadingCounterRef.current[canvasType] !== currentLoadId) {
          return;
        }
        console.warn(`[DualCanvasOCRDesigner] Failed to load ${canvasType} stream image, falling back to mock data`);
        drawFallbackCanvas(ctx, fallbackGradient);
      };
      
      img.src = imageUrl;
    } else {
      console.log(`[DualCanvasOCRDesigner] No ${canvasType} stream URL provided, using fallback`);
      drawFallbackCanvas(ctx, fallbackGradient);
    }
  }, [drawFallbackCanvas]);

  /**
   * Initialize canvas backgrounds with stream data or fallback
   * Follows TRAE coding practices with clear comments
   */
  const initializeCanvases = useCallback(() => {
    const primaryCanvas = primaryCanvasRef.current;
    const secondaryCanvas = secondaryCanvasRef.current;
    
    if (!primaryCanvas || !secondaryCanvas) return;

    // Only update if URLs have actually changed
    const primaryChanged = primaryStreamUrl !== primaryStreamUrlRef.current;
    const secondaryChanged = secondaryStreamUrl !== secondaryStreamUrlRef.current;

    if (primaryChanged) {
      console.log(`[DualCanvasOCRDesigner] Primary stream URL changed`);
      primaryStreamUrlRef.current = primaryStreamUrl || null;
      loadStreamImage(primaryCanvas, primaryStreamUrl || '', ['#1e40af', '#3b82f6'], 'primary');
    }
    
    if (secondaryChanged) {
      console.log(`[DualCanvasOCRDesigner] Secondary stream URL changed`);
      secondaryStreamUrlRef.current = secondaryStreamUrl || null;
      loadStreamImage(secondaryCanvas, secondaryStreamUrl || '', ['#10b981', '#059669'], 'secondary');
    }

    // Initial load if refs are null
    if (primaryStreamUrlRef.current === null && secondaryStreamUrlRef.current === null) {
      console.log(`[DualCanvasOCRDesigner] Initializing canvases with streams:`);
      console.log(`[DualCanvasOCRDesigner] Primary URL: ${primaryStreamUrl ? 'Available' : 'Not available'}`);
      console.log(`[DualCanvasOCRDesigner] Secondary URL: ${secondaryStreamUrl ? 'Available' : 'Not available'}`);

      primaryStreamUrlRef.current = primaryStreamUrl || null;
      secondaryStreamUrlRef.current = secondaryStreamUrl || null;
      
      loadStreamImage(primaryCanvas, primaryStreamUrl || '', ['#1e40af', '#3b82f6'], 'primary');
      loadStreamImage(secondaryCanvas, secondaryStreamUrl || '', ['#10b981', '#059669'], 'secondary');
    }
  }, [primaryStreamUrl, secondaryStreamUrl, loadStreamImage]);

  /**
   * Draw OCR regions overlay with TRAE design system colors
   * Now draws overlays on both primary and secondary canvases
   */
  const drawRegionsOverlay = useCallback(() => {
    // Draw on both overlay canvases
    [
      { canvas: primaryOverlayCanvasRef.current, monitor: 'primary' as const },
      { canvas: secondaryOverlayCanvasRef.current, monitor: 'secondary' as const }
    ].forEach(({ canvas, monitor }) => {
      if (!canvas) return;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      // Clear overlay canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Only draw on the active canvas
      if (activeCanvas !== monitor) return;

      // Draw current drawing region (if actively drawing)
      if (canvasState.isDrawing) {
        const x = Math.min(canvasState.drawStartX, canvasState.drawCurrentX);
        const y = Math.min(canvasState.drawStartY, canvasState.drawCurrentY);
        const width = Math.abs(canvasState.drawCurrentX - canvasState.drawStartX);
        const height = Math.abs(canvasState.drawCurrentY - canvasState.drawStartY);

        // Draw semi-transparent blue rectangle for active drawing
        ctx.strokeStyle = '#3b82f6';
        ctx.fillStyle = 'rgba(59, 130, 246, 0.2)';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]); // Dashed line for active drawing

        ctx.fillRect(x, y, width, height);
        ctx.strokeRect(x, y, width, height);

        ctx.setLineDash([]); // Reset line dash

        // Draw dimensions label
        ctx.fillStyle = '#3b82f6';
        ctx.font = 'bold 14px Inter, sans-serif';
        ctx.fillText(`${Math.round(width)} × ${Math.round(height)}`, x + 5, y + 20);
      }

      // Draw OCR regions with confidence-based colors
      regions.forEach((region) => {
        const isSelected = canvasState.selectedNode === region.id;
        const isActive = region.isActive;
        
        // Find OCR result for this region to get confidence
        const ocrResult = ocrResults.find(r => r.zone_id === region.id);
        const confidence = ocrResult?.confidence ?? 0;
        
        // Get confidence-based colors
        let strokeColor = '#6b7280';
        let fillColor = 'rgba(107, 114, 128, 0.1)';
        let labelBg = 'rgba(107, 114, 128, 0.9)';
        
        if (isSelected) {
          strokeColor = '#8b5cf6';
          fillColor = 'rgba(139, 92, 246, 0.15)';
          labelBg = 'rgba(139, 92, 246, 0.9)';
        } else if (confidence > 0) {
          if (confidence >= 0.9) {
            strokeColor = '#10b981';
            fillColor = 'rgba(16, 185, 129, 0.12)';
            labelBg = 'rgba(16, 185, 129, 0.9)';
          } else if (confidence >= 0.7) {
            strokeColor = '#f59e0b';
            fillColor = 'rgba(245, 158, 11, 0.12)';
            labelBg = 'rgba(245, 158, 11, 0.9)';
          } else {
            strokeColor = '#ef4444';
            fillColor = 'rgba(239, 68, 68, 0.12)';
            labelBg = 'rgba(239, 68, 68, 0.9)';
          }
        } else if (isActive) {
          strokeColor = '#3b82f6';
          fillColor = 'rgba(59, 130, 246, 0.1)';
          labelBg = 'rgba(59, 130, 246, 0.9)';
        }

        // Apply confidence-based colors
        ctx.strokeStyle = strokeColor;
        ctx.fillStyle = fillColor;
        ctx.lineWidth = isSelected ? 3 : 2;

        // Draw region rectangle
        ctx.fillRect(region.x, region.y, region.width, region.height);
        ctx.strokeRect(region.x, region.y, region.width, region.height);

        // Draw label background
        const labelText = region.label;
        ctx.font = '500 12px Inter, sans-serif';
        const textMetrics = ctx.measureText(labelText);
        const labelHeight = 20;
        const labelWidth = textMetrics.width + 16;
        const labelY = region.y > 25 ? region.y - labelHeight - 4 : region.y + region.height + 4;
        
        ctx.fillStyle = labelBg;
        ctx.fillRect(region.x, labelY, labelWidth, labelHeight);

        // Draw label text
        ctx.fillStyle = '#ffffff';
        ctx.fillText(labelText, region.x + 8, labelY + 14);

        // Draw confidence badge if OCR result exists
        if (ocrResult) {
          const confidenceText = `${(confidence * 100).toFixed(0)}%`;
          const badgeWidth = ctx.measureText(confidenceText).width + 12;
          const badgeX = region.x + region.width - badgeWidth - 4;
          const badgeY = region.y + 4;
          
          // Badge background
          ctx.fillStyle = confidence >= 0.9 ? 'rgba(16, 185, 129, 0.9)' : 
                          confidence >= 0.7 ? 'rgba(245, 158, 11, 0.9)' : 
                          'rgba(239, 68, 68, 0.9)';
          ctx.fillRect(badgeX, badgeY, badgeWidth, 18);
          
          // Badge text
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 10px Inter, sans-serif';
          ctx.fillText(confidenceText, badgeX + 6, badgeY + 13);
        }

        // Draw status indicator for active regions without OCR results
        if (isActive && !ocrResult) {
          ctx.fillStyle = '#10b981';
          ctx.beginPath();
          ctx.arc(region.x + region.width - 8, region.y + 8, 4, 0, 2 * Math.PI);
          ctx.fill();
        }
      });

      // Draw workflow nodes
      workflowNodes.forEach((node) => {
        const isSelected = canvasState.selectedNode === node.id;
        const isExecutable = node.isExecutable;
        
        // Node colors based on type and state
        let nodeColor = '#6b7280';
        if (isExecutable) nodeColor = '#10b981';
        if (node.type === 'action') nodeColor = '#ef4444';
        if (node.type === 'interface') nodeColor = '#f59e0b';
        if (isSelected) nodeColor = '#8b5cf6';
        
        ctx.strokeStyle = nodeColor;
        ctx.fillStyle = isSelected ? `${nodeColor}20` : `${nodeColor}10`;
        ctx.lineWidth = isSelected ? 3 : 2;

        // Draw node rectangle
        ctx.fillRect(node.x, node.y, node.width, node.height);
        ctx.strokeRect(node.x, node.y, node.width, node.height);

        // Draw node label
        ctx.fillStyle = nodeColor;
        ctx.font = '500 12px Inter, sans-serif';
        ctx.fillText(node.label, node.x + 8, node.y + 20);
        
        // Draw node type badge
        ctx.font = '400 10px Inter, sans-serif';
        ctx.fillText(node.type.toUpperCase(), node.x + 8, node.y + node.height - 8);
      });
    });
  }, [regions, workflowNodes, ocrResults, canvasState.selectedNode, canvasState.isDrawing, canvasState.drawStartX, canvasState.drawStartY, canvasState.drawCurrentX, canvasState.drawCurrentY, activeCanvas, frameVersion]);

  // ============================================================================ 
  // REGION AND NODE MANAGEMENT 
  // ============================================================================ 

  /**
   * Add new OCR region with proper validation
   */
  const addOCRRegion = useCallback((x: number, y: number, width: number, height: number) => {
    if (width < 10 || height < 10) return;

    const newRegion: OCRRegion = {
      id: `region-${Date.now()}`,
      label: `OCR Zone ${regions.length + 1}`,
      x: Math.min(x, x + width),
      y: Math.min(y, y + height),
      width: Math.abs(width),
      height: Math.abs(height),
      isActive: true,
      lastExtractedText: '',
      extractionHistory: []
    };

    const updatedRegions = [...regions, newRegion];
    setRegions(updatedRegions);

    // Update config for external components
    if (config && onConfigChange) {
      onConfigChange({
        ...config,
        ocrRegions: updatedRegions,
        updatedAt: new Date().toISOString()
      });
    }

    toast({
      title: "OCR Zone Created",
      description: `Zone "${newRegion.label}" added for text extraction`,
    });
  }, [regions, config, onConfigChange, toast]);

  /**
   * Delete OCR region by ID
   */
  const deleteOCRRegion = useCallback((regionId: string) => {
    const updatedRegions = regions.filter(r => r.id !== regionId);
    setRegions(updatedRegions);

    // Update config for external components
    if (config && onConfigChange) {
      onConfigChange({
        ...config,
        ocrRegions: updatedRegions,
        updatedAt: new Date().toISOString()
      });
    }

    toast({
      title: "OCR Zone Deleted",
      description: "Zone removed successfully",
    });
  }, [regions, config, onConfigChange, toast]);

  /**
   * Delete selected region/node
   */
  const handleDeleteSelected = useCallback(() => {
    if (!canvasState.selectedNode) return;

    const selectedRegion = regions.find(r => r.id === canvasState.selectedNode);
    if (selectedRegion) {
      deleteOCRRegion(selectedRegion.id);
      setCanvasState(prev => ({ ...prev, selectedNode: null }));
    }
  }, [canvasState.selectedNode, regions, deleteOCRRegion]);

  /**
   * Add new workflow node with type validation
   */
  const addWorkflowNode = useCallback((type: WorkflowNode['type'], x: number, y: number) => {
    const newNode: WorkflowNode = {
      id: `node-${type}-${Date.now()}`,
      type,
      label: `${type.charAt(0).toUpperCase() + type.slice(1)} Node`,
      x,
      y,
      width: 120,
      height: 60,
      config: {},
      isActive: true,
      isExecutable: type === 'action' || type === 'interface' // Only action and interface nodes are executable
    };

    setWorkflowNodes(prev => [...prev, newNode]);

    toast({
      title: "Workflow Node Added",
      description: `${type} node created`,
    });
  }, [toast]);

  // ============================================================================ 
  // EVENT HANDLERS FOR INTERACTION 
  // ============================================================================ 

  /**
   * Handle mouse events for region and node selection/creation
   * Implements TRAE interaction patterns
   */
  const handleCanvasMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = e.currentTarget;
    const rect = canvas.getBoundingClientRect();

    // Calculate actual canvas coordinates considering scaling
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;

    // Check for node/region selection
    const clickedRegion = regions.find(region =>
      x >= region.x && x <= region.x + region.width &&
      y >= region.y && y <= region.y + region.height
    );

    const clickedNode = workflowNodes.find(node =>
      x >= node.x && x <= node.x + node.width &&
      y >= node.y && y <= node.y + node.height
    );

    if (clickedRegion) {
      setCanvasState(prev => ({ ...prev, selectedNode: clickedRegion.id }));
    } else if (clickedNode) {
      setCanvasState(prev => ({ ...prev, selectedNode: clickedNode.id }));
    } else {
      // Start drawing new region/node
      setCanvasState(prev => ({
        ...prev,
        selectedNode: null,
        isDrawing: true,
        drawStartX: x,
        drawStartY: y,
        drawCurrentX: x,
        drawCurrentY: y
      }));
    }
  }, [regions, workflowNodes]);

  /**
   * Handle mouse move for drawing regions
   */
  const handleCanvasMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasState.isDrawing) return;

    const canvas = e.currentTarget;
    const rect = canvas.getBoundingClientRect();

    // Calculate actual canvas coordinates considering scaling
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;

    setCanvasState(prev => ({
      ...prev,
      drawCurrentX: x,
      drawCurrentY: y
    }));
  }, [canvasState.isDrawing]);

  /**
   * Handle mouse up to finish drawing
   */
  const handleCanvasMouseUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasState.isDrawing) return;

    const canvas = e.currentTarget;
    const rect = canvas.getBoundingClientRect();

    // Calculate actual canvas coordinates considering scaling
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;

    const width = Math.abs(x - canvasState.drawStartX);
    const height = Math.abs(y - canvasState.drawStartY);

    // Only create region if it's large enough
    if (width >= 20 && height >= 20) {
      addOCRRegion(
        Math.min(canvasState.drawStartX, x),
        Math.min(canvasState.drawStartY, y),
        width,
        height
      );
    }

    // Reset drawing state
    setCanvasState(prev => ({
      ...prev,
      isDrawing: false,
      drawStartX: 0,
      drawStartY: 0,
      drawCurrentX: 0,
      drawCurrentY: 0
    }));
  }, [canvasState.isDrawing, canvasState.drawStartX, canvasState.drawStartY, addOCRRegion]);

  /**
   * Handle workflow execution for action and interface nodes
   * Only executable nodes can be triggered
   */
  const handleNodeExecution = useCallback((nodeId: string) => {
    const node = workflowNodes.find(n => n.id === nodeId);
    if (!node || !node.isExecutable) return;

    if (node.type === 'action' || node.type === 'interface') {
      onWorkflowExecute?.(node.config);
      setIsWorkflowRunning(true);

      toast({
        title: "Workflow Executed",
        description: `Node "${node.label}" execution started`,
      });
    }
  }, [workflowNodes, onWorkflowExecute, toast]);

  // ============================================================================ 
  // OCR EXTRACTION LOGIC 
  // ============================================================================ 

  /**
   * Check OCR backend health on mount
   */
  useEffect(() => {
    const checkBackendHealth = async () => {
      try {
        // First check if native Electron OCR is available
        if (isElectron() && isMoireAvailable()) {
          console.log('[OCRDesigner] Native Electron OCR available');
          setUseNativeOCR(true);
          setBackendHealthy(true);
          return;
        }
        
        // Fallback to backend service
        const healthy = await OCRBackendService.isHealthy();
        setBackendHealthy(healthy);
        if (healthy) {
          console.log('[OCRDesigner] OCR backend is healthy');
        }
      } catch (error) {
        console.error('[OCRDesigner] Failed to check backend health:', error);
        setBackendHealthy(false);
      }
    };

    checkBackendHealth();
  }, []);

  /**
   * Extract OCR text from all active regions
   * Uses native Electron OCR if available, otherwise falls back to backend
   */
  const extractOCRText = useCallback(async () => {
    if (!backendHealthy) {
      toast({
        title: "OCR Backend Not Available",
        description: "Please ensure OCR backend is running on port 8007",
        variant: "destructive"
      });
      return;
    }

    if (regions.length === 0) {
      toast({
        title: "No OCR Zones Defined",
        description: "Draw regions on the canvas to extract text",
        variant: "default"
      });
      return;
    }

    setIsExtracting(true);
    electronLog('info', `Starting OCR extraction for ${regions.length} regions`);

    try {
      // Get the current active canvas with retry logic
      const canvasRef = activeCanvas === 'primary' ? primaryCanvasRef : secondaryCanvasRef;
      let canvas = canvasRef.current;

      // Retry logic: wait for canvas to be available
      if (!canvas) {
        console.warn('[DualCanvasOCRDesigner] Canvas ref is null, waiting for canvas to mount...');
        for (let i = 0; i < 20; i++) {
          await new Promise(resolve => setTimeout(resolve, 100));
          canvas = canvasRef.current;
          if (canvas) {
            console.log('[DualCanvasOCRDesigner] Canvas ref now available after retry');
            break;
          }
        }

        if (!canvas) {
          throw new Error(`Canvas not available for ${activeCanvas} monitor after waiting.`);
        }
      }

      // Convert canvas to base64
      const imageDataBase64 = await OCRBackendService.canvasToBase64(canvas);

      // Prepare regions for OCR
      const ocrRegions = regions.map(region => ({
        id: region.id,
        x: region.x,
        y: region.y,
        width: region.width,
        height: region.height,
        label: region.label,
        language: 'eng'
      }));

      let response: any;

      // Try native Electron OCR first if available
      if (useNativeOCR && isElectron() && isMoireAvailable()) {
        console.log('[OCRDesigner] Using native Electron OCR');
        const nativeResult = await performNativeOCR(imageDataBase64, {
          regions: ocrRegions,
          confidence_threshold: 0.5
        });
        
        if (nativeResult && nativeResult.success) {
          response = {
            success: true,
            results: nativeResult.results.map(r => ({
              zone_id: r.zone_id,
              text: r.text,
              confidence: r.confidence,
              metadata: {
                engine: 'electron-native',
                processing_time: nativeResult.processing_time_ms,
                timestamp: new Date().toISOString()
              }
            }))
          };
          showNativeNotification('OCR Extraction', `Extracted text from ${nativeResult.results.length} regions`);
        } else {
          console.log('[OCRDesigner] Native OCR failed, falling back to backend');
          response = await OCRBackendService.extractText(imageDataBase64, ocrRegions);
        }
      } else {
        response = await OCRBackendService.extractText(imageDataBase64, ocrRegions);
      }

      if (response.success) {
        // Detect text changes
        const newChanges = new Map(textChanges);
        let changeCount = 0;

        response.results.forEach((result) => {
          const previousResult = previousOcrResults.find(r => r.zone_id === result.zone_id);
          if (previousResult && previousResult.text !== result.text) {
            newChanges.set(result.zone_id, {
              previous: previousResult.text,
              current: result.text,
              timestamp: result.metadata.timestamp
            });
            changeCount++;
          }
        });

        setTextChanges(newChanges);
        setPreviousOcrResults(response.results);
        setOcrResults(response.results);

        // Update regions with extracted text
        const updatedRegions = regions.map(region => {
          const result = response.results.find((r) => r.zone_id === region.id);
          if (result) {
            return {
              ...region,
              lastExtractedText: result.text,
              extractionHistory: [
                ...(region.extractionHistory || []),
                {
                  text: result.text,
                  confidence: result.confidence,
                  timestamp: result.metadata.timestamp
                }
              ]
            };
          }
          return region;
        });

        setRegions(updatedRegions);

        toast({
          title: "OCR Extraction Complete",
          description: changeCount > 0
            ? `${changeCount} text change${changeCount !== 1 ? 's' : ''} detected`
            : `Extracted text from ${response.results.length} region${response.results.length !== 1 ? 's' : ''}`,
        });
      }
    } catch (error) {
      console.error('[OCRDesigner] OCR extraction failed:', error);
      toast({
        title: "OCR Extraction Failed",
        description: error instanceof Error ? error.message : "Unknown error occurred",
        variant: "destructive"
      });
    } finally {
      setIsExtracting(false);
    }
  }, [regions, activeCanvas, backendHealthy, textChanges, previousOcrResults, useNativeOCR, toast]);

  /**
   * Toggle auto-OCR mode
   */
  const toggleAutoOCR = useCallback(() => {
    if (autoOCREnabled) {
      if (autoOCRIntervalRef.current) {
        clearInterval(autoOCRIntervalRef.current);
        autoOCRIntervalRef.current = null;
      }
      setAutoOCREnabled(false);
      toast({
        title: "Auto-OCR Disabled",
        description: "Continuous text extraction stopped",
      });
    } else {
      setAutoOCREnabled(true);
      extractOCRText();

      autoOCRIntervalRef.current = setInterval(() => {
        extractOCRText();
      }, 5000);

      toast({
        title: "Auto-OCR Enabled",
        description: "Extracting text every 5 seconds",
      });
    }
  }, [autoOCREnabled, extractOCRText, toast]);

  // Cleanup auto-OCR interval on unmount
  useEffect(() => {
    return () => {
      if (autoOCRIntervalRef.current) {
        clearInterval(autoOCRIntervalRef.current);
      }
    };
  }, []);

  // ============================================================================
  // MOIRE DETECTION FUNCTIONS
  // ============================================================================

  /**
   * Send current canvas frame to MoireServer for detection
   */
  const sendFrameToMoire = useCallback(async () => {
    if (!moireConnected) {
      console.warn('[MoireDetection] Not connected');
      return;
    }

    const canvasRef = activeCanvas === 'primary' ? primaryCanvasRef : secondaryCanvasRef;
    const canvas = canvasRef.current;
    if (!canvas) return;

    try {
      // Convert canvas to base64
      const imageData = canvas.toDataURL('image/jpeg', 0.8);
      const base64Data = imageData.replace(/^data:image\/\w+;base64,/, '');

      analyzeMoireFrame(base64Data, {
        runOCR: true,
        runCNN: true,
        detectionMode: 'advanced'
      });

      console.log('[MoireDetection] Frame sent for analysis');
    } catch (error) {
      console.error('[MoireDetection] Failed to send frame:', error);
    }
  }, [moireConnected, activeCanvas, analyzeMoireFrame]);

  /**
   * Toggle automatic Moire detection
   */
  const toggleAutoMoireDetection = useCallback(() => {
    if (autoMoireDetection) {
      if (autoMoireIntervalRef.current) {
        clearInterval(autoMoireIntervalRef.current);
        autoMoireIntervalRef.current = null;
      }
      setAutoMoireDetection(false);
      toast({
        title: "Auto-Detection Disabled",
        description: "Continuous UI detection stopped",
      });
    } else {
      if (!moireConnected) {
        connectMoire();
      }
      setAutoMoireDetection(true);
      sendFrameToMoire();

      autoMoireIntervalRef.current = setInterval(() => {
        sendFrameToMoire();
      }, 3000); // Every 3 seconds

      toast({
        title: "Auto-Detection Enabled",
        description: "Detecting UI elements every 3 seconds",
      });
    }
  }, [autoMoireDetection, moireConnected, connectMoire, sendFrameToMoire, toast]);

  // Cleanup auto-Moire interval on unmount
  useEffect(() => {
    return () => {
      if (autoMoireIntervalRef.current) {
        clearInterval(autoMoireIntervalRef.current);
      }
    };
  }, []);

  // ============================================================================ 
  // CONNECTION AND STREAM MANAGEMENT 
  // ============================================================================ 

  const handleConnectionToggle = useCallback(() => {
    if (isConnected) {
      onDisconnect?.();
      toast({
        title: "Disconnected",
        description: "WebSocket connection closed",
      });
    } else {
      onConnect?.();
      toast({
        title: "Connecting...",
        description: "Establishing WebSocket connection",
      });
    }
  }, [isConnected, onConnect, onDisconnect, toast]);

  const handleExpandMonitor = useCallback((monitor: 'primary' | 'secondary') => {
    setExpandedMonitor(monitor);
    setActiveCanvas(monitor);
  }, []);

  const handleCloseExpanded = useCallback(() => {
    setExpandedMonitor(null);
  }, []);

  // ============================================================================ 
  // EFFECTS FOR INITIALIZATION 
  // ============================================================================ 

  useEffect(() => {
    initializeCanvases();
  }, [initializeCanvases]);

  useEffect(() => {
    console.log(`[DualCanvasOCRDesigner] Stream URLs changed, updating canvases`);
    initializeCanvases();
  }, [primaryStreamUrl, secondaryStreamUrl, initializeCanvases]);

  useEffect(() => {
    drawRegionsOverlay();
  }, [drawRegionsOverlay, canvasState, frameVersion]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && expandedMonitor) {
        handleCloseExpanded();
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [expandedMonitor, handleCloseExpanded]);

  // ============================================================================ 
  // RENDER METHODS 
  // ============================================================================ 

  const renderControlPanel = () => (
    <div className="mb-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">OCR Designer</h2>
        <Badge variant={isConnected ? "default" : "secondary"} className="text-xs">
          {isConnected ? <Wifi className="w-3 h-3 mr-1" /> : <WifiOff className="w-3 h-3 mr-1" />}
          {isConnected ? 'Connected' : 'Disconnected'}
        </Badge>
        <Badge variant={backendHealthy ? "default" : "secondary"} className="text-xs">
          {backendHealthy ? '🟢 OCR Ready' : '🔴 OCR Offline'}
        </Badge>
        {useNativeOCR && (
          <Badge variant="outline" className="text-xs">
            ⚡ Native OCR
          </Badge>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Tabs value={activeCanvas} onValueChange={(value) => setActiveCanvas(value as 'primary' | 'secondary')} asChild>
          <TabsList className="h-8">
            <TabsTrigger value="primary">Monitor 1</TabsTrigger>
            <TabsTrigger value="secondary">Monitor 2</TabsTrigger>
          </TabsList>
        </Tabs>

        {/* OCR Controls */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={extractOCRText}
            disabled={isExtracting || !backendHealthy || regions.length === 0}
          >
            {isExtracting ? (
              <>
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                Extracting...
              </>
            ) : (
              <>
                <ScanText className="w-4 h-4 mr-1" />
                Extract OCR
              </>
            )}
          </Button>

          <div className="flex items-center gap-2 border rounded px-2 py-1">
            <Label htmlFor="auto-ocr" className="text-xs cursor-pointer">
              Auto-OCR
            </Label>
            <Switch
              id="auto-ocr"
              checked={autoOCREnabled}
              onCheckedChange={toggleAutoOCR}
              disabled={!backendHealthy || regions.length === 0}
            />
          </div>
        </div>

        {/* Moire Detection Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 border rounded px-2 py-1">
            <Label htmlFor="moire-detection" className="text-xs cursor-pointer">
              UI Detection
            </Label>
            <Switch
              id="moire-detection"
              checked={moireEnabled}
              onCheckedChange={(checked) => {
                setMoireEnabled(checked);
                if (checked && !moireConnected) {
                  connectMoire();
                }
              }}
            />
            {moireConnected && (
              <Badge variant="default" className="text-xs ml-1">
                {detectionBoxes.length} boxes
              </Badge>
            )}
          </div>

          {moireEnabled && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={sendFrameToMoire}
                disabled={!moireConnected || moireAnalyzing}
              >
                {moireAnalyzing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                    Detecting...
                  </>
                ) : (
                  <>
                    <Target className="w-4 h-4 mr-1" />
                    Detect
                  </>
                )}
              </Button>

              <div className="flex items-center gap-2 border rounded px-2 py-1">
                <Label htmlFor="auto-moire" className="text-xs cursor-pointer">
                  Auto
                </Label>
                <Switch
                  id="auto-moire"
                  checked={autoMoireDetection}
                  onCheckedChange={toggleAutoMoireDetection}
                  disabled={!moireConnected}
                />
              </div>
            </>
          )}
        </div>

        {canvasState.selectedNode && (
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDeleteSelected}
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );

  const renderMonitorPanels = () => (
    <div className="flex flex-1 gap-4">
      <div className="flex-1 flex flex-col">
        <Card className={expandedMonitor === 'primary' ? 'h-5/6 flex-1 flex-col border-t-2 border-primary' : 'h-full'}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{expandedMonitor === 'primary' ? 'Monitor 1 (Expanded)' : 'Monitor 1'}</CardTitle>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" onClick={() => handleExpandMonitor('primary')}>
                  <Maximize2 className="w-4 h-4" />
                </Button>
                <Button variant="ghost" size="icon">
                  {expandedMonitor === 'primary' ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="relative h-full bg-gray-100 border rounded">
              <canvas ref={primaryCanvasRef} width={CANVAS_WIDTH} height={CANVAS_HEIGHT} />
              <canvas ref={primaryOverlayCanvasRef} width={CANVAS_WIDTH} height={CANVAS_HEIGHT} />
              {/* Moire Detection Overlay - Primary */}
              {moireEnabled && activeCanvas === 'primary' && (
                <MoireDetectionOverlay
                  boxes={detectionBoxes}
                  containerWidth={CANVAS_WIDTH}
                  containerHeight={CANVAS_HEIGHT}
                  selectedBoxId={selectedMoireBox}
                  onBoxClick={(box) => setSelectedMoireBox(box.id)}
                  showLabels={true}
                  showConfidence={true}
                />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
      <div className="flex-1 flex flex-col">
        <Card className={expandedMonitor === 'secondary' ? 'h-5/6 flex-1 flex-col border-t-2 border-primary' : 'h-full'}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{expandedMonitor === 'secondary' ? 'Monitor 2 (Expanded)' : 'Monitor 2'}</CardTitle>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" onClick={() => handleExpandMonitor('secondary')}>
                  <Maximize2 className="w-4 h-4" />
                </Button>
                <Button variant="ghost" size="icon">
                  {expandedMonitor === 'secondary' ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="relative h-full bg-gray-100 border rounded">
              <canvas ref={secondaryCanvasRef} width={CANVAS_WIDTH} height={CANVAS_HEIGHT} />
              <canvas ref={secondaryOverlayCanvasRef} width={CANVAS_WIDTH} height={CANVAS_HEIGHT} />
              {/* Moire Detection Overlay - Secondary */}
              {moireEnabled && activeCanvas === 'secondary' && (
                <MoireDetectionOverlay
                  boxes={detectionBoxes}
                  containerWidth={CANVAS_WIDTH}
                  containerHeight={CANVAS_HEIGHT}
                  selectedBoxId={selectedMoireBox}
                  onBoxClick={(box) => setSelectedMoireBox(box.id)}
                  showLabels={true}
                  showConfidence={true}
                />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );

  const renderRegionsPanel = () => (
    <Card className="h-1/6">
      <CardHeader>
        <CardTitle>OCR Regions</CardTitle>
      </CardHeader>
      <CardContent className="flex-1">
        <Tabs value={expandedMonitor ?? 'primary'} onValueChange={(value) => setExpandedMonitor(value as 'primary' | 'secondary')}>
          <TabsList className="h-8">
            <TabsTrigger value="primary">Monitor 1</TabsTrigger>
            <TabsTrigger value="secondary">Monitor 2</TabsTrigger>
          </TabsList>
          <TabsContent value="primary" className="p-2">
            <div className="flex-1 flex flex-col">
              <Card className="flex-1">
                <CardHeader>
                  <CardTitle>Detected Text on Monitor 1</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-auto max-h-48">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="border-b bg-muted/50">
                          <th className="text-left p-2 font-medium">Label</th>
                          <th className="text-left p-2 font-medium">Confidence</th>
                          <th className="text-left p-2 font-medium">Text</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ocrResults.filter(r => r.zone_id.startsWith('region')).map((r, idx) => (
                          <tr key={idx} className="border-b hover:bg-muted/30">
                            <td className="p-2">{r.zone_id}</td>
                            <td className="p-2">{r.confidence?.toFixed(2) || 'N/A'}</td>
                            <td className="p-2 truncate max-w-xs">{r.text?.length > 25 ? r.text.substring(0, 25) + '...' : r.text}</td>
                          </tr>
                        ))}
                        {ocrResults.filter(r => r.zone_id.startsWith('region')).length === 0 && (
                          <tr>
                            <td colSpan={3} className="p-4 text-center text-muted-foreground">No OCR results</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
          <TabsContent value="secondary" className="p-2">
            <div className="flex-1 flex flex-col">
              <Card className="flex-1">
                <CardHeader>
                  <CardTitle>Detected Text on Monitor 2</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-auto max-h-48">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="border-b bg-muted/50">
                          <th className="text-left p-2 font-medium">Label</th>
                          <th className="text-left p-2 font-medium">Confidence</th>
                          <th className="text-left p-2 font-medium">Text</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ocrResults.filter(r => r.zone_id.startsWith('region')).map((r, idx) => (
                          <tr key={idx} className="border-b hover:bg-muted/30">
                            <td className="p-2">{r.zone_id}</td>
                            <td className="p-2">{r.confidence?.toFixed(2) || 'N/A'}</td>
                            <td className="p-2 truncate max-w-xs">{r.text?.length > 25 ? r.text.substring(0, 25) + '...' : r.text}</td>
                          </tr>
                        ))}
                        {ocrResults.filter(r => r.zone_id.startsWith('region')).length === 0 && (
                          <tr>
                            <td colSpan={3} className="p-4 text-center text-muted-foreground">No OCR results</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );

  return (
    <div className={`relative flex flex-1 flex-col ${className}`}>
      <div className={`absolute inset-0 flex flex-col transition-opacity duration-300 ${!isConnected ? 'opacity-40' : 'opacity-100'}`}>
        {renderMonitorPanels()}
        {renderRegionsPanel()}
      </div>
      {renderControlPanel()}
    </div>
  );
};