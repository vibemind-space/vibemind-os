/**
 * Node Type Definitions
 */

export type NodeCategory = 'trigger' | 'action' | 'logic' | 'data' | 'snapshot' | 'automation';

export interface NodeConfig {
  id: string;
  type: string;
  label: string;
  category: NodeCategory;
  inputs?: number;
  outputs?: number;
}

export default NodeConfig;
