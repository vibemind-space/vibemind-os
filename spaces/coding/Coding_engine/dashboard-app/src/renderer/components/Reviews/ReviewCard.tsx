import { useState } from 'react'
import { ThumbsUp, ThumbsDown, Shield, MessageSquare, ChevronDown, ChevronUp } from 'lucide-react'
import { StarRating } from './StarRating'
import type { Review } from '../../types/portal'
import { reviewAPI } from '../../api/portalAPI'

interface ReviewCardProps {
  review: Review
  onVote?: (reviewId: string, vote: 'helpful' | 'not_helpful') => void
  className?: string
}

export function ReviewCard({ review, onVote, className = '' }: ReviewCardProps) {
  const [showResponse, setShowResponse] = useState(false)
  const [voting, setVoting] = useState(false)
  const [localVote, setLocalVote] = useState(review.userVote)
  const [helpfulCount, setHelpfulCount] = useState(review.helpful)
  const [notHelpfulCount, setNotHelpfulCount] = useState(review.notHelpful)

  const handleVote = async (vote: 'helpful' | 'not_helpful') => {
    if (voting || localVote === vote) return

    setVoting(true)
    try {
      const result = await reviewAPI.vote(review.id, vote)
      setHelpfulCount(result.helpful)
      setNotHelpfulCount(result.notHelpful)
      setLocalVote(vote)
      onVote?.(review.id, vote)
    } catch (error) {
      console.error('Failed to vote:', error)
    } finally {
      setVoting(false)
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  }

  return (
    <div className={`bg-engine-dark rounded-lg border border-gray-700 p-4 ${className}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {/* Avatar */}
          {review.author.avatarUrl ? (
            <img
              src={review.author.avatarUrl}
              alt={review.author.displayName}
              className="w-10 h-10 rounded-full object-cover"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-engine-darker flex items-center justify-center text-gray-500 text-sm font-medium">
              {review.author.displayName.charAt(0).toUpperCase()}
            </div>
          )}

          {/* Author & Date */}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{review.author.displayName}</span>
              {review.verified && (
                <span className="flex items-center gap-1 text-xs text-green-400">
                  <Shield className="w-3 h-3" />
                  Verified Install
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <span>{formatDate(review.createdAt)}</span>
              <span>v{review.cellVersion}</span>
            </div>
          </div>
        </div>

        {/* Rating */}
        <StarRating rating={review.rating} size="sm" />
      </div>

      {/* Title */}
      <h4 className="font-medium mb-2">{review.title}</h4>

      {/* Content */}
      <p className="text-sm text-gray-400 whitespace-pre-line">{review.content}</p>

      {/* Author Response */}
      {review.authorResponse && (
        <div className="mt-4">
          <button
            onClick={() => setShowResponse(!showResponse)}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Developer Response
            {showResponse ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>

          {showResponse && (
            <div className="mt-2 pl-4 border-l-2 border-engine-primary">
              <p className="text-sm text-gray-400">{review.authorResponse.content}</p>
              <span className="text-xs text-gray-500 mt-1 block">
                {formatDate(review.authorResponse.respondedAt)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-4 mt-4 pt-3 border-t border-gray-700">
        <span className="text-xs text-gray-500">Was this review helpful?</span>

        <button
          onClick={() => handleVote('helpful')}
          disabled={voting}
          className={`
            flex items-center gap-1 text-xs
            ${localVote === 'helpful' ? 'text-green-400' : 'text-gray-500 hover:text-gray-300'}
            transition-colors disabled:opacity-50
          `}
        >
          <ThumbsUp className="w-3.5 h-3.5" />
          <span>{helpfulCount}</span>
        </button>

        <button
          onClick={() => handleVote('not_helpful')}
          disabled={voting}
          className={`
            flex items-center gap-1 text-xs
            ${localVote === 'not_helpful' ? 'text-red-400' : 'text-gray-500 hover:text-gray-300'}
            transition-colors disabled:opacity-50
          `}
        >
          <ThumbsDown className="w-3.5 h-3.5" />
          <span>{notHelpfulCount}</span>
        </button>
      </div>
    </div>
  )
}
