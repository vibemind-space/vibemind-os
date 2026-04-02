"""
Video Analysis Agent - Frame-Analyse mit Nemotron Vision Model.

Analysiert Desktop-Screenshots nach Tool-Ausfuehrungen und generiert
strukturierte JSON-Trainingsdaten die Ausfuehrungsschritte + visuelle
Verifikation kombinieren.

Model: nvidia/nemotron-nano-12b-v2-vl (via OpenRouter)
Pricing: $0.20/1M input, $0.60/1M output (~$0.002 per frame analysis)
"""

import os
import json
import base64
import logging
import asyncio
import time
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def _get_vision_model() -> str:
    try:
        from app.config import get_settings
        return get_settings().vision_model
    except Exception:
        return "nvidia/nemotron-nano-12b-v2-vl:free"

# Training data directory
TRAINING_DIR = Path(__file__).parent.parent.parent / "training_data"
TRAINING_DIR.mkdir(exist_ok=True)

# Skip analysis for these tools (they already read screen or are meta-tools)
SKIP_TOOLS = {"read_screen", "get_focus", "update_tasks", "screen_read", "screen_scan"}


async def capture_current_frame(quality: int = 50, viewport: dict = None) -> Optional[str]:
    """Capture current screen as base64 JPEG for video agent.

    In remote mode: reads from StreamFrameCache (frames from desktop client).
    In local mode: captures via pyautogui.screenshot().
    Optional viewport dict {x, y, width, height} crops to a screen region.
    """
    raw_data = None
    try:
        from app.config import get_settings
        if get_settings().execution_mode == "remote":
            from moire_agents.stream_frame_cache import StreamFrameCache
            # Use short TTL (500ms) for video agent — fresh frames are critical
            frame = StreamFrameCache.get_fresh_frame(monitor_id=0, max_age_ms=500)
            if frame and frame.data:
                data = frame.data
                # Strip data URI prefix if present
                if data.startswith("data:"):
                    data = data.split(",", 1)[1] if "," in data else data
                raw_data = data
            else:
                logger.debug("[VideoAgent] No fresh frame in StreamFrameCache")
                return None
        else:
            import pyautogui
            screenshot = pyautogui.screenshot()
            buffer = BytesIO()
            screenshot.save(buffer, format="JPEG", quality=quality)
            raw_data = base64.b64encode(buffer.getvalue()).decode()
    except Exception as e:
        logger.debug(f"[VideoAgent] Frame capture failed: {e}")
        return None

    # Crop to viewport if specified
    if viewport and raw_data:
        try:
            from PIL import Image
            img = Image.open(BytesIO(base64.b64decode(raw_data)))
            vx = max(0, int(viewport.get("x", 0)))
            vy = max(0, int(viewport.get("y", 0)))
            vw = int(viewport.get("width", 300))
            vh = int(viewport.get("height", 300))
            cropped = img.crop((vx, vy, vx + vw, vy + vh))
            buffer = BytesIO()
            cropped.save(buffer, format="JPEG", quality=quality)
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception:
            pass  # Fall through to full frame

    return raw_data


class VideoAgent:
    """Analyzes desktop frames using Nemotron vision model via OpenRouter.

    Supports two modes:
    - Guardian Mode: Auto-correct failed actions (max retries)
    - Monitor Mode: Realtime screen monitoring via StreamFrameCache listener
    """

    def __init__(self, guardian_mode: bool = False, monitor_mode: bool = False):
        self._session_data: Dict[str, List[Dict]] = {}  # conversation_id -> steps
        self._enabled = bool(OPENROUTER_API_KEY)
        self.guardian_mode = guardian_mode
        self.monitor_mode = monitor_mode
        self._tool_executor = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_callback_id = None

        if not self._enabled:
            logger.warning("[VideoAgent] No OPENROUTER_API_KEY - video agent disabled")

        if guardian_mode:
            logger.info("[VideoAgent] Guardian Mode ENABLED - auto-corrections active")
        if monitor_mode:
            logger.info("[VideoAgent] Monitor Mode ENABLED - realtime monitoring active")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def analyze_frame(
        self,
        frame_base64: str,
        context: Dict[str, Any],
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        Send frame + context to Nemotron for analysis.

        Args:
            frame_base64: JPEG screenshot as base64 string
            context: {tool, params, result, task, step_index}
            conversation_id: Session ID for grouping steps

        Returns:
            Structured analysis: {screen_state, action_verified, elements_visible, anomalies, confidence}
        """
        if not self._enabled:
            return {"error": "Video agent disabled (no API key)", "action_verified": None}

        prompt = self._build_prompt(context)

        payload = {
            "model": _get_vision_model(),
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{frame_base64}"
                    }}
                ]
            }],
            "response_format": {"type": "json_object"},
            "max_tokens": 500,
            "temperature": 0.1
        }

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://moire-desktop-automation.local",
            "X-Title": "Moire Video Agent"
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                analysis = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"[VideoAgent] Non-JSON response: {content[:200]}")
            analysis = {
                "screen_state": content[:200] if content else "unknown",
                "action_verified": None,
                "confidence": 0.0
            }
        except Exception as e:
            logger.error(f"[VideoAgent] Analysis failed: {e}")
            analysis = {"error": str(e), "action_verified": None, "confidence": 0.0}

        # Store in session
        step_record = {
            "timestamp": datetime.now().isoformat(),
            "tool": context.get("tool"),
            "params": context.get("params"),
            "result_success": context.get("result", {}).get("success") if isinstance(context.get("result"), dict) else None,
            "visual_analysis": analysis,
            "step_index": context.get("step_index")
        }

        if conversation_id not in self._session_data:
            self._session_data[conversation_id] = []
        self._session_data[conversation_id].append(step_record)

        logger.info(
            f"[VideoAgent] Step {context.get('step_index')}: "
            f"{context.get('tool')} -> verified={analysis.get('action_verified')} "
            f"conf={analysis.get('confidence', 0):.2f}"
        )

        return analysis

    # ========== Guardian Mode Methods ==========

    def set_tool_executor(self, executor):
        """Wire Video Agent to tool executor (ActionRouter or MCP handlers)."""
        self._tool_executor = executor
        logger.info("[VideoAgent] Tool executor configured")

    async def analyze_and_guard(
        self,
        frame_base64: str,
        context: Dict[str, Any],
        conversation_id: str,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """Analyze frame AND optionally execute corrective actions.

        Args:
            frame_base64: Screenshot as base64
            context: {tool, params, result, task, step_index, ocr_hint, viewport}
            conversation_id: Session ID
            max_retries: Maximum correction attempts (default: 2)

        Returns:
            {
                "analysis": {...},
                "corrections": [...],
                "final_status": "verified" | "corrected" | "failed"
            }
        """
        # 1. Initial Analysis
        analysis = await self.analyze_frame(frame_base64, context, conversation_id)

        result = {
            "analysis": analysis,
            "corrections": [],
            "final_status": "unknown"
        }

        # 2. Guardian Mode disabled? Return immediately
        if not self.guardian_mode or not self._tool_executor:
            result["final_status"] = "verified" if analysis.get("action_verified") else "unverified"
            return result

        # 3. Check if correction needed
        needs_correction = self._needs_correction(analysis, context)

        if not needs_correction:
            result["final_status"] = "verified"
            logger.info("[Guardian] Action verified - no correction needed")
            return result

        # 4. Execute Corrections (max retries)
        for attempt in range(max_retries):
            correction_action = self._plan_correction(analysis, context)

            if not correction_action:
                logger.warning("[Guardian] No correction strategy available")
                break  # No correction possible

            logger.info(f"[Guardian] Attempt {attempt + 1}/{max_retries}: {correction_action['tool']}({correction_action['args']})")
            correction_result = await self._execute_correction(correction_action)
            result["corrections"].append(correction_result)

            # Wait for UI update
            await asyncio.sleep(0.5)

            # Re-capture frame
            new_frame = await capture_current_frame(quality=50, viewport=context.get("viewport"))
            if not new_frame:
                logger.warning("[Guardian] Failed to capture frame after correction")
                break

            # Re-analyze
            analysis = await self.analyze_frame(new_frame, context, conversation_id)
            result["analysis"] = analysis

            # Success?
            if analysis.get("action_verified") and analysis.get("confidence", 0) > 0.7:
                result["final_status"] = "corrected"
                logger.info(f"[Guardian] Correction successful after {attempt + 1} attempt(s)")
                return result

        result["final_status"] = "failed"
        logger.error(f"[Guardian] Correction failed after {max_retries} attempts")
        return result

    def _needs_correction(self, analysis: Dict, context: Dict) -> bool:
        """Decide if correction is needed based on analysis."""
        # Not verified OR low confidence
        if not analysis.get("action_verified", False):
            return True

        if analysis.get("confidence", 0) < 0.5:
            return True

        # Cursor not near target (for mouse actions)
        tool = context.get("tool", "")
        if tool in ["mouse_move", "mouse_click"]:
            if not analysis.get("cursor_near_target", False):
                return True

        # Anomalies detected
        anomalies = analysis.get("anomalies")
        if anomalies and anomalies != "none" and anomalies:
            return True

        return False

    def _plan_correction(self, analysis: Dict, context: Dict) -> Optional[Dict]:
        """Plan corrective action based on analysis.

        Returns:
            {"tool": "mouse_move", "args": {...}} or None
        """
        tool = context.get("tool", "")
        params = context.get("params", {})
        screen_state = analysis.get("screen_state", "").lower()

        # Case 1: Mouse position correction (use OCR hint)
        if tool in ["mouse_move", "mouse_click"]:
            ocr_hint = context.get("ocr_hint")
            if ocr_hint and not analysis.get("cursor_near_target"):
                logger.info("[Guardian] Using OCR hint for position correction")
                return {
                    "tool": "mouse_move",
                    "args": {"x": ocr_hint.get("x"), "y": ocr_hint.get("y")}
                }

        # Case 2: Element not visible → Scroll
        if "not visible" in screen_state or "off screen" in screen_state:
            logger.info("[Guardian] Element not visible - scrolling down")
            return {
                "tool": "action_scroll",
                "args": {"direction": "down", "amount": 3}
            }

        # Case 3: Dialog/Popup blocking
        if "dialog" in screen_state or "popup" in screen_state:
            logger.info("[Guardian] Dialog detected - closing with ESC")
            return {
                "tool": "action_press",
                "args": {"key": "escape"}
            }

        # No correction strategy available
        return None

    async def _execute_correction(self, correction: Dict) -> Dict:
        """Execute corrective tool call via MCP handlers (bypasses ActionRouter)."""
        try:
            tool = correction["tool"]
            args = correction["args"]

            # Import MCP handlers directly for local execution
            try:
                from moire_agents.mcp_handlers import action_tools
            except ImportError:
                logger.error("[Guardian] MCP handlers not available - cannot execute corrections")
                return {"success": False, "error": "MCP handlers not available"}

            # Map tool names to handlers
            if tool == "mouse_move":
                result = await action_tools.handle_mouse_move(args.get("x"), args.get("y"))
            elif tool == "mouse_click":
                result = await action_tools.handle_mouse_click(
                    args.get("x"), args.get("y"), args.get("button", "left")
                )
            elif tool == "action_scroll":
                result = await action_tools.handle_scroll(
                    args.get("direction"), args.get("amount", 3)
                )
            elif tool == "action_press":
                result = await action_tools.handle_press_key(args.get("key"))
            else:
                return {"success": False, "error": f"Unsupported tool: {tool}"}

            return {
                "tool": tool,
                "args": args,
                "result": result
            }
        except Exception as e:
            logger.error(f"[Guardian] Correction failed: {e}")
            return {
                "tool": correction["tool"],
                "args": correction["args"],
                "error": str(e)
            }

    # ========== Monitor Mode Methods ==========

    async def start_monitor(self, conversation_id: str):
        """Start background monitoring task."""
        if not self.monitor_mode:
            logger.warning("[VideoAgent] Monitor mode disabled")
            return

        if self._monitor_task and not self._monitor_task.done():
            logger.warning("[VideoAgent] Monitor already running")
            return

        logger.info("[VideoAgent] Starting realtime monitor...")

        # Register listener on StreamFrameCache
        try:
            from moire_agents.stream_frame_cache import StreamFrameCache

            self._monitor_callback_id = f"video_agent_{conversation_id}"
            StreamFrameCache.add_listener(
                self._monitor_callback_id,
                self._on_frame_update
            )

            # Start background task
            self._monitor_task = asyncio.create_task(
                self._monitor_loop(conversation_id)
            )

            logger.info("[VideoAgent] Monitor started successfully")
        except ImportError:
            logger.error("[VideoAgent] StreamFrameCache not available - cannot start monitor")

    async def stop_monitor(self):
        """Stop background monitoring task."""
        logger.info("[VideoAgent] Stopping realtime monitor...")

        # Unregister listener
        if self._monitor_callback_id:
            try:
                from moire_agents.stream_frame_cache import StreamFrameCache
                StreamFrameCache.remove_listener(self._monitor_callback_id)
                self._monitor_callback_id = None
                logger.info("[VideoAgent] Listener unregistered")
            except ImportError:
                pass

        # Cancel task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            logger.info("[VideoAgent] Monitor task cancelled")

    def _on_frame_update(self, monitor_id: int, frame: 'FrameData'):
        """Callback when new frame arrives (called by StreamFrameCache).

        Don't block - actual analysis happens in _monitor_loop.
        """
        pass  # Frame analysis handled in background loop

    async def _monitor_loop(self, conversation_id: str):
        """Background monitoring loop with intelligent sampling."""
        last_analysis_time = 0
        min_interval = 2.0  # Minimum 2 seconds between analyses (avoid rate limits)
        last_frame_hash = None
        error_count = 0
        max_errors = 3

        logger.info("[Monitor] Background loop started")

        try:
            while True:
                await asyncio.sleep(0.5)  # Check every 500ms

                # Rate limiting
                if time.time() - last_analysis_time < min_interval:
                    continue

                # Get fresh frame
                try:
                    from moire_agents.stream_frame_cache import StreamFrameCache
                    frame = StreamFrameCache.get_fresh_frame(monitor_id=0, max_age_ms=1000)
                except ImportError:
                    logger.error("[Monitor] StreamFrameCache not available")
                    break

                if not frame:
                    continue

                # Change detection (simple hash)
                frame_hash = hash(frame.data[:1000])  # Hash first 1000 chars
                if frame_hash == last_frame_hash:
                    continue  # No change

                last_frame_hash = frame_hash

                # Analyze
                logger.info("[Monitor] Screen changed - analyzing...")
                context = {
                    "tool": "monitor",
                    "params": {},
                    "task": "monitor screen for changes"
                }

                try:
                    analysis = await self.analyze_frame(frame.data, context, conversation_id)
                    last_analysis_time = time.time()
                    error_count = 0  # Reset on success

                    # Classify event
                    event_type = self._classify_screen_event(analysis)

                    if event_type == "dialog":
                        # Auto-handle dialog
                        logger.info("[Monitor] Dialog detected - auto-closing")
                        if self._tool_executor:
                            correction = {"tool": "action_press", "args": {"key": "escape"}}
                            await self._execute_correction(correction)

                    elif event_type == "unexpected":
                        # Alert user
                        logger.warning(f"[Monitor] Unexpected change: {analysis.get('screen_state')}")
                        # TODO: Send SSE event to frontend

                except Exception as e:
                    error_count += 1
                    logger.error(f"[Monitor] Analysis failed ({error_count}/{max_errors}): {e}")

                    if error_count >= max_errors:
                        logger.error("[Monitor] Too many errors - stopping monitor")
                        break

        except asyncio.CancelledError:
            logger.info("[Monitor] Task cancelled")
        except Exception as e:
            logger.error(f"[Monitor] Fatal error: {e}")

        logger.info("[Monitor] Background loop stopped")

    def _classify_screen_event(self, analysis: Dict) -> str:
        """Classify screen change event.

        Returns:
            "normal", "dialog", "unexpected"
        """
        screen_state = analysis.get("screen_state", "").lower()

        if "dialog" in screen_state or "popup" in screen_state:
            return "dialog"

        if "error" in screen_state or "warning" in screen_state:
            return "unexpected"

        return "normal"

    # ========== Original Methods ==========

    def save_training_data(self, conversation_id: str, task_summary: str) -> str:
        """
        Save session data as training JSON file.

        Returns filepath if saved, empty string if nothing to save.
        """
        steps = self._session_data.pop(conversation_id, [])
        if not steps:
            return ""

        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{conversation_id[:8]}.json"
        filepath = TRAINING_DIR / filename

        training_record = {
            "conversation_id": conversation_id,
            "task": task_summary,
            "timestamp": datetime.now().isoformat(),
            "total_steps": len(steps),
            "steps": steps,
            "summary": self._generate_summary(steps)
        }

        try:
            filepath.write_text(
                json.dumps(training_record, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"[VideoAgent] Training data saved: {filepath}")
        except OSError as e:
            logger.error(f"[VideoAgent] Failed to save training data: {e}")
            return ""

        return str(filepath)

    def get_session_stats(self, conversation_id: str) -> Dict[str, Any]:
        """Get current session statistics without saving."""
        steps = self._session_data.get(conversation_id, [])
        if not steps:
            return {"steps_analyzed": 0}
        return {
            "steps_analyzed": len(steps),
            **self._generate_summary(steps)
        }

    def _build_prompt(self, context: Dict) -> str:
        tool = context.get("tool", "unknown")
        params = context.get("params", {})
        result = context.get("result", {})
        viewport = context.get("viewport")

        # Compact params/result to save tokens
        params_str = json.dumps(params, ensure_ascii=False)
        if len(params_str) > 300:
            params_str = params_str[:300] + "..."

        result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        if len(result_str) > 300:
            result_str = result_str[:300] + "..."

        base_prompt = f"""Analyze this desktop screenshot after a UI automation step.

Action executed: {tool}
Parameters: {params_str}
Reported result: {result_str}"""

        # OCR position hint from async screen_find
        ocr_hint = context.get("ocr_hint")
        if ocr_hint:
            hx, hy = ocr_hint.get("x", "?"), ocr_hint.get("y", "?")
            base_prompt += f"""

OCR HINT: Text matching the task was detected at screen position ({hx}, {hy}).
Use this as a reference point to validate element positions."""

        # Enhanced validation for mouse_move with viewport
        if tool == "mouse_move" and viewport:
            base_prompt += f"""

This is a ZOOMED viewport ({viewport['width']}x{viewport['height']}px) centered around the mouse target position.
The mouse was moved to ({params.get('x')},{params.get('y')}).
VALIDATE: Is the mouse cursor visible near the center? What UI element is under/near the cursor?
Is this likely the correct position for the user's task: "{context.get('task', 'unknown')}"?"""
            if ocr_hint:
                base_prompt += f"""
OCR suggests the target text is at ({hx}, {hy}). Is the cursor close to this position?"""

        base_prompt += """

Respond in JSON with:
{
  "screen_state": "brief description of what's visible",
  "action_verified": true/false,
  "elements_visible": ["key UI elements visible"],
  "cursor_near_target": true/false,
  "anomalies": "any unexpected state or 'none'",
  "confidence": 0.0-1.0
}"""

        return base_prompt

    def _generate_summary(self, steps: List[Dict]) -> Dict:
        verified = sum(
            1 for s in steps
            if s.get("visual_analysis", {}).get("action_verified") is True
        )
        failed = sum(
            1 for s in steps
            if s.get("visual_analysis", {}).get("action_verified") is False
        )
        return {
            "total_steps": len(steps),
            "verified_steps": verified,
            "failed_steps": failed,
            "verification_rate": round(verified / max(len(steps), 1), 2),
            "tools_used": list(set(s.get("tool", "") for s in steps if s.get("tool")))
        }

    def cleanup_session(self, conversation_id: str) -> None:
        """Remove session data without saving (e.g., on cancel)."""
        self._session_data.pop(conversation_id, None)


# Global instance (singleton pattern)
# Guardian/Monitor mode configured via environment variables
import os as _os_config
_GUARDIAN_MODE = _os_config.getenv("VIDEO_AGENT_GUARDIAN_MODE", "false").lower() == "true"
_MONITOR_MODE = _os_config.getenv("VIDEO_AGENT_MONITOR_MODE", "false").lower() == "true"

video_agent = VideoAgent(guardian_mode=_GUARDIAN_MODE, monitor_mode=_MONITOR_MODE)

# Alias for compatibility
video_agent_instance = video_agent
