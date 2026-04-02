"""
Browser Console Agent - Erfasst Console Errors via Playwright MCP
Verwendet native Playwright MCP Tools für zuverlässige Fehlererfassung

Note: MCP actor errors (BrokenResourceError, McpError timeouts) are suppressed
to reduce log noise - these are expected when MCP sessions fail to initialize.
"""
from dataclasses import dataclass, field
from pathlib import Path
import asyncio
import re
import logging
import json
from typing import Any, Optional

from ..utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)

# Suppress noisy MCP actor errors from autogen_ext
# These errors flood logs when Playwright MCP fails to initialize
logging.getLogger("autogen_ext.tools.mcp").setLevel(logging.CRITICAL)
logging.getLogger("autogen_ext.tools.mcp._actor").setLevel(logging.CRITICAL)
logging.getLogger("anyio").setLevel(logging.WARNING)

try:
    from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    McpWorkbench = None
    StdioServerParams = None


@dataclass
class ConsoleMessage:
    """Eine einzelne Console-Nachricht"""
    level: str  # INFO, WARNING, ERROR, LOG
    message: str
    source: str = ""
    
    @classmethod
    def from_line(cls, line: str) -> "ConsoleMessage":
        """Parse eine Zeile aus browser_console_messages"""
        # Format: [ERROR] message @ source:line
        match = re.match(r'\[(\w+)\]\s*(.*?)(?:\s*@\s*(.*))?$', line.strip())
        if match:
            level = match.group(1)
            message = match.group(2)
            source = match.group(3) or ""
            return cls(level=level, message=message, source=source)
        return cls(level="UNKNOWN", message=line)


@dataclass
class NetworkRequest:
    """Ein einzelner Network Request"""
    method: str
    url: str
    status: int
    status_text: str
    
    @classmethod
    def from_line(cls, line: str) -> "NetworkRequest | None":
        """Parse eine Zeile aus browser_network_requests"""
        # Format: [GET] http://url => [200] OK
        match = re.match(r'\[(\w+)\]\s*(.*?)\s*=>\s*\[(\d+)\]\s*(.*)', line.strip())
        if match:
            return cls(
                method=match.group(1),
                url=match.group(2),
                status=int(match.group(3)),
                status_text=match.group(4)
            )
        return None
    
    @property
    def is_error(self) -> bool:
        """True wenn Status >= 400"""
        return self.status >= 400


@dataclass
class ViteError:
    """Ein Vite/ESM Modul-Ladefehler aus dem Error Overlay"""
    error_type: str  # "missing_export", "syntax_error", "import_error"
    message: str
    file_path: str = ""
    missing_export: str = ""
    target_module: str = ""

    @classmethod
    def from_overlay_text(cls, text: str) -> "ViteError | None":
        """Parse einen Vite Error Overlay Text"""
        import re

        # Pattern: "does not provide an export named 'X'"
        export_match = re.search(
            r"does not provide an export named ['\"]([^'\"]+)['\"]",
            text,
            re.IGNORECASE
        )
        if export_match:
            # Extract file path from "/@fs/..." or file path
            file_match = re.search(r"/@fs/([^'\"]+\.(?:ts|tsx|js|jsx))", text)
            file_path = file_match.group(1) if file_match else ""

            return cls(
                error_type="missing_export",
                message=text[:500],
                file_path=file_path,
                missing_export=export_match.group(1),
            )

        # Pattern: "Failed to resolve module"
        module_match = re.search(
            r"Failed to resolve (?:module|import) ['\"]([^'\"]+)['\"]",
            text,
            re.IGNORECASE
        )
        if module_match:
            return cls(
                error_type="import_error",
                message=text[:500],
                target_module=module_match.group(1),
            )

        # Pattern: "SyntaxError"
        if "SyntaxError" in text:
            return cls(
                error_type="syntax_error",
                message=text[:500],
            )

        return None

    @classmethod
    async def from_overlay_text_async(
        cls,
        text: str,
        working_dir: str = ".",
    ) -> "ViteError":
        """
        Parse Vite Error Overlay text with LLM fallback for unknown errors.

        Uses multi-tier classification:
        1. Pattern-based fast classification
        2. LLM fallback for unknown error types
        """
        # Try pattern-based classification first
        pattern_result = cls.from_overlay_text(text)
        if pattern_result is not None:
            return pattern_result

        # Use classification cache for LLM fallback
        cache = get_classification_cache()
        key = cache._generate_key(text, "browser_error")

        result = await cache.classify(
            key=key,
            content=text,
            pattern_classifier=lambda t: _pattern_classify_browser_error(t),
            llm_classifier=lambda t: _llm_classify_browser_error(t, working_dir),
            category_type="browser_error",
        )

        # Extract file path if present
        file_match = re.search(r"/@fs/([^'\"]+\.(?:ts|tsx|js|jsx))", text)
        file_path = file_match.group(1) if file_match else ""

        # Extract module name for import errors
        module_match = re.search(r"['\"]([^'\"]+)['\"]", text)
        target_module = module_match.group(1) if module_match else ""

        return cls(
            error_type=result.category,
            message=text[:500],
            file_path=file_path,
            target_module=target_module if result.category == "import_error" else "",
        )


def _pattern_classify_browser_error(text: str) -> ClassificationResult:
    """Fast pattern-based browser error classification."""
    text_lower = text.lower()

    patterns = [
        (["does not provide an export"], "missing_export", 0.95),
        (["failed to resolve module"], "import_error", 0.95),
        (["failed to resolve import"], "import_error", 0.95),
        (["cannot find module"], "import_error", 0.9),
        (["syntaxerror"], "syntax_error", 0.95),
        (["unexpected token"], "syntax_error", 0.9),
        (["referenceerror"], "reference_error", 0.9),
        (["is not defined"], "reference_error", 0.85),
        (["typeerror"], "type_error", 0.9),
        (["is not a function"], "type_error", 0.85),
        (["cannot read propert"], "type_error", 0.85),
        (["rangeerror"], "range_error", 0.9),
        (["networkerror"], "network_error", 0.9),
        (["failed to fetch"], "network_error", 0.85),
        (["cors"], "cors_error", 0.9),
        (["uncaught"], "runtime_error", 0.7),
    ]

    for keywords, category, confidence in patterns:
        if all(kw in text_lower for kw in keywords):
            return ClassificationResult(
                category=category,
                confidence=confidence,
                source=ClassificationSource.PATTERN,
                metadata={"matched_keywords": keywords},
            )

    return ClassificationResult(
        category="unknown",
        confidence=0.0,
        source=ClassificationSource.PATTERN,
    )


async def _llm_classify_browser_error(text: str, working_dir: str) -> ClassificationResult:
    """LLM-based semantic browser error classification."""
    prompt = f"""Classify this browser console error into ONE category:

Error: {text[:1000]}

Categories:
- missing_export: Module does not export the requested name
- import_error: Failed to resolve/find module
- syntax_error: JavaScript/TypeScript syntax error
- reference_error: Variable/function is not defined
- type_error: Type mismatch, not a function, cannot read property
- range_error: Value out of range
- network_error: Failed to fetch, network issues
- cors_error: Cross-origin request blocked
- runtime_error: General runtime error
- unknown: Cannot classify

Return ONLY valid JSON: {{"category": "...", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""
    try:
        from ..tools.claude_code_tool import ClaudeCodeTool
        tool = ClaudeCodeTool(working_dir=working_dir)
        response = await tool.execute(prompt=prompt, skill_tier="minimal")

        # Parse JSON response
        match = re.search(r'\{[^}]+\}', response)
        if match:
            data = json.loads(match.group())
            category = data.get("category", "unknown")
            valid_categories = [
                "missing_export", "import_error", "syntax_error", "reference_error",
                "type_error", "range_error", "network_error", "cors_error",
                "runtime_error", "unknown"
            ]
            if category not in valid_categories:
                category = "runtime_error"

            return ClassificationResult(
                category=category,
                confidence=min(data.get("confidence", 0.7), 0.95),
                source=ClassificationSource.LLM,
                metadata={"reasoning": data.get("reasoning", "")},
            )
    except Exception:
        pass

    return ClassificationResult(
        category="runtime_error",
        confidence=0.3,
        source=ClassificationSource.LLM,
        metadata={"error": "LLM classification failed"},
    )


@dataclass
class ConsoleCapture:
    """Erfasste Console-Daten von einer URL"""
    url: str
    console_messages: list[ConsoleMessage] = field(default_factory=list)
    network_requests: list[NetworkRequest] = field(default_factory=list)
    vite_errors: list[ViteError] = field(default_factory=list)  # NEW: Vite overlay errors
    page_errors: list[str] = field(default_factory=list)  # NEW: Uncaught exceptions
    navigation_ok: bool = True
    error_message: str = ""

    @property
    def errors(self) -> list[ConsoleMessage]:
        """Nur ERROR Level Messages"""
        return [m for m in self.console_messages if m.level == "ERROR"]

    @property
    def all_errors_count(self) -> int:
        """Gesamtzahl aller Fehler (Console + Vite + Page)"""
        return len(self.errors) + len(self.vite_errors) + len(self.page_errors)
    
    @property
    def warnings(self) -> list[ConsoleMessage]:
        """Nur WARNING Level Messages"""
        return [m for m in self.console_messages if m.level in ("WARNING", "WARN")]
    
    @property
    def failed_requests(self) -> list[NetworkRequest]:
        """Nur fehlgeschlagene Network Requests (4xx, 5xx)"""
        return [r for r in self.network_requests if r.is_error]
    
    def format_for_claude(self) -> str:
        """Formatiert alle Fehler für Claude CLI Context"""
        lines = []

        if not self.navigation_ok:
            lines.append(f"[WARNING] Navigation fehlgeschlagen: {self.error_message}")
            return "\n".join(lines)

        # Vite/ESM Module Errors (HIGHEST PRIORITY - these break the app!)
        if self.vite_errors:
            lines.append(f"## Vite/Module Errors ({len(self.vite_errors)}) - CRITICAL")
            for err in self.vite_errors:
                lines.append(f"- [{err.error_type.upper()}] {err.message[:200]}")
                if err.file_path:
                    lines.append(f"  File: {err.file_path}")
                if err.missing_export:
                    lines.append(f"  Missing Export: {err.missing_export}")
                if err.target_module:
                    lines.append(f"  Target Module: {err.target_module}")

        # Page Errors (Uncaught exceptions)
        if self.page_errors:
            lines.append(f"\n## Page Errors ({len(self.page_errors)}) - Uncaught Exceptions")
            for err in self.page_errors:
                lines.append(f"- {err[:200]}")

        # Console Errors
        if self.errors:
            lines.append(f"\n## Console Errors ({len(self.errors)})")
            for err in self.errors:
                lines.append(f"- {err.message}")
                if err.source:
                    lines.append(f"  Source: {err.source}")

        # Console Warnings
        if self.warnings:
            lines.append(f"\n## Console Warnings ({len(self.warnings)})")
            for warn in self.warnings:
                lines.append(f"- {warn.message}")

        # Failed Network Requests
        if self.failed_requests:
            lines.append(f"\n## Failed Network Requests ({len(self.failed_requests)})")
            for req in self.failed_requests:
                lines.append(f"- [{req.method}] {req.url} => {req.status} {req.status_text}")

        if not lines:
            return "[OK] Keine Console-Fehler gefunden"

        return "\n".join(lines)


@dataclass
class MultiRouteCapture:
    """Erfasste Console-Daten von mehreren Routes"""
    base_url: str
    routes_crawled: list[str] = field(default_factory=list)
    captures: dict[str, ConsoleCapture] = field(default_factory=dict)
    
    @property
    def total_errors(self) -> int:
        return sum(len(c.errors) for c in self.captures.values())
    
    @property
    def total_warnings(self) -> int:
        return sum(len(c.warnings) for c in self.captures.values())
    
    @property
    def total_failed_requests(self) -> int:
        return sum(len(c.failed_requests) for c in self.captures.values())
    
    def format_for_claude(self) -> str:
        """Formatiert alle Fehler von allen Routes für Claude CLI"""
        lines = [
            f"# Browser Console Capture",
            f"Base URL: {self.base_url}",
            f"Routes crawled: {', '.join(self.routes_crawled)}",
            f"Total Errors: {self.total_errors}",
            f"Total Warnings: {self.total_warnings}",
            f"Failed Requests: {self.total_failed_requests}",
            ""
        ]
        
        for route, capture in self.captures.items():
            if capture.errors or capture.warnings or capture.failed_requests:
                lines.append(f"\n## Route: {route}")
                lines.append(capture.format_for_claude())
        
        return "\n".join(lines)
    
    def to_console_capture(self) -> ConsoleCapture:
        """Konvertiert zu einem einzelnen ConsoleCapture (für Kompatibilität)"""
        merged = ConsoleCapture(url=self.base_url)
        for capture in self.captures.values():
            merged.console_messages.extend(capture.console_messages)
            merged.network_requests.extend(capture.network_requests)
        return merged


class BrowserConsoleAgent:
    """
    Agent zur Erfassung von Browser Console Errors via Playwright MCP.
    Verwendet native Playwright MCP Tools für zuverlässige Fehlererfassung.
    """

    # Timeout for individual MCP tool calls (navigation, snapshot, etc.)
    MCP_TOOL_TIMEOUT = 60.0  # 60 seconds per MCP call (increased for slow dev servers)

    # Timeout for MCP session initialization (starting the browser)
    MCP_SESSION_TIMEOUT = 120.0  # 120 seconds to start MCP server + browser (matches servers.json)

    def __init__(self, browser: str = None):
        """
        Args:
            browser: Browser-Typ ("chrome", "firefox", "webkit", "msedge")
                     Default from config: firefox (most stable - no user-data-dir conflicts)
        """
        if not MCP_AVAILABLE:
            raise ImportError(
                "AutoGen MCP nicht verfügbar. Installation: pip install autogen-ext[mcp]"
            )

        # Use config default if not specified (firefox is most stable)
        if browser is None:
            from ..config import get_settings
            settings = get_settings()
            browser = getattr(settings, 'browser_error_detector_browser', 'firefox')

        self.browser = browser
        self._workbench: McpWorkbench | None = None
    
    def _get_server_params(self) -> StdioServerParams:
        """Erstellt die Playwright MCP Server Parameter"""
        return StdioServerParams(
            command="npx",
            args=["--yes", "@playwright/mcp@latest", "--browser", self.browser, "--headless"],
            read_timeout_seconds=120.0,  # Match servers.json read_timeout_seconds
            env={
                "PLAYWRIGHT_TIMEOUT": "60000",  # 60 seconds for internal Playwright timeouts
            }
        )
    
    async def capture_console(
        self,
        url: str,
        wait_seconds: float = 3.0,
        check_vite_overlay: bool = True
    ) -> ConsoleCapture:
        """
        Erfasst Console Messages, Network Requests und Vite Error Overlays von einer URL.

        Args:
            url: Die zu testende URL
            wait_seconds: Wartezeit für async Requests
            check_vite_overlay: Ob nach Vite Error Overlay gesucht werden soll

        Returns:
            ConsoleCapture mit allen erfassten Daten
        """
        capture = ConsoleCapture(url=url)

        # Wrap entire MCP session with timeout to prevent hangs during initialization
        try:
            capture = await asyncio.wait_for(
                self._capture_console_impl(url, wait_seconds, check_vite_overlay),
                timeout=self.MCP_SESSION_TIMEOUT
            )
        except asyncio.TimeoutError:
            import structlog
            _logger = structlog.get_logger(__name__)
            _logger.warning(
                "mcp_session_timeout",
                url=url,
                timeout=self.MCP_SESSION_TIMEOUT,
                hint="MCP Playwright server took too long to start"
            )
            capture.navigation_ok = False
            capture.error_message = f"MCP session timeout ({self.MCP_SESSION_TIMEOUT}s) - browser may be slow to start"
        except Exception as e:
            import structlog
            _logger = structlog.get_logger(__name__)
            _logger.debug(
                "mcp_session_failed",
                url=url,
                error=str(e)[:100]
            )
            capture.navigation_ok = False
            capture.error_message = f"MCP session failed: {str(e)[:100]}"

        return capture

    async def _capture_console_impl(
        self,
        url: str,
        wait_seconds: float = 3.0,
        check_vite_overlay: bool = True
    ) -> ConsoleCapture:
        """
        Internal implementation of capture_console.
        Called with a timeout wrapper from capture_console().
        """
        capture = ConsoleCapture(url=url)

        params = self._get_server_params()

        try:
            async with McpWorkbench(server_params=params) as workbench:
                # 1. Seite navigieren (with timeout protection)
                try:
                    nav_result = await asyncio.wait_for(
                        workbench.call_tool("browser_navigate", {"url": url}),
                        timeout=self.MCP_TOOL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    capture.navigation_ok = False
                    capture.error_message = f"Navigation timeout ({self.MCP_TOOL_TIMEOUT}s) - server may be slow or unresponsive"
                    return capture

                # Navigation-Ergebnis prüfen
                if hasattr(nav_result, 'is_error') and nav_result.is_error:
                    capture.navigation_ok = False
                    if hasattr(nav_result, 'result') and nav_result.result:
                        for item in nav_result.result:
                            if hasattr(item, 'content'):
                                capture.error_message = item.content
                    return capture

                # 2. Warten für async Requests
                await asyncio.sleep(wait_seconds)

                # 3. Console Messages holen (with timeout protection)
                try:
                    console_result = await asyncio.wait_for(
                        workbench.call_tool("browser_console_messages", {}),
                        timeout=self.MCP_TOOL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    console_result = None  # Continue without console messages
                if console_result and hasattr(console_result, 'result') and console_result.result:
                    for item in console_result.result:
                        if hasattr(item, 'content'):
                            lines = item.content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and line != "### Result":
                                    msg = ConsoleMessage.from_line(line)
                                    capture.console_messages.append(msg)

                                    # GENERIC: Treat ALL console ERROR messages as potential vite_errors
                                    # The BugFixerAgent with Claude will classify and fix them
                                    if msg.level == "ERROR":
                                        # Try pattern-based parser first (fast path)
                                        vite_err = ViteError.from_overlay_text(line)
                                        if vite_err:
                                            if vite_err not in capture.vite_errors:
                                                capture.vite_errors.append(vite_err)
                                            continue

                                        # Fall back to pattern-based classification
                                        classification = _pattern_classify_browser_error(line)
                                        error_type = classification.category if classification.confidence > 0 else "runtime_error"

                                        # Extract variable name for reference errors
                                        undefined_name = ""
                                        if error_type == "reference_error":
                                            match = re.search(r"(\w+)\s+is not defined", line, re.IGNORECASE)
                                            undefined_name = match.group(1) if match else ""

                                        # Create ViteError with classified type
                                        vite_err = ViteError(
                                            error_type=error_type,
                                            message=line[:500],
                                            missing_export=undefined_name,
                                        )
                                        if vite_err not in capture.vite_errors:
                                            capture.vite_errors.append(vite_err)

                # 4. Network Requests holen (with timeout protection)
                try:
                    network_result = await asyncio.wait_for(
                        workbench.call_tool("browser_network_requests", {}),
                        timeout=self.MCP_TOOL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    network_result = None  # Continue without network requests
                if network_result and hasattr(network_result, 'result') and network_result.result:
                    for item in network_result.result:
                        if hasattr(item, 'content'):
                            lines = item.content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and line != "### Result":
                                    req = NetworkRequest.from_line(line)
                                    if req:
                                        capture.network_requests.append(req)

                # 5. NEW: Check for Vite Error Overlay using browser_snapshot (with timeout)
                if check_vite_overlay:
                    try:
                        snapshot_result = await asyncio.wait_for(
                            workbench.call_tool("browser_snapshot", {}),
                            timeout=self.MCP_TOOL_TIMEOUT
                        )
                        if hasattr(snapshot_result, 'result') and snapshot_result.result:
                            for item in snapshot_result.result:
                                if hasattr(item, 'content'):
                                    snapshot_text = item.content

                                    # Look for Vite error patterns in the page content
                                    # Vite error overlay contains specific text patterns
                                    vite_errors = self._parse_vite_errors_from_snapshot(snapshot_text)
                                    for ve in vite_errors:
                                        if ve not in capture.vite_errors:
                                            capture.vite_errors.append(ve)
                    except (asyncio.TimeoutError, Exception):
                        pass  # Snapshot failed or timed out, continue without it

                # 6. Browser schließen (with timeout, but don't fail if it times out)
                try:
                    await asyncio.wait_for(
                        workbench.call_tool("browser_close", {}),
                        timeout=5.0  # Short timeout for close
                    )
                except asyncio.TimeoutError:
                    pass  # Browser close timed out, continue anyway

        except Exception:
            # Re-raise to be handled by the outer capture_console() method
            # which has proper timeout and error handling
            raise

        return capture

    def _parse_vite_errors_from_snapshot(self, snapshot_text: str) -> list[ViteError]:
        """
        Parse Vite error overlay content from a browser snapshot.

        Looks for common Vite/ESM error patterns in the page content.

        Args:
            snapshot_text: The accessibility tree or DOM snapshot

        Returns:
            List of detected ViteErrors
        """
        errors = []

        # Patterns that indicate Vite/ESM module errors
        error_indicators = [
            "does not provide an export named",
            "Failed to resolve module specifier",
            "Failed to load module script",
            "Uncaught SyntaxError",
            "Uncaught ReferenceError",  # e.g., "require is not defined"
            "Uncaught TypeError",
            "ReferenceError:",  # Without "Uncaught" prefix
            "TypeError:",
            "The requested module",
            "Failed to fetch dynamically imported module",
        ]

        # Check if any error indicator is present
        found_errors = False
        for indicator in error_indicators:
            if indicator.lower() in snapshot_text.lower():
                found_errors = True
                break

        if not found_errors:
            return errors

        # Extract the error message - look for full sentences containing the indicator
        import re

        # Pattern 1: "does not provide an export named 'X'"
        export_matches = re.findall(
            r"[^.]*does not provide an export named ['\"]([^'\"]+)['\"][^.]*",
            snapshot_text,
            re.IGNORECASE
        )
        for match in export_matches:
            # Find the full context around this match
            full_match = re.search(
                rf"([^.]*?['\"][^'\"]+['\"][^.]*does not provide an export named ['\"]({re.escape(match)})['\"][^.]*)",
                snapshot_text,
                re.IGNORECASE
            )
            file_path = ""
            if full_match:
                file_match = re.search(r"/@fs/([^'\"]+\.(?:ts|tsx|js|jsx))", full_match.group(1))
                if file_match:
                    file_path = file_match.group(1)

            errors.append(ViteError(
                error_type="missing_export",
                message=full_match.group(0) if full_match else f"Missing export: {match}",
                file_path=file_path,
                missing_export=match,
            ))

        # Pattern 2: Uncaught SyntaxError with module context
        syntax_matches = re.findall(
            r"Uncaught SyntaxError:[^.]+",
            snapshot_text,
            re.IGNORECASE
        )
        for match in syntax_matches:
            vite_err = ViteError.from_overlay_text(match)
            if vite_err:
                errors.append(vite_err)
            else:
                # Use pattern classifier as fallback
                classification = _pattern_classify_browser_error(match)
                error_type = classification.category if classification.confidence > 0 else "syntax_error"
                errors.append(ViteError(
                    error_type=error_type,
                    message=f"SyntaxError: {match[:500]}",
                ))

        # Pattern 3: Uncaught ReferenceError (e.g., "require is not defined")
        reference_matches = re.findall(
            r"(?:Uncaught )?ReferenceError:\s*([^\n]+)",
            snapshot_text,
            re.IGNORECASE
        )
        for match in reference_matches:
            undefined_match = re.search(r"(\w+)\s+is not defined", match)
            undefined_name = undefined_match.group(1) if undefined_match else ""
            errors.append(ViteError(
                error_type="reference_error",
                message=f"ReferenceError: {match}",
                missing_export=undefined_name,
            ))

        # Pattern 4: Uncaught TypeError
        type_matches = re.findall(
            r"(?:Uncaught )?TypeError:\s*([^\n]+)",
            snapshot_text,
            re.IGNORECASE
        )
        for match in type_matches:
            errors.append(ViteError(
                error_type="type_error",
                message=f"TypeError: {match}",
            ))

        return errors
    
    def discover_routes(self, app_dir: str | Path) -> list[str]:
        """
        Entdeckt alle Routes aus einem Next.js App Directory.
        
        Args:
            app_dir: Pfad zum app/ Verzeichnis
            
        Returns:
            Liste von Route-Pfaden (z.B. ["/", "/dashboard", "/settings"])
        """
        app_path = Path(app_dir)
        if not app_path.exists():
            return ["/"]
        
        routes = []
        
        # Suche nach page.tsx/page.js Dateien
        for item in app_path.rglob("page.tsx"):
            rel_path = item.parent.relative_to(app_path)
            route_parts = [p for p in str(rel_path).replace("\\", "/").split("/") if p and p != "."]
            
            # Filtere spezielle Next.js Verzeichnisse
            route_parts = [
                p for p in route_parts 
                if not p.startswith("(") and not p.startswith("_") and not p.startswith("[")
            ]
            
            if route_parts:
                route = "/" + "/".join(route_parts)
            else:
                route = "/"
            
            routes.append(route)
        
        # Auch page.js suchen
        for item in app_path.rglob("page.js"):
            rel_path = item.parent.relative_to(app_path)
            route_parts = [p for p in str(rel_path).replace("\\", "/").split("/") if p and p != "."]
            route_parts = [
                p for p in route_parts 
                if not p.startswith("(") and not p.startswith("_") and not p.startswith("[")
            ]
            
            if route_parts:
                route = "/" + "/".join(route_parts)
            else:
                route = "/"
            
            routes.append(route)
        
        # Deduplizieren und sortieren
        routes = sorted(set(routes))
        
        return routes if routes else ["/"]
    
    async def crawl_all_routes(
        self,
        base_url: str,
        app_dir: str | Path,
        wait_seconds: float = 3.0
    ) -> MultiRouteCapture:
        """
        Crawlt alle entdeckten Routes und erfasst Console-Daten.

        Args:
            base_url: Basis-URL (z.B. "http://localhost:3000")
            app_dir: Pfad zum app/ Verzeichnis
            wait_seconds: Wartezeit pro Route

        Returns:
            MultiRouteCapture mit allen erfassten Daten
        """
        routes = self.discover_routes(app_dir)

        multi_capture = MultiRouteCapture(
            base_url=base_url,
            routes_crawled=routes
        )

        # Calculate total timeout based on number of routes
        # Each route needs MCP_TOOL_TIMEOUT + wait_seconds, plus session startup
        total_timeout = self.MCP_SESSION_TIMEOUT + (len(routes) * (self.MCP_TOOL_TIMEOUT + wait_seconds + 5))

        try:
            multi_capture = await asyncio.wait_for(
                self._crawl_all_routes_impl(base_url, routes, wait_seconds),
                timeout=total_timeout
            )
        except asyncio.TimeoutError:
            import structlog
            _logger = structlog.get_logger(__name__)
            _logger.warning(
                "mcp_crawl_session_timeout",
                base_url=base_url,
                routes=len(routes),
                timeout=total_timeout
            )
        except Exception as e:
            import structlog
            _logger = structlog.get_logger(__name__)
            _logger.debug(
                "mcp_crawl_session_failed",
                base_url=base_url,
                error=str(e)[:100]
            )

        return multi_capture

    async def _crawl_all_routes_impl(
        self,
        base_url: str,
        routes: list[str],
        wait_seconds: float = 3.0
    ) -> MultiRouteCapture:
        """
        Internal implementation of crawl_all_routes.
        Called with a timeout wrapper from crawl_all_routes().
        """
        multi_capture = MultiRouteCapture(
            base_url=base_url,
            routes_crawled=routes
        )

        params = self._get_server_params()

        try:
            async with McpWorkbench(server_params=params) as workbench:
                for route in routes:
                    url = f"{base_url.rstrip('/')}{route}"
                    capture = ConsoleCapture(url=url)

                    # 1. Seite navigieren (with timeout protection)
                    try:
                        nav_result = await asyncio.wait_for(
                            workbench.call_tool("browser_navigate", {"url": url}),
                            timeout=self.MCP_TOOL_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        capture.navigation_ok = False
                        capture.error_message = f"Navigation timeout ({self.MCP_TOOL_TIMEOUT}s)"
                        multi_capture.captures[route] = capture
                        continue

                    # Navigation-Ergebnis prüfen
                    if hasattr(nav_result, 'is_error') and nav_result.is_error:
                        capture.navigation_ok = False
                        if hasattr(nav_result, 'result') and nav_result.result:
                            for item in nav_result.result:
                                if hasattr(item, 'content'):
                                    capture.error_message = item.content
                        multi_capture.captures[route] = capture
                        continue

                    # 2. Warten für async Requests
                    await asyncio.sleep(wait_seconds)

                    # 3. Console Messages holen (with timeout protection)
                    try:
                        console_result = await asyncio.wait_for(
                            workbench.call_tool("browser_console_messages", {}),
                            timeout=self.MCP_TOOL_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        console_result = None
                    if console_result and hasattr(console_result, 'result') and console_result.result:
                        for item in console_result.result:
                            if hasattr(item, 'content'):
                                lines = item.content.split('\n')
                                for line in lines:
                                    line = line.strip()
                                    if line and line != "### Result":
                                        msg = ConsoleMessage.from_line(line)
                                        capture.console_messages.append(msg)

                    # 4. Network Requests holen (with timeout protection)
                    try:
                        network_result = await asyncio.wait_for(
                            workbench.call_tool("browser_network_requests", {}),
                            timeout=self.MCP_TOOL_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        network_result = None
                    if network_result and hasattr(network_result, 'result') and network_result.result:
                        for item in network_result.result:
                            if hasattr(item, 'content'):
                                lines = item.content.split('\n')
                                for line in lines:
                                    line = line.strip()
                                    if line and line != "### Result":
                                        req = NetworkRequest.from_line(line)
                                        if req:
                                            capture.network_requests.append(req)

                    multi_capture.captures[route] = capture

                # Browser am Ende schließen (with timeout)
                try:
                    await asyncio.wait_for(
                        workbench.call_tool("browser_close", {}),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    pass
        except Exception:
            # Re-raise to be handled by the outer crawl_all_routes() method
            raise

        return multi_capture


# Alias für Abwärtskompatibilität
BrowserConsoleCaptureAgent = BrowserConsoleAgent