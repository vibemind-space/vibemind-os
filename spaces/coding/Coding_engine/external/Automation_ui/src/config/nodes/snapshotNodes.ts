/**
 * Snapshot Node Definitions
 */

import { createNodeTemplate } from './nodeTemplate';

export const snapshotNodes = [
  createNodeTemplate({
    id: 'screenshot',
    type: 'snapshot',
    label: 'Screenshot',
    category: 'snapshot',
    description: 'Capture screenshot'
  }),
  createNodeTemplate({
    id: 'screen-record',
    type: 'snapshot',
    label: 'Record',
    category: 'snapshot',
    description: 'Record screen'
  })
];

export default snapshotNodes;
