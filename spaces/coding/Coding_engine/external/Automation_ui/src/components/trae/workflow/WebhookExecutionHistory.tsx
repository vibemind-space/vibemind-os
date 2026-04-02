/**
 * Webhook Execution History Component
 * Shows list of webhook executions for webhook trigger nodes
 */

import React from 'react';
import { Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

interface WebhookExecution {
  id: string;
  timestamp: string;
  method: string;
  path: string;
  status: 'success' | 'error' | 'pending';
  duration?: number;
  payload?: any;
  headers?: any;
  response?: any;
  error?: string;
}

interface WebhookExecutionHistoryProps {
  executions: WebhookExecution[];
  onClearHistory?: () => void;
}

export const WebhookExecutionHistory: React.FC<WebhookExecutionHistoryProps> = ({
  executions,
  onClearHistory
}) => {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'pending':
        return <AlertCircle className="w-4 h-4 text-yellow-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = "px-2 py-1 text-xs rounded-full font-medium";
    switch (status) {
      case 'success':
        return `${baseClasses} bg-green-100 text-green-800`;
      case 'error':
        return `${baseClasses} bg-red-100 text-red-800`;
      case 'pending':
        return `${baseClasses} bg-yellow-100 text-yellow-800`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800`;
    }
  };

  if (executions.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <Clock className="w-8 h-8 mx-auto mb-2 text-gray-300" />
        <p className="text-sm">No webhook executions yet</p>
        <p className="text-xs text-gray-400 mt-1">
          Executions will appear here when webhooks are triggered
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-700">
            Execution History ({executions.length})
          </span>
        </div>
        {onClearHistory && (
          <button
            onClick={onClearHistory}
            className="text-xs text-gray-500 hover:text-red-600 transition-colors"
          >
            Clear History
          </button>
        )}
      </div>

      <div className="max-h-64 overflow-y-auto space-y-2">
        {executions.map((execution) => (
          <div
            key={execution.id}
            className="border border-gray-200 rounded-lg p-3 bg-white hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                {getStatusIcon(execution.status)}
                <span className="font-mono text-xs font-medium text-gray-600">
                  {execution.method} {execution.path}
                </span>
              </div>
              <span className={getStatusBadge(execution.status)}>
                {execution.status}
              </span>
            </div>

            <div className="text-xs text-gray-500 mb-2">
              {new Date(execution.timestamp).toLocaleString()}
              {execution.duration && (
                <span className="ml-2">• {execution.duration}ms</span>
              )}
            </div>

            {execution.error && (
              <div className="bg-red-50 border border-red-200 rounded p-2 mt-2">
                <p className="text-xs text-red-700 font-medium">Error:</p>
                <p className="text-xs text-red-600 mt-1">{execution.error}</p>
              </div>
            )}

            {execution.payload && (
              <details className="mt-2">
                <summary className="text-xs text-gray-600 cursor-pointer hover:text-gray-800">
                  View Payload
                </summary>
                <pre className="text-xs bg-gray-50 border rounded p-2 mt-1 overflow-x-auto">
                  {JSON.stringify(execution.payload, null, 2)}
                </pre>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};