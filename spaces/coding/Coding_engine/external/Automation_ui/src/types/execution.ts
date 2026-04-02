export interface NodeExecution {
  node_id: string;
  node_name: string;
  node_type: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped';
  start_time?: string;
  end_time?: string;
  duration_ms?: number;
  input_data?: any;
  output_data?: any;
  error_message?: string;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  workflow_name: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled';
  trigger_type: 'manual' | 'webhook' | 'schedule' | 'file_watch';
  start_time: string;
  end_time?: string;
  duration_ms?: number;
  total_nodes: number;
  completed_nodes: number;
  failed_nodes: number;
  node_executions: NodeExecution[];
  error_message?: string;
}

export interface ExecutionStats {
  total_executions: number;
  success_rate: number;
  avg_duration_ms: number;
  last_execution?: string;
}