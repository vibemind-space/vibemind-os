/**
 * ============================================================================
 * WORKFLOW SERIALIZATION SERVICE
 * ============================================================================
 * 
 * Converts React Flow canvas state into standardized execution format.
 * Transforms nodes and edges into executable workflow data packets and 
 * dependency graphs for the execution engine.
 */

import { Node, Edge } from '@xyflow/react';
import { WorkflowDataPacket } from '@/types/dataFlow';
import { SIMPLIFIED_NODE_TEMPLATES } from '@/config/simplifiedNodeTemplates';

export interface SerializedWorkflow {
  id: string;
  name: string;
  nodes: SerializedNode[];
  edges: SerializedEdge[];
  executionOrder: string[];
  dataFlow: Map<string, WorkflowDataPacket>;
  metadata: {
    version: string;
    createdAt: string;
    lastModified: string;
    nodeCount: number;
    edgeCount: number;
  };
}

export interface SerializedNode {
  id: string;
  type: string;
  label: string;
  position: { x: number; y: number };
  config: Record<string, any>;
  template: any;
  inputs: NodeConnection[];
  outputs: NodeConnection[];
  dependencies: string[];
}

export interface SerializedEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  dataType: string;
}

export interface NodeConnection {
  id: string;
  name: string;
  type: 'input' | 'output';
  dataType: string;
  required: boolean;
  connected: boolean;
  connectedTo?: string[];
}

export class WorkflowSerializer {
  /**
   * Serialize React Flow canvas state to executable workflow format
   */
  public static serialize(
    nodes: Node[], 
    edges: Edge[], 
    workflowName: string = 'Untitled Workflow'
  ): SerializedWorkflow {
    const workflowId = `workflow_${Date.now()}`;
    
    // Transform nodes with configuration and templates
    const serializedNodes = nodes.map(node => this.serializeNode(node, edges));
    
    // Transform edges with data type information
    const serializedEdges = edges.map(edge => this.serializeEdge(edge, nodes));
    
    // Calculate execution order based on dependencies
    const executionOrder = this.calculateExecutionOrder(serializedNodes, serializedEdges);
    
    // Generate data flow packets for each node
    const dataFlow = this.generateDataFlow(serializedNodes, serializedEdges, workflowId);
    
    return {
      id: workflowId,
      name: workflowName,
      nodes: serializedNodes,
      edges: serializedEdges,
      executionOrder,
      dataFlow,
      metadata: {
        version: '1.0.0',
        createdAt: new Date().toISOString(),
        lastModified: new Date().toISOString(),
        nodeCount: nodes.length,
        edgeCount: edges.length
      }
    };
  }

  /**
   * Serialize individual node with template and configuration
   */
  private static serializeNode(node: Node, edges: Edge[]): SerializedNode {
    const nodeData = node.data as any;
    const template = SIMPLIFIED_NODE_TEMPLATES[nodeData?.type || 'unknown'];
    
    // Get incoming and outgoing edges for this node
    const incomingEdges = edges.filter(e => e.target === node.id);
    const outgoingEdges = edges.filter(e => e.source === node.id);
    
    // Build input connections
    const inputs: NodeConnection[] = template?.inputs?.map((input: any) => ({
      id: input.id,
      name: input.name,
      type: 'input' as const,
      dataType: input.accepts?.[0] || 'any',
      required: input.required || false,
      connected: incomingEdges.some(e => e.targetHandle === input.id),
      connectedTo: incomingEdges
        .filter(e => e.targetHandle === input.id)
        .map(e => e.source)
    })) || [];

    // Build output connections
    const outputs: NodeConnection[] = template?.outputs?.map((output: any) => ({
      id: output.id,
      name: output.name,
      type: 'output' as const,
      dataType: output.provides || 'any',
      required: false,
      connected: outgoingEdges.some(e => e.sourceHandle === output.id),
      connectedTo: outgoingEdges
        .filter(e => e.sourceHandle === output.id)
        .map(e => e.target)
    })) || [];

    // Calculate dependencies (nodes that must execute before this one)
    const dependencies = incomingEdges.map(e => e.source);

    return {
      id: node.id,
      type: nodeData?.type || 'unknown',
      label: nodeData?.label || node.id,
      position: node.position,
      config: nodeData?.config || {},
      template,
      inputs,
      outputs,
      dependencies
    };
  }

  /**
   * Serialize individual edge with data type information
   */
  private static serializeEdge(edge: Edge, nodes: Node[]): SerializedEdge {
    const sourceNode = nodes.find(n => n.id === edge.source);
    const targetNode = nodes.find(n => n.id === edge.target);
    
    // Determine data type based on source node output
    let dataType = 'any';
    if (sourceNode) {
      const sourceTemplate = SIMPLIFIED_NODE_TEMPLATES[(sourceNode.data as any)?.type];
      const sourceOutput = sourceTemplate?.outputs?.find((o: any) => o.id === edge.sourceHandle);
      if (sourceOutput) {
        dataType = sourceOutput.provides || 'any';
      }
    }

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      dataType
    };
  }

  /**
   * Calculate execution order based on node dependencies
   */
  private static calculateExecutionOrder(
    nodes: SerializedNode[], 
    edges: SerializedEdge[]
  ): string[] {
    const visited = new Set<string>();
    const visiting = new Set<string>();
    const order: string[] = [];
    
    const visit = (nodeId: string) => {
      if (visited.has(nodeId)) return;
      if (visiting.has(nodeId)) {
        throw new Error(`Circular dependency detected involving node: ${nodeId}`);
      }
      
      visiting.add(nodeId);
      
      const node = nodes.find(n => n.id === nodeId);
      if (node) {
        // Visit all dependencies first
        node.dependencies.forEach(depId => visit(depId));
      }
      
      visiting.delete(nodeId);
      visited.add(nodeId);
      order.push(nodeId);
    };

    // Start with trigger nodes (nodes with no dependencies)
    const triggerNodes = nodes.filter(n => n.dependencies.length === 0);
    
    if (triggerNodes.length === 0) {
      throw new Error('No trigger nodes found - workflow must have at least one starting point');
    }
    
    triggerNodes.forEach(node => visit(node.id));
    
    // Visit any remaining unvisited nodes
    nodes.forEach(node => {
      if (!visited.has(node.id)) {
        visit(node.id);
      }
    });
    
    return order;
  }

  /**
   * Generate data flow packets for workflow execution
   */
  private static generateDataFlow(
    nodes: SerializedNode[],
    edges: SerializedEdge[],
    workflowId: string
  ): Map<string, WorkflowDataPacket> {
    const dataFlow = new Map<string, WorkflowDataPacket>();
    const executionId = `exec_${Date.now()}`;
    
    nodes.forEach(node => {
      const packet: WorkflowDataPacket = {
        trigger: {
          timestamp: new Date().toISOString(),
          source: 'workflow_serializer',
          type: node.type === 'manual_trigger' ? 'manual' : 'schedule',
          payload: node.config
        },
        data: {
          type: this.inferDataType(node),
          value: node.config,
          format: 'json'
        },
        context: {
          workflow_id: workflowId,
          execution_id: executionId,
          node_id: node.id,
          parent_node_id: node.dependencies[0] // First dependency as parent
        },
        metadata: {
          success: true,
          duration_ms: 0, // Will be filled during execution
          node_type: node.type
        }
      };
      
      dataFlow.set(node.id, packet);
    });
    
    return dataFlow;
  }

  /**
   * Infer data type from node configuration
   */
  private static inferDataType(node: SerializedNode): 'coordinates' | 'text' | 'image' | 'boolean' | 'object' | 'array' {
    switch (node.type) {
      case 'click_action':
        return 'coordinates';
      case 'type_text_action':
        return 'text';
      case 'screenshot_action':
      case 'ocr_action':
        return 'image';
      case 'if_condition':
        return 'boolean';
      default:
        return 'object';
    }
  }

  /**
   * Validate workflow integrity
   */
  public static validate(workflow: SerializedWorkflow): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    
    // Check for orphaned nodes
    const connectedNodes = new Set([
      ...workflow.edges.map(e => e.source),
      ...workflow.edges.map(e => e.target)
    ]);
    
    const orphanedNodes = workflow.nodes.filter(n => 
      !connectedNodes.has(n.id) && n.dependencies.length === 0 && 
      !['manual_trigger', 'schedule_trigger'].includes(n.type)
    );
    
    if (orphanedNodes.length > 0) {
      errors.push(`Orphaned nodes found: ${orphanedNodes.map(n => n.label).join(', ')}`);
    }
    
    // Check for missing required inputs
    workflow.nodes.forEach(node => {
      const missingInputs = node.inputs.filter(input => input.required && !input.connected);
      if (missingInputs.length > 0) {
        errors.push(`Node "${node.label}" has missing required inputs: ${missingInputs.map(i => i.name).join(', ')}`);
      }
    });
    
    // Check for circular dependencies (already done in calculateExecutionOrder, but double-check)
    try {
      this.calculateExecutionOrder(workflow.nodes, workflow.edges);
    } catch (error) {
      errors.push(`Dependency error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
    
    return {
      valid: errors.length === 0,
      errors
    };
  }

  /**
   * Convert serialized workflow back to React Flow format
   */
  public static deserialize(workflow: SerializedWorkflow): { nodes: Node[]; edges: Edge[] } {
    const nodes: Node[] = workflow.nodes.map(serializedNode => ({
      id: serializedNode.id,
      type: 'simplified',
      position: serializedNode.position,
      data: {
        type: serializedNode.type,
        label: serializedNode.label,
        config: serializedNode.config,
        template: serializedNode.template
      }
    }));
    
    const edges: Edge[] = workflow.edges.map(serializedEdge => ({
      id: serializedEdge.id,
      source: serializedEdge.source,
      target: serializedEdge.target,
      sourceHandle: serializedEdge.sourceHandle,
      targetHandle: serializedEdge.targetHandle
    }));
    
    return { nodes, edges };
  }
}