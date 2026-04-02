import { create } from 'zustand'

// ── Types ────────────────────────────────────────────────────────────────

export interface ModelRoleConfig {
  provider: 'anthropic' | 'openrouter'
  model: string
  max_tokens: number
  description?: string
}

export interface ProviderConfig {
  base_url: string | null
  api_key_env: string
}

export interface LLMConfig {
  providers: Record<string, ProviderConfig>
  models: Record<string, ModelRoleConfig>
  source: 'yaml' | 'fallback'
  yaml_path: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

// Role metadata for UI display
export const ROLE_META: Record<string, { label: string; icon: string; color: string }> = {
  primary: { label: 'Primary (SDK)', icon: '🔵', color: 'text-blue-400' },
  cli: { label: 'CLI', icon: '⚡', color: 'text-yellow-400' },
  mcp_standard: { label: 'MCP Standard', icon: '🟢', color: 'text-green-400' },
  mcp_agent: { label: 'MCP Agent', icon: '🤖', color: 'text-purple-400' },
  judge: { label: 'Judge', icon: '⚖️', color: 'text-orange-400' },
  reasoning: { label: 'Reasoning', icon: '🧠', color: 'text-pink-400' },
  enrichment: { label: 'Enrichment', icon: '📚', color: 'text-cyan-400' },
}

interface LLMConfigState {
  // Data
  config: LLMConfig | null
  isLoading: boolean
  isSaving: boolean
  error: string | null
  lastSaved: string | null
  validation: ValidationResult | null

  // Dirty tracking (unsaved changes)
  editedModels: Record<string, ModelRoleConfig>
  isDirty: boolean

  // Actions
  fetchConfig: () => Promise<void>
  updateRole: (role: string, field: keyof ModelRoleConfig, value: string | number) => void
  saveConfig: () => Promise<boolean>
  validateConfig: () => Promise<ValidationResult>
  resetChanges: () => void
  reloadConfig: () => Promise<void>
}

// Must use absolute URL — Electron loads from file:// protocol,
// so relative URLs resolve to filesystem paths instead of HTTP
const API_BASE = 'http://localhost:8000'

export const useLLMConfigStore = create<LLMConfigState>((set, get) => ({
  config: null,
  isLoading: false,
  isSaving: false,
  error: null,
  lastSaved: null,
  validation: null,
  editedModels: {},
  isDirty: false,

  fetchConfig: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await fetch(`${API_BASE}/api/v1/llm-config`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`)
      }
      const data: LLMConfig = await response.json()
      set({
        config: data,
        editedModels: { ...data.models },
        isLoading: false,
        isDirty: false,
        validation: null,
      })
    } catch (error) {
      set({ isLoading: false, error: String(error) })
    }
  },

  updateRole: (role, field, value) => {
    const { editedModels, config } = get()
    const current = editedModels[role]
    if (!current) return

    const updated = { ...current, [field]: value }
    const newEdited = { ...editedModels, [role]: updated }

    // Check if anything changed from original
    const original = config?.models || {}
    let dirty = false
    for (const r of Object.keys(newEdited)) {
      const orig = original[r]
      const edit = newEdited[r]
      if (!orig || orig.model !== edit.model || orig.provider !== edit.provider || orig.max_tokens !== edit.max_tokens) {
        dirty = true
        break
      }
    }

    set({ editedModels: newEdited, isDirty: dirty, validation: null })
  },

  saveConfig: async () => {
    const { editedModels } = get()
    set({ isSaving: true, error: null })
    try {
      const response = await fetch(`${API_BASE}/api/v1/llm-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ models: editedModels }),
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
        const detail = errData.detail
        if (typeof detail === 'object' && detail.errors) {
          set({
            isSaving: false,
            validation: { valid: false, errors: detail.errors, warnings: detail.warnings || [] },
          })
          return false
        }
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
      }

      const updatedConfig: LLMConfig = await response.json()
      set({
        config: updatedConfig,
        editedModels: { ...updatedConfig.models },
        isSaving: false,
        isDirty: false,
        lastSaved: new Date().toISOString(),
        validation: { valid: true, errors: [], warnings: [] },
      })
      return true
    } catch (error) {
      set({ isSaving: false, error: String(error) })
      return false
    }
  },

  validateConfig: async () => {
    const { editedModels } = get()
    try {
      const response = await fetch(`${API_BASE}/api/v1/llm-config/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ models: editedModels }),
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const result: ValidationResult = await response.json()
      set({ validation: result })
      return result
    } catch (error) {
      const result: ValidationResult = { valid: false, errors: [String(error)], warnings: [] }
      set({ validation: result })
      return result
    }
  },

  resetChanges: () => {
    const { config } = get()
    if (config) {
      set({
        editedModels: { ...config.models },
        isDirty: false,
        validation: null,
        error: null,
      })
    }
  },

  reloadConfig: async () => {
    try {
      await fetch(`${API_BASE}/api/v1/llm-config/reload`, { method: 'POST' })
      await get().fetchConfig()
    } catch (error) {
      set({ error: String(error) })
    }
  },
}))
