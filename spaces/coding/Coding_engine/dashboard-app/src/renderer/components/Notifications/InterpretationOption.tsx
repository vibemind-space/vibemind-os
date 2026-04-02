/**
 * InterpretationOption - Single interpretation option with full details.
 *
 * Displays an interpretation choice with:
 * - Label and recommended badge
 * - Complexity indicator
 * - Description
 * - Technical approach
 * - Trade-offs
 */

import React from 'react';
import { Interpretation } from '../../api/clarificationAPI';

interface InterpretationOptionProps {
  interpretation: Interpretation;
  selected: boolean;
  onSelect: () => void;
}

export const InterpretationOption: React.FC<InterpretationOptionProps> = ({
  interpretation,
  selected,
  onSelect,
}) => {
  const complexityColors = {
    low: 'bg-green-500/20 text-green-400',
    medium: 'bg-amber-500/20 text-amber-400',
    high: 'bg-red-500/20 text-red-400',
  };

  return (
    <div
      onClick={onSelect}
      className={`p-4 rounded-lg border cursor-pointer transition-all ${
        selected
          ? 'border-blue-500 bg-blue-500/10 ring-2 ring-blue-500/50'
          : 'border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/50'
      }`}
    >
      {/* Header: Label + Badges */}
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-white">{interpretation.label}</span>
          {interpretation.is_recommended && (
            <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full font-medium">
              Recommended
            </span>
          )}
        </div>
        <span
          className={`text-xs px-2 py-1 rounded-full font-medium ${
            complexityColors[interpretation.complexity]
          }`}
        >
          {interpretation.complexity}
        </span>
      </div>

      {/* Description */}
      <p className="text-sm text-zinc-400 mb-3">{interpretation.description}</p>

      {/* Technical Approach */}
      <div className="text-xs text-zinc-500 mb-2">
        <span className="font-medium text-zinc-400">Approach: </span>
        {interpretation.technical_approach}
      </div>

      {/* Trade-offs */}
      {interpretation.trade_offs.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {interpretation.trade_offs.map((tradeoff, i) => (
            <span
              key={i}
              className="text-xs bg-zinc-800 text-zinc-400 px-2 py-1 rounded"
            >
              {tradeoff}
            </span>
          ))}
        </div>
      )}

      {/* Selection Indicator */}
      {selected && (
        <div className="flex items-center gap-1.5 mt-3 text-blue-400 text-sm">
          <svg
            className="w-4 h-4"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          <span>Selected</span>
        </div>
      )}
    </div>
  );
};

export default InterpretationOption;
