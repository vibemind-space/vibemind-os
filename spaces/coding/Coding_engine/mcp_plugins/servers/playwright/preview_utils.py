import asyncio
import base64
import json
import re
import time
from typing import Any, Optional, Tuple

# Keep imports consistent with existing codebase
from autogen_core.tools import ImageResultContent


class PreviewManager:
    """
    Encapsulates preview-related logic for the Playwright MCP agent.
    - Captures screenshots via the MCP screenshot tool
    - Extracts and streams the active URL/source using the tabs tool
    - Maintains robust "browser open" state using hysteresis across signals

    Clear comments are provided for easier debugging and maintenance.
    """

    def __init__(self, mcp, event_server, screenshot_tool: Optional[str], tabs_tool_name: str) -> None:
        # External dependencies injected for testability and modularity
        self.mcp = mcp
        self.event_server = event_server
        self.screenshot_tool = screenshot_tool
        self.tabs_tool_name = tabs_tool_name

        # Internal throttle for screenshotting
        self._last_shot_ts: float = 0.0

    # ---------------------------- Utilities ----------------------------
    def _extract_image_payload(self, obj: Any) -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
        """
        Try to normalize various image payload shapes into (mime, raw_bytes, ui_uri).
        Returns (mime, bytes, data_uri_or_url) where bytes may be None if we only have a URI.
        """
        try:
            # Case 1: ImageResultContent with data_uri
            if isinstance(obj, ImageResultContent):
                try:
                    du = getattr(obj.content, 'data_uri', None)
                    if isinstance(du, str) and du.startswith('data:'):
                        m = re.match(r"^data:([^;]+);base64,(.+)$", du)
                        if m:
                            mime = m.group(1) or 'image/png'
                            b = base64.b64decode(m.group(2))
                            return mime, b, du
                        return None, None, du
                except Exception:
                    pass
            # Case 2: dict-like shapes
            if isinstance(obj, dict):
                du = obj.get('data_uri')
                if isinstance(du, str) and du:
                    try:
                        if du.startswith('data:'):
                            m = re.match(r"^data:([^;]+);base64,(.+)$", du)
                            if m:
                                mime = m.group(1) or 'image/png'
                                b = base64.b64decode(m.group(2))
                                return mime, b, du
                    except Exception:
                        pass
                    return None, None, du
                data_b64 = obj.get('data')
                mime = obj.get('mime') or 'image/png'
                if isinstance(data_b64, str) and data_b64:
                    try:
                        b = base64.b64decode(data_b64)
                        du = f"data:{mime};base64,{data_b64}"
                        return mime, b, du
                    except Exception:
                        pass
                url = obj.get('url')
                if isinstance(url, str) and url:
                    return None, None, url
            # Case 3: string (data URI or JSON)
            if isinstance(obj, str):
                s = obj.strip()
                if s.startswith('data:'):
                    try:
                        m = re.match(r"^data:([^;]+);base64,(.+)$", s)
                        if m:
                            mime = m.group(1) or 'image/png'
                            b = base64.b64decode(m.group(2))
                            return mime, b, s
                    except Exception:
                        pass
                    return None, None, s
                if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
                    try:
                        return self._extract_image_payload(json.loads(s))
                    except Exception:
                        pass
            # Case 4: objects exposing .content attribute
            content = getattr(obj, 'content', None)
            if content is not None and content is not obj:
                return self._extract_image_payload(content)
        except Exception:
            pass
        return None, None, None

    def _has_tabs(self, obj: Any) -> bool:
        """Heuristically detect presence of tabs/contexts in arbitrary structures."""
        try:
            if obj is None:
                return False
            if isinstance(obj, dict):
                pages = obj.get('pages')
                contexts = obj.get('contexts')
                if isinstance(pages, list) and len(pages) > 0:
                    return True
                if isinstance(contexts, list) and len(contexts) > 0:
                    return True
                if 'url' in obj or 'title' in obj:
                    return True
                for v in obj.values():
                    if self._has_tabs(v):
                        return True
            if isinstance(obj, list):
                if len(obj) > 0:
                    if any(isinstance(it, dict) and ('url' in it or 'title' in it) for it in obj):
                        return True
                    return True
        except Exception:
            pass
        return False

    def _extract_urls(self, obj: Any) -> list:
        urls = []
        try:
            if obj is None:
                return urls
            if isinstance(obj, str):
                s = obj.strip()
                if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
                    try:
                        return self._extract_urls(json.loads(s))
                    except Exception:
                        pass
                m = re.search(r"https?://[\w\-._~:/?#\\\[\]@!$&'()*+,;=%]+", s)
                if m:
                    urls.append(m.group(0))
                return urls
            if isinstance(obj, dict):
                for k, v in obj.items():
                    try:
                        if str(k).lower() in ("url", "currenturl", "href") and isinstance(v, str) and v.startswith("http"):
                            urls.append(v)
                        else:
                            urls.extend(self._extract_urls(v))
                    except Exception:
                        continue
                return urls
            if isinstance(obj, (list, tuple)):
                for it in obj:
                    urls.extend(self._extract_urls(it))
                return urls
        except Exception:
            pass
        return urls

    # ---------------------------- Public API ----------------------------
    async def maybe_capture_screenshot(self) -> None:
        """Attempt a screenshot. Broadcast UI updates and persist bytes for /browser endpoints.
        Throttled to avoid excessive capture frequency.
        """
        if not self.screenshot_tool:
            return
        # Debounced info message when browser not open
        try:
            if not getattr(self.event_server, 'browser_open_last_state', None):
                now = time.time()
                last_log = getattr(self.event_server, 'screenshot_skip_last_log_ts', 0.0) or 0.0
                if now - last_log > 15:
                    try:
                        self.event_server.screenshot_skip_last_log_ts = now
                    except Exception:
                        pass
                    try:
                        self._broadcast('status', 'screenshot skipped: browser not open')
                        if getattr(self.event_server, 'browser_open_last_state', None) is not False:
                            self.event_server.browser_open_last_state = False
                            self.event_server.broadcast('log', 'No preview yet')
                    except Exception:
                        pass
        except Exception:
            pass

        # Throttle screenshots
        now = time.time()
        if now - self._last_shot_ts < 2.0:
            return
        self._last_shot_ts = now

        # Hysteresis: consider browser open if image recently seen
        try:
            last_image = getattr(self.event_server, 'last_image_ts', 0.0) or 0.0
            if last_image and now - last_image <= 8.0:
                if getattr(self.event_server, 'browser_open_last_state', None) is False:
                    self.event_server.browser_open_last_state = True
                    self.event_server.broadcast('log', 'Browser open')
        except Exception:
            pass

        # Perform tool call and fan-in different image shapes
        try:
            result = await self.mcp.call_tool(self.screenshot_tool, {})
        except Exception as e:
            self._broadcast('error', f'Screenshot failed: {e}')
            return

        parts = getattr(result, 'result', None) or []
        for part in parts:
            mime, img_bytes, ui_uri = self._extract_image_payload(part)
            if not ui_uri:
                continue
            # Update UI
            try:
                self.event_server.broadcast('browser', {"data_uri": ui_uri, "text": f"{self.screenshot_tool} captured"})
            except Exception:
                pass
            # Persist raw bytes for /browser endpoints
            try:
                if img_bytes:
                    self.event_server.set_channel_image(img_bytes, mime or 'image/png', channel='default')
                    self.event_server.last_image_ts = time.time()
                    # Also update preview.png for UIHandler consumers
                    # Clear comments for easy debug; only set when PNG data is available
                    try:
                        fmt = (mime or 'image/png')
                        if fmt.lower() == 'image/png':
                            b64 = base64.b64encode(img_bytes).decode('ascii')
                            self.event_server.set_preview_png(b64)
                    except Exception:
                        # Never raise from preview update
                        pass
            except Exception:
                pass
            # Mark browser open if previously closed
            try:
                if getattr(self.event_server, 'browser_open_last_state', None) is False:
                    self.event_server.browser_open_last_state = True
                    self.event_server.broadcast('browser_state', {"open": True, "text": "Browser open"})
            except Exception:
                pass
            return

        # If no image content was delivered
        self._broadcast('status', f'{self.screenshot_tool}: no image content in result')

    async def maybe_capture_source(self) -> None:
        """Try to read the active URL via the tabs tool and stream as 'source'.
        Also updates a robust 'browser open' state using recent open signals and images.
        """
        try:
            result = await self.mcp.call_tool(self.tabs_tool_name, {})
        except Exception:
            return

        url_candidate = None
        has_tabs = False

        parts = getattr(result, 'result', None) or []
        for part in parts:
            raw = getattr(part, 'content', None)
            if raw is None:
                raw = str(part)
            parsed = None
            try:
                if isinstance(raw, (dict, list)):
                    parsed = raw
                elif isinstance(raw, str) and raw.strip() and (raw.strip().startswith('{') or raw.strip().startswith('[')):
                    parsed = json.loads(raw)
            except Exception:
                parsed = None

            if parsed is not None:
                try:
                    if self._has_tabs(parsed):
                        has_tabs = True
                except Exception:
                    pass
                if url_candidate is None:
                    try:
                        urls = self._extract_urls(parsed)
                        if urls:
                            url_candidate = urls[0]
                    except Exception:
                        pass
            if url_candidate is None:
                try:
                    text = str(raw)
                    m = re.search(r"https?://[\w\-._~:/?#\\\[\]@!$&'()*+,;=%]+", text)
                    if m:
                        url_candidate = m.group(0)
                except Exception:
                    pass

        # Emit source update if URL changed
        if url_candidate:
            try:
                last = getattr(self.event_server, 'last_source', None)
                if last != url_candidate:
                    self.event_server.last_source = url_candidate
                    self.event_server.broadcast('source', {"text": url_candidate})
            except Exception:
                pass
            # URL implies activity -> record open signal
            try:
                self.event_server.last_open_signal_ts = time.time()
            except Exception:
                pass

        # Hysteresis open/close decision
        now = time.time()
        grace = 8.0
        try:
            open_signal_recent = (getattr(self.event_server, 'last_open_signal_ts', 0.0) and (now - getattr(self.event_server, 'last_open_signal_ts', 0.0) <= grace))
            image_recent = (getattr(self.event_server, 'last_image_ts', 0.0) and (now - getattr(self.event_server, 'last_image_ts', 0.0) <= grace))
        except Exception:
            open_signal_recent = False
            image_recent = False

        if has_tabs:
            try:
                self.event_server.last_open_signal_ts = now
                open_signal_recent = True
            except Exception:
                pass

        open_now = bool(open_signal_recent or image_recent)
        try:
            if getattr(self.event_server, 'browser_open_last_state', None) != open_now:
                self.event_server.browser_open_last_state = open_now
                self.event_server.broadcast('browser_state', {"open": open_now, "text": (url_candidate or "No preview yet")})
        except Exception:
            pass

    # ---------------------------- Helpers ----------------------------
    def _broadcast(self, typ: str, payload: Any) -> None:
        try:
            self.event_server.broadcast(typ, payload)
        except Exception:
            pass