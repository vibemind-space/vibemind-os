import React, { useState } from 'react';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  ChevronDown, 
  ChevronRight, 
  Play, 
  CheckCircle, 
  XCircle, 
  Clock, 
  AlertCircle 
} from 'lucide-react';
import { WorkflowExecution, NodeExecution } from '@/types/execution';
import { ExecutionEngine } from '@/components/trae/workflow/ExecutionEngine';
import { Node, Edge } from '@xyflow/react';

// Mock data for demonstration
const mockExecutions: WorkflowExecution[] = [
  {
    id: 'exec-1',
    workflow_id: 'wf-1',
    workflow_name: 'Data Processing Workflow',
    status: 'running',
    trigger_type: 'manual',
    start_time: new Date().toISOString(),
    total_nodes: 5,
    completed_nodes: 3,
    failed_nodes: 0,
    node_executions: [
      {
        node_id: 'node-1',
        node_name: 'Trigger',
        node_type: 'webhook',
        status: 'success',
        start_time: new Date(Date.now() - 5000).toISOString(),
        end_time: new Date(Date.now() - 4500).toISOString(),
        duration_ms: 500,
      },
      {
        node_id: 'node-2',
        node_name: 'Data Transform',
        node_type: 'transform',
        status: 'success',
        start_time: new Date(Date.now() - 4000).toISOString(),
        end_time: new Date(Date.now() - 3200).toISOString(),
        duration_ms: 800,
      },
      {
        node_id: 'node-3',
        node_name: 'API Call',
        node_type: 'http',
        status: 'running',
        start_time: new Date(Date.now() - 3000).toISOString(),
      }
    ]
  },
  {
    id: 'exec-2',
    workflow_id: 'wf-1',
    workflow_name: 'Data Processing Workflow',
    status: 'success',
    trigger_type: 'webhook',
    start_time: new Date(Date.now() - 300000).toISOString(),
    end_time: new Date(Date.now() - 285000).toISOString(),
    duration_ms: 15000,
    total_nodes: 5,
    completed_nodes: 5,
    failed_nodes: 0,
    node_executions: []
  },
  {
    id: 'exec-3',
    workflow_id: 'wf-1',
    workflow_name: 'Data Processing Workflow',
    status: 'failed',
    trigger_type: 'schedule',
    start_time: new Date(Date.now() - 600000).toISOString(),
    end_time: new Date(Date.now() - 590000).toISOString(),
    duration_ms: 10000,
    total_nodes: 5,
    completed_nodes: 2,
    failed_nodes: 1,
    error_message: 'HTTP request timeout',
    node_executions: []
  }
];

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'success':
        return { 
          variant: 'default' as const, 
          icon: CheckCircle, 
          className: 'bg-green-500/10 text-green-600 border-green-500/20' 
        };
      case 'failed':
        return { 
          variant: 'destructive' as const, 
          icon: XCircle, 
          className: 'bg-red-500/10 text-red-600 border-red-500/20' 
        };
      case 'running':
        return { 
          variant: 'secondary' as const, 
          icon: Play, 
          className: 'bg-blue-500/10 text-blue-600 border-blue-500/20' 
        };
      case 'pending':
        return { 
          variant: 'outline' as const, 
          icon: Clock, 
          className: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20' 
        };
      default:
        return { 
          variant: 'outline' as const, 
          icon: AlertCircle, 
          className: '' 
        };
    }
  };

  const config = getStatusConfig(status);
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className={`${config.className} gap-1`}>
      <Icon className="h-3 w-3" />
      {status}
    </Badge>
  );
};

const formatDuration = (ms?: number) => {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

const formatTimestamp = (timestamp: string) => {
  return new Date(timestamp).toLocaleString();
};

interface ExecutionHistoryProps {
  nodes: Node[];
  edges: Edge[];
  workflowName: string;
  onNodeUpdate: (nodeId: string, updates: any) => void;
}

const ExecutionHistory: React.FC<ExecutionHistoryProps> = ({ 
  nodes, 
  edges, 
  workflowName, 
  onNodeUpdate 
}) => {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRowExpansion = (executionId: string) => {
    const newExpandedRows = new Set(expandedRows);
    if (newExpandedRows.has(executionId)) {
      newExpandedRows.delete(executionId);
    } else {
      newExpandedRows.add(executionId);
    }
    setExpandedRows(newExpandedRows);
  };

  return (
    <div className="h-full flex flex-col">
      <ExecutionEngine
        nodes={nodes}
        edges={edges}
        workflowName={workflowName}
        onNodeUpdate={onNodeUpdate}
        onExecutionComplete={(results) => {
          console.log('Workflow execution completed:', results);
        }}
      />
      
      <div className="flex items-center justify-between mb-4 mt-4">
        <div>
          <h3 className="text-sm font-medium text-foreground">Execution History</h3>
          <p className="text-xs text-muted-foreground">
            {mockExecutions.length} past executions
          </p>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8"></TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Trigger</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Progress</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockExecutions.map((execution) => (
              <React.Fragment key={execution.id}>
                <TableRow className="hover:bg-muted/50 cursor-pointer">
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={() => toggleRowExpansion(execution.id)}
                    >
                      {expandedRows.has(execution.id) ? (
                        <ChevronDown className="h-3 w-3" />
                      ) : (
                        <ChevronRight className="h-3 w-3" />
                      )}
                    </Button>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={execution.status} />
                  </TableCell>
                  <TableCell>
                    <span className="text-xs bg-muted px-2 py-1 rounded">
                      {execution.trigger_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatTimestamp(execution.start_time)}
                  </TableCell>
                  <TableCell className="text-xs">
                    {formatDuration(execution.duration_ms)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
                        <div 
                          className="h-full bg-primary transition-all duration-300"
                          style={{ 
                            width: `${(execution.completed_nodes / execution.total_nodes) * 100}%` 
                          }}
                        ></div>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {execution.completed_nodes}/{execution.total_nodes}
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
                
                {expandedRows.has(execution.id) && execution.node_executions.length > 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="p-0">
                      <div className="bg-muted/30 p-4 border-t">
                        <h4 className="text-xs font-medium mb-2">Node Executions</h4>
                        <div className="space-y-2">
                          {execution.node_executions.map((node) => (
                            <div 
                              key={node.node_id} 
                              className="flex items-center justify-between py-2 px-3 bg-background rounded border"
                            >
                              <div className="flex items-center gap-3">
                                <StatusBadge status={node.status} />
                                <div>
                                  <div className="text-xs font-medium">{node.node_name}</div>
                                  <div className="text-xs text-muted-foreground">{node.node_type}</div>
                                </div>
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {formatDuration(node.duration_ms)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};

export default ExecutionHistory;
