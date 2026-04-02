import { create } from 'zustand'
import type {
  PortalCell,
  CellSearchFilters,
  Category,
  Review,
  ReviewStats,
} from '../types/portal'
import { cellAPI, reviewAPI, categoryAPI } from '../api/portalAPI'

// ============================================================================
// Types
// ============================================================================

interface PortalState {
  // Search state
  searchQuery: string
  searchFilters: CellSearchFilters
  searchResults: PortalCell[]
  totalResults: number
  currentPage: number
  pageSize: number
  hasMore: boolean
  isSearching: boolean
  searchError: string | null

  // Featured cells
  trendingCells: PortalCell[]
  recentCells: PortalCell[]
  topRatedCells: PortalCell[]
  featuredLoading: boolean

  // Categories
  categories: Category[]
  categoriesLoading: boolean

  // Selected cell (for detail modal)
  selectedCell: PortalCell | null
  selectedCellReviews: Review[]
  selectedCellReviewStats: ReviewStats | null
  cellDetailLoading: boolean

  // Actions
  setSearchQuery: (query: string) => void
  setSearchFilters: (filters: Partial<CellSearchFilters>) => void
  search: () => Promise<void>
  searchNextPage: () => Promise<void>
  clearSearch: () => void

  loadFeaturedCells: () => Promise<void>
  loadCategories: () => Promise<void>

  selectCell: (cell: PortalCell | null) => void
  loadCellDetail: (cellId: string) => Promise<void>
  loadCellReviews: (cellId: string, page?: number) => Promise<void>

  // Install action
  installCell: (
    cellId: string,
    version?: string,
    targetNamespace?: string
  ) => Promise<{ success: boolean; error?: string }>
}

// ============================================================================
// Store
// ============================================================================

export const usePortalStore = create<PortalState>()((set, get) => ({
  // Initial state
  searchQuery: '',
  searchFilters: {},
  searchResults: [],
  totalResults: 0,
  currentPage: 1,
  pageSize: 20,
  hasMore: false,
  isSearching: false,
  searchError: null,

  trendingCells: [],
  recentCells: [],
  topRatedCells: [],
  featuredLoading: false,

  categories: [],
  categoriesLoading: false,

  selectedCell: null,
  selectedCellReviews: [],
  selectedCellReviewStats: null,
  cellDetailLoading: false,

  // Actions
  setSearchQuery: (query) => {
    set({ searchQuery: query })
  },

  setSearchFilters: (filters) => {
    set((state) => ({
      searchFilters: { ...state.searchFilters, ...filters },
    }))
  },

  search: async () => {
    const { searchQuery, searchFilters, pageSize } = get()

    set({
      isSearching: true,
      searchError: null,
      currentPage: 1,
    })

    try {
      const result = await cellAPI.search({
        ...searchFilters,
        query: searchQuery || undefined,
        page: 1,
        pageSize,
      })

      set({
        searchResults: result.cells,
        totalResults: result.total,
        hasMore: result.hasMore,
        currentPage: result.page,
        isSearching: false,
      })
    } catch (error: any) {
      set({
        searchError: error.message || 'Search failed',
        isSearching: false,
      })
    }
  },

  searchNextPage: async () => {
    const { searchQuery, searchFilters, currentPage, pageSize, hasMore, isSearching } =
      get()

    if (!hasMore || isSearching) return

    set({ isSearching: true })

    try {
      const result = await cellAPI.search({
        ...searchFilters,
        query: searchQuery || undefined,
        page: currentPage + 1,
        pageSize,
      })

      set((state) => ({
        searchResults: [...state.searchResults, ...result.cells],
        totalResults: result.total,
        hasMore: result.hasMore,
        currentPage: result.page,
        isSearching: false,
      }))
    } catch (error: any) {
      set({
        searchError: error.message || 'Failed to load more',
        isSearching: false,
      })
    }
  },

  clearSearch: () => {
    set({
      searchQuery: '',
      searchFilters: {},
      searchResults: [],
      totalResults: 0,
      currentPage: 1,
      hasMore: false,
      searchError: null,
    })
  },

  loadFeaturedCells: async () => {
    set({ featuredLoading: true })

    try {
      const [trending, recent, topRated] = await Promise.all([
        cellAPI.getTrending(8),
        cellAPI.getRecent(8),
        cellAPI.getTopRated(8),
      ])

      set({
        trendingCells: trending,
        recentCells: recent,
        topRatedCells: topRated,
        featuredLoading: false,
      })
    } catch (error) {
      console.error('Failed to load featured cells:', error)
      set({ featuredLoading: false })
    }
  },

  loadCategories: async () => {
    set({ categoriesLoading: true })

    try {
      const categories = await categoryAPI.getAll()
      set({
        categories,
        categoriesLoading: false,
      })
    } catch (error) {
      console.error('Failed to load categories:', error)
      set({ categoriesLoading: false })
    }
  },

  selectCell: (cell) => {
    set({
      selectedCell: cell,
      selectedCellReviews: [],
      selectedCellReviewStats: null,
    })
  },

  loadCellDetail: async (cellId) => {
    set({ cellDetailLoading: true })

    try {
      const [cell, reviewData] = await Promise.all([
        cellAPI.getById(cellId),
        reviewAPI.getForCell(cellId, { pageSize: 10 }),
      ])

      set({
        selectedCell: cell,
        selectedCellReviews: reviewData.reviews,
        selectedCellReviewStats: reviewData.stats,
        cellDetailLoading: false,
      })
    } catch (error) {
      console.error('Failed to load cell detail:', error)
      set({ cellDetailLoading: false })
    }
  },

  loadCellReviews: async (cellId, page = 1) => {
    try {
      const reviewData = await reviewAPI.getForCell(cellId, { page, pageSize: 10 })

      set((state) => ({
        selectedCellReviews:
          page === 1
            ? reviewData.reviews
            : [...state.selectedCellReviews, ...reviewData.reviews],
        selectedCellReviewStats: reviewData.stats,
      }))
    } catch (error) {
      console.error('Failed to load reviews:', error)
    }
  },

  installCell: async (cellId, version, targetNamespace = 'default') => {
    try {
      const result = await cellAPI.install({
        cellId,
        version,
        targetNamespace,
      })

      if (result.success) {
        // Refresh cell stats after install
        const cell = get().selectedCell
        if (cell?.id === cellId) {
          const updated = await cellAPI.getById(cellId)
          set({ selectedCell: updated })
        }
      }

      return result
    } catch (error: any) {
      return { success: false, error: error.message || 'Install failed' }
    }
  },
}))
