import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Tenant, TenantMember, TenantRole, PortalCell } from '../types/portal'
import { tenantAPI } from '../api/portalAPI'

// ============================================================================
// Types
// ============================================================================

interface TenantState {
  // Current state
  tenants: Tenant[]
  activeTenantId: string | null
  isLoading: boolean
  error: string | null

  // Active tenant details
  activeTenantMembers: TenantMember[]
  activeTenantCells: PortalCell[]
  detailsLoading: boolean

  // Computed
  getActiveTenant: () => Tenant | null
  getMyRole: () => TenantRole | null

  // Actions
  loadTenants: () => Promise<void>
  switchTenant: (tenantId: string) => void
  createTenant: (data: {
    name: string
    displayName: string
    description?: string
  }) => Promise<Tenant | null>
  updateTenant: (
    tenantId: string,
    updates: { displayName?: string; description?: string }
  ) => Promise<boolean>

  // Member management
  loadTenantDetails: () => Promise<void>
  inviteMember: (email: string, role: TenantRole) => Promise<boolean>
  updateMemberRole: (memberId: string, role: TenantRole) => Promise<boolean>
  removeMember: (memberId: string) => Promise<boolean>
}

// ============================================================================
// Store
// ============================================================================

export const useTenantStore = create<TenantState>()(
  persist(
    (set, get) => ({
      // Initial state
      tenants: [],
      activeTenantId: null,
      isLoading: false,
      error: null,

      activeTenantMembers: [],
      activeTenantCells: [],
      detailsLoading: false,

      // Computed
      getActiveTenant: () => {
        const { tenants, activeTenantId } = get()
        return tenants.find((t) => t.id === activeTenantId) || null
      },

      getMyRole: () => {
        const { activeTenantMembers } = get()
        // TODO: Get current user ID from auth state
        // For now, return the first member's role
        return activeTenantMembers[0]?.role || null
      },

      // Actions
      loadTenants: async () => {
        set({ isLoading: true, error: null })

        try {
          const tenants = await tenantAPI.getMyTenants()
          const { activeTenantId } = get()

          set({
            tenants,
            isLoading: false,
            // Auto-select first tenant if none selected
            activeTenantId:
              activeTenantId && tenants.find((t) => t.id === activeTenantId)
                ? activeTenantId
                : tenants[0]?.id || null,
          })

          // Load details for active tenant
          if (get().activeTenantId) {
            get().loadTenantDetails()
          }
        } catch (error: any) {
          set({
            error: error.message || 'Failed to load tenants',
            isLoading: false,
          })
        }
      },

      switchTenant: (tenantId) => {
        const { tenants } = get()
        if (tenants.find((t) => t.id === tenantId)) {
          set({
            activeTenantId: tenantId,
            activeTenantMembers: [],
            activeTenantCells: [],
          })
          // Load details for new tenant
          get().loadTenantDetails()
        }
      },

      createTenant: async (data) => {
        set({ isLoading: true, error: null })

        try {
          const tenant = await tenantAPI.create(data)
          set((state) => ({
            tenants: [...state.tenants, tenant],
            activeTenantId: tenant.id,
            isLoading: false,
          }))
          return tenant
        } catch (error: any) {
          set({
            error: error.message || 'Failed to create tenant',
            isLoading: false,
          })
          return null
        }
      },

      updateTenant: async (tenantId, updates) => {
        try {
          const updated = await tenantAPI.update(tenantId, updates)
          set((state) => ({
            tenants: state.tenants.map((t) => (t.id === tenantId ? updated : t)),
          }))
          return true
        } catch (error: any) {
          set({ error: error.message || 'Failed to update tenant' })
          return false
        }
      },

      loadTenantDetails: async () => {
        const { activeTenantId } = get()
        if (!activeTenantId) return

        set({ detailsLoading: true })

        try {
          const [members, cells] = await Promise.all([
            tenantAPI.getMembers(activeTenantId),
            tenantAPI.getCells(activeTenantId),
          ])

          set({
            activeTenantMembers: members,
            activeTenantCells: cells,
            detailsLoading: false,
          })
        } catch (error) {
          console.error('Failed to load tenant details:', error)
          set({ detailsLoading: false })
        }
      },

      inviteMember: async (email, role) => {
        const { activeTenantId } = get()
        if (!activeTenantId) return false

        try {
          await tenantAPI.inviteMember(activeTenantId, email, role)
          return true
        } catch (error: any) {
          set({ error: error.message || 'Failed to invite member' })
          return false
        }
      },

      updateMemberRole: async (memberId, role) => {
        const { activeTenantId } = get()
        if (!activeTenantId) return false

        try {
          const updated = await tenantAPI.updateMemberRole(activeTenantId, memberId, role)
          set((state) => ({
            activeTenantMembers: state.activeTenantMembers.map((m) =>
              m.id === memberId ? updated : m
            ),
          }))
          return true
        } catch (error: any) {
          set({ error: error.message || 'Failed to update role' })
          return false
        }
      },

      removeMember: async (memberId) => {
        const { activeTenantId } = get()
        if (!activeTenantId) return false

        try {
          await tenantAPI.removeMember(activeTenantId, memberId)
          set((state) => ({
            activeTenantMembers: state.activeTenantMembers.filter((m) => m.id !== memberId),
          }))
          return true
        } catch (error: any) {
          set({ error: error.message || 'Failed to remove member' })
          return false
        }
      },
    }),
    {
      name: 'coding-engine-tenants',
      partialize: (state) => ({
        activeTenantId: state.activeTenantId,
      }),
    }
  )
)
