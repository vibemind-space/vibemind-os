/**
 * ClarificationAPI - API client for clarification queue endpoints.
 *
 * Provides methods to fetch pending clarifications, submit choices,
 * and use default resolutions.
 */

import { API_BASE_URL } from './config';

// Types matching backend QueuedClarification
export interface Interpretation {
  id: string;
  label: string;
  description: string;
  technical_approach: string;
  complexity: 'low' | 'medium' | 'high';
  is_recommended: boolean;
  trade_offs: string[];
}

export interface QueuedClarification {
  id: string;
  ambiguity_id: string;
  requirement_id: string;
  description: string;
  requirement_text: string;
  detected_term: string;
  priority: number; // 1=high, 2=medium, 3=low
  severity: 'high' | 'medium' | 'low';
  queued_at: string;
  timeout_at: string | null;
  answered: boolean;
  selected_interpretation_id: string | null;
  auto_resolved: boolean;
  interpretations: Interpretation[];
}

export interface ClarificationStatistics {
  total: number;
  pending: number;
  resolved: number;
  auto_resolved: number;
  by_priority: {
    high: number;
    medium: number;
    low: number;
  };
  by_severity: {
    high: number;
    medium: number;
    low: number;
  };
}

export interface PendingClarificationsResponse {
  pending: QueuedClarification[];
  queue_mode: boolean;
  count: number;
  statistics: ClarificationStatistics;
}

export interface ResolveResponse {
  success: boolean;
  clarification_id?: string;
  interpretation_id?: string;
  pending_count: number;
}

export interface ResolveAllResponse {
  success: boolean;
  resolved_count: number;
  pending_count: number;
}

const getApiBase = (): string => {
  // Use configured base URL or default
  return API_BASE_URL || 'http://localhost:8000';
};

/**
 * Fetch all pending clarifications from the queue.
 */
export async function fetchPendingClarifications(): Promise<PendingClarificationsResponse> {
  const response = await fetch(
    `${getApiBase()}/api/v1/dashboard/notifications/clarifications`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch clarifications: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Submit a choice for a specific clarification.
 *
 * @param clarificationId - The queue item ID (CLARQ-XXXX)
 * @param interpretationId - The chosen interpretation ID
 */
export async function submitClarificationChoice(
  clarificationId: string,
  interpretationId: string
): Promise<ResolveResponse> {
  const response = await fetch(
    `${getApiBase()}/api/v1/dashboard/notifications/clarifications/${clarificationId}/resolve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interpretation_id: interpretationId }),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'Failed to submit choice');
  }

  return response.json();
}

/**
 * Resolve all pending clarifications with their recommended defaults.
 */
export async function useAllDefaultClarifications(): Promise<ResolveAllResponse> {
  const response = await fetch(
    `${getApiBase()}/api/v1/dashboard/notifications/clarifications/resolve-all-defaults`,
    { method: 'POST' }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'Failed to use defaults');
  }

  return response.json();
}

/**
 * Get clarification queue statistics.
 */
export async function getClarificationStatistics(): Promise<{
  queue_mode: boolean;
  statistics: ClarificationStatistics;
}> {
  const response = await fetch(
    `${getApiBase()}/api/v1/dashboard/notifications/clarifications/statistics`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch statistics: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Format time remaining until timeout.
 *
 * @param timeoutAt - ISO timestamp of timeout
 * @returns Formatted string like "4m 30s" or "expired"
 */
export function formatTimeRemaining(timeoutAt: string | null): string {
  if (!timeoutAt) return '';

  const now = new Date();
  const timeout = new Date(timeoutAt);
  const diffMs = timeout.getTime() - now.getTime();

  if (diffMs <= 0) return 'expired';

  const diffSeconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(diffSeconds / 60);
  const seconds = diffSeconds % 60;

  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

/**
 * Get priority label from numeric priority.
 */
export function getPriorityLabel(priority: number): string {
  switch (priority) {
    case 1:
      return 'High';
    case 2:
      return 'Medium';
    case 3:
      return 'Low';
    default:
      return 'Unknown';
  }
}

/**
 * Get severity color class for styling.
 */
export function getSeverityColorClass(severity: string): string {
  switch (severity) {
    case 'high':
      return 'border-red-500 bg-red-500/10';
    case 'medium':
      return 'border-amber-500 bg-amber-500/10';
    case 'low':
      return 'border-blue-500 bg-blue-500/10';
    default:
      return 'border-zinc-500 bg-zinc-500/10';
  }
}
