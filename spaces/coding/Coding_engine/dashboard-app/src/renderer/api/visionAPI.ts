/**
 * Vision API Client for Review Gate
 *
 * Provides functions to capture VNC screenshots and analyze them with Claude Vision.
 */

const API_BASE = 'http://localhost:8000/api/v1'

export interface VisionAnalysisResult {
  analysis: string
  success: boolean
  error?: string
}

/**
 * Capture a screenshot from the VNC iframe.
 *
 * This attempts to get the canvas element from the noVNC iframe and convert it to base64.
 * Due to CORS restrictions, this may not work in all cases.
 */
export async function captureVNCScreenshot(vncPort: number): Promise<string | null> {
  try {
    // Find the VNC iframe
    const iframe = document.querySelector(
      `iframe[src*="localhost:${vncPort}"]`
    ) as HTMLIFrameElement

    if (!iframe) {
      console.warn('[VisionAPI] VNC iframe not found')
      return null
    }

    // Try to access the canvas inside the iframe
    // Note: This may be blocked by CORS if the iframe is from a different origin
    try {
      const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document
      if (iframeDoc) {
        const canvas = iframeDoc.querySelector('canvas')
        if (canvas) {
          return canvas.toDataURL('image/png')
        }
      }
    } catch (corsError) {
      console.warn('[VisionAPI] Cannot access iframe content due to CORS')
    }

    // Fallback: Use html2canvas or similar to capture the visible area
    // For now, we'll return null and let the backend handle it
    console.warn('[VisionAPI] Could not capture VNC canvas, will try backend capture')
    return null
  } catch (error) {
    console.error('[VisionAPI] Screenshot capture failed:', error)
    return null
  }
}

/**
 * Capture screenshot via backend (Docker exec into container).
 *
 * This is more reliable than trying to capture the canvas from the iframe.
 */
export async function captureVNCScreenshotViaBackend(
  projectId: string
): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE}/vnc/${projectId}/screenshot`, {
      method: 'POST'
    })

    if (response.ok) {
      const data = await response.json()
      return data.screenshot // base64 encoded
    }

    console.error('[VisionAPI] Backend screenshot failed:', response.statusText)
    return null
  } catch (error) {
    console.error('[VisionAPI] Backend screenshot error:', error)
    return null
  }
}

/**
 * Analyze a screenshot with Claude Vision.
 */
export async function analyzeWithVision(
  screenshot: string,
  userMessage: string
): Promise<VisionAnalysisResult> {
  try {
    const response = await fetch(`${API_BASE}/vision/analyze-ui-feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: screenshot,
        prompt: userMessage,
        max_tokens: 1024
      })
    })

    if (response.ok) {
      const data = await response.json()
      return {
        analysis: data.analysis,
        success: data.success,
        error: data.error
      }
    }

    return {
      analysis: '',
      success: false,
      error: `API error: ${response.statusText}`
    }
  } catch (error: any) {
    console.error('[VisionAPI] Analysis failed:', error)
    return {
      analysis: '',
      success: false,
      error: error.message || 'Analysis failed'
    }
  }
}

/**
 * Submit feedback for a paused generation.
 */
export async function submitReviewFeedback(
  projectId: string,
  feedback: string
): Promise<boolean> {
  try {
    const response = await fetch(
      `${API_BASE}/dashboard/generation/${projectId}/feedback`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback })
      }
    )
    return response.ok
  } catch (error) {
    console.error('[VisionAPI] Submit feedback failed:', error)
    return false
  }
}

/**
 * Get the current review status.
 */
export async function getReviewStatus(
  projectId: string
): Promise<{ paused: boolean; has_feedback: boolean } | null> {
  try {
    const response = await fetch(
      `${API_BASE}/dashboard/generation/${projectId}/review-status`
    )

    if (response.ok) {
      return await response.json()
    }
    return null
  } catch (error) {
    console.error('[VisionAPI] Get review status failed:', error)
    return null
  }
}
