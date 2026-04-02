/**
 * Virtual Desktop Card Component
 * Displays individual virtual desktop information in a card format
 * Author: TRAE Development Team
 * Version: 1.0.0
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  Monitor, 
  Play, 
  Pause, 
  Square, 
  Settings, 
  Trash2,
  Activity,
  Cpu,
  MemoryStick,
  Network,
  Eye,
  Bot,
  Zap
} from 'lucide-react';
import { VirtualDesktop } from '@/types/virtualDesktop';

interface VirtualDesktopCardProps {
  /** Virtual desktop data */
  desktop: VirtualDesktop;
  /** Called when desktop is selected */
  onSelect: () => void;
  /** Called when desktop should be deleted */
  onDelete: () => void;
  /** Called when streaming should start */
  onStartStream: () => void;
  /** Called when streaming should stop */
  onStopStream: () => void;
  /** Whether this desktop is currently selected */
  isSelected?: boolean;
  /** Whether to show detailed information */
  showDetails?: boolean;
}

export const VirtualDesktopCard: React.FC<VirtualDesktopCardProps> = ({
  desktop,
  onSelect,
  onDelete,
  onStartStream,
  onStopStream,
  isSelected = false,
  showDetails = true
}) => {
  // ============================================================================
  // HELPER FUNCTIONS
  // ============================================================================

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'streaming': return 'bg-blue-500';
      case 'paused': return 'bg-yellow-500';
      case 'stopped': return 'bg-gray-500';
      case 'error': return 'bg-red-500';
      case 'creating': return 'bg-orange-500';
      default: return 'bg-gray-500';
    }
  };

  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'active': return 'default';
      case 'streaming': return 'default';
      case 'paused': return 'secondary';
      case 'stopped': return 'secondary';
      case 'error': return 'destructive';
      case 'creating': return 'secondary';
      default: return 'secondary';
    }
  };

  const formatUptime = (createdAt: Date) => {
    const now = new Date();
    const diff = now.getTime() - createdAt.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const formatMemory = (memoryMB: number) => {
    if (memoryMB >= 1024) {
      return `${(memoryMB / 1024).toFixed(1)}GB`;
    }
    return `${memoryMB}MB`;
  };

  const formatBandwidth = (kbps: number) => {
    if (kbps >= 1000) {
      return `${(kbps / 1000).toFixed(1)}Mbps`;
    }
    return `${kbps}kbps`;
  };

  // ============================================================================
  // RENDER HELPERS
  // ============================================================================

  const renderHeader = () => (
    <CardHeader className="pb-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <Monitor className="h-8 w-8 text-blue-500" />
            <div 
              className={`absolute -top-1 -right-1 w-3 h-3 rounded-full ${getStatusColor(desktop.status)}`}
            />
          </div>
          <div>
            <CardTitle className="text-lg">{desktop.name}</CardTitle>
            <p className="text-sm text-gray-500">
              {desktop.resolution?.width || 1920}x{desktop.resolution?.height || 1080}
            </p>
          </div>
        </div>
        <Badge variant={getStatusVariant(desktop.status)}>
          {desktop.status}
        </Badge>
      </div>
    </CardHeader>
  );

  const renderApplications = () => (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Applications</span>
        <span className="text-sm text-gray-500">{desktop.applications.length}</span>
      </div>
      
      {desktop.applications.length > 0 ? (
        <div className="space-y-1">
          {desktop.applications.slice(0, 3).map(app => (
            <div key={app.id} className="flex items-center justify-between text-sm">
              <span className="truncate">{app.name}</span>
              <Badge 
                variant={app.status === 'running' ? 'default' : 'secondary'}
                className="text-xs"
              >
                {app.status}
              </Badge>
            </div>
          ))}
          {desktop.applications.length > 3 && (
            <p className="text-xs text-gray-500">
              +{desktop.applications.length - 3} more
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No applications running</p>
      )}
    </div>
  );

  const renderResourceUsage = () => (
    <div className="grid grid-cols-2 gap-4">
      <div className="space-y-2">
        <div className="flex items-center space-x-2">
          <Cpu className="h-4 w-4 text-orange-500" />
          <span className="text-sm">CPU</span>
        </div>
        <div className="text-lg font-semibold">
          {desktop.resourceUsage.cpuUsage.toFixed(1)}%
        </div>
      </div>
      
      <div className="space-y-2">
        <div className="flex items-center space-x-2">
          <MemoryStick className="h-4 w-4 text-purple-500" />
          <span className="text-sm">Memory</span>
        </div>
        <div className="text-lg font-semibold">
          {formatMemory(desktop.resourceUsage.memoryUsage)}
        </div>
      </div>
      
      <div className="space-y-2">
        <div className="flex items-center space-x-2">
          <Network className="h-4 w-4 text-red-500" />
          <span className="text-sm">Network</span>
        </div>
        <div className="text-lg font-semibold">
          {formatBandwidth(desktop.resourceUsage.networkUsage)}
        </div>
      </div>
      
      <div className="space-y-2">
        <div className="flex items-center space-x-2">
          <Activity className="h-4 w-4 text-green-500" />
          <span className="text-sm">Uptime</span>
        </div>
        <div className="text-lg font-semibold">
          {formatUptime(desktop.createdAt)}
        </div>
      </div>
    </div>
  );

  const renderFeatures = () => (
    <div className="flex flex-wrap gap-2">
      {desktop.streamConfig.quality > 0 && (
        <div className="flex items-center space-x-1 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
          <Eye className="h-3 w-3" />
          <span>Streaming</span>
        </div>
      )}
      
      {desktop.automationConfig.ocrEnabled && (
        <div className="flex items-center space-x-1 text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
          <Bot className="h-3 w-3" />
          <span>OCR</span>
        </div>
      )}
      
      {desktop.automationConfig.eventAutomationEnabled && (
        <div className="flex items-center space-x-1 text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded">
          <Zap className="h-3 w-3" />
          <span>Automation</span>
        </div>
      )}
      
      {desktop.streamConfig.audioEnabled && (
        <div className="flex items-center space-x-1 text-xs bg-orange-100 text-orange-800 px-2 py-1 rounded">
          <span>🔊</span>
          <span>Audio</span>
        </div>
      )}
    </div>
  );

  const renderActions = () => (
    <div className="flex space-x-2">
      {/* Stream Control */}
      {desktop.status === 'streaming' ? (
        <Button
          size="sm"
          variant="outline"
          onClick={(e) => {
            e.stopPropagation();
            onStopStream();
          }}
          className="flex-1"
        >
          <Square className="h-4 w-4 mr-1" />
          Stop
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={(e) => {
            e.stopPropagation();
            onStartStream();
          }}
          className="flex-1"
          disabled={desktop.status === 'creating' || desktop.status === 'error'}
        >
          <Play className="h-4 w-4 mr-1" />
          Stream
        </Button>
      )}

      {/* Settings */}
      <Button
        size="sm"
        variant="outline"
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
      >
        <Settings className="h-4 w-4" />
      </Button>

      {/* Delete */}
      <Button
        size="sm"
        variant="outline"
        onClick={(e) => {
          e.stopPropagation();
          if (confirm(`Are you sure you want to delete "${desktop.name}"?`)) {
            onDelete();
          }
        }}
        className="text-red-600 hover:text-red-700"
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <Card 
      className={`cursor-pointer transition-all duration-200 hover:shadow-lg ${
        isSelected ? 'ring-2 ring-blue-500 shadow-lg' : ''
      }`}
      onClick={onSelect}
    >
      {renderHeader()}
      
      <CardContent className="space-y-4">
        {showDetails && (
          <>
            {/* Applications */}
            {renderApplications()}
            
            {/* Resource Usage */}
            <div className="border-t pt-4">
              <h4 className="text-sm font-medium mb-3">Resource Usage</h4>
              {renderResourceUsage()}
            </div>
            
            {/* Features */}
            <div className="border-t pt-4">
              <h4 className="text-sm font-medium mb-3">Features</h4>
              {renderFeatures()}
            </div>
          </>
        )}
        
        {/* Actions */}
        <div className="border-t pt-4">
          {renderActions()}
        </div>
      </CardContent>
    </Card>
  );
};