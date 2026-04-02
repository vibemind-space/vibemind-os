// front/src/hooks/useEngine.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { engineApi, getDbProjects, type EngineProject, type EngineProjectDetail, type GenerationStatus } from '@/services/engineApi';

export const engineKeys = {
  all: ['engine'] as const,
  projects: () => [...engineKeys.all, 'projects'] as const,
  dbProjects: () => [...engineKeys.all, 'db-projects'] as const,
  project: (name: string) => [...engineKeys.all, 'project', name] as const,
  status: (name: string) => [...engineKeys.all, 'status', name] as const,
};

export function useEngineProjects() {
  return useQuery({
    queryKey: engineKeys.projects(),
    queryFn: async () => {
      // Try local-projects scan, but don't fail if it errors
      try {
        return await engineApi.listProjects();
      } catch {
        return [] as EngineProject[];
      }
    },
    staleTime: 60000,
    refetchOnWindowFocus: false,
  });
}

// DB-backed projects from PostgreSQL (/api/v1/db/projects)
export function useDbProjects() {
  return useQuery({
    queryKey: engineKeys.dbProjects(),
    queryFn: async () => {
      try {
        return await getDbProjects();
      } catch {
        return [];
      }
    },
    staleTime: 30000,
    refetchOnWindowFocus: true,
  });
}

export function useEngineProject(name: string, enabled = true) {
  return useQuery({
    queryKey: engineKeys.project(name),
    queryFn: () => engineApi.getProject(name),
    enabled: enabled && !!name,
    staleTime: 60000,
  });
}

export function useGenerationStatus(name: string, enabled = true) {
  return useQuery({
    queryKey: engineKeys.status(name),
    queryFn: () => engineApi.getStatus(name),
    enabled: enabled && !!name,
    refetchInterval: 3000, // Always poll — backend generation can start externally
    retry: 1,
  });
}

export function useStartGeneration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, projectPath, parallelism }: {
      name: string;
      projectPath?: string;
      parallelism?: number;
    }) =>
      engineApi.startGeneration(name, { projectPath, parallelism }),
    onSuccess: (status) => {
      queryClient.setQueryData(engineKeys.status(status.project_name), status);
      queryClient.invalidateQueries({ queryKey: engineKeys.projects() });
    },
  });
}

export function useStopGeneration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => engineApi.stopGeneration(name),
    onSuccess: (status) => {
      queryClient.setQueryData(engineKeys.status(status.project_name), status);
    },
  });
}

// ── Project Data Hooks (DB-backed) ──────────────────────

const API = '/api/v1/dashboard';

export function useEpics(projectPath: string | null) {
  return useQuery({
    queryKey: ['epics', projectPath],
    queryFn: async () => {
      const res = await fetch(`${API}/epics?project_path=${encodeURIComponent(projectPath!)}`);
      if (!res.ok) return { epics: [] };
      return res.json();
    },
    staleTime: 10000,
    refetchInterval: 15000,
    enabled: !!projectPath,
  });
}

export function useEpicTasks(dbProjectId: number, epicId: string) {
  return useQuery({
    queryKey: ['epic-tasks', dbProjectId, epicId],
    queryFn: async () => {
      const res = await fetch(`${API}/epics/${dbProjectId}/${epicId}/tasks`);
      if (!res.ok) return { tasks: [] };
      return res.json();
    },
    staleTime: 5000,
    enabled: dbProjectId > 0 && !!epicId,
  });
}

export function useFixTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { taskId: string; epicId?: string; errorMessage?: string }) => {
      const res = await fetch(`${API}/fix-task`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: params.taskId,
          epic_id: params.epicId || '',
          error_message: params.errorMessage || 'Fix requested from UI',
          max_retries: 3,
        }),
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['epics'] });
      queryClient.invalidateQueries({ queryKey: engineKeys.dbProjects() });
    },
  });
}

export function useFixAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (dbJobId: number) => {
      const res = await fetch(`${API}/fixall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: dbJobId }),
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['epics'] });
      queryClient.invalidateQueries({ queryKey: engineKeys.dbProjects() });
    },
  });
}

export function useImportProjectData() {
  return useMutation({
    mutationFn: async (projectName: string) => {
      const res = await fetch(`${API}/import-project-data?project_name=${encodeURIComponent(projectName)}`, {
        method: 'POST',
      });
      return res.json();
    },
  });
}
