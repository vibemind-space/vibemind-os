import { useState } from 'react'
import { useProjectStore } from '../../stores/projectStore'
import { X, FolderOpen, FileJson } from 'lucide-react'

interface CreateProjectModalProps {
  onClose: () => void
}

export function CreateProjectModal({ onClose }: CreateProjectModalProps) {
  const { addProject } = useProjectStore()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [requirementsPath, setRequirementsPath] = useState('')
  const [outputDir, setOutputDir] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!name || !requirementsPath || !outputDir) return

    addProject({
      name,
      description,
      requirementsPath,
      outputDir
    })

    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-engine-dark rounded-lg border border-gray-700 w-full max-w-lg shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold">Create New Project</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Project Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Awesome App"
              className="w-full px-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of the project..."
              rows={2}
              className="w-full px-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition resize-none"
            />
          </div>

          {/* Requirements Path */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Requirements JSON Path *
            </label>
            <div className="relative">
              <FileJson className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="text"
                value={requirementsPath}
                onChange={(e) => setRequirementsPath(e.target.value)}
                placeholder="C:\path\to\requirements.json"
                className="w-full pl-10 pr-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition"
                required
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Path to the JSON file containing project requirements
            </p>
          </div>

          {/* Output Directory */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Output Directory *
            </label>
            <div className="relative">
              <FolderOpen className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="text"
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
                placeholder="C:\path\to\output"
                className="w-full pl-10 pr-3 py-2 bg-engine-darker border border-gray-600 rounded focus:border-engine-primary focus:outline-none transition"
                required
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Directory where generated code will be saved
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition"
            >
              Create Project
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
