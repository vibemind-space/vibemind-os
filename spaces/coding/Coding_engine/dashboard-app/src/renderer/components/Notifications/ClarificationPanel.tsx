/**
 * ClarificationPanel - Slide-out panel listing all pending clarifications.
 *
 * Appears from the right side when the badge is clicked.
 * Shows all pending clarifications sorted by priority.
 * Provides "Use Defaults" button to auto-resolve all.
 */

import React from 'react';
import { QueuedClarification, ClarificationStatistics } from '../../api/clarificationAPI';
import { ClarificationCard } from './ClarificationCard';

interface ClarificationPanelProps {
  isOpen: boolean;
  isLoading?: boolean;
  clarifications: QueuedClarification[];
  statistics?: ClarificationStatistics | null;
  onClose: () => void;
  onSelect: (id: string) => void;
  onResolveAll: () => void;
  onRefresh?: () => void;
}

export const ClarificationPanel: React.FC<ClarificationPanelProps> = ({
  isOpen,
  isLoading = false,
  clarifications,
  statistics,
  onClose,
  onSelect,
  onResolveAll,
  onRefresh,
}) => {
  // Sort by priority (1 = high first)
  const sortedClarifications = [...clarifications].sort(
    (a, b) => a.priority - b.priority
  );

  const hasRecommended = clarifications.some((c) =>
    c.interpretations.some((i) => i.is_recommended)
  );

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40"
          onClick={onClose}
        />
      )}

      {/* Slide-out Panel */}
      <div
        className={`fixed right-0 top-0 h-full w-96 bg-zinc-900 shadow-2xl border-l border-zinc-700 z-50 transform transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="p-4 border-b border-zinc-700 flex justify-between items-center">
          <div>
            <h2 className="text-lg font-semibold text-white">
              Clarifications Needed
            </h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              {clarifications.length} pending
              {statistics?.auto_resolved
                ? ` (${statistics.auto_resolved} auto-resolved)`
                : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={isLoading}
                className="p-1.5 text-zinc-400 hover:text-white transition-colors rounded-lg hover:bg-zinc-800"
                title="Refresh"
              >
                <svg
                  className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-white transition-colors rounded-lg hover:bg-zinc-800"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Statistics Bar */}
        {statistics && (
          <div className="px-4 py-2 bg-zinc-800/50 border-b border-zinc-700 flex gap-4 text-xs">
            <span className="text-zinc-400">
              <span className="text-red-400 font-medium">
                {statistics.by_priority.high}
              </span>{' '}
              high
            </span>
            <span className="text-zinc-400">
              <span className="text-amber-400 font-medium">
                {statistics.by_priority.medium}
              </span>{' '}
              medium
            </span>
            <span className="text-zinc-400">
              <span className="text-blue-400 font-medium">
                {statistics.by_priority.low}
              </span>{' '}
              low
            </span>
          </div>
        )}

        {/* Content Area */}
        <div className="p-4 space-y-3 overflow-y-auto h-[calc(100%-12rem)]">
          {sortedClarifications.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <svg
                className="w-12 h-12 mx-auto mb-3 text-zinc-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <p>All clarifications resolved!</p>
            </div>
          ) : (
            sortedClarifications.map((clar) => (
              <ClarificationCard
                key={clar.id}
                clarification={clar}
                onClick={() => onSelect(clar.id)}
              />
            ))
          )}
        </div>

        {/* Footer Actions */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-zinc-700 bg-zinc-900">
          {clarifications.length > 0 && (
            <button
              onClick={onResolveAll}
              disabled={isLoading || !hasRecommended}
              className={`w-full py-3 rounded-lg font-medium transition-all ${
                hasRecommended && !isLoading
                  ? 'bg-blue-600 hover:bg-blue-700 text-white'
                  : 'bg-zinc-700 text-zinc-500 cursor-not-allowed'
              }`}
              title={
                hasRecommended
                  ? 'Resolve all with recommended defaults'
                  : 'No recommended options available'
              }
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Resolving...
                </span>
              ) : (
                'Use Defaults for All'
              )}
            </button>
          )}
          {clarifications.length > 0 && (
            <p className="text-xs text-zinc-500 text-center mt-2">
              Click a card to review and choose an interpretation
            </p>
          )}
        </div>
      </div>
    </>
  );
};

export default ClarificationPanel;
