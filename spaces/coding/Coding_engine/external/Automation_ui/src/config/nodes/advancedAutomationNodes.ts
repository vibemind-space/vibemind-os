/**
 * Advanced Automation Node Definitions
 */

import { createNodeTemplate } from './nodeTemplate';

export const advancedAutomationNodes = [
  createNodeTemplate({
    id: 'ai-automation',
    type: 'automation',
    label: 'AI Automation',
    category: 'automation',
    description: 'AI-powered automation'
  }),
  createNodeTemplate({
    id: 'ocr-extraction',
    type: 'automation',
    label: 'OCR',
    category: 'automation',
    description: 'Text extraction'
  })
];

export default advancedAutomationNodes;
