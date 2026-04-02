/**
 * Custom hook for managing Live Desktop configurations
 *
 * MIGRATED: Now uses local FastAPI backend instead of Supabase
 */

import { useState, useEffect, useCallback } from 'react';
import { ConfigApiService, LiveDesktopConfig as ApiConfig } from '@/services/configApiService';
import { LiveDesktopConfig } from '@/types/liveDesktop';
import { useToast } from '@/hooks/use-toast';
import { WEBSOCKET_CONFIG } from '@/config/websocketConfig';

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

export const useLiveDesktopConfig = () => {
  const [configs, setConfigs] = useState<LiveDesktopConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  // Load configurations from local API
  const loadConfigs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await ConfigApiService.getConfigs();
      const typedConfigs = data.map(transformConfig);
      setConfigs(typedConfigs);
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading configs:', err);
      setError(message);
      toast({
        title: 'Error loading configurations',
        description: message,
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  // Create new configuration
  const createConfig = async (config: Partial<LiveDesktopConfig>) => {
    try {
      const data = await ConfigApiService.createConfig({
        name: config.name || 'New Configuration',
        description: config.description,
        category: config.category,
        configuration: config as Record<string, unknown>,
        is_active: true,
      });

      toast({
        title: 'Configuration created',
        description: `Configuration "${data.name}" has been created successfully.`,
      });

      await loadConfigs();
      return data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error creating config:', err);
      toast({
        title: 'Error creating configuration',
        description: message,
        variant: 'destructive',
      });
      throw err;
    }
  };

  // Update existing configuration
  const updateConfig = async (id: string, updates: Partial<LiveDesktopConfig>) => {
    try {
      await ConfigApiService.updateConfig(id, {
        name: updates.name,
        description: updates.description,
        category: updates.category,
        configuration: updates as Record<string, unknown>,
      });

      toast({
        title: 'Configuration updated',
        description: 'Configuration has been updated successfully.',
      });

      await loadConfigs();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error updating config:', err);
      toast({
        title: 'Error updating configuration',
        description: message,
        variant: 'destructive',
      });
      throw err;
    }
  };

  // Delete configuration
  const deleteConfig = async (id: string) => {
    try {
      await ConfigApiService.deleteConfig(id);

      toast({
        title: 'Configuration deleted',
        description: 'Configuration has been deleted successfully.',
      });

      await loadConfigs();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error deleting config:', err);
      toast({
        title: 'Error deleting configuration',
        description: message,
        variant: 'destructive',
      });
      throw err;
    }
  };

  // Toggle configuration active status
  const toggleConfigActive = async (id: string, isActive: boolean) => {
    try {
      await ConfigApiService.updateConfig(id, { is_active: isActive });
      await loadConfigs();
    } catch (err: unknown) {
      console.error('Error toggling config:', err);
      throw err;
    }
  };

  // Load configs on mount
  useEffect(() => {
    loadConfigs();
  }, [loadConfigs]);

  return {
    configs,
    loading,
    error,
    loadConfigs,
    createConfig,
    updateConfig,
    deleteConfig,
    toggleConfigActive,
  };
};
