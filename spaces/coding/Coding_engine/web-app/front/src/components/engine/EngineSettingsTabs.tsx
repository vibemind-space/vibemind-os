/**
 * Engine Settings Tabs — wraps the existing SettingsPanel with additional tabs
 * for Discord, Generation, Fix Strategies, and Projects configuration.
 *
 * All settings are read/written via config/engine_settings.yml through the API.
 */
import { useState } from 'react';
import {
  Settings, MessageSquare, Cpu, Wrench, FolderOpen, Save, Loader2, Check,
} from 'lucide-react';
import {
  useEngineSettings, useUpdateSetting,
  MODEL_ROLES, AVAILABLE_MODELS,
  type EngineSettings, type ModelConfig,
} from '@/services/engineSettingsApi';

type TabId = 'models' | 'discord' | 'generation' | 'fix' | 'projects';

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'models', label: 'Models', icon: <Cpu className="w-3.5 h-3.5" /> },
  { id: 'discord', label: 'Discord', icon: <MessageSquare className="w-3.5 h-3.5" /> },
  { id: 'generation', label: 'Generation', icon: <Settings className="w-3.5 h-3.5" /> },
  { id: 'fix', label: 'Fix', icon: <Wrench className="w-3.5 h-3.5" /> },
  { id: 'projects', label: 'Projects', icon: <FolderOpen className="w-3.5 h-3.5" /> },
];

export function EngineSettingsTabs() {
  const [activeTab, setActiveTab] = useState<TabId>('models');
  const { data: settings, isLoading, error } = useEngineSettings();
  const updateSetting = useUpdateSetting();

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading settings...</div>;
  if (error || !settings) return <div className="p-4 text-sm text-red-400">Failed to load settings</div>;

  return (
    <div className="h-full flex flex-col">
      {/* Tab Bar */}
      <div className="flex border-b border-border/30 bg-muted/5 px-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors
              ${activeTab === tab.id
                ? 'text-primary border-b-2 border-primary'
                : 'text-muted-foreground hover:text-foreground'
              }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'models' && (
          <ModelsTab settings={settings} onUpdate={(p, v) => updateSetting.mutate({ path: p, value: v })} isPending={updateSetting.isPending} />
        )}
        {activeTab === 'discord' && (
          <DiscordTab settings={settings} onUpdate={(p, v) => updateSetting.mutate({ path: p, value: v })} isPending={updateSetting.isPending} />
        )}
        {activeTab === 'generation' && (
          <GenerationTab settings={settings} onUpdate={(p, v) => updateSetting.mutate({ path: p, value: v })} isPending={updateSetting.isPending} />
        )}
        {activeTab === 'fix' && (
          <FixTab settings={settings} onUpdate={(p, v) => updateSetting.mutate({ path: p, value: v })} isPending={updateSetting.isPending} />
        )}
        {activeTab === 'projects' && (
          <ProjectsTab settings={settings} onUpdate={(p, v) => updateSetting.mutate({ path: p, value: v })} isPending={updateSetting.isPending} />
        )}
      </div>
    </div>
  );
}

// ── Shared Components ──

function SettingRow({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/10 last:border-0">
      <div>
        <div className="text-xs font-medium">{label}</div>
        {description && <div className="text-[10px] text-muted-foreground">{description}</div>}
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

function SaveButton({ onClick, isPending }: { onClick: () => void; isPending: boolean }) {
  return (
    <button onClick={onClick} disabled={isPending}
      className="flex items-center gap-1 px-2 py-1 text-[10px] bg-primary/10 text-primary border border-primary/30 rounded hover:bg-primary/20 disabled:opacity-50">
      {isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
      Save
    </button>
  );
}

// ── Models Tab ──

interface TabProps {
  settings: EngineSettings;
  onUpdate: (path: string, value: unknown) => void;
  isPending: boolean;
}

function ModelsTab({ settings, onUpdate, isPending }: TabProps) {
  const models = settings.models || {};

  return (
    <div className="space-y-3">
      <p className="text-[10px] text-muted-foreground">Configure which AI model is used for each role in the pipeline.</p>
      {Object.entries(MODEL_ROLES).map(([role, meta]) => {
        const config = models[role] || { provider: 'openai', model: 'gpt-5.4', max_tokens: 16384 };
        return (
          <ModelRoleCard
            key={role}
            role={role}
            label={meta.label}
            description={meta.description}
            config={config}
            onSave={(newConfig) => onUpdate(`models.${role}`, newConfig)}
            isPending={isPending}
          />
        );
      })}
    </div>
  );
}

function ModelRoleCard({ role, label, description, config, onSave, isPending }: {
  role: string; label: string; description: string;
  config: ModelConfig; onSave: (c: ModelConfig) => void; isPending: boolean;
}) {
  const [provider, setProvider] = useState(config.provider);
  const [model, setModel] = useState(config.model);
  const [maxTokens, setMaxTokens] = useState(config.max_tokens);
  const isDirty = provider !== config.provider || model !== config.model || maxTokens !== config.max_tokens;

  const modelOptions = AVAILABLE_MODELS[provider] || [];

  return (
    <div className="p-3 bg-muted/10 border border-border/20 rounded-lg space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold">{label}</div>
          <div className="text-[10px] text-muted-foreground">{description}</div>
        </div>
        {isDirty && (
          <button onClick={() => onSave({ provider, model, max_tokens: maxTokens })}
            disabled={isPending}
            className="flex items-center gap-1 px-2 py-1 text-[10px] bg-green-500/10 text-green-400 border border-green-500/30 rounded hover:bg-green-500/20">
            {isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
            Save
          </button>
        )}
      </div>

      {/* Provider selector */}
      <div className="flex gap-1">
        {['openai', 'openrouter', 'anthropic'].map((p) => (
          <button key={p} onClick={() => setProvider(p)}
            className={`px-2 py-0.5 text-[10px] rounded border transition ${
              provider === p ? 'bg-primary/20 text-primary border-primary/50' : 'border-border/30 text-muted-foreground hover:text-foreground'
            }`}>
            {p}
          </button>
        ))}
      </div>

      {/* Model selector */}
      <div className="flex gap-1 flex-wrap">
        {modelOptions.map((m) => (
          <button key={m} onClick={() => setModel(m)}
            className={`px-2 py-0.5 text-[10px] rounded border transition ${
              model === m ? 'bg-blue-500/20 text-blue-400 border-blue-500/50' : 'border-border/20 text-muted-foreground hover:text-foreground'
            }`}>
            {m}
          </button>
        ))}
      </div>

      {/* Current value */}
      <div className="text-[10px] text-muted-foreground font-mono">
        {provider}/{model} (max {maxTokens.toLocaleString()} tokens)
      </div>
    </div>
  );
}

// ── Discord Tab ──

function DiscordTab({ settings, onUpdate, isPending }: TabProps) {
  const discord = settings.discord || {} as any;
  const channels = discord.channels || {};
  const autoStatus = discord.auto_status || {};
  const autoFix = discord.auto_fix || {};

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h4 className="text-xs font-semibold flex items-center gap-1.5">
          <MessageSquare className="w-3.5 h-3.5 text-indigo-400" /> Auto-Status
        </h4>
        <SettingRow label="Enabled" description="Post status to Discord periodically">
          <ToggleButton value={autoStatus.enabled} onChange={(v) => onUpdate('discord.auto_status.enabled', v)} />
        </SettingRow>
        <SettingRow label="Interval" description="Seconds between status posts">
          <NumberInput value={autoStatus.interval_seconds || 180} onChange={(v) => onUpdate('discord.auto_status.interval_seconds', v)} min={30} max={600} step={30} />
        </SettingRow>
      </div>

      <div className="space-y-1">
        <h4 className="text-xs font-semibold flex items-center gap-1.5">
          <Wrench className="w-3.5 h-3.5 text-orange-400" /> Auto-Fix
        </h4>
        <SettingRow label="Enabled" description="Automatically fix failed tasks">
          <ToggleButton value={autoFix.enabled} onChange={(v) => onUpdate('discord.auto_fix.enabled', v)} />
        </SettingRow>
        <SettingRow label="Max Rounds" description="Max fix attempts after generation">
          <NumberInput value={autoFix.max_rounds || 3} onChange={(v) => onUpdate('discord.auto_fix.max_rounds', v)} min={1} max={10} />
        </SettingRow>
        <SettingRow label="Fix on Idle" description="Fix failed tasks even when no generation ran">
          <ToggleButton value={autoFix.trigger_on_idle} onChange={(v) => onUpdate('discord.auto_fix.trigger_on_idle', v)} />
        </SettingRow>
      </div>

      <div className="space-y-1">
        <h4 className="text-xs font-semibold">Channel IDs</h4>
        <p className="text-[10px] text-muted-foreground">Discord channel IDs for message routing</p>
        {Object.entries(channels).map(([key, value]) => (
          <SettingRow key={key} label={key}>
            <input type="text" defaultValue={value as string}
              onBlur={(e) => onUpdate(`discord.channels.${key}`, e.target.value)}
              className="w-48 px-2 py-0.5 text-[10px] font-mono bg-muted/20 border border-border/30 rounded" />
          </SettingRow>
        ))}
      </div>
    </div>
  );
}

// ── Generation Tab ──

function GenerationTab({ settings, onUpdate, isPending }: TabProps) {
  const gen = settings.generation || {} as any;

  return (
    <div className="space-y-3">
      <SettingRow label="Backend" description="Default code generation backend">
        <select value={gen.backend || 'openai'}
          onChange={(e) => onUpdate('generation.backend', e.target.value)}
          className="px-2 py-1 text-xs bg-muted/20 border border-border/30 rounded">
          <option value="openai">OpenAI</option>
          <option value="openrouter">OpenRouter</option>
          <option value="claude">Claude CLI</option>
          <option value="kilo">Kilo CLI</option>
        </select>
      </SettingRow>

      <SettingRow label="Parallel Tasks" description="Max tasks running simultaneously">
        <NumberInput value={gen.max_parallel_tasks || 4} onChange={(v) => onUpdate('generation.max_parallel_tasks', v)} min={1} max={16} />
      </SettingRow>

      <SettingRow label="Task Timeout" description="Seconds before a task is killed">
        <NumberInput value={gen.task_timeout_seconds || 300} onChange={(v) => onUpdate('generation.task_timeout_seconds', v)} min={60} max={1800} step={60} />
      </SettingRow>

      <SettingRow label="Max Retries" description="Task retry attempts on failure">
        <NumberInput value={gen.max_task_retries || 3} onChange={(v) => onUpdate('generation.max_task_retries', v)} min={0} max={10} />
      </SettingRow>

      <SettingRow label="Feature Ordering" description="Group tasks by feature (setup→schema→api→fe)">
        <ToggleButton value={gen.feature_based_ordering} onChange={(v) => onUpdate('generation.feature_based_ordering', v)} />
      </SettingRow>

      <SettingRow label="Society of Mind" description="Enable multi-agent orchestration">
        <ToggleButton value={gen.enable_som} onChange={(v) => onUpdate('generation.enable_som', v)} />
      </SettingRow>

      <SettingRow label="SoM Agents" description="Number of concurrent agents">
        <NumberInput value={gen.som_agents || 16} onChange={(v) => onUpdate('generation.som_agents', v)} min={4} max={64} />
      </SettingRow>
    </div>
  );
}

// ── Fix Strategies Tab ──

function FixTab({ settings, onUpdate, isPending }: TabProps) {
  const strategies = settings.fix_strategies || {};

  const methods = ['prisma_push', 'eslint_fix', 'build_check', 'gpt_fix', 'rerun'];

  return (
    <div className="space-y-3">
      <p className="text-[10px] text-muted-foreground">Configure how each task type is fixed when it fails.</p>
      {Object.entries(strategies).map(([type, strategy]) => (
        <div key={type} className="p-3 bg-muted/10 border border-border/20 rounded-lg space-y-2">
          <div className="text-xs font-semibold capitalize">{type}</div>
          <SettingRow label="Method">
            <select value={(strategy as any).method || 'gpt_fix'}
              onChange={(e) => onUpdate(`fix_strategies.${type}.method`, e.target.value)}
              className="px-2 py-0.5 text-[10px] bg-muted/20 border border-border/30 rounded">
              {methods.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </SettingRow>
          {(strategy as any).max_attempts && (
            <SettingRow label="Max Attempts">
              <NumberInput value={(strategy as any).max_attempts} onChange={(v) => onUpdate(`fix_strategies.${type}.max_attempts`, v)} min={1} max={10} />
            </SettingRow>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Projects Tab ──

function ProjectsTab({ settings, onUpdate, isPending }: TabProps) {
  const projects = settings.projects || {};

  return (
    <div className="space-y-3">
      <p className="text-[10px] text-muted-foreground">Registered projects for generation.</p>
      {Object.entries(projects).map(([key, proj]) => (
        <div key={key} className="p-3 bg-muted/10 border border-border/20 rounded-lg space-y-1">
          <div className="text-xs font-semibold">{(proj as any).name || key}</div>
          <div className="text-[10px] text-muted-foreground font-mono">{(proj as any).id}</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px]">
            <span className="text-muted-foreground">Tech Stack:</span>
            <span>{(proj as any).tech_stack}</span>
            <span className="text-muted-foreground">Output:</span>
            <span className="font-mono truncate">{(proj as any).output_dir}</span>
            <span className="text-muted-foreground">Preview:</span>
            <span className="font-mono">{(proj as any).preview_url}</span>
            <span className="text-muted-foreground">DB Job ID:</span>
            <span>{(proj as any).db_job_id}</span>
          </div>
        </div>
      ))}
      {Object.keys(projects).length === 0 && (
        <div className="text-xs text-muted-foreground text-center py-4">No projects registered</div>
      )}
    </div>
  );
}

// ── Shared input components ──

function ToggleButton({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!value)}
      className={`w-9 h-5 rounded-full transition-colors ${value ? 'bg-green-500' : 'bg-muted/40'} relative`}>
      <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${value ? 'left-[18px]' : 'left-0.5'}`} />
    </button>
  );
}

function NumberInput({ value, onChange, min, max, step = 1 }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number;
}) {
  return (
    <input type="number" value={value} min={min} max={max} step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-20 px-2 py-0.5 text-[10px] font-mono bg-muted/20 border border-border/30 rounded text-center" />
  );
}
