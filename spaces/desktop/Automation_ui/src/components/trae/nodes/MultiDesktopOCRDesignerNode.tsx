/**
 * Multi-Desktop OCR Designer Node Component
 * Workflow node wrapper for the Multi-Desktop OCR Zone Designer
 * Integrates with the TRAE Unity AI Platform workflow system
 * 
 * Features:
 * - Workflow node interface compliance
 * - Real-time desktop stream integration
 * - Configuration persistence and export
 * - Status monitoring and validation
 * - Template management integration
 * 
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  Monitor, 
  Layout, 
  Settings, 
  Play, 
  Pause, 
  Download, 
  Upload,
  Eye,
  EyeOff,
  CheckCircle,
  AlertCircle,
  Zap,
  Target,
  Edit3,
  TestTube
} from 'lucide-react';
import { MultiDesktopOCRZoneDesigner } from '@/components/trae/liveDesktop/MultiDesktopOCRZoneDesigner';
import { OCRZoneConfigurationPanel } from '@/components/trae/liveDesktop/OCRZoneConfigurationPanel';
import { useToast } from '@/hooks/use-toast';

// ============================================================================
// INTERFACES & TYPES
// ============================================================================

interface MultiDesktopOCRDesignerNodeData {
  // Configuration
  isExpanded: boolean;
  isConnected: boolean;
  autoStart: boolean;
  
  // Desktop Configuration
  desktopLayout: 'horizontal' | 'vertical' | 'grid_2x2' | 'custom';
  enabledDesktops: string[];
  
  // OCR Configuration
  ocrConfig: {
    confidence_threshold: number;
    preprocessing: boolean;
    language: string;
    timeout: number;
  };
  
  // Zone Configuration
  zoneConfig: {
    snap_to_grid: boolean;
    grid_size: number;
    min_zone_size: number;
    show_grid: boolean;
    show_rulers: boolean;
  };
  
  // Testing Configuration
  testConfig: {
    auto_test: boolean;
    test_interval: number;
    validation_threshold: number;
  };
  
  // Template Configuration
  templateConfig: {
    auto_save: boolean;
    version_control: boolean;
    export_format: 'json' | 'yaml' | 'xml';
  };
  
  // Status
  status: 'idle' | 'connecting' | 'connected' | 'designing' | 'testing' | 'error';
  lastUpdate: string;
  
  // Statistics
  stats: {
    total_zones: number;
    active_zones: number;
    test_success_rate: number;
    last_test_time: string;
  };
}

interface MultiDesktopOCRDesignerNodeProps {
  id: string;
  data: MultiDesktopOCRDesignerNodeData;
  selected?: boolean;
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export const MultiDesktopOCRDesignerNode: React.FC<MultiDesktopOCRDesignerNodeProps> = ({
  id,
  data,
  selected
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const [nodeData, setNodeData] = useState<MultiDesktopOCRDesignerNodeData>(data);
  const [desktopStreams, setDesktopStreams] = useState<{ [key: string]: string }>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ocrZones, setOcrZones] = useState<any[]>([]);
  const [currentTemplate, setCurrentTemplate] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<string>('designer');

  const { toast } = useToast();

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const statusColor = useMemo(() => {
    switch (nodeData.status) {
      case 'connected':
      case 'designing':
        return 'bg-green-500';
      case 'connecting':
      case 'testing':
        return 'bg-yellow-500';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  }, [nodeData.status]);

  const statusText = useMemo(() => {
    switch (nodeData.status) {
      case 'idle':
        return 'Ready to Connect';
      case 'connecting':
        return 'Connecting to Desktop Stream';
      case 'connected':
        return 'Connected - Ready to Design';
      case 'designing':
        return 'OCR Zone Design Active';
      case 'testing':
        return 'Running OCR Tests';
      case 'error':
        return error || 'Connection Error';
      default:
        return 'Unknown Status';
    }
  }, [nodeData.status, error]);

  // ============================================================================
  // CONNECTION MANAGEMENT
  // ============================================================================

  const connectToDesktopStream = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      setNodeData(prev => ({ ...prev, status: 'connecting' }));

      // Simulate WebSocket connection to desktop stream service
      // In real implementation, this would connect to the actual desktop stream service
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Mock desktop stream data
      const mockStreams = {
        'desktop-1': 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=',
        'desktop-2': 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k='
      };

      setDesktopStreams(mockStreams);
      setNodeData(prev => ({ 
        ...prev, 
        status: 'connected',
        isConnected: true,
        lastUpdate: new Date().toISOString()
      }));

      toast({
        title: "Desktop Stream Connected",
        description: "Successfully connected to multi-desktop stream",
      });

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to connect to desktop stream';
      setError(errorMessage);
      setNodeData(prev => ({ ...prev, status: 'error', isConnected: false }));
      
      toast({
        title: "Connection Failed",
        description: errorMessage,
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  const disconnectFromDesktopStream = useCallback(() => {
    setDesktopStreams({});
    setNodeData(prev => ({ 
      ...prev, 
      status: 'idle',
      isConnected: false,
      lastUpdate: new Date().toISOString()
    }));

    toast({
      title: "Desktop Stream Disconnected",
      description: "Disconnected from multi-desktop stream",
    });
  }, [toast]);

  // ============================================================================
  // OCR ZONE MANAGEMENT
  // ============================================================================

  const handleOCRZonesChange = useCallback((zones: any[]) => {
    setOcrZones(zones);
    setNodeData(prev => ({
      ...prev,
      stats: {
        ...prev.stats,
        total_zones: zones.length,
        active_zones: zones.filter(z => z.enabled).length
      },
      lastUpdate: new Date().toISOString()
    }));
  }, []);

  const handleTemplateChange = useCallback((template: any) => {
    setCurrentTemplate(template);
    setNodeData(prev => ({
      ...prev,
      lastUpdate: new Date().toISOString()
    }));
  }, []);

  // ============================================================================
  // CONFIGURATION HANDLERS
  // ============================================================================

  const handleConfigChange = useCallback((config: any) => {
    setNodeData(prev => ({
      ...prev,
      ...config,
      lastUpdate: new Date().toISOString()
    }));
  }, []);

  const toggleExpanded = useCallback(() => {
    setNodeData(prev => ({ ...prev, isExpanded: !prev.isExpanded }));
  }, []);

  const toggleAutoStart = useCallback(() => {
    setNodeData(prev => ({ ...prev, autoStart: !prev.autoStart }));
  }, []);

  // ============================================================================
  // EXPORT/IMPORT HANDLERS
  // ============================================================================

  const exportConfiguration = useCallback(() => {
    const exportData = {
      nodeId: id,
      nodeType: 'multi_desktop_ocr_designer',
      configuration: nodeData,
      timestamp: new Date().toISOString(),
      version: '1.0.0'
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { 
      type: 'application/json' 
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ocr-designer-config-${id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast({
      title: "Configuration Exported",
      description: "OCR designer configuration has been downloaded",
    });
  }, [id, nodeData, toast]);

  const importConfiguration = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const importData = JSON.parse(e.target?.result as string);
          if (importData.nodeType === 'multi_desktop_ocr_designer') {
            setNodeData(prev => ({
              ...prev,
              ...importData.configuration,
              lastUpdate: new Date().toISOString()
            }));

            toast({
              title: "Configuration Imported",
              description: "OCR designer configuration has been loaded",
            });
          } else {
            throw new Error('Invalid configuration file');
          }
        } catch (err) {
          toast({
            title: "Import Failed",
            description: "Failed to import configuration file",
            variant: "destructive"
          });
        }
      };
      reader.readAsText(file);
    };
    input.click();
  }, [toast]);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Auto-connect on mount if enabled
  useEffect(() => {
    if (nodeData.autoStart && !nodeData.isConnected) {
      connectToDesktopStream();
    }
  }, [nodeData.autoStart, nodeData.isConnected, connectToDesktopStream]);

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const renderCompactView = () => (
    <div className="space-y-3">
      {/* Status Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className={`w-2 h-2 rounded-full ${statusColor}`} />
          <span className="text-sm font-medium">{statusText}</span>
        </div>
        <div className="flex items-center space-x-1">
          <Badge variant="outline" className="text-xs">
            {nodeData.stats.total_zones} zones
          </Badge>
          {nodeData.stats.test_success_rate > 0 && (
            <Badge variant="default" className="text-xs">
              {(nodeData.stats.test_success_rate * 100).toFixed(0)}% success
            </Badge>
          )}
        </div>
      </div>

      {/* Quick Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Switch
            checked={nodeData.autoStart}
            onCheckedChange={toggleAutoStart}
            className="scale-90"
          />
          <Label className="text-xs">Auto-start</Label>
        </div>
        
        <div className="flex items-center space-x-1">
          {!nodeData.isConnected ? (
            <Button
              size="sm"
              variant="outline"
              onClick={connectToDesktopStream}
              disabled={isLoading}
            >
              {isLoading ? (
                <div className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
              ) : (
                <Play className="w-3 h-3" />
              )}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={disconnectFromDesktopStream}
            >
              <Pause className="w-3 h-3" />
            </Button>
          )}
          
          <Button
            size="sm"
            variant="ghost"
            onClick={toggleExpanded}
          >
            {nodeData.isExpanded ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
          </Button>
        </div>
      </div>

      {/* Connection Status */}
      {nodeData.isConnected && (
        <div className="text-xs text-muted-foreground">
          Connected to {Object.keys(desktopStreams).length} desktop(s)
        </div>
      )}
    </div>
  );

  const renderExpandedView = () => (
    <div className="space-y-4">
      {/* Compact View */}
      {renderCompactView()}
      
      <Separator />

      {/* Error Display */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-700">{error}</span>
          </div>
        </div>
      )}

      {/* Main Interface Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="designer" className="flex items-center gap-2">
            <Layout className="w-4 h-4" />
            Visual Designer
          </TabsTrigger>
          <TabsTrigger value="configuration" className="flex items-center gap-2">
            <Edit3 className="w-4 h-4" />
            Zone Configuration
          </TabsTrigger>
        </TabsList>

        <TabsContent value="designer" className="mt-4">
          <div className="border rounded-lg min-h-[600px]">
            <MultiDesktopOCRZoneDesigner
              config={nodeData}
              onConfigChange={handleConfigChange}
              desktopStreams={desktopStreams}
              isConnected={nodeData.isConnected}
              onConnect={connectToDesktopStream}
              onDisconnect={disconnectFromDesktopStream}
            />
          </div>
        </TabsContent>

        <TabsContent value="configuration" className="mt-4">
          <div className="border rounded-lg">
            <OCRZoneConfigurationPanel
              desktopStreams={desktopStreams}
              onZonesChange={handleOCRZonesChange}
              onTemplateChange={handleTemplateChange}
              initialZones={ocrZones}
              initialTemplate={currentTemplate}
              isConnected={nodeData.isConnected}
              className="min-h-[500px]"
            />
          </div>
        </TabsContent>
      </Tabs>

      <Separator />

      {/* Advanced Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Button
            size="sm"
            variant="outline"
            onClick={exportConfiguration}
            disabled={ocrZones.length === 0}
          >
            <Download className="w-3 h-3 mr-1" />
            Export
          </Button>
          
          <Button
            size="sm"
            variant="outline"
            onClick={importConfiguration}
          >
            <Upload className="w-3 h-3 mr-1" />
            Import
          </Button>

          <Badge variant="outline" className="flex items-center gap-1 ml-2">
            <Target className="w-3 h-3" />
            {ocrZones.length} Zones
          </Badge>

          {currentTemplate && (
            <Badge variant="secondary" className="flex items-center gap-1">
              <Layout className="w-3 h-3" />
              {currentTemplate.name}
            </Badge>
          )}
        </div>

        <div className="text-xs text-muted-foreground">
          Last updated: {new Date(nodeData.lastUpdate).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <div className={`min-w-[320px] ${nodeData.isExpanded ? 'min-w-[800px]' : ''}`}>
      {/* Input Handles */}
      <Handle
        type="target"
        position={Position.Left}
        id="desktop_stream"
        style={{ top: '25%', background: '#3b82f6' }}
      />
      <Handle
        type="target"
        position={Position.Left}
        id="websocket_config"
        style={{ top: '75%', background: '#10b981' }}
      />

      {/* Node Content */}
      <Card className={`${selected ? 'ring-2 ring-blue-500' : ''} transition-all duration-200`}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center space-x-2 text-sm">
            <Layout className="w-4 h-4" />
            <span>Multi-Desktop OCR Designer</span>
            {nodeData.isConnected && (
              <div className={`w-2 h-2 rounded-full ${statusColor} animate-pulse`} />
            )}
          </CardTitle>
        </CardHeader>
        
        <CardContent className="pt-0">
          {nodeData.isExpanded ? renderExpandedView() : renderCompactView()}
        </CardContent>
      </Card>

      {/* Output Handles */}
      <Handle
        type="source"
        position={Position.Right}
        id="ocr_zones"
        style={{ top: '20%', background: '#f59e0b' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="test_results"
        style={{ top: '40%', background: '#8b5cf6' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="templates"
        style={{ top: '60%', background: '#06b6d4' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="status"
        style={{ top: '80%', background: '#84cc16' }}
      />
    </div>
  );
};

export default MultiDesktopOCRDesignerNode;