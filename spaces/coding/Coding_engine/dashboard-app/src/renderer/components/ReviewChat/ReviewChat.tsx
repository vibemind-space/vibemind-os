/**
 * ReviewChat Component
 *
 * Multi-mode interactive panel:
 *   1. Chat Mode: Cursor-like Claude CLI chat for code editing
 *   2. Debug Mode: Screen recording + error tracking + auto fix-task generation
 *
 * Works both during generation pause (Review Gate) and active generation.
 */

import { useState, useRef, useEffect } from 'react'
import {
  Send,
  PlayCircle,
  Loader2,
  Bot,
  User,
  Code,
  FileText,
  Circle,
  Square,
  MousePointer2,
  AlertTriangle,
  Terminal,
  Wrench,
  Sparkles,
} from 'lucide-react'
import {
  captureVNCScreenshot,
  analyzeWithVision,
  type VisionAnalysisResult,
} from '../../api/visionAPI'
import type { DebugInteraction, DebugFixTask } from '../../stores/debugStore'
import { VibeChat } from '../VibeChat'

export interface ReviewMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  screenshot?: string
  filesModified?: string[]
  filesCreated?: string[]
  timestamp: Date
}

interface ReviewChatProps {
  projectId: string
  projectPath?: string
  outputDir?: string
  vncPort?: number
  onResume?: (feedback: string) => void
  onCancel?: () => void
  mode?: 'debug' | 'chat' | 'vibe'
  // Debug mode props
  debugInteractions?: DebugInteraction[]
  debugFixTasks?: DebugFixTask[]
  onStartRecording?: () => void
  onStopRecording?: () => void
  onAnalyze?: () => void
  recording?: boolean
  analyzing?: boolean
}

export function ReviewChat({
  projectId,
  projectPath,
  outputDir,
  vncPort,
  onResume,
  onCancel,
  mode = 'chat',
  debugInteractions = [],
  debugFixTasks = [],
  onStartRecording,
  onStopRecording,
  onAnalyze,
  recording = false,
  analyzing: debugAnalyzing = false,
}: ReviewChatProps) {
  const [messages, setMessages] = useState<ReviewMessage[]>([])
  const [input, setInput] = useState('')
  const [chatAnalyzing, setChatAnalyzing] = useState(false)
  const [screenshotError, setScreenshotError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const timelineEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll
  useEffect(() => {
    if (mode === 'chat') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, mode])

  useEffect(() => {
    if (mode === 'debug') {
      timelineEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [debugInteractions, mode])

  // Build conversation history for Claude context
  const getConversationHistory = () =>
    messages.map((m) => ({ role: m.role, content: m.content }))

  const sendMessage = async () => {
    if (!input.trim() || chatAnalyzing) return

    const userMessage = input.trim()
    setInput('')
    setScreenshotError(null)

    const userMsg: ReviewMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: userMessage,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setChatAnalyzing(true)

    try {
      const api = window.electronAPI as any
      const hasClaudeChat = api?.claude?.chat
      const hasProjectContext = projectPath && outputDir

      if (hasClaudeChat && hasProjectContext) {
        const result = await api.claude.chat({
          message: userMessage,
          projectPath,
          outputDir,
          conversationHistory: getConversationHistory(),
        })

        const assistantMsg: ReviewMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: result.success
            ? result.response || 'Changes applied.'
            : `Error: ${result.error}`,
          filesModified: result.files_modified || [],
          filesCreated: result.files_created || [],
          timestamp: new Date(),
        }
        setMessages((prev) => [...prev, assistantMsg])
      } else {
        // Fallback: Vision mode
        let screenshot: string | null = null
        if (vncPort) {
          screenshot = await captureVNCScreenshot(vncPort)
          if (!screenshot) {
            setScreenshotError('Could not capture VNC screenshot (CORS restriction)')
          }
        }

        let analysis: VisionAnalysisResult | null = null
        if (screenshot) {
          analysis = await analyzeWithVision(screenshot, userMessage)
        }

        const assistantMsg: ReviewMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: analysis?.success
            ? analysis.analysis
            : analysis?.error
              ? `Analysis failed: ${analysis.error}\n\nYour feedback has been recorded.`
              : 'Your feedback has been recorded.',
          screenshot: screenshot || undefined,
          timestamp: new Date(),
        }
        setMessages((prev) => [...prev, assistantMsg])
      }
    } catch (error: any) {
      console.error('[ReviewChat] Error:', error)
      const errorMsg: ReviewMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Error: ${error.message}`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setChatAnalyzing(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // ─── Vibe Mode (Phase 31) ────────────────────────────────────────────────────

  if (mode === 'vibe') {
    return <VibeChat projectId={projectId} outputDir={outputDir || '.'} />
  }

  // ─── Debug Mode ───────────────────────────────────────────────────────────────

  if (mode === 'debug') {
    const errorCount = debugInteractions.filter(
      (i) => i.type === 'error' || i.type === 'log'
    ).length
    const clickCount = debugInteractions.filter((i) => i.type === 'click').length

    return (
      <div className="flex flex-col h-full bg-engine-dark rounded-lg border border-gray-700">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-gray-200">Debug Session</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Record interactions + capture errors
            </p>
          </div>
          <div className="flex items-center gap-2">
            {recording ? (
              <button
                onClick={onStopRecording}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-xs font-medium transition"
              >
                <Square className="w-3 h-3" />
                Stop
              </button>
            ) : (
              <button
                onClick={onStartRecording}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600/80 hover:bg-red-600 rounded text-xs font-medium transition"
              >
                <Circle className="w-3 h-3 fill-current" />
                Record
              </button>
            )}
          </div>
        </div>

        {/* Stats bar */}
        <div className="px-4 py-2 border-b border-gray-700/50 flex items-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1">
            <MousePointer2 className="w-3 h-3" />
            {clickCount} clicks
          </span>
          <span className="flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-red-400" />
            {errorCount} errors
          </span>
          <span className="flex items-center gap-1">
            <Wrench className="w-3 h-3 text-blue-400" />
            {debugFixTasks.length} fix tasks
          </span>
        </div>

        {/* Timeline */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {debugInteractions.length === 0 && !recording && (
            <div className="text-center text-gray-500 py-8">
              <MousePointer2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No interactions recorded</p>
              <p className="text-xs mt-1">
                Click "Record" and interact with the VNC preview
              </p>
            </div>
          )}

          {debugInteractions.length === 0 && recording && (
            <div className="text-center text-gray-500 py-8">
              <div className="w-3 h-3 rounded-full bg-red-500 animate-pulse mx-auto mb-3" />
              <p className="text-sm">Recording...</p>
              <p className="text-xs mt-1">
                Click on the VNC preview to record interactions
              </p>
            </div>
          )}

          {debugInteractions.map((interaction) => (
            <InteractionRow key={interaction.id} interaction={interaction} />
          ))}

          <div ref={timelineEndRef} />
        </div>

        {/* Fix Tasks Section */}
        {debugFixTasks.length > 0 && (
          <div className="border-t border-gray-700 max-h-48 overflow-y-auto">
            <div className="px-4 py-2 bg-gray-800/50">
              <h4 className="text-xs font-medium text-gray-300 flex items-center gap-1">
                <Wrench className="w-3 h-3" />
                Fix Tasks ({debugFixTasks.length})
              </h4>
            </div>
            <div className="p-2 space-y-1">
              {debugFixTasks.map((task) => (
                <FixTaskRow key={task.id} task={task} />
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="p-3 border-t border-gray-700">
          <button
            onClick={onAnalyze}
            disabled={debugInteractions.length === 0 || debugAnalyzing || recording}
            className="w-full px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition flex items-center justify-center gap-2"
          >
            {debugAnalyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Analyzing with Claude...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Analyze & Create Fix Tasks
              </>
            )}
          </button>
        </div>
      </div>
    )
  }

  // ─── Chat Mode (default) ─────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-engine-dark rounded-lg border border-gray-700">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700">
        <h3 className="text-sm font-medium text-gray-200">Claude Assistant</h3>
        <p className="text-xs text-gray-500 mt-1">
          Ask Claude to fix code, explain errors, or make changes.
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            <Code className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Chat with Claude</p>
            <p className="text-xs mt-1">
              "Fix the login form", "Add dark mode", "Why is the build failing?"
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}

        {chatAnalyzing && <TypingIndicator />}

        <div ref={messagesEndRef} />
      </div>

      {/* Screenshot Error */}
      {screenshotError && (
        <div className="px-4 py-2 bg-yellow-900/30 border-t border-yellow-700/50">
          <p className="text-xs text-yellow-400">{screenshotError}</p>
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t border-gray-700">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask Claude anything..."
            rows={2}
            className="flex-1 p-3 bg-gray-800 border border-gray-600 rounded-lg text-sm resize-none focus:outline-none focus:border-blue-500"
            disabled={chatAnalyzing}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || chatAnalyzing}
            className="px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg transition"
          >
            {chatAnalyzing ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Continue Button (only when onResume is provided) */}
        {onResume && messages.length > 0 && (
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => {
                const feedbackContext = messages
                  .filter((m) => m.role === 'user')
                  .map((m) => `- ${m.content}`)
                  .join('\n')
                onResume(feedbackContext)
              }}
              className="flex-1 px-4 py-3 bg-green-600 hover:bg-green-700 rounded-lg text-sm font-medium transition flex items-center justify-center gap-2"
            >
              <PlayCircle className="w-5 h-5" />
              Continue ({messages.filter((m) => m.role === 'user').length} feedback items)
            </button>
            {onCancel && (
              <button
                onClick={onCancel}
                className="px-4 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition"
              >
                Cancel
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

/** Timeline row for a single debug interaction */
function InteractionRow({ interaction }: { interaction: DebugInteraction }) {
  const time = new Date(interaction.timestamp).toLocaleTimeString()

  if (interaction.type === 'click') {
    return (
      <div className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-gray-800/50 text-xs">
        <MousePointer2 className="w-3.5 h-3.5 text-blue-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-gray-400">{time}</span>
          <span className="text-gray-300 ml-2">
            Click ({interaction.x}%, {interaction.y}%)
          </span>
          {interaction.componentInfo && (
            <span className="text-blue-400 ml-1">{interaction.componentInfo}</span>
          )}
        </div>
      </div>
    )
  }

  if (interaction.type === 'error') {
    return (
      <div className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-gray-800/50 text-xs bg-red-900/10">
        <AlertTriangle className="w-3.5 h-3.5 text-red-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-gray-400">{time}</span>
          <span className="text-red-300 ml-2 break-all">
            {interaction.errorMessage || 'Unknown error'}
          </span>
          {interaction.sourceFile && (
            <span className="text-gray-500 ml-1">
              ({interaction.sourceFile}
              {interaction.lineNumber ? `:${interaction.lineNumber}` : ''})
            </span>
          )}
        </div>
      </div>
    )
  }

  // type === 'log'
  return (
    <div className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-gray-800/50 text-xs bg-yellow-900/10">
      <Terminal className="w-3.5 h-3.5 text-yellow-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-gray-400">{time}</span>
        <span className="text-yellow-400 ml-1">
          [{interaction.logSource || 'log'}]
        </span>
        <span className="text-gray-300 ml-1 break-all">
          {interaction.logContent || interaction.errorMessage || 'Log entry'}
        </span>
      </div>
    </div>
  )
}

/** Fix task row in the debug panel */
function FixTaskRow({ task }: { task: DebugFixTask }) {
  const severityColor: Record<string, string> = {
    critical: 'text-red-400 bg-red-900/20',
    high: 'text-orange-400 bg-orange-900/20',
    medium: 'text-yellow-400 bg-yellow-900/20',
    low: 'text-gray-400 bg-gray-800',
  }
  const color = severityColor[task.severity] || severityColor.medium

  return (
    <div className={`px-3 py-2 rounded text-xs ${color}`}>
      <div className="flex items-start gap-2">
        <Wrench className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="font-medium">{task.title}</p>
          <p className="text-gray-400 mt-0.5">{task.description}</p>
          {task.affectedFiles.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {task.affectedFiles.map((f) => (
                <span key={f} className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-400">
                  {f}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Chat bubble for chat mode */
function ChatBubble({ message }: { message: ReviewMessage }) {
  const isUser = message.role === 'user'
  const hasFiles =
    (message.filesModified?.length || 0) + (message.filesCreated?.length || 0) > 0

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser ? 'bg-blue-600' : 'bg-purple-600'
        }`}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div
        className={`max-w-[80%] rounded-lg p-3 ${
          isUser ? 'bg-blue-600/20 border border-blue-600/30' : 'bg-gray-800'
        }`}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>

        {hasFiles && (
          <div className="mt-2 space-y-1">
            {message.filesModified?.map((f) => (
              <div key={f} className="flex items-center gap-1 text-xs text-yellow-400">
                <FileText className="w-3 h-3" />
                <span>{f}</span>
              </div>
            ))}
            {message.filesCreated?.map((f) => (
              <div key={f} className="flex items-center gap-1 text-xs text-green-400">
                <FileText className="w-3 h-3" />
                <span>+ {f}</span>
              </div>
            ))}
          </div>
        )}

        {message.screenshot && (
          <div className="mt-2">
            <img
              src={message.screenshot}
              alt="Screenshot"
              className="max-w-full rounded border border-gray-700"
            />
          </div>
        )}
        <p className="text-xs text-gray-500 mt-1">
          {message.timestamp.toLocaleTimeString()}
        </p>
      </div>
    </div>
  )
}

/** Typing indicator for chat mode */
function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-full flex items-center justify-center bg-purple-600">
        <Bot className="w-4 h-4" />
      </div>
      <div className="bg-gray-800 rounded-lg p-3">
        <div className="flex gap-1">
          <div className="w-2 h-2 rounded-full bg-gray-500 animate-bounce" />
          <div
            className="w-2 h-2 rounded-full bg-gray-500 animate-bounce"
            style={{ animationDelay: '0.1s' }}
          />
          <div
            className="w-2 h-2 rounded-full bg-gray-500 animate-bounce"
            style={{ animationDelay: '0.2s' }}
          />
        </div>
      </div>
    </div>
  )
}
