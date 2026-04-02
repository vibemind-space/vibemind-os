
export interface NodeVariable {
  id: string;
  name: string;
  type: 'input' | 'output' | 'config';
  dataType: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'null';
  value: any;
  description?: string;
  timestamp: string;
}

export interface WorkflowVariable {
  id: string;
  name: string;
  value: any;
  type: 'global' | 'environment' | 'runtime';
  dataType: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'null';
  description?: string;
  isEditable: boolean;
  lastModified: string;
}

export interface VariableContext {
  workflow_id: string;
  execution_id?: string;
  node_variables: Record<string, NodeVariable[]>;
  workflow_variables: WorkflowVariable[];
  environment_variables: Record<string, any>;
}

export interface VariableFilters {
  type?: 'input' | 'output' | 'config' | 'global' | 'environment';
  dataType?: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'null';
  search?: string;
  nodeId?: string;
}
