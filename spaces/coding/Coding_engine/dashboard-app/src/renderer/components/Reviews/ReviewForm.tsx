import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { StarRating } from './StarRating'

interface ReviewFormProps {
  cellId: string
  onSubmit: (data: { rating: number; title: string; content: string }) => Promise<void>
  onCancel?: () => void
  className?: string
}

export function ReviewForm({ cellId, onSubmit, onCancel, className = '' }: ReviewFormProps) {
  const [rating, setRating] = useState(0)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isValid = rating > 0 && title.trim().length >= 5 && content.trim().length >= 20

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!isValid) return

    setSubmitting(true)
    setError(null)

    try {
      await onSubmit({
        rating,
        title: title.trim(),
        content: content.trim(),
      })

      // Reset form on success
      setRating(0)
      setTitle('')
      setContent('')
    } catch (err: any) {
      setError(err.message || 'Failed to submit review')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={`bg-engine-dark rounded-lg border border-gray-700 p-4 ${className}`}
    >
      <h3 className="font-medium mb-4">Write a Review</h3>

      {/* Rating */}
      <div className="mb-4">
        <label className="block text-sm text-gray-400 mb-2">
          Your Rating <span className="text-red-400">*</span>
        </label>
        <StarRating
          rating={rating}
          size="lg"
          interactive
          onChange={setRating}
        />
        {rating === 0 && (
          <p className="text-xs text-gray-500 mt-1">Click to rate</p>
        )}
      </div>

      {/* Title */}
      <div className="mb-4">
        <label htmlFor="review-title" className="block text-sm text-gray-400 mb-2">
          Title <span className="text-red-400">*</span>
        </label>
        <input
          id="review-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Summarize your experience"
          maxLength={100}
          className="
            w-full
            px-3 py-2
            bg-engine-darker
            border border-gray-600
            rounded
            text-sm
            placeholder-gray-500
            focus:outline-none
            focus:border-engine-primary
          "
        />
        <p className="text-xs text-gray-500 mt-1">
          {title.length}/100 characters (min 5)
        </p>
      </div>

      {/* Content */}
      <div className="mb-4">
        <label htmlFor="review-content" className="block text-sm text-gray-400 mb-2">
          Review <span className="text-red-400">*</span>
        </label>
        <textarea
          id="review-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Share your experience with this cell. What worked well? What could be improved?"
          rows={5}
          maxLength={2000}
          className="
            w-full
            px-3 py-2
            bg-engine-darker
            border border-gray-600
            rounded
            text-sm
            placeholder-gray-500
            resize-none
            focus:outline-none
            focus:border-engine-primary
          "
        />
        <p className="text-xs text-gray-500 mt-1">
          {content.length}/2000 characters (min 20)
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-3">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="
              px-4 py-2
              text-sm
              text-gray-400
              hover:text-white
              transition-colors
              disabled:opacity-50
            "
          >
            Cancel
          </button>
        )}

        <button
          type="submit"
          disabled={!isValid || submitting}
          className="
            flex items-center gap-2
            px-4 py-2
            bg-engine-primary
            hover:bg-blue-600
            rounded
            text-sm
            font-medium
            transition-colors
            disabled:opacity-50
            disabled:cursor-not-allowed
          "
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Submitting...
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              Submit Review
            </>
          )}
        </button>
      </div>

      {/* Guidelines */}
      <div className="mt-4 pt-4 border-t border-gray-700">
        <h4 className="text-xs text-gray-500 mb-2">Review Guidelines</h4>
        <ul className="text-xs text-gray-600 space-y-1">
          <li>Be specific about what you liked or disliked</li>
          <li>Mention the version you used</li>
          <li>Keep it constructive and helpful for others</li>
          <li>Avoid personal attacks or inappropriate content</li>
        </ul>
      </div>
    </form>
  )
}
