/**
 * VibeChat Component (Phase 31)
 *
 * Live-streaming chat interface for user intervention during pipeline execution.
 * Connects via WebSocket, auto-routes to Claude Code agents, streams output.
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Loader2, Bot, User, Wrench, CheckCircle } from 'lucide-react'
import { useVibeStore } from '../../stores/vibeStore'
import { createVibeSocket, sendVibePrompt } from '../../api/vibeAPI'
import type { VibeFrame } from '../../api/vibeAPI'

interface VibeChatProps {
  projectId: string
  outputDir: string
}

export function VibeChat({ projectId, outputDir }: VibeChatProps) {
  const [input, setInput] = useState('')
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const store = useVibeStore()

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [store.messages])

  // Connect WebSocket
  useEffect(() => {
    const ws = createVibeSocket(
      projectId,
      (frame: VibeFrame) => {
        switch (frame.type) {
          case 'agent':
            store.setCurrentAgent(frame.name || null)
            break
          case 'text':
            store.appendAssistantText(frame.content || '')
            break
          case 'tool_use':
            store.addToolUse(frame.tool || '', frame.file || '', frame.status || '')
            break
          case 'error':
            store.addErrorMessage(frame.message || 'Unknown error')
            break
          case 'complete':
            store.completeMessage(frame.files || [], frame.session_id || null)
            break
        }
      },
      () => store.setConnected(false),
    )

    ws.onopen = () => store.setConnected(true)
    wsRef.current = ws
    store.setProjectId(projectId)

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [projectId])

  const handleSend = useCallback(() => {
    if (!input.trim() || !wsRef.current || store.isStreaming) return

    store.addUserMessage(input)
    store.setStreaming(true)
    sendVibePrompt(wsRef.current, input, outputDir, store.sessionId || undefined)
    setInput('')
  }, [input, outputDir, store.sessionId, store.isStreaming])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full bg-gray-900 rounded-lg border border-gray-700">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
        <Bot className="w-5 h-5 text-purple-400" />
        <span className="text-sm font-medium text-gray-200">Vibe Coder</span>
        {store.currentAgent && (
          <span className="px-2 py-0.5 text-xs rounded-full bg-purple-900 text-purple-300">
            {store.currentAgent}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <div className={`w-2 h-2 rounded-full ${store.connected ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-xs text-gray-500">
            {store.connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {store.messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role !== 'user' && (
              <div className="w-7 h-7 rounded-full bg-purple-900 flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4 text-purple-300" />
              </div>
            )}
            <div className={`max-w-[80%] ${
              msg.role === 'user'
                ? 'bg-blue-900 text-blue-100 rounded-2xl rounded-br-md px-4 py-2'
                : msg.role === 'system'
                ? 'bg-red-900/50 text-red-300 rounded-lg px-4 py-2'
                : 'bg-gray-800 text-gray-200 rounded-2xl rounded-bl-md px-4 py-2'
            }`}>
              <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
              {msg.toolUses && msg.toolUses.length > 0 && (
                <div className="mt-2 space-y-1">
                  {msg.toolUses.map((tu, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-xs text-gray-400">
                      <Wrench className="w-3 h-3" />
                      <span className="text-purple-400">{tu.tool}</span>
                      <span className="truncate">{tu.file}</span>
                    </div>
                  ))}
                </div>
              )}
              {msg.files && msg.files.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-700">
                  <div className="flex items-center gap-1.5 text-xs text-green-400">
                    <CheckCircle className="w-3 h-3" />
                    <span>{msg.files.length} file{msg.files.length > 1 ? 's' : ''} changed</span>
                  </div>
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-blue-900 flex items-center justify-center flex-shrink-0">
                <User className="w-4 h-4 text-blue-300" />
              </div>
            )}
          </div>
        ))}

        {store.isStreaming && (
          <div className="flex items-center gap-2 text-purple-400 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{store.currentAgent || 'Agent'} is working...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-gray-700">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={store.isStreaming ? 'Agent is working...' : 'Describe what to fix or change...'}
            disabled={store.isStreaming || !store.connected}
            rows={1}
            className="flex-1 bg-gray-800 text-gray-200 rounded-lg px-4 py-2 text-sm resize-none
                       border border-gray-600 focus:border-purple-500 focus:outline-none
                       disabled:opacity-50 placeholder-gray-500"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || store.isStreaming || !store.connected}
            className="px-3 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700
                       rounded-lg text-white transition-colors disabled:opacity-50"
          >
            {store.isStreaming ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
        {store.sessionId && (
          <div className="mt-1 text-xs text-gray-600">
            Session: {store.sessionId.slice(0, 8)}...
          </div>
        )}
      </div>
    </div>
  )
}
