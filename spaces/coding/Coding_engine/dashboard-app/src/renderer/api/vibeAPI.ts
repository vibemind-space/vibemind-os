/**
 * Vibe-Coding WebSocket client (Phase 31).
 * Connects to /api/v1/vibe/ws/{projectId} for live agent streaming.
 */
import { API_BASE_URL } from './config'

export interface VibeFrame {
  type: 'agent' | 'text' | 'tool_use' | 'error' | 'complete'
  name?: string         // agent type
  content?: string      // text content
  tool?: string         // tool name
  file?: string         // file path
  status?: string       // tool status
  message?: string      // error message
  files?: string[]      // changed files (complete)
  session_id?: string   // session ID (complete)
  success?: boolean     // success flag (complete)
}

export interface VibeHistoryEntry {
  id: string
  prompt: string
  agent: string
  files: string[]
  success: boolean
  timestamp: string
  session_id?: string
}

export function createVibeSocket(
  projectId: string,
  onFrame: (frame: VibeFrame) => void,
  onClose?: () => void,
): WebSocket {
  // Derive WS URL from API base (http://localhost:8000 -> ws://localhost:8000)
  // This works in Electron (file://), Electron dev (localhost:5173), and web mode
  const wsBase = API_BASE_URL.replace(/^http/, 'ws')
  const ws = new WebSocket(`${wsBase}/api/v1/vibe/ws/${projectId}`)

  ws.onmessage = (event) => {
    try {
      const frame: VibeFrame = JSON.parse(event.data)
      onFrame(frame)
    } catch (e) {
      console.error('Failed to parse vibe frame:', e)
    }
  }

  ws.onclose = () => onClose?.()
  ws.onerror = (e) => console.error('Vibe WS error:', e)

  return ws
}

export async function sendVibePrompt(
  ws: WebSocket,
  prompt: string,
  outputDir: string,
  sessionId?: string,
): Promise<void> {
  ws.send(JSON.stringify({
    prompt,
    output_dir: outputDir,
    session_id: sessionId,
  }))
}

export async function fetchVibeHistory(): Promise<VibeHistoryEntry[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/vibe/history`)
  if (!res.ok) return []
  return res.json()
}
