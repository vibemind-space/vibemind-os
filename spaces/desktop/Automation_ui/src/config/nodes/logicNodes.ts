/**
 * Logic Node Definitions
 */

import { createNodeTemplate } from './nodeTemplate';

export const logicNodes = [
  createNodeTemplate({
    id: 'if-else',
    type: 'logic',
    label: 'If/Else',
    category: 'logic',
    description: 'Conditional branching'
  }),
  createNodeTemplate({
    id: 'switch',
    type: 'logic',
    label: 'Switch',
    category: 'logic',
    description: 'Multiple condition routing'
  })
];

export default logicNodes;
