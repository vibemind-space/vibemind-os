import { useState, useEffect, useRef, useCallback } from 'react'
import { AlertCircle, RefreshCw, ExternalLink, Clock } from 'lucide-react'

interface ClickMarker {
  id: string
  x: number
  y: number
  fadeOut: boolean
}

interface VNCViewerProps {
  port: number
  projectId: string
  debugRecording?: boolean
  onDebugClick?: (x: number, y: number) => void
}

// Health check settings
const HEALTH_CHECK_INTERVAL = 2000 // ms between checks
const MAX_HEALTH_CHECKS = 30 // Max attempts (60 seconds total)

export function VNCViewer({ port, projectId, debugRecording, onDebugClick }: VNCViewerProps) {
  const [status, setStatus] = useState<'checking' | 'loading' | 'loaded' | 'error'>('checking')
  const [key, setKey] = useState(0)
  const [healthCheckCount, setHealthCheckCount] = useState(0)
  const [showIframe, setShowIframe] = useState(false)
  const [containerLogs, setContainerLogs] = useState<string>('')
  const healthCheckRef = useRef<NodeJS.Timeout | null>(null)
  const [clickMarkers, setClickMarkers] = useState<ClickMarker[]>([])

  // Handle debug click on overlay
  const handleDebugOverlayClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.round(((e.clientX - rect.left) / rect.width) * 100)
    const y = Math.round(((e.clientY - rect.top) / rect.height) * 100)

    // Add visual marker
    const marker: ClickMarker = { id: crypto.randomUUID(), x, y, fadeOut: false }
    setClickMarkers((prev) => [...prev, marker])

    // Fade out after 1.5s, remove after 2s
    setTimeout(() => {
      setClickMarkers((prev) => prev.map((m) => m.id === marker.id ? { ...m, fadeOut: true } : m))
    }, 1500)
    setTimeout(() => {
      setClickMarkers((prev) => prev.filter((m) => m.id !== marker.id))
    }, 2000)

    onDebugClick?.(x, y)
  }, [onDebugClick])

  // noVNC web client URL - our Docker sandbox serves this on the VNC port
  const vncUrl = `http://localhost:${port}/vnc.html?autoconnect=true&resize=scale&reconnect=true`

  // Health check function - uses Image loading to bypass CORS and detect if noVNC is serving
  const checkVNCHealth = async (): Promise<boolean> => {
    try {
      // Use an Image element to bypass CORS - noVNC serves static files
      return new Promise((resolve) => {
        const img = new Image()
        const timeout = setTimeout(() => {
          img.onload = null
          img.onerror = null
          resolve(false)
        }, 2000)  // 2 second timeout per check

        img.onload = () => {
          clearTimeout(timeout)
          console.log(`[VNC] Health check passed - noVNC is serving on port ${port}`)
          resolve(true)
        }
        img.onerror = () => {
          clearTimeout(timeout)
          // Image failed to load - try fallback check with favicon
          const favicon = new Image()
          const fallbackTimeout = setTimeout(() => {
            favicon.onload = null
            favicon.onerror = null
            resolve(false)
          }, 1000)

          favicon.onload = () => {
            clearTimeout(fallbackTimeout)
            console.log(`[VNC] Fallback health check passed - port ${port}`)
            resolve(true)
          }
          favicon.onerror = () => {
            clearTimeout(fallbackTimeout)
            resolve(false)
          }
          // Try loading favicon as fallback
          favicon.src = `http://localhost:${port}/favicon.ico?t=${Date.now()}`
        }
        // noVNC serves static files at /app/images/icons/
        img.src = `http://localhost:${port}/app/images/icons/novnc-16x16.png?t=${Date.now()}`
      })
    } catch (error) {
      console.error('[VNC] Health check error:', error)
      return false
    }
  }

  // Start health checking when component mounts or port changes
  useEffect(() => {
    let isMounted = true
    setStatus('checking')
    setHealthCheckCount(0)
    setShowIframe(false)

    const runHealthCheck = async () => {
      let attempts = 0

      while (attempts < MAX_HEALTH_CHECKS && isMounted) {
        const isHealthy = await checkVNCHealth()

        if (!isMounted) break

        attempts++
        setHealthCheckCount(attempts)

        if (isHealthy) {
          console.log(`[VNC] Port ${port} is ready after ${attempts} checks`)
          setStatus('loading')
          setShowIframe(true)
          return
        }

        // Wait before next check
        await new Promise(resolve => setTimeout(resolve, HEALTH_CHECK_INTERVAL))
      }

      // Max attempts reached
      if (isMounted) {
        console.error(`[VNC] Port ${port} not available after ${MAX_HEALTH_CHECKS} attempts`)
        setStatus('error')
      }
    }

    runHealthCheck()

    return () => {
      isMounted = false
      if (healthCheckRef.current) {
        clearTimeout(healthCheckRef.current)
      }
    }
  }, [port, key])

  // Fetch container logs when VNC fails to help diagnose issues
  useEffect(() => {
    if (status === 'error' && (window as any).electronAPI?.getProjectLogs) {
      (window as any).electronAPI.getProjectLogs(projectId, 50)
        .then((logs: string) => {
          setContainerLogs(logs)
          console.log('[VNC] Container logs fetched for debugging')
        })
        .catch((err: Error) => {
          console.warn('[VNC] Could not fetch container logs:', err)
        })
    }
  }, [status, projectId])

  const handleLoad = () => {
    console.log('[VNC] iframe loaded successfully:', vncUrl)
    setStatus('loaded')
  }

  const handleError = (e: React.SyntheticEvent) => {
    console.error('[VNC] iframe error:', vncUrl, e)
    // Don't immediately show error - could be a race condition
    // Let the health check continue
    if (status !== 'checking') {
      setStatus('error')
    }
  }

  const handleReconnect = () => {
    setStatus('checking')
    setShowIframe(false)
    setKey((k) => k + 1) // Force iframe reload and restart health check
  }

  const openInBrowser = () => {
    window.open(vncUrl, '_blank')
  }

  return (
    <div className="relative w-full h-full bg-black">
      {/* noVNC iframe - only rendered after health check passes */}
      {showIframe && (
        <iframe
          key={key}
          src={vncUrl}
          className="w-full h-full border-0"
          title={`VNC Preview - ${projectId}`}
          sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups"
          allow="clipboard-read; clipboard-write"
          onLoad={handleLoad}
          onError={handleError}
          style={{ display: status === 'loaded' ? 'block' : 'none' }}
        />
      )}

      {/* Health Check Overlay */}
      {status === 'checking' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black">
          <div className="text-center">
            <Clock className="w-10 h-10 mx-auto mb-3 text-yellow-500 animate-pulse" />
            <p className="text-gray-300">Waiting for VNC server...</p>
            <p className="text-xs text-gray-500 mt-1">
              Port {port} • Check {healthCheckCount}/{MAX_HEALTH_CHECKS}
            </p>
            <div className="w-48 h-1 bg-gray-700 rounded mt-3 mx-auto overflow-hidden">
              <div
                className="h-full bg-yellow-500 transition-all duration-500"
                style={{ width: `${(healthCheckCount / MAX_HEALTH_CHECKS) * 100}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Loading Overlay */}
      {status === 'loading' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black">
          <div className="text-center">
            <RefreshCw className="w-10 h-10 mx-auto mb-3 text-engine-primary animate-spin" />
            <p className="text-gray-300">Connecting to VNC...</p>
            <p className="text-xs text-gray-500 mt-1">Port {port}</p>
          </div>
        </div>
      )}

      {/* Error Overlay */}
      {status === 'error' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black overflow-auto py-4">
          <div className="text-center max-w-lg">
            <AlertCircle className="w-10 h-10 mx-auto mb-3 text-red-500" />
            <p className="text-gray-300">Failed to connect to VNC</p>
            <p className="text-xs text-gray-500 mt-1">
              Port {port} - Container may still be starting
            </p>
            <div className="flex gap-2 mt-4 justify-center">
              <button
                onClick={handleReconnect}
                className="px-4 py-2 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition"
              >
                Retry
              </button>
              <button
                onClick={openInBrowser}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition flex items-center gap-2"
              >
                <ExternalLink className="w-4 h-4" />
                Open in Browser
              </button>
            </div>
            {containerLogs && (
              <details className="mt-4 text-left">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300">
                  Container Logs (click to expand)
                </summary>
                <pre className="mt-2 p-2 bg-gray-900 text-xs text-gray-400 overflow-auto max-h-40 rounded text-left whitespace-pre-wrap">
                  {containerLogs}
                </pre>
              </details>
            )}
          </div>
        </div>
      )}

      {/* Connection Status Indicator */}
      {status === 'loaded' && !debugRecording && (
        <div className="absolute top-2 right-2 flex items-center gap-2 px-2 py-1 bg-black/50 rounded text-xs">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-gray-300">Live</span>
        </div>
      )}

      {/* Debug Recording Overlay - captures clicks when recording */}
      {debugRecording && status === 'loaded' && (
        <div
          className="absolute inset-0 cursor-crosshair"
          style={{ zIndex: 10 }}
          onClick={handleDebugOverlayClick}
        >
          {/* REC indicator */}
          <div className="absolute top-2 left-2 flex items-center gap-2 px-2 py-1 bg-red-600/80 rounded text-xs z-20">
            <div className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
            <span className="text-white font-medium">REC</span>
          </div>

          {/* Click markers */}
          {clickMarkers.map((marker) => (
            <div
              key={marker.id}
              className={`absolute w-6 h-6 -ml-3 -mt-3 rounded-full border-2 border-red-400 bg-red-500/30 transition-opacity duration-500 ${
                marker.fadeOut ? 'opacity-0' : 'opacity-100'
              }`}
              style={{ left: `${marker.x}%`, top: `${marker.y}%` }}
            >
              <div className="absolute inset-0 rounded-full bg-red-400/50 animate-ping" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
