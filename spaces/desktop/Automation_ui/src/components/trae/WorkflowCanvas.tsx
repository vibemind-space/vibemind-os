import React, { useCallback, useEffect, useState, useMemo, memo } from 'react';
import {
  ReactFlow,
  Node,
  Edge,
  addEdge,
  Connection,
  useNodesState,
  useEdgesState,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  NodeTypes,
  EdgeTypes,
  ReactFlowProvider,
  useReactFlow,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { toast } from 'sonner';

// Import enhanced components
import { ConnectionValidator } from './workflow/ConnectionValidator';
import { WorkflowTemplates, WorkflowTemplate } from './workflow/WorkflowTemplates';
import { ExecutionEngine } from './workflow/ExecutionEngine';
import { NodeConfigurationModal } from './workflow/NodeConfigurationModal';
import { DynamicNodeManager, nodeTemplates, NodeTemplate } from './DynamicNodeManager';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { 
  Play, 
  Square, 
  Save, 
  Download, 
  Upload, 
  Trash2, 
  Settings,
  Monitor,
  MousePointer,
  Keyboard,
  Timer,
  Globe,
  GitBranch,
  Database,
  Zap,
  AlertTriangle,
  Search,
  Wifi,
  Radio,
  FileText,
  Cog,
  X
} from 'lucide-react';

// Types
interface NodeData extends Record<string, unknown> {
  label: string;
  type: string;
  category?: string;
  status?: 'idle' | 'running' | 'completed' | 'error';
  config?: Record<string, any>;
  inputs?: any[];
  outputs?: any[];
  executionResult?: any;
  metadata?: Record<string, any>;
  description?: string;
  icon?: string;
  color?: string;
  template?: string;
}

interface WorkflowGraph {
  id?: string;
  name: string;
  nodes: any[];
  edges: any[];
}

// Helper functions for node styling (memoized outside component)
const getNodeColor = (type: string): string => {
  switch (type) {
    case 'manual_trigger': return 'bg-gradient-to-br from-emerald-100 to-green-200 border-emerald-400 shadow-emerald-200/50';
    case 'schedule_trigger': return 'bg-gradient-to-br from-blue-100 to-indigo-200 border-blue-400 shadow-blue-200/50';
    case 'websocket_comm': return 'bg-gradient-to-br from-emerald-100 to-teal-200 border-emerald-400 shadow-emerald-200/50';
    case 'click_action': return 'bg-gradient-to-br from-orange-100 to-amber-200 border-orange-400 shadow-orange-200/50';
    case 'type_text_action': return 'bg-gradient-to-br from-purple-100 to-violet-200 border-purple-400 shadow-purple-200/50';
    case 'delay': return 'bg-gradient-to-br from-yellow-100 to-amber-200 border-yellow-400 shadow-yellow-200/50';
    case 'http_request_action': return 'bg-gradient-to-br from-red-100 to-rose-200 border-red-400 shadow-red-200/50';
    case 'if_condition': return 'bg-gradient-to-br from-cyan-100 to-teal-200 border-cyan-400 shadow-cyan-200/50';
    case 'variable_store': return 'bg-gradient-to-br from-pink-100 to-rose-200 border-pink-400 shadow-pink-200/50';
    case 'end': return 'bg-gradient-to-br from-gray-100 to-slate-200 border-gray-400 shadow-gray-200/50';
    default: return 'bg-gradient-to-br from-white to-gray-100 border-gray-300 shadow-gray-200/50';
  }
};

const getNodeIcon = (type: string) => {
  switch (type) {
    case 'manual_trigger': return <Play className="w-5 h-5 text-emerald-600" />;
    case 'schedule_trigger': return <Timer className="w-5 h-5 text-blue-600" />;
    case 'live_desktop': return <Monitor className="w-5 h-5 text-slate-600" />;
    case 'websocket_comm': return <Wifi className="w-5 h-5 text-emerald-600" />;
    case 'click_action': return <MousePointer className="w-5 h-5 text-orange-600" />;
    case 'type_text_action': return <Keyboard className="w-5 h-5 text-purple-600" />;
    case 'delay': return <Timer className="w-5 h-5 text-yellow-600" />;
    case 'http_request_action': return <Globe className="w-5 h-5 text-red-600" />;
    case 'if_condition': return <GitBranch className="w-5 h-5 text-cyan-600" />;
    case 'variable_store': return <Database className="w-5 h-5 text-pink-600" />;
    case 'end': return <Square className="w-5 h-5 text-gray-600" />;
    default: return <Settings className="w-5 h-5 text-gray-600" />;
  }
};

// Custom Node Component - n8n style simplified
const CustomNode: React.FC<{ data: NodeData; id: string }> = memo(({ data, id }) => {
  // Config nodes (like websocket) - no handles, just visual
  if (data.type === 'websocket_config') {
    return (
      <div className="relative bg-gradient-to-br from-purple-100 to-violet-200 border-2 border-purple-400 shadow-lg shadow-purple-200/50 rounded-lg px-4 py-3 min-w-[200px] hover:shadow-xl transition-all duration-300 cursor-pointer">
        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0 p-2 bg-white/60 rounded-lg">
            <Wifi className="w-6 h-6 text-purple-600" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-bold text-purple-800">{data.label}</div>
            <div className="text-xs text-purple-600">Configuration</div>
          </div>
        </div>
      </div>
    );
  }

  // Live Desktop node - needs websocket config input + regular flow
  if (data.type === 'live_desktop') {
    return (
      <div className="relative bg-gradient-to-br from-slate-100 to-gray-200 border-2 border-slate-400 shadow-lg shadow-slate-200/50 rounded-lg px-4 py-3 min-w-[200px] hover:shadow-xl transition-all duration-300 cursor-pointer">
        {/* Input from previous node */}
        <Handle
          type="target"
          position={Position.Left}
          className="w-3 h-3 bg-gray-400 border-2 border-white shadow-md"
        />
        
        {/* Config connection (websocket) */}
        <Handle
          type="target"
          position={Position.Top}
          id="config"
          className="w-3 h-3 bg-purple-400 border-2 border-white shadow-md"
          style={{ left: '75%' }}
        />

        <div className="flex items-center space-x-3">
          <div className="flex-shrink-0 p-2 bg-white/60 rounded-lg">
            <Monitor className="w-6 h-6 text-slate-600" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-bold text-slate-800">{data.label}</div>
            <div className="text-xs text-slate-600">Live Desktop</div>
          </div>
        </div>

        {/* Output to next node */}
        <Handle
          type="source"
          position={Position.Right}
          className="w-3 h-3 bg-gray-400 border-2 border-white shadow-md"
        />
      </div>
    );
  }


  const hasConfig = data.config && Object.keys(data.config).length > 0;
  const isConfigured = hasConfig && Object.values(data.config).some(v => v !== undefined && v !== '');

  // Regular nodes - simplified n8n style with 1 input, 1 output
  return (
    <div className={`
      px-4 py-3 rounded-lg border-2 min-w-[180px] relative transition-all duration-300 hover:shadow-lg backdrop-blur-sm cursor-pointer
      ${getNodeColor(data.type)}
    `}>
      {/* Input Handle - only for non-trigger nodes */}
      {data.type !== 'manual_trigger' && data.type !== 'schedule_trigger' && (
        <Handle
          type="target"
          position={Position.Left}
          className="w-3 h-3 bg-gray-400 border-2 border-white shadow-md"
        />
      )}

      <div className="flex items-center space-x-3">
        <div className="flex-shrink-0 p-2 bg-white/60 rounded-lg">
          {getNodeIcon(data.type)}
        </div>
        <div className="flex-1">
          <div className="text-sm font-bold text-gray-800">{data.label}</div>
          <div className="text-xs text-gray-600 capitalize">{data.type.replace('_', ' ')}</div>
          {!isConfigured && hasConfig && (
            <div className="flex items-center mt-1">
              <AlertTriangle className="w-3 h-3 text-amber-500 mr-1" />
              <span className="text-xs text-amber-600">Not configured</span>
            </div>
          )}
        </div>
      </div>

      {data.status && (
        <div className="mt-2">
          <Badge 
            variant={data.status === 'completed' ? 'default' : data.status === 'error' ? 'destructive' : 'secondary'}
            className="text-xs px-2 py-1 font-medium"
          >
            {data.status}
          </Badge>
        </div>
      )}

      {/* Output Handle - only for non-end nodes */}
      {data.type !== 'end' && (
        <Handle
          type="source"
          position={Position.Right}
          className="w-3 h-3 bg-gray-400 border-2 border-white shadow-md"
        />
      )}
    </div>
  );
});

CustomNode.displayName = 'CustomNode';

// Define custom node types (constant - already optimized via React.memo on CustomNode)
const nodeTypes: NodeTypes = {
  custom: CustomNode,
  manual_trigger: CustomNode,
  schedule_trigger: CustomNode,
  live_desktop: CustomNode,
  websocket_comm: CustomNode,
  websocket_config: CustomNode,
  click_action: CustomNode,
  type_text_action: CustomNode,
  delay: CustomNode,
  http_request_action: CustomNode,
  if_condition: CustomNode,
  variable_store: CustomNode,
  end: CustomNode,
};

interface WorkflowCanvasProps {
  workflowId?: string;
  readOnly?: boolean;
  onWorkflowChange?: (workflow: WorkflowGraph) => void;
  onExecutionStart?: (executionId: string) => void;
}

const WorkflowCanvasInner: React.FC<WorkflowCanvasProps> = memo(({
  workflowId,
  readOnly = false,
  onWorkflowChange,
  onExecutionStart,
}) => {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NodeData>>([
    {
      id: '1',
      type: 'manual_trigger',
      position: { x: 250, y: 50 },
      data: { 
        label: 'Manual Trigger', 
        type: 'manual_trigger',
        config: {}
      },
    }
  ]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<Node<NodeData> | null>(null);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [isTemplatesOpen, setIsTemplatesOpen] = useState(false);
  const [isExecutionPanelOpen, setIsExecutionPanelOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [workflowName, setWorkflowName] = useState('Untitled Workflow');
  const [isDirty, setIsDirty] = useState(false);

  const reactFlowInstance = useReactFlow();

  // Enhanced connection validation
  const onConnect = useCallback(
    (params: Connection) => {
      if (readOnly) return;
      
      const validation = ConnectionValidator.validateConnection(params, nodes);
      
      if (!validation.valid) {
        toast.error(`Connection failed: ${validation.error}`);
        return;
      }
      
      if (validation.warning) {
        toast.warning(validation.warning);
      }
      
      const newEdge = {
        ...params,
        id: `edge-${params.source}-${params.target}-${Date.now()}`,
        type: 'default',
        style: { stroke: '#000000', strokeWidth: 2 }
      };
      
      setEdges((eds) => addEdge(newEdge, eds));
      setIsDirty(true);
      toast.success('Connection created successfully!');
    },
    [readOnly, nodes, setEdges]
  );

  // Handle node selection - n8n style inline configuration
  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    setSelectedNode(node as Node<NodeData>);
    setIsConfigModalOpen(true);
  }, []);

  // Handle node data updates
  const onNodeDataChange = useCallback((nodeId: string, newData: Partial<NodeData>) => {
    if (readOnly) return;
    
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === nodeId) {
          return {
            ...node,
            data: {
              ...node.data,
              ...newData,
            },
          };
        }
        return node;
      })
    );
    setIsDirty(true);
  }, [readOnly, setNodes]);

  // Template selection handler
  const handleSelectTemplate = useCallback((template: WorkflowTemplate) => {
    if (readOnly) return;
    
    // Clear existing workflow
    setNodes([]);
    setEdges([]);
    
    // Load template
    setNodes(template.nodes.map(node => ({
      ...node,
      data: {
        ...node.data,
        status: 'idle' as const,
      },
    })));
    setEdges(template.edges);
    
    setWorkflowName(template.name);
    setIsTemplatesOpen(false);
    setIsDirty(true);
    
    toast.success(`Template "${template.name}" loaded successfully!`);
  }, [readOnly, setNodes, setEdges]);

  // Add new node from template
  const onAddNodeFromTemplate = useCallback((template: NodeTemplate, position?: { x: number; y: number }) => {
    if (readOnly) return;
    
    const finalPosition = position || reactFlowInstance.screenToFlowPosition({
      x: Math.random() * 400 + 100,
      y: Math.random() * 400 + 100,
    });

    const newNode: Node<NodeData> = {
      id: `node-${Date.now()}`,
      type: template.type,
      position: finalPosition,
      data: {
        label: template.label,
        type: template.type,
        category: template.category,
        status: 'idle',
        config: { ...template.defaultConfig },
        inputs: template.inputs,
        outputs: template.outputs,
        description: template.description,
        icon: template.icon.name,
        color: template.color,
        template: template.id,
      },
    };

    setNodes((nds) => [...nds, newNode]);
    setSelectedNode(newNode);
    setIsConfigModalOpen(true);
    setIsDirty(true);
    setIsLibraryOpen(false);
    toast.success(`Added ${template.label} node!`);
  }, [readOnly, reactFlowInstance, setNodes]);

  // Delete node handler
  const onDeleteNode = useCallback((nodeId: string) => {
    if (readOnly) return;
    
    setNodes((nds) => nds.filter(n => n.id !== nodeId));
    setEdges((eds) => eds.filter(e => e.source !== nodeId && e.target !== nodeId));
    
    if (selectedNode?.id === nodeId) {
      setSelectedNode(null);
      setIsConfigModalOpen(false);
    }
    
    setIsDirty(true);
    toast.success('Node deleted!');
  }, [readOnly, setNodes, setEdges, selectedNode]);

  // Validate workflow (memoized)
  const validation = useMemo(() => {
    return ConnectionValidator.validateWorkflow(nodes, edges);
  }, [nodes, edges]);

  return (
    <div className="h-full flex bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Main Canvas */}
      <div className="flex-1 relative overflow-hidden">
        {/* Enhanced Toolbar */}
        <div className="absolute top-6 left-6 z-20 flex space-x-3">
          <div className="bg-white/90 backdrop-blur-sm rounded-xl shadow-lg border border-white/20 p-2 flex space-x-2">
            <Button 
              onClick={() => setIsTemplatesOpen(true)} 
              variant="ghost" 
              size="sm"
              className="bg-gradient-to-r from-purple-500 to-pink-600 text-white hover:from-purple-600 hover:to-pink-700 transition-all duration-300 shadow-md"
            >
              <FileText className="w-4 h-4 mr-2" />
              Templates
            </Button>
            <Button 
              onClick={() => setIsLibraryOpen(true)} 
              variant="ghost" 
              size="sm"
              className="bg-gradient-to-r from-blue-500 to-purple-600 text-white hover:from-blue-600 hover:to-purple-700 transition-all duration-300 shadow-md"
            >
              <Zap className="w-4 h-4 mr-2" />
              Add Node
            </Button>
            <Button 
              onClick={() => setIsExecutionPanelOpen(true)} 
              variant="ghost" 
              size="sm" 
              disabled={!validation.valid}
              className="bg-gradient-to-r from-green-500 to-emerald-600 text-white hover:from-green-600 hover:to-emerald-700 disabled:from-gray-400 disabled:to-gray-500 transition-all duration-300 shadow-md"
            >
              <Cog className="w-4 h-4 mr-2" />
              Execute
            </Button>
            <Button 
              variant="ghost" 
              size="sm"
              className="bg-gradient-to-r from-amber-500 to-orange-600 text-white hover:from-amber-600 hover:to-orange-700 transition-all duration-300 shadow-md"
            >
              <Save className="w-4 h-4 mr-2" />
              Save
            </Button>
          </div>
        </div>

        {/* Enhanced Validation Status */}
        {!validation.valid && (
          <div className="absolute top-6 right-6 z-20">
            <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-4 shadow-lg backdrop-blur-sm max-w-sm">
              <div className="flex items-start space-x-3">
                <div className="bg-gradient-to-r from-amber-400 to-orange-500 p-2 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-white" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-amber-800 mb-2">Workflow Issues</p>
                  <p className="text-xs text-amber-700">{validation.error}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Enhanced React Flow */}
        <div className="h-full relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            fitView
            className="rounded-lg"
            style={{
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            }}
          >
            <Controls 
              className="bg-white/90 backdrop-blur-sm rounded-xl shadow-lg border border-white/20"
            />
            <MiniMap 
              className="bg-white/90 backdrop-blur-sm rounded-xl shadow-lg border border-white/20 overflow-hidden"
              nodeColor={useCallback((node: Node<NodeData>) => {
                switch (node.data?.status) {
                  case 'running': return '#3b82f6';
                  case 'completed': return '#10b981';
                  case 'error': return '#ef4444';
                  default: return '#6b7280';
                }
              }, [])}
            />
            <Background 
              variant={BackgroundVariant.Dots} 
              gap={20} 
              size={1.5} 
              color="rgba(255,255,255,0.3)"
            />
          </ReactFlow>
        </div>
      </div>

      {/* Enhanced Configuration Panel */}
      <div className="w-96 bg-white/95 backdrop-blur-xl border-l border-white/20 shadow-2xl">
        <div className="h-full flex flex-col">
          {/* Panel Header */}
          <div className="bg-gradient-to-r from-slate-100 to-blue-50 p-6 border-b border-slate-200">
            <h2 className="text-xl font-bold bg-gradient-to-r from-slate-700 to-blue-600 bg-clip-text text-transparent">
              Node Configuration
            </h2>
            <p className="text-sm text-slate-600 mt-1">
              {selectedNode ? `Configure ${selectedNode.data.label}` : 'Select a node to configure'}
            </p>
          </div>
          
          {/* Panel Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {selectedNode ? (
              <div className="bg-gradient-to-br from-white to-slate-50 rounded-xl p-6 shadow-sm border border-slate-100">
                {/* Configuration form can be implemented here or imported */}
                <p className="text-sm text-muted-foreground">Configuration UI goes here.</p>
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="bg-gradient-to-br from-slate-100 to-blue-100 w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Settings className="w-12 h-12 text-slate-400" />
                </div>
                <p className="text-slate-500 text-sm">
                  Click on a node to configure its properties
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Workflow Templates Modal */}
      {isTemplatesOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 p-6 max-w-4xl w-full m-4 max-h-[80vh] overflow-hidden animate-scale-in">
            <WorkflowTemplates
              onSelectTemplate={handleSelectTemplate}
              onClose={() => setIsTemplatesOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Dynamic Node Library Modal */}
      {isLibraryOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 p-6 max-w-4xl w-full m-4 max-h-[80vh] overflow-hidden animate-scale-in">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h3 className="text-2xl font-bold bg-gradient-to-r from-slate-700 to-blue-600 bg-clip-text text-transparent">
                  Dynamic Node Library
                </h3>
                <p className="text-sm text-slate-600 mt-1">
                  Choose from our collection of dynamic workflow nodes
                </p>
              </div>
              <Button 
                variant="ghost" 
                onClick={() => setIsLibraryOpen(false)}
                className="hover-scale rounded-full"
              >
                ×
              </Button>
            </div>
            
            <div className="h-full overflow-y-auto">
              <DynamicNodeManager
                onAddNode={onAddNodeFromTemplate}
                onUpdateNode={onNodeDataChange}
                onDeleteNode={onDeleteNode}
                selectedNode={selectedNode}
                nodes={nodes}
              />
            </div>
          </div>
        </div>
      )}

      {/* Execution Engine Modal */}
      {isExecutionPanelOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/20 p-6 max-w-2xl w-full m-4 max-h-[80vh] overflow-hidden animate-scale-in">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-2xl font-bold bg-gradient-to-r from-slate-700 to-blue-600 bg-clip-text text-transparent">
                Workflow Execution
              </h3>
              <Button 
                variant="ghost" 
                onClick={() => setIsExecutionPanelOpen(false)}
                className="hover-scale rounded-full"
              >
                ×
              </Button>
            </div>
            
            <ExecutionEngine
              nodes={nodes}
              edges={edges}
              onNodeUpdate={onNodeDataChange}
              onExecutionComplete={(results) => {
                console.log('Execution completed:', results);
                toast.success(`Workflow completed with ${results.filter(r => r.success).length}/${results.length} successful steps`);
              }}
            />
          </div>
        </div>
      )}

      {/* Node Configuration Modal - n8n style */}
      <NodeConfigurationModal
        node={selectedNode}
        isOpen={isConfigModalOpen}
        onClose={() => {
          setIsConfigModalOpen(false);
          setSelectedNode(null);
        }}
        onSave={(node) => onNodeDataChange(node.id, node.data)}
        onDelete={onDeleteNode}
      />
    </div>
  );
});

WorkflowCanvasInner.displayName = 'WorkflowCanvasInner';

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = memo((props) => {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner {...props} />
    </ReactFlowProvider>
  );
});

WorkflowCanvas.displayName = 'WorkflowCanvas';

export default WorkflowCanvas;
