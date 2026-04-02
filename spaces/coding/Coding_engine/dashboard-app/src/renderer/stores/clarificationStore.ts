/**
 * ClarificationStore - Zustand store for clarification queue management.
 *
 * Manages the state of pending clarifications and provides actions
 * for resolving them.
 */

import { create } from 'zustand';
import {
  QueuedClarification,
  ClarificationStatistics,
  fetchPendingClarifications,
  submitClarificationChoice,
  useAllDefaultClarifications,
} from '../api/clarificationAPI';

interface ClarificationState {
  // State
  pending: QueuedClarification[];
  statistics: ClarificationStatistics | null;
  queueMode: boolean;
  isPanelOpen: boolean;
  selectedId: string | null;
  isEditorOpen: boolean;
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;

  // Actions
  setPending: (items: QueuedClarification[]) => void;
  setStatistics: (stats: ClarificationStatistics) => void;
  openPanel: () => void;
  closePanel: () => void;
  selectClarification: (id: string) => void;
  closeEditor: () => void;
  refreshPending: () => Promise<void>;
  submitChoice: (clarificationId: string, interpretationId: string) => Promise<boolean>;
  useAllDefaults: () => Promise<boolean>;
  clearError: () => void;
}

export const useClarificationStore = create<ClarificationState>((set, get) => ({
  // Initial state
  pending: [],
  statistics: null,
  queueMode: false,
  isPanelOpen: false,
  selectedId: null,
  isEditorOpen: false,
  isLoading: false,
  error: null,
  lastUpdated: null,

  // Simple setters
  setPending: (items) => set({ pending: items }),
  setStatistics: (stats) => set({ statistics: stats }),

  // Panel actions
  openPanel: () => set({ isPanelOpen: true }),
  closePanel: () => set({ isPanelOpen: false }),

  // Editor actions
  selectClarification: (id) =>
    set({
      selectedId: id,
      isEditorOpen: true,
      isPanelOpen: false,
    }),

  closeEditor: () =>
    set({
      isEditorOpen: false,
      selectedId: null,
    }),

  clearError: () => set({ error: null }),

  // Async actions
  refreshPending: async () => {
    set({ isLoading: true, error: null });

    try {
      const response = await fetchPendingClarifications();
      set({
        pending: response.pending,
        statistics: response.statistics,
        queueMode: response.queue_mode,
        isLoading: false,
        lastUpdated: new Date(),
      });
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : 'Failed to fetch clarifications',
      });
    }
  },

  submitChoice: async (clarificationId: string, interpretationId: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await submitClarificationChoice(clarificationId, interpretationId);

      if (response.success) {
        // Refresh the pending list
        await get().refreshPending();

        // Close the editor
        set({
          isEditorOpen: false,
          selectedId: null,
          isLoading: false,
        });

        return true;
      } else {
        set({ isLoading: false, error: 'Failed to submit choice' });
        return false;
      }
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : 'Failed to submit choice',
      });
      return false;
    }
  },

  useAllDefaults: async () => {
    set({ isLoading: true, error: null });

    try {
      const response = await useAllDefaultClarifications();

      if (response.success) {
        // Refresh the pending list
        await get().refreshPending();

        // Close the panel
        set({
          isPanelOpen: false,
          isLoading: false,
        });

        return true;
      } else {
        set({ isLoading: false, error: 'Failed to use defaults' });
        return false;
      }
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : 'Failed to use defaults',
      });
      return false;
    }
  },
}));

// Selector for getting the selected clarification
export const useSelectedClarification = () => {
  const pending = useClarificationStore((state) => state.pending);
  const selectedId = useClarificationStore((state) => state.selectedId);

  if (!selectedId) return null;
  return pending.find((c) => c.id === selectedId) || null;
};

// Selector for pending count
export const usePendingCount = () => {
  return useClarificationStore((state) => state.pending.length);
};

// Selector for high priority count
export const useHighPriorityCount = () => {
  return useClarificationStore((state) =>
    state.pending.filter((c) => c.priority === 1).length
  );
};
