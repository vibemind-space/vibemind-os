// front/src/services/llmConfigApi.ts
import { API_URL } from './api';

// Provider definitions with their default base URLs
export const PROVIDERS = {
  anthropic: { label: 'Anthropic', baseUrl: null, apiKeyEnv: 'ANTHROPIC_API_KEY' },
  openrouter: { label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', apiKeyEnv: 'OPENROUTER_API_KEY' },
  openai: { label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', apiKeyEnv: 'OPENAI_API_KEY' },
  gemini: { label: 'Google Gemini', baseUrl: 'https://generativelanguage.googleapis.com/v1beta', apiKeyEnv: 'GEMINI_API_KEY' },
  ollama: { label: 'Ollama (Local)', baseUrl: 'http://localhost:11434/v1', apiKeyEnv: 'OLLAMA_API_KEY' },
  custom: { label: 'Custom Endpoint', baseUrl: '', apiKeyEnv: 'CUSTOM_API_KEY' },
} as const;

export type ProviderId = keyof typeof PROVIDERS;

export const MODEL_ROLES = {
  primary: { label: 'Primary', desc: 'Main code generation (SDK direct)' },
  cli: { label: 'CLI', desc: 'Claude CLI / Kilo CLI' },
  mcp_standard: { label: 'MCP Standard', desc: 'AutoGen teams, orchestrator' },
  mcp_agent: { label: 'MCP Agent', desc: 'Individual plugin agents' },
  judge: { label: 'Judge', desc: 'Validation, debate, analysis' },
  reasoning: { label: 'Reasoning', desc: 'Complex reasoning, architecture' },
  enrichment: { label: 'Enrichment', desc: 'Schema discovery, task mapping' },
} as const;

export type ModelRole = keyof typeof MODEL_ROLES;

export interface ModelRoleConfig {
  provider: string;
  model: string;
  max_tokens: number;
  description?: string | null;
}

export interface ProviderConfig {
  base_url: string | null;
  api_key_env: string;
}

export interface LLMConfig {
  providers: Record<string, ProviderConfig>;
  models: Record<string, ModelRoleConfig>;
  source: string;
  yaml_path: string;
}

// Popular models per provider for quick selection
export const POPULAR_MODELS: Record<ProviderId, string[]> = {
  anthropic: [
    'claude-opus-4-6',
    'claude-sonnet-4-6',
    'claude-4.5-sonnet',
    'claude-haiku-4-5',
    'claude-opus-4-20250514',
  ],
  openrouter: [
    // --- Paid (top tier 2026) ---
    'anthropic/claude-opus-4-6',
    'anthropic/claude-sonnet-4-6',
    'openai/gpt-5.4',
    'openai/gpt-4o',
    'google/gemini-3.1-pro',
    'google/gemini-2.5-pro',
    'x-ai/grok-4.1',
    'deepseek/deepseek-r1',
    // --- FREE (no cost, great for testing) ---
    'openrouter/free',
    'nvidia/nemotron-3-super-120b-a12b:free',
    'stepfun/step-3.5-flash:free',
    'qwen/qwen3-coder:free',
    'qwen/qwen3-next-80b-a3b-instruct:free',
    'arcee-ai/trinity-large-preview:free',
    'minimax/minimax-m2.5:free',
    'nvidia/nemotron-3-nano-30b-a3b:free',
    'openrouter/hunter-alpha',
    'openrouter/healer-alpha',
  ],
  openai: ['gpt-5.4', 'gpt-5.1', 'gpt-4o', 'gpt-4o-mini', 'o1-preview', 'o1-mini'],
  gemini: ['gemini-3.1-pro', 'gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash'],
  ollama: ['qwen2.5-coder:32b', 'qwen2.5-coder:7b', 'deepseek-coder-v2:16b', 'codellama:34b', 'llama3.1:70b', 'llama3.1:8b'],
  custom: [],
};

// ─── Presets ─────────────────────────────────────────────────────────
// One-click configurations for all 7 model roles

export interface ModelPreset {
  label: string;
  description: string;
  badge?: string;
  badgeColor?: string;
  models: Record<ModelRole, ModelRoleConfig>;
}

export const MODEL_PRESETS: Record<string, ModelPreset> = {
  free_testing: {
    label: 'Free Testing',
    description: 'OpenRouter free models — zero cost, great for testing pipelines',
    badge: 'FREE',
    badgeColor: 'green',
    models: {
      primary:      { provider: 'openrouter', model: 'qwen/qwen3-coder:free',                    max_tokens: 16384 },
      cli:          { provider: 'openrouter', model: 'qwen/qwen3-coder:free',                    max_tokens: 16384 },
      mcp_standard: { provider: 'openrouter', model: 'qwen/qwen3-coder:free',                    max_tokens: 8192  },
      mcp_agent:    { provider: 'openrouter', model: 'qwen/qwen3-coder:free',                    max_tokens: 8192  },
      judge:        { provider: 'openrouter', model: 'nvidia/nemotron-3-super-120b-a12b:free',    max_tokens: 8192  },
      reasoning:    { provider: 'openrouter', model: 'nvidia/nemotron-3-super-120b-a12b:free',    max_tokens: 16384 },
      enrichment:   { provider: 'openrouter', model: 'qwen/qwen3-next-80b-a3b-instruct:free',    max_tokens: 8192  },
    },
  },
  claude_pro: {
    label: 'Claude Pro',
    description: 'Anthropic Claude across all roles — best quality, highest cost',
    badge: 'PRO',
    badgeColor: 'purple',
    models: {
      primary:      { provider: 'anthropic', model: 'claude-sonnet-4-6',    max_tokens: 16384 },
      cli:          { provider: 'anthropic', model: 'claude-sonnet-4-6',    max_tokens: 16384 },
      mcp_standard: { provider: 'anthropic', model: 'claude-sonnet-4-6',    max_tokens: 8192  },
      mcp_agent:    { provider: 'anthropic', model: 'claude-haiku-4-5',     max_tokens: 8192  },
      judge:        { provider: 'anthropic', model: 'claude-opus-4-6',      max_tokens: 8192  },
      reasoning:    { provider: 'anthropic', model: 'claude-opus-4-6',      max_tokens: 16384 },
      enrichment:   { provider: 'anthropic', model: 'claude-haiku-4-5',     max_tokens: 8192  },
    },
  },
  hybrid_budget: {
    label: 'Hybrid Budget',
    description: 'Claude for critical roles, free models for the rest — balanced cost',
    badge: '$',
    badgeColor: 'yellow',
    models: {
      primary:      { provider: 'anthropic',  model: 'claude-sonnet-4-6',                        max_tokens: 16384 },
      cli:          { provider: 'anthropic',  model: 'claude-sonnet-4-6',                        max_tokens: 16384 },
      mcp_standard: { provider: 'openrouter', model: 'qwen/qwen3-coder:free',                   max_tokens: 8192  },
      mcp_agent:    { provider: 'openrouter', model: 'qwen/qwen3-coder:free',                   max_tokens: 8192  },
      judge:        { provider: 'anthropic',  model: 'claude-sonnet-4-6',                        max_tokens: 8192  },
      reasoning:    { provider: 'openrouter', model: 'nvidia/nemotron-3-super-120b-a12b:free',   max_tokens: 16384 },
      enrichment:   { provider: 'openrouter', model: 'qwen/qwen3-next-80b-a3b-instruct:free',   max_tokens: 8192  },
    },
  },
};

// REST API
export const llmConfigApi = {
  getConfig: async (): Promise<LLMConfig> => {
    const res = await fetch(`${API_URL}/llm-config`);
    if (!res.ok) throw new Error(`Failed to fetch LLM config: ${res.status}`);
    return res.json();
  },

  updateConfig: async (models: Record<string, ModelRoleConfig>): Promise<LLMConfig> => {
    const res = await fetch(`${API_URL}/llm-config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ models }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || err.errors?.join(', ') || `Failed: ${res.status}`);
    }
    return res.json();
  },

  updateRole: async (role: string, config: ModelRoleConfig): Promise<LLMConfig> => {
    const res = await fetch(`${API_URL}/llm-config/role/${role}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `Failed: ${res.status}`);
    }
    return res.json();
  },

  validate: async (models: Record<string, ModelRoleConfig>): Promise<{ valid: boolean; errors: string[]; warnings: string[] }> => {
    const res = await fetch(`${API_URL}/llm-config/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ models }),
    });
    if (!res.ok) throw new Error(`Validation failed: ${res.status}`);
    return res.json();
  },
};
