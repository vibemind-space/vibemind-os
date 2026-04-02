/**
 * Vibe-Coding state management (Phase 31).
 */
import { create } from 'zustand'
import type { VibeFrame, VibeHistoryEntry } from '../api/vibeAPI'

export interface VibeMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  agent?: string
  toolUses?: Array<{ tool: string; file: string; status: string }>
  files?: string[]
  timestamp: Date
}

interface VibeState {
  // Connection
  connected: boolean
  projectId: string | null
  sessionId: string | null

  // Messages
  messages: VibeMessage[]
  isStreaming: boolean
  currentAgent: string | null

  // History
  history: VibeHistoryEntry[]

  // Actions
  setConnected: (connected: boolean) => void
  setProjectId: (id: string) => void
  setSessionId: (id: string | null) => void
  setStreaming: (streaming: boolean) => void
  setCurrentAgent: (agent: string | null) => void
  addUserMessage: (content: string) => void
  appendAssistantText: (content: string) => void
  addToolUse: (tool: string, file: string, status: string) => void
  completeMessage: (files: string[], sessionId: string | null) => void
  addErrorMessage: (message: string) => void
  setHistory: (history: VibeHistoryEntry[]) => void
  clearMessages: () => void
}

let msgCounter = 0
const nextId = () => `vibe-${++msgCounter}-${Date.now()}`

export const useVibeStore = create<VibeState>((set, get) => ({
  connected: false,
  projectId: null,
  sessionId: null,
  messages: [],
  isStreaming: false,
  currentAgent: null,
  history: [],

  setConnected: (connected) => set({ connected }),
  setProjectId: (id) => set({ projectId: id }),
  setSessionId: (id) => set({ sessionId: id }),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  setCurrentAgent: (agent) => set({ currentAgent: agent }),

  addUserMessage: (content) => set((state) => ({
    messages: [...state.messages, {
      id: nextId(),
      role: 'user',
      content,
      timestamp: new Date(),
    }],
  })),

  appendAssistantText: (content) => set((state) => {
    const msgs = [...state.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant' && !last.files) {
      msgs[msgs.length - 1] = { ...last, content: last.content + content }
    } else {
      msgs.push({
        id: nextId(),
        role: 'assistant',
        content,
        agent: state.currentAgent || undefined,
        toolUses: [],
        timestamp: new Date(),
      })
    }
    return { messages: msgs }
  }),

  addToolUse: (tool, file, status) => set((state) => {
    const msgs = [...state.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') {
      const toolUses = [...(last.toolUses || []), { tool, file, status }]
      msgs[msgs.length - 1] = { ...last, toolUses }
    }
    return { messages: msgs }
  }),

  completeMessage: (files, sessionId) => set((state) => {
    const msgs = [...state.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') {
      msgs[msgs.length - 1] = { ...last, files }
    }
    return {
      messages: msgs,
      isStreaming: false,
      sessionId: sessionId || state.sessionId,
    }
  }),

  addErrorMessage: (message) => set((state) => ({
    messages: [...state.messages, {
      id: nextId(),
      role: 'system',
      content: `Error: ${message}`,
      timestamp: new Date(),
    }],
    isStreaming: false,
  })),

  setHistory: (history) => set({ history }),
  clearMessages: () => set({ messages: [], sessionId: null, currentAgent: null }),
}))
