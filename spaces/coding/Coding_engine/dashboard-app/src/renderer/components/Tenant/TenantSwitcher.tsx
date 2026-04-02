import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Building2, Plus, Check, Settings, LogOut } from 'lucide-react'
import { useTenantStore } from '../../stores/tenantStore'
import type { Tenant } from '../../types/portal'

interface TenantSwitcherProps {
  className?: string
}

export function TenantSwitcher({ className = '' }: TenantSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const {
    tenants,
    activeTenantId,
    isLoading,
    switchTenant,
    createTenant,
    getActiveTenant,
  } = useTenantStore()

  const activeTenant = getActiveTenant()

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setShowCreateForm(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleTenantSelect = (tenantId: string) => {
    switchTenant(tenantId)
    setIsOpen(false)
  }

  const handleCreateTenant = async (name: string, displayName: string) => {
    const tenant = await createTenant({ name, displayName })
    if (tenant) {
      setShowCreateForm(false)
    }
  }

  if (tenants.length === 0 && !isLoading) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className={`
          flex items-center gap-2 px-3 py-2
          bg-engine-dark border border-gray-600
          rounded-lg text-sm
          hover:border-gray-500
          transition-colors
          ${className}
        `}
      >
        <Plus className="w-4 h-4" />
        Create Organization
      </button>
    )
  }

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className="
          flex items-center gap-2 px-3 py-2
          bg-engine-dark border border-gray-600
          rounded-lg text-sm
          hover:border-gray-500
          transition-colors
          min-w-[180px]
        "
      >
        {activeTenant?.logoUrl ? (
          <img
            src={activeTenant.logoUrl}
            alt={activeTenant.displayName}
            className="w-5 h-5 rounded"
          />
        ) : (
          <Building2 className="w-4 h-4 text-gray-400" />
        )}
        <span className="flex-1 text-left truncate">
          {activeTenant?.displayName || 'Select Organization'}
        </span>
        <ChevronDown
          className={`w-4 h-4 text-gray-400 transition-transform ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-engine-dark border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
          {/* Tenant List */}
          <div className="max-h-60 overflow-y-auto">
            {tenants.map((tenant) => (
              <TenantItem
                key={tenant.id}
                tenant={tenant}
                isActive={tenant.id === activeTenantId}
                onClick={() => handleTenantSelect(tenant.id)}
              />
            ))}
          </div>

          {/* Divider */}
          <div className="border-t border-gray-700" />

          {/* Create New */}
          {showCreateForm ? (
            <CreateTenantForm
              onSubmit={handleCreateTenant}
              onCancel={() => setShowCreateForm(false)}
            />
          ) : (
            <button
              onClick={() => setShowCreateForm(true)}
              className="
                w-full flex items-center gap-2 px-4 py-3
                text-sm text-gray-400
                hover:bg-gray-800 hover:text-white
                transition-colors
              "
            >
              <Plus className="w-4 h-4" />
              Create Organization
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// Tenant List Item
interface TenantItemProps {
  tenant: Tenant
  isActive: boolean
  onClick: () => void
}

function TenantItem({ tenant, isActive, onClick }: TenantItemProps) {
  return (
    <button
      onClick={onClick}
      className={`
        w-full flex items-center gap-3 px-4 py-3
        text-left
        ${isActive ? 'bg-engine-primary/10' : 'hover:bg-gray-800'}
        transition-colors
      `}
    >
      {tenant.logoUrl ? (
        <img
          src={tenant.logoUrl}
          alt={tenant.displayName}
          className="w-8 h-8 rounded"
        />
      ) : (
        <div className="w-8 h-8 rounded bg-engine-darker flex items-center justify-center">
          <Building2 className="w-4 h-4 text-gray-500" />
        </div>
      )}

      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{tenant.displayName}</div>
        <div className="text-xs text-gray-500 truncate">{tenant.name}</div>
      </div>

      {isActive && <Check className="w-4 h-4 text-engine-primary flex-shrink-0" />}
    </button>
  )
}

// Create Tenant Form
interface CreateTenantFormProps {
  onSubmit: (name: string, displayName: string) => void
  onCancel: () => void
}

function CreateTenantForm({ onSubmit, onCancel }: CreateTenantFormProps) {
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !displayName.trim()) return

    setSubmitting(true)
    await onSubmit(name.trim(), displayName.trim())
    setSubmitting(false)
  }

  // Auto-generate name from display name
  const handleDisplayNameChange = (value: string) => {
    setDisplayName(value)
    if (!name || name === toSlug(displayName)) {
      setName(toSlug(value))
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-3">
      <div>
        <label className="block text-xs text-gray-500 mb-1">Display Name</label>
        <input
          type="text"
          value={displayName}
          onChange={(e) => handleDisplayNameChange(e.target.value)}
          placeholder="My Organization"
          className="
            w-full px-3 py-2
            bg-engine-darker border border-gray-600
            rounded text-sm
            focus:outline-none focus:border-engine-primary
          "
        />
      </div>

      <div>
        <label className="block text-xs text-gray-500 mb-1">URL Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(toSlug(e.target.value))}
          placeholder="my-organization"
          className="
            w-full px-3 py-2
            bg-engine-darker border border-gray-600
            rounded text-sm
            focus:outline-none focus:border-engine-primary
          "
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-gray-400 hover:text-white"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={!name.trim() || !displayName.trim() || submitting}
          className="
            px-3 py-1.5
            bg-engine-primary hover:bg-blue-600
            rounded text-sm font-medium
            disabled:opacity-50
            transition-colors
          "
        >
          Create
        </button>
      </div>
    </form>
  )
}

// Helper to convert display name to URL-safe slug
function toSlug(str: string): string {
  return str
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}
