"""
OpenClaw Gateway Bridge — communicates with OpenClaw for sandboxed execution,
user channel messaging (no timeout), and Claude CLI delegation via ACP.

Requires OpenClaw Gateway running at OPENCLAW_URL (default: ws://127.0.0.1:18789).
Falls back gracefully when OpenClaw is not available.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default: coding-engine-openclaw container already running on 18789
OPENCLAW_URL = os.getenv("OPENCLAW_URL", "ws://127.0.0.1:18789")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "vibemind-local")


class OpenClawBridge:
    """Bridge to OpenClaw Gateway for sandboxed execution and user communication."""

    def __init__(self, gateway_url: str = None):
        self._url = gateway_url or OPENCLAW_URL
        self._token = OPENCLAW_TOKEN
        self._ws = None
        self._connected = False
        self._request_id = 0
        self._pending: Dict[str, asyncio.Future] = {}
        self._agent_response_future: Optional[asyncio.Future] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Connect to OpenClaw Gateway via WebSocket Protocol 3."""
        try:
            import websockets
            self._ws = await asyncio.wait_for(
                websockets.connect(self._url), timeout=5.0
            )
            # 1. Wait for connect.challenge
            challenge_raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            challenge = json.loads(challenge_raw)
            logger.debug(f"OpenClaw challenge: {challenge.get('event', '?')}")

            # 2. Send Protocol 3 connect request
            self._request_id += 1
            connect_msg = {
                "type": "req",
                "id": str(self._request_id),
                "method": "connect",
                "params": {
                    "minProtocol": 3,
                    "maxProtocol": 3,
                    "client": {
                        "id": "cli",
                        "version": "1.0.0",
                        "platform": "windows",
                        "mode": "cli",
                    },
                    "role": "operator",
                    "scopes": ["operator.read", "operator.write", "operator.admin"],
                    "auth": {"token": self._token} if self._token else {},
                },
            }
            await self._ws.send(json.dumps(connect_msg))

            # 3. Wait for hello-ok response
            resp = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=5.0))
            self._connected = resp.get("ok", False)
            if self._connected:
                proto = resp.get("payload", {}).get("protocol", "?")
                conn_id = resp.get("payload", {}).get("server", {}).get("connId", "?")[:12]
                logger.info(f"OpenClaw connected (proto={proto}, conn={conn_id})")
                asyncio.create_task(self._listen())
            else:
                err = resp.get("error", {})
                logger.warning(f"OpenClaw connect rejected: {err}")
            return self._connected
        except Exception as e:
            logger.warning(f"OpenClaw not available: {e}")
            self._connected = False
            return False

    async def _listen(self):
        """Background listener for events and responses."""
        try:
            async for msg in self._ws:
                data = json.loads(msg)
                if data.get("type") == "res":
                    req_id = data.get("id")
                    if str(req_id) in self._pending:
                        self._pending[str(req_id)].set_result(data)
                    elif req_id in self._pending:
                        self._pending[req_id].set_result(data)
                elif data.get("type") == "event":
                    event_name = data.get("event", "")
                    payload = data.get("payload", {})
                    # Collect agent text responses
                    if event_name in ("chat", "agent"):
                        text = payload.get("text", payload.get("message", ""))
                        if text and self._agent_response_future and not self._agent_response_future.done():
                            self._agent_response_future.set_result(text)
                    logger.debug(f"OpenClaw event: {event_name}")
        except Exception as e:
            logger.warning(f"OpenClaw listener ended: {e}")
            self._connected = False

    async def _request(self, method: str, params: dict = None,
                       timeout: float = None) -> dict:
        """Send request to OpenClaw Gateway and wait for response."""
        if not self._connected:
            raise ConnectionError("OpenClaw not connected")

        self._request_id += 1
        req_id = str(self._request_id)
        msg = {"type": "req", "id": req_id, "method": method, "params": params or {}}

        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        await self._ws.send(json.dumps(msg))

        try:
            if timeout:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future  # No timeout — waits indefinitely
            return result.get("payload", {})
        finally:
            self._pending.pop(req_id, None)

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # User Communication (NO TIMEOUT)
    # ------------------------------------------------------------------

    async def ask_user(self, question: str, channel: str = None,
                       options: List[str] = None) -> str:
        """Ask user a question via channel. NO TIMEOUT — waits until user responds."""
        if not self._connected:
            logger.warning("OpenClaw not connected, skipping user question")
            return ""

        import uuid
        message = question
        if options:
            message += "\n" + "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))

        result = await self._request("send", {
            "message": message,
            "idempotencyKey": f"ask-{uuid.uuid4().hex[:12]}",
        }, timeout=None)  # No timeout — wait for user
        return result.get("reply", result.get("text", ""))

    async def send_status(self, message: str, channel: str = None):
        """Send status update to user (non-blocking, best-effort)."""
        if not self._connected:
            logger.info(f"[Pipeline Status] {message}")
            return
        params = {"message": message}
        if channel:
            params["channel"] = channel
        try:
            await self._request("send", params, timeout=5.0)
        except Exception:
            logger.debug(f"Status send failed: {message[:50]}")

    # ------------------------------------------------------------------
    # Docker Sandbox Execution
    # ------------------------------------------------------------------

    async def run_in_sandbox(self, args: List[str], workdir: str = None,
                             timeout: float = None) -> Dict[str, Any]:
        """Execute command in OpenClaw Docker sandbox."""
        if not self._connected:
            return await self._local_exec(args, workdir, timeout)

        result = await self._request("agent", {
            "task": " ".join(args),
            "runtime": "sandbox",
        }, timeout=timeout)

        return {
            "success": result.get("ok", False),
            "output": result.get("output", ""),
            "exit_code": result.get("exitCode", -1),
        }

    async def docker_build(self, context_path: str,
                           timeout: float = None) -> Dict[str, Any]:
        """Run docker compose build in sandbox."""
        return await self.run_in_sandbox(
            ["docker", "compose", "-f", f"{context_path}/docker-compose.yml", "build"],
            workdir=context_path, timeout=timeout,
        )

    async def docker_run(self, context_path: str,
                         timeout: float = None) -> Dict[str, Any]:
        """Run docker compose up in sandbox."""
        return await self.run_in_sandbox(
            ["docker", "compose", "-f", f"{context_path}/docker-compose.yml",
             "up", "--abort-on-container-exit"],
            workdir=context_path, timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Claude CLI Delegation via ACP
    # ------------------------------------------------------------------

    async def delegate_to_claude_cli(self, task: str,
                                     files: List[str] = None,
                                     timeout: float = 300.0) -> Dict[str, Any]:
        """Delegate task to Claude CLI via OpenClaw embedded agent or direct CLI.

        Priority:
        1. OpenClaw CLI --local (embedded agent, no gateway pairing needed)
        2. Direct Claude CLI (claude.cmd)
        """
        import uuid
        idem_key = f"vibemind-{uuid.uuid4().hex[:12]}"

        # Strategy 1: OpenClaw embedded agent (--local, no gateway needed)
        openclaw_cli = shutil.which("openclaw.cmd") or shutil.which("openclaw")
        if openclaw_cli:
            try:
                env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
                result = subprocess.run(
                    [openclaw_cli, "agent", "--local", "--agent", "main",
                     "--message", task, "--json", "--timeout", str(int(timeout))],
                    capture_output=True, text=True, timeout=timeout + 10,
                    shell=(os.name == "nt"), env=env,
                )
                if result.returncode == 0:
                    try:
                        data = json.loads(result.stdout)
                        text = data.get("payloads", [{}])[0].get("text", "")
                        return {"success": True, "output": text, "run_id": idem_key}
                    except (json.JSONDecodeError, IndexError, KeyError):
                        return {"success": True, "output": result.stdout.strip(), "run_id": idem_key}
                else:
                    logger.warning(f"OpenClaw agent failed: {result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                logger.warning("OpenClaw agent timeout")
            except Exception as e:
                logger.warning(f"OpenClaw agent error: {e}")

        # Strategy 2: Direct Claude CLI fallback
        return await self._local_claude_cli(task, timeout)

    # ------------------------------------------------------------------
    # Local Fallbacks
    # ------------------------------------------------------------------

    async def _local_exec(self, args: List[str], workdir: str = None,
                          timeout: float = 300.0) -> Dict[str, Any]:
        """Fallback: run command locally via subprocess (no shell)."""
        try:
            result = subprocess.run(
                args, capture_output=True, text=True,
                cwd=workdir, timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout + result.stderr,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Timeout", "exit_code": -1}
        except Exception as e:
            return {"success": False, "output": str(e), "exit_code": -1}

    async def _local_claude_cli(self, task: str,
                                timeout: float = 300.0) -> Dict[str, Any]:
        """Fallback: run Claude CLI directly (no shell injection)."""
        # Windows: prefer claude.cmd over bare claude (node wrapper)
        claude_path = shutil.which("claude.cmd") or shutil.which("claude")
        if not claude_path:
            return {"success": False, "output": "Claude CLI not found"}

        try:
            # Remove CLAUDECODE env var to allow nested sessions
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            result = subprocess.run(
                [claude_path, "--print", "--output-format", "text", "-p", task],
                capture_output=True, text=True, timeout=timeout,
                shell=(os.name == "nt"),  # Windows needs shell=True for .cmd
                env=env,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "session_id": None,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Claude CLI timeout"}
        except Exception as e:
            return {"success": False, "output": str(e)}

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def disconnect(self):
        """Close WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._connected = False
            logger.info("OpenClaw disconnected")
