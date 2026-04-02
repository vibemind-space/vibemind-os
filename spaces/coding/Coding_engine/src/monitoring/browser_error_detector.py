"""
Browser Error Detector - Monitors browser console for JavaScript errors.

Uses MCP Playwright to detect client-side errors that the dev server
cannot see, such as:
- Missing exports (SyntaxError in browser)
- Runtime JavaScript errors
- Network request failures
- Unhandled promise rejections

Publishes BROWSER_ERROR events to trigger BugFixerAgent.
"""

import asyncio
import re
from datetime import datetime
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

import aiohttp
import structlog

from src.mind.event_bus import EventBus, Event, EventType

# Import BrowserConsoleAgent for MCP Playwright integration
try:
    from src.agents.browser_console_agent import (
        BrowserConsoleAgent,
        MCP_AVAILABLE,
        ViteError,
        ConsoleCapture,
    )
except ImportError:
    MCP_AVAILABLE = False
    BrowserConsoleAgent = None
    ViteError = None
    ConsoleCapture = None

# Import ClaudeCodeTool for LLM-based error classification
try:
    from src.tools.claude_code_tool import ClaudeCodeTool
    LLM_AVAILABLE = True
except ImportError:
    ClaudeCodeTool = None
    LLM_AVAILABLE = False

logger = structlog.get_logger(__name__)


@dataclass
class BrowserError:
    """Represents a browser console error."""
    error_type: str  # "missing_export", "syntax_error", "runtime_error", "network_error"
    message: str
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    stack_trace: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    # Parsed details for specific error types
    missing_export: Optional[str] = None
    target_module: Optional[str] = None

    # Fields for 500 error debugging (populated by enhanced error handling)
    response_body: Optional[str] = None
    status_code: Optional[int] = None


class BrowserErrorDetector:
    """
    Monitors browser console for JavaScript errors using MCP Playwright.

    Workflow:
    1. Navigate to preview URL
    2. Listen for console.error events
    3. Parse error messages to extract details
    4. Publish BROWSER_ERROR events for BugFixerAgent

    Usage:
        detector = BrowserErrorDetector(event_bus, port=5174)
        await detector.start()
        # ... monitors in background ...
        await detector.stop()
    """

    # Error patterns to detect and classify
    ERROR_PATTERNS = [
        # Missing export - Vite/ESM syntax error
        (
            r"does not provide an export named '([^']+)'",
            "missing_export",
            lambda m: {"missing_export": m.group(1)}
        ),
        (
            r"The requested module '([^']+)' does not provide an export named '([^']+)'",
            "missing_export",
            lambda m: {"target_module": m.group(1), "missing_export": m.group(2)}
        ),
        # Import resolution errors
        (
            r"Failed to resolve module specifier \"([^\"]+)\"",
            "import_error",
            lambda m: {"target_module": m.group(1)}
        ),
        # Syntax errors
        (
            r"SyntaxError: (.+)",
            "syntax_error",
            lambda m: {"message": m.group(1)}
        ),
        # Reference errors (undefined variables)
        (
            r"ReferenceError: (.+) is not defined",
            "reference_error",
            lambda m: {"undefined_name": m.group(1)}
        ),
        # Type errors
        (
            r"TypeError: (.+)",
            "type_error",
            lambda m: {"message": m.group(1)}
        ),
        # Network errors
        (
            r"Failed to load resource: the server responded with a status of (\d+)",
            "network_error",
            lambda m: {"status_code": int(m.group(1))}
        ),
        (
            r"net::ERR_([A-Z_]+)",
            "network_error",
            lambda m: {"error_code": m.group(1)}
        ),
    ]

    # How long to remember an error hash before allowing re-detection (seconds)
    ERROR_CACHE_TTL = 60.0  # 1 minute

    def __init__(
        self,
        event_bus: EventBus,
        port: int = 5173,
        check_interval: float = 2.0,  # Reduced from 5s for faster error detection
        working_dir: Optional[str] = None,
        mcp_playwright_available: Optional[bool] = None,
    ):
        """
        Initialize the browser error detector.

        Args:
            event_bus: EventBus for publishing events
            port: Preview server port
            check_interval: Seconds between page checks
            working_dir: Project working directory
            mcp_playwright_available: Whether MCP Playwright is available (auto-detected if None)
        """
        self.event_bus = event_bus
        self.port = port
        self.check_interval = check_interval
        self.working_dir = working_dir
        # Auto-detect MCP availability if not specified
        self.mcp_playwright_available = mcp_playwright_available if mcp_playwright_available is not None else MCP_AVAILABLE

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._detected_errors: list[BrowserError] = []
        # Error hash -> timestamp for TTL-based duplicate detection
        self._error_hashes: dict[str, float] = {}
        self._code_tool: Optional[Any] = None  # Lazy-loaded ClaudeCodeTool for LLM classification
        self._llm_classification_enabled = LLM_AVAILABLE

        self.logger = logger.bind(
            component="browser_error_detector",
            port=port,
        )

        # Subscribe to port detection events
        self.event_bus.subscribe(EventType.SERVER_PORT_DETECTED, self._on_port_detected)
        # Subscribe to CODE_FIXED to clear error cache (allow re-detection after fix)
        self.event_bus.subscribe(EventType.CODE_FIXED, self._on_code_fixed)

    async def _on_code_fixed(self, event: Event) -> None:
        """Handle CODE_FIXED event - clear error cache to allow re-detection.

        When a fix is applied, the same error might still occur if the fix
        didn't work. By clearing the cache, we can re-detect and re-fix.
        """
        fix_data = event.data or {}
        fix_type = fix_data.get("fix_type", "unknown")

        # Clear ALL error hashes - the fix might have fixed multiple errors
        old_count = len(self._error_hashes)
        self._error_hashes.clear()

        self.logger.info(
            "error_cache_cleared_on_fix",
            fix_type=fix_type,
            cleared_entries=old_count,
        )

    def _is_error_cached(self, error_hash: str) -> bool:
        """Check if error is in cache and not expired.

        Returns True if the error should be skipped (already recently handled).
        Returns False if the error should be processed (new or expired).
        """
        import time
        current_time = time.time()

        if error_hash not in self._error_hashes:
            return False

        cached_time = self._error_hashes[error_hash]
        age = current_time - cached_time

        if age > self.ERROR_CACHE_TTL:
            # Expired - allow re-detection
            self.logger.debug(
                "error_cache_expired",
                error_hash=error_hash[:50],
                age_seconds=round(age, 1),
            )
            return False

        # Still valid - skip this error
        return True

    def _cache_error(self, error_hash: str) -> None:
        """Add error to cache with current timestamp."""
        import time
        self._error_hashes[error_hash] = time.time()

        # Periodic cleanup of expired entries (every 20 entries)
        if len(self._error_hashes) % 20 == 0:
            self._cleanup_expired_cache()

    def _cleanup_expired_cache(self) -> None:
        """Remove expired entries from error cache."""
        import time
        current_time = time.time()
        expired = [
            h for h, t in self._error_hashes.items()
            if current_time - t > self.ERROR_CACHE_TTL
        ]
        for h in expired:
            del self._error_hashes[h]

        if expired:
            self.logger.debug(
                "expired_cache_entries_removed",
                count=len(expired),
            )

    async def _on_port_detected(self, event: Event) -> None:
        """Handle port detection event - only update for frontend ports.

        Backend ports (e.g., Express on 3001) cannot be debugged with
        Playwright since they serve JSON APIs, not HTML/JS pages.
        """
        if not event.data:
            return

        new_port = event.data.get("port")
        port_type = event.data.get("port_type", "frontend")  # Default to frontend for backwards compatibility

        if not new_port:
            return

        # Only monitor frontend ports (HTML/JS that Playwright can debug)
        if port_type != "frontend":
            self.logger.debug(
                "ignoring_backend_port",
                port=new_port,
                port_type=port_type,
                reason="Playwright can only debug frontend pages, not API endpoints",
            )
            return

        if new_port != self.port:
            old_port = self.port
            self.port = new_port
            self.logger.info(
                "port_updated_from_detection",
                old_port=old_port,
                new_port=new_port,
                port_type=port_type,
            )
            self.logger = logger.bind(
                component="browser_error_detector",
                port=new_port,
            )

    async def start(self) -> None:
        """Start the browser error monitoring loop."""
        if self._running:
            self.logger.warning("detector_already_running")
            return

        if not self.mcp_playwright_available:
            self.logger.warning("mcp_playwright_not_available",
                              message="Browser error detection disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

        self.logger.info(
            "browser_error_detector_started",
            check_interval=self.check_interval,
        )

    async def stop(self) -> None:
        """Stop the browser error monitoring loop."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self.logger.info(
            "browser_error_detector_stopped",
            total_errors_detected=len(self._detected_errors),
        )

    async def _monitor_loop(self) -> None:
        """Main monitoring loop - periodically checks for browser errors."""
        self.logger.info("monitor_loop_starting")

        # Initial delay to let preview server start (reduced from 10s for faster detection)
        await asyncio.sleep(3.0)

        while self._running:
            try:
                await self._check_for_errors()
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "monitor_loop_error",
                    error=str(e),
                )
                await asyncio.sleep(self.check_interval)

        self.logger.info("monitor_loop_stopped")

    async def _is_server_healthy(self, url: str, timeout: float = 3.0) -> bool:
        """
        Quick HTTP health check before launching browser capture.

        This avoids wasting time on expensive MCP browser operations
        when the dev server isn't even responding.

        Args:
            url: URL to check
            timeout: HTTP request timeout in seconds

        Returns:
            True if server responds with any HTTP status, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                ) as response:
                    # Any response means server is running
                    self.logger.debug(
                        "server_health_check_ok",
                        url=url,
                        status=response.status,
                    )
                    return True
        except asyncio.TimeoutError:
            self.logger.debug("server_health_check_timeout", url=url, timeout=timeout)
            return False
        except aiohttp.ClientError as e:
            self.logger.debug("server_health_check_failed", url=url, error=str(e))
            return False
        except Exception as e:
            self.logger.debug("server_health_check_error", url=url, error=str(e))
            return False

    async def _fetch_response_body(self, url: str, timeout: float = 3.0) -> str:
        """
        Fetch response body for failed requests (500 errors contain error details).

        When a 500 error occurs, the response body often contains the actual
        error message from Vite or the backend server.

        Args:
            url: URL to fetch
            timeout: HTTP request timeout in seconds

        Returns:
            Response body text (truncated to 2000 chars), or empty string on failure
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                ) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        # Truncate to avoid huge payloads
                        return body[:2000]
        except asyncio.TimeoutError:
            self.logger.debug("response_body_fetch_timeout", url=url)
        except Exception as e:
            self.logger.debug("response_body_fetch_failed", url=url, error=str(e))
        return ""

    async def _check_dependencies_exist(self) -> bool:
        """
        Check if node_modules exists in the working directory.

        Used to provide actionable hints for 500 errors that may be caused
        by missing dependencies.

        Returns:
            True if node_modules exists and is not empty, False otherwise
        """
        if not self.working_dir:
            return True  # Assume ok if no working dir configured

        from pathlib import Path
        node_modules = Path(self.working_dir) / "node_modules"

        if not node_modules.exists():
            return False

        # Check if directory has any contents
        try:
            return any(node_modules.iterdir())
        except Exception:
            return False

    async def _check_for_errors(self) -> None:
        """
        Check the browser console for errors using MCP Playwright.

        This method calls MCP Playwright tools to:
        1. Verify server is responding via HTTP health check
        2. Navigate to the preview URL
        3. Capture console errors
        4. Parse and publish error events
        """
        url = f"http://localhost:{self.port}"

        # Quick HTTP health check before expensive browser capture
        if not await self._is_server_healthy(url):
            self.logger.debug(
                "skipping_browser_capture",
                url=url,
                reason="Server not responding to HTTP",
            )
            return

        try:
            # Use MCP Playwright to check the page
            # This integrates with the existing MCP Playwright setup
            errors = await self._get_console_errors_via_mcp(url)

            for error in errors:
                await self._handle_error(error)

        except Exception as e:
            self.logger.debug(
                "check_for_errors_failed",
                url=url,
                error=str(e),
            )

    async def _get_console_errors_via_mcp(self, url: str) -> list[dict]:
        """
        Get console errors from MCP Playwright via BrowserConsoleAgent.

        Uses BrowserConsoleAgent to navigate to the page and capture
        console errors, network failures, and Vite module errors.

        Returns:
            List of error dictionaries with message, type, location info
        """
        if not MCP_AVAILABLE or BrowserConsoleAgent is None:
            self.logger.warning(
                "mcp_playwright_not_available",
                message="Browser error detection disabled - MCP Playwright not installed",
            )
            return []

        # Check if browser error detection is enabled in config
        from ..config import get_settings
        settings = get_settings()
        if not getattr(settings, 'browser_error_detector_enabled', True):
            self.logger.debug(
                "browser_error_detection_disabled",
                message="Browser error detection disabled via config",
            )
            return []

        errors = []

        try:
            # Create BrowserConsoleAgent instance with config-based browser
            # Firefox is default - most stable (no user-data-dir conflicts with user's open browser)
            browser = getattr(settings, 'browser_error_detector_browser', 'firefox')
            agent = BrowserConsoleAgent(browser=browser)

            # Capture console messages from the URL (now includes Vite overlay detection!)
            capture = await agent.capture_console(
                url=url,
                wait_seconds=3.0,
                check_vite_overlay=True  # Enable Vite error overlay detection
            )

            # Log capture status for debugging
            if not capture.navigation_ok:
                self.logger.info(
                    "browser_capture_failed",
                    url=url,
                    error=capture.error_message,
                    hint="Server may be slow/rebuilding, or MCP Playwright not installed (npm i -g @playwright/mcp)",
                )
                # FALLBACK: Try HTTP-based error detection when Playwright fails
                fallback_errors = await self._http_fallback_error_detection(url, port)
                if fallback_errors:
                    self.logger.info(
                        "http_fallback_detected_errors",
                        error_count=len(fallback_errors),
                    )
                    # Publish fallback errors as events for BugFixerAgent
                    for error in fallback_errors:
                        browser_error = BrowserError(
                            message=error.get("message", "Unknown error"),
                            error_type=error.get("error_type", "unknown"),
                            source_file=error.get("source", ""),
                            source="http_fallback",
                        )
                        await self._publish_error_event(browser_error)
                    return fallback_errors

            # HIGHEST PRIORITY: Vite/ESM module errors (these break the app!)
            for vite_error in capture.vite_errors:
                errors.append({
                    "message": vite_error.message,
                    "type": "vite_error",
                    "error_type": vite_error.error_type,
                    "source": vite_error.file_path,
                    "missing_export": vite_error.missing_export,
                    "target_module": vite_error.target_module,
                })
                self.logger.warning(
                    "vite_module_error_detected",
                    error_type=vite_error.error_type,
                    missing_export=vite_error.missing_export,
                    file_path=vite_error.file_path,
                )

            # Convert console errors to our format
            for error in capture.errors:
                errors.append({
                    "message": error.message,
                    "type": "error",
                    "source": error.source,
                })

            # Also capture failed network requests as errors
            for req in capture.failed_requests:
                # For 500 errors, try to fetch the response body for context
                response_body = ""
                if req.status >= 500:
                    response_body = await self._fetch_response_body(req.url)

                errors.append({
                    "message": f"Failed to load resource: the server responded with a status of {req.status} ({req.url})",
                    "type": "error",
                    "source": req.url,
                    "status_code": req.status,
                    "response_body": response_body,
                })

            if errors:
                self.logger.info(
                    "browser_errors_captured",
                    total_errors=len(errors),
                    vite_errors=len(capture.vite_errors),
                    console_errors=len(capture.errors),
                    network_failures=len(capture.failed_requests),
                )

        except Exception as e:
            self.logger.debug(
                "browser_console_capture_failed",
                error=str(e),
                url=url,
            )

        return errors

    async def _http_fallback_error_detection(self, url: str, port: int) -> list[dict]:
        """
        HTTP-based fallback for error detection when Playwright fails.

        Fetches the page HTML and checks for:
        1. Vite error overlay (vite-error-overlay custom element)
        2. React error boundary messages
        3. Crash indicators in HTML

        This is less accurate than browser console capture but works
        when Playwright can't navigate (crashed page, browser conflicts, etc.)
        """
        import httpx
        import re

        errors = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                html = response.text

                # Check for Vite error overlay
                if '<vite-error-overlay' in html or 'vite-error' in html.lower():
                    # Extract error message from overlay
                    error_match = re.search(
                        r'<pre[^>]*class="[^"]*message[^"]*"[^>]*>(.*?)</pre>',
                        html,
                        re.DOTALL | re.IGNORECASE
                    )
                    message = error_match.group(1) if error_match else "Vite error overlay detected"
                    message = re.sub(r'<[^>]+>', '', message).strip()  # Remove HTML tags

                    errors.append({
                        "message": message,
                        "type": "vite_error",
                        "error_type": "vite_overlay",
                        "source": "http_fallback",
                    })
                    self.logger.info("http_fallback_vite_error", message=message[:100])

                # Check for React error boundary
                if 'error boundary' in html.lower() or 'something went wrong' in html.lower():
                    errors.append({
                        "message": "React error boundary triggered - app crashed",
                        "type": "error",
                        "error_type": "react_crash",
                        "source": "http_fallback",
                    })

                # Check for common crash patterns in HTML
                crash_patterns = [
                    (r"Cannot read propert(?:y|ies) of (?:undefined|null)", "property_access_error"),
                    (r"TypeError:.*is not a function", "type_error"),
                    (r"ReferenceError:.*is not defined", "reference_error"),
                    (r"Uncaught.*Error", "uncaught_error"),
                ]

                for pattern, error_type in crash_patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        errors.append({
                            "message": match.group(0),
                            "type": "error",
                            "error_type": error_type,
                            "source": "http_fallback",
                        })
                        self.logger.info(
                            "http_fallback_error_pattern",
                            error_type=error_type,
                            message=match.group(0)[:100],
                        )

                # Detect React app crash by checking for empty/minimal content
                # A healthy React app should have substantial content after hydration
                # But the initial HTML might just have <div id="root"></div>
                # Check for React 18 createRoot's error display
                if '<div id="root">' in html:
                    # Check if root div has minimal content (app crashed before render)
                    root_match = re.search(r'<div id="root"[^>]*>(.*?)</div>', html, re.DOTALL)
                    if root_match:
                        root_content = root_match.group(1).strip()
                        # If root is empty or very small, app likely crashed
                        if len(root_content) < 50 and not errors:
                            self.logger.debug(
                                "possible_react_crash",
                                root_content_length=len(root_content),
                            )

        except Exception as e:
            self.logger.debug("http_fallback_failed", error=str(e))

        return errors

    def parse_error(self, error_message: str, error_type: str = "error") -> Optional[BrowserError]:
        """
        Parse a browser console error message into a structured BrowserError.

        Args:
            error_message: Raw error message from console
            error_type: Console message type (error, warning, etc.)

        Returns:
            BrowserError if parseable, None otherwise
        """
        # Try to match against known patterns
        for pattern, error_class, extractor in self.ERROR_PATTERNS:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                extra_data = extractor(match)

                # Extract file path if present in the message
                file_match = re.search(
                    r"/@fs/([^'\"]+\.(?:ts|tsx|js|jsx))",
                    error_message
                )
                source_file = file_match.group(1) if file_match else None

                # Clean up source file path
                if source_file:
                    # Remove Windows path prefixes from Vite
                    source_file = re.sub(r'^[A-Z]:/', '', source_file)

                return BrowserError(
                    error_type=error_class,
                    message=error_message,
                    source_file=source_file,
                    missing_export=extra_data.get("missing_export"),
                    target_module=extra_data.get("target_module"),
                )

        # Generic error if no pattern matched
        if error_type == "error":
            return BrowserError(
                error_type="unknown_error",
                message=error_message,
            )

        return None

    async def _classify_error_with_llm(self, error_message: str) -> Optional[BrowserError]:
        """
        Use Claude to classify unknown error types.

        This is a fallback for errors that don't match known patterns.
        Uses LLM to extract structured information from the error message.

        Args:
            error_message: Raw error message from browser console

        Returns:
            BrowserError with LLM-extracted details, or None if classification fails
        """
        if not self._llm_classification_enabled or ClaudeCodeTool is None:
            return None

        # Lazy-load code tool
        if self._code_tool is None:
            try:
                self._code_tool = ClaudeCodeTool(working_dir=self.working_dir or ".")
            except Exception as e:
                self.logger.warning("code_tool_init_failed", error=str(e))
                self._llm_classification_enabled = False
                return None

        prompt = f"""Classify this browser error and extract structured information:

Error: {error_message[:1000]}

Return ONLY JSON (no markdown, no explanation):
{{
  "error_type": "missing_export|syntax_error|runtime_error|network_error|reference_error|type_error|unknown",
  "source_file": "extracted file path or empty string",
  "missing_export": "if applicable, otherwise empty string",
  "target_module": "if applicable, otherwise empty string",
  "severity": "critical|high|medium|low",
  "suggested_fix": "brief fix suggestion in one line"
}}
"""

        try:
            result = await asyncio.wait_for(
                self._code_tool.execute(prompt, "", "debugging"),
                timeout=15.0  # Fast timeout for classification
            )

            output = result.output if hasattr(result, 'output') else str(result)

            # Extract JSON from output
            import json
            json_match = re.search(r'\{[^{}]*"error_type"[^{}]*\}', output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                self.logger.info(
                    "llm_error_classification",
                    error_type=data.get("error_type"),
                    severity=data.get("severity"),
                    source_file=data.get("source_file"),
                )

                return BrowserError(
                    error_type=data.get("error_type", "unknown"),
                    message=error_message,
                    source_file=data.get("source_file") or None,
                    missing_export=data.get("missing_export") or None,
                    target_module=data.get("target_module") or None,
                )

        except asyncio.TimeoutError:
            self.logger.debug("llm_classification_timeout")
        except Exception as e:
            self.logger.debug("llm_classification_failed", error=str(e))

        return None

    async def parse_error_with_llm_fallback(
        self, error_message: str, error_type: str = "error"
    ) -> Optional[BrowserError]:
        """
        Parse an error with LLM fallback for unknown patterns.

        First tries regex patterns, then falls back to LLM classification
        for unrecognized error types.

        Args:
            error_message: Raw error message from console
            error_type: Console message type (error, warning, etc.)

        Returns:
            BrowserError if parseable, None otherwise
        """
        # First try regex patterns
        result = self.parse_error(error_message, error_type)

        # If we got an unknown_error and LLM is available, try LLM classification
        if result and result.error_type == "unknown_error" and self._llm_classification_enabled:
            llm_result = await self._classify_error_with_llm(error_message)
            if llm_result and llm_result.error_type != "unknown":
                return llm_result

        return result

    # =========================================================================
    # Phase 9: LLM-Enhanced Console Error Semantic Classification
    # =========================================================================

    async def classify_console_errors_with_llm(
        self,
        errors: list[dict],
    ) -> list[dict]:
        """
        Use LLM to semantically classify browser console errors.

        This method provides deeper understanding than regex patterns by:
        1. Identifying error categories (network, runtime, react, security, etc.)
        2. Determining actionability (can we fix it or is it third-party?)
        3. Finding root causes across related errors
        4. Suggesting specific fixes

        Args:
            errors: List of error dicts with 'message', 'type', 'source' keys

        Returns:
            List of classified error dicts with additional fields:
            - category: network | runtime | react | security | deprecation | third_party
            - severity: critical | error | warning | info
            - actionable: bool
            - root_cause: str
            - fix: str
        """
        import json

        if not errors:
            return []

        if not self._llm_classification_enabled or ClaudeCodeTool is None:
            # Return basic classification without LLM
            return [
                {
                    **error,
                    "category": self._guess_category(error.get("message", "")),
                    "severity": "error",
                    "actionable": True,
                    "root_cause": "Unknown - LLM classification unavailable",
                    "fix": "Review error manually",
                }
                for error in errors
            ]

        # Lazy-load code tool
        if self._code_tool is None:
            try:
                self._code_tool = ClaudeCodeTool(working_dir=self.working_dir or ".")
            except Exception as e:
                self.logger.warning("code_tool_init_failed", error=str(e))
                self._llm_classification_enabled = False
                return errors

        # Format errors for LLM (limit to 20 for token efficiency)
        errors_text = json.dumps(errors[:20], indent=2)

        prompt = f"""Classify these browser console errors semantically:

## ERRORS:
{errors_text}

## CLASSIFICATION TASK:

For each error, determine:

1. **Category**:
   - `network`: Failed HTTP requests, CORS, fetch errors
   - `runtime`: JavaScript runtime errors (TypeError, ReferenceError, etc.)
   - `react`: React-specific errors (hooks, rendering, state)
   - `security`: CSP violations, mixed content, XSS blocks
   - `deprecation`: Deprecated API warnings
   - `third_party`: Errors from external libraries we can't fix

2. **Severity**:
   - `critical`: App won't load/function (missing exports, syntax errors)
   - `error`: Feature broken but app loads
   - `warning`: Degraded experience but functional
   - `info`: Informational, can be ignored

3. **Actionable**: Can we fix this in our codebase? (true/false)
   - `true`: Our code issue (missing export, type error, etc.)
   - `false`: Third-party library, browser extension, etc.

4. **Root Cause**: What's actually wrong (1 sentence)

5. **Fix**: How to fix it (1 sentence, code-specific if possible)

## RESPONSE FORMAT:

```json
{{
  "classified_errors": [
    {{
      "original_message": "First 100 chars of original error",
      "category": "runtime",
      "severity": "critical",
      "actionable": true,
      "root_cause": "Component UserProfile.tsx accesses user.name before user is loaded",
      "fix": "Add loading check: if (!user) return <Loading />"
    }}
  ],
  "summary": {{
    "total": 5,
    "critical": 1,
    "actionable": 3,
    "top_issue": "Most important issue to fix first"
  }}
}}
```
"""

        try:
            result = await asyncio.wait_for(
                self._code_tool.execute(prompt, "", "debugging"),
                timeout=30.0
            )

            output = result.output if hasattr(result, 'output') else str(result)

            # Extract JSON from output
            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))
                classified = analysis.get("classified_errors", [])

                self.logger.info(
                    "llm_batch_classification_complete",
                    total_errors=len(errors),
                    classified=len(classified),
                    summary=analysis.get("summary", {}),
                )

                # Merge classifications back with original errors
                result_errors = []
                for i, error in enumerate(errors[:20]):
                    classified_data = classified[i] if i < len(classified) else {}
                    result_errors.append({
                        **error,
                        "category": classified_data.get("category", "unknown"),
                        "severity": classified_data.get("severity", "error"),
                        "actionable": classified_data.get("actionable", True),
                        "root_cause": classified_data.get("root_cause", ""),
                        "fix": classified_data.get("fix", ""),
                    })

                # Add any remaining errors without classification
                for error in errors[20:]:
                    result_errors.append({
                        **error,
                        "category": self._guess_category(error.get("message", "")),
                        "severity": "error",
                        "actionable": True,
                        "root_cause": "Not classified (batch limit)",
                        "fix": "",
                    })

                return result_errors

        except asyncio.TimeoutError:
            self.logger.warning("llm_batch_classification_timeout")
        except Exception as e:
            self.logger.warning("llm_batch_classification_failed", error=str(e))

        # Return original errors with basic guessed categories
        return [
            {
                **error,
                "category": self._guess_category(error.get("message", "")),
                "severity": "error",
                "actionable": True,
                "root_cause": "Classification failed",
                "fix": "",
            }
            for error in errors
        ]

    def _guess_category(self, message: str) -> str:
        """Quick heuristic category guess without LLM."""
        message_lower = message.lower()

        if any(kw in message_lower for kw in ["fetch", "network", "cors", "http", "404", "500", "net::"]):
            return "network"
        if any(kw in message_lower for kw in ["react", "hook", "render", "component", "usestate", "useeffect"]):
            return "react"
        if any(kw in message_lower for kw in ["security", "csp", "mixed content", "xss"]):
            return "security"
        if any(kw in message_lower for kw in ["deprecated", "deprecation"]):
            return "deprecation"
        if any(kw in message_lower for kw in ["extension", "chrome-extension", "moz-extension"]):
            return "third_party"

        return "runtime"

    async def trace_export_chain_with_llm(
        self,
        error_message: str,
        index_files: dict[str, str],
    ) -> dict:
        """
        Use LLM to trace "module not found" errors through barrel exports.

        When a component can't find an export, it might be missing from
        one or more index.ts files in the export chain.

        Args:
            error_message: The "module not found" or "does not provide export" error
            index_files: Dict of {path: content} for index.ts files

        Returns:
            Dict with:
            - missing_export: What's being imported
            - should_be_in: Which file should export it
            - chain: Full export chain path
            - fix: Specific fix instruction
        """
        import json

        if not self._llm_classification_enabled or ClaudeCodeTool is None:
            return {
                "missing_export": "",
                "should_be_in": "",
                "chain": [],
                "fix": "LLM unavailable - review manually",
            }

        # Lazy-load code tool
        if self._code_tool is None:
            try:
                self._code_tool = ClaudeCodeTool(working_dir=self.working_dir or ".")
            except Exception:
                return {"error": "Failed to initialize code tool"}

        # Format index files for LLM
        index_text = json.dumps(index_files, indent=2)[:3000]

        prompt = f"""Trace this import error through the export chain:

## ERROR:
{error_message}

## INDEX FILES (barrel exports):
{index_text}

## TASK:

When you see errors like:
- "The requested module 'X' does not provide an export named 'Y'"
- "Module not found: Can't resolve 'X'"

The issue is usually:
1. Component Y exists but isn't exported from its index.ts
2. Parent index.ts doesn't re-export from child index.ts
3. Circular dependency in barrel exports

Trace the chain and find:
1. What's being imported?
2. Where should it be exported from?
3. Which index.ts is missing the export?
4. Full chain: component → index.ts → parent/index.ts

## RESPONSE FORMAT:

```json
{{
  "missing_export": "ComponentName",
  "should_be_in": "src/components/index.ts",
  "chain": ["src/components/UserProfile.tsx", "src/components/index.ts", "src/index.ts"],
  "fix": "Add 'export {{ ComponentName }} from './ComponentName'' to src/components/index.ts"
}}
```
"""

        try:
            result = await asyncio.wait_for(
                self._code_tool.execute(prompt, "", "debugging"),
                timeout=20.0
            )

            output = result.output if hasattr(result, 'output') else str(result)

            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                trace = json.loads(json_match.group(1))

                self.logger.info(
                    "export_chain_traced",
                    missing_export=trace.get("missing_export"),
                    should_be_in=trace.get("should_be_in"),
                )

                return trace

        except asyncio.TimeoutError:
            self.logger.warning("export_chain_trace_timeout")
        except Exception as e:
            self.logger.warning("export_chain_trace_failed", error=str(e))

        return {
            "missing_export": "",
            "should_be_in": "",
            "chain": [],
            "fix": "Trace failed - review manually",
        }

    async def get_actionable_errors(self) -> list[dict]:
        """
        Get only actionable errors that we can fix.

        Uses LLM classification to filter out:
        - Third-party library errors
        - Browser extension errors
        - Deprecation warnings (low priority)

        Returns:
            List of classified errors that are actionable
        """
        raw_errors = [
            {"message": e.message, "type": e.error_type, "source": e.source_file}
            for e in self._detected_errors
        ]

        if not raw_errors:
            return []

        classified = await self.classify_console_errors_with_llm(raw_errors)

        # Filter to only actionable errors
        actionable = [
            e for e in classified
            if e.get("actionable", True) and e.get("severity") in ("critical", "error")
        ]

        # Sort by severity (critical first)
        severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        actionable.sort(key=lambda e: severity_order.get(e.get("severity", "error"), 1))

        return actionable

    async def _handle_error(self, error_data: dict) -> None:
        """Handle a detected browser error."""
        error_message = error_data.get("message", "")
        error_type = error_data.get("type", "error")

        # Extract 500 error context if available
        status_code = error_data.get("status_code")
        response_body = error_data.get("response_body", "")

        # Special handling for Vite errors (already pre-parsed with extra data)
        if error_type == "vite_error":
            vite_error_type = error_data.get("error_type", "unknown")
            missing_export = error_data.get("missing_export", "")
            target_module = error_data.get("target_module", "")
            source_file = error_data.get("source", "")

            # Check for duplicate with TTL - include message hash for generic errors
            # This ensures different runtime errors aren't treated as duplicates
            import hashlib
            msg_hash = hashlib.md5(error_message[:200].encode()).hexdigest()[:8]
            error_hash = f"vite:{vite_error_type}:{missing_export}:{source_file}:{msg_hash}"
            if self._is_error_cached(error_hash):
                return
            self._cache_error(error_hash)

            # Create BrowserError from Vite data
            browser_error = BrowserError(
                error_type=vite_error_type,
                message=error_message,
                source_file=source_file,
                missing_export=missing_export,
                target_module=target_module,
            )

            self._detected_errors.append(browser_error)

            self.logger.warning(
                "vite_error_detected",
                error_type=vite_error_type,
                missing_export=missing_export,
                source_file=source_file,
                target_module=target_module,
            )

            # Publish event for BugFixerAgent
            await self._publish_error_event(browser_error)
            return

        # Standard error handling path
        browser_error = self.parse_error(error_message, error_type)
        if not browser_error:
            return

        # Add 500 error context if available
        if status_code:
            browser_error.status_code = status_code
        if response_body:
            browser_error.response_body = response_body

        # Check for duplicate with TTL (avoid spamming)
        error_hash = f"{browser_error.error_type}:{browser_error.message[:100]}"
        if self._is_error_cached(error_hash):
            return
        self._cache_error(error_hash)

        # Store the error
        self._detected_errors.append(browser_error)

        self.logger.warning(
            "browser_error_detected",
            error_type=browser_error.error_type,
            message=browser_error.message[:200],
            source_file=browser_error.source_file,
            missing_export=browser_error.missing_export,
        )

        # Publish event for BugFixerAgent
        await self._publish_error_event(browser_error)

    async def _publish_error_event(self, error: BrowserError) -> None:
        """
        Publish a BROWSER_ERROR event to the event bus.

        For 500 errors, includes enhanced context:
        - Vite server logs (from SharedState)
        - node_modules existence check
        - Response body (if available)
        - Investigation hints
        """
        event_data = {
            "error_type": error.error_type,
            "message": error.message,
            "source_file": error.source_file,
            "line_number": error.line_number,
            "missing_export": error.missing_export,
            "target_module": error.target_module,
            "working_dir": self.working_dir,
            "timestamp": error.timestamp.isoformat(),
        }

        # Enhanced context for 500/network errors
        is_500_error = (
            error.error_type == "network_error" and
            ("500" in error.message or (error.status_code and error.status_code >= 500))
        )

        if is_500_error:
            # Get Vite server logs from SharedState
            try:
                from src.mind.shared_state import SharedState
                vite_logs = SharedState().get_vite_logs(20)
            except Exception:
                vite_logs = []

            # Check if dependencies exist
            deps_exist = await self._check_dependencies_exist()

            # Build investigation hints
            investigation_hints = []
            if not deps_exist:
                investigation_hints.append(
                    "CRITICAL: node_modules missing or empty - run 'npm install' first"
                )
            investigation_hints.extend([
                "500 errors are server-side - check vite_server_logs field for actual error",
                "Source file attribution (:0) is unreliable for server errors",
            ])

            # Add enhanced context to event
            event_data["requires_investigation"] = True
            event_data["vite_server_logs"] = vite_logs
            event_data["node_modules_exists"] = deps_exist
            event_data["response_body"] = error.response_body or ""
            event_data["status_code"] = error.status_code
            event_data["investigation_hints"] = investigation_hints

            self.logger.info(
                "500_error_context_added",
                has_vite_logs=len(vite_logs) > 0,
                deps_exist=deps_exist,
                has_response_body=bool(error.response_body),
            )

        event = Event(
            type=EventType.BROWSER_ERROR,
            source="browser_error_detector",
            data=event_data,
        )

        await self.event_bus.publish(event)

        self.logger.info(
            "browser_error_event_published",
            error_type=error.error_type,
            is_500=is_500_error,
        )

    async def report_error(self, error_message: str, error_type: str = "error") -> None:
        """
        Manually report an error (called by external integrations).

        This is the main entry point for MCP Playwright integration.
        When Playwright detects a console.error, it calls this method.

        Args:
            error_message: The error message from the browser console
            error_type: The console message type
        """
        await self._handle_error({
            "message": error_message,
            "type": error_type,
        })

    def clear_error_cache(self) -> None:
        """Clear the duplicate error cache to allow re-detection."""
        self._error_hashes.clear()
        self.logger.info("error_cache_cleared")

    @property
    def is_running(self) -> bool:
        """Check if detector is running."""
        return self._running

    @property
    def status(self) -> dict:
        """Get current detector status."""
        return {
            "running": self._running,
            "port": self.port,
            "check_interval": self.check_interval,
            "total_errors_detected": len(self._detected_errors),
            "unique_errors_cached": len(self._error_hashes),
            "mcp_playwright_available": self.mcp_playwright_available,
        }


async def create_browser_error_detector(
    event_bus: EventBus,
    port: int = 5173,
    check_interval: float = 2.0,  # Reduced from 5s for faster error detection
    working_dir: Optional[str] = None,
    auto_start: bool = True,
) -> BrowserErrorDetector:
    """
    Factory function to create and optionally start a browser error detector.

    Args:
        event_bus: EventBus for publishing events
        port: Preview server port
        check_interval: Seconds between checks
        working_dir: Project working directory
        auto_start: Start monitoring immediately

    Returns:
        BrowserErrorDetector instance
    """
    detector = BrowserErrorDetector(
        event_bus=event_bus,
        port=port,
        check_interval=check_interval,
        working_dir=working_dir,
    )

    if auto_start:
        await detector.start()

    return detector
