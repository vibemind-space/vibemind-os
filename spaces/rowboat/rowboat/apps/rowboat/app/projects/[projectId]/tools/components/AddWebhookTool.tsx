'use client';

import React from 'react';
import { WebhookConfig } from './WebhookConfig';
import { Button } from '@heroui/react';
import { WorkflowTool } from '@/app/lib/types/workflow_types';
import { z } from 'zod';

interface AddWebhookToolProps {
  projectId: string;
  onAddTool: (tool: Partial<z.infer<typeof WorkflowTool>>) => void;
}

export function AddWebhookTool({ projectId, onAddTool }: AddWebhookToolProps) {
  function handleAddTool() {
    onAddTool({
      description: 'Webhook tool',
      mockTool: true,
      isWebhook: true,
    });
  }

  return (
    <div className="space-y-6">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Add webhook tool
        </h2>
      </div>
      
      <WebhookConfig projectId={projectId} />

      <div>
        Click here to add a webhook tool:
      </div>
      <Button
        size="lg"
        color="primary"
        onPress={handleAddTool}
      >Add webhook tool</Button>
    </div>
  );
} 