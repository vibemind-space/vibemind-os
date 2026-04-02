
/**
 * Standardized Data Flow Interface for TRAE Workflow System
 * Defines the JSON structure passed between nodes
 */

export interface WorkflowDataPacket {
  // Execution trigger information
  trigger: {
    timestamp: string;
    source: string;
    type: 'manual' | 'webhook' | 'schedule' | 'file_watch';
    payload: Record<string, any>;
  };
  
  // Main data payload
  data: {
    type: 'coordinates' | 'text' | 'image' | 'boolean' | 'object' | 'array';
    value: any;
    format?: string;
  };
  
  // Execution context
  context: {
    workflow_id: string;
    execution_id: string;
    node_id: string;
    parent_node_id?: string;
  };
  
  // Execution metadata
  metadata: {
    success: boolean;
    duration_ms: number;
    error?: string;
    node_type: string;
  };
}

export interface NodeDependency {
  id: string;
  type: string;
  required: boolean;
  description: string;
  status: 'connected' | 'missing' | 'invalid';
}

export interface NodeInputSpec {
  id: string;
  name: string;
  type: 'trigger' | 'data' | 'config';
  required: boolean;
  accepts: string[];
  description: string;
  placeholder?: string;
}

export interface NodeOutputSpec {
  id: string;
  name: string;
  type: 'data' | 'trigger' | 'event' | 'config';
  provides: string;
  description: string;
}
