import React, { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Node } from '@xyflow/react';
import { 
  Plus, 
  Trash2, 
  Copy, 
  Settings, 
  Play, 
  Clock, 
  Monitor, 
  MousePointer, 
  Keyboard,
  Wifi,
  Globe,
  Database,
  GitBranch,
  Timer,
  Square
} from 'lucide-react';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';

interface NodeTemplate {
  id: string;
  type: string;
  label: string;
  category: string;
  icon: React.ComponentType<any>;
  color: string;
  description: string;
  defaultConfig: Record<string, any>;
  configSchema: Array<{
    key: string;
    label: string;
    type: 'text' | 'number' | 'select' | 'textarea' | 'checkbox';
    options?: string[];
    defaultValue?: any;
    required?: boolean;
  }>;
  inputs: Array<{
    id: string;
    label: string;
    type: string;
    position: 'top' | 'left' | 'right' | 'bottom';
    style?: string;
  }>;
  outputs: Array<{
    id: string;
    label: string;
    type: string;
    position: 'top' | 'left' | 'right' | 'bottom';
    style?: string;
  }>;
}

interface NodeData extends Record<string, unknown> {
  label: string;
  type: string;
  category?: string;
  status?: string;
  config?: Record<string, any>;
  inputs?: any[];
  outputs?: any[];
}

// Dynamic Node Templates
const nodeTemplates: NodeTemplate[] = [
  {
    id: 'manual_trigger',
    type: 'manual_trigger',
    label: 'Manual Trigger',
    category: 'triggers',
    icon: Play,
    color: 'from-green-400 to-emerald-600',
    description: 'Manually triggered workflow execution',
    defaultConfig: { triggerName: 'Manual Start' },
    configSchema: [
      { key: 'triggerName', label: 'Trigger Name', type: 'text', defaultValue: 'Manual Start', required: true }
    ],
    inputs: [],
    outputs: [
      { id: 'trigger', label: 'Trigger', type: 'trigger', position: 'bottom', style: 'bg-green-500' }
    ]
  },
  {
    id: 'live_desktop',
    type: 'live_desktop',
    label: 'Live Desktop',
    category: 'desktop',
    icon: Monitor,
    color: 'from-slate-400 to-gray-600',
    description: 'Live desktop streaming and interaction',
    defaultConfig: { width: 1200, height: 900, pcTarget: 'Windows PC', executionMode: 'direct' },
    configSchema: [
      { key: 'width', label: 'Width', type: 'number', defaultValue: 1200, required: true },
      { key: 'height', label: 'Height', type: 'number', defaultValue: 900, required: true },
      { key: 'pcTarget', label: 'Target PC', type: 'text', defaultValue: 'Windows PC', required: true },
      { 
        key: 'executionMode', 
        label: 'Execution Mode', 
        type: 'select', 
        options: ['direct', 'preview', 'simulation'], 
        defaultValue: 'direct',
        required: true 
      }
    ],
    inputs: [
      { id: 'control', label: 'Control', type: 'control', position: 'top', style: 'bg-blue-500' },
      { id: 'websocket', label: 'WebSocket', type: 'websocket', position: 'left', style: 'bg-purple-500' },
      { id: 'coordinates', label: 'Coordinates', type: 'coordinates', position: 'left', style: 'bg-orange-500' }
    ],
    outputs: [
      { id: 'events', label: 'Events', type: 'events', position: 'right', style: 'bg-green-500' },
      { id: 'stream', label: 'Stream', type: 'stream', position: 'right', style: 'bg-indigo-500' },
      { id: 'flow', label: 'Flow', type: 'flow', position: 'bottom', style: 'bg-slate-500' }
    ]
  },
  {
    id: 'websocket_comm',
    type: 'websocket_comm',
    label: 'WebSocket Communication',
    category: 'communication',
    icon: Wifi,
    color: 'from-purple-400 to-violet-600',
    description: 'WebSocket connection for real-time communication',
    defaultConfig: { url: WEBSOCKET_CONFIG.BASE_URL, protocol: 'ws', autoReconnect: true },
    configSchema: [
      { key: 'url', label: 'WebSocket URL', type: 'text', defaultValue: WEBSOCKET_CONFIG.BASE_URL, required: true },
      { key: 'protocol', label: 'Protocol', type: 'select', options: ['ws', 'wss'], defaultValue: 'ws', required: true },
      { key: 'autoReconnect', label: 'Auto Reconnect', type: 'checkbox', defaultValue: true }
    ],
    inputs: [
      { id: 'trigger', label: 'Connect', type: 'trigger', position: 'top', style: 'bg-blue-500' }
    ],
    outputs: [
      { id: 'connection', label: 'Connection', type: 'websocket', position: 'bottom', style: 'bg-purple-500' },
      { id: 'messages', label: 'Messages', type: 'data', position: 'right', style: 'bg-green-500' }
    ]
  },
  {
    id: 'click_action',
    type: 'click_action',
    label: 'Click Action',
    category: 'actions',
    icon: MousePointer,
    color: 'from-orange-400 to-amber-600',
    description: 'Perform click actions on the desktop',
    defaultConfig: { x: 0, y: 0, clickType: 'left', delay: 100 },
    configSchema: [
      { key: 'x', label: 'X Position', type: 'number', defaultValue: 0, required: true },
      { key: 'y', label: 'Y Position', type: 'number', defaultValue: 0, required: true },
      { key: 'clickType', label: 'Click Type', type: 'select', options: ['left', 'right', 'double'], defaultValue: 'left' },
      { key: 'delay', label: 'Delay (ms)', type: 'number', defaultValue: 100 }
    ],
    inputs: [
      { id: 'trigger', label: 'Execute', type: 'trigger', position: 'top', style: 'bg-blue-500' },
      { id: 'coordinates', label: 'Coordinates', type: 'coordinates', position: 'left', style: 'bg-orange-500' }
    ],
    outputs: [
      { id: 'result', label: 'Result', type: 'data', position: 'bottom', style: 'bg-green-500' }
    ]
  }
];

interface DynamicNodeManagerProps {
  onAddNode: (template: NodeTemplate, position?: { x: number; y: number }) => void;
  onUpdateNode: (nodeId: string, updates: Partial<NodeData>) => void;
  onDeleteNode: (nodeId: string) => void;
  selectedNode?: Node<NodeData> | null;
  nodes: Node<NodeData>[];
}

export const DynamicNodeManager: React.FC<DynamicNodeManagerProps> = ({
  onAddNode,
  onUpdateNode,
  onDeleteNode,
  selectedNode,
  nodes
}) => {
  const [showTemplateCreator, setShowTemplateCreator] = useState(false);
  const [activeCategory, setActiveCategory] = useState<string>('all');

  const categories = Array.from(new Set(nodeTemplates.map(t => t.category)));

  const filteredTemplates = activeCategory === 'all' 
    ? nodeTemplates 
    : nodeTemplates.filter(t => t.category === activeCategory);

  const handleAddNode = useCallback((template: NodeTemplate) => {
    const position = {
      x: Math.random() * 300 + 100,
      y: Math.random() * 300 + 100
    };
    onAddNode(template, position);
  }, [onAddNode]);

  const handleCloneNode = useCallback((nodeId: string) => {
    const nodeToClone = nodes.find(n => n.id === nodeId);
    if (!nodeToClone) return;

    const template = nodeTemplates.find(t => t.type === nodeToClone.data.type);
    if (!template) return;

    const position = {
      x: nodeToClone.position.x + 50,
      y: nodeToClone.position.y + 50
    };

    onAddNode(template, position);
  }, [nodes, onAddNode]);

  return (
    <div className="space-y-6">
      {/* Category Filter */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={activeCategory === 'all' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveCategory('all')}
          className="animate-fade-in"
        >
          All
        </Button>
        {categories.map(category => (
          <Button
            key={category}
            variant={activeCategory === category ? 'default' : 'outline'}
            size="sm"
            onClick={() => setActiveCategory(category)}
            className="animate-fade-in capitalize"
          >
            {category}
          </Button>
        ))}
      </div>

      {/* Node Templates Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredTemplates.map((template) => {
          const IconComponent = template.icon;
          return (
            <Card 
              key={template.id} 
              className="hover-scale cursor-pointer animate-scale-in group hover:shadow-lg transition-all duration-300"
              onClick={() => handleAddNode(template)}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center space-x-3">
                  <div className={`p-2 rounded-lg bg-gradient-to-br ${template.color}`}>
                    <IconComponent className="w-5 h-5 text-white" />
                  </div>
                  <div className="flex-1">
                    <CardTitle className="text-sm">{template.label}</CardTitle>
                    <Badge variant="secondary" className="text-xs">
                      {template.category}
                    </Badge>
                  </div>
                  <Plus className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="text-xs text-muted-foreground mb-3">
                  {template.description}
                </p>
                <div className="flex justify-between items-center text-xs text-muted-foreground">
                  <span>{template.inputs.length} inputs</span>
                  <span>{template.outputs.length} outputs</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Quick Actions for Selected Node */}
      {selectedNode && (
        <Card className="animate-fade-in">
          <CardHeader>
            <CardTitle className="text-lg flex items-center space-x-2">
              <Settings className="w-5 h-5" />
              <span>Selected: {selectedNode.data.label}</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCloneNode(selectedNode.id)}
                className="hover-scale"
              >
                <Copy className="w-4 h-4 mr-2" />
                Clone
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onDeleteNode(selectedNode.id)}
                className="hover-scale text-destructive hover:text-destructive"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Node Statistics */}
      <Card className="animate-fade-in">
        <CardHeader>
          <CardTitle className="text-sm">Workflow Statistics</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="font-medium">Total Nodes</div>
              <div className="text-2xl font-bold text-primary">{nodes.length}</div>
            </div>
            <div>
              <div className="font-medium">Node Types</div>
              <div className="text-2xl font-bold text-primary">
                {new Set(nodes.map(n => n.data.type)).size}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export { nodeTemplates };
export type { NodeTemplate };