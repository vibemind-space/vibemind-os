interface QualityScoreProps {
  completed: number;
  failed: number;
  pending: number;
  total: number;
  size?: 'sm' | 'md' | 'lg';
}

export function QualityScore({ completed, failed, pending, total, size = 'md' }: QualityScoreProps) {
  if (total === 0) return null;

  const completedPct = Math.round((completed / total) * 100);
  const failedPct = Math.round((failed / total) * 100);
  const radius = 15.9;
  const circumference = 2 * Math.PI * radius;

  // SVG dash segments: completed (green), failed (red), pending (gray)
  const completedDash = (completed / total) * 100;
  const failedDash = (failed / total) * 100;

  const sizeMap = { sm: 'w-16 h-16', md: 'w-20 h-20', lg: 'w-28 h-28' };
  const textSize = { sm: 'text-[6px]', md: 'text-[7px]', lg: 'text-[8px]' };
  const subSize = { sm: 'text-[3.5px]', md: 'text-[4px]', lg: 'text-[4.5px]' };

  return (
    <div className="flex flex-col items-center gap-1">
      <svg viewBox="0 0 36 36" className={sizeMap[size]}>
        {/* Background circle */}
        <circle cx="18" cy="18" r={radius} fill="none" stroke="#374151" strokeWidth="3" />

        {/* Pending (gray) - full circle base */}
        <circle
          cx="18" cy="18" r={radius} fill="none"
          stroke="#4b5563" strokeWidth="3"
          strokeDasharray={`${100} 0`}
          strokeDashoffset="25"
          className="transition-all duration-700"
        />

        {/* Failed (red) - on top of pending */}
        {failedDash > 0 && (
          <circle
            cx="18" cy="18" r={radius} fill="none"
            stroke="#ef4444" strokeWidth="3"
            strokeDasharray={`${failedDash} ${100 - failedDash}`}
            strokeDashoffset={25 - completedDash}
            className="transition-all duration-700"
          />
        )}

        {/* Completed (green) - on top */}
        {completedDash > 0 && (
          <circle
            cx="18" cy="18" r={radius} fill="none"
            stroke="#22c55e" strokeWidth="3"
            strokeDasharray={`${completedDash} ${100 - completedDash}`}
            strokeDashoffset="25"
            className="transition-all duration-700"
          />
        )}

        {/* Center text */}
        <text x="18" y="17" textAnchor="middle" className={`${textSize[size]} fill-white font-bold`}>
          {completedPct}%
        </text>
        <text x="18" y="21.5" textAnchor="middle" className={`${subSize[size]} fill-gray-400`}>
          {completed}/{total}
        </text>
      </svg>

      {/* Legend */}
      <div className="flex gap-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          {completed}
        </span>
        {failed > 0 && (
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            {failed}
          </span>
        )}
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-gray-500" />
          {pending}
        </span>
      </div>
    </div>
  );
}
