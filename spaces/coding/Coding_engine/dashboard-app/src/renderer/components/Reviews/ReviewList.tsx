import { useState } from 'react'
import { Loader2, Filter } from 'lucide-react'
import type { Review, ReviewStats } from '../../types/portal'
import { ReviewCard } from './ReviewCard'
import { StarRating } from './StarRating'

interface ReviewListProps {
  reviews: Review[]
  stats: ReviewStats | null
  loading?: boolean
  hasMore?: boolean
  onLoadMore?: () => void
  onVote?: (reviewId: string, vote: 'helpful' | 'not_helpful') => void
  onFilterChange?: (filter: { rating?: number; verified?: boolean }) => void
  className?: string
}

export function ReviewList({
  reviews,
  stats,
  loading = false,
  hasMore = false,
  onLoadMore,
  onVote,
  onFilterChange,
  className = '',
}: ReviewListProps) {
  const [filterRating, setFilterRating] = useState<number | undefined>()
  const [filterVerified, setFilterVerified] = useState(false)

  const handleRatingFilter = (rating: number) => {
    const newRating = filterRating === rating ? undefined : rating
    setFilterRating(newRating)
    onFilterChange?.({ rating: newRating, verified: filterVerified })
  }

  const handleVerifiedFilter = () => {
    const newVerified = !filterVerified
    setFilterVerified(newVerified)
    onFilterChange?.({ rating: filterRating, verified: newVerified })
  }

  return (
    <div className={className}>
      {/* Stats Summary */}
      {stats && (
        <div className="bg-engine-dark rounded-lg border border-gray-700 p-4 mb-6">
          <div className="flex items-start gap-8">
            {/* Overall Rating */}
            <div className="text-center">
              <div className="text-4xl font-bold text-white">
                {stats.averageRating.toFixed(1)}
              </div>
              <StarRating rating={stats.averageRating} size="md" className="mt-1" />
              <div className="text-sm text-gray-500 mt-1">
                {stats.totalReviews.toLocaleString()} reviews
              </div>
            </div>

            {/* Rating Distribution */}
            <div className="flex-1">
              {[5, 4, 3, 2, 1].map((rating) => {
                const count = stats.ratingDistribution[rating as keyof typeof stats.ratingDistribution]
                const percentage = stats.totalReviews > 0
                  ? (count / stats.totalReviews) * 100
                  : 0

                return (
                  <button
                    key={rating}
                    onClick={() => handleRatingFilter(rating)}
                    className={`
                      flex items-center gap-2 w-full py-1 text-left
                      ${filterRating === rating ? 'text-engine-primary' : 'text-gray-400 hover:text-white'}
                      transition-colors
                    `}
                  >
                    <span className="text-xs w-8">{rating} star</span>
                    <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-yellow-400 rounded-full transition-all"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                    <span className="text-xs w-12 text-right">
                      {count.toLocaleString()}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4">
        <Filter className="w-4 h-4 text-gray-500" />
        <span className="text-sm text-gray-500">Filter:</span>

        <button
          onClick={handleVerifiedFilter}
          className={`
            px-2.5 py-1 rounded text-xs
            ${filterVerified ? 'bg-green-500/20 text-green-400' : 'bg-engine-dark border border-gray-600 text-gray-400 hover:border-gray-500'}
            transition-colors
          `}
        >
          Verified Only
        </button>

        {filterRating && (
          <button
            onClick={() => handleRatingFilter(filterRating)}
            className="px-2.5 py-1 bg-engine-primary/20 text-engine-primary rounded text-xs flex items-center gap-1"
          >
            {filterRating} stars
            <span className="ml-1">&times;</span>
          </button>
        )}
      </div>

      {/* Reviews */}
      <div className="space-y-4">
        {reviews.map((review) => (
          <ReviewCard
            key={review.id}
            review={review}
            onVote={onVote}
          />
        ))}
      </div>

      {/* Empty State */}
      {!loading && reviews.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg">No reviews yet</p>
          <p className="text-sm mt-1">Be the first to review this cell</p>
        </div>
      )}

      {/* Load More */}
      {hasMore && (
        <div className="flex justify-center mt-6">
          <button
            onClick={onLoadMore}
            disabled={loading}
            className="
              px-4 py-2
              bg-engine-dark
              border border-gray-600
              rounded-lg
              text-sm
              hover:border-gray-500
              disabled:opacity-50
              transition-colors
            "
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              'Load More Reviews'
            )}
          </button>
        </div>
      )}
    </div>
  )
}
