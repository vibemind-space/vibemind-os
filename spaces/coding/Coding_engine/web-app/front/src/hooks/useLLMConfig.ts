// front/src/hooks/useLLMConfig.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { llmConfigApi, type LLMConfig, type ModelRoleConfig } from '@/services/llmConfigApi';

export const llmConfigKeys = {
  all: ['llm-config'] as const,
  config: () => [...llmConfigKeys.all, 'current'] as const,
};

export function useLLMConfig() {
  return useQuery({
    queryKey: llmConfigKeys.config(),
    queryFn: () => llmConfigApi.getConfig(),
    staleTime: 30000,
    refetchOnWindowFocus: false,
  });
}

export function useUpdateLLMConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (models: Record<string, ModelRoleConfig>) => llmConfigApi.updateConfig(models),
    onSuccess: (data) => {
      queryClient.setQueryData(llmConfigKeys.config(), data);
    },
  });
}

export function useUpdateModelRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ role, config }: { role: string; config: ModelRoleConfig }) =>
      llmConfigApi.updateRole(role, config),
    onSuccess: (data) => {
      queryClient.setQueryData(llmConfigKeys.config(), data);
    },
  });
}
