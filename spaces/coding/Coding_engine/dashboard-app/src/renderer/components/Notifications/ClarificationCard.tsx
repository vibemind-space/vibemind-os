/**
 * ClarificationCard - Summary card for a clarification in the panel list.
 *
 * Displays:
 * - Description
 * - Priority indicator
 * - Requirement text preview
 * - Number of interpretations
 * - Time remaining until timeout
 */

import React, { useState, useEffect } from 'react';
import {
  QueuedClarification,
  formatTimeRemaining,
  getPriorityLabel,
  getSeverityColorClass,
} from '../../api/clarificationAPI';

interface ClarificationCardProps {
  clarification: QueuedClarification;
  onClick: () => void;
}

export const ClarificationCard: React.FC<ClarificationCardProps> = ({
  clarification,
  onClick,
}) => {
  const [timeRemaining, setTimeRemaining] = useState(
    formatTimeRemaining(clarification.timeout_at)
  );

  // Update time remaining every second
  useEffect(() => {
    if (!clarification.timeout_at) return;

    const interval = setInterval(() => {
      setTimeRemaining(formatTimeRemaining(clarification.timeout_at));
    }, 1000);

    return () => clearInterval(interval);
  }, [clarification.timeout_at]);

  const severityClass = getSeverityColorClass(clarification.severity);
  const priorityLabel = getPriorityLabel(clarification.priority);

  return (
    <div
      onClick={onClick}
      className={`p-4 rounded-lg border cursor-pointer transition-all hover:ring-2 hover:ring-white/10 ${severityClass}`}
    >
      {/* Header: Description + Priority */}
      <div className="flex justify-between items-start gap-2 mb-2">
        <span className="text-sm font-medium text-white line-clamp-2">
          {clarification.description}
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${
            clarification.priority === 1
              ? 'bg-red-500/20 text-red-400'
              : clarification.priority === 2
              ? 'bg-amber-500/20 text-amber-400'
              : 'bg-blue-500/20 text-blue-400'
          }`}
        >
          {priorityLabel}
        </span>
      </div>

      {/* Detected Term */}
      {clarification.detected_term && (
        <div className="text-xs text-zinc-500 mb-2">
          <span className="font-medium">Term: </span>
          <span className="text-zinc-400 font-mono bg-zinc-800 px-1 rounded">
            {clarification.detected_term}
          </span>
        </div>
      )}

      {/* Requirement Text Preview */}
      <p className="text-xs text-zinc-500 mb-3 line-clamp-2">
        {clarification.requirement_text}
      </p>

      {/* Footer: Options Count + Timeout */}
      <div className="flex justify-between items-center text-xs">
        <span className="text-zinc-400">
          {clarification.interpretations.length} option
          {clarification.interpretations.length !== 1 ? 's' : ''}
        </span>

        {timeRemaining && timeRemaining !== 'expired' && (
          <span className="text-amber-400 flex items-center gap-1">
            {/* Clock Icon */}
            <svg
              className="w-3 h-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            {timeRemaining}
          </span>
        )}

        {timeRemaining === 'expired' && (
          <span className="text-red-400 text-xs">Auto-resolving...</span>
        )}
      </div>

      {/* Recommended Badge */}
      {clarification.interpretations.some((i) => i.is_recommended) && (
        <div className="mt-2 text-xs text-green-400 flex items-center gap-1">
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          Has recommended option
        </div>
      )}
    </div>
  );
};

export default ClarificationCard;
