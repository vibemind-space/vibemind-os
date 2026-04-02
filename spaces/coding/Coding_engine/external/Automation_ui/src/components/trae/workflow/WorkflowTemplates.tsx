
import React from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Play, Monitor, Globe, Database, Zap } from 'lucide-react';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  category: 'desktop' | 'api' | 'data' | 'hybrid';
  icon: React.ComponentType<any>;
  nodes: any[];
  edges: any[];
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  estimatedTime: string;
}

const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  {
    id: 'dual-desktop-automation',
    name: 'Dual Desktop Automation',
    description: 'Automation workflow with two separate desktop interfaces for multi-stream configuration',
    category: 'desktop',
    icon: Monitor,
    difficulty: 'intermediate',
    estimatedTime: '8 min',
    nodes: [
      {
        id: 'trigger-1',
        type: 'manual_trigger',
        position: { x: 50, y: 150 },
        data: { label: 'Manual Start', type: 'manual_trigger', config: {} }
      },
      {
        id: 'websocket-config-1',
        type: 'websocket_config',
        position: { x: 50, y: 50 },
        data: { 
          label: 'WebSocket Service', 
          type: 'websocket_config',
          config: { 
            url: `${WEBSOCKET_CONFIG.BASE_URL}${WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP}`,
            reconnect: true,
            filesystem_bridge: true,
            data_directory: './workflow-data'
          }
        }
      },
      {
        id: 'websocket-config-2',
        type: 'websocket_config',
        position: { x: 50, y: 250 },
        data: { 
          label: 'WebSocket Service 2', 
          type: 'websocket_config',
          config: {
            url: `${WEBSOCKET_CONFIG.BASE_URL}${WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP}`, 
            reconnect: true,
            filesystem_bridge: true,
            data_directory: './workflow-data-2'
          }
        }
      },
      {
        id: 'desktop-1',
        type: 'live_desktop',
        position: { x: 300, y: 100 },
        data: { 
          label: 'Live Desktop Interface 1', 
          type: 'live_desktop',
          config: { 
            fps: 30, 
            quality: 80, 
            width: 1920, 
            height: 1080,
            data_output_path: './workflow-data/desktop-1'
          }
        }
      },
      {
        id: 'desktop-2',
        type: 'live_desktop',
        position: { x: 300, y: 200 },
        data: { 
          label: 'Live Desktop Interface 2', 
          type: 'live_desktop',
          config: { 
            fps: 30, 
            quality: 80, 
            width: 1920, 
            height: 1080,
            data_output_path: './workflow-data/desktop-2'
          }
        }
      },
      {
        id: 'click-1',
        type: 'click_action',
        position: { x: 550, y: 80 },
        data: { 
          label: 'Click Action Desktop 1', 
          type: 'click_action',
          config: { x: 100, y: 100, button: 'left' }
        }
      },
      {
        id: 'click-2',
        type: 'click_action',
        position: { x: 550, y: 180 },
        data: { 
          label: 'Click Action Desktop 2', 
          type: 'click_action',
          config: { x: 200, y: 200, button: 'left' }
        }
      },
      {
        id: 'end-1',
        type: 'end',
        position: { x: 750, y: 150 },
        data: { label: 'End', type: 'end', config: {} }
      }
    ],
    edges: [
      { id: 'e1', source: 'trigger-1', target: 'desktop-1' },
      { id: 'e2', source: 'trigger-1', target: 'desktop-2' },
      { id: 'e3', source: 'websocket-config-1', target: 'desktop-1' },
      { id: 'e4', source: 'websocket-config-2', target: 'desktop-2' },
      { id: 'e5', source: 'desktop-1', target: 'click-1' },
      { id: 'e6', source: 'desktop-2', target: 'click-2' },
      { id: 'e7', source: 'click-1', target: 'end-1' },
      { id: 'e8', source: 'click-2', target: 'end-1' }
    ]
  },
  {
    id: 'basic-desktop-automation',
    name: 'Basic Desktop Automation',
    description: 'Simple click and type workflow for desktop automation',
    category: 'desktop',
    icon: Monitor,
    difficulty: 'beginner',
    estimatedTime: '5 min',
    nodes: [
      {
        id: 'trigger-1',
        type: 'manual_trigger',
        position: { x: 100, y: 50 },
        data: { label: 'Manual Start', type: 'manual_trigger', config: {} }
      },
      {
        id: 'websocket-1',
        type: 'websocket_comm',
        position: { x: 100, y: 150 },
        data: { 
          label: 'WebSocket Connection', 
          type: 'websocket_comm',
          config: { url: WEBSOCKET_CONFIG.BASE_URL, protocol: 'ws' }
        }
      },
      {
        id: 'desktop-1',
        type: 'live_desktop',
        position: { x: 300, y: 100 },
        data: { 
          label: 'Live Desktop', 
          type: 'live_desktop',
          config: { width: 1200, height: 900, executionMode: 'direct' }
        }
      },
      {
        id: 'click-1',
        type: 'click_action',
        position: { x: 500, y: 50 },
        data: { 
          label: 'Click Action', 
          type: 'click_action',
          config: { x: 100, y: 100, clickType: 'left' }
        }
      },
      {
        id: 'type-1',
        type: 'type_text_action',
        position: { x: 500, y: 150 },
        data: { 
          label: 'Type Text', 
          type: 'type_text_action',
          config: { text: 'Hello World' }
        }
      },
      {
        id: 'end-1',
        type: 'end',
        position: { x: 700, y: 100 },
        data: { label: 'End', type: 'end', config: {} }
      }
    ],
    edges: [
      { id: 'e1', source: 'trigger-1', target: 'websocket-1' },
      { id: 'e2', source: 'websocket-1', target: 'desktop-1' },
      { id: 'e3', source: 'desktop-1', target: 'click-1' },
      { id: 'e4', source: 'click-1', target: 'type-1' },
      { id: 'e5', source: 'type-1', target: 'end-1' }
    ]
  },
  {
    id: 'conditional-desktop-flow',
    name: 'Conditional Desktop Flow',
    description: 'Desktop automation with conditional logic and delays',
    category: 'desktop',
    icon: Zap,
    difficulty: 'intermediate',
    estimatedTime: '10 min',
    nodes: [
      {
        id: 'trigger-1',
        type: 'manual_trigger',
        position: { x: 50, y: 100 },
        data: { label: 'Manual Start', type: 'manual_trigger', config: {} }
      },
      {
        id: 'websocket-1',
        type: 'websocket_comm',
        position: { x: 200, y: 100 },
        data: { label: 'WebSocket', type: 'websocket_comm', config: {} }
      },
      {
        id: 'desktop-1',
        type: 'live_desktop',
        position: { x: 350, y: 100 },
        data: { label: 'Live Desktop', type: 'live_desktop', config: {} }
      },
      {
        id: 'condition-1',
        type: 'if_condition',
        position: { x: 500, y: 100 },
        data: { label: 'Check Condition', type: 'if_condition', config: {} }
      },
      {
        id: 'click-1',
        type: 'click_action',
        position: { x: 650, y: 50 },
        data: { label: 'Click if True', type: 'click_action', config: {} }
      },
      {
        id: 'delay-1',
        type: 'delay',
        position: { x: 650, y: 150 },
        data: { label: 'Wait 2s', type: 'delay', config: { duration: 2 } }
      },
      {
        id: 'end-1',
        type: 'end',
        position: { x: 800, y: 100 },
        data: { label: 'End', type: 'end', config: {} }
      }
    ],
    edges: [
      { id: 'e1', source: 'trigger-1', target: 'websocket-1' },
      { id: 'e2', source: 'websocket-1', target: 'desktop-1' },
      { id: 'e3', source: 'desktop-1', target: 'condition-1' },
      { id: 'e4', source: 'condition-1', target: 'click-1' },
      { id: 'e5', source: 'condition-1', target: 'delay-1' },
      { id: 'e6', source: 'click-1', target: 'end-1' },
      { id: 'e7', source: 'delay-1', target: 'end-1' }
    ]
  }
];

interface WorkflowTemplatesProps {
  onSelectTemplate: (template: WorkflowTemplate) => void;
  onClose: () => void;
}

export const WorkflowTemplates: React.FC<WorkflowTemplatesProps> = ({
  onSelectTemplate,
  onClose
}) => {
  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'desktop': return 'bg-blue-100 text-blue-800';
      case 'api': return 'bg-green-100 text-green-800';
      case 'data': return 'bg-purple-100 text-purple-800';
      case 'hybrid': return 'bg-orange-100 text-orange-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case 'beginner': return 'bg-green-100 text-green-800';
      case 'intermediate': return 'bg-yellow-100 text-yellow-800';
      case 'advanced': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Workflow Templates</h2>
          <p className="text-muted-foreground">Choose a template to get started quickly</p>
        </div>
        <Button variant="ghost" onClick={onClose}>×</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {WORKFLOW_TEMPLATES.map((template) => {
          const IconComponent = template.icon;
          return (
            <Card key={template.id} className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-primary/10 rounded-lg">
                      <IconComponent className="w-6 h-6 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-lg">{template.name}</CardTitle>
                      <p className="text-sm text-muted-foreground mt-1">
                        {template.description}
                      </p>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex space-x-2">
                    <Badge className={getCategoryColor(template.category)}>
                      {template.category}
                    </Badge>
                    <Badge className={getDifficultyColor(template.difficulty)}>
                      {template.difficulty}
                    </Badge>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {template.estimatedTime}
                  </span>
                </div>

                <div className="flex items-center justify-between text-sm text-muted-foreground mb-4">
                  <span>{template.nodes.length} nodes</span>
                  <span>{template.edges.length} connections</span>
                </div>

                <Button 
                  className="w-full" 
                  onClick={() => onSelectTemplate(template)}
                >
                  <Play className="w-4 h-4 mr-2" />
                  Use Template
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
};

export { WORKFLOW_TEMPLATES };

