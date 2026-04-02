import { useEffect, useCallback, useRef } from 'react'
import { Loader2, Package, TrendingUp, Clock, Award } from 'lucide-react'
import { usePortalStore } from '../../stores/portalStore'
import { SearchBar } from './SearchBar'
import { FilterPanel } from './FilterPanel'
import { CellCard } from './CellCard'
import type { PortalCell } from '../../types/portal'

interface MarketplaceBrowserProps {
  onCellClick?: (cell: PortalCell) => void
  onCellInstall?: (cell: PortalCell) => void
  className?: string
}

export function MarketplaceBrowser({
  onCellClick,
  onCellInstall,
  className = '',
}: MarketplaceBrowserProps) {
  const {
    searchQuery,
    searchFilters,
    searchResults,
    totalResults,
    hasMore,
    isSearching,
    searchError,
    trendingCells,
    recentCells,
    topRatedCells,
    featuredLoading,
    categories,
    setSearchQuery,
    setSearchFilters,
    search,
    searchNextPage,
    clearSearch,
    loadFeaturedCells,
    loadCategories,
  } = usePortalStore()

  const observerRef = useRef<IntersectionObserver | null>(null)
  const loadMoreRef = useRef<HTMLDivElement>(null)

  // Initial load
  useEffect(() => {
    loadFeaturedCells()
    loadCategories()
  }, [loadFeaturedCells, loadCategories])

  // Infinite scroll
  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect()
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isSearching) {
          searchNextPage()
        }
      },
      { threshold: 0.1 }
    )

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current)
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect()
      }
    }
  }, [hasMore, isSearching, searchNextPage])

  // Search when query or filters change
  const handleSearch = useCallback(() => {
    search()
  }, [search])

  const handleQueryChange = useCallback(
    (query: string) => {
      setSearchQuery(query)
      if (query || Object.keys(searchFilters).length > 0) {
        // Trigger search after debounce
        const timer = setTimeout(() => search(), 300)
        return () => clearTimeout(timer)
      }
    },
    [setSearchQuery, search, searchFilters]
  )

  const isSearchMode = searchQuery || Object.keys(searchFilters).length > 0

  return (
    <div className={`flex gap-6 ${className}`}>
      {/* Sidebar - Filters */}
      <aside className="w-64 flex-shrink-0">
        <FilterPanel
          categories={categories}
          filters={searchFilters}
          onFiltersChange={(filters) => {
            setSearchFilters(filters)
            search()
          }}
          onClear={clearSearch}
        />
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0">
        {/* Search Bar */}
        <div className="mb-6">
          <SearchBar
            value={searchQuery}
            onChange={handleQueryChange}
            onSearch={handleSearch}
            placeholder="Search for cells, features, or tech stack..."
            className="max-w-xl"
          />
        </div>

        {/* Content */}
        {isSearchMode ? (
          // Search Results
          <div>
            {/* Results header */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium">
                {totalResults > 0
                  ? `${totalResults.toLocaleString()} results`
                  : 'No results found'}
              </h2>
              {isSearching && (
                <Loader2 className="w-5 h-5 text-engine-primary animate-spin" />
              )}
            </div>

            {/* Error */}
            {searchError && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 mb-4">
                {searchError}
              </div>
            )}

            {/* Results grid */}
            {searchResults.length > 0 ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {searchResults.map((cell) => (
                  <CellCard
                    key={cell.id}
                    cell={cell}
                    onClick={() => onCellClick?.(cell)}
                    onInstall={() => onCellInstall?.(cell)}
                  />
                ))}
              </div>
            ) : (
              !isSearching && (
                <EmptyState
                  icon={<Package className="w-12 h-12" />}
                  title="No cells found"
                  description="Try adjusting your search or filters"
                />
              )
            )}

            {/* Load more trigger */}
            {hasMore && (
              <div ref={loadMoreRef} className="flex justify-center py-8">
                {isSearching && (
                  <Loader2 className="w-6 h-6 text-engine-primary animate-spin" />
                )}
              </div>
            )}
          </div>
        ) : (
          // Featured Sections
          <div className="space-y-10">
            {/* Trending */}
            <CellSection
              icon={<TrendingUp className="w-5 h-5 text-orange-400" />}
              title="Trending"
              cells={trendingCells}
              loading={featuredLoading}
              onCellClick={onCellClick}
              onCellInstall={onCellInstall}
            />

            {/* Top Rated */}
            <CellSection
              icon={<Award className="w-5 h-5 text-yellow-400" />}
              title="Top Rated"
              cells={topRatedCells}
              loading={featuredLoading}
              onCellClick={onCellClick}
              onCellInstall={onCellInstall}
            />

            {/* Recently Added */}
            <CellSection
              icon={<Clock className="w-5 h-5 text-blue-400" />}
              title="Recently Added"
              cells={recentCells}
              loading={featuredLoading}
              onCellClick={onCellClick}
              onCellInstall={onCellInstall}
            />
          </div>
        )}
      </main>
    </div>
  )
}

// Featured section component
interface CellSectionProps {
  icon: React.ReactNode
  title: string
  cells: PortalCell[]
  loading: boolean
  onCellClick?: (cell: PortalCell) => void
  onCellInstall?: (cell: PortalCell) => void
}

function CellSection({
  icon,
  title,
  cells,
  loading,
  onCellClick,
  onCellInstall,
}: CellSectionProps) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-4">
        {icon}
        <h2 className="text-lg font-medium">{title}</h2>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CellCardSkeleton key={i} />
          ))}
        </div>
      ) : cells.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {cells.map((cell) => (
            <CellCard
              key={cell.id}
              cell={cell}
              onClick={() => onCellClick?.(cell)}
              onInstall={() => onCellInstall?.(cell)}
              compact
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Package className="w-8 h-8" />}
          title="No cells available"
          description="Check back later for new cells"
          compact
        />
      )}
    </section>
  )
}

// Loading skeleton
function CellCardSkeleton() {
  return (
    <div className="bg-engine-dark rounded-lg border border-gray-700 p-3 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-gray-700 rounded-lg" />
        <div className="flex-1">
          <div className="h-4 bg-gray-700 rounded w-3/4 mb-2" />
          <div className="h-3 bg-gray-700 rounded w-1/2" />
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <div className="h-4 bg-gray-700 rounded w-16" />
        <div className="h-4 bg-gray-700 rounded w-12" />
      </div>
    </div>
  )
}

// Empty state component
interface EmptyStateProps {
  icon: React.ReactNode
  title: string
  description: string
  compact?: boolean
}

function EmptyState({ icon, title, description, compact = false }: EmptyStateProps) {
  return (
    <div
      className={`
        flex flex-col items-center justify-center text-center text-gray-500
        ${compact ? 'py-8' : 'py-16'}
      `}
    >
      <div className="mb-3 text-gray-600">{icon}</div>
      <h3 className={`font-medium ${compact ? 'text-sm' : 'text-lg'}`}>{title}</h3>
      <p className={`${compact ? 'text-xs' : 'text-sm'} mt-1`}>{description}</p>
    </div>
  )
}
