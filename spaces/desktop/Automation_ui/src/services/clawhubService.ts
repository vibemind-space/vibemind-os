/**
 * ClawHub Service - Skill Marketplace Integration
 *
 * Frontend client for the ClawHub.ai skill marketplace API.
 * Provides skill search, installation, management, and execution.
 *
 * API Base: /api/clawhub
 */

// ============================================================================
// INTERFACES
// ============================================================================

export type SkillCategory =
  | "automation"
  | "browser"
  | "desktop"
  | "file_management"
  | "development"
  | "data"
  | "communication"
  | "ai_ml"
  | "system"
  | "custom";

export type SkillPermission =
  | "filesystem"
  | "network"
  | "desktop_control"
  | "shell"
  | "browser"
  | "clipboard"
  | "screenshot"
  | "ocr";

export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  category: SkillCategory;
  tags: string[];
  install_count: number;
  rating: number;
  icon?: string;
  installed: boolean;
}

export interface SkillDetail extends SkillSummary {
  long_description?: string;
  permissions: SkillPermission[];
  dependencies: string[];
  parameters: Record<string, SkillParameter>;
  code_bundle_url?: string;
  documentation_url?: string;
  repository_url?: string;
  created_at?: string;
  updated_at?: string;
  changelog?: string;
}

export interface SkillParameter {
  type: string;
  description: string;
  required?: boolean;
  enum?: string[];
}

export interface InstalledSkill {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  category: SkillCategory;
  tags: string[];
  permissions: SkillPermission[];
  parameters: Record<string, SkillParameter>;
  status: "available" | "installed" | "updating" | "error";
  enabled: boolean;
  installed_at: string;
  last_executed?: string;
  execution_count: number;
  local_path?: string;
}

export interface SkillSearchResponse {
  query: string;
  total: number;
  skills: SkillSummary[];
  offset: number;
  limit: number;
}

export interface SkillExecuteResponse {
  success: boolean;
  skill_id: string;
  message: string;
  data?: Record<string, unknown>;
  error?: string;
  execution_time_ms: number;
}

export interface CategoryInfo {
  category: string;
  count: number;
}

export interface SkillStats {
  total_installed: number;
  enabled: number;
  disabled: number;
  total_executions: number;
  skills_dir: string;
}

// ============================================================================
// CATEGORY DISPLAY INFO
// ============================================================================

export const CATEGORY_INFO: Record<
  SkillCategory,
  { label: string; icon: string; color: string }
> = {
  automation: { label: "Automation", icon: "zap", color: "bg-yellow-500" },
  browser: { label: "Browser", icon: "globe", color: "bg-blue-500" },
  desktop: { label: "Desktop", icon: "monitor", color: "bg-purple-500" },
  file_management: {
    label: "File Management",
    icon: "folder",
    color: "bg-green-500",
  },
  development: { label: "Development", icon: "code", color: "bg-gray-700" },
  data: { label: "Data", icon: "database", color: "bg-orange-500" },
  communication: { label: "Communication", icon: "mail", color: "bg-pink-500" },
  ai_ml: { label: "AI & ML", icon: "brain", color: "bg-indigo-500" },
  system: { label: "System", icon: "terminal", color: "bg-gray-500" },
  custom: { label: "Custom", icon: "puzzle", color: "bg-teal-500" },
};

// ============================================================================
// SERVICE CLASS
// ============================================================================

class ClawHubServiceClass {
  private baseUrl: string;

  constructor(baseUrl: string = "/api/clawhub") {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ClawHub API error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  // ============================================================================
  // Search & Discovery
  // ============================================================================

  async searchSkills(
    query: string = "",
    options?: {
      category?: SkillCategory;
      limit?: number;
      offset?: number;
      sort_by?: "relevance" | "rating" | "installs" | "newest";
    },
  ): Promise<SkillSearchResponse> {
    const params = new URLSearchParams({ q: query });
    if (options?.category) {
      params.set("category", options.category);
    }
    if (options?.limit) {
      params.set("limit", String(options.limit));
    }
    if (options?.offset) {
      params.set("offset", String(options.offset));
    }
    if (options?.sort_by) {
      params.set("sort_by", options.sort_by);
    }

    return this.request<SkillSearchResponse>(`/search?${params}`);
  }

  async getTrending(limit: number = 10): Promise<SkillSummary[]> {
    return this.request<SkillSummary[]>(`/trending?limit=${limit}`);
  }

  async getCategories(): Promise<CategoryInfo[]> {
    return this.request<CategoryInfo[]>("/categories");
  }

  async getSkillDetail(skillId: string): Promise<SkillDetail> {
    return this.request<SkillDetail>(`/skill/${encodeURIComponent(skillId)}`);
  }

  // ============================================================================
  // Installation & Management
  // ============================================================================

  async getInstalledSkills(): Promise<InstalledSkill[]> {
    return this.request<InstalledSkill[]>("/installed");
  }

  async installSkill(
    skillId: string,
    version?: string,
  ): Promise<{
    status: string;
    skill: InstalledSkill;
  }> {
    return this.request("/install", {
      method: "POST",
      body: JSON.stringify({ skill_id: skillId, version }),
    });
  }

  async uninstallSkill(
    skillId: string,
  ): Promise<{ status: string; skill_id: string }> {
    return this.request("/uninstall", {
      method: "POST",
      body: JSON.stringify({ skill_id: skillId }),
    });
  }

  async toggleSkill(
    skillId: string,
    enabled: boolean,
  ): Promise<{
    status: string;
    skill_id: string;
    enabled: boolean;
  }> {
    return this.request("/toggle", {
      method: "POST",
      body: JSON.stringify({ skill_id: skillId, enabled }),
    });
  }

  // ============================================================================
  // Execution
  // ============================================================================

  async executeSkill(
    skillId: string,
    params: Record<string, unknown> = {},
    userId: string = "web_user",
    platform: string = "web",
  ): Promise<SkillExecuteResponse> {
    return this.request<SkillExecuteResponse>("/execute", {
      method: "POST",
      body: JSON.stringify({
        skill_id: skillId,
        params,
        user_id: userId,
        platform,
      }),
    });
  }

  // ============================================================================
  // Stats
  // ============================================================================

  async getStats(): Promise<SkillStats> {
    return this.request<SkillStats>("/stats");
  }
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8007";
const apiBase = `${backendUrl}/api/clawhub`;

export const ClawHubService = new ClawHubServiceClass(apiBase);
export { ClawHubServiceClass };
