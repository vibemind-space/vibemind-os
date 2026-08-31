"""Broadcast space-changes to the Electron UI.

Reuses the existing `navigate_to_space` / `space_changed` message types
documented in voice/CLAUDE.md. The Electron renderer (glass_bubbles.js)
must listen for these — that wiring is Gap G2 from the audit and lives
outside this MCP.

Three delivery channels (best-effort, all optional):

  1) CDP (Chrome DevTools Protocol) when NAVIGATOR_USE_CDP=1 — the most
     reliable path: connects directly to Electron's :9223 and calls
     window.multiverseApp.navigateToSpace(renderer_id). Works from any
     Python process, no Electron-subprocess requirement. Requires
     `--remote-allow-origins=*` on the Electron launch (set in main.js
     since 2026-06-02).
  2) HTTP POST to electron_backend's bridge port (when NAVIGATOR_BRIDGE_URL set)
  3) Stdout JSON line (picked up by anything reading our stdout — only
     useful when this process is a child of electron_backend.py)

If none is available, the broadcast is a no-op and the call still succeeds —
state is updated regardless, so a later reconnect can re-sync.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, Optional

import urllib.request
import urllib.error

from spaces._navigator.registry import get_renderer_id


_BRIDGE_URL = os.environ.get("NAVIGATOR_BRIDGE_URL", "").strip()
_BRIDGE_TIMEOUT = float(os.environ.get("NAVIGATOR_BRIDGE_TIMEOUT", "1.5"))
_CDP_PORT = int(os.environ.get(
    "NAVIGATOR_CDP_PORT",
    "9223" if os.environ.get("NAVIGATOR_USE_CDP", "").strip() in ("1", "true", "yes") else "0",
))
_CDP_TIMEOUT = float(os.environ.get("NAVIGATOR_CDP_TIMEOUT", "5"))


def _cdp_navigate(space: str) -> Optional[str]:
    """Drive window.multiverseApp.navigateToSpace via CDP. Returns error string or None.

    Resolves the canonical brain-registry id to the renderer-side scene name
    (e.g. coding -> projects, brain -> thebrain) before sending. Returns
    immediately with an error string if the space has no renderer
    representation (minibook, n8n, research, schedule).
    """
    # Explicit None means "registered, but no 3D scene" — return immediately
    # instead of falling back to the brain-id (which the renderer wouldn't
    # know either and would silently no-op).
    from spaces._navigator.registry import SPACES
    if space in SPACES:
        rid = SPACES[space].get("renderer_id")
        if rid is None:
            return f"space '{space}' has no 3D scene (renderer_id=None)"
    else:
        # Unknown to registry — try the literal string anyway (caller might
        # already have a renderer name like 'thebrain').
        rid = space

    # Lazy import — websockets is heavy, only load when CDP is actually used.
    # Both `websockets` (async) and `websocket-client` (sync) are common; try
    # the sync one first because we don't want to start an event loop here.
    try:
        import websocket  # type: ignore  # websocket-client
        return _cdp_sync(rid, websocket)
    except ImportError:
        pass
    try:
        import asyncio
        import websockets  # type: ignore
        return asyncio.run(_cdp_async(rid, websockets))
    except ImportError:
        return "no websocket library available (pip install websocket-client OR websockets)"
    except Exception as e:
        return f"CDP error: {type(e).__name__}: {str(e)[:200]}"


def _cdp_sync(renderer_id: str, websocket_mod) -> Optional[str]:
    try:
        tabs_raw = urllib.request.urlopen(
            f"http://127.0.0.1:{_CDP_PORT}/json", timeout=_CDP_TIMEOUT
        ).read()
    except Exception as e:
        return f"CDP unreachable on :{_CDP_PORT}: {e}"
    tabs = json.loads(tabs_raw)
    target = next(
        (t for t in tabs if "Multiverse" in t.get("title", "") or
         "renderer/index.html" in t.get("url", "")),
        None,
    )
    if not target:
        return "no Multiverse target in CDP"
    ws_url = target["webSocketDebuggerUrl"]

    # Build a Runtime.evaluate that calls navigateToSpace + returns the new state
    expr = (
        "(async () => { try {"
        f" await window.multiverseApp.navigateToSpace({json.dumps(renderer_id)});"
        " return {ok: true, currentSpace: window.currentSpace,"
        " navigating: window.multiverseApp.isNavigating};"
        " } catch(e) { return {ok: false, error: String(e)}; } })()"
    )
    try:
        ws = websocket_mod.create_connection(ws_url, timeout=_CDP_TIMEOUT)
    except Exception as e:
        return f"CDP ws connect failed (origin block? need --remote-allow-origins=*): {e}"
    try:
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
        }))
        resp = json.loads(ws.recv())
        result = resp.get("result", {}).get("result", {}).get("value", {})
        if not result.get("ok"):
            return f"renderer rejected nav: {result.get('error', 'unknown')}"
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return None


async def _cdp_async(renderer_id: str, websockets_mod) -> Optional[str]:
    try:
        tabs_raw = urllib.request.urlopen(
            f"http://127.0.0.1:{_CDP_PORT}/json", timeout=_CDP_TIMEOUT
        ).read()
    except Exception as e:
        return f"CDP unreachable on :{_CDP_PORT}: {e}"
    tabs = json.loads(tabs_raw)
    target = next(
        (t for t in tabs if "Multiverse" in t.get("title", "") or
         "renderer/index.html" in t.get("url", "")),
        None,
    )
    if not target:
        return "no Multiverse target in CDP"
    ws_url = target["webSocketDebuggerUrl"]
    expr = (
        "(async () => { try {"
        f" await window.multiverseApp.navigateToSpace({json.dumps(renderer_id)});"
        " return {ok: true, currentSpace: window.currentSpace,"
        " navigating: window.multiverseApp.isNavigating};"
        " } catch(e) { return {ok: false, error: String(e)}; } })()"
    )
    # websockets 12 uses extra_headers (older versions: additional_headers)
    connect_kwargs: Dict[str, Any] = {}
    try:
        async with websockets_mod.connect(ws_url, **connect_kwargs) as ws:
            await ws.send(json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
            }))
            import asyncio
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=_CDP_TIMEOUT))
            result = resp.get("result", {}).get("result", {}).get("value", {})
            if not result.get("ok"):
                return f"renderer rejected nav: {result.get('error', 'unknown')}"
    except Exception as e:
        return f"CDP ws connect failed (origin block? need --remote-allow-origins=*): {e}"
    return None


def broadcast(message: Dict[str, Any]) -> Dict[str, Any]:
    """Send a navigation message to whatever channels are configured."""
    payload = dict(message)
    payload.setdefault("ts", time.time())
    payload.setdefault("source", "space-navigator")

    delivered_via: list[str] = []
    errors: list[str] = []

    # 1) CDP — most reliable, only when explicitly enabled. Only sends
    #    navigate_to_space messages; other types (space_changed, future)
    #    fall through to HTTP/stdout.
    if _CDP_PORT and payload.get("type") == "navigate_to_space" and payload.get("space"):
        err = _cdp_navigate(payload["space"])
        if err:
            errors.append(f"cdp: {err}")
        else:
            delivered_via.append("cdp")

    # 2) HTTP POST to electron_backend bridge (legacy)
    if _BRIDGE_URL:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                _BRIDGE_URL,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=_BRIDGE_TIMEOUT)
            delivered_via.append("http")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            errors.append(f"http: {e}")

    # 3) Stdout — only useful if this process is a child of electron
    try:
        sys.stdout.write(f"__NAV_BROADCAST__ {json.dumps(payload)}\n")
        sys.stdout.flush()
        delivered_via.append("stdout")
    except Exception as e:
        errors.append(f"stdout: {e}")

    result = {"delivered_via": delivered_via, "payload": payload}
    if errors:
        result["errors"] = errors
    return result


def navigate(space: str, *, reason: Optional[str] = None) -> Dict[str, Any]:
    return broadcast({
        "type": "navigate_to_space",
        "space": space,
        "reason": reason or "",
    })
