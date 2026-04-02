/**
 * Virtual Desktop Details Component
 * Detailed view and management of a single virtual desktop
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { 
  Monitor, 
  Play, 
  Pause, 
  Square, 
  Plus,
  Trash2,
  Settings,
  Activity,
  Cpu,
  MemoryStick,
  Network,
  HardDrive,
  RefreshCw,
  Camera,
  Terminal,
  FileText
} from 'lucide-react';
import { VirtualDesktop, VirtualDesktopApplication } from '@/types/virtualDesktop';
import { getVirtualDesktopManager } from '@/services/virtualDesktopManager';
import { useToast } from '@/hooks/use-toast';

interface VirtualDesktopDetailsProps {
  /** Virtual desktop to display */
  desktop: VirtualDesktop;
  /** Called when desktop is updated */
  onUpdate: (updates: Partial<VirtualDesktop>) => void;
}

export const VirtualDesktopDetails: React.FC<VirtualDesktopDetailsProps> = ({
  desktop,
  onUpdate
}) => {
  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const [isLaunchingApp, setIsLaunchingApp] = useState(false);
  const [newAppPath, setNewAppPath] = useState('');
  const [newAppName, setNewAppName] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const { toast } = useToast();
  const virtualDesktopManager = getVirtualDesktopManager();

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleLaunchApplication = async () => {
    if (!newAppPath.trim()) return;

    setIsLaunchingApp(true);
    try {
      await virtualDesktopManager.launchApplication(desktop.id, newAppPath, {
        name: newAppName.trim() || undefined
      });
      
      setNewAppPath('');
      setNewAppName('');
      
      toast({
        title: "Application Launched",
        description: `Successfully launched ${newAppName || newAppPath}`,
      });
    } catch (error) {
      console.error('Error launching application:', error);
      toast({
        title: "Launch Failed",
        description: "Failed to launch application",
        variant: "destructive"
      });
    } finally {
      setIsLaunchingApp(false);
    }
  };

  const handleCloseApplication = async (appId: string) => {
    try {
      await virtualDesktopManager.closeApplication(desktop.id, appId);
      
      toast({
        title: "Application Closed",
        description: "Application closed successfully",
      });
    } catch (error) {
      console.error('Error closing application:', error);
      toast({
        title: "Close Failed",
        description: "Failed to close application",
        variant: "destructive"
      });
    }
  };

  const handleTakeScreenshot = async () => {
    try {
      setRefreshing(true);
      const screenshot = await virtualDesktopManager.takeScreenshot(desktop.id);
      
      // In a real implementation, this would display or download the screenshot
      toast({
        title: "Screenshot Taken",
        description: "Desktop screenshot captured successfully",
      });
    } catch (error) {
      console.error('Error taking screenshot:', error);
      toast({
        title: "Screenshot Failed",
        description: "Failed to capture screenshot",
        variant: "destructive"
      });
    } finally {
      setRefreshing(false);
    }
  };

  const handleSendInput = async (inputType: 'mouse' | 'keyboard', inputData: any) => {
    try {
      await virtualDesktopManager.sendInput(desktop.id, inputType, inputData);
      
      toast({
        title: "Input Sent",
        description: `${inputType} input sent successfully`,
      });
    } catch (error) {
      console.error('Error sending input:', error);
      toast({
        title: "Input Failed",
        description: "Failed to send input",
        variant: "destructive"
      });
    }
  };

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const renderDesktopInfo = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center">
          <Monitor className="h-5 w-5 mr-2" />
          Desktop Information
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label className="text-sm font-medium">Name</Label>
            <p className="text-sm text-gray-600">{desktop.name}</p>
          </div>
          <div>
            <Label className="text-sm font-medium">Status</Label>
            <Badge variant={desktop.status === 'streaming' ? 'default' : 'secondary'}>
              {desktop.status}
            </Badge>
          </div>
          <div>
            <Label className="text-sm font-medium">Resolution</Label>
            <p className="text-sm text-gray-600">
              {desktop.resolution?.width || 1920}x{desktop.resolution?.height || 1080}
            </p>
          </div>
          <div>
            <Label className="text-sm font-medium">Created</Label>
            <p className="text-sm text-gray-600">
              {desktop.createdAt.toLocaleDateString()}
            </p>
          </div>
        </div>
        
        <Separator />
        
        <div className="flex space-x-2">
          <Button
            size="sm"
            variant="outline"
            onClick={handleTakeScreenshot}
            disabled={refreshing}
          >
            <Camera className="h-4 w-4 mr-2" />
            {refreshing ? 'Taking...' : 'Screenshot'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleSendInput('keyboard', { key: 'Alt+Tab' })}
          >
            <Terminal className="h-4 w-4 mr-2" />
            Alt+Tab
          </Button>
        </div>
      </CardContent>
    </Card>
  );

  const renderResourceUsage = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center">
          <Activity className="h-5 w-5 mr-2" />
          Resource Usage
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <Cpu className="h-4 w-4 text-orange-500" />
              <Label className="text-sm">CPU Usage</Label>
            </div>
            <div className="text-2xl font-bold">
              {desktop.resourceUsage.cpuUsage.toFixed(1)}%
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-orange-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.min(desktop.resourceUsage.cpuUsage, 100)}%` }}
              />
            </div>
          </div>
          
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <MemoryStick className="h-4 w-4 text-purple-500" />
              <Label className="text-sm">Memory Usage</Label>
            </div>
            <div className="text-2xl font-bold">
              {(desktop.resourceUsage.memoryUsage / 1024).toFixed(1)}GB
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-purple-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.min((desktop.resourceUsage.memoryUsage / 1024) * 10, 100)}%` }}
              />
            </div>
          </div>
          
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <Network className="h-4 w-4 text-red-500" />
              <Label className="text-sm">Network Usage</Label>
            </div>
            <div className="text-2xl font-bold">
              {(desktop.resourceUsage.networkUsage / 1000).toFixed(1)}Mbps
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-red-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.min(desktop.resourceUsage.networkUsage / 100, 100)}%` }}
              />
            </div>
          </div>
          
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <HardDrive className="h-4 w-4 text-green-500" />
              <Label className="text-sm">Disk I/O</Label>
            </div>
            <div className="text-2xl font-bold">
              {desktop.resourceUsage.diskUsage.toFixed(1)}MB/s
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-green-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.min(desktop.resourceUsage.diskUsage * 10, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const renderApplications = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center">
            <Terminal className="h-5 w-5 mr-2" />
            Applications ({desktop.applications.length})
          </div>
          <Button
            size="sm"
            onClick={() => {
              // Scroll to launch section
              document.getElementById('launch-app')?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            <Plus className="h-4 w-4 mr-2" />
            Launch App
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {desktop.applications.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Terminal className="h-12 w-12 mx-auto mb-4 text-gray-300" />
            <p>No applications running</p>
            <p className="text-sm">Launch an application to get started</p>
          </div>
        ) : (
          desktop.applications.map(app => (
            <div key={app.id} className="flex items-center justify-between p-3 border rounded-lg">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
                  <FileText className="h-4 w-4 text-blue-600" />
                </div>
                <div>
                  <p className="font-medium">{app.name}</p>
                  <p className="text-sm text-gray-500 truncate max-w-48">
                    {app.executablePath}
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <Badge 
                  variant={app.status === 'running' ? 'default' : 'secondary'}
                >
                  {app.status}
                </Badge>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleCloseApplication(app.id)}
                  disabled={app.status !== 'running'}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );

  const renderLaunchApplication = () => (
    <Card id="launch-app">
      <CardHeader>
        <CardTitle className="flex items-center">
          <Plus className="h-5 w-5 mr-2" />
          Launch Application
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="app-path">Application Path</Label>
          <Input
            id="app-path"
            placeholder="C:\Program Files\App\app.exe"
            value={newAppPath}
            onChange={(e) => setNewAppPath(e.target.value)}
          />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="app-name">Display Name (Optional)</Label>
          <Input
            id="app-name"
            placeholder="My Application"
            value={newAppName}
            onChange={(e) => setNewAppName(e.target.value)}
          />
        </div>
        
        <div className="flex space-x-2">
          <Button
            onClick={handleLaunchApplication}
            disabled={!newAppPath.trim() || isLaunchingApp}
            className="flex-1"
          >
            {isLaunchingApp ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Launching...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                Launch Application
              </>
            )}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              // In a real implementation, this would open a file picker
              toast({
                title: "File Picker",
                description: "File picker integration coming soon",
              });
            }}
          >
            Browse
          </Button>
        </div>
        
        <div className="text-sm text-gray-500">
          <p>Common applications:</p>
          <div className="flex flex-wrap gap-2 mt-2">
            {[
              'notepad.exe',
              'calc.exe',
              'mspaint.exe',
              'cmd.exe'
            ].map(app => (
              <Button
                key={app}
                size="sm"
                variant="outline"
                onClick={() => setNewAppPath(app)}
                className="text-xs"
              >
                {app}
              </Button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <div className="space-y-6">
      {renderDesktopInfo()}
      {renderResourceUsage()}
      {renderApplications()}
      {renderLaunchApplication()}
    </div>
  );
};