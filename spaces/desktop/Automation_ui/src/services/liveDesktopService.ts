/**
 * Live Desktop Service
 * Handles all API operations for Live Desktop functionality
 *
 * MIGRATED: Now uses local FastAPI backend instead of Supabase
 */

import { ConfigApiService, LiveDesktopConfig as ApiConfig } from '@/services/configApiService';
import { LiveDesktopConfig, OCRRegion } from '@/types/liveDesktop';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';
import { safeExecute, transformError, ErrorCode } from '@/utils/errorHandling';

/**
 * Transform API config to LiveDesktopConfig type
 */
function transformConfig(apiConfig: ApiConfig): LiveDesktopConfig {
  const config = apiConfig.configuration as Record<string, unknown>;
  return {
    id: apiConfig.id,
    name: apiConfig.name,
    description: apiConfig.description || '',
    websocketUrl: `${WEBSOCKET_CONFIG.BASE_URL}${WEBSOCKET_CONFIG.ENDPOINTS.LIVE_DESKTOP}`,
    ...config,
    createdAt: apiConfig.created_at || new Date().toISOString(),
    updatedAt: apiConfig.updated_at || new Date().toISOString(),
    category: apiConfig.category || undefined,
  } as LiveDesktopConfig;
}

export class LiveDesktopService {
  /**
   * Get all live desktop configurations
   */
  static async getConfigs(): Promise<LiveDesktopConfig[]> {
    const result = await safeExecute(async () => {
      const configs = await ConfigApiService.getConfigs();
      return configs.map(transformConfig);
    }, { operation: 'getConfigs' });

    if (result.error) {
      throw transformError(result.error, { operation: 'getConfigs' });
    }

    return result.data || [];
  }

  /**
   * Get a single configuration by ID
   */
  static async getConfig(id: string): Promise<LiveDesktopConfig | null> {
    const result = await safeExecute(async () => {
      try {
        const config = await ConfigApiService.getConfig(id);
        return transformConfig(config);
      } catch (error: unknown) {
        if (error instanceof Error && error.message.includes('404')) {
          return null;
        }
        throw error;
      }
    }, { operation: 'getConfig', configId: id });

    if (result.error) {
      throw transformError(result.error, { operation: 'getConfig', configId: id });
    }

    return result.data ?? null;
  }

  /**
   * Create a new configuration
   */
  static async createConfig(config: Partial<LiveDesktopConfig>): Promise<LiveDesktopConfig> {
    const result = await safeExecute(async () => {
      const created = await ConfigApiService.createConfig({
        name: config.name || 'New Configuration',
        description: config.description,
        category: config.category,
        configuration: config as Record<string, unknown>,
        is_active: true,
      });
      return transformConfig(created);
    }, { operation: 'createConfig', configName: config.name });

    if (result.error) {
      throw transformError(result.error, { operation: 'createConfig', configName: config.name });
    }

    if (!result.data) {
      throw transformError(new Error('Failed to create configuration'), { operation: 'createConfig' });
    }

    return result.data;
  }

  /**
   * Update an existing configuration
   */
  static async updateConfig(id: string, updates: Partial<LiveDesktopConfig>): Promise<void> {
    const result = await safeExecute(async () => {
      await ConfigApiService.updateConfig(id, {
        name: updates.name,
        description: updates.description,
        category: updates.category,
        configuration: updates as Record<string, unknown>,
      });
    }, { operation: 'updateConfig', configId: id });

    if (result.error) {
      throw transformError(result.error, { operation: 'updateConfig', configId: id });
    }
  }

  /**
   * Delete a configuration
   */
  static async deleteConfig(id: string): Promise<void> {
    const result = await safeExecute(async () => {
      await ConfigApiService.deleteConfig(id);
    }, { operation: 'deleteConfig', configId: id });

    if (result.error) {
      throw transformError(result.error, { operation: 'deleteConfig', configId: id });
    }
  }

  /**
   * Get active configurations
   */
  static async getActiveConfigs(): Promise<LiveDesktopConfig[]> {
    const configs = await ConfigApiService.getActiveConfigs();
    return configs.map(transformConfig);
  }

  /**
   * Update OCR regions for a configuration
   */
  static async updateOCRRegions(configId: string, regions: OCRRegion[]): Promise<void> {
    const result = await safeExecute(async () => {
      const config = await this.getConfig(configId);
      if (!config) {
        throw transformError(new Error('Configuration not found'), {
          operation: 'updateOCRRegions',
          configId,
          code: ErrorCode.NOT_FOUND,
        });
      }

      config.ocrRegions = regions;
      await this.updateConfig(configId, config);
    }, { operation: 'updateOCRRegions', configId, regionCount: regions.length });

    if (result.error) {
      throw transformError(result.error, { operation: 'updateOCRRegions', configId });
    }
  }

  /**
   * Toggle configuration active status
   */
  static async toggleActive(id: string, isActive: boolean): Promise<void> {
    await ConfigApiService.updateConfig(id, { is_active: isActive });
  }

  /**
   * Get configurations by category
   */
  static async getConfigsByCategory(category: string): Promise<LiveDesktopConfig[]> {
    const configs = await ConfigApiService.getConfigs({ category });
    return configs.map(transformConfig);
  }
}
