/**
 * Debug API Client
 *
 * Communicates with the Python backend for debug session analysis
 * and fix task generation.
 */

import type { DebugInteraction, DebugFixTask } from '../stores/debugStore'

const API_BASE = 'http://localhost:8000/api/v1'

/**
 * Send recorded debug session interactions to backend for Claude analysis.
 * Returns generated fix tasks.
 */
export async function analyzeDebugSession(payload: {
  projectId: string
  outputDir: string
  interactions: DebugInteraction[]
}): Promise<{ success: boolean; fixTasks: DebugFixTask[]; error?: string }> {
  try {
    const response = await fetch(`${API_BASE}/dashboard/debug/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: payload.projectId,
        output_dir: payload.outputDir,
        interactions: payload.interactions.map((i) => ({
          type: i.type,
          timestamp: i.timestamp,
          x: i.x,
          y: i.y,
          errorType: i.errorType,
          errorMessage: i.errorMessage,
          sourceFile: i.sourceFile,
          lineNumber: i.lineNumber,
          logSource: i.logSource,
          logContent: i.logContent,
          componentInfo: i.componentInfo,
        })),
      }),
    })

    if (response.ok) {
      const data = await response.json()
      return {
        success: true,
        fixTasks: data.fix_tasks || [],
      }
    }

    return {
      success: false,
      fixTasks: [],
      error: `API error: ${response.statusText}`,
    }
  } catch (error: any) {
    console.error('[DebugAPI] Analysis failed:', error)
    return {
      success: false,
      fixTasks: [],
      error: error.message || 'Analysis failed',
    }
  }
}

/**
 * Fetch browser errors from the ErrorReceiverServer (port 8765).
 * Falls back to IPC if available.
 */
export async function getBrowserErrors(): Promise<any[]> {
  try {
    // Try IPC first (Electron)
    const api = (window as any).electronAPI
    if (api?.debug?.getBrowserErrors) {
      return await api.debug.getBrowserErrors()
    }

    // Fallback: direct HTTP to error receiver
    const response = await fetch('http://localhost:8765/api/browser-errors')
    if (response.ok) {
      const data = await response.json()
      return data.errors || []
    }
    return []
  } catch {
    return []
  }
}

/**
 * Fetch Docker container logs for a project.
 */
export async function getDockerLogs(
  projectId: string,
  tail: number = 200
): Promise<string> {
  try {
    const api = (window as any).electronAPI
    if (api?.debug?.getDockerLogs) {
      return await api.debug.getDockerLogs(projectId, tail)
    }
    return ''
  } catch {
    return ''
  }
}

/**
 * Capture a VNC screenshot for a project.
 */
export async function captureDebugScreenshot(
  projectId: string
): Promise<{ success: boolean; screenshot?: string }> {
  try {
    const api = (window as any).electronAPI
    if (api?.debug?.captureScreenshot) {
      return await api.debug.captureScreenshot(projectId)
    }
    return { success: false }
  } catch {
    return { success: false }
  }
}
