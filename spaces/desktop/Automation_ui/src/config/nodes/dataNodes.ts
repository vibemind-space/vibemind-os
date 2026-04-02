/**
 * Data Node Definitions
 */

import { createNodeTemplate } from './nodeTemplate';

export const dataNodes = [
  createNodeTemplate({
    id: 'data-transform',
    type: 'data',
    label: 'Transform',
    category: 'data',
    description: 'Transform data'
  }),
  createNodeTemplate({
    id: 'data-filter',
    type: 'data',
    label: 'Filter',
    category: 'data',
    description: 'Filter data'
  })
];

export default dataNodes;
