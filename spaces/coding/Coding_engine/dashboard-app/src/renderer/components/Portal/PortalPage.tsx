import { useState, useEffect } from 'react'
import { Store, Plus } from 'lucide-react'
import { usePortalStore } from '../../stores/portalStore'
import { useTenantStore } from '../../stores/tenantStore'
import { MarketplaceBrowser } from './MarketplaceBrowser'
import { CellDetailModal } from './CellDetailModal'
import { TenantSwitcher } from '../Tenant/TenantSwitcher'
import { PublishCellModal } from '../CellPublication/PublishCellModal'
import type { PortalCell } from '../../types/portal'

export function PortalPage() {
  const [selectedCell, setSelectedCell] = useState<PortalCell | null>(null)
  const [showPublishModal, setShowPublishModal] = useState(false)

  const { selectCell, loadCellDetail } = usePortalStore()
  const { loadTenants, activeTenantId } = useTenantStore()

  // Load tenants on mount
  useEffect(() => {
    loadTenants()
  }, [loadTenants])

  const handleCellClick = (cell: PortalCell) => {
    setSelectedCell(cell)
    selectCell(cell)
    loadCellDetail(cell.id)
  }

  const handleCellInstall = (cell: PortalCell) => {
    // Open detail modal for install
    handleCellClick(cell)
  }

  const handleCloseDetail = () => {
    setSelectedCell(null)
    selectCell(null)
  }

  const handlePublishSuccess = () => {
    setShowPublishModal(false)
    // Refresh featured cells
    usePortalStore.getState().loadFeaturedCells()
  }

  return (
    <div className="h-full flex flex-col bg-engine-darker">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <Store className="w-6 h-6 text-engine-primary" />
          <h1 className="text-xl font-semibold">Cell Marketplace</h1>
        </div>

        <div className="flex items-center gap-4">
          {/* Tenant Switcher */}
          <TenantSwitcher />

          {/* Publish Button */}
          {activeTenantId && (
            <button
              onClick={() => setShowPublishModal(true)}
              className="
                flex items-center gap-2
                px-4 py-2
                bg-engine-primary
                hover:bg-blue-600
                rounded-lg
                font-medium
                transition-colors
              "
            >
              <Plus className="w-4 h-4" />
              Publish Cell
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        <MarketplaceBrowser
          onCellClick={handleCellClick}
          onCellInstall={handleCellInstall}
        />
      </main>

      {/* Cell Detail Modal */}
      {selectedCell && (
        <CellDetailModal
          cell={selectedCell}
          onClose={handleCloseDetail}
          onInstall={(cell, version) => {
            console.log('Installing:', cell.name, version)
          }}
        />
      )}

      {/* Publish Modal */}
      {showPublishModal && (
        <PublishCellModal
          onClose={() => setShowPublishModal(false)}
          onSuccess={handlePublishSuccess}
        />
      )}
    </div>
  )
}
