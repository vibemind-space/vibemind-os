/**
 * Portal TypeScript Interfaces
 * Types for marketplace cells, tenants, reviews, and related entities
 */

// ============================================================================
// Cell Types
// ============================================================================

export type CellVisibility = 'public' | 'private' | 'unlisted'
export type CellStatus = 'draft' | 'published' | 'quarantined' | 'deprecated'
export type ValidationStatus = 'pending' | 'passed' | 'failed' | 'skipped'

export interface CellAuthor {
  id: string
  username: string
  displayName: string
  avatarUrl?: string
  verified: boolean
}

export interface CellVersion {
  version: string
  changelog?: string
  releaseDate: string
  downloadUrl: string
  validationStatus: ValidationStatus
  securityScore: number
  downloadCount: number
}

export interface CellStats {
  downloads: number
  installs: number
  stars: number
  forks: number
  reviews: number
  averageRating: number
}

export interface CellDependency {
  cellId: string
  cellName: string
  versionConstraint: string
  optional: boolean
}

export interface PortalCell {
  id: string
  namespace: string
  name: string
  displayName: string
  description: string
  longDescription?: string
  category: string
  tags: string[]
  visibility: CellVisibility
  status: CellStatus
  author: CellAuthor
  currentVersion: string
  versions: CellVersion[]
  stats: CellStats
  dependencies: CellDependency[]
  techStack: string[]
  license: string
  repositoryUrl?: string
  documentationUrl?: string
  iconUrl?: string
  screenshotUrls: string[]
  createdAt: string
  updatedAt: string
  publishedAt?: string
}

export interface CellSearchResult {
  cells: PortalCell[]
  total: number
  page: number
  pageSize: number
  hasMore: boolean
}

export interface CellSearchFilters {
  query?: string
  category?: string
  tags?: string[]
  techStack?: string[]
  author?: string
  visibility?: CellVisibility
  status?: CellStatus
  minRating?: number
  sortBy?: 'relevance' | 'downloads' | 'rating' | 'recent' | 'name'
  sortOrder?: 'asc' | 'desc'
  page?: number
  pageSize?: number
}

// ============================================================================
// Tenant Types
// ============================================================================

export type TenantRole = 'owner' | 'admin' | 'developer' | 'viewer'
export type TenantStatus = 'active' | 'suspended' | 'pending'

export interface TenantMember {
  id: string
  userId: string
  username: string
  displayName: string
  avatarUrl?: string
  email: string
  role: TenantRole
  joinedAt: string
  lastActiveAt?: string
}

export interface TenantQuota {
  maxCells: number
  maxVersionsPerCell: number
  maxStorageBytes: number
  usedStorageBytes: number
  maxMembers: number
}

export interface Tenant {
  id: string
  name: string
  displayName: string
  description?: string
  logoUrl?: string
  status: TenantStatus
  members: TenantMember[]
  quota: TenantQuota
  cellCount: number
  createdAt: string
  updatedAt: string
}

export interface TenantInvite {
  id: string
  tenantId: string
  email: string
  role: TenantRole
  invitedBy: string
  expiresAt: string
  createdAt: string
}

// ============================================================================
// Review Types
// ============================================================================

export interface ReviewAuthor {
  id: string
  username: string
  displayName: string
  avatarUrl?: string
}

export interface Review {
  id: string
  cellId: string
  cellVersion: string
  author: ReviewAuthor
  rating: number // 1-5
  title: string
  content: string
  helpful: number
  notHelpful: number
  userVote?: 'helpful' | 'not_helpful'
  verified: boolean // Verified install
  createdAt: string
  updatedAt?: string
  authorResponse?: {
    content: string
    respondedAt: string
  }
}

export interface ReviewStats {
  totalReviews: number
  averageRating: number
  ratingDistribution: {
    1: number
    2: number
    3: number
    4: number
    5: number
  }
}

export interface ReviewFilters {
  cellId?: string
  rating?: number
  verified?: boolean
  sortBy?: 'recent' | 'rating' | 'helpful'
  page?: number
  pageSize?: number
}

// ============================================================================
// Moderation Types
// ============================================================================

export type ReportReason =
  | 'malware'
  | 'vulnerability'
  | 'spam'
  | 'inappropriate'
  | 'license_violation'
  | 'other'

export type ReportStatus = 'pending' | 'investigating' | 'resolved' | 'dismissed'

export interface CellReport {
  id: string
  cellId: string
  reporterId: string
  reason: ReportReason
  description: string
  status: ReportStatus
  priority: 'low' | 'medium' | 'high' | 'critical'
  resolution?: string
  createdAt: string
  resolvedAt?: string
}

// ============================================================================
// Publication Types
// ============================================================================

export interface PublishCellRequest {
  name: string
  displayName: string
  description: string
  longDescription?: string
  category: string
  tags: string[]
  techStack: string[]
  license: string
  visibility: CellVisibility
  repositoryUrl?: string
  documentationUrl?: string
  iconFile?: File
  screenshotFiles?: File[]
}

export interface VersionUploadRequest {
  version: string
  changelog: string
  artifactFile: File
}

// ============================================================================
// Category Types
// ============================================================================

export interface Category {
  id: string
  name: string
  displayName: string
  description: string
  iconName: string
  cellCount: number
}

// ============================================================================
// Installation Types
// ============================================================================

export interface InstallRequest {
  cellId: string
  version?: string // Defaults to latest
  targetNamespace: string
}

export interface InstallResult {
  success: boolean
  message?: string
  error?: string
  deployedCellId?: string
}
