import { Download, Star, GitFork, ExternalLink, Box, Shield } from 'lucide-react'
import type { PortalCell } from '../../types/portal'
import { RatingDisplay } from '../Reviews/StarRating'

interface CellCardProps {
  cell: PortalCell
  onClick?: () => void
  onInstall?: () => void
  compact?: boolean
  className?: string
}

export function CellCard({
  cell,
  onClick,
  onInstall,
  compact = false,
  className = '',
}: CellCardProps) {
  const handleInstallClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    onInstall?.()
  }

  return (
    <div
      onClick={onClick}
      className={`
        bg-engine-dark
        rounded-lg
        border border-gray-700
        hover:border-gray-600
        transition-all
        ${onClick ? 'cursor-pointer hover:shadow-lg' : ''}
        ${compact ? 'p-3' : 'p-4'}
        ${className}
      `}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="flex-shrink-0">
          {cell.iconUrl ? (
            <img
              src={cell.iconUrl}
              alt={cell.displayName}
              className={`rounded-lg object-cover ${compact ? 'w-10 h-10' : 'w-12 h-12'}`}
            />
          ) : (
            <div
              className={`
                rounded-lg
                bg-engine-darker
                flex items-center justify-center
                ${compact ? 'w-10 h-10' : 'w-12 h-12'}
              `}
            >
              <Box className={`text-gray-500 ${compact ? 'w-5 h-5' : 'w-6 h-6'}`} />
            </div>
          )}
        </div>

        {/* Title & Author */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3
              className={`
                font-medium text-white truncate
                ${compact ? 'text-sm' : 'text-base'}
              `}
            >
              {cell.displayName}
            </h3>
            {cell.author.verified && (
              <Shield className="w-3.5 h-3.5 text-engine-primary flex-shrink-0" />
            )}
          </div>
          <p className="text-xs text-gray-500 truncate">
            by {cell.author.displayName}
          </p>
        </div>

        {/* Install button */}
        {onInstall && !compact && (
          <button
            onClick={handleInstallClick}
            className="
              flex-shrink-0
              px-3 py-1.5
              bg-engine-primary
              hover:bg-blue-600
              rounded
              text-xs
              font-medium
              transition-colors
            "
          >
            Install
          </button>
        )}
      </div>

      {/* Description */}
      {!compact && (
        <p className="mt-3 text-sm text-gray-400 line-clamp-2">
          {cell.description}
        </p>
      )}

      {/* Tags */}
      {!compact && cell.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {cell.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="
                px-2 py-0.5
                bg-engine-darker
                rounded
                text-xs
                text-gray-400
              "
            >
              {tag}
            </span>
          ))}
          {cell.tags.length > 3 && (
            <span className="text-xs text-gray-500">+{cell.tags.length - 3}</span>
          )}
        </div>
      )}

      {/* Stats */}
      <div className={`flex items-center gap-4 ${compact ? 'mt-2' : 'mt-4'}`}>
        <RatingDisplay
          rating={cell.stats.averageRating}
          reviewCount={cell.stats.reviews}
          size="sm"
        />

        <div className="flex items-center gap-1 text-xs text-gray-500">
          <Download className="w-3 h-3" />
          <span>{formatNumber(cell.stats.downloads)}</span>
        </div>

        {!compact && (
          <>
            <div className="flex items-center gap-1 text-xs text-gray-500">
              <Star className="w-3 h-3" />
              <span>{formatNumber(cell.stats.stars)}</span>
            </div>

            <div className="flex items-center gap-1 text-xs text-gray-500">
              <GitFork className="w-3 h-3" />
              <span>{formatNumber(cell.stats.forks)}</span>
            </div>
          </>
        )}
      </div>

      {/* Tech Stack */}
      {!compact && cell.techStack.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <div className="flex flex-wrap gap-1.5">
            {cell.techStack.slice(0, 4).map((tech) => (
              <span
                key={tech}
                className="
                  px-2 py-0.5
                  bg-blue-500/10
                  text-blue-400
                  rounded
                  text-xs
                "
              >
                {tech}
              </span>
            ))}
            {cell.techStack.length > 4 && (
              <span className="text-xs text-gray-500">+{cell.techStack.length - 4}</span>
            )}
          </div>
        </div>
      )}

      {/* External links (only on hover for full cards) */}
      {!compact && cell.repositoryUrl && (
        <div className="mt-3 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <a
            href={cell.repositoryUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300"
          >
            <ExternalLink className="w-3 h-3" />
            Repository
          </a>
        </div>
      )}
    </div>
  )
}

// Helper function to format large numbers
function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}
