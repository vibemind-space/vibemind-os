/**
 * ClarificationBadge - Notification badge showing pending clarification count.
 *
 * Displays a bell icon with a badge showing the number of pending clarifications.
 * Clicking opens the ClarificationPanel.
 */

import React from 'react';

interface ClarificationBadgeProps {
  count: number;
  highPriorityCount?: number;
  onClick: () => void;
}

export const ClarificationBadge: React.FC<ClarificationBadgeProps> = ({
  count,
  highPriorityCount = 0,
  onClick,
}) => {
  if (count === 0) return null;

  return (
    <button
      onClick={onClick}
      className="relative p-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 transition-colors"
      title={`${count} clarification${count !== 1 ? 's' : ''} needed`}
    >
      {/* Bell Icon */}
      <svg
        className="w-5 h-5 text-amber-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
        />
      </svg>

      {/* Badge Count */}
      <span
        className={`absolute -top-1 -right-1 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center ${
          highPriorityCount > 0 ? 'bg-red-500' : 'bg-amber-500'
        }`}
      >
        {count > 99 ? '99+' : count}
      </span>

      {/* Pulse animation for high priority */}
      {highPriorityCount > 0 && (
        <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 animate-ping opacity-75" />
      )}
    </button>
  );
};

export default ClarificationBadge;
