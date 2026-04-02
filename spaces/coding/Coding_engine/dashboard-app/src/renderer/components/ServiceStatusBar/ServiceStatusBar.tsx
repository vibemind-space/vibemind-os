/**
 * ServiceStatusBar — Shows the health of backend services:
 *   - FastAPI server (running/starting/error)
 *   - Docker Desktop (running/error)
 *   - Python environment (available/missing)
 *
 * Receives real-time status updates from the Electron main process via IPC.
 * Also provides a manual restart button for FastAPI.
 */

import { useState, useEffect } from 'react'
import {
  Server,
  Container,
  Code2,
  CheckCircle,
  XCircle,
  Loader2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

interface ServiceStatus {
  name: string
  status: 'stopped' | 'starting' | 'running' | 'error'
  url?: string
  pid?: number
  error?: string
  upSince?: string
}

interface AllServiceStatus {
  fastapi: ServiceStatus
  docker: ServiceStatus
  python: ServiceStatus
}

const defaultStatus: AllServiceStatus = {
  fastapi: { name: 'FastAPI', status: 'stopped' },
  docker: { name: 'Docker', status: 'stopped' },
  python: { name: 'Python', status: 'stopped' },
}

export function ServiceStatusBar() {
  const [services, setServices] = useState<AllServiceStatus>(defaultStatus)
  const [expanded, setExpanded] = useState(false)
  const [restarting, setRestarting] = useState(false)

  // Fetch initial status and listen for updates
  useEffect(() => {
    // Get initial status
    window.electronAPI?.services?.getStatus?.().then((status: AllServiceStatus) => {
      if (status) setServices(status)
    }).catch(() => {})

    // Listen for real-time status updates from main process
    const cleanup = window.electronAPI?.services?.onStatusUpdate?.((status: AllServiceStatus) => {
      if (status) setServices(status)
    })

    return () => {
      cleanup?.()
    }
  }, [])

  const handleRestart = async () => {
    setRestarting(true)
    try {
      const status = await window.electronAPI?.services?.restartFastAPI?.()
      if (status) setServices(status)
    } catch (err) {
      console.error('Failed to restart services:', err)
    } finally {
      setRestarting(false)
    }
  }

  // Compute overall status
  const allRunning = services.fastapi.status === 'running' && services.python.status === 'running'
  const hasErrors = services.fastapi.status === 'error' || services.python.status === 'error'
  const isStarting = services.fastapi.status === 'starting'

  return (
    <div className="bg-engine-darker border-t border-gray-700">
      {/* Compact Bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-1.5 text-xs hover:bg-gray-800/50 transition"
      >
        <div className="flex items-center gap-3">
          {/* Overall indicator */}
          {isStarting ? (
            <Loader2 className="w-3.5 h-3.5 text-yellow-500 animate-spin" />
          ) : allRunning ? (
            <CheckCircle className="w-3.5 h-3.5 text-green-500" />
          ) : hasErrors ? (
            <XCircle className="w-3.5 h-3.5 text-red-500" />
          ) : (
            <Loader2 className="w-3.5 h-3.5 text-gray-500 animate-spin" />
          )}

          <span className="text-gray-400">
            {isStarting
              ? 'Starting services...'
              : allRunning
                ? 'All services running'
                : hasErrors
                  ? 'Service issues detected'
                  : 'Checking services...'}
          </span>

          {/* Individual service pills */}
          <div className="flex items-center gap-2 ml-2">
            <StatusPill name="API" status={services.fastapi.status} />
            <StatusPill name="Docker" status={services.docker.status} />
            <StatusPill name="Python" status={services.python.status} />
          </div>
        </div>

        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
        ) : (
          <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
        )}
      </button>

      {/* Expanded Detail Panel */}
      {expanded && (
        <div className="px-4 pb-3 pt-1 space-y-2 border-t border-gray-700/50">
          <ServiceRow
            icon={<Server className="w-4 h-4" />}
            service={services.fastapi}
            detail={services.fastapi.url || `Port 8000`}
          />
          <ServiceRow
            icon={<Container className="w-4 h-4" />}
            service={services.docker}
            detail="VNC sandbox & preview"
          />
          <ServiceRow
            icon={<Code2 className="w-4 h-4" />}
            service={services.python}
            detail="Python runtime"
          />

          {/* Restart button */}
          <div className="flex justify-end pt-1">
            <button
              onClick={handleRestart}
              disabled={restarting}
              className="flex items-center gap-1.5 px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${restarting ? 'animate-spin' : ''}`} />
              {restarting ? 'Restarting...' : 'Restart Services'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function StatusPill({ name, status }: { name: string; status: string }) {
  const colorClass =
    status === 'running'
      ? 'bg-green-500/20 text-green-400'
      : status === 'starting'
        ? 'bg-yellow-500/20 text-yellow-400'
        : status === 'error'
          ? 'bg-red-500/20 text-red-400'
          : 'bg-gray-500/20 text-gray-500'

  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${colorClass}`}>
      {name}
    </span>
  )
}

function ServiceRow({
  icon,
  service,
  detail,
}: {
  icon: React.ReactNode
  service: ServiceStatus
  detail: string
}) {
  return (
    <div className="flex items-center gap-3 text-xs">
      <div className="text-gray-400">{icon}</div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-200">{service.name}</span>
          <StatusBadge status={service.status} />
        </div>
        {service.error ? (
          <p className="text-red-400 mt-0.5 text-[11px]">{service.error}</p>
        ) : (
          <p className="text-gray-500 mt-0.5">{detail}</p>
        )}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'running') {
    return (
      <span className="flex items-center gap-1 text-green-400">
        <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
        Running
      </span>
    )
  }
  if (status === 'starting') {
    return (
      <span className="flex items-center gap-1 text-yellow-400">
        <Loader2 className="w-3 h-3 animate-spin" />
        Starting
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="flex items-center gap-1 text-red-400">
        <XCircle className="w-3 h-3" />
        Error
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1 text-gray-500">
      <span className="w-1.5 h-1.5 bg-gray-500 rounded-full" />
      Stopped
    </span>
  )
}
