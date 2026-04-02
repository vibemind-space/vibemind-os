"""
ActionRouter - Abstracts local vs. remote tool execution.

In local mode: returns sentinel so execute_tool() handles everything as before.
In remote mode: sends command to desktop client via WebSocket and awaits ACK.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional
from uuid import uuid4

from app.services.tool_safety import ToolRisk, get_tool_risk

logger = logging.getLogger(__name__)


class ActionRouter:
    """Routes tool execution to local pyautogui or remote desktop client."""

    def __init__(self):
        self._mode: str = "local"
        self._pending_acks: Dict[str, asyncio.Future] = {}
        self._ws_manager = None
        self._target_client_id: Optional[str] = None
        self._timeout: int = 30
        self._frame_max_age_ms: int = 2000

    def configure(self, settings) -> None:
        """Configure from Settings object."""
        self._mode = getattr(settings, "execution_mode", "local")
        self._target_client_id = getattr(settings, "remote_desktop_client_id", "") or None
        self._timeout = getattr(settings, "remote_action_timeout", 30)
        self._frame_max_age_ms = getattr(settings, "remote_frame_max_age_ms", 2000)
        logger.info(f"[ActionRouter] Configured: mode={self._mode}, timeout={self._timeout}s")

    def set_ws_manager(self, manager) -> None:
        """Set the WebSocket ConnectionManager reference."""
        self._ws_manager = manager

    @property
    def is_remote(self) -> bool:
        return self._mode == "remote"

    @property
    def frame_max_age_ms(self) -> int:
        return self._frame_max_age_ms

    def get_risk(self, tool_name: str) -> ToolRisk:
        return get_tool_risk(tool_name)

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Route tool to local or remote based on mode and risk level."""
        risk = self.get_risk(tool_name)

        if self._mode == "local":
            return {"_route": "local"}

        if risk == ToolRisk.SAFE:
            return {"_route": "local"}

        if risk == ToolRisk.APPROVAL:
            return {
                "_approval_required": True,
                "tool": tool_name,
                "arguments": arguments,
                "message": f"Tool '{tool_name}' requires user approval in remote mode",
            }

        # DELEGATED: send to desktop client
        return await self._execute_remote(tool_name, arguments)

    async def _execute_remote(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Send command to desktop client and wait for ACK."""
        if not self._ws_manager:
            return {"success": False, "error": "WebSocket manager not configured"}

        target = self._resolve_target_client()
        if not target:
            return {"success": False, "error": "No desktop client connected for remote execution"}

        command_id = f"cmd_{uuid4().hex[:12]}"
        command_msg = {
            "type": "execute_action",
            "commandId": command_id,
            "tool": tool_name,
            "arguments": arguments,
            "timestamp": time.time(),
        }

        loop = asyncio.get_running_loop()
        ack_future = loop.create_future()
        self._pending_acks[command_id] = ack_future

        try:
            ws = self._ws_manager.active_connections.get(target)
            if not ws:
                return {"success": False, "error": f"Desktop client '{target}' not connected"}

            await ws.send_text(json.dumps(command_msg))
            logger.info(f"[ActionRouter] Sent {tool_name} to {target} (cmd={command_id})")

            result = await asyncio.wait_for(ack_future, timeout=self._timeout)
            return result

        except asyncio.TimeoutError:
            logger.error(f"[ActionRouter] Timeout for ACK from {target} (cmd={command_id})")
            return {"success": False, "error": f"Desktop client did not respond within {self._timeout}s"}
        except Exception as e:
            logger.error(f"[ActionRouter] Remote execution failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self._pending_acks.pop(command_id, None)

    def handle_ack(self, command_id: str, result: Dict[str, Any]) -> bool:
        """Called when desktop client sends an ACK. Resolves the waiting future."""
        future = self._pending_acks.get(command_id)
        if future and not future.done():
            future.set_result(result)
            logger.info(f"[ActionRouter] ACK received: {command_id}")
            return True
        logger.warning(f"[ActionRouter] Orphan ACK: {command_id}")
        return False

    def _resolve_target_client(self) -> Optional[str]:
        """Find the desktop client to send commands to."""
        if not self._ws_manager:
            return None

        # Try configured client first
        if self._target_client_id and self._target_client_id in self._ws_manager.active_connections:
            return self._target_client_id

        # Auto-detect: find first connected desktop client
        desktop_types = {
            "dual_screen_desktop", "desktop_capture",
            "multi_monitor_desktop_capture", "desktop",
        }
        for client_id, info in self._ws_manager.client_info.items():
            client_type = info.get("clientType", "")
            if client_type in desktop_types:
                return client_id

        return None


# Global singleton
action_router = ActionRouter()
