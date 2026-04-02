import { useState } from 'react'
import { ChevronDown, ChevronUp, X, Filter } from 'lucide-react'
import type { Category, CellSearchFilters } from '../../types/portal'
import { StarRating } from '../Reviews/StarRating'

interface FilterPanelProps {
  categories: Category[]
  filters: CellSearchFilters
  onFiltersChange: (filters: Partial<CellSearchFilters>) => void
  onClear: () => void
  className?: string
}

const SORT_OPTIONS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'downloads', label: 'Most Downloads' },
  { value: 'rating', label: 'Highest Rated' },
  { value: 'recent', label: 'Recently Added' },
  { value: 'name', label: 'Name (A-Z)' },
] as const

const TECH_STACKS = [
  'React',
  'Vue',
  'Angular',
  'Node.js',
  'Python',
  'TypeScript',
  'Go',
  'Rust',
  'Java',
  'Docker',
  'Kubernetes',
  'PostgreSQL',
  'MongoDB',
  'Redis',
  'GraphQL',
]

export function FilterPanel({
  categories,
  filters,
  onFiltersChange,
  onClear,
  className = '',
}: FilterPanelProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['category', 'sort'])
  )

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(section)) {
      newExpanded.delete(section)
    } else {
      newExpanded.add(section)
    }
    setExpandedSections(newExpanded)
  }

  const activeFilterCount = [
    filters.category,
    filters.minRating,
    filters.techStack?.length,
    filters.tags?.length,
  ].filter(Boolean).length

  return (
    <div className={`bg-engine-dark rounded-lg border border-gray-700 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-400" />
          <span className="font-medium">Filters</span>
          {activeFilterCount > 0 && (
            <span className="px-1.5 py-0.5 bg-engine-primary rounded text-xs">
              {activeFilterCount}
            </span>
          )}
        </div>
        {activeFilterCount > 0 && (
          <button
            onClick={onClear}
            className="text-xs text-gray-400 hover:text-white transition-colors"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Sort */}
      <FilterSection
        title="Sort By"
        isExpanded={expandedSections.has('sort')}
        onToggle={() => toggleSection('sort')}
      >
        <select
          value={filters.sortBy || 'relevance'}
          onChange={(e) =>
            onFiltersChange({ sortBy: e.target.value as CellSearchFilters['sortBy'] })
          }
          className="
            w-full
            px-3 py-2
            bg-engine-darker
            border border-gray-600
            rounded
            text-sm
            focus:outline-none
            focus:border-engine-primary
          "
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </FilterSection>

      {/* Categories */}
      <FilterSection
        title="Category"
        isExpanded={expandedSections.has('category')}
        onToggle={() => toggleSection('category')}
      >
        <div className="space-y-1">
          <button
            onClick={() => onFiltersChange({ category: undefined })}
            className={`
              w-full text-left px-2 py-1.5 rounded text-sm
              ${!filters.category ? 'bg-engine-primary/20 text-engine-primary' : 'text-gray-400 hover:text-white hover:bg-gray-700'}
              transition-colors
            `}
          >
            All Categories
          </button>
          {categories.map((category) => (
            <button
              key={category.id}
              onClick={() => onFiltersChange({ category: category.id })}
              className={`
                w-full text-left px-2 py-1.5 rounded text-sm flex items-center justify-between
                ${filters.category === category.id ? 'bg-engine-primary/20 text-engine-primary' : 'text-gray-400 hover:text-white hover:bg-gray-700'}
                transition-colors
              `}
            >
              <span>{category.displayName}</span>
              <span className="text-xs text-gray-500">{category.cellCount}</span>
            </button>
          ))}
        </div>
      </FilterSection>

      {/* Rating */}
      <FilterSection
        title="Minimum Rating"
        isExpanded={expandedSections.has('rating')}
        onToggle={() => toggleSection('rating')}
      >
        <div className="space-y-2">
          {[4, 3, 2, 1].map((rating) => (
            <button
              key={rating}
              onClick={() =>
                onFiltersChange({
                  minRating: filters.minRating === rating ? undefined : rating,
                })
              }
              className={`
                w-full flex items-center gap-2 px-2 py-1.5 rounded
                ${filters.minRating === rating ? 'bg-engine-primary/20' : 'hover:bg-gray-700'}
                transition-colors
              `}
            >
              <StarRating rating={rating} size="sm" />
              <span className="text-sm text-gray-400">& up</span>
            </button>
          ))}
        </div>
      </FilterSection>

      {/* Tech Stack */}
      <FilterSection
        title="Tech Stack"
        isExpanded={expandedSections.has('tech')}
        onToggle={() => toggleSection('tech')}
      >
        <div className="flex flex-wrap gap-1.5">
          {TECH_STACKS.map((tech) => {
            const isSelected = filters.techStack?.includes(tech)
            return (
              <button
                key={tech}
                onClick={() => {
                  const current = filters.techStack || []
                  const updated = isSelected
                    ? current.filter((t) => t !== tech)
                    : [...current, tech]
                  onFiltersChange({ techStack: updated.length ? updated : undefined })
                }}
                className={`
                  px-2 py-1 rounded text-xs
                  ${isSelected ? 'bg-engine-primary text-white' : 'bg-engine-darker text-gray-400 hover:bg-gray-700'}
                  transition-colors
                `}
              >
                {tech}
              </button>
            )
          })}
        </div>
      </FilterSection>

      {/* Active Filters */}
      {activeFilterCount > 0 && (
        <div className="p-4 border-t border-gray-700">
          <div className="text-xs text-gray-500 mb-2">Active Filters</div>
          <div className="flex flex-wrap gap-1.5">
            {filters.category && (
              <FilterTag
                label={categories.find((c) => c.id === filters.category)?.displayName || filters.category}
                onRemove={() => onFiltersChange({ category: undefined })}
              />
            )}
            {filters.minRating && (
              <FilterTag
                label={`${filters.minRating}+ stars`}
                onRemove={() => onFiltersChange({ minRating: undefined })}
              />
            )}
            {filters.techStack?.map((tech) => (
              <FilterTag
                key={tech}
                label={tech}
                onRemove={() =>
                  onFiltersChange({
                    techStack: filters.techStack?.filter((t) => t !== tech),
                  })
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Collapsible section
interface FilterSectionProps {
  title: string
  isExpanded: boolean
  onToggle: () => void
  children: React.ReactNode
}

function FilterSection({ title, isExpanded, onToggle, children }: FilterSectionProps) {
  return (
    <div className="border-b border-gray-700 last:border-b-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 text-sm font-medium hover:bg-gray-800/50 transition-colors"
      >
        {title}
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>
      {isExpanded && <div className="px-4 pb-4">{children}</div>}
    </div>
  )
}

// Filter tag pill
interface FilterTagProps {
  label: string
  onRemove: () => void
}

function FilterTag({ label, onRemove }: FilterTagProps) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 bg-engine-primary/20 text-engine-primary rounded text-xs">
      {label}
      <button
        onClick={onRemove}
        className="hover:text-white transition-colors"
        aria-label={`Remove ${label} filter`}
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  )
}
