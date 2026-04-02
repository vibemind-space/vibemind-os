/**
 * Config API Service
 *
 * Replaces Supabase REST API calls with local FastAPI backend.
 * Provides CRUD operations for live desktop configurations.
 */

const getApiBaseUrl = (): string => {
  return import.meta.env.VITE_BACKEND_URL || 'http://localhost:8007';
};

export interface LiveDesktopConfig {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  configuration: Record<string, unknown>;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
  created_by: string | null;
  tags: string[];
}

export interface ConfigCreate {
  name: string;
  description?: string | null;
  category?: string | null;
  configuration?: Record<string, unknown>;
  is_active?: boolean;
  tags?: string[];
  created_by?: string | null;
}

export interface ConfigUpdate {
  name?: string;
  description?: string | null;
  category?: string | null;
  configuration?: Record<string, unknown>;
  is_active?: boolean;
  tags?: string[];
}

class ConfigApiServiceClass {
  private baseUrl: string;

  constructor() {
    this.baseUrl = getApiBaseUrl();
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP error: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Get all configurations
   */
  async getConfigs(options?: {
    category?: string;
    is_active?: boolean;
  }): Promise<LiveDesktopConfig[]> {
    const params = new URLSearchParams();
    if (options?.category) params.set('category', options.category);
    if (options?.is_active !== undefined) params.set('is_active', String(options.is_active));

    const url = `${this.baseUrl}/api/configs/${params.toString() ? '?' + params.toString() : ''}`;
    const response = await fetch(url);
    return this.handleResponse<LiveDesktopConfig[]>(response);
  }

  /**
   * Get active configurations only
   */
  async getActiveConfigs(): Promise<LiveDesktopConfig[]> {
    const response = await fetch(`${this.baseUrl}/api/configs/active`);
    return this.handleResponse<LiveDesktopConfig[]>(response);
  }

  /**
   * Get a specific configuration by ID
   */
  async getConfig(id: string): Promise<LiveDesktopConfig> {
    const response = await fetch(`${this.baseUrl}/api/configs/${id}`);
    return this.handleResponse<LiveDesktopConfig>(response);
  }

  /**
   * Create a new configuration
   */
  async createConfig(config: ConfigCreate): Promise<LiveDesktopConfig> {
    const response = await fetch(`${this.baseUrl}/api/configs/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    return this.handleResponse<LiveDesktopConfig>(response);
  }

  /**
   * Update an existing configuration
   */
  async updateConfig(id: string, config: ConfigUpdate): Promise<LiveDesktopConfig> {
    const response = await fetch(`${this.baseUrl}/api/configs/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    return this.handleResponse<LiveDesktopConfig>(response);
  }

  /**
   * Delete a configuration
   */
  async deleteConfig(id: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/configs/${id}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP error: ${response.status}`);
    }
  }

  /**
   * Duplicate a configuration
   */
  async duplicateConfig(id: string): Promise<LiveDesktopConfig> {
    const response = await fetch(`${this.baseUrl}/api/configs/${id}/duplicate`, {
      method: 'POST',
    });
    return this.handleResponse<LiveDesktopConfig>(response);
  }
}

// Export singleton instance
export const ConfigApiService = new ConfigApiServiceClass();

// Export static methods for compatibility with existing code
export const getConfigs = (options?: { category?: string; is_active?: boolean }) =>
  ConfigApiService.getConfigs(options);

export const getActiveConfigs = () => ConfigApiService.getActiveConfigs();

export const getConfig = (id: string) => ConfigApiService.getConfig(id);

export const createConfig = (config: ConfigCreate) => ConfigApiService.createConfig(config);

export const updateConfig = (id: string, config: ConfigUpdate) =>
  ConfigApiService.updateConfig(id, config);

export const deleteConfig = (id: string) => ConfigApiService.deleteConfig(id);

export const duplicateConfig = (id: string) => ConfigApiService.duplicateConfig(id);
