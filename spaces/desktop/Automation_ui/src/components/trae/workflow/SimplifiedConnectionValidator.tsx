
/**
 * Simplified Connection Validator
 * Enhanced with C4 Architecture validation rules
 */

import { Node, Edge, Connection } from '@xyflow/react';
import { SIMPLIFIED_NODE_TEMPLATES } from '../../../config/simplifiedNodeTemplates';

export interface ValidationResult {
  valid: boolean;
  error?: string;
  warning?: string;
}

export class SimplifiedConnectionValidator {
  static validateConnection(params: Connection, nodes: Node[]): ValidationResult {
    const sourceNode = nodes.find(n => n.id === params.source);
    const targetNode = nodes.find(n => n.id === params.target);

    if (!sourceNode || !targetNode) {
      return { valid: false, error: 'Source or target node not found' };
    }

    // Type guard to ensure we have valid node types
    const sourceType = sourceNode.data?.type;
    const targetType = targetNode.data?.type;
    
    if (typeof sourceType !== 'string' || typeof targetType !== 'string') {
      return { valid: false, error: 'Invalid node type' };
    }

    const sourceTemplate = SIMPLIFIED_NODE_TEMPLATES[sourceType];
    const targetTemplate = SIMPLIFIED_NODE_TEMPLATES[targetType];

    if (!sourceTemplate || !targetTemplate) {
      return { valid: false, error: 'Unknown node type in connection' };
    }

    // C4 Architecture Connection Rules
    return this.validateC4ArchitectureRules(sourceTemplate, targetTemplate, params);
  }

  /**
   * Validates connections according to C4 Architecture rules:
   * Config → Interface → Actions → Logic → Results
   */
  private static validateC4ArchitectureRules(
    sourceTemplate: any, 
    targetTemplate: any, 
    params: Connection
  ): ValidationResult {
    const sourceCategory = sourceTemplate.category;
    const targetCategory = targetTemplate.category;

    // Rule 1: Config nodes can only connect to Interface nodes (warning first, then allow)
    if (sourceCategory === 'config') {
      if (targetCategory !== 'interface') {
        return {
          valid: true,
          warning: `Config nodes (${sourceTemplate.label}) work best when connected to Interface nodes. Consider adding a Live Desktop Interface node.`
        };
      }
      
      // Validate specific config connection
      const sourceOutput = sourceTemplate.outputs?.[0];
      const targetInput = targetTemplate.inputs?.find((input: any) => 
        input.accepts?.includes(sourceOutput?.provides)
      );
      
      if (!targetInput) {
        return {
          valid: false,
          error: `${targetTemplate.label} cannot accept ${sourceOutput?.provides} from ${sourceTemplate.label}`
        };
      }
      
      return { valid: true };
    }

    // Rule 2: Trigger nodes can only connect to Interface nodes (warning first, then allow)
    if (sourceCategory === 'triggers') {
      if (targetCategory !== 'interface') {
        return {
          valid: true,
          warning: `Trigger nodes (${sourceTemplate.label}) work best when connected to Interface nodes. Consider adding a Live Desktop Interface node.`
        };
      }
      
      // Validate trigger connection
      const sourceOutput = sourceTemplate.outputs?.[0];
      const targetInput = targetTemplate.inputs?.find((input: any) => 
        input.accepts?.includes(sourceOutput?.provides)
      );
      
      if (!targetInput) {
        return {
          valid: false,
          error: `${targetTemplate.label} cannot accept ${sourceOutput?.provides} from ${sourceTemplate.label}`
        };
      }
      
      return { valid: true };
    }

    // Rule 3: Interface nodes can connect to Action nodes (more permissive)
    if (sourceCategory === 'interface') {
      if (!['actions', 'logic', 'results', 'triggers'].includes(targetCategory)) {
        return {
          valid: true,
          warning: `Interface nodes (${sourceTemplate.label}) work best when connected to Action, Logic, or Result nodes.`
        };
      }
      
      return this.validateDataConnection(sourceTemplate, targetTemplate, params);
    }

    // Rule 4: Action nodes can connect to other Action nodes, Logic nodes, or back to Interface nodes
    if (sourceCategory === 'actions') {
      if (!['actions', 'logic', 'results', 'interface'].includes(targetCategory)) {
        return {
          valid: false,
          error: `Action nodes (${sourceTemplate.label}) can only connect to Action, Logic, Result, or Interface nodes, not ${targetCategory} nodes`
        };
      }
      
      return this.validateDataConnection(sourceTemplate, targetTemplate, params);
    }

    // Rule 5: Logic nodes can connect to Result nodes or other Logic nodes
    if (sourceCategory === 'logic') {
      if (!['logic', 'results'].includes(targetCategory)) {
        return {
          valid: false,
          error: `Logic nodes (${sourceTemplate.label}) can only connect to other Logic or Result nodes, not ${targetCategory} nodes`
        };
      }
      
      return this.validateDataConnection(sourceTemplate, targetTemplate, params);
    }

    // Rule 6: Result nodes cannot be source nodes (they are endpoints)
    if (sourceCategory === 'results') {
      return {
        valid: false,
        error: `Result nodes (${sourceTemplate.label}) cannot be used as source nodes - they are workflow endpoints`
      };
    }

    // Default validation for any other cases
    return this.validateDataConnection(sourceTemplate, targetTemplate, params);
  }

  /**
   * Validates data connections between nodes
   */
  private static validateDataConnection(
    sourceTemplate: any, 
    targetTemplate: any, 
    params: Connection
  ): ValidationResult {
    // Find the specific output being connected
    const sourceOutputId = params.sourceHandle;
    const targetInputId = params.targetHandle;

    let sourceOutput;
    if (sourceTemplate.outputs && sourceOutputId) {
      sourceOutput = sourceTemplate.outputs.find((output: any) => output.id === sourceOutputId);
    } else if (sourceTemplate.output) {
      sourceOutput = sourceTemplate.output;
    }

    let targetInput;
    if (targetTemplate.inputs && targetInputId) {
      targetInput = targetTemplate.inputs.find((input: any) => input.id === targetInputId);
    } else if (targetTemplate.input) {
      targetInput = targetTemplate.input;
    }

    if (!sourceOutput) {
      return { valid: false, error: `${sourceTemplate.label} has no valid output` };
    }

    if (!targetInput) {
      return { valid: false, error: `${targetTemplate.label} has no valid input` };
    }

    // Check if target accepts what source provides (more permissive)
    const sourceProvides = sourceOutput.provides;
    const targetAccepts = targetInput.accepts;

    if (!targetAccepts || !targetAccepts.includes(sourceProvides)) {
      return {
        valid: true,
        warning: `Data types may not match: ${targetTemplate.label} (${targetInput.name}) expects different data than what ${sourceTemplate.label} (${sourceOutput.name}) provides. Connection allowed but may need configuration.`
      };
    }

    return { valid: true };
  }

  static validateWorkflow(nodes: Node[], edges: Edge[]): ValidationResult {
    // C4 Architecture Workflow Validation

    // Rule 1: Must have at least one trigger
    const triggerNodes = nodes.filter(n => {
      const nodeType = n.data?.type;
      if (typeof nodeType !== 'string') return false;
      
      const template = SIMPLIFIED_NODE_TEMPLATES[nodeType];
      return template && template.category === 'triggers';
    });

    if (triggerNodes.length === 0) {
      return { valid: false, error: 'Workflow must have at least one trigger node' };
    }

    // Rule 2: Interface nodes must have config connections
    const interfaceNodes = nodes.filter(n => {
      const nodeType = n.data?.type;
      if (typeof nodeType !== 'string') return false;
      
      const template = SIMPLIFIED_NODE_TEMPLATES[nodeType];
      return template && template.category === 'interface';
    });

    for (const interfaceNode of interfaceNodes) {
      const hasConfigConnection = edges.some(edge => {
        const sourceNode = nodes.find(n => n.id === edge.source);
        if (!sourceNode) return false;
        
        const sourceType = sourceNode.data?.type;
        if (typeof sourceType !== 'string') return false;
        
        const sourceTemplate = SIMPLIFIED_NODE_TEMPLATES[sourceType];
        return sourceTemplate && 
               sourceTemplate.category === 'config' && 
               edge.target === interfaceNode.id;
      });

      if (!hasConfigConnection) {
        const template = SIMPLIFIED_NODE_TEMPLATES[interfaceNode.data?.type as keyof typeof SIMPLIFIED_NODE_TEMPLATES];
        return {
          valid: false,
          error: `Interface node "${template?.label}" requires a config connection (e.g., WebSocket Service)`
        };
      }
    }

    // Rule 3: Check for proper C4 flow
    const configNodes = nodes.filter(n => {
      const nodeType = n.data?.type;
      if (typeof nodeType !== 'string') return false;
      
      const template = SIMPLIFIED_NODE_TEMPLATES[nodeType];
      return template && template.category === 'config';
    });

    // Warn if config nodes exist but no interface nodes
    if (configNodes.length > 0 && interfaceNodes.length === 0) {
      return {
        valid: true,
        warning: 'Config nodes found but no Interface nodes. Add a Live Desktop Interface to complete the C4 architecture.'
      };
    }

    // Rule 4: Check for orphaned nodes (except triggers and config)
    const connectedNodeIds = new Set();
    edges.forEach(edge => {
      connectedNodeIds.add(edge.source);
      connectedNodeIds.add(edge.target);
    });

    const orphanedNodes = nodes.filter(n => {
      const nodeType = n.data?.type;
      if (typeof nodeType !== 'string') return false;
      
      const template = SIMPLIFIED_NODE_TEMPLATES[nodeType];
      return template && 
             template.category !== 'triggers' && 
             template.category !== 'config' && 
             !connectedNodeIds.has(n.id);
    });

    if (orphanedNodes.length > 0) {
      return {
        valid: true,
        warning: `${orphanedNodes.length} nodes are not connected to the workflow. Follow C4 architecture: Config → Interface → Actions → Logic → Results`
      };
    }

    return { valid: true };
  }

  static checkNodeDependencies(nodeType: string, allNodes: Node[]): ValidationResult {
    const template = SIMPLIFIED_NODE_TEMPLATES[nodeType];
    if (!template) return { valid: true };

    // C4 Architecture dependency checking
    if (template.category === 'interface') {
      // Interface nodes need config nodes
      const hasConfigNode = allNodes.some(n => {
        const nType = n.data?.type;
        if (typeof nType !== 'string') return false;
        
        const nTemplate = SIMPLIFIED_NODE_TEMPLATES[nType];
        return nTemplate && nTemplate.category === 'config';
      });

      if (!hasConfigNode) {
        return {
          valid: false,
          error: 'Interface nodes require a Config node (e.g., WebSocket Service) to be present in the workflow'
        };
      }
    }

    if (template.category === 'actions') {
      // Action nodes need interface nodes
      const hasInterfaceNode = allNodes.some(n => {
        const nType = n.data?.type;
        if (typeof nType !== 'string') return false;
        
        const nTemplate = SIMPLIFIED_NODE_TEMPLATES[nType];
        return nTemplate && nTemplate.category === 'interface';
      });

      if (!hasInterfaceNode) {
        return {
          valid: false,
          error: 'Action nodes require an Interface node (e.g., Live Desktop Interface) to be present in the workflow'
        };
      }
    }

    return { valid: true };
  }

  /**
   * Get connection suggestions based on C4 architecture
   */
  static getConnectionSuggestions(nodeType: string): string[] {
    const template = SIMPLIFIED_NODE_TEMPLATES[nodeType];
    if (!template) return [];

    switch (template.category) {
      case 'config':
        return ['Add an Interface node (e.g., Live Desktop Interface) to connect this config'];
      case 'triggers':
        return ['Connect to an Interface node to start the workflow'];
      case 'interface':
        return ['Connect to Action nodes to perform operations', 'Connect to Logic nodes for data processing'];
      case 'actions':
        return ['Connect to other Action nodes to chain operations', 'Connect to Logic nodes for processing', 'Connect to Result nodes to output data'];
      case 'logic':
        return ['Connect to Result nodes to output processed data', 'Connect to other Logic nodes for complex processing'];
      default:
        return [];
    }
  }
}
