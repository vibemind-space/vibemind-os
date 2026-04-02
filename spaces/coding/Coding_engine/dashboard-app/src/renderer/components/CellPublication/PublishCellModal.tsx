import { useState, useRef } from 'react'
import { X, Upload, Loader2, Image as ImageIcon, Plus, Trash2 } from 'lucide-react'
import { useTenantStore } from '../../stores/tenantStore'
import { publicationAPI } from '../../api/portalAPI'
import type { PublishCellRequest, CellVisibility } from '../../types/portal'

interface PublishCellModalProps {
  onClose: () => void
  onSuccess?: () => void
}

const CATEGORIES = [
  'API',
  'Authentication',
  'Database',
  'DevOps',
  'Frontend',
  'Backend',
  'Analytics',
  'AI/ML',
  'Communication',
  'Storage',
  'Security',
  'Utility',
]

const LICENSES = [
  'MIT',
  'Apache-2.0',
  'GPL-3.0',
  'BSD-3-Clause',
  'ISC',
  'Proprietary',
]

export function PublishCellModal({ onClose, onSuccess }: PublishCellModalProps) {
  const { activeTenantId } = useTenantStore()

  const [formData, setFormData] = useState<Partial<PublishCellRequest>>({
    visibility: 'public',
    tags: [],
    techStack: [],
    license: 'MIT',
  })
  const [iconPreview, setIconPreview] = useState<string | null>(null)
  const [screenshotPreviews, setScreenshotPreviews] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [techInput, setTechInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const iconInputRef = useRef<HTMLInputElement>(null)
  const screenshotInputRef = useRef<HTMLInputElement>(null)

  const updateField = <K extends keyof PublishCellRequest>(
    field: K,
    value: PublishCellRequest[K]
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  const handleIconChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      updateField('iconFile', file)
      setIconPreview(URL.createObjectURL(file))
    }
  }

  const handleScreenshotsChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length) {
      const current = formData.screenshotFiles || []
      const newFiles = [...current, ...files].slice(0, 5) // Max 5 screenshots
      updateField('screenshotFiles', newFiles)
      setScreenshotPreviews(newFiles.map((f) => URL.createObjectURL(f)))
    }
  }

  const removeScreenshot = (index: number) => {
    const newFiles = [...(formData.screenshotFiles || [])]
    newFiles.splice(index, 1)
    updateField('screenshotFiles', newFiles)

    const newPreviews = [...screenshotPreviews]
    URL.revokeObjectURL(newPreviews[index])
    newPreviews.splice(index, 1)
    setScreenshotPreviews(newPreviews)
  }

  const addTag = () => {
    const tag = tagInput.trim().toLowerCase()
    if (tag && !formData.tags?.includes(tag)) {
      updateField('tags', [...(formData.tags || []), tag])
    }
    setTagInput('')
  }

  const removeTag = (tag: string) => {
    updateField('tags', formData.tags?.filter((t) => t !== tag) || [])
  }

  const addTech = () => {
    const tech = techInput.trim()
    if (tech && !formData.techStack?.includes(tech)) {
      updateField('techStack', [...(formData.techStack || []), tech])
    }
    setTechInput('')
  }

  const removeTech = (tech: string) => {
    updateField('techStack', formData.techStack?.filter((t) => t !== tech) || [])
  }

  const isValid =
    formData.name &&
    formData.displayName &&
    formData.description &&
    formData.category &&
    formData.license

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isValid || !activeTenantId) return

    setSubmitting(true)
    setError(null)

    try {
      await publicationAPI.publishCell(formData as PublishCellRequest, activeTenantId)
      onSuccess?.()
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to publish cell')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-engine-darker rounded-xl border border-gray-700 w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold">Publish New Cell</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-auto p-6 space-y-5">
          {/* Icon & Basic Info */}
          <div className="flex gap-4">
            {/* Icon Upload */}
            <div className="flex-shrink-0">
              <input
                ref={iconInputRef}
                type="file"
                accept="image/*"
                onChange={handleIconChange}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => iconInputRef.current?.click()}
                className="
                  w-20 h-20 rounded-xl
                  bg-engine-dark border border-gray-600 border-dashed
                  flex items-center justify-center
                  hover:border-gray-500
                  transition-colors overflow-hidden
                "
              >
                {iconPreview ? (
                  <img
                    src={iconPreview}
                    alt="Icon preview"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <ImageIcon className="w-8 h-8 text-gray-500" />
                )}
              </button>
              <p className="text-xs text-gray-500 mt-1 text-center">Icon</p>
            </div>

            {/* Name & Display Name */}
            <div className="flex-1 space-y-3">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Display Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formData.displayName || ''}
                  onChange={(e) => {
                    updateField('displayName', e.target.value)
                    if (!formData.name) {
                      updateField('name', toSlug(e.target.value))
                    }
                  }}
                  placeholder="My Awesome Cell"
                  className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  URL Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formData.name || ''}
                  onChange={(e) => updateField('name', toSlug(e.target.value))}
                  placeholder="my-awesome-cell"
                  className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
                />
              </div>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Short Description <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={formData.description || ''}
              onChange={(e) => updateField('description', e.target.value)}
              placeholder="A brief description of your cell"
              maxLength={200}
              className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Long Description</label>
            <textarea
              value={formData.longDescription || ''}
              onChange={(e) => updateField('longDescription', e.target.value)}
              placeholder="Detailed description with features, use cases, etc."
              rows={4}
              className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary resize-none"
            />
          </div>

          {/* Category & License */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Category <span className="text-red-400">*</span>
              </label>
              <select
                value={formData.category || ''}
                onChange={(e) => updateField('category', e.target.value)}
                className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
              >
                <option value="">Select category</option>
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">
                License <span className="text-red-400">*</span>
              </label>
              <select
                value={formData.license || ''}
                onChange={(e) => updateField('license', e.target.value)}
                className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
              >
                {LICENSES.map((lic) => (
                  <option key={lic} value={lic}>
                    {lic}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Visibility */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">Visibility</label>
            <div className="flex gap-3">
              {(['public', 'unlisted', 'private'] as CellVisibility[]).map((vis) => (
                <button
                  key={vis}
                  type="button"
                  onClick={() => updateField('visibility', vis)}
                  className={`
                    px-4 py-2 rounded text-sm capitalize
                    ${
                      formData.visibility === vis
                        ? 'bg-engine-primary text-white'
                        : 'bg-engine-dark border border-gray-600 text-gray-400 hover:border-gray-500'
                    }
                    transition-colors
                  `}
                >
                  {vis}
                </button>
              ))}
            </div>
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Tags</label>
            <div className="flex flex-wrap gap-2 mb-2">
              {formData.tags?.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-engine-dark border border-gray-600 rounded text-xs"
                >
                  {tag}
                  <button type="button" onClick={() => removeTag(tag)}>
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
                placeholder="Add tag"
                className="flex-1 px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
              />
              <button
                type="button"
                onClick={addTag}
                className="px-3 py-2 bg-engine-dark border border-gray-600 rounded hover:border-gray-500"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Tech Stack */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Tech Stack</label>
            <div className="flex flex-wrap gap-2 mb-2">
              {formData.techStack?.map((tech) => (
                <span
                  key={tech}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-blue-500/10 text-blue-400 rounded text-xs"
                >
                  {tech}
                  <button type="button" onClick={() => removeTech(tech)}>
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={techInput}
                onChange={(e) => setTechInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTech())}
                placeholder="Add technology"
                className="flex-1 px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
              />
              <button
                type="button"
                onClick={addTech}
                className="px-3 py-2 bg-engine-dark border border-gray-600 rounded hover:border-gray-500"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* URLs */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Repository URL</label>
              <input
                type="url"
                value={formData.repositoryUrl || ''}
                onChange={(e) => updateField('repositoryUrl', e.target.value)}
                placeholder="https://github.com/..."
                className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Documentation URL</label>
              <input
                type="url"
                value={formData.documentationUrl || ''}
                onChange={(e) => updateField('documentationUrl', e.target.value)}
                placeholder="https://docs.example.com"
                className="w-full px-3 py-2 bg-engine-dark border border-gray-600 rounded text-sm focus:outline-none focus:border-engine-primary"
              />
            </div>
          </div>

          {/* Screenshots */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">Screenshots (max 5)</label>
            <input
              ref={screenshotInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleScreenshotsChange}
              className="hidden"
            />
            <div className="flex gap-2 overflow-x-auto pb-2">
              {screenshotPreviews.map((url, i) => (
                <div key={i} className="relative flex-shrink-0">
                  <img
                    src={url}
                    alt={`Screenshot ${i + 1}`}
                    className="h-24 rounded-lg object-cover"
                  />
                  <button
                    type="button"
                    onClick={() => removeScreenshot(i)}
                    className="absolute -top-2 -right-2 p-1 bg-red-500 rounded-full"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
              {screenshotPreviews.length < 5 && (
                <button
                  type="button"
                  onClick={() => screenshotInputRef.current?.click()}
                  className="
                    h-24 w-24 flex-shrink-0
                    bg-engine-dark border border-gray-600 border-dashed
                    rounded-lg flex items-center justify-center
                    hover:border-gray-500 transition-colors
                  "
                >
                  <Plus className="w-6 h-6 text-gray-500" />
                </button>
              )}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400">
              {error}
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || submitting}
            className="
              flex items-center gap-2
              px-4 py-2
              bg-engine-primary hover:bg-blue-600
              rounded font-medium text-sm
              disabled:opacity-50
              transition-colors
            "
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Publishing...
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                Publish Cell
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

function toSlug(str: string): string {
  return str
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}
