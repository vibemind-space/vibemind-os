// front/src/components/engine/SettingsPanel.tsx
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useLLMConfig, useUpdateModelRole, useUpdateLLMConfig } from '@/hooks/useLLMConfig';
import {
  PROVIDERS, POPULAR_MODELS, MODEL_ROLES, MODEL_PRESETS,
  type ProviderId, type ModelRole, type ModelRoleConfig,
} from '@/services/llmConfigApi';
import { API_URL } from '@/services/api';
import {
  Settings, Cpu, Zap, Check, AlertTriangle, Loader2, ChevronDown,
  Server, Database, HardDrive, Container, Globe, ToggleLeft, ToggleRight,
  Plug, Sparkles, Key, Eye, EyeOff, Save, X,
} from 'lucide-react';

// ─── Parallelism Slider ──────────────────────────────────────────────

function ParallelismSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  const labels = ['Sequential', '2 parallel', '3 parallel', '4 parallel', '5 parallel'];
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-foreground">Parallelism</label>
        <span className="text-xs font-mono text-primary">{labels[value - 1]}</span>
      </div>
      <input
        type="range"
        min={1}
        max={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-muted rounded-full appearance-none cursor-pointer
          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
          [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-md
          [&::-webkit-slider-thumb]:hover:bg-primary/80 [&::-webkit-slider-thumb]:transition"
      />
      <div className="flex justify-between text-[9px] text-muted-foreground px-0.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <span key={n} className={n === value ? 'text-primary font-semibold' : ''}>{n}</span>
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground/60">
        Higher parallelism = faster generation, but more API calls. File conflicts are auto-detected.
      </p>
    </div>
  );
}

// ─── Model Role Row ──────────────────────────────────────────────────

function ModelRoleRow({
  role,
  config,
  onUpdate,
  isPending,
}: {
  role: ModelRole;
  config: ModelRoleConfig;
  onUpdate: (role: ModelRole, config: ModelRoleConfig) => void;
  isPending: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [provider, setProvider] = useState<ProviderId>(config.provider as ProviderId);
  const [model, setModel] = useState(config.model);
  const [maxTokens, setMaxTokens] = useState(config.max_tokens);
  const [customUrl, setCustomUrl] = useState('');
  const [dirty, setDirty] = useState(false);

  const info = MODEL_ROLES[role];
  const models = POPULAR_MODELS[provider] || [];

  useEffect(() => {
    setProvider(config.provider as ProviderId);
    setModel(config.model);
    setMaxTokens(config.max_tokens);
    setDirty(false);
  }, [config]);

  const handleProviderChange = (p: ProviderId) => {
    setProvider(p);
    // Auto-select first popular model for new provider
    const firstModel = POPULAR_MODELS[p]?.[0] || '';
    setModel(firstModel);
    setDirty(true);
  };

  const handleSave = () => {
    onUpdate(role, { provider, model, max_tokens: maxTokens });
    setDirty(false);
  };

  return (
    <div className="border border-border/30 rounded-lg overflow-hidden">
      {/* Header row - always visible */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/30 transition text-left"
      >
        <Cpu className="w-3 h-3 text-muted-foreground shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-xs font-medium">{info.label}</span>
          <span className="text-[10px] text-muted-foreground ml-2">{info.desc}</span>
        </div>
        <span className="text-[10px] font-mono text-primary/80 truncate max-w-[200px]">
          {config.provider}/{config.model}
        </span>
        <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Expanded config */}
      {isOpen && (
        <div className="px-3 pb-3 pt-1 space-y-2 bg-muted/10 border-t border-border/20">
          {/* Provider Select */}
          <div className="grid grid-cols-3 gap-1.5">
            {(Object.keys(PROVIDERS) as ProviderId[]).map((p) => (
              <button
                key={p}
                onClick={() => handleProviderChange(p)}
                className={`text-[10px] px-2 py-1 rounded border transition ${
                  provider === p
                    ? 'bg-primary/15 border-primary/40 text-primary font-medium'
                    : 'bg-muted/30 border-border/30 text-muted-foreground hover:text-foreground hover:border-border/50'
                }`}
              >
                {PROVIDERS[p].label}
              </button>
            ))}
          </div>

          {/* Custom URL (only for custom/ollama) */}
          {(provider === 'custom' || provider === 'ollama') && (
            <input
              type="text"
              value={customUrl || PROVIDERS[provider].baseUrl || ''}
              onChange={(e) => { setCustomUrl(e.target.value); setDirty(true); }}
              placeholder="http://localhost:11434/v1"
              className="w-full text-[11px] px-2 py-1 rounded border border-border/30 bg-background
                placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none"
            />
          )}

          {/* Model Select or Input */}
          <div className="flex gap-1.5">
            <div className="flex-1 relative">
              <input
                type="text"
                value={model}
                onChange={(e) => { setModel(e.target.value); setDirty(true); }}
                placeholder="Model name..."
                className="w-full text-[11px] px-2 py-1 rounded border border-border/30 bg-background
                  placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none"
                list={`models-${role}`}
              />
              <datalist id={`models-${role}`}>
                {models.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </div>
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => { setMaxTokens(Number(e.target.value)); setDirty(true); }}
              className="w-20 text-[11px] px-2 py-1 rounded border border-border/30 bg-background
                text-right focus:border-primary/50 focus:outline-none"
              min={256}
              max={200000}
              step={1024}
            />
          </div>

          {/* Quick model chips */}
          {models.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {models.slice(0, 4).map((m) => (
                <button
                  key={m}
                  onClick={() => { setModel(m); setDirty(true); }}
                  className={`text-[9px] px-1.5 py-0.5 rounded border transition ${
                    model === m
                      ? 'bg-primary/15 border-primary/30 text-primary'
                      : 'bg-muted/20 border-border/20 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {m.split('/').pop()}
                </button>
              ))}
            </div>
          )}

          {/* Save button */}
          {dirty && (
            <button
              onClick={handleSave}
              disabled={isPending}
              className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium bg-primary/15 text-primary
                border border-primary/30 rounded hover:bg-primary/25 transition disabled:opacity-50"
            >
              {isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
              Apply
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── API Keys Section ────────────────────────────────────────────────

interface APIKeyStatus {
  env_var: string;
  provider: string;
  is_set: boolean;
  preview: string | null;
}

function APIKeyRow({
  keyInfo,
  onSave,
  isSaving,
}: {
  keyInfo: APIKeyStatus;
  onSave: (envVar: string, value: string) => void;
  isSaving: boolean;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [value, setValue] = useState('');
  const [showValue, setShowValue] = useState(false);

  const handleSave = () => {
    if (value.trim()) {
      onSave(keyInfo.env_var, value.trim());
      setValue('');
      setIsEditing(false);
    }
  };

  return (
    <div className={`flex items-center gap-2 px-3 py-2 border rounded-lg transition ${
      keyInfo.is_set ? 'border-border/30' : 'border-yellow-500/25 bg-yellow-500/5'
    }`}>
      <Key className={`w-3 h-3 shrink-0 ${keyInfo.is_set ? 'text-green-400' : 'text-yellow-400'}`} />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-medium">{keyInfo.provider}</div>
        <div className="text-[9px] font-mono text-muted-foreground/60">
          {keyInfo.is_set ? keyInfo.preview : 'not set'}
        </div>
      </div>

      {isEditing ? (
        <div className="flex items-center gap-1">
          <div className="relative">
            <input
              type={showValue ? 'text' : 'password'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={`${keyInfo.env_var}...`}
              className="w-40 text-[10px] font-mono px-2 py-1 pr-6 rounded border border-primary/30 bg-background
                placeholder:text-muted-foreground/30 focus:border-primary/50 focus:outline-none"
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') setIsEditing(false); }}
            />
            <button
              onClick={() => setShowValue(!showValue)}
              className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground"
            >
              {showValue ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            </button>
          </div>
          <button
            onClick={handleSave}
            disabled={!value.trim() || isSaving}
            className="p-1 text-green-400 hover:text-green-300 disabled:opacity-30"
          >
            <Save className="w-3 h-3" />
          </button>
          <button
            onClick={() => { setIsEditing(false); setValue(''); }}
            className="p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      ) : (
        <button
          onClick={() => setIsEditing(true)}
          className={`text-[9px] px-2 py-0.5 rounded border transition ${
            keyInfo.is_set
              ? 'border-border/30 text-muted-foreground hover:text-foreground hover:border-border/50'
              : 'border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/10 font-medium'
          }`}
        >
          {keyInfo.is_set ? 'change' : 'set key'}
        </button>
      )}
    </div>
  );
}

function APIKeysSection() {
  const queryClient = useQueryClient();

  const { data: keys, isLoading } = useQuery<APIKeyStatus[]>({
    queryKey: ['api-keys'],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/llm-config/api-keys`);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      return res.json();
    },
    staleTime: 30000,
  });

  const saveMutation = useMutation({
    mutationFn: async ({ envVar, value }: { envVar: string; value: string }) => {
      const res = await fetch(`${API_URL}/llm-config/api-keys`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ env_var: envVar, value }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-2 justify-center text-muted-foreground">
        <Loader2 className="w-3 h-3 animate-spin" />
        <span className="text-[10px]">Loading keys...</span>
      </div>
    );
  }

  const missingCount = keys?.filter((k) => !k.is_set).length || 0;

  return (
    <div className="space-y-1.5">
      {saveMutation.isSuccess && (
        <div className="flex items-center gap-1.5 px-2 py-1 bg-green-500/10 border border-green-500/25 rounded text-[10px] text-green-400">
          <Check className="w-3 h-3" />
          Key saved & active
        </div>
      )}
      {saveMutation.isError && (
        <div className="flex items-center gap-1.5 px-2 py-1 bg-red-500/10 border border-red-500/25 rounded text-[10px] text-red-400">
          <AlertTriangle className="w-3 h-3" />
          {(saveMutation.error as Error).message}
        </div>
      )}
      {keys?.map((k) => (
        <APIKeyRow
          key={k.env_var}
          keyInfo={k}
          onSave={(envVar, value) => saveMutation.mutate({ envVar, value })}
          isSaving={saveMutation.isPending}
        />
      ))}
      {missingCount > 0 && (
        <p className="text-[9px] text-yellow-400/60 px-1">
          {missingCount} key{missingCount > 1 ? 's' : ''} missing — some providers won't work
        </p>
      )}
    </div>
  );
}

// ─── MCP Server Config ──────────────────────────────────────────────

const SERVER_ICONS: Record<string, typeof Server> = {
  filesystem: HardDrive,
  docker: Container,
  postgres: Database,
  prisma: Database,
  redis: Database,
  playwright: Globe,
  npm: Server,
  git: Server,
};

interface MCPServerOverride {
  enabled: boolean;
  env_vars: Record<string, string>;
  args_override: string[];
  notes: string;
}

interface MCPConfig {
  project_id: string;
  project_path: string;
  output_dir: string;
  sandbox_container: string;
  vnc_port: number;
  app_port: number;
  servers: Record<string, MCPServerOverride>;
}

function MCPServerRow({
  name,
  config,
  onToggle,
  onUpdateEnv,
}: {
  name: string;
  config: MCPServerOverride;
  onToggle: () => void;
  onUpdateEnv: (key: string, value: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const Icon = SERVER_ICONS[name] || Plug;
  const envEntries = Object.entries(config.env_vars || {});

  return (
    <div className={`border rounded-lg overflow-hidden transition ${
      config.enabled ? 'border-border/30' : 'border-border/15 opacity-60'
    }`}>
      <div className="flex items-center gap-2 px-3 py-1.5">
        <Icon className="w-3 h-3 text-muted-foreground shrink-0" />
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex-1 text-left text-xs font-medium hover:text-foreground transition"
        >
          {name}
        </button>
        {config.notes && (
          <span className="text-[9px] text-muted-foreground/60 truncate max-w-[180px]">
            {config.notes}
          </span>
        )}
        <button onClick={onToggle} className="shrink-0">
          {config.enabled
            ? <ToggleRight className="w-4 h-4 text-green-400" />
            : <ToggleLeft className="w-4 h-4 text-muted-foreground" />
          }
        </button>
      </div>

      {isOpen && config.enabled && envEntries.length > 0 && (
        <div className="px-3 pb-2 pt-1 space-y-1 bg-muted/10 border-t border-border/20">
          {envEntries.map(([key, value]) => (
            <div key={key} className="flex gap-1.5 items-center">
              <span className="text-[9px] font-mono text-muted-foreground w-28 shrink-0 truncate">
                {key}
              </span>
              <input
                type="text"
                value={value}
                onChange={(e) => onUpdateEnv(key, e.target.value)}
                className="flex-1 text-[10px] font-mono px-1.5 py-0.5 rounded border border-border/30 bg-background
                  focus:border-primary/50 focus:outline-none"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MCPConfigSection({ projectName }: { projectName: string }) {
  const queryClient = useQueryClient();

  const { data: mcpConfig, isLoading, error } = useQuery<MCPConfig>({
    queryKey: ['mcp-config', projectName],
    queryFn: async () => {
      const projectPath = `/data/projects/${projectName}`;
      const res = await fetch(`${API_URL}/dashboard/project/mcp-config?project_path=${encodeURIComponent(projectPath)}`);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      return res.json();
    },
    staleTime: 60000,
    retry: 1,
  });

  const updateMutation = useMutation({
    mutationFn: async (updates: Record<string, unknown>) => {
      const projectPath = `/data/projects/${projectName}`;
      const res = await fetch(`${API_URL}/dashboard/project/mcp-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: projectPath, updates }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['mcp-config', projectName], data);
    },
  });

  const handleToggle = (serverName: string) => {
    if (!mcpConfig) return;
    const current = mcpConfig.servers[serverName];
    updateMutation.mutate({
      servers: {
        [serverName]: { enabled: !current?.enabled },
      },
    });
  };

  const handleUpdateEnv = (serverName: string, key: string, value: string) => {
    updateMutation.mutate({
      servers: {
        [serverName]: { env_vars: { [key]: value } },
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 justify-center text-muted-foreground">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span className="text-[10px]">Loading MCP config...</span>
      </div>
    );
  }

  if (error || !mcpConfig) {
    return (
      <div className="flex items-center gap-2 p-2 bg-muted/20 border border-border/20 rounded text-[10px] text-muted-foreground">
        <Server className="w-3.5 h-3.5" />
        No MCP config yet. Start generation to auto-configure.
      </div>
    );
  }

  const serverEntries = Object.entries(mcpConfig.servers);

  return (
    <div className="space-y-1.5">
      {/* Project context summary */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px] text-muted-foreground/70 px-1 mb-2">
        <span>Sandbox: <code className="text-primary/60">{mcpConfig.sandbox_container}</code></span>
        <span>VNC: <code className="text-primary/60">:{mcpConfig.vnc_port}</code></span>
        <span>Output: <code className="text-primary/60 truncate">{mcpConfig.output_dir.split('/').slice(-2).join('/')}</code></span>
        <span>App: <code className="text-primary/60">:{mcpConfig.app_port}</code></span>
      </div>

      {serverEntries.length === 0 ? (
        <div className="text-[10px] text-muted-foreground/50 text-center py-2">
          No servers configured
        </div>
      ) : (
        serverEntries.map(([name, srv]) => (
          <MCPServerRow
            key={name}
            name={name}
            config={srv}
            onToggle={() => handleToggle(name)}
            onUpdateEnv={(key, value) => handleUpdateEnv(name, key, value)}
          />
        ))
      )}

      {updateMutation.isError && (
        <div className="text-[10px] text-red-400 px-1">
          {(updateMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}

// ─── Backend Selector ────────────────────────────────────────────────

type Backend = 'kilo' | 'claude' | 'openrouter';

interface BackendAuthStatus {
  ready: boolean;
  reason: string;
}

interface BackendData {
  active_backend: Backend;
  active_model: string;
  auth_status?: Record<Backend, BackendAuthStatus>;
}

const BACKENDS: { id: Backend; label: string; desc: string; badge?: string; badgeColor?: string; keyEnvVar?: string; keyLabel?: string }[] = [
  { id: 'kilo', label: 'Kilo CLI', desc: 'Free — Kilo Code CLI', badge: 'FREE', badgeColor: 'green', keyEnvVar: 'OPENROUTER_API_KEY', keyLabel: 'OpenRouter Key' },
  { id: 'claude', label: 'Claude CLI', desc: 'Claude Code CLI (needs API key)', badge: 'PRO', badgeColor: 'purple', keyEnvVar: 'ANTHROPIC_API_KEY', keyLabel: 'Anthropic Key' },
  { id: 'openrouter', label: 'OpenRouter', desc: 'OpenRouter API (free models)', badge: 'API', badgeColor: 'yellow', keyEnvVar: 'OPENROUTER_API_KEY', keyLabel: 'OpenRouter Key' },
];

function BackendSelector() {
  const queryClient = useQueryClient();
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [keyValue, setKeyValue] = useState('');
  const [showKey, setShowKey] = useState(false);

  const { data, isLoading } = useQuery<BackendData>({
    queryKey: ['pipeline-backend'],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/dashboard/pipeline/backend`);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      return res.json();
    },
    staleTime: 10000,
  });

  const mutation = useMutation({
    mutationFn: async (backend: Backend) => {
      const res = await fetch(`${API_URL}/dashboard/pipeline/backend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backend }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline-backend'] });
    },
  });

  const saveKeyMutation = useMutation({
    mutationFn: async ({ envVar, value }: { envVar: string; value: string }) => {
      const res = await fetch(`${API_URL}/llm-config/api-keys`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ env_var: envVar, value }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      return res.json();
    },
    onSuccess: () => {
      setEditingKey(null);
      setKeyValue('');
      setShowKey(false);
      queryClient.invalidateQueries({ queryKey: ['pipeline-backend'] });
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
    },
  });

  const current = data?.active_backend || 'kilo';
  const authStatus = data?.auth_status;

  return (
    <div className="space-y-2">
      {isLoading ? (
        <div className="flex items-center gap-2 py-2 justify-center text-muted-foreground">
          <Loader2 className="w-3 h-3 animate-spin" />
          <span className="text-[10px]">Loading...</span>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-1.5">
          {BACKENDS.map((b) => {
            const isActive = current === b.id;
            const auth = authStatus?.[b.id];
            const badgeColors: Record<string, string> = {
              green:  'bg-green-500/15 text-green-400 border-green-500/30',
              purple: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
              yellow: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
            };
            return (
              <button
                key={b.id}
                onClick={() => mutation.mutate(b.id)}
                disabled={mutation.isPending}
                className={`flex flex-col items-center gap-1 px-2 py-2 rounded-lg border transition text-center ${
                  isActive
                    ? 'bg-primary/15 border-primary/40 text-primary'
                    : 'bg-muted/20 border-border/30 text-muted-foreground hover:text-foreground hover:border-border/50'
                } disabled:opacity-50`}
              >
                {b.badge && (
                  <span className={`text-[8px] font-bold px-1 py-0.5 rounded border ${badgeColors[b.badgeColor || 'green']}`}>
                    {b.badge}
                  </span>
                )}
                <span className="text-[10px] font-medium">{b.label}</span>
                <span className="text-[8px] text-muted-foreground/60 leading-tight">{b.desc}</span>
                {auth && (
                  <span className={`text-[8px] flex items-center gap-0.5 mt-0.5 ${auth.ready ? 'text-green-400' : 'text-red-400'}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${auth.ready ? 'bg-green-400' : 'bg-red-400'}`} />
                    {auth.ready ? 'Ready' : 'Not ready'}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Auth warning + inline key setup for active backend */}
      {authStatus && !authStatus[current]?.ready && (() => {
        const backendDef = BACKENDS.find((b) => b.id === current);
        const envVar = backendDef?.keyEnvVar;
        const isEditing = editingKey === envVar;
        return (
          <div className="px-2 py-1.5 bg-yellow-500/10 border border-yellow-500/25 rounded space-y-1.5">
            <div className="flex items-center gap-1.5 text-[10px] text-yellow-400">
              <AlertTriangle className="w-3 h-3 shrink-0" />
              <span>{authStatus[current]?.reason}</span>
            </div>
            {envVar && !isEditing && (
              <button
                onClick={() => { setEditingKey(envVar); setKeyValue(''); setShowKey(false); }}
                className="flex items-center gap-1 text-[9px] px-2 py-1 rounded border border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/10 font-medium transition"
              >
                <Key className="w-3 h-3" />
                Set {backendDef?.keyLabel || envVar}
              </button>
            )}
            {envVar && isEditing && (
              <div className="flex items-center gap-1">
                <div className="relative flex-1">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={keyValue}
                    onChange={(e) => setKeyValue(e.target.value)}
                    placeholder={`${envVar}...`}
                    className="w-full text-[10px] font-mono px-2 py-1 pr-6 rounded border border-primary/30 bg-background
                      placeholder:text-muted-foreground/30 focus:border-primary/50 focus:outline-none"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && keyValue.trim()) saveKeyMutation.mutate({ envVar, value: keyValue.trim() });
                      if (e.key === 'Escape') { setEditingKey(null); setKeyValue(''); }
                    }}
                  />
                  <button
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-1 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground"
                  >
                    {showKey ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                  </button>
                </div>
                <button
                  onClick={() => { if (keyValue.trim()) saveKeyMutation.mutate({ envVar, value: keyValue.trim() }); }}
                  disabled={!keyValue.trim() || saveKeyMutation.isPending}
                  className="p-1 text-green-400 hover:text-green-300 disabled:opacity-30"
                >
                  {saveKeyMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                </button>
                <button
                  onClick={() => { setEditingKey(null); setKeyValue(''); }}
                  className="p-1 text-muted-foreground hover:text-foreground"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
            {saveKeyMutation.isError && (
              <div className="text-[9px] text-red-400">{(saveKeyMutation.error as Error).message}</div>
            )}
          </div>
        );
      })()}

      {/* Key saved confirmation */}
      {saveKeyMutation.isSuccess && (
        <div className="flex items-center gap-1.5 px-2 py-1 bg-green-500/10 border border-green-500/25 rounded text-[10px] text-green-400">
          <Check className="w-3 h-3" />
          Key saved — backend ready
        </div>
      )}

      {mutation.isSuccess && (
        <div className="flex items-center gap-1.5 px-2 py-1 bg-green-500/10 border border-green-500/25 rounded text-[10px] text-green-400">
          <Check className="w-3 h-3" />
          Backend switched to {current}
        </div>
      )}
      {mutation.isError && (
        <div className="flex items-center gap-1.5 px-2 py-1 bg-red-500/10 border border-red-500/25 rounded text-[10px] text-red-400">
          <AlertTriangle className="w-3 h-3" />
          {(mutation.error as Error).message}
        </div>
      )}
      {data?.active_model && (
        <p className="text-[9px] text-muted-foreground/60 px-1">
          Active model: <code className="text-primary/60">{data.active_model}</code>
        </p>
      )}
    </div>
  );
}

// ─── Main Settings Panel ─────────────────────────────────────────────

interface SettingsPanelProps {
  projectName: string;
  parallelism: number;
  onParallelismChange: (v: number) => void;
}

export function SettingsPanel({ projectName, parallelism, onParallelismChange }: SettingsPanelProps) {
  const { data: llmConfig, isLoading, error } = useLLMConfig();
  const updateRole = useUpdateModelRole();
  const updateAllRoles = useUpdateLLMConfig();

  const handleUpdateRole = (role: ModelRole, config: ModelRoleConfig) => {
    updateRole.mutate({ role, config });
  };

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Settings className="w-4 h-4 text-primary" />
        <h3 className="text-sm font-semibold">Generation Settings</h3>
      </div>

      {/* Parallelism */}
      <div className="p-3 bg-muted/10 border border-border/20 rounded-lg">
        <div className="flex items-center gap-1.5 mb-3">
          <Zap className="w-3.5 h-3.5 text-yellow-400" />
          <span className="text-xs font-medium">Task Parallelism</span>
        </div>
        <ParallelismSlider value={parallelism} onChange={onParallelismChange} />
      </div>

      {/* Code Generation Backend */}
      <div className="p-3 bg-muted/10 border border-border/20 rounded-lg space-y-2">
        <div className="flex items-center gap-1.5">
          <Server className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-medium">Code Generation Backend</span>
          <span className="text-[9px] px-1.5 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/25 rounded">
            Stage 2
          </span>
        </div>
        <BackendSelector />
      </div>

      {/* API Keys */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Key className="w-3.5 h-3.5 text-orange-400" />
          <span className="text-xs font-medium">API Keys</span>
        </div>
        <APIKeysSection />
      </div>

      {/* Model Configuration */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-blue-400" />
          <span className="text-xs font-medium">Model Configuration</span>
          {llmConfig?.source === 'fallback' && (
            <span className="text-[9px] px-1.5 py-0.5 bg-yellow-500/10 text-yellow-400 border border-yellow-500/25 rounded">
              fallback
            </span>
          )}
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 py-4 justify-center text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-xs">Loading config...</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/25 rounded text-xs text-red-400">
            <AlertTriangle className="w-3.5 h-3.5" />
            Failed to load LLM config
          </div>
        )}

        {updateRole.isError && (
          <div className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/25 rounded text-xs text-red-400">
            <AlertTriangle className="w-3.5 h-3.5" />
            {(updateRole.error as Error).message}
          </div>
        )}

        {(updateRole.isSuccess || updateAllRoles.isSuccess) && (
          <div className="flex items-center gap-2 p-2 bg-green-500/10 border border-green-500/25 rounded text-xs text-green-400">
            <Check className="w-3.5 h-3.5" />
            {updateAllRoles.isSuccess ? 'Preset applied — all roles updated' : 'Config saved & reloaded'}
          </div>
        )}

        {updateAllRoles.isError && (
          <div className="flex items-center gap-2 p-2 bg-red-500/10 border border-red-500/25 rounded text-xs text-red-400">
            <AlertTriangle className="w-3.5 h-3.5" />
            {(updateAllRoles.error as Error).message}
          </div>
        )}

        {/* Presets */}
        {llmConfig && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 mb-1">
              <Sparkles className="w-3 h-3 text-amber-400" />
              <span className="text-[10px] font-medium text-muted-foreground">Quick Presets</span>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {Object.entries(MODEL_PRESETS).map(([key, preset]) => {
                const badgeColors: Record<string, string> = {
                  green:  'bg-green-500/15 text-green-400 border-green-500/30',
                  purple: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
                  yellow: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
                };
                return (
                  <button
                    key={key}
                    onClick={() => {
                      // Apply all 7 roles in one API call
                      updateAllRoles.mutate(preset.models);
                    }}
                    disabled={updateRole.isPending || updateAllRoles.isPending}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] rounded-lg border
                      border-border/30 bg-muted/20 hover:bg-muted/40 hover:border-border/50
                      transition disabled:opacity-50 group"
                    title={preset.description}
                  >
                    {preset.badge && (
                      <span className={`text-[8px] font-bold px-1 py-0.5 rounded border ${badgeColors[preset.badgeColor || 'green']}`}>
                        {preset.badge}
                      </span>
                    )}
                    <span className="font-medium group-hover:text-foreground">{preset.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Model Roles */}
        {llmConfig && (
          <div className="space-y-1.5">
            {(Object.keys(MODEL_ROLES) as ModelRole[]).map((role) => (
              <ModelRoleRow
                key={role}
                role={role}
                config={
                  llmConfig.models[role] || {
                    provider: 'anthropic',
                    model: 'claude-sonnet-4-6',
                    max_tokens: 4096,
                  }
                }
                onUpdate={handleUpdateRole}
                isPending={updateRole.isPending}
              />
            ))}
          </div>
        )}
      </div>

      {/* MCP Server Configuration */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <Plug className="w-3.5 h-3.5 text-purple-400" />
          <span className="text-xs font-medium">MCP Server Config</span>
          <span className="text-[9px] px-1.5 py-0.5 bg-purple-500/10 text-purple-400 border border-purple-500/25 rounded">
            per project
          </span>
        </div>
        <MCPConfigSection projectName={projectName} />
      </div>

      {/* Info */}
      <p className="text-[10px] text-muted-foreground/50 leading-relaxed">
        Model changes apply immediately to new tasks. MCP config is auto-generated
        when generation starts and scoped to this project.
      </p>
    </div>
  );
}
