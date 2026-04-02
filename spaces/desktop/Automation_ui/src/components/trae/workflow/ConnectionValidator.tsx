
import { Node, Edge, Connection } from '@xyflow/react';

export interface ValidationResult {
  valid: boolean;
  error?: string;
  warning?: string;
}

export interface NodeConnectionRules {
  allowedSources: string[];
  allowedTargets: string[];
  maxInputs?: number;
  maxOutputs?: number;
  requiredInputs?: string[];
}

const NODE_CONNECTION_RULES: Record<string, NodeConnectionRules> = {
  // Config nodes (no workflow connections)
  websocket_config: {
    allowedSources: [],
    allowedTargets: ['live_desktop'],
    maxInputs: 0,
    maxOutputs: 1,
  },
  
  // Desktop nodes
  live_desktop: {
    allowedSources: ['manual_trigger', 'schedule_trigger', 'webhook_trigger'],
    allowedTargets: ['click_action', 'type_text_action', 'ocr_action'],
    maxInputs: 2,
    maxOutputs: 1,
    requiredInputs: ['websocket_config']
  },
  // Action nodes
  click_action: {
    allowedSources: ['live_desktop', 'manual_trigger', 'schedule_trigger', 'webhook_trigger'],
    allowedTargets: ['end'],
    maxInputs: 1,
    maxOutputs: 1,
  },
  type_text_action: {
    allowedSources: ['live_desktop', 'manual_trigger', 'schedule_trigger', 'webhook_trigger'],
    allowedTargets: ['end'],
    maxInputs: 1,
    maxOutputs: 1,
  },
  ocr_action: {
    allowedSources: ['live_desktop', 'manual_trigger', 'schedule_trigger', 'webhook_trigger'],
    allowedTargets: ['end'],
    maxInputs: 1,
    maxOutputs: 1,
  },
  if_condition: {
    allowedSources: ['live_desktop', 'click_action', 'type_text_action', 'variable_store'],
    allowedTargets: ['click_action', 'type_text_action', 'delay', 'end'],
    maxInputs: 1,
    maxOutputs: 2,
  },
  delay: {
    allowedSources: ['click_action', 'type_text_action', 'if_condition'],
    allowedTargets: ['click_action', 'type_text_action', 'if_condition', 'end'],
    maxInputs: 1,
    maxOutputs: 1,
  },
  variable_store: {
    allowedSources: ['live_desktop', 'click_action', 'type_text_action'],
    allowedTargets: ['if_condition', 'type_text_action'],
    maxInputs: 3,
    maxOutputs: 5,
  },
  // Trigger nodes
  manual_trigger: {
    allowedSources: [],
    allowedTargets: ['live_desktop', 'click_action', 'type_text_action', 'ocr_action'],
    maxInputs: 0,
    maxOutputs: 1,
  },
  schedule_trigger: {
    allowedSources: [],
    allowedTargets: ['live_desktop', 'click_action', 'type_text_action', 'ocr_action'],
    maxInputs: 0,
    maxOutputs: 1,
  },
  webhook_trigger: {
    allowedSources: [],
    allowedTargets: ['live_desktop', 'click_action', 'type_text_action', 'ocr_action'],
    maxInputs: 0,
    maxOutputs: 1,
  },
  end: {
    allowedSources: ['click_action', 'type_text_action', 'if_condition', 'delay'],
    allowedTargets: [],
    maxInputs: 10,
    maxOutputs: 0,
  },
};

export class ConnectionValidator {
  static validateConnection(params: Connection, nodes: Node[]): ValidationResult {
    const sourceNode = nodes.find(n => n.id === params.source);
    const targetNode = nodes.find(n => n.id === params.target);

    if (!sourceNode || !targetNode) {
      return { valid: false, error: 'Source or target node not found' };
    }

    const sourceRules = NODE_CONNECTION_RULES[(sourceNode.data as any)?.type];
    const targetRules = NODE_CONNECTION_RULES[(targetNode.data as any)?.type];

    if (!sourceRules || !targetRules) {
      return { valid: false, error: 'Unknown node type in connection' };
    }

    // Check if target is allowed for source
    if (!sourceRules.allowedTargets.includes((targetNode.data as any)?.type)) {
      return {
        valid: false,
        error: `${(sourceNode.data as any)?.type} cannot connect to ${(targetNode.data as any)?.type}`
      };
    }

    // Check if source is allowed for target
    if (!targetRules.allowedSources.includes((sourceNode.data as any)?.type)) {
      return {
        valid: false,
        error: `${(targetNode.data as any)?.type} cannot accept connections from ${(sourceNode.data as any)?.type}`
      };
    }

    return { valid: true };
  }

  static validateWorkflow(nodes: Node[], edges: Edge[]): ValidationResult {
    // Check for required start nodes
    const hasValidStart = nodes.some(n => 
      (n.data as any)?.type === 'manual_trigger' || (n.data as any)?.type === 'schedule_trigger'
    );

    if (!hasValidStart) {
      return { valid: false, error: 'Workflow must have a trigger node (Manual or Schedule)' };
    }

    // Check for end nodes
    const hasEnd = nodes.some(n => (n.data as any)?.type === 'end');
    if (!hasEnd) {
      return { valid: false, error: 'Workflow must have an End node' };
    }

    // Check Live Desktop + WebSocket Config requirement
    const liveDesktopNodes = nodes.filter(n => (n.data as any)?.type === 'live_desktop');
    const websocketConfigNodes = nodes.filter(n => (n.data as any)?.type === 'websocket_config');

    if (liveDesktopNodes.length > 0 && websocketConfigNodes.length === 0) {
      return { 
        valid: false, 
        error: 'Live Desktop nodes require WebSocket Config nodes' 
      };
    }

    // Check for orphaned nodes
    const connectedNodeIds = new Set();
    edges.forEach(edge => {
      connectedNodeIds.add(edge.source);
      connectedNodeIds.add(edge.target);
    });

    const orphanedNodes = nodes.filter(n => 
      !connectedNodeIds.has(n.id) && 
      (n.data as any)?.type !== 'manual_trigger' && 
      (n.data as any)?.type !== 'schedule_trigger'
    );

    if (orphanedNodes.length > 0) {
      return {
        valid: true,
        warning: `${orphanedNodes.length} nodes are not connected to the workflow`
      };
    }

    return { valid: true };
  }
}
