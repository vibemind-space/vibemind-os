/**
 * Live Desktop Configuration Manager
 * Handles saving, loading, and managing Live Desktop configurations
 */

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Save, Upload, Download, Trash2, Plus, Settings, Copy } from 'lucide-react';
import { LiveDesktopConfig, LiveDesktopTemplate } from '@/types/liveDesktop';
import { useToast } from '@/hooks/use-toast';
import { ConfigApiService } from '@/services/configApiService';
// Import centralized WebSocket configuration for consistent URL handling
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';

interface LiveDesktopConfigManagerProps {
  currentConfig: LiveDesktopConfig | null;
  onConfigLoad: (config: LiveDesktopConfig) => void;
  onConfigSave: (config: LiveDesktopConfig) => void;
}

const DEFAULT_TEMPLATES: LiveDesktopTemplate[] = [
  {
    id: 'monitoring-basic',
    name: 'Basic Monitoring',
    description: 'Simple desktop monitoring with basic OCR regions',
    category: 'monitoring',
    config: {
      streaming: { fps: 5, quality: 70, scale: 0.8 },
      ocr: { enabled: true, extractionInterval: 30, autoSend: false },
      connection: { timeout: 30, maxReconnectAttempts: 5, reconnectInterval: 5 }
    }
  },
  {
    id: 'automation-high-freq',
    name: 'High Frequency Automation',
    description: 'High-frequency streaming for real-time automation',
    category: 'automation',
    config: {
      streaming: { fps: 15, quality: 85, scale: 1.0 },
      ocr: { enabled: true, extractionInterval: 5, autoSend: true },
      connection: { timeout: 10, maxReconnectAttempts: 10, reconnectInterval: 2 }
    }
  },
  {
    id: 'data-extraction',
    name: 'Data Extraction',
    description: 'Optimized for OCR data extraction workflows',
    category: 'data-extraction',
    config: {
      streaming: { fps: 3, quality: 95, scale: 1.0 },
      ocr: { enabled: true, extractionInterval: 60, autoSend: true },
      connection: { timeout: 60, maxReconnectAttempts: 3, reconnectInterval: 10 }
    }
  }
];

export const LiveDesktopConfigManager: React.FC<LiveDesktopConfigManagerProps> = ({
  currentConfig,
  onConfigLoad,
  onConfigSave
}) => {
  const [savedConfigs, setSavedConfigs] = useState<LiveDesktopConfig[]>([]);
  const [isNewConfigDialogOpen, setIsNewConfigDialogOpen] = useState(false);
  const [newConfigName, setNewConfigName] = useState('');
  const [newConfigDescription, setNewConfigDescription] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const { toast } = useToast();

  // Load saved configurations from local API on mount
  useEffect(() => {
    const loadConfigs = async () => {
      try {
        const data = await ConfigApiService.getConfigs();
        setSavedConfigs(data.map(item => {
          const config = item.configuration as Record<string, unknown>;
          return {
            id: item.id,
            name: item.name,
            description: item.description || '',
            websocketUrl: (config.websocketUrl as string) || WEBSOCKET_CONFIG.BASE_URL,
            streaming: (config.streaming as LiveDesktopConfig['streaming']) || { fps: 10, quality: 75, scale: 0.8 },
            connection: (config.connection as LiveDesktopConfig['connection']) || { timeout: 30, maxReconnectAttempts: 5, reconnectInterval: 5 },
            ocr: (config.ocr as LiveDesktopConfig['ocr']) || { enabled: false, extractionInterval: 30, autoSend: false },
            ocrRegions: (config.ocrRegions as LiveDesktopConfig['ocrRegions']) || [],
            createdAt: item.created_at || new Date().toISOString(),
            updatedAt: item.updated_at || new Date().toISOString(),
            category: item.category || 'custom'
          } as LiveDesktopConfig;
        }));
      } catch (error) {
        console.error('Error loading configs from API:', error);
        // Fallback to localStorage
        const saved = localStorage.getItem('liveDesktopConfigs');
        if (saved) {
          setSavedConfigs(JSON.parse(saved));
        }
      }
    };

    loadConfigs();
  }, []);

  // Save configurations to localStorage
  const saveToStorage = (configs: LiveDesktopConfig[]) => {
    localStorage.setItem('liveDesktopConfigs', JSON.stringify(configs));
    setSavedConfigs(configs);
  };

  const handleSaveCurrentConfig = async () => {
    if (!currentConfig) {
      toast({
        title: "No Configuration",
        description: "Please create a configuration first",
        variant: "destructive",
      });
      return;
    }

    try {
      // Check if config exists (update) or is new (create)
      const isExisting = savedConfigs.some(c => c.id === currentConfig.id);
      let savedData;

      if (isExisting) {
        savedData = await ConfigApiService.updateConfig(currentConfig.id, {
          name: currentConfig.name,
          description: currentConfig.description,
          category: currentConfig.category || 'custom',
          configuration: currentConfig as unknown as Record<string, unknown>,
        });
      } else {
        savedData = await ConfigApiService.createConfig({
          name: currentConfig.name,
          description: currentConfig.description,
          category: currentConfig.category || 'custom',
          configuration: currentConfig as unknown as Record<string, unknown>,
          is_active: true,
        });
      }

      // Update local state
      const now = new Date().toISOString();
      const updated = savedConfigs.map(config =>
        config.id === currentConfig.id ? { ...currentConfig, updatedAt: now } : config
      );

      if (!updated.some(config => config.id === currentConfig.id)) {
        updated.push({ ...currentConfig, id: savedData?.id || currentConfig.id, updatedAt: now });
      }

      setSavedConfigs(updated);
      onConfigSave(currentConfig);

      toast({
        title: "Configuration Saved",
        description: `"${currentConfig.name}" has been saved successfully`,
      });
    } catch (error) {
      console.error('Error saving config:', error);
      toast({
        title: "Save Failed",
        description: "Failed to save configuration to database",
        variant: "destructive",
      });
    }
  };

  const handleLoadConfig = (config: LiveDesktopConfig) => {
    onConfigLoad(config);
    toast({
      title: "Configuration Loaded",
      description: `"${config.name}" has been loaded`,
    });
  };

  const handleDeleteConfig = (configId: string) => {
    const configToDelete = savedConfigs.find(c => c.id === configId);
    const updatedConfigs = savedConfigs.filter(c => c.id !== configId);
    saveToStorage(updatedConfigs);

    toast({
      title: "Configuration Deleted",
      description: `"${configToDelete?.name}" has been deleted`,
    });
  };

  const handleCreateNewConfig = () => {
    if (!newConfigName.trim()) {
      toast({
        title: "Name Required",
        description: "Please enter a configuration name",
        variant: "destructive",
      });
      return;
    }

    const template = DEFAULT_TEMPLATES.find(t => t.id === selectedTemplate);
    const baseConfig = template?.config || {};

    const newConfig: LiveDesktopConfig = {
      id: `config-${Date.now()}`,
      name: newConfigName.trim(),
      description: newConfigDescription.trim(),
      websocketUrl: WEBSOCKET_CONFIG.BASE_URL,
      streaming: {
        fps: baseConfig.streaming?.fps || 10,
        quality: baseConfig.streaming?.quality || 75,
        scale: baseConfig.streaming?.scale || 0.8,
      },
      connection: {
        timeout: baseConfig.connection?.timeout || 30,
        maxReconnectAttempts: baseConfig.connection?.maxReconnectAttempts || 5,
        reconnectInterval: baseConfig.connection?.reconnectInterval || 5,
      },
      ocr: {
        enabled: baseConfig.ocr?.enabled || false,
        extractionInterval: baseConfig.ocr?.extractionInterval || 30,
        autoSend: baseConfig.ocr?.autoSend || false,
      },
      ocrRegions: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    onConfigLoad(newConfig);
    setIsNewConfigDialogOpen(false);
    setNewConfigName('');
    setNewConfigDescription('');
    setSelectedTemplate('');

    toast({
      title: "Configuration Created",
      description: `"${newConfig.name}" has been created`,
    });
  };

  const handleDuplicateConfig = (config: LiveDesktopConfig) => {
    const duplicatedConfig: LiveDesktopConfig = {
      ...config,
      id: `config-${Date.now()}`,
      name: `${config.name} (Copy)`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    onConfigLoad(duplicatedConfig);

    toast({
      title: "Configuration Duplicated",
      description: `"${duplicatedConfig.name}" has been created`,
    });
  };

  const exportConfig = (config: LiveDesktopConfig) => {
    const dataStr = JSON.stringify(config, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${config.name.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.json`;
    link.click();
    URL.revokeObjectURL(url);

    toast({
      title: "Configuration Exported",
      description: `"${config.name}" has been exported`,
    });
  };

  return (
    <div className="space-y-6">
      {/* Current Configuration */}
      {currentConfig && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Current Configuration</span>
              <Button onClick={handleSaveCurrentConfig} size="sm">
                <Save className="w-4 h-4 mr-2" />
                Save
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-medium">{currentConfig.name}</span>
                <Badge variant="outline">
                  {currentConfig.ocrRegions?.length || 0} OCR Regions
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">{currentConfig.description}</p>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>FPS: {currentConfig.streaming.fps}</div>
                <div>Quality: {currentConfig.streaming.quality}%</div>
                <div>OCR: {currentConfig.ocr.enabled ? 'Enabled' : 'Disabled'}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Create New Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration Management</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Dialog open={isNewConfigDialogOpen} onOpenChange={setIsNewConfigDialogOpen}>
              <DialogTrigger asChild>
                <Button>
                  <Plus className="w-4 h-4 mr-2" />
                  New Configuration
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create New Configuration</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="configName">Configuration Name</Label>
                    <Input
                      id="configName"
                      value={newConfigName}
                      onChange={(e) => setNewConfigName(e.target.value)}
                      placeholder="Enter configuration name"
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="configDescription">Description</Label>
                    <Textarea
                      id="configDescription"
                      value={newConfigDescription}
                      onChange={(e) => setNewConfigDescription(e.target.value)}
                      placeholder="Describe this configuration's purpose"
                      rows={3}
                    />
                  </div>

                  <div>
                    <Label htmlFor="template">Template</Label>
                    <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
                      <SelectTrigger>
                        <SelectValue placeholder="Choose a template (optional)" />
                      </SelectTrigger>
                      <SelectContent>
                        {DEFAULT_TEMPLATES.map((template) => (
                          <SelectItem key={template.id} value={template.id}>
                            <div>
                              <div className="font-medium">{template.name}</div>
                              <div className="text-sm text-muted-foreground">{template.description}</div>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={() => setIsNewConfigDialogOpen(false)}>
                      Cancel
                    </Button>
                    <Button onClick={handleCreateNewConfig}>
                      Create Configuration
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </CardContent>
      </Card>

      {/* Saved Configurations */}
      {savedConfigs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Saved Configurations ({savedConfigs.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {savedConfigs.map((config) => (
                <div key={config.id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{config.name}</span>
                      <Badge variant="outline">
                        {config.ocrRegions?.length || 0} regions
                      </Badge>
                      {config.ocr.enabled && (
                        <Badge variant="secondary">OCR</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">{config.description}</p>
                    <div className="text-xs text-muted-foreground">
                      Updated: {new Date(config.updatedAt).toLocaleDateString()}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleLoadConfig(config)}
                    >
                      <Upload className="w-4 h-4 mr-2" />
                      Load
                    </Button>
                    
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDuplicateConfig(config)}
                    >
                      <Copy className="w-4 h-4" />
                    </Button>
                    
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => exportConfig(config)}
                    >
                      <Download className="w-4 h-4" />
                    </Button>
                    
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDeleteConfig(config.id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};