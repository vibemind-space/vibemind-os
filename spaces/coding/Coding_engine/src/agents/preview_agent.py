"""
Preview Agent - Deploys and manages live previews using Claude Code CLI.

This agent:
1. Uses Claude Code CLI to automate app deployment (npm build, npm run dev)
2. Manages live preview lifecycle with health checks
3. Is triggered by a 30-second timer for continuous monitoring
4. Integrates with EventBus for real-time status updates
5. Uses BrowserConsoleAgent for capturing browser console errors
"""

import asyncio
import os
import subprocess
import socket
import httpx
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Callable
import structlog

from src.tools.claude_code_tool import ClaudeCodeTool, CodeGenerationResult
from src.mind.event_bus import EventBus, Event, EventType
from src.autogen.cli_wrapper import ClaudeCLI


logger = structlog.get_logger(__name__)


# Lazy import for BrowserConsoleAgent to avoid circular dependencies
def _get_browser_console_agent():
    """Lazy import BrowserConsoleAgent."""
    try:
        from src.agents.browser_console_agent import (
            BrowserConsoleAgent, 
            ConsoleCapture,
            MultiRouteCapture,
        )
        return BrowserConsoleAgent, ConsoleCapture, MultiRouteCapture
    except ImportError:
        return None, None, None


class PreviewState(str, Enum):
    """Current state of the preview."""
    IDLE = "idle"
    INSTALLING = "installing"
    BUILDING = "building"
    STARTING = "starting"
    RUNNING = "running"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class PreviewStatus:
    """Status information for a preview deployment."""
    state: PreviewState = PreviewState.IDLE
    url: Optional[str] = None
    port: int = 3000
    pid: Optional[int] = None
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    health_check_count: int = 0
    consecutive_failures: int = 0
    error: Optional[str] = None
    build_output: str = ""
    
    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "url": self.url,
            "port": self.port,
            "pid": self.pid,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "health_check_count": self.health_check_count,
            "consecutive_failures": self.consecutive_failures,
            "error": self.error,
        }


class PreviewAgent:
    """
    Agent that uses Claude Code CLI to deploy and manage live previews.

    Features:
    - Automated npm install, build, and dev server management
    - 30-second timer for health checks
    - Claude Code CLI integration for intelligent error handling
    - BrowserConsoleAgent for capturing browser console errors
    - EventBus integration for real-time status updates
    """
    
    # Default timer interval in seconds
    DEFAULT_TIMER_INTERVAL = 30.0
    
    # Max consecutive failures before attempting recovery
    MAX_CONSECUTIVE_FAILURES = 3
    
    def __init__(
        self,
        working_dir: str,
        event_bus: Optional[EventBus] = None,
        port: int = 3000,
        timer_interval: float = DEFAULT_TIMER_INTERVAL,
        auto_start_timer: bool = True,
        enable_console_capture: bool = True,
    ):
        self.working_dir = Path(working_dir)
        self.event_bus = event_bus or EventBus()
        self.port = port
        self.timer_interval = timer_interval
        self.auto_start_timer = auto_start_timer
        self.enable_console_capture = enable_console_capture
        
        # Status tracking
        self.status = PreviewStatus(port=port)
        
        # Process management
        self._dev_process: Optional[subprocess.Popen] = None
        
        # Timer task
        self._timer_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Claude Code Tool for intelligent operations
        self.claude_tool = ClaudeCodeTool(working_dir=str(self.working_dir))
        self.claude_cli = ClaudeCLI(working_dir=str(self.working_dir))
        
        # Browser Console Agent for error capture
        self._browser_console_agent = None
        self._last_console_capture = None
        
        self.logger = logger.bind(
            component="preview_agent",
            working_dir=str(working_dir),
            port=port,
        )
    
    async def start(self) -> bool:
        """
        Start the preview agent and deploy the app.

        Returns:
            True if deployment succeeded
        """
        self.logger.info("preview_agent_starting")
        self._running = True
        
        try:
            # Step 1: Install dependencies
            if not await self._install_dependencies():
                return False
            
            # Step 2: Build the project
            if not await self._build_project():
                return False
            
            # Step 3: Start dev server
            if not await self._start_dev_server():
                return False
            
            # Step 4: Wait for server to be ready
            if not await self._wait_for_server():
                self.logger.warning("server_startup_timeout")
                # Don't fail, server might still come up
            
            # Step 5: Start the 30-second timer
            if self.auto_start_timer:
                self._start_timer()
            
            # Publish preview ready event
            await self._publish_event(EventType.PREVIEW_READY, {
                "url": self.status.url,
                "port": self.port,
            })
            
            self.logger.info("preview_agent_started", url=self.status.url)
            return True
            
        except Exception as e:
            self.status.state = PreviewState.ERROR
            self.status.error = str(e)
            self.logger.error("preview_agent_start_failed", error=str(e))
            
            await self._publish_event(EventType.DEPLOY_FAILED, {
                "error": str(e),
            })
            
            return False

    async def stop(self) -> None:
        """Stop the preview agent and dev server."""
        self.logger.info("preview_agent_stopping")
        self._running = False
        
        # Stop timer
        if self._timer_task:
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
            self._timer_task = None
        
        # Stop dev server
        await self._stop_dev_server()
        
        self.status.state = PreviewState.STOPPED
        self.logger.info("preview_agent_stopped")
    
    async def _install_dependencies(self) -> bool:
        """Install npm dependencies using Claude Code CLI."""
        self.status.state = PreviewState.INSTALLING
        self.logger.info("installing_dependencies")
        
        await self._publish_event(EventType.DEPLOY_STARTED, {
            "phase": "install",
        })
        
        try:
            # First try simple npm install
            result = await self._run_command(["npm", "install"])
            
            if not result["success"]:
                # Use Claude Code CLI to diagnose and fix
                self.logger.warning("npm_install_failed_using_claude")
                
                fix_result = await self.claude_cli.execute(
                    f"""Die npm install ist fehlgeschlagen. Analysiere den Fehler und behebe ihn:

Fehlerausgabe:
{result.get('output', 'Keine Ausgabe')}

Stderr:
{result.get('stderr', 'Kein stderr')}

Bitte:
1. Analysiere was schief gelaufen ist
2. Behebe das Problem (z.B. durch Bearbeiten von package.json)
3. Führe npm install erneut aus
4. Stelle sicher, dass alle Dependencies installiert sind"""
                )
                
                if not fix_result.success:
                    self.status.error = f"Failed to install dependencies: {fix_result.error}"
                    return False
            
            self.logger.info("dependencies_installed")
            return True
            
        except Exception as e:
            self.status.error = f"Install error: {str(e)}"
            self.logger.error("install_error", error=str(e))
            return False
    
    async def _build_project(self) -> bool:
        """Build the project using npm run build."""
        self.status.state = PreviewState.BUILDING
        self.logger.info("building_project")
        
        await self._publish_event(EventType.BUILD_STARTED, {
            "phase": "build",
        })
        
        try:
            # Check if build script exists
            package_json = self.working_dir / "package.json"
            if package_json.exists():
                import json
                with open(package_json) as f:
                    pkg = json.load(f)
                
                if "build" not in pkg.get("scripts", {}):
                    self.logger.info("no_build_script_skipping")
                    return True
            
            # Run npm build
            result = await self._run_command(["npm", "run", "build"])
            self.status.build_output = result.get("output", "")
            
            if not result["success"]:
                # Use Claude Code CLI to fix build errors
                self.logger.warning("build_failed_using_claude")
                
                fix_result = await self.claude_cli.execute(
                    f"""Der Build ist fehlgeschlagen. Analysiere den Fehler und behebe ihn:

Build-Ausgabe:
{result.get('output', 'Keine Ausgabe')}

Stderr:
{result.get('stderr', 'Kein stderr')}

Bitte:
1. Analysiere die Build-Fehler
2. Finde und behebe die Ursache im Code
3. Führe npm run build erneut aus
4. Stelle sicher, dass der Build erfolgreich ist"""
                )
                
                if not fix_result.success:
                    # One more attempt with broader fix
                    self.logger.info("attempting_comprehensive_build_fix")
                    
                    # Let Claude handle it comprehensively
                    comprehensive_fix = await self.claude_cli.execute(
                        """Der Build ist mehrfach fehlgeschlagen. Bitte führe eine umfassende Analyse durch:

1. Prüfe alle TypeScript/JavaScript Dateien auf Syntaxfehler
2. Prüfe imports und exports
3. Prüfe ob alle benötigten Pakete in package.json sind
4. Behebe alle gefundenen Probleme
5. Führe npm run build aus

Wenn der Build dann noch fehlschlägt, entferne problematische Features und stelle einen minimalen funktionierenden Build her."""
                    )
                    
                    if not comprehensive_fix.success:
                        self.status.error = f"Build failed after fix attempts"
                        await self._publish_event(EventType.BUILD_FAILED, {
                            "error": self.status.build_output,
                        })
                        return False
            
            await self._publish_event(EventType.BUILD_COMPLETED, {
                "success": True,
            })
            
            self.logger.info("build_completed")
            return True
            
        except Exception as e:
            self.status.error = f"Build error: {str(e)}"
            self.logger.error("build_error", error=str(e))
            await self._publish_event(EventType.BUILD_FAILED, {
                "error": str(e),
            })
            return False
    
    async def _start_dev_server(self) -> bool:
        """Start the development server."""
        self.status.state = PreviewState.STARTING
        self.logger.info("starting_dev_server")
        
        try:
            # Detect dev command
            dev_cmd = await self._detect_dev_command()
            if not dev_cmd:
                # Use Claude to create a dev script
                self.logger.info("no_dev_command_asking_claude")
                
                setup_result = await self.claude_cli.execute(
                    """Es gibt keinen 'dev' oder 'start' script in package.json.

Bitte:
1. Analysiere das Projekt und füge einen passenden dev script hinzu
2. Für React/Vite: "dev": "vite"
3. Für Next.js: "dev": "next dev"  
4. Für Create React App: "start": "react-scripts start"
5. Für einfaches HTML: "dev": "npx serve -s . -l 3000"

Füge den passenden script zu package.json hinzu."""
                )
                
                dev_cmd = await self._detect_dev_command()
                if not dev_cmd:
                    dev_cmd = ["npm", "run", "dev"]  # Try anyway
            
            # Find available port
            self.port = await self._find_available_port(self.port)
            self.status.port = self.port
            self.status.url = f"http://localhost:{self.port}"
            
            # Set environment for port
            env = os.environ.copy()
            env["PORT"] = str(self.port)
            env["VITE_PORT"] = str(self.port)
            
            # Start the process
            use_shell = os.name == 'nt'  # Windows needs shell=True for npm
            
            self._dev_process = subprocess.Popen(
                dev_cmd,
                cwd=str(self.working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=use_shell,
                env=env,
            )
            
            self.status.pid = self._dev_process.pid
            self.status.started_at = datetime.now()
            self.status.state = PreviewState.RUNNING
            
            self.logger.info(
                "dev_server_started",
                command=" ".join(dev_cmd),
                pid=self._dev_process.pid,
                port=self.port,
            )
            
            return True
            
        except Exception as e:
            self.status.error = f"Dev server start error: {str(e)}"
            self.status.state = PreviewState.ERROR
            self.logger.error("dev_server_start_error", error=str(e))
            return False
    
    async def _stop_dev_server(self) -> None:
        """Stop the development server."""
        if not self._dev_process:
            return
        
        try:
            if os.name == 'nt':
                # Windows: use taskkill for process tree
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(self._dev_process.pid)],
                    capture_output=True,
                )
            else:
                # Unix: terminate
                self._dev_process.terminate()
                await asyncio.sleep(2)
                if self._dev_process.poll() is None:
                    self._dev_process.kill()
            
            self._dev_process = None
            self.status.pid = None
            self.logger.info("dev_server_stopped")
            
        except Exception as e:
            self.logger.error("dev_server_stop_error", error=str(e))
    
    async def _wait_for_server(self, timeout: float = 60.0) -> bool:
        """Wait for the server to be ready."""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            if await self._check_health():
                self.status.state = PreviewState.HEALTHY
                return True
            
            # Check if process crashed
            if self._dev_process and self._dev_process.poll() is not None:
                self.logger.error("dev_server_crashed")
                return False
            
            await asyncio.sleep(2)
        
        return False
    
    async def _check_health(self) -> bool:
        """Check if the server is healthy."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:{self.port}",
                    timeout=5.0,
                    follow_redirects=True,
                )
                
                self.status.last_health_check = datetime.now()
                self.status.health_check_count += 1
                
                if response.status_code < 500:
                    self.status.consecutive_failures = 0
                    self.status.state = PreviewState.HEALTHY
                    return True
                else:
                    self.status.consecutive_failures += 1
                    self.status.state = PreviewState.UNHEALTHY
                    return False
                    
        except Exception as e:
            self.status.consecutive_failures += 1
            self.status.state = PreviewState.UNHEALTHY
            self.logger.debug("health_check_failed", error=str(e))
            return False
    
    async def _handle_health_failure(self) -> None:
        """Handle repeated health check failures using Claude Code CLI and BrowserConsoleAgent."""
        self.logger.warning(
            "handling_health_failure",
            consecutive_failures=self.status.consecutive_failures,
        )
        
        # Collect server output for diagnosis
        server_output = ""
        if self._dev_process and self._dev_process.stdout:
            try:
                # Non-blocking read
                import select
                if os.name != 'nt':
                    ready, _, _ = select.select([self._dev_process.stdout], [], [], 0)
                    if ready:
                        server_output = self._dev_process.stdout.read(8192).decode('utf-8', errors='replace')
            except Exception:
                pass
        
        # Capture browser console errors if enabled
        console_context = ""
        if self.enable_console_capture:
            self.logger.info(
                "console_capture_starting",
                url=f"http://127.0.0.1:{self.port}",
            )
            console_capture = await self._capture_console_errors()
            
            if console_capture:
                # Check for issues
                has_issues = (
                    len(console_capture.errors) > 0 or 
                    len(console_capture.warnings) > 0 or 
                    len(console_capture.failed_requests) > 0
                )
                
                if has_issues:
                    console_context = console_capture.format_for_claude()
                    self._last_console_capture = console_capture
                    
                    self.logger.info(
                        "console_capture_completed",
                        errors=len(console_capture.errors),
                        warnings=len(console_capture.warnings),
                        failed_requests=len(console_capture.failed_requests),
                    )
                    
                    # Publish console errors event
                    await self._publish_event(EventType.VALIDATION_FAILED, {
                        "type": "console_errors",
                        "errors": len(console_capture.errors),
                        "warnings": len(console_capture.warnings),
                        "failed_requests": len(console_capture.failed_requests),
                        "details": [
                            {"level": e.level, "message": e.message[:200]} 
                            for e in console_capture.errors[:10]
                        ],
                    })
                else:
                    self.logger.info(
                        "console_capture_no_issues",
                        url=console_capture.url,
                    )
            else:
                self.logger.warning("console_capture_failed_null_result")
        else:
            self.logger.info("console_capture_disabled")
        
        # Build comprehensive prompt for Claude with console errors
        prompt_parts = [
            f"Der Dev Server ist nicht mehr erreichbar nach {self.status.consecutive_failures} fehlgeschlagenen Health-Checks.",
            "",
            f"Server URL: http://127.0.0.1:{self.port}",
            f"Server PID: {self.status.pid}",
        ]
        
        if server_output:
            prompt_parts.extend([
                "",
                "## Server Output",
                server_output,
            ])
        
        if console_context:
            prompt_parts.extend([
                "",
                "## Browser Console Errors (via Playwright MCP)",
                console_context,
            ])
        
        prompt_parts.extend([
            "",
            "## Anweisungen",
            "1. Analysiere warum der Server nicht antwortet",
            "2. Prüfe ob es Port-Konflikte gibt",
            "3. WICHTIG: Behebe die Browser Console Errors - das sind die eigentlichen Bugs!",
            "4. Häufige Fehler:",
            "   - Hydration Errors: Server/Client HTML Mismatch",
            "   - 404 API Calls: Backend fehlt oder falscher Endpoint",
            "   - WebSocket Errors: Backend WebSocket Server fehlt",
            "   - Import Errors: Fehlende Dependencies",
            "5. Behebe die Ursache im Source Code",
            "6. Starte den Server neu mit: npm run dev",
        ])
        
        diagnosis_prompt = "\n".join(prompt_parts)
        
        # Use Claude to diagnose and fix
        diagnosis_result = await self.claude_cli.execute(diagnosis_prompt)
        
        if diagnosis_result.success:
            # Restart the server
            await self._stop_dev_server()
            await asyncio.sleep(2)
            await self._start_dev_server()
            self.status.consecutive_failures = 0
            
            # Verify fix with another console capture
            if self.enable_console_capture:
                await asyncio.sleep(5)  # Wait for server to stabilize
                verify_capture = await self._capture_console_errors()
                if verify_capture:
                    before_errors = len(self._last_console_capture.errors) if self._last_console_capture else 0
                    after_errors = len(verify_capture.errors)
                    self.logger.info(
                        "post_fix_verification",
                        errors_before=before_errors,
                        errors_after=after_errors,
                    )
    
    async def _capture_console_errors(self):
        """Capture browser console errors using BrowserConsoleAgent with multi-route crawling."""
        BrowserConsoleAgent, ConsoleCapture, MultiRouteCapture = _get_browser_console_agent()
        
        if not BrowserConsoleAgent:
            self.logger.warning("browser_console_agent_not_available", reason="import_failed")
            return None
        
        try:
            if not self._browser_console_agent:
                self.logger.info("creating_browser_console_agent")
                self._browser_console_agent = BrowserConsoleAgent(browser="chrome")
            
            base_url = f"http://127.0.0.1:{self.port}"
            
            # Check if app/ directory exists for multi-route crawling
            app_dir = self.working_dir / "app"
            
            if app_dir.exists():
                # Use multi-route crawling
                self.logger.info(
                    "crawling_all_routes", 
                    base_url=base_url,
                    app_dir=str(app_dir),
                )
                
                multi_capture = await self._browser_console_agent.crawl_all_routes(
                    base_url=base_url,
                    app_dir=app_dir,
                    wait_seconds=5.0,
                )
                
                self.logger.info(
                    "multi_route_crawl_complete",
                    routes_crawled=len(multi_capture.routes_crawled),
                    total_errors=multi_capture.total_errors,
                    total_warnings=multi_capture.total_warnings,
                    total_failed_requests=multi_capture.total_failed_requests,
                )
                
                # Check if there are any issues
                has_issues = (
                    multi_capture.total_errors > 0 or 
                    multi_capture.total_warnings > 0 or 
                    multi_capture.total_failed_requests > 0
                )
                
                if has_issues:
                    self.logger.warning(
                        "console_errors_detected",
                        routes_with_errors=[
                            r for r, c in multi_capture.captures.items() 
                            if c.errors or c.warnings or c.failed_requests
                        ],
                        errors=multi_capture.total_errors,
                        warnings=multi_capture.total_warnings,
                        failed_requests=multi_capture.total_failed_requests,
                    )
                else:
                    self.logger.info("console_capture_clean_all_routes")
                
                # Return aggregated ConsoleCapture
                return multi_capture.to_console_capture()
            else:
                # Fallback to single URL capture
                self.logger.info("single_url_capture", url=base_url)
                
                capture = await self._browser_console_agent.capture_console(
                    url=base_url,
                    wait_seconds=5.0,
                )
                
                # Check if there are any issues
                has_issues = len(capture.errors) > 0 or len(capture.warnings) > 0 or len(capture.failed_requests) > 0
                
                if has_issues:
                    self.logger.warning(
                        "console_errors_detected",
                        errors=len(capture.errors),
                        warnings=len(capture.warnings),
                        failed_requests=len(capture.failed_requests),
                        first_error=capture.errors[0].message[:100] if capture.errors else None,
                    )
                else:
                    self.logger.info("console_capture_clean", url=base_url)
                
                return capture
            
        except Exception as e:
            self.logger.error("console_capture_failed", error=str(e), error_type=type(e).__name__)
            import traceback
            self.logger.debug("console_capture_traceback", traceback=traceback.format_exc())
            return None
    
    def get_last_console_capture(self):
        """Get the last console capture result."""
        return self._last_console_capture
    
    def _start_timer(self) -> None:
        """Start the 30-second health check timer."""
        if self._timer_task:
            return
        
        self._timer_task = asyncio.create_task(self._timer_loop())
        self.logger.info("health_check_timer_started", interval=self.timer_interval)
    
    async def _timer_loop(self) -> None:
        """Main timer loop - runs health checks every 30 seconds."""
        while self._running:
            await asyncio.sleep(self.timer_interval)
            
            if not self._running:
                break
            
            # Perform health check
            is_healthy = await self._check_health()
            
            self.logger.debug(
                "timer_health_check",
                healthy=is_healthy,
                check_count=self.status.health_check_count,
            )
            
            # Publish status event
            await self._publish_event(EventType.CONVERGENCE_UPDATE, {
                "preview_status": self.status.to_dict(),
            })
            
            # Handle failures
            if self.status.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                self.logger.warning("max_failures_reached_attempting_recovery")
                await self._handle_health_failure()
    
    async def _detect_dev_command(self) -> Optional[list[str]]:
        """Detect the appropriate dev command from package.json."""
        package_json = self.working_dir / "package.json"
        if not package_json.exists():
            return None
        
        try:
            import json
            with open(package_json) as f:
                pkg = json.load(f)
            
            scripts = pkg.get("scripts", {})
            
            # Priority order
            for cmd in ["dev", "start", "serve", "develop"]:
                if cmd in scripts:
                    return ["npm", "run", cmd]
            
            return None
            
        except Exception as e:
            self.logger.warning("package_json_parse_error", error=str(e))
            return None
    
    async def _find_available_port(self, start_port: int) -> int:
        """Find an available port starting from start_port."""
        port = start_port
        max_attempts = 100
        
        for _ in range(max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    return port
            except OSError:
                port += 1
        
        return start_port  # Fallback
    
    async def _run_command(self, cmd: list[str]) -> dict:
        """Run a shell command and return result."""
        try:
            use_shell = os.name == 'nt'
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=use_shell if isinstance(cmd, str) else False,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300,  # 5 minute timeout
            )
            
            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "output": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Command timed out",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def _publish_event(self, event_type: EventType, data: dict) -> None:
        """Publish an event to the EventBus."""
        event = Event(
            type=event_type,
            source="preview_agent",
            data=data,
        )
        await self.event_bus.publish(event)
    
    def get_status(self) -> dict:
        """Get current preview status."""
        return self.status.to_dict()
    
    async def deploy_with_claude(self, instructions: Optional[str] = None) -> bool:
        """
        Use Claude Code CLI to deploy the app with custom instructions.
        
        This is the main method that uses Claude Code as a tool for deployment.
        
        Args:
            instructions: Optional custom deployment instructions
            
        Returns:
            True if deployment succeeded
        """
        self.logger.info("deploying_with_claude", instructions=instructions[:100] if instructions else None)
        
        default_instructions = """Deploye diese App für eine Live-Preview:

1. Installiere alle Dependencies mit npm install
2. Führe npm run build aus (falls vorhanden)
3. Starte den Dev Server mit npm run dev oder npm start
4. Stelle sicher dass der Server auf einem freien Port läuft
5. Gib die URL und den Port zurück

Bei Fehlern:
- Analysiere die Fehlermeldung
- Behebe das Problem im Code
- Versuche es erneut

Das Ziel ist eine funktionierende Live-Preview der App."""
        
        prompt = instructions or default_instructions
        
        result = await self.claude_cli.execute(prompt)
        
        if result.success:
            self.logger.info("claude_deployment_completed")
            
            # Start the timer for health checks
            if not self._timer_task and self.auto_start_timer:
                self._start_timer()
            
            return True
        else:
            self.logger.error("claude_deployment_failed", error=result.error)
            return False


# Convenience function
async def create_preview_agent(
    working_dir: str,
    event_bus: Optional[EventBus] = None,
    port: int = 3000,
    auto_deploy: bool = True,
    enable_console_capture: bool = True,
) -> PreviewAgent:
    """
    Create and optionally start a preview agent.
    
    Args:
        working_dir: Project directory
        event_bus: Optional event bus
        port: Dev server port
        auto_deploy: Start deployment immediately
        enable_console_capture: Enable browser console error capture
        
    Returns:
        PreviewAgent instance
    """
    agent = PreviewAgent(
        working_dir=working_dir,
        event_bus=event_bus,
        port=port,
        enable_console_capture=enable_console_capture,
    )
    
    if auto_deploy:
        await agent.start()
    
    return agent