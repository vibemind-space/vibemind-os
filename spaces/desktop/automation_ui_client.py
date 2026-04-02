"""
AutomationUIClient - HTTP bridge to Automation_ui FastAPI backend.

Provides synchronous methods that map VibeMind desktop tool calls
to Automation_ui REST API endpoints at localhost:8009.

Uses httpx for sync HTTP with timeout/retry/health-check support.
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# Stable conversation ID for VibeMind desktop session
VIBEMIND_CONVERSATION_ID = "vibemind-desktop-session"


class AutomationUIClient:
    """Synchronous HTTP client for Automation_ui backend."""

    def __init__(
        self,
        base_url: str = None,
        timeout: float = None,
        intent_timeout: float = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("AUTOMATION_UI_URL", "http://localhost:8009")
        ).rstrip("/")
        self.timeout = timeout or float(os.getenv("AUTOMATION_UI_TIMEOUT", "30"))
        self.intent_timeout = intent_timeout or float(
            os.getenv("AUTOMATION_UI_INTENT_TIMEOUT", "120")
        )
        self._client: Optional[httpx.Client] = None
        self._healthy: Optional[bool] = None
        self._last_health_check: float = 0
        self._health_cache_ttl: float = 30.0

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialized httpx sync client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def is_available(self) -> bool:
        """Check if Automation_ui backend is reachable (cached 30s)."""
        now = time.time()
        if now - self._last_health_check < self._health_cache_ttl:
            return self._healthy or False

        try:
            resp = self.client.get("/api/health/health", timeout=3.0)
            self._healthy = resp.status_code == 200
        except Exception:
            self._healthy = False
        self._last_health_check = now

        if self._healthy:
            logger.debug("Automation_ui backend available at %s", self.base_url)
        else:
            logger.debug("Automation_ui backend NOT available at %s", self.base_url)
        return self._healthy

    # ------------------------------------------------------------------
    # Direct automation endpoints (simple actions, no LLM needed)
    # ------------------------------------------------------------------

    def click(self, x: float, y: float, button: str = "left", click_type: str = "single") -> Dict[str, Any]:
        """Direct click at coordinates."""
        resp = self.client.post("/api/automation/click", json={
            "x": x, "y": y, "button": button, "click_type": click_type, "delay": 0.1,
        })
        resp.raise_for_status()
        return resp.json()

    def type_text(self, text: str, interval: float = 0.02) -> Dict[str, Any]:
        """Type text at current cursor position."""
        resp = self.client.post("/api/automation/type", json={
            "text": text, "interval": interval,
        })
        resp.raise_for_status()
        return resp.json()

    def press_key(self, key: str) -> Dict[str, Any]:
        """Press a keyboard key. Handles 'ctrl+s' hotkey format."""
        if "+" in key:
            keys = [k.strip() for k in key.split("+")]
            resp = self.client.post("/api/automation/hotkey", json={"keys": keys})
        else:
            resp = self.client.post("/api/automation/key", json={
                "key": key, "modifiers": [],
            })
        resp.raise_for_status()
        return resp.json()

    def scroll(self, direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        """Scroll the screen."""
        scroll_amount = amount if direction == "up" else -amount
        resp = self.client.post("/api/automation/scroll", json={
            "amount": scroll_amount, "direction": "vertical",
        })
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # LLM Intent endpoint (agentic — vision, OCR, multi-step)
    # ------------------------------------------------------------------

    def llm_intent(self, text: str, conversation_id: str = None) -> Dict[str, Any]:
        """
        Send natural language command to the agentic LLM endpoint.

        Parses the SSE stream and returns the final result dict containing:
        - summary (str): LLM's text answer
        - success (bool): whether all steps succeeded
        - total_steps (int): number of tool calls executed
        - steps (list): individual step results collected during stream
        """
        logger.debug("llm_intent called: text=%s", text[:80])
        cid = conversation_id or VIBEMIND_CONVERSATION_ID
        payload = {"text": text, "conversation_id": cid}

        summary_text = ""
        done_event = None
        steps = []

        try:
            with self.client.stream(
                "POST",
                "/api/llm/intent",
                json=payload,
                timeout=httpx.Timeout(self.intent_timeout, connect=5.0),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    event_type = data.get("type")
                    if event_type == "step":
                        steps.append(data)
                    elif event_type == "summary":
                        summary_text = data.get("content", "")
                    elif event_type == "done":
                        done_event = data
                        break  # terminal event

        except httpx.TimeoutException:
            return {
                "success": False,
                "summary": "",
                "error": f"Timeout ({self.intent_timeout}s) bei agentic execution",
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "summary": "",
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }

        if done_event:
            done_event["summary"] = summary_text
            done_event["steps"] = steps
            return done_event

        # No done event received — partial result
        return {
            "success": False,
            "summary": summary_text,
            "steps": steps,
            "error": "Stream ended without 'done' event",
        }

    # ------------------------------------------------------------------
    # Clawdbot messaging endpoints
    # ------------------------------------------------------------------

    def clawdbot_send(self, recipient: str, message: str, platform: str = "whatsapp") -> Dict[str, Any]:
        """Send a message via Clawdbot messaging bridge."""
        try:
            resp = self.client.post("/api/clawdbot/command", json={
                "command": f"send to {recipient}: {message}",
                "user_id": "vibemind",
                "platform": platform,
            })
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("clawdbot_send error: %s", e)
            return {"success": False, "error": str(e)}

    def clawdbot_status(self) -> Dict[str, Any]:
        """Get Clawdbot messaging bridge status."""
        try:
            resp = self.client.get("/api/clawdbot/status")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("clawdbot_status error: %s", e)
            return {"success": False, "error": str(e)}

    def close(self):
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_client: Optional[AutomationUIClient] = None


def get_automation_client() -> AutomationUIClient:
    """Get or create the singleton AutomationUIClient."""
    global _client
    if _client is None:
        _client = AutomationUIClient()
    return _client


__all__ = ["AutomationUIClient", "get_automation_client"]
