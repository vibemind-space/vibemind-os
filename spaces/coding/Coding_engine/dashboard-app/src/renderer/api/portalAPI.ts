/**
 * Portal API - Integration with Portal Backend
 * Handles marketplace cells, tenants, reviews, and moderation
 */

import type {
  PortalCell,
  CellSearchResult,
  CellSearchFilters,
  Tenant,
  TenantMember,
  TenantInvite,
  TenantRole,
  Review,
  ReviewStats,
  ReviewFilters,
  Category,
  InstallRequest,
  InstallResult,
  PublishCellRequest,
  VersionUploadRequest,
  CellReport,
  ReportReason,
} from '../types/portal'

// Detect if running in Electron production mode (file:// protocol)
// In Electron production, use absolute URL since there's no proxy
// In Vite dev mode, use relative URL for proxy to work
function getPortalAPIBase(): string {
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') {
    return 'http://localhost:8000/api/v1/portal'
  }
  return '/api/v1/portal'
}

const PORTAL_API_BASE = getPortalAPIBase()

// ============================================================================
// Helper Functions
// ============================================================================

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`HTTP ${response.status}: ${errorText}`)
  }

  return response.json()
}

async function fetchWithFiles<T>(url: string, formData: FormData): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`HTTP ${response.status}: ${errorText}`)
  }

  return response.json()
}

// ============================================================================
// Marketplace / Cell API
// ============================================================================

export const cellAPI = {
  /**
   * Search marketplace cells
   */
  search: async (filters: CellSearchFilters = {}): Promise<CellSearchResult> => {
    const params = new URLSearchParams()

    if (filters.query) params.set('query', filters.query)
    if (filters.category) params.set('category', filters.category)
    if (filters.tags?.length) params.set('tags', filters.tags.join(','))
    if (filters.techStack?.length) params.set('tech_stack', filters.techStack.join(','))
    if (filters.author) params.set('author', filters.author)
    if (filters.visibility) params.set('visibility', filters.visibility)
    if (filters.status) params.set('status', filters.status)
    if (filters.minRating) params.set('min_rating', String(filters.minRating))
    if (filters.sortBy) params.set('sort_by', filters.sortBy)
    if (filters.sortOrder) params.set('sort_order', filters.sortOrder)
    if (filters.page) params.set('page', String(filters.page))
    if (filters.pageSize) params.set('page_size', String(filters.pageSize))

    return fetchJSON<CellSearchResult>(
      `${PORTAL_API_BASE}/marketplace/search?${params.toString()}`
    )
  },

  /**
   * Get cell by ID
   */
  getById: async (cellId: string): Promise<PortalCell> => {
    return fetchJSON<PortalCell>(`${PORTAL_API_BASE}/cells/${cellId}`)
  },

  /**
   * Get cell by namespace (e.g., "author/cell-name")
   */
  getByNamespace: async (namespace: string): Promise<PortalCell> => {
    return fetchJSON<PortalCell>(`${PORTAL_API_BASE}/cells/ns/${namespace}`)
  },

  /**
   * Install a cell from marketplace into a colony
   */
  install: async (request: InstallRequest): Promise<InstallResult> => {
    return fetchJSON<InstallResult>(`${PORTAL_API_BASE}/cells/${request.cellId}/install`, {
      method: 'POST',
      body: JSON.stringify({
        version: request.version,
        target_namespace: request.targetNamespace,
      }),
    })
  },

  /**
   * Get trending cells
   */
  getTrending: async (limit = 10): Promise<PortalCell[]> => {
    const result = await fetchJSON<CellSearchResult>(
      `${PORTAL_API_BASE}/marketplace/search?sort_by=downloads&page_size=${limit}`
    )
    return result.cells
  },

  /**
   * Get recently published cells
   */
  getRecent: async (limit = 10): Promise<PortalCell[]> => {
    const result = await fetchJSON<CellSearchResult>(
      `${PORTAL_API_BASE}/marketplace/search?sort_by=recent&page_size=${limit}`
    )
    return result.cells
  },

  /**
   * Get top rated cells
   */
  getTopRated: async (limit = 10): Promise<PortalCell[]> => {
    const result = await fetchJSON<CellSearchResult>(
      `${PORTAL_API_BASE}/marketplace/search?sort_by=rating&page_size=${limit}`
    )
    return result.cells
  },

  /**
   * Get cells by category
   */
  getByCategory: async (category: string, limit = 20): Promise<PortalCell[]> => {
    const result = await fetchJSON<CellSearchResult>(
      `${PORTAL_API_BASE}/marketplace/search?category=${category}&page_size=${limit}`
    )
    return result.cells
  },
}

// ============================================================================
// Cell Publication API
// ============================================================================

export const publicationAPI = {
  /**
   * Publish a new cell to the marketplace
   */
  publishCell: async (
    request: PublishCellRequest,
    tenantId: string
  ): Promise<PortalCell> => {
    const formData = new FormData()
    formData.append('name', request.name)
    formData.append('display_name', request.displayName)
    formData.append('description', request.description)
    if (request.longDescription) {
      formData.append('long_description', request.longDescription)
    }
    formData.append('category', request.category)
    formData.append('tags', JSON.stringify(request.tags))
    formData.append('tech_stack', JSON.stringify(request.techStack))
    formData.append('license', request.license)
    formData.append('visibility', request.visibility)
    if (request.repositoryUrl) {
      formData.append('repository_url', request.repositoryUrl)
    }
    if (request.documentationUrl) {
      formData.append('documentation_url', request.documentationUrl)
    }
    if (request.iconFile) {
      formData.append('icon', request.iconFile)
    }
    if (request.screenshotFiles) {
      request.screenshotFiles.forEach((file, index) => {
        formData.append(`screenshot_${index}`, file)
      })
    }

    return fetchWithFiles<PortalCell>(
      `${PORTAL_API_BASE}/cells?tenant_id=${tenantId}`,
      formData
    )
  },

  /**
   * Upload a new version of a cell
   */
  uploadVersion: async (
    cellId: string,
    request: VersionUploadRequest
  ): Promise<{ success: boolean; version: string }> => {
    const formData = new FormData()
    formData.append('version', request.version)
    formData.append('changelog', request.changelog)
    formData.append('artifact', request.artifactFile)

    return fetchWithFiles(`${PORTAL_API_BASE}/cells/${cellId}/versions`, formData)
  },

  /**
   * Update cell metadata
   */
  updateCell: async (
    cellId: string,
    updates: Partial<PublishCellRequest>
  ): Promise<PortalCell> => {
    return fetchJSON<PortalCell>(`${PORTAL_API_BASE}/cells/${cellId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
  },

  /**
   * Delete a cell (owner only)
   */
  deleteCell: async (cellId: string): Promise<{ success: boolean }> => {
    return fetchJSON(`${PORTAL_API_BASE}/cells/${cellId}`, {
      method: 'DELETE',
    })
  },
}

// ============================================================================
// Tenant API
// ============================================================================

export const tenantAPI = {
  /**
   * Get all tenants for current user
   */
  getMyTenants: async (): Promise<Tenant[]> => {
    return fetchJSON<Tenant[]>(`${PORTAL_API_BASE}/tenants`)
  },

  /**
   * Get tenant by ID
   */
  getById: async (tenantId: string): Promise<Tenant> => {
    return fetchJSON<Tenant>(`${PORTAL_API_BASE}/tenants/${tenantId}`)
  },

  /**
   * Create a new tenant
   */
  create: async (data: {
    name: string
    displayName: string
    description?: string
  }): Promise<Tenant> => {
    return fetchJSON<Tenant>(`${PORTAL_API_BASE}/tenants`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  /**
   * Update tenant
   */
  update: async (
    tenantId: string,
    updates: Partial<{ displayName: string; description: string }>
  ): Promise<Tenant> => {
    return fetchJSON<Tenant>(`${PORTAL_API_BASE}/tenants/${tenantId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
  },

  /**
   * Get tenant members
   */
  getMembers: async (tenantId: string): Promise<TenantMember[]> => {
    return fetchJSON<TenantMember[]>(`${PORTAL_API_BASE}/tenants/${tenantId}/members`)
  },

  /**
   * Invite a member
   */
  inviteMember: async (
    tenantId: string,
    email: string,
    role: TenantRole
  ): Promise<TenantInvite> => {
    return fetchJSON<TenantInvite>(`${PORTAL_API_BASE}/tenants/${tenantId}/invites`, {
      method: 'POST',
      body: JSON.stringify({ email, role }),
    })
  },

  /**
   * Update member role
   */
  updateMemberRole: async (
    tenantId: string,
    memberId: string,
    role: TenantRole
  ): Promise<TenantMember> => {
    return fetchJSON<TenantMember>(
      `${PORTAL_API_BASE}/tenants/${tenantId}/members/${memberId}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ role }),
      }
    )
  },

  /**
   * Remove a member
   */
  removeMember: async (
    tenantId: string,
    memberId: string
  ): Promise<{ success: boolean }> => {
    return fetchJSON(`${PORTAL_API_BASE}/tenants/${tenantId}/members/${memberId}`, {
      method: 'DELETE',
    })
  },

  /**
   * Get cells owned by tenant
   */
  getCells: async (tenantId: string): Promise<PortalCell[]> => {
    return fetchJSON<PortalCell[]>(`${PORTAL_API_BASE}/tenants/${tenantId}/cells`)
  },
}

// ============================================================================
// Review API
// ============================================================================

export const reviewAPI = {
  /**
   * Get reviews for a cell
   */
  getForCell: async (
    cellId: string,
    filters: ReviewFilters = {}
  ): Promise<{ reviews: Review[]; stats: ReviewStats }> => {
    const params = new URLSearchParams()
    params.set('cell_id', cellId)

    if (filters.rating) params.set('rating', String(filters.rating))
    if (filters.verified !== undefined) params.set('verified', String(filters.verified))
    if (filters.sortBy) params.set('sort_by', filters.sortBy)
    if (filters.page) params.set('page', String(filters.page))
    if (filters.pageSize) params.set('page_size', String(filters.pageSize))

    return fetchJSON(`${PORTAL_API_BASE}/reviews?${params.toString()}`)
  },

  /**
   * Get review stats for a cell
   */
  getStats: async (cellId: string): Promise<ReviewStats> => {
    return fetchJSON<ReviewStats>(`${PORTAL_API_BASE}/reviews/stats/${cellId}`)
  },

  /**
   * Submit a review
   */
  submit: async (
    cellId: string,
    data: { rating: number; title: string; content: string }
  ): Promise<Review> => {
    return fetchJSON<Review>(`${PORTAL_API_BASE}/reviews`, {
      method: 'POST',
      body: JSON.stringify({ cell_id: cellId, ...data }),
    })
  },

  /**
   * Update a review
   */
  update: async (
    reviewId: string,
    data: { rating?: number; title?: string; content?: string }
  ): Promise<Review> => {
    return fetchJSON<Review>(`${PORTAL_API_BASE}/reviews/${reviewId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  },

  /**
   * Delete a review
   */
  delete: async (reviewId: string): Promise<{ success: boolean }> => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews/${reviewId}`, {
      method: 'DELETE',
    })
  },

  /**
   * Vote on a review (helpful/not helpful)
   */
  vote: async (
    reviewId: string,
    vote: 'helpful' | 'not_helpful'
  ): Promise<{ helpful: number; notHelpful: number }> => {
    return fetchJSON(`${PORTAL_API_BASE}/reviews/${reviewId}/vote`, {
      method: 'POST',
      body: JSON.stringify({ vote }),
    })
  },

  /**
   * Author response to a review
   */
  respond: async (reviewId: string, content: string): Promise<Review> => {
    return fetchJSON<Review>(`${PORTAL_API_BASE}/reviews/${reviewId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
  },
}

// ============================================================================
// Category API
// ============================================================================

export const categoryAPI = {
  /**
   * Get all categories
   */
  getAll: async (): Promise<Category[]> => {
    return fetchJSON<Category[]>(`${PORTAL_API_BASE}/categories`)
  },

  /**
   * Get category by ID
   */
  getById: async (categoryId: string): Promise<Category> => {
    return fetchJSON<Category>(`${PORTAL_API_BASE}/categories/${categoryId}`)
  },
}

// ============================================================================
// Moderation API
// ============================================================================

export const moderationAPI = {
  /**
   * Submit a report for a cell
   */
  reportCell: async (
    cellId: string,
    reason: ReportReason,
    description: string
  ): Promise<CellReport> => {
    return fetchJSON<CellReport>(`${PORTAL_API_BASE}/moderation/reports`, {
      method: 'POST',
      body: JSON.stringify({
        cell_id: cellId,
        reason,
        description,
      }),
    })
  },

  /**
   * Get reports submitted by current user
   */
  getMyReports: async (): Promise<CellReport[]> => {
    return fetchJSON<CellReport[]>(`${PORTAL_API_BASE}/moderation/reports/mine`)
  },
}

// ============================================================================
// Combined Portal API Export
// ============================================================================

export const portalAPI = {
  cells: cellAPI,
  publication: publicationAPI,
  tenants: tenantAPI,
  reviews: reviewAPI,
  categories: categoryAPI,
  moderation: moderationAPI,
}

export default portalAPI
