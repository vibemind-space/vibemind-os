import { useProjectStore } from '../../stores/projectStore'
import { VNCViewer } from './VNCViewer'
import { X, Maximize2, Minimize2, RefreshCw, ExternalLink } from 'lucide-react'
import { useState } from 'react'

export function LivePreview() {
  const { previewProjectId, getProject, setPreviewProject } = useProjectStore()
  const [isFullscreen, setIsFullscreen] = useState(false)

  const project = previewProjectId ? getProject(previewProjectId) : null

  if (!project) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>No preview selected</p>
      </div>
    )
  }

  const openInBrowser = () => {
    if (project.appPort) {
      window.open(`http://localhost:${project.appPort}`, '_blank')
    }
  }

  return (
    <div
      className={`flex flex-col bg-engine-dark ${
        isFullscreen ? 'fixed inset-0 z-50' : 'h-full'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
          <span className="text-sm font-medium">{project.name}</span>
          {project.vncPort && (
            <span className="text-xs text-gray-500">VNC:{project.vncPort}</span>
          )}
        </div>

        <div className="flex items-center gap-1">
          {project.appPort && (
            <button
              onClick={openInBrowser}
              className="p-1.5 hover:bg-gray-700 rounded transition"
              title="Open in Browser"
            >
              <ExternalLink className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 hover:bg-gray-700 rounded transition"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={() => setPreviewProject(null)}
            className="p-1.5 hover:bg-gray-700 rounded transition"
            title="Close Preview"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* VNC Viewer */}
      <div className="flex-1 bg-black">
        {project.vncPort ? (
          <VNCViewer port={project.vncPort} projectId={project.id} />
        ) : (
          <div className="h-full flex items-center justify-center text-gray-500">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p>Waiting for VNC connection...</p>
              <p className="text-xs mt-1">Container is starting</p>
            </div>
          </div>
        )}
      </div>

      {/* Status Bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-gray-700 text-xs text-gray-500">
        <span>
          Status: <span className="text-green-400">{project.status}</span>
        </span>
        {project.appPort && (
          <span>
            App: <span className="text-blue-400">localhost:{project.appPort}</span>
          </span>
        )}
      </div>
    </div>
  )
}
