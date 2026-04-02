import { useEffect, useState } from 'react'
import {
  useLLMConfigStore,
  ROLE_META,
  type ModelRoleConfig,
} from '../../stores/llmConfigStore'
import {
  Settings,
  Save,
  RotateCcw,
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Loader2,
  FileText,
  Cpu,
} from 'lucide-react'

const PROVIDER_OPTIONS = [
  { value: 'anthropic', label: 'Anthropic (Direct SDK)' },
  { value: 'openrouter', label: 'OpenRouter' },
]

const TOKEN_PRESETS = [2048, 4096, 8192, 16384, 32768, 65536, 131072]

export function LLMConfigEditor() {
  const {
    config,
    isLoading,
    isSaving,
    error,
    lastSaved,
    validation,
    editedModels,
    isDirty,
    fetchConfig,
    updateRole,
    saveConfig,
    validateConfig,
    resetChanges,
    reloadConfig,
  } = useLLMConfigStore()

  const [expandedRole, setExpandedRole] = useState<string | null>(null)

  useEffect(() => {
    fetchConfig()
  }, [fetchConfig])

  const handleSave = async () => {
    const result = await validateConfig()
    if (result.valid) {
      await saveConfig()
    }
  }

  if (isLoading && !config) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        Loading LLM configuration...
      </div>
    )
  }

  if (error && !config) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
        <XCircle className="w-8 h-8 text-red-400" />
        <p className="text-red-400">Failed to load config</p>
        <p className="text-sm text-gray-500">{error}</p>
        <button
          onClick={fetchConfig}
          className="px-3 py-1.5 bg-engine-primary hover:bg-blue-600 rounded text-sm"
        >
          Retry
        </button>
      </div>
    )
  }

  const roles = Object.keys(editedModels)

  return (
    <div className="h-full flex flex-col bg-engine-dark">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5 text-engine-primary" />
          <h2 className="text-sm font-semibold">LLM Configuration</h2>
          {config?.source === 'fallback' && (
            <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded">
              Fallback
            </span>
          )}
          {config?.source === 'yaml' && (
            <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded">
              YAML
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Last saved indicator */}
          {lastSaved && (
            <span className="text-xs text-gray-500">
              Saved {new Date(lastSaved).toLocaleTimeString()}
            </span>
          )}

          {/* Reload from disk */}
          <button
            onClick={reloadConfig}
            disabled={isLoading}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition"
            title="Reload from YAML"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          {/* Reset changes */}
          <button
            onClick={resetChanges}
            disabled={!isDirty}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition ${
              isDirty
                ? 'text-gray-300 hover:bg-gray-700'
                : 'text-gray-600 cursor-not-allowed'
            }`}
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={!isDirty || isSaving}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition ${
              isDirty
                ? 'bg-engine-primary hover:bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-500 cursor-not-allowed'
            }`}
          >
            {isSaving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {/* Validation Messages */}
      {validation && !validation.valid && (
        <div className="mx-4 mt-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
          <div className="flex items-center gap-2 text-red-400 text-sm font-medium mb-1">
            <XCircle className="w-4 h-4" />
            Validation Failed
          </div>
          {validation.errors.map((err, i) => (
            <p key={i} className="text-xs text-red-300 ml-6">
              {err}
            </p>
          ))}
        </div>
      )}

      {validation && validation.valid && validation.warnings.length > 0 && (
        <div className="mx-4 mt-3 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-1">
            <AlertTriangle className="w-4 h-4" />
            Warnings
          </div>
          {validation.warnings.map((warn, i) => (
            <p key={i} className="text-xs text-yellow-300 ml-6">
              {warn}
            </p>
          ))}
        </div>
      )}

      {validation && validation.valid && validation.warnings.length === 0 && (
        <div className="mx-4 mt-3 p-2 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-green-400" />
          <span className="text-xs text-green-400">Configuration saved successfully</span>
        </div>
      )}

      {/* Error banner */}
      {error && config && (
        <div className="mx-4 mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-400" />
          <span className="text-xs text-red-400">{error}</span>
        </div>
      )}

      {/* Role Cards */}
      <div className="flex-1 overflow-auto p-4 space-y-2">
        {roles.map((role) => {
          const meta = ROLE_META[role] || { label: role, icon: '⚙️', color: 'text-gray-400' }
          const edited = editedModels[role]
          const original = config?.models[role]
          const isChanged =
            original &&
            (original.model !== edited.model ||
              original.provider !== edited.provider ||
              original.max_tokens !== edited.max_tokens)
          const isExpanded = expandedRole === role

          return (
            <div
              key={role}
              className={`rounded-lg border transition ${
                isChanged
                  ? 'border-engine-primary/50 bg-engine-primary/5'
                  : 'border-gray-700 bg-engine-darker'
              }`}
            >
              {/* Compact row */}
              <button
                onClick={() => setExpandedRole(isExpanded ? null : role)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition rounded-lg"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-lg">{meta.icon}</span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${meta.color}`}>
                        {meta.label}
                      </span>
                      {isChanged && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-engine-primary/20 text-engine-primary rounded">
                          modified
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-500 truncate block">
                      {edited.model}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 font-mono">
                    {edited.provider === 'anthropic' ? 'ANT' : 'OR'}
                  </span>
                  <span className="text-xs text-gray-600">
                    {(edited.max_tokens / 1024).toFixed(0)}K
                  </span>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-gray-500" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-gray-500" />
                  )}
                </div>
              </button>

              {/* Expanded editor */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-3 border-t border-gray-700/50 pt-3">
                  {/* Description */}
                  {edited.description && (
                    <p className="text-xs text-gray-500 flex items-center gap-1.5">
                      <FileText className="w-3 h-3" />
                      {edited.description}
                    </p>
                  )}

                  {/* Provider */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Provider</label>
                    <div className="flex gap-2">
                      {PROVIDER_OPTIONS.map((opt) => (
                        <button
                          key={opt.value}
                          onClick={() => updateRole(role, 'provider', opt.value)}
                          className={`flex-1 px-3 py-2 rounded text-xs font-medium transition ${
                            edited.provider === opt.value
                              ? 'bg-engine-primary/20 text-engine-primary border border-engine-primary/40'
                              : 'bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-500'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Model */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Model ID</label>
                    <input
                      type="text"
                      value={edited.model}
                      onChange={(e) => updateRole(role, 'model', e.target.value)}
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 focus:border-engine-primary focus:outline-none font-mono"
                      placeholder={
                        edited.provider === 'anthropic'
                          ? 'claude-sonnet-4-20250514'
                          : 'anthropic/claude-sonnet-4.5'
                      }
                    />
                    <p className="text-[10px] text-gray-600 mt-1">
                      {edited.provider === 'anthropic'
                        ? 'Anthropic model name (no org/ prefix)'
                        : 'OpenRouter format: org/model-name'}
                    </p>
                  </div>

                  {/* Max Tokens */}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Max Tokens ({edited.max_tokens.toLocaleString()})
                    </label>
                    <div className="flex gap-1.5 flex-wrap">
                      {TOKEN_PRESETS.map((preset) => (
                        <button
                          key={preset}
                          onClick={() => updateRole(role, 'max_tokens', preset)}
                          className={`px-2 py-1 rounded text-xs font-mono transition ${
                            edited.max_tokens === preset
                              ? 'bg-engine-primary/20 text-engine-primary border border-engine-primary/40'
                              : 'bg-gray-800 text-gray-500 border border-gray-700 hover:border-gray-500'
                          }`}
                        >
                          {preset >= 1024 ? `${preset / 1024}K` : preset}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Env override hint */}
                  <div className="text-[10px] text-gray-600 bg-gray-800/50 rounded px-2 py-1.5 font-mono">
                    Override: LLM_MODEL_{role.toUpperCase()}={edited.model}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-gray-700 flex items-center justify-between text-[10px] text-gray-600">
        <span>
          {config?.yaml_path && (
            <>
              <FileText className="w-3 h-3 inline mr-1" />
              {config.yaml_path.split(/[/\\]/).slice(-2).join('/')}
            </>
          )}
        </span>
        <span>{roles.length} roles configured</span>
      </div>
    </div>
  )
}
