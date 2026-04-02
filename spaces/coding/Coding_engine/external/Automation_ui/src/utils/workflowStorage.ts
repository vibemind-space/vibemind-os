
import { Node, Edge } from '@xyflow/react';

export interface SavedWorkflow {
  id: string;
  name: string;
  description?: string;
  nodes: Node[];
  edges: Edge[];
  settings?: Record<string, any>;
  createdAt: string;
  updatedAt: string;
}

export class WorkflowStorage {
  private static STORAGE_KEY = 'trae_workflows';

  static saveWorkflow(workflow: Omit<SavedWorkflow, 'id' | 'createdAt' | 'updatedAt'>): SavedWorkflow {
    const id = `workflow_${Date.now()}`;
    const timestamp = new Date().toISOString();
    
    const savedWorkflow: SavedWorkflow = {
      ...workflow,
      id,
      createdAt: timestamp,
      updatedAt: timestamp
    };

    const workflows = this.getAllWorkflows();
    workflows.push(savedWorkflow);
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(workflows));
    
    return savedWorkflow;
  }

  static updateWorkflow(id: string, updates: Partial<SavedWorkflow>): SavedWorkflow | null {
    const workflows = this.getAllWorkflows();
    const index = workflows.findIndex(w => w.id === id);
    
    if (index === -1) return null;
    
    workflows[index] = {
      ...workflows[index],
      ...updates,
      updatedAt: new Date().toISOString()
    };
    
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(workflows));
    return workflows[index];
  }

  static getAllWorkflows(): SavedWorkflow[] {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  }

  static getWorkflow(id: string): SavedWorkflow | null {
    const workflows = this.getAllWorkflows();
    return workflows.find(w => w.id === id) || null;
  }

  static deleteWorkflow(id: string): boolean {
    const workflows = this.getAllWorkflows();
    const filtered = workflows.filter(w => w.id !== id);
    
    if (filtered.length === workflows.length) return false;
    
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(filtered));
    return true;
  }

  static exportWorkflow(id: string): string | null {
    const workflow = this.getWorkflow(id);
    if (!workflow) return null;
    
    return JSON.stringify(workflow, null, 2);
  }

  static importWorkflow(jsonData: string): SavedWorkflow | null {
    try {
      const workflow = JSON.parse(jsonData);
      
      // Validate basic structure
      if (!workflow.nodes || !workflow.edges || !workflow.name) {
        throw new Error('Invalid workflow format');
      }
      
      return this.saveWorkflow({
        name: `${workflow.name} (Imported)`,
        description: workflow.description,
        nodes: workflow.nodes,
        edges: workflow.edges,
        settings: workflow.settings
      });
    } catch {
      return null;
    }
  }
}
