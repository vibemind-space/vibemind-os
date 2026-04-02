
import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  Settings, 
  Layout, 
  Zap, 
  Grid3X3, 
  Plug, 
  Save, 
  RotateCcw,
  Monitor,
  Palette,
  Clock,
  Shield
} from 'lucide-react';
import { toast } from 'sonner';
import { WorkflowSettings, DEFAULT_WORKFLOW_SETTINGS } from '@/types/settings';

interface WorkflowSettingsProps {
  settings?: WorkflowSettings;
  onSettingsChange?: (settings: WorkflowSettings) => void;
}

const WorkflowSettingsComponent: React.FC<WorkflowSettingsProps> = ({
  settings = DEFAULT_WORKFLOW_SETTINGS,
  onSettingsChange,
}) => {
  const [currentSettings, setCurrentSettings] = useState<WorkflowSettings>(settings);

  const updateSettings = (path: string, value: any) => {
    const keys = path.split('.');
    const newSettings = { ...currentSettings };
    let current = newSettings as any;
    
    for (let i = 0; i < keys.length - 1; i++) {
      current = current[keys[i]];
    }
    current[keys[keys.length - 1]] = value;
    
    setCurrentSettings(newSettings);
    onSettingsChange?.(newSettings);
  };

  const handleSaveSettings = () => {
    localStorage.setItem('trae-workflow-settings', JSON.stringify(currentSettings));
    toast.success('Settings saved successfully!');
  };

  const handleResetSettings = () => {
    setCurrentSettings(DEFAULT_WORKFLOW_SETTINGS);
    onSettingsChange?.(DEFAULT_WORKFLOW_SETTINGS);
    toast.info('Settings reset to defaults');
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Settings className="w-5 h-5 text-primary" />
            <h3 className="text-lg font-semibold">Workflow Settings</h3>
          </div>
          <div className="flex space-x-2">
            <Button variant="outline" size="sm" onClick={handleResetSettings}>
              <RotateCcw className="w-4 h-4 mr-2" />
              Reset
            </Button>
            <Button size="sm" onClick={handleSaveSettings}>
              <Save className="w-4 h-4 mr-2" />
              Save
            </Button>
          </div>
        </div>
      </div>

      {/* Settings Content */}
      <div className="flex-1 overflow-y-auto">
        <Tabs defaultValue="panel" className="h-full">
          <TabsList className="w-full justify-start border-b rounded-none bg-transparent p-0 h-auto">
            <TabsTrigger value="panel" className="flex items-center space-x-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              <Layout className="w-4 h-4" />
              <span>Panel</span>
            </TabsTrigger>
            <TabsTrigger value="execution" className="flex items-center space-x-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              <Zap className="w-4 h-4" />
              <span>Execution</span>
            </TabsTrigger>
            <TabsTrigger value="canvas" className="flex items-center space-x-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              <Grid3X3 className="w-4 h-4" />
              <span>Canvas</span>
            </TabsTrigger>
            <TabsTrigger value="integration" className="flex items-center space-x-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              <Plug className="w-4 h-4" />
              <span>Integration</span>
            </TabsTrigger>
          </TabsList>

          {/* Panel Settings */}
          <TabsContent value="panel" className="p-4 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Layout className="w-5 h-5" />
                  <span>Layout Configuration</span>
                </CardTitle>
                <CardDescription>Configure panel layout and behavior</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Canvas Panel Size (%)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.panel.layout.defaultPanelSizes.canvas}
                      onChange={(e) => updateSettings('panel.layout.defaultPanelSizes.canvas', parseInt(e.target.value))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Debug Panel Size (%)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.panel.layout.defaultPanelSizes.debug}
                      onChange={(e) => updateSettings('panel.layout.defaultPanelSizes.debug', parseInt(e.target.value))}
                    />
                  </div>
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Remember Panel State</Label>
                  <Switch
                    checked={currentSettings.panel.layout.rememberPanelState}
                    onCheckedChange={(checked) => updateSettings('panel.layout.rememberPanelState', checked)}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Auto-hide Empty Panels</Label>
                  <Switch
                    checked={currentSettings.panel.layout.autoHideEmptyPanels}
                    onCheckedChange={(checked) => updateSettings('panel.layout.autoHideEmptyPanels', checked)}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Palette className="w-5 h-5" />
                  <span>Theme Settings</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Theme Mode</Label>
                  <Select value={currentSettings.panel.theme.mode} onValueChange={(value) => updateSettings('panel.theme.mode', value)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="light">Light</SelectItem>
                      <SelectItem value="dark">Dark</SelectItem>
                      <SelectItem value="system">System</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>High Contrast</Label>
                  <Switch
                    checked={currentSettings.panel.theme.highContrast}
                    onCheckedChange={(checked) => updateSettings('panel.theme.highContrast', checked)}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Reduced Motion</Label>
                  <Switch
                    checked={currentSettings.panel.theme.reducedMotion}
                    onCheckedChange={(checked) => updateSettings('panel.theme.reducedMotion', checked)}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Monitor className="w-5 h-5" />
                  <span>Console Settings</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Auto Scroll</Label>
                  <Switch
                    checked={currentSettings.panel.console.autoScroll}
                    onCheckedChange={(checked) => updateSettings('panel.console.autoScroll', checked)}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Max Log Entries</Label>
                  <Input 
                    type="number"
                    value={currentSettings.panel.console.maxLogEntries}
                    onChange={(e) => updateSettings('panel.console.maxLogEntries', parseInt(e.target.value))}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Timestamp Format</Label>
                  <Select value={currentSettings.panel.console.timestampFormat} onValueChange={(value) => updateSettings('panel.console.timestampFormat', value)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="12h">12 Hour</SelectItem>
                      <SelectItem value="24h">24 Hour</SelectItem>
                      <SelectItem value="relative">Relative</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Execution Settings */}
          <TabsContent value="execution" className="p-4 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Clock className="w-5 h-5" />
                  <span>Timeout Configuration</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Enable Timeouts</Label>
                  <Switch
                    checked={currentSettings.execution.timeout.enableTimeouts}
                    onCheckedChange={(checked) => updateSettings('execution.timeout.enableTimeouts', checked)}
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Node Timeout (seconds)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.execution.timeout.nodeTimeout}
                      onChange={(e) => updateSettings('execution.timeout.nodeTimeout', parseInt(e.target.value))}
                      disabled={!currentSettings.execution.timeout.enableTimeouts}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Workflow Timeout (seconds)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.execution.timeout.workflowTimeout}
                      onChange={(e) => updateSettings('execution.timeout.workflowTimeout', parseInt(e.target.value))}
                      disabled={!currentSettings.execution.timeout.enableTimeouts}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Shield className="w-5 h-5" />
                  <span>Error Handling</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Stop on Error</Label>
                  <Switch
                    checked={currentSettings.execution.errorHandling.stopOnError}
                    onCheckedChange={(checked) => updateSettings('execution.errorHandling.stopOnError', checked)}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Retry Failed Nodes</Label>
                  <Switch
                    checked={currentSettings.execution.errorHandling.retryFailedNodes}
                    onCheckedChange={(checked) => updateSettings('execution.errorHandling.retryFailedNodes', checked)}
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Max Retries</Label>
                    <Input 
                      type="number"
                      value={currentSettings.execution.errorHandling.maxRetries}
                      onChange={(e) => updateSettings('execution.errorHandling.maxRetries', parseInt(e.target.value))}
                      disabled={!currentSettings.execution.errorHandling.retryFailedNodes}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Retry Delay (ms)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.execution.errorHandling.retryDelay}
                      onChange={(e) => updateSettings('execution.errorHandling.retryDelay', parseInt(e.target.value))}
                      disabled={!currentSettings.execution.errorHandling.retryFailedNodes}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Performance Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Max Concurrent Nodes</Label>
                  <Input 
                    type="number"
                    value={currentSettings.execution.performance.maxConcurrentNodes}
                    onChange={(e) => updateSettings('execution.performance.maxConcurrentNodes', parseInt(e.target.value))}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Memory Limit (MB)</Label>
                  <Input 
                    type="number"
                    value={currentSettings.execution.performance.memoryLimit}
                    onChange={(e) => updateSettings('execution.performance.memoryLimit', parseInt(e.target.value))}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Enable Caching</Label>
                  <Switch
                    checked={currentSettings.execution.performance.enableCaching}
                    onCheckedChange={(checked) => updateSettings('execution.performance.enableCaching', checked)}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Canvas Settings */}
          <TabsContent value="canvas" className="p-4 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Grid3X3 className="w-5 h-5" />
                  <span>Grid Settings</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Show Grid</Label>
                  <Switch
                    checked={currentSettings.canvas.grid.showGrid}
                    onCheckedChange={(checked) => updateSettings('canvas.grid.showGrid', checked)}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Snap to Grid</Label>
                  <Switch
                    checked={currentSettings.canvas.grid.snapToGrid}
                    onCheckedChange={(checked) => updateSettings('canvas.grid.snapToGrid', checked)}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Grid Size</Label>
                  <Input 
                    type="number"
                    value={currentSettings.canvas.grid.size}
                    onChange={(e) => updateSettings('canvas.grid.size', parseInt(e.target.value))}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Node Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Show Minimap</Label>
                  <Switch
                    checked={currentSettings.canvas.nodes.showMinimap}
                    onCheckedChange={(checked) => updateSettings('canvas.nodes.showMinimap', checked)}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Enable Animations</Label>
                  <Switch
                    checked={currentSettings.canvas.nodes.enableAnimations}
                    onCheckedChange={(checked) => updateSettings('canvas.nodes.enableAnimations', checked)}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label>Show Node IDs</Label>
                  <Switch
                    checked={currentSettings.canvas.nodes.showNodeIds}
                    onCheckedChange={(checked) => updateSettings('canvas.nodes.showNodeIds', checked)}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Auto-save Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Enable Auto-save</Label>
                  <Switch
                    checked={currentSettings.canvas.autoSave.enabled}
                    onCheckedChange={(checked) => updateSettings('canvas.autoSave.enabled', checked)}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>Auto-save Interval (minutes)</Label>
                  <Input 
                    type="number"
                    value={currentSettings.canvas.autoSave.interval}
                    onChange={(e) => updateSettings('canvas.autoSave.interval', parseInt(e.target.value))}
                    disabled={!currentSettings.canvas.autoSave.enabled}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Integration Settings */}
          <TabsContent value="integration" className="p-4 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Plug className="w-5 h-5" />
                  <span>API Configuration</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Base URL</Label>
                  <Input 
                    value={currentSettings.integration.api.baseUrl}
                    onChange={(e) => updateSettings('integration.api.baseUrl', e.target.value)}
                    placeholder="https://api.example.com"
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Timeout (ms)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.integration.api.timeout}
                      onChange={(e) => updateSettings('integration.api.timeout', parseInt(e.target.value))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Retry Attempts</Label>
                    <Input 
                      type="number"
                      value={currentSettings.integration.api.retryAttempts}
                      onChange={(e) => updateSettings('integration.api.retryAttempts', parseInt(e.target.value))}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Webhook Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Enable Webhooks</Label>
                  <Switch
                    checked={currentSettings.integration.webhooks.enableWebhooks}
                    onCheckedChange={(checked) => updateSettings('integration.webhooks.enableWebhooks', checked)}
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Default Timeout (ms)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.integration.webhooks.defaultTimeout}
                      onChange={(e) => updateSettings('integration.webhooks.defaultTimeout', parseInt(e.target.value))}
                      disabled={!currentSettings.integration.webhooks.enableWebhooks}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Max Payload Size (KB)</Label>
                    <Input 
                      type="number"
                      value={currentSettings.integration.webhooks.maxPayloadSize}
                      onChange={(e) => updateSettings('integration.webhooks.maxPayloadSize', parseInt(e.target.value))}
                      disabled={!currentSettings.integration.webhooks.enableWebhooks}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Security Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label>Enable Third-party Integrations</Label>
                  <Switch
                    checked={currentSettings.integration.external.enableThirdPartyIntegrations}
                    onCheckedChange={(checked) => updateSettings('integration.external.enableThirdPartyIntegrations', checked)}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label>API Key Storage</Label>
                  <Select value={currentSettings.integration.external.apiKeyStorage} onValueChange={(value) => updateSettings('integration.external.apiKeyStorage', value)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="local">Local Storage</SelectItem>
                      <SelectItem value="secure">Secure Storage</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default WorkflowSettingsComponent;
