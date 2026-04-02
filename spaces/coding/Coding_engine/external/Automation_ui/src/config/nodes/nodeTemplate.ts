/**
 * Node Template Definitions
 */

export interface NodeTemplate {
  id: string;
  type: string;
  label: string;
  category: string;
  icon?: string;
  description?: string;
}

export const createNodeTemplate = (config: Partial<NodeTemplate>): NodeTemplate => {
  return {
    id: config.id || 'node',
    type: config.type || 'custom',
    label: config.label || 'Node',
    category: config.category || 'general',
    icon: config.icon,
    description: config.description
  };
};

export default createNodeTemplate;
