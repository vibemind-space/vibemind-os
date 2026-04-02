import { useEffect, useRef } from 'react'
import { MainLayout } from './components/Layout/MainLayout'
import { ToastContainer } from './components/Toast'
import { useEngineStore } from './stores/engineStore'
import { useProjectStore } from './stores/projectStore'

function App() {
  const { checkEngineStatus, connectWebSocket, wsConnected } = useEngineStore()
  const { loadFromOrchestrator } = useProjectStore()
  const wsAttempted = useRef(false)

  useEffect(() => {
    // Check engine status on mount
    checkEngineStatus()

    // Load projects from req-orchestrator
    loadFromOrchestrator()

    // Periodic status check (every 30s instead of 5s to reduce noise)
    const interval = setInterval(checkEngineStatus, 30000)

    return () => clearInterval(interval)
  }, [checkEngineStatus, loadFromOrchestrator])

  // Auto-connect WebSocket when FastAPI becomes ready
  // Listen for service status updates from Electron main process
  useEffect(() => {
    const cleanup = window.electronAPI?.services?.onStatusUpdate?.((status: any) => {
      if (status?.fastapi?.status === 'running' && !wsAttempted.current) {
        console.log('[App] FastAPI is ready — auto-connecting WebSocket')
        wsAttempted.current = true
        connectWebSocket()
      }
    })

    // Also try to connect immediately if FastAPI is already running
    window.electronAPI?.services?.getStatus?.().then((status: any) => {
      if (status?.fastapi?.status === 'running' && !wsAttempted.current) {
        console.log('[App] FastAPI already running — connecting WebSocket')
        wsAttempted.current = true
        connectWebSocket()
      }
    }).catch(() => {})

    return () => { cleanup?.() }
  }, [connectWebSocket])

  return (
    <>
      <MainLayout />
      <ToastContainer />
    </>
  )
}

export default App
