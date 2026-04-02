import { Star } from 'lucide-react'

interface StarRatingProps {
  rating: number
  maxRating?: number
  size?: 'sm' | 'md' | 'lg'
  interactive?: boolean
  onChange?: (rating: number) => void
  showValue?: boolean
  className?: string
}

const sizeClasses = {
  sm: 'w-3 h-3',
  md: 'w-4 h-4',
  lg: 'w-5 h-5',
}

export function StarRating({
  rating,
  maxRating = 5,
  size = 'md',
  interactive = false,
  onChange,
  showValue = false,
  className = '',
}: StarRatingProps) {
  const handleClick = (value: number) => {
    if (interactive && onChange) {
      onChange(value)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent, value: number) => {
    if (interactive && onChange && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault()
      onChange(value)
    }
  }

  return (
    <div className={`flex items-center gap-0.5 ${className}`}>
      {Array.from({ length: maxRating }, (_, i) => {
        const value = i + 1
        const filled = value <= rating
        const halfFilled = !filled && value - 0.5 <= rating

        return (
          <button
            key={i}
            type="button"
            disabled={!interactive}
            onClick={() => handleClick(value)}
            onKeyDown={(e) => handleKeyDown(e, value)}
            className={`
              relative
              ${interactive ? 'cursor-pointer hover:scale-110 transition-transform' : 'cursor-default'}
              ${interactive ? 'focus:outline-none focus:ring-2 focus:ring-engine-primary focus:ring-offset-1 focus:ring-offset-engine-dark rounded' : ''}
            `}
            aria-label={interactive ? `Rate ${value} out of ${maxRating}` : undefined}
          >
            {/* Background star (empty) */}
            <Star
              className={`${sizeClasses[size]} text-gray-600`}
              fill="none"
              strokeWidth={1.5}
            />

            {/* Foreground star (filled or half-filled) */}
            {(filled || halfFilled) && (
              <Star
                className={`
                  ${sizeClasses[size]}
                  text-yellow-400
                  absolute top-0 left-0
                  ${halfFilled ? 'clip-path-half' : ''}
                `}
                fill="currentColor"
                strokeWidth={1.5}
                style={halfFilled ? { clipPath: 'inset(0 50% 0 0)' } : undefined}
              />
            )}
          </button>
        )
      })}

      {showValue && (
        <span className="ml-1.5 text-sm text-gray-400">
          {rating.toFixed(1)}
        </span>
      )}
    </div>
  )
}

// Compact display component for showing rating with count
interface RatingDisplayProps {
  rating: number
  reviewCount: number
  size?: 'sm' | 'md'
  className?: string
}

export function RatingDisplay({
  rating,
  reviewCount,
  size = 'sm',
  className = '',
}: RatingDisplayProps) {
  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <StarRating rating={rating} size={size} />
      <span className="text-sm text-gray-400">
        {rating.toFixed(1)} ({reviewCount.toLocaleString()})
      </span>
    </div>
  )
}
