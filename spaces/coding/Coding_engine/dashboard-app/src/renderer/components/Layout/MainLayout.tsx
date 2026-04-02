import { useState, useEffect } from 'react'
import { ProjectList } from '../Sidebar/ProjectList'
import { ProjectSpace } from '../ProjectSpace/ProjectSpace'
import { GenerationMonitor } from '../GenerationMonitor/GenerationMonitor'
import { LivePreview } from '../LivePreview/LivePreview'
import { PortalPage } from '../Portal/PortalPage'
import { ServiceStatusBar } from '../ServiceStatusBar/ServiceStatusBar'
import {
  ClarificationBadge,
  ClarificationPanel,
  ClarificationEditor,
} from '../Notifications'
import { useEngineStore } from '../../stores/engineStore'
import { useProjectStore } from '../../stores/projectStore'
import {
  useClarificationStore,
  useSelectedClarification,
  usePendingCount,
  useHighPriorityCount,
} from '../../stores/clarificationStore'
import { Play, Square, Wifi, WifiOff, Server, Store, FolderOpen } from 'lucide-react'

type ActiveView = 'projects' | 'portal'

export function MainLayout() {
  const [activeView, setActiveView] = useState<ActiveView>('projects')
  const { engineRunning, wsConnected, startEngine, stopEngine } = useEngineStore()
  const { previewProjectId } = useProjectStore()

  // Clarification state
  const {
    pending: clarifications,
    statistics,
    isPanelOpen,
    isEditorOpen,
    isLoading: clarificationLoading,
    openPanel,
    closePanel,
    selectClarification,
    closeEditor,
    refreshPending,
    submitChoice,
    useAllDefaults,
  } = useClarificationStore()

  const selectedClarification = useSelectedClarification()
  const pendingCount = usePendingCount()
  const highPriorityCount = useHighPriorityCount()

  // Poll for clarification updates when engine is running
  useEffect(() => {
    if (!engineRunning) return

    // Initial fetch
    refreshPending()

    // Poll every 5 seconds
    const interval = setInterval(() => {
      refreshPending()
    }, 5000)

    return () => clearInterval(interval)
  }, [engineRunning, refreshPending])

  return (
    <div className="h-screen flex flex-col bg-engine-darker">
      {/* Header */}
      <header className="h-12 bg-engine-dark border-b border-gray-700 flex items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <Server className="w-5 h-5 text-engine-primary" />
            <h1 className="text-lg font-semibold">Coding Engine</h1>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1">
            <button
              onClick={() => setActiveView('projects')}
              className={`
                flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition
                ${activeView === 'projects'
                  ? 'bg-engine-primary/20 text-engine-primary'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
                }
              `}
            >
              <FolderOpen className="w-4 h-4" />
              Projects
            </button>
            <button
              onClick={() => setActiveView('portal')}
              className={`
                flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition
                ${activeView === 'portal'
                  ? 'bg-engine-primary/20 text-engine-primary'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
                }
              `}
            >
              <Store className="w-4 h-4" />
              Marketplace
            </button>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {/* Clarification Badge */}
          <ClarificationBadge
            count={pendingCount}
            highPriorityCount={highPriorityCount}
            onClick={openPanel}
          />

          {/* WebSocket Status */}
          <div className="flex items-center gap-2 text-sm">
            {wsConnected ? (
              <>
                <Wifi className="w-4 h-4 text-green-500" />
                <span className="text-green-500">Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="w-4 h-4 text-gray-500" />
                <span className="text-gray-500">Disconnected</span>
              </>
            )}
          </div>

          {/* Engine Control */}
          {engineRunning ? (
            <button
              onClick={stopEngine}
              className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-sm font-medium transition"
            >
              <Square className="w-4 h-4" />
              Stop Engine
            </button>
          ) : (
            <button
              onClick={startEngine}
              className="flex items-center gap-2 px-3 py-1.5 bg-engine-primary hover:bg-blue-600 rounded text-sm font-medium transition"
            >
              <Play className="w-4 h-4" />
              Start Engine
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      {activeView === 'projects' ? (
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar - Project List */}
          <aside className="w-64 bg-engine-dark border-r border-gray-700 flex flex-col">
            <ProjectList />
          </aside>

          {/* Center - Project Space & Generation Monitor */}
          <main className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-auto">
              <ProjectSpace />
            </div>
            <div className="h-48 border-t border-gray-700">
              <GenerationMonitor />
            </div>
          </main>

          {/* Right Panel - Live Preview */}
          {previewProjectId && (
            <aside className="w-[500px] bg-engine-dark border-l border-gray-700">
              <LivePreview />
            </aside>
          )}
        </div>
      ) : (
        <PortalPage />
      )}

      {/* Clarification Panel (Slide-out) */}
      <ClarificationPanel
        isOpen={isPanelOpen}
        isLoading={clarificationLoading}
        clarifications={clarifications}
        statistics={statistics}
        onClose={closePanel}
        onSelect={selectClarification}
        onResolveAll={useAllDefaults}
        onRefresh={refreshPending}
      />

      {/* Clarification Editor (Modal) */}
      <ClarificationEditor
        clarification={selectedClarification}
        isOpen={isEditorOpen}
        isLoading={clarificationLoading}
        onClose={closeEditor}
        onSubmit={submitChoice}
      />

      {/* Service Status Bar (bottom) */}
      <ServiceStatusBar />
    </div>
  )
}
