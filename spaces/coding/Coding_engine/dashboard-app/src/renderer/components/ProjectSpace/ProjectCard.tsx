import { Project } from '../../stores/projectStore'
import {
  Rocket,
  Play,
  Square,
  FolderOpen,
  FileJson,
  Clock,
  AlertCircle,
  Loader2,
  ExternalLink,
  Eye
} from 'lucide-react'

interface ProjectCardProps {
  project: Project
  onStartGeneration: () => void
  onStartPreview: () => void
  onStopPreview: () => void
}

export function ProjectCard({
  project,
  onStartGeneration,
  onStartPreview,
  onStopPreview
}: ProjectCardProps) {
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never'
    return new Date(dateString).toLocaleString()
  }

  const openInExplorer = (path: string) => {
    window.electronAPI.fs.showInExplorer(path)
  }

  const openFolder = (path: string) => {
    window.electronAPI.fs.openFolder(path)
  }

  return (
    <div className="bg-engine-dark rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">{project.name}</h2>
          <p className="text-sm text-gray-400 mt-1">{project.description}</p>
        </div>
        <StatusBadge status={project.status} progress={project.progress} />
      </div>

      {/* Details */}
      <div className="p-4 space-y-4">
        {/* Paths */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider">
              Requirements
            </label>
            <button
              onClick={() => openInExplorer(project.requirementsPath)}
              className="mt-1 flex items-center gap-2 text-sm text-gray-300 hover:text-white transition group"
            >
              <FileJson className="w-4 h-4 text-blue-400" />
              <span className="truncate">{project.requirementsPath}</span>
              <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100" />
            </button>
          </div>
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider">
              Output Directory
            </label>
            <button
              onClick={() => openFolder(project.outputDir)}
              className="mt-1 flex items-center gap-2 text-sm text-gray-300 hover:text-white transition group"
            >
              <FolderOpen className="w-4 h-4 text-yellow-400" />
              <span className="truncate">{project.outputDir}</span>
              <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100" />
            </button>
          </div>
        </div>

        {/* Timestamps */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2 text-gray-400">
            <Clock className="w-4 h-4" />
            <span>Created: {formatDate(project.createdAt)}</span>
          </div>
          <div className="flex items-center gap-2 text-gray-400">
            <Clock className="w-4 h-4" />
            <span>Last Run: {formatDate(project.lastRunAt)}</span>
          </div>
        </div>

        {/* Ports */}
        {(project.vncPort || project.appPort) && (
          <div className="flex gap-4 text-sm">
            {project.vncPort && (
              <div className="px-3 py-1 bg-purple-500/20 text-purple-400 rounded">
                VNC: localhost:{project.vncPort}
              </div>
            )}
            {project.appPort && (
              <div className="px-3 py-1 bg-green-500/20 text-green-400 rounded">
                App: localhost:{project.appPort}
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {project.error && (
          <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-400">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{project.error}</span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="p-4 border-t border-gray-700 flex gap-3">
        {project.status === 'generating' ? (
          <button
            disabled
            className="flex items-center gap-2 px-4 py-2 bg-gray-600 rounded text-sm font-medium cursor-not-allowed"
          >
            <Loader2 className="w-4 h-4 animate-spin" />
            Generating... {project.progress}%
          </button>
        ) : (
          <button
            onClick={onStartGeneration}
            className="flex items-center gap-2 px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition"
          >
            <Rocket className="w-4 h-4" />
            Generate Code
          </button>
        )}

        {project.status === 'running' ? (
          <button
            onClick={onStopPreview}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-sm font-medium transition"
          >
            <Square className="w-4 h-4" />
            Stop Preview
          </button>
        ) : (
          <button
            onClick={onStartPreview}
            disabled={project.status === 'generating'}
            className="flex items-center gap-2 px-4 py-2 bg-engine-secondary hover:bg-emerald-600 rounded text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Eye className="w-4 h-4" />
            Live Preview
          </button>
        )}
      </div>
    </div>
  )
}

function StatusBadge({ status, progress }: { status: Project['status']; progress: number }) {
  const config = {
    idle: { bg: 'bg-gray-500/20', text: 'text-gray-400', label: 'Idle' },
    generating: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: `Generating ${progress}%` },
    running: { bg: 'bg-green-500/20', text: 'text-green-400', label: 'Running' },
    stopped: { bg: 'bg-gray-500/20', text: 'text-gray-400', label: 'Stopped' },
    error: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'Error' }
  }

  const { bg, text, label } = config[status]

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${bg} ${text}`}>
      {label}
    </span>
  )
}
