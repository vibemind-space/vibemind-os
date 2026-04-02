/**
 * ClarificationEditor - Full editor modal for detailed clarification editing.
 *
 * Shows:
 * - Full context of the clarification
 * - All interpretation options with details
 * - Selection controls
 * - Confirm/Cancel actions
 */

import React, { useState, useEffect } from 'react';
import { QueuedClarification, formatTimeRemaining } from '../../api/clarificationAPI';
import { InterpretationOption } from './InterpretationOption';

interface ClarificationEditorProps {
  clarification: QueuedClarification | null;
  isOpen: boolean;
  isLoading?: boolean;
  onClose: () => void;
  onSubmit: (clarificationId: string, interpretationId: string) => void;
}

export const ClarificationEditor: React.FC<ClarificationEditorProps> = ({
  clarification,
  isOpen,
  isLoading = false,
  onClose,
  onSubmit,
}) => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState('');

  // Reset selection when clarification changes
  useEffect(() => {
    if (clarification) {
      // Auto-select recommended option if available
      const recommended = clarification.interpretations.find((i) => i.is_recommended);
      setSelectedId(recommended?.id || null);
    } else {
      setSelectedId(null);
    }
  }, [clarification]);

  // Update time remaining
  useEffect(() => {
    if (!clarification?.timeout_at) return;

    setTimeRemaining(formatTimeRemaining(clarification.timeout_at));

    const interval = setInterval(() => {
      setTimeRemaining(formatTimeRemaining(clarification.timeout_at));
    }, 1000);

    return () => clearInterval(interval);
  }, [clarification?.timeout_at]);

  if (!isOpen || !clarification) return null;

  const handleSubmit = () => {
    if (selectedId) {
      onSubmit(clarification.id, selectedId);
    }
  };

  const selectedInterpretation = clarification.interpretations.find(
    (i) => i.id === selectedId
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-zinc-900 rounded-xl shadow-2xl border border-zinc-700 w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-zinc-700">
          <div className="flex justify-between items-start gap-4">
            <div className="flex-1">
              <h2 className="text-xl font-semibold text-white mb-2">
                {clarification.description}
              </h2>
              <div className="flex items-center gap-3 text-sm">
                <span
                  className={`px-2 py-0.5 rounded-full ${
                    clarification.severity === 'high'
                      ? 'bg-red-500/20 text-red-400'
                      : clarification.severity === 'medium'
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-blue-500/20 text-blue-400'
                  }`}
                >
                  {clarification.severity} severity
                </span>
                {timeRemaining && timeRemaining !== 'expired' && (
                  <span className="text-amber-400 flex items-center gap-1">
                    <svg
                      className="w-4 h-4"
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
                    {timeRemaining} remaining
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-zinc-400 hover:text-white transition-colors p-1"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Requirement Context */}
          <div className="mt-4 p-3 bg-zinc-800 rounded-lg">
            <span className="text-xs text-zinc-500 block mb-1">From requirement:</span>
            <p className="text-sm text-zinc-300">{clarification.requirement_text}</p>
          </div>

          {/* Detected Term */}
          {clarification.detected_term && (
            <div className="mt-3 text-sm text-zinc-400">
              <span className="font-medium">Detected term: </span>
              <code className="bg-zinc-800 px-2 py-0.5 rounded text-amber-400">
                {clarification.detected_term}
              </code>
            </div>
          )}
        </div>

        {/* Interpretation Options */}
        <div className="flex-1 overflow-y-auto p-6">
          <h3 className="text-sm font-medium text-zinc-300 mb-4">
            Choose an interpretation:
          </h3>
          <div className="space-y-4">
            {clarification.interpretations.map((interp) => (
              <InterpretationOption
                key={interp.id}
                interpretation={interp}
                selected={selectedId === interp.id}
                onSelect={() => setSelectedId(interp.id)}
              />
            ))}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="p-6 border-t border-zinc-700 bg-zinc-900/50">
          <div className="flex justify-between items-center">
            {/* Selection Summary */}
            <div className="text-sm text-zinc-400">
              {selectedInterpretation ? (
                <span>
                  Selected: <strong className="text-white">{selectedInterpretation.label}</strong>
                </span>
              ) : (
                <span className="text-amber-400">Please select an option</span>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-zinc-400 hover:text-white transition-colors"
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={!selectedId || isLoading}
                className={`px-6 py-2 rounded-lg font-medium transition-all ${
                  selectedId && !isLoading
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'bg-zinc-700 text-zinc-500 cursor-not-allowed'
                }`}
              >
                {isLoading ? (
                  <span className="flex items-center gap-2">
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
                    Submitting...
                  </span>
                ) : (
                  'Confirm Selection'
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ClarificationEditor;
