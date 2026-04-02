import { useState } from 'react'
import {
  Users,
  Mail,
  Shield,
  Trash2,
  Plus,
  ChevronDown,
  Loader2,
  Crown,
  UserCog,
  Code,
  Eye,
} from 'lucide-react'
import { useTenantStore } from '../../stores/tenantStore'
import type { TenantMember, TenantRole } from '../../types/portal'

interface TenantManagementPanelProps {
  onClose?: () => void
  className?: string
}

const ROLE_CONFIG: Record<TenantRole, { label: string; icon: React.ReactNode; color: string }> = {
  owner: { label: 'Owner', icon: <Crown className="w-4 h-4" />, color: 'text-yellow-400' },
  admin: { label: 'Admin', icon: <Shield className="w-4 h-4" />, color: 'text-purple-400' },
  developer: { label: 'Developer', icon: <Code className="w-4 h-4" />, color: 'text-blue-400' },
  viewer: { label: 'Viewer', icon: <Eye className="w-4 h-4" />, color: 'text-gray-400' },
}

export function TenantManagementPanel({ onClose, className = '' }: TenantManagementPanelProps) {
  const [showInviteForm, setShowInviteForm] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<TenantRole>('developer')
  const [inviting, setInviting] = useState(false)
  const [removingMemberId, setRemovingMemberId] = useState<string | null>(null)

  const {
    getActiveTenant,
    activeTenantMembers,
    detailsLoading,
    inviteMember,
    updateMemberRole,
    removeMember,
    getMyRole,
    error,
  } = useTenantStore()

  const tenant = getActiveTenant()
  const myRole = getMyRole()
  const canManageMembers = myRole === 'owner' || myRole === 'admin'

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inviteEmail.trim()) return

    setInviting(true)
    const success = await inviteMember(inviteEmail.trim(), inviteRole)
    setInviting(false)

    if (success) {
      setInviteEmail('')
      setShowInviteForm(false)
    }
  }

  const handleRemoveMember = async (memberId: string) => {
    setRemovingMemberId(memberId)
    await removeMember(memberId)
    setRemovingMemberId(null)
  }

  const handleRoleChange = async (memberId: string, newRole: TenantRole) => {
    await updateMemberRole(memberId, newRole)
  }

  if (!tenant) {
    return (
      <div className={`p-8 text-center text-gray-500 ${className}`}>
        No organization selected
      </div>
    )
  }

  return (
    <div className={`bg-engine-dark rounded-lg border border-gray-700 ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">{tenant.displayName}</h2>
            <p className="text-sm text-gray-500">{tenant.name}</p>
          </div>
          <div className="text-sm text-gray-400">
            {activeTenantMembers.length} / {tenant.quota.maxMembers} members
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Members List */}
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-gray-400" />
            <h3 className="font-medium">Members</h3>
          </div>

          {canManageMembers && activeTenantMembers.length < tenant.quota.maxMembers && (
            <button
              onClick={() => setShowInviteForm(true)}
              className="
                flex items-center gap-1.5
                px-3 py-1.5
                bg-engine-primary hover:bg-blue-600
                rounded text-sm font-medium
                transition-colors
              "
            >
              <Plus className="w-4 h-4" />
              Invite
            </button>
          )}
        </div>

        {/* Invite Form */}
        {showInviteForm && (
          <form onSubmit={handleInvite} className="mb-4 p-4 bg-engine-darker rounded-lg">
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-xs text-gray-500 mb-1">Email</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@company.com"
                  className="
                    w-full px-3 py-2
                    bg-engine-dark border border-gray-600
                    rounded text-sm
                    focus:outline-none focus:border-engine-primary
                  "
                />
              </div>
              <div className="w-32">
                <label className="block text-xs text-gray-500 mb-1">Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as TenantRole)}
                  className="
                    w-full px-3 py-2
                    bg-engine-dark border border-gray-600
                    rounded text-sm
                    focus:outline-none focus:border-engine-primary
                  "
                >
                  <option value="viewer">Viewer</option>
                  <option value="developer">Developer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button
                type="button"
                onClick={() => setShowInviteForm(false)}
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!inviteEmail.trim() || inviting}
                className="
                  flex items-center gap-1.5
                  px-3 py-1.5
                  bg-engine-primary hover:bg-blue-600
                  rounded text-sm font-medium
                  disabled:opacity-50
                  transition-colors
                "
              >
                {inviting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Mail className="w-4 h-4" />
                )}
                Send Invite
              </button>
            </div>
          </form>
        )}

        {/* Members Table */}
        {detailsLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 text-gray-400 animate-spin" />
          </div>
        ) : (
          <div className="space-y-2">
            {activeTenantMembers.map((member) => (
              <MemberRow
                key={member.id}
                member={member}
                canManage={canManageMembers && member.role !== 'owner'}
                isRemoving={removingMemberId === member.id}
                onRoleChange={(role) => handleRoleChange(member.id, role)}
                onRemove={() => handleRemoveMember(member.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Quota Info */}
      <div className="p-4 border-t border-gray-700">
        <h3 className="text-sm font-medium mb-3">Organization Limits</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <QuotaItem
            label="Members"
            used={activeTenantMembers.length}
            max={tenant.quota.maxMembers}
          />
          <QuotaItem
            label="Cells"
            used={tenant.cellCount}
            max={tenant.quota.maxCells}
          />
          <QuotaItem
            label="Storage"
            used={formatBytes(tenant.quota.usedStorageBytes)}
            max={formatBytes(tenant.quota.maxStorageBytes)}
            isString
          />
          <QuotaItem
            label="Versions/Cell"
            used="-"
            max={String(tenant.quota.maxVersionsPerCell)}
            isString
          />
        </div>
      </div>
    </div>
  )
}

// Member Row
interface MemberRowProps {
  member: TenantMember
  canManage: boolean
  isRemoving: boolean
  onRoleChange: (role: TenantRole) => void
  onRemove: () => void
}

function MemberRow({ member, canManage, isRemoving, onRoleChange, onRemove }: MemberRowProps) {
  const [showRoleDropdown, setShowRoleDropdown] = useState(false)
  const roleConfig = ROLE_CONFIG[member.role]

  return (
    <div className="flex items-center gap-3 p-3 bg-engine-darker rounded-lg">
      {/* Avatar */}
      {member.avatarUrl ? (
        <img
          src={member.avatarUrl}
          alt={member.displayName}
          className="w-10 h-10 rounded-full"
        />
      ) : (
        <div className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 font-medium">
          {member.displayName.charAt(0).toUpperCase()}
        </div>
      )}

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="font-medium truncate">{member.displayName}</div>
        <div className="text-sm text-gray-500 truncate">{member.email}</div>
      </div>

      {/* Role */}
      <div className="relative">
        <button
          onClick={() => canManage && setShowRoleDropdown(!showRoleDropdown)}
          disabled={!canManage}
          className={`
            flex items-center gap-1.5 px-2.5 py-1.5
            rounded text-sm
            ${roleConfig.color}
            ${canManage ? 'hover:bg-gray-700 cursor-pointer' : 'cursor-default'}
          `}
        >
          {roleConfig.icon}
          {roleConfig.label}
          {canManage && <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {showRoleDropdown && (
          <div className="absolute right-0 top-full mt-1 w-36 bg-engine-dark border border-gray-700 rounded-lg shadow-xl z-10 overflow-hidden">
            {(['admin', 'developer', 'viewer'] as TenantRole[]).map((role) => {
              const config = ROLE_CONFIG[role]
              return (
                <button
                  key={role}
                  onClick={() => {
                    onRoleChange(role)
                    setShowRoleDropdown(false)
                  }}
                  className={`
                    w-full flex items-center gap-2 px-3 py-2 text-sm
                    ${member.role === role ? 'bg-gray-700' : 'hover:bg-gray-700'}
                    ${config.color}
                  `}
                >
                  {config.icon}
                  {config.label}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Remove */}
      {canManage && (
        <button
          onClick={onRemove}
          disabled={isRemoving}
          className="p-2 text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50"
          title="Remove member"
        >
          {isRemoving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Trash2 className="w-4 h-4" />
          )}
        </button>
      )}
    </div>
  )
}

// Quota Item
interface QuotaItemProps {
  label: string
  used: number | string
  max: number | string
  isString?: boolean
}

function QuotaItem({ label, used, max, isString = false }: QuotaItemProps) {
  const usedNum = typeof used === 'number' ? used : 0
  const maxNum = typeof max === 'number' ? max : 0
  const percentage = !isString && maxNum > 0 ? (usedNum / maxNum) * 100 : 0

  return (
    <div>
      <div className="flex justify-between text-gray-400 mb-1">
        <span>{label}</span>
        <span>
          {used} / {max}
        </span>
      </div>
      {!isString && (
        <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${
              percentage > 90 ? 'bg-red-500' : percentage > 70 ? 'bg-yellow-500' : 'bg-green-500'
            }`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      )}
    </div>
  )
}

// Helper
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}
