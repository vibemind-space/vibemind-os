/**
 * Virtual Desktop Creator Component
 * Modal dialog for creating new virtual desktops with configuration options
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Monitor, Settings, Bot, Zap } from 'lucide-react';
import { VirtualDesktop } from '@/types/virtualDesktop';

interface VirtualDesktopCreatorProps {
  /** Called when the dialog should close */
  onClose: () => void;
  /** Called when a new desktop should be created */
  onCreate: (config: Partial<VirtualDesktop>) => void;
  /** Initial configuration values */
  initialConfig?: Partial<VirtualDesktop>;
}

export const VirtualDesktopCreator: React.FC<VirtualDesktopCreatorProps> = ({
  onClose,
  onCreate,
  initialConfig
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const [config, setConfig] = useState<Partial<VirtualDesktop>>({
    name: '',
    resolution: { width: 1920, height: 1080 },
    streamConfig: {
      quality: 80,
      frameRate: 30,
      format: 'jpeg',
      audioEnabled: false,
      compression: 'medium',
      bitrate: 2000
    },
    automationConfig: {
      ocrEnabled: false,
      ocrRegions: [],
      eventAutomationEnabled: false,
      automationScripts: []
    },
    ...initialConfig
  });

  const [activeTab, setActiveTab] = useState('basic');
  const [isCreating, setIsCreating] = useState(false);

  // ============================================================================
  // PREDEFINED OPTIONS
  // ============================================================================

  const resolutionPresets = [
    { name: 'HD (1280x720)', width: 1280, height: 720 },
    { name: 'Full HD (1920x1080)', width: 1920, height: 1080 },
    { name: 'QHD (2560x1440)', width: 2560, height: 1440 },
    { name: '4K (3840x2160)', width: 3840, height: 2160 },
    { name: 'Custom', width: 0, height: 0 }
  ];

  const streamFormats = [
    { value: 'jpeg', label: 'JPEG (Best compatibility)' },
    { value: 'png', label: 'PNG (Lossless)' },
    { value: 'webp', label: 'WebP (Best compression)' }
  ];

  const compressionLevels = [
    { value: 'none', label: 'None (Highest quality)' },
    { value: 'low', label: 'Low (Good quality)' },
    { value: 'medium', label: 'Medium (Balanced)' },
    { value: 'high', label: 'High (Smallest size)' }
  ];

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleCreate = async () => {
    if (!config.name?.trim()) {
      return;
    }

    setIsCreating(true);
    try {
      await onCreate(config);
    } finally {
      setIsCreating(false);
    }
  };

  const updateConfig = (updates: Partial<VirtualDesktop>) => {
    setConfig(prev => ({
      ...prev,
      ...updates
    }));
  };

  const updateStreamConfig = (updates: any) => {
    setConfig(prev => ({
      ...prev,
      streamConfig: {
        ...prev.streamConfig,
        ...updates
      }
    }));
  };

  const updateAutomationConfig = (updates: any) => {
    setConfig(prev => ({
      ...prev,
      automationConfig: {
        ...prev.automationConfig,
        ...updates
      }
    }));
  };

  const handleResolutionPresetChange = (preset: string) => {
    const selectedPreset = resolutionPresets.find(p => p.name === preset);
    if (selectedPreset && selectedPreset.width > 0) {
      updateConfig({
        resolution: {
          width: selectedPreset.width,
          height: selectedPreset.height
        }
      });
    }
  };

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const renderBasicTab = () => (
    <div className="space-y-6">
      {/* Desktop Name */}
      <div className="space-y-2">
        <Label htmlFor="desktop-name">Desktop Name</Label>
        <Input
          id="desktop-name"
          placeholder="Enter desktop name..."
          value={config.name || ''}
          onChange={(e) => updateConfig({ name: e.target.value })}
        />
      </div>

      {/* Resolution Settings */}
      <div className="space-y-4">
        <Label>Display Resolution</Label>
        
        {/* Preset Selection */}
        <Select onValueChange={handleResolutionPresetChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select resolution preset" />
          </SelectTrigger>
          <SelectContent>
            {resolutionPresets.map(preset => (
              <SelectItem key={preset.name} value={preset.name}>
                {preset.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Custom Resolution */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="width">Width</Label>
            <Input
              id="width"
              type="number"
              value={config.resolution?.width || 1920}
              onChange={(e) => updateConfig({
                resolution: {
                  ...config.resolution!,
                  width: parseInt(e.target.value) || 1920
                }
              })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="height">Height</Label>
            <Input
              id="height"
              type="number"
              value={config.resolution?.height || 1080}
              onChange={(e) => updateConfig({
                resolution: {
                  ...config.resolution!,
                  height: parseInt(e.target.value) || 1080
                }
              })}
            />
          </div>
        </div>
      </div>

      {/* Preview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Preview</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-4">
            <Monitor className="h-8 w-8 text-blue-500" />
            <div>
              <p className="font-medium">{config.name || 'Unnamed Desktop'}</p>
              <p className="text-sm text-gray-500">
                {config.resolution?.width}x{config.resolution?.height}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  const renderStreamingTab = () => (
    <div className="space-y-6">
      {/* Stream Quality */}
      <div className="space-y-4">
        <Label>Stream Quality: {config.streamConfig?.quality}%</Label>
        <Slider
          value={[config.streamConfig?.quality || 80]}
          onValueChange={([value]) => updateStreamConfig({ quality: value })}
          min={10}
          max={100}
          step={5}
          className="w-full"
        />
        <p className="text-sm text-gray-500">
          Higher quality means better image but larger file sizes
        </p>
      </div>

      {/* Frame Rate */}
      <div className="space-y-4">
        <Label>Frame Rate: {config.streamConfig?.frameRate} FPS</Label>
        <Slider
          value={[config.streamConfig?.frameRate || 30]}
          onValueChange={([value]) => updateStreamConfig({ frameRate: value })}
          min={1}
          max={60}
          step={1}
          className="w-full"
        />
        <p className="text-sm text-gray-500">
          Higher frame rates provide smoother video but use more bandwidth
        </p>
      </div>

      {/* Stream Format */}
      <div className="space-y-2">
        <Label>Stream Format</Label>
        <Select 
          value={config.streamConfig?.format || 'jpeg'}
          onValueChange={(value) => updateStreamConfig({ format: value })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {streamFormats.map(format => (
              <SelectItem key={format.value} value={format.value}>
                {format.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Compression */}
      <div className="space-y-2">
        <Label>Compression Level</Label>
        <Select 
          value={config.streamConfig?.compression || 'medium'}
          onValueChange={(value) => updateStreamConfig({ compression: value })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {compressionLevels.map(level => (
              <SelectItem key={level.value} value={level.value}>
                {level.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Audio Capture */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <Label>Audio Capture</Label>
          <p className="text-sm text-gray-500">
            Capture audio from the virtual desktop
          </p>
        </div>
        <Switch
          checked={config.streamConfig?.audioEnabled || false}
          onCheckedChange={(checked) => updateStreamConfig({ audioEnabled: checked })}
        />
      </div>

      {/* Bitrate */}
      <div className="space-y-4">
        <Label>Target Bitrate: {config.streamConfig?.bitrate} kbps</Label>
        <Slider
          value={[config.streamConfig?.bitrate || 2000]}
          onValueChange={([value]) => updateStreamConfig({ bitrate: value })}
          min={500}
          max={10000}
          step={100}
          className="w-full"
        />
        <p className="text-sm text-gray-500">
          Higher bitrates provide better quality but require more bandwidth
        </p>
      </div>
    </div>
  );

  const renderAutomationTab = () => (
    <div className="space-y-6">
      {/* OCR Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center">
            <Bot className="h-4 w-4 mr-2" />
            OCR (Optical Character Recognition)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Label>Enable OCR Processing</Label>
              <p className="text-sm text-gray-500">
                Automatically extract text from the desktop
              </p>
            </div>
            <Switch
              checked={config.automationConfig?.ocrEnabled || false}
              onCheckedChange={(checked) => updateAutomationConfig({ ocrEnabled: checked })}
            />
          </div>
          
          {config.automationConfig?.ocrEnabled && (
            <div className="space-y-2">
              <Label>OCR Language</Label>
              <Select defaultValue="eng">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="eng">English</SelectItem>
                  <SelectItem value="deu">German</SelectItem>
                  <SelectItem value="fra">French</SelectItem>
                  <SelectItem value="spa">Spanish</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Event Automation */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center">
            <Zap className="h-4 w-4 mr-2" />
            Event Automation
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Label>Enable Event Automation</Label>
              <p className="text-sm text-gray-500">
                Automatically trigger actions based on desktop events
              </p>
            </div>
            <Switch
              checked={config.automationConfig?.eventAutomationEnabled || false}
              onCheckedChange={(checked) => updateAutomationConfig({ eventAutomationEnabled: checked })}
            />
          </div>
        </CardContent>
      </Card>

      {/* AI Agent Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center">
            <Bot className="h-4 w-4 mr-2" />
            AI Agent (Coming Soon)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-500">
            AI-powered automation and analysis will be available in a future update.
          </p>
        </CardContent>
      </Card>
    </div>
  );

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Virtual Desktop</DialogTitle>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="basic" className="flex items-center">
              <Monitor className="h-4 w-4 mr-2" />
              Basic
            </TabsTrigger>
            <TabsTrigger value="streaming" className="flex items-center">
              <Settings className="h-4 w-4 mr-2" />
              Streaming
            </TabsTrigger>
            <TabsTrigger value="automation" className="flex items-center">
              <Bot className="h-4 w-4 mr-2" />
              Automation
            </TabsTrigger>
          </TabsList>

          <TabsContent value="basic" className="mt-6">
            {renderBasicTab()}
          </TabsContent>

          <TabsContent value="streaming" className="mt-6">
            {renderStreamingTab()}
          </TabsContent>

          <TabsContent value="automation" className="mt-6">
            {renderAutomationTab()}
          </TabsContent>
        </Tabs>

        {/* Actions */}
        <div className="flex justify-end space-x-2 pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button 
            onClick={handleCreate}
            disabled={!config.name?.trim() || isCreating}
          >
            {isCreating ? 'Creating...' : 'Create Desktop'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};