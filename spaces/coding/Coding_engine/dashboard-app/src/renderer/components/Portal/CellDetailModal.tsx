import { useState, useEffect } from 'react'
import {
  X,
  Download,
  Star,
  GitFork,
  ExternalLink,
  Box,
  Shield,
  ChevronDown,
  Loader2,
  Check,
  AlertTriangle,
  FileText,
  GitBranch,
} from 'lucide-react'
import type { PortalCell } from '../../types/portal'
import { usePortalStore } from '../../stores/portalStore'
import { RatingDisplay, StarRating } from '../Reviews/StarRating'
import { ReviewList } from '../Reviews/ReviewList'
import { ReviewForm } from '../Reviews/ReviewForm'
import { reviewAPI } from '../../api/portalAPI'

interface CellDetailModalProps {
  cell: PortalCell
  onClose: () => void
  onInstall?: (cell: PortalCell, version?: string) => void
}

type TabType = 'overview' | 'versions' | 'reviews' | 'dependencies'

export function CellDetailModal({ cell, onClose, onInstall }: CellDetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [selectedVersion, setSelectedVersion] = useState(cell.currentVersion)
  const [installing, setInstalling] = useState(false)
  const [installResult, setInstallResult] = useState<{
    success: boolean
    message?: string
  } | null>(null)

  const {
    selectedCellReviews,
    selectedCellReviewStats,
    loadCellReviews,
    installCell,
  } = usePortalStore()

  // Load reviews when switching to reviews tab
  useEffect(() => {
    if (activeTab === 'reviews') {
      loadCellReviews(cell.id)
    }
  }, [activeTab, cell.id, loadCellReviews])

  // Close on escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [onClose])

  const handleInstall = async () => {
    setInstalling(true)
    setInstallResult(null)

    try {
      const result = await installCell(cell.id, selectedVersion)
      setInstallResult(result)
      onInstall?.(cell, selectedVersion)
    } catch (error: any) {
      setInstallResult({ success: false, message: error.message })
    } finally {
      setInstalling(false)
    }
  }

  const handleReviewSubmit = async (data: { rating: number; title: string; content: string }) => {
    await reviewAPI.submit(cell.id, data)
    loadCellReviews(cell.id)
  }

  const selectedVersionData = cell.versions.find((v) => v.version === selectedVersion)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-engine-darker rounded-xl border border-gray-700 w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start gap-4 p-6 border-b border-gray-700">
          {/* Icon */}
          {cell.iconUrl ? (
            <img
              src={cell.iconUrl}
              alt={cell.displayName}
              className="w-16 h-16 rounded-xl object-cover"
            />
          ) : (
            <div className="w-16 h-16 rounded-xl bg-engine-dark flex items-center justify-center">
              <Box className="w-8 h-8 text-gray-500" />
            </div>
          )}

          {/* Title & Meta */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-semibold">{cell.displayName}</h2>
              {cell.author.verified && (
                <Shield className="w-5 h-5 text-engine-primary" />
              )}
            </div>
            <p className="text-sm text-gray-400 mt-1">
              by {cell.author.displayName} &middot; {cell.namespace}
            </p>
            <div className="flex items-center gap-4 mt-2">
              <RatingDisplay
                rating={cell.stats.averageRating}
                reviewCount={cell.stats.reviews}
              />
              <div className="flex items-center gap-1 text-sm text-gray-500">
                <Download className="w-4 h-4" />
                {cell.stats.downloads.toLocaleString()} downloads
              </div>
            </div>
          </div>

          {/* Install Section */}
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              {/* Version Selector */}
              <div className="relative">
                <select
                  value={selectedVersion}
                  onChange={(e) => setSelectedVersion(e.target.value)}
                  className="
                    appearance-none
                    pl-3 pr-8 py-2
                    bg-engine-dark
                    border border-gray-600
                    rounded
                    text-sm
                    focus:outline-none
                    focus:border-engine-primary
                  "
                >
                  {cell.versions.map((v) => (
                    <option key={v.version} value={v.version}>
                      v{v.version}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>

              {/* Install Button */}
              <button
                onClick={handleInstall}
                disabled={installing}
                className="
                  flex items-center gap-2
                  px-4 py-2
                  bg-engine-primary
                  hover:bg-blue-600
                  rounded
                  font-medium
                  transition-colors
                  disabled:opacity-50
                "
              >
                {installing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
                Install
              </button>
            </div>

            {/* Install Result */}
            {installResult && (
              <div
                className={`text-xs flex items-center gap-1 ${
                  installResult.success ? 'text-green-400' : 'text-red-400'
                }`}
              >
                {installResult.success ? (
                  <>
                    <Check className="w-3 h-3" />
                    Installed successfully
                  </>
                ) : (
                  <>
                    <AlertTriangle className="w-3 h-3" />
                    {installResult.message || 'Install failed'}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Close Button */}
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          {(['overview', 'versions', 'reviews', 'dependencies'] as TabType[]).map(
            (tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`
                  px-4 py-3 text-sm font-medium capitalize
                  ${
                    activeTab === tab
                      ? 'text-engine-primary border-b-2 border-engine-primary'
                      : 'text-gray-400 hover:text-white'
                  }
                  transition-colors
                `}
              >
                {tab}
              </button>
            )
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {activeTab === 'overview' && (
            <OverviewTab cell={cell} selectedVersion={selectedVersionData} />
          )}
          {activeTab === 'versions' && <VersionsTab cell={cell} />}
          {activeTab === 'reviews' && (
            <div className="space-y-6">
              <ReviewForm cellId={cell.id} onSubmit={handleReviewSubmit} />
              <ReviewList
                reviews={selectedCellReviews}
                stats={selectedCellReviewStats}
                onLoadMore={() => loadCellReviews(cell.id, 2)}
              />
            </div>
          )}
          {activeTab === 'dependencies' && <DependenciesTab cell={cell} />}
        </div>
      </div>
    </div>
  )
}

// Overview Tab
function OverviewTab({
  cell,
  selectedVersion,
}: {
  cell: PortalCell
  selectedVersion?: PortalCell['versions'][0]
}) {
  return (
    <div className="grid grid-cols-3 gap-6">
      {/* Main Content */}
      <div className="col-span-2 space-y-6">
        {/* Description */}
        <div>
          <h3 className="font-medium mb-2">Description</h3>
          <p className="text-sm text-gray-400 whitespace-pre-line">
            {cell.longDescription || cell.description}
          </p>
        </div>

        {/* Screenshots */}
        {cell.screenshotUrls.length > 0 && (
          <div>
            <h3 className="font-medium mb-2">Screenshots</h3>
            <div className="flex gap-2 overflow-x-auto pb-2">
              {cell.screenshotUrls.map((url, i) => (
                <img
                  key={i}
                  src={url}
                  alt={`Screenshot ${i + 1}`}
                  className="h-40 rounded-lg object-cover"
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Sidebar */}
      <div className="space-y-4">
        {/* Info Card */}
        <div className="bg-engine-dark rounded-lg border border-gray-700 p-4 space-y-3">
          <InfoRow label="Category" value={cell.category} />
          <InfoRow label="License" value={cell.license} />
          <InfoRow label="Version" value={`v${cell.currentVersion}`} />
          <InfoRow
            label="Published"
            value={cell.publishedAt ? formatDate(cell.publishedAt) : 'N/A'}
          />
          <InfoRow label="Updated" value={formatDate(cell.updatedAt)} />

          {selectedVersion && (
            <InfoRow
              label="Security Score"
              value={
                <div className="flex items-center gap-1">
                  <Shield
                    className={`w-4 h-4 ${
                      selectedVersion.securityScore >= 80
                        ? 'text-green-400'
                        : selectedVersion.securityScore >= 60
                        ? 'text-yellow-400'
                        : 'text-red-400'
                    }`}
                  />
                  {selectedVersion.securityScore}/100
                </div>
              }
            />
          )}
        </div>

        {/* Tags */}
        <div className="bg-engine-dark rounded-lg border border-gray-700 p-4">
          <h4 className="text-sm font-medium mb-2">Tags</h4>
          <div className="flex flex-wrap gap-1.5">
            {cell.tags.map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 bg-engine-darker rounded text-xs text-gray-400"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>

        {/* Tech Stack */}
        <div className="bg-engine-dark rounded-lg border border-gray-700 p-4">
          <h4 className="text-sm font-medium mb-2">Tech Stack</h4>
          <div className="flex flex-wrap gap-1.5">
            {cell.techStack.map((tech) => (
              <span
                key={tech}
                className="px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded text-xs"
              >
                {tech}
              </span>
            ))}
          </div>
        </div>

        {/* Links */}
        <div className="bg-engine-dark rounded-lg border border-gray-700 p-4 space-y-2">
          {cell.repositoryUrl && (
            <a
              href={cell.repositoryUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <GitBranch className="w-4 h-4" />
              Repository
              <ExternalLink className="w-3 h-3 ml-auto" />
            </a>
          )}
          {cell.documentationUrl && (
            <a
              href={cell.documentationUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <FileText className="w-4 h-4" />
              Documentation
              <ExternalLink className="w-3 h-3 ml-auto" />
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

// Versions Tab
function VersionsTab({ cell }: { cell: PortalCell }) {
  return (
    <div className="space-y-4">
      {cell.versions.map((version) => (
        <div
          key={version.version}
          className="bg-engine-dark rounded-lg border border-gray-700 p-4"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="font-medium">v{version.version}</span>
              {version.version === cell.currentVersion && (
                <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs">
                  Latest
                </span>
              )}
              <span
                className={`px-2 py-0.5 rounded text-xs ${
                  version.validationStatus === 'passed'
                    ? 'bg-green-500/20 text-green-400'
                    : version.validationStatus === 'failed'
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-gray-500/20 text-gray-400'
                }`}
              >
                {version.validationStatus}
              </span>
            </div>
            <span className="text-sm text-gray-500">{formatDate(version.releaseDate)}</span>
          </div>
          {version.changelog && (
            <p className="text-sm text-gray-400 whitespace-pre-line">
              {version.changelog}
            </p>
          )}
          <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
            <span>{version.downloadCount.toLocaleString()} downloads</span>
            <span>Security: {version.securityScore}/100</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// Dependencies Tab
function DependenciesTab({ cell }: { cell: PortalCell }) {
  if (cell.dependencies.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <Box className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>No dependencies</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {cell.dependencies.map((dep) => (
        <div
          key={dep.cellId}
          className="bg-engine-dark rounded-lg border border-gray-700 p-4 flex items-center justify-between"
        >
          <div>
            <span className="font-medium">{dep.cellName}</span>
            <span className="text-sm text-gray-500 ml-2">{dep.versionConstraint}</span>
          </div>
          {dep.optional && (
            <span className="px-2 py-0.5 bg-gray-500/20 text-gray-400 rounded text-xs">
              optional
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

// Helper components
function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-300">{value}</span>
    </div>
  )
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
