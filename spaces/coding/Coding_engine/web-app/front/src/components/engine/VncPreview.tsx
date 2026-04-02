// front/src/components/engine/VncPreview.tsx
// Merged: Electron VNCViewer features + web-app platform adapter pattern
import { useState, useEffect, useRef, useCallback } from 'react';
import { AlertCircle, RefreshCw, ExternalLink, Clock } from 'lucide-react';
import { platform, isElectron } from '@/services/platform';
import { useEngineStore } from '@/stores/engineStore';

interface ClickMarker {
  id: string;
  x: number;
  y: number;
  fadeOut: boolean;
}

interface VncPreviewProps {
  vncUrl?: string;
  projectName: string;
  debugRecording?: boolean;
  onDebugClick?: (x: number, y: number) => void;
}

// Health check settings
const HEALTH_CHECK_INTERVAL = 2000; // ms between checks
const MAX_HEALTH_CHECKS = 30; // Max attempts (60 seconds total)

export function VncPreview({
  vncUrl: propVncUrl,
  projectName,
  debugRecording,
  onDebugClick,
}: VncPreviewProps) {
  const [status, setStatus] = useState<'checking' | 'loading' | 'connected' | 'error'>('checking');
  const [key, setKey] = useState(0);
  const [healthCheckCount, setHealthCheckCount] = useState(0);
  const [showIframe, setShowIframe] = useState(false);
  const [containerLogs, setContainerLogs] = useState<string>('');
  const [vncPort, setVncPort] = useState<number | null>(null);
  const [clickMarkers, setClickMarkers] = useState<ClickMarker[]>([]);
  const [previewMode, setPreviewMode] = useState<'app' | 'api' | 'vnc'>('app');
  const [appStatus, setAppStatus] = useState<'checking' | 'running' | 'error'>('checking');
  const [apiStatus, setApiStatus] = useState<'checking' | 'running' | 'error'>('checking');
  const healthCheckRef = useRef<NodeJS.Timeout | null>(null);
  const storeVncUrl = useEngineStore((state) => state.vncPreviewUrl);

  // Preview URLs (auto-detected based on what's running)
  const APP_PORT = 3100;     // Frontend App (Vite / Expo Web)
  const API_PORT = 3201;     // Backend API (NestJS / FastAPI) — mapped from 3000 in docker-compose
  const VNC_PORT = 6090;     // Android Emulator via noVNC
  const appPreviewUrl = `http://localhost:${APP_PORT}`;
  const apiPreviewUrl = `http://localhost:${API_PORT}`;

  // Check which servers are running → auto-select best tab
  useEffect(() => {
    const checkServers = async () => {
      // Check Frontend App (Vite / Expo Web on port 3100)
      try {
        await fetch(`http://localhost:${APP_PORT}`, { mode: 'no-cors' });
        setAppStatus('running');
      } catch {
        setAppStatus('checking');
      }

      // Check Backend API (NestJS / FastAPI on port 3200)
      try {
        await fetch(`http://localhost:${API_PORT}`, { mode: 'no-cors' });
        setApiStatus('running');
      } catch {
        setApiStatus('checking');
      }
    };
    checkServers();
    const interval = setInterval(checkServers, 5000);
    return () => clearInterval(interval);
  }, [previewMode]);

  // Resolve VNC port via platform adapter
  useEffect(() => {
    if (projectName) {
      platform.ports.getVncPort(projectName).then((port) => {
        if (port) setVncPort(port);
      });
    }
  }, [projectName]);

  // Build VNC URL: prop > store > port-resolved > default 6090 (mapped from container 6080)
  const resolvedPort = vncPort || 6090;
  const vncUrl =
    propVncUrl ||
    storeVncUrl ||
    `http://localhost:${resolvedPort}/vnc.html?autoconnect=true&resize=scale&reconnect=true&path=websockify`;

  // Fetch-based health check (COEP-safe, uses no-cors mode)
  const checkVNCHealth = useCallback(async (): Promise<boolean> => {
    const port = resolvedPort;
    try {
      const res = await fetch(`http://localhost:${port}/`, { mode: 'no-cors' });
      // no-cors returns opaque response (type: 'opaque', status: 0) on success
      console.log(`[VNC] Health check passed on port ${port}`);
      return true;
    } catch {
      return false;
    }
  }, [resolvedPort]);

  // Health check loop
  useEffect(() => {

    let isMounted = true;
    setStatus('checking');
    setHealthCheckCount(0);
    setShowIframe(false);

    const runHealthCheck = async () => {
      let attempts = 0;
      while (attempts < MAX_HEALTH_CHECKS && isMounted) {
        const isHealthy = await checkVNCHealth();
        if (!isMounted) break;
        attempts++;
        setHealthCheckCount(attempts);

        if (isHealthy) {
          console.log(`[VNC] Port ready after ${attempts} checks`);
          setStatus('loading');
          setShowIframe(true);
          return;
        }
        await new Promise((r) => setTimeout(r, HEALTH_CHECK_INTERVAL));
      }
      if (isMounted) {
        console.error(`[VNC] Not available after ${MAX_HEALTH_CHECKS} attempts`);
        setStatus('error');
      }
    };

    runHealthCheck();
    return () => {
      isMounted = false;
      if (healthCheckRef.current) clearTimeout(healthCheckRef.current);
    };
  }, [resolvedPort, key, checkVNCHealth]);

  // Fetch container logs on error (Electron only)
  useEffect(() => {
    if (status === 'error' && isElectron() && (window as any).electronAPI?.getProjectLogs) {
      (window as any).electronAPI
        .getProjectLogs(projectName, 50)
        .then((logs: string) => setContainerLogs(logs))
        .catch((err: Error) => console.warn('[VNC] Could not fetch container logs:', err));
    }
  }, [status, projectName]);

  // Debug click overlay handler
  const handleDebugOverlayClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = Math.round(((e.clientX - rect.left) / rect.width) * 100);
      const y = Math.round(((e.clientY - rect.top) / rect.height) * 100);

      const marker: ClickMarker = { id: crypto.randomUUID(), x, y, fadeOut: false };
      setClickMarkers((prev) => [...prev, marker]);
      setTimeout(() => {
        setClickMarkers((prev) => prev.map((m) => (m.id === marker.id ? { ...m, fadeOut: true } : m)));
      }, 1500);
      setTimeout(() => {
        setClickMarkers((prev) => prev.filter((m) => m.id !== marker.id));
      }, 2000);

      onDebugClick?.(x, y);
    },
    [onDebugClick]
  );

  const handleLoad = () => {
    console.log('[VNC] iframe loaded successfully');
    setStatus('connected');
  };

  const handleError = () => {
    if (status !== 'checking') setStatus('error');
  };

  const handleReconnect = () => {
    setStatus('checking');
    setShowIframe(false);
    setContainerLogs('');
    setKey((k) => k + 1);
  };

  const openInBrowser = () => {
    if (vncUrl) window.open(vncUrl, '_blank');
  };

  return (
    <div className="flex flex-col h-full border-l border-border/30">
      {/* Header with mode tabs */}
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-border/30">
        {(['app', 'api', 'vnc'] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => setPreviewMode(mode)}
            className={`text-[10px] px-2 py-1 rounded transition-colors ${
              previewMode === mode
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'text-muted-foreground hover:text-foreground hover:bg-white/5'
            }`}
          >
            {mode === 'app' ? '📱 App' : mode === 'api' ? '🔌 API' : '🖥 Emulator'}
            {mode === 'app' && appStatus === 'running' && <span className="ml-1 w-1.5 h-1.5 bg-green-400 rounded-full inline-block" />}
            {mode === 'api' && apiStatus === 'running' && <span className="ml-1 w-1.5 h-1.5 bg-green-400 rounded-full inline-block" />}
          </button>
        ))}
        <span
          className={`ml-auto text-[10px] px-2 py-0.5 rounded-full border ${
            (previewMode === 'app' && appStatus === 'running') || (previewMode === 'api' && apiStatus === 'running')
              ? 'bg-green-500/10 text-green-400 border-green-500/25'
              : previewMode === 'vnc' && status === 'connected'
                ? 'bg-green-500/10 text-green-400 border-green-500/25'
                : status === 'error'
                  ? 'bg-red-500/10 text-red-400 border-red-500/25'
                  : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/25'
          }`}
        >
          {previewMode === 'app'
            ? appStatus === 'running' ? 'Running' : 'Starting...'
            : previewMode === 'api'
              ? apiStatus === 'running' ? 'Running' : 'Starting...'
              : status === 'connected'
                ? 'Connected'
                : status === 'error'
                  ? 'Error'
                  : 'Waiting...'}
        </span>
      </div>

      {/* Main content area */}
      <div className="relative flex-1 bg-black m-1.5 rounded-md overflow-hidden">
        {/* App Preview (Frontend: Vite / Expo Web on port 3100) */}
        {previewMode === 'app' && (
          appStatus === 'running' ? (
            <iframe
              key={`app-${key}`}
              src={appPreviewUrl}
              className="w-full h-full border-0"
              title={`App Preview: ${projectName}`}
              sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups"
              onLoad={() => setStatus('connected')}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <p className="text-sm text-muted-foreground">📱 Waiting for app server...</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Port {APP_PORT} · Starts after frontend generation</p>
              </div>
            </div>
          )
        )}

        {/* API Preview (Backend: NestJS / FastAPI on port 3200) */}
        {previewMode === 'api' && (
          apiStatus === 'running' ? (
            <iframe
              key={`api-${key}`}
              src={apiPreviewUrl}
              className="w-full h-full border-0"
              title={`API Preview: ${projectName}`}
              sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups"
              onLoad={() => setStatus('connected')}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <p className="text-sm text-muted-foreground">🔌 Waiting for API server...</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Port {API_PORT} · Starts after backend generation</p>
              </div>
            </div>
          )
        )}

        {/* noVNC iframe - only after health check passes */}
        {previewMode === 'vnc' && showIframe && vncUrl && (
          <iframe
            key={`vnc-${key}`}
            src={vncUrl}
            className="w-full h-full border-0"
            title={`VNC: ${projectName}`}
            sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups"
            allow="clipboard-read; clipboard-write"
            onLoad={handleLoad}
            onError={handleError}
            style={{ display: status === 'connected' ? 'block' : 'none' }}
          />
        )}

        {/* Health Check Overlay */}
        {status === 'checking' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Clock className="w-8 h-8 mx-auto mb-2 text-yellow-500 animate-pulse" />
              <p className="text-sm text-muted-foreground">Waiting for VNC server...</p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                Port {resolvedPort} &middot; Check {healthCheckCount}/{MAX_HEALTH_CHECKS}
              </p>
              <div className="w-40 h-1 bg-gray-700 rounded mt-2 mx-auto overflow-hidden">
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
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 mx-auto mb-2 text-blue-400 animate-spin" />
              <p className="text-sm text-muted-foreground">Connecting to VNC...</p>
            </div>
          </div>
        )}

        {/* Error Overlay */}
        {status === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center overflow-auto py-4">
            <div className="text-center max-w-md px-4">
              <AlertCircle className="w-8 h-8 mx-auto mb-2 text-red-500" />
              <p className="text-sm text-muted-foreground">Failed to connect to VNC</p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                Port {resolvedPort} &middot; Container may still be starting
              </p>
              <div className="flex gap-2 mt-3 justify-center">
                <button
                  onClick={handleReconnect}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-xs font-medium transition text-white"
                >
                  Retry
                </button>
                <button
                  onClick={openInBrowser}
                  className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-medium transition text-white flex items-center gap-1.5"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Browser
                </button>
              </div>
              {containerLogs && (
                <details className="mt-3 text-left">
                  <summary className="text-[10px] text-muted-foreground/60 cursor-pointer hover:text-muted-foreground">
                    Container Logs
                  </summary>
                  <pre className="mt-1 p-2 bg-gray-900 text-[10px] text-muted-foreground/60 overflow-auto max-h-32 rounded whitespace-pre-wrap">
                    {containerLogs}
                  </pre>
                </details>
              )}
            </div>
          </div>
        )}

        {/* Connection indicator (when connected, no debug) */}
        {status === 'connected' && !debugRecording && (
          <div className="absolute top-1.5 right-1.5 flex items-center gap-1.5 px-1.5 py-0.5 bg-black/50 rounded text-[10px]">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-gray-300">Live</span>
          </div>
        )}

        {/* Debug Recording Overlay */}
        {debugRecording && status === 'connected' && (
          <div
            className="absolute inset-0 cursor-crosshair"
            style={{ zIndex: 10 }}
            onClick={handleDebugOverlayClick}
          >
            <div className="absolute top-1.5 left-1.5 flex items-center gap-1.5 px-1.5 py-0.5 bg-red-600/80 rounded text-[10px] z-20">
              <div className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
              <span className="text-white font-medium">REC</span>
            </div>
            {clickMarkers.map((marker) => (
              <div
                key={marker.id}
                className={`absolute w-5 h-5 -ml-2.5 -mt-2.5 rounded-full border-2 border-red-400 bg-red-500/30 transition-opacity duration-500 ${
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

      {/* Footer */}
      <div className="px-3 py-1.5 text-[10px] text-muted-foreground bg-background/50 flex items-center gap-2">
        <span>
          {previewMode === 'app' ? appPreviewUrl
            : previewMode === 'api' ? apiPreviewUrl
            : vncUrl || `localhost:${resolvedPort}/vnc.html`}
        </span>
        <button
          onClick={() => {
            const url = previewMode === 'app' ? appPreviewUrl
              : previewMode === 'api' ? apiPreviewUrl : vncUrl;
            if (url) window.open(url, '_blank');
          }}
          className="ml-auto hover:text-foreground transition-colors"
        >
          <ExternalLink className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
