/**
 * Engine Settings API Service
 *
 * Central settings for the DaveFelix Coding Engine.
 * Reads/writes config/engine_settings.yml via REST API.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const API_BASE = "/api/v1/dashboard";

// ── Types ──

export interface ModelConfig {
  provider: string;
  model: string;
  max_tokens: number;
}

export interface DiscordChannels {
  dev_tasks: string;
  fixes: string;
  prs: string;
  orchestrator: string;
  integration: string;
  testing: string;
  done: string;
}

export interface AutoStatusConfig {
  enabled: boolean;
  interval_seconds: number;
  channel: string;
}

export interface AutoFixConfig {
  enabled: boolean;
  max_rounds: number;
  trigger_on_idle: boolean;
  channel: string;
}

export interface DiscordConfig {
  channels: DiscordChannels;
  auto_status: AutoStatusConfig;
  auto_fix: AutoFixConfig;
  use_threads: boolean;
}

export interface GenerationConfig {
  backend: string;
  max_parallel_tasks: number;
  max_parallel_epics: number;
  task_timeout_seconds: number;
  epic_timeout_seconds: number;
  max_task_retries: number;
  feature_based_ordering: boolean;
  enable_som: boolean;
  som_agents: number;
}

export interface FixStrategy {
  method: string;
  fallback?: string;
  max_attempts?: number;
  max_retries?: number;
  command?: string;
}

export interface ProjectConfig {
  id: string;
  name: string;
  requirements_path: string;
  output_dir: string;
  db_job_id: number;
  tech_stack: string;
  preview_url: string;
}

export interface EngineSettings {
  models: Record<string, ModelConfig>;
  providers: Record<string, { base_url: string | null; api_key_env: string }>;
  discord: DiscordConfig;
  generation: GenerationConfig;
  fix_strategies: Record<string, FixStrategy>;
  verification: Record<string, unknown>;
  projects: Record<string, ProjectConfig>;
  infrastructure: Record<string, unknown>;
}

// ── API Functions ──

async function fetchSettings(): Promise<EngineSettings> {
  const resp = await fetch(`${API_BASE}/engine-settings`);
  if (!resp.ok) throw new Error("Failed to fetch settings");
  return resp.json();
}

async function fetchSection(section: string): Promise<unknown> {
  const resp = await fetch(`${API_BASE}/engine-settings/${section}`);
  if (!resp.ok) throw new Error(`Failed to fetch ${section}`);
  return resp.json();
}

async function patchSetting(path: string, value: unknown): Promise<void> {
  const resp = await fetch(`${API_BASE}/engine-settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, value }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update setting");
  }
}

// ── React Query Hooks ──

export function useEngineSettings() {
  return useQuery({
    queryKey: ["engine-settings"],
    queryFn: fetchSettings,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

export function useEngineModels() {
  return useQuery({
    queryKey: ["engine-settings", "models"],
    queryFn: () => fetchSection("models"),
    staleTime: 30_000,
  });
}

export function useEngineDiscord() {
  return useQuery({
    queryKey: ["engine-settings", "discord"],
    queryFn: () => fetchSection("discord"),
    staleTime: 30_000,
  });
}

export function useEngineProjects() {
  return useQuery({
    queryKey: ["engine-settings", "projects"],
    queryFn: () => fetchSection("projects"),
    staleTime: 30_000,
  });
}

export function useUpdateSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, value }: { path: string; value: unknown }) =>
      patchSetting(path, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["engine-settings"] });
    },
  });
}

// ── Available Models per Provider ──

export const AVAILABLE_MODELS: Record<string, string[]> = {
  openai: [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o4-mini",
    "o3",
    "o3-mini",
  ],
  openrouter: [
    "anthropic/claude-sonnet-4",
    "anthropic/claude-opus-4",
    "openai/gpt-5.4",
    "google/gemini-2.5-pro",
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-r1:free",
  ],
  anthropic: [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-3-20250414",
  ],
};

// ── Model Role Labels ──

export const MODEL_ROLES: Record<string, { label: string; description: string }> = {
  generation: { label: "Code Generation", description: "Primary model for generating code" },
  fixing: { label: "Code Fixing", description: "Used by !fixall and auto-fix" },
  schema: { label: "Schema Fix", description: "Prisma schema generation & repair" },
  review: { label: "PR Review", description: "Code review and PR analysis" },
  planning: { label: "Task Planning", description: "Task enrichment & planning" },
  reasoning: { label: "Reasoning", description: "Complex architecture decisions" },
};
