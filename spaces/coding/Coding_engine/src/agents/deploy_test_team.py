"""
Deploy Test Team - Orchestriert Deployment und Testing aller Services.

Koordiniert:
1. EntrypointDetector - Erkennt automatisch wie das Projekt gestartet wird
2. ParallelRunner - Startet Frontend + Backend parallel
3. BrowserConsoleAgent - Testet alle Routes via Playwright
4. FixDispatcher - Sammelt Errors und dispatcht Fixes via Claude CLI
5. Writes TestSpec documents to DocumentRegistry for reports/tests/
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any
import structlog
import uuid

from src.agents.entrypoint_detector import EntrypointDetector, ProjectConfig
from src.agents.parallel_runner import ParallelRunner, RunnerResult
from src.agents.browser_console_agent import BrowserConsoleAgent, MultiRouteCapture
from src.autogen.cli_wrapper import ClaudeCLI
from src.registry.document_registry import DocumentRegistry
from src.registry.documents import TestSpec, TestCase, TestResults
from src.registry.document_types import DocumentStatus

logger = structlog.get_logger(__name__)


@dataclass
class TeamResult:
    """Ergebnis des gesamten Deploy & Test Zyklus."""
    success: bool
    
    # Detection
    project_config: Optional[ProjectConfig] = None
    detected_stack: str = "unknown"
    
    # Services
    frontend_running: bool = False
    backend_running: bool = False
    frontend_port: int = 0
    backend_port: int = 0
    
    # Testing
    routes_tested: list[str] = field(default_factory=list)
    console_errors: int = 0
    console_warnings: int = 0
    network_errors: int = 0
    backend_errors: int = 0
    
    # Fixes
    fixes_attempted: int = 0
    fixes_successful: int = 0
    
    # All Errors
    all_errors: list[str] = field(default_factory=list)
    
    # Timing
    execution_time_ms: int = 0
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "detected_stack": self.detected_stack,
            "frontend_running": self.frontend_running,
            "backend_running": self.backend_running,
            "frontend_port": self.frontend_port,
            "backend_port": self.backend_port,
            "routes_tested": self.routes_tested,
            "console_errors": self.console_errors,
            "console_warnings": self.console_warnings,
            "network_errors": self.network_errors,
            "backend_errors": self.backend_errors,
            "fixes_attempted": self.fixes_attempted,
            "fixes_successful": self.fixes_successful,
            "all_errors": self.all_errors[:20],
            "execution_time_ms": self.execution_time_ms,
        }


class DeployTestTeam:
    """
    Orchestriert den gesamten Deploy & Test Workflow.
    
    Workflow:
    1. EntrypointDetector analysiert Projekt via Claude CLI
    2. ParallelRunner startet Frontend + Backend
    3. BrowserConsoleAgent testet alle Routes
    4. Bei Errors: FixDispatcher ruft Claude CLI für Fixes
    5. Retry bis success oder max_iterations erreicht
    6. Writes TestSpec to DocumentRegistry
    """
    
    def __init__(
        self,
        working_dir: str,
        max_fix_iterations: int = 3,
        startup_timeout: float = 60.0,
        browser: str = "chrome",
        on_progress: Optional[Callable[[str, dict], None]] = None,
    ):
        self.working_dir = Path(working_dir)
        self.max_fix_iterations = max_fix_iterations
        self.startup_timeout = startup_timeout
        self.browser = browser
        self.on_progress = on_progress
        
        # Components (lazy initialized)
        self._detector: Optional[EntrypointDetector] = None
        self._runner: Optional[ParallelRunner] = None
        self._browser_agent: Optional[BrowserConsoleAgent] = None
        self._claude_cli: Optional[ClaudeCLI] = None
        
        # State
        self._config: Optional[ProjectConfig] = None
        
        # DocumentRegistry for writing TestSpecs
        self._doc_registry = DocumentRegistry(str(working_dir))
        
        self.logger = logger.bind(
            component="deploy_test_team",
            working_dir=str(working_dir),
        )
    
    async def _write_test_spec(
        self,
        result: 'TeamResult',
        iteration: int,
    ) -> None:
        """
        Write a TestSpec document to the DocumentRegistry.
        
        Args:
            result: Current TeamResult with test data
            iteration: Current test iteration number
        """
        try:
            import time
            start_time = time.time()
            
            # Build test cases from routes tested
            test_cases = []
            for i, route in enumerate(result.routes_tested):
                test_cases.append(TestCase(
                    id=f"route_{i+1}",
                    name=f"Route Test: {route}",
                    description=f"Browser console test for route {route}",
                    test_type="e2e",
                    priority=1 if route == "/" else 2,
                    steps=[
                        f"Navigate to {route}",
                        "Wait for page load",
                        "Capture console logs",
                        "Capture network requests",
                    ],
                    expected_result="No console errors or failed network requests",
                    target_element=route,
                ))
            
            # Build test results
            total_tests = len(result.routes_tested)
            passed_tests = total_tests - (1 if result.console_errors > 0 or result.network_errors > 0 else 0)
            failed_tests = 1 if result.console_errors > 0 or result.network_errors > 0 else 0
            
            # Build failures list
            failures = []
            if result.console_errors > 0:
                failures.append({
                    "type": "console_error",
                    "count": result.console_errors,
                    "samples": result.all_errors[:5],
                })
            if result.network_errors > 0:
                failures.append({
                    "type": "network_error",
                    "count": result.network_errors,
                    "samples": [e for e in result.all_errors if "[Network]" in e][:5],
                })
            if result.backend_errors > 0:
                failures.append({
                    "type": "backend_error",
                    "count": result.backend_errors,
                    "samples": [e for e in result.all_errors if "[Backend]" in e][:5],
                })
            
            test_results = TestResults(
                total=total_tests,
                passed=passed_tests,
                failed=failed_tests,
                skipped=0,
                duration_seconds=result.execution_time_ms / 1000.0,
                failures=failures,
            )
            
            # Create TestSpec document
            spec = TestSpec(
                id=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
                timestamp=datetime.now(),
                source_agent="DeployTestTeam",
                status=DocumentStatus.PENDING if not result.success else DocumentStatus.CONSUMED,
                responding_to=None,  # Could link to ImplementationPlan if available
                test_cases=test_cases,
                coverage_targets=[
                    f"Routes: {len(result.routes_tested)}",
                    f"Stack: {result.detected_stack}",
                    f"Frontend: {'✓' if result.frontend_running else '✗'}",
                    f"Backend: {'✓' if result.backend_running else '✗'}",
                ],
                results=test_results,
                executed_at=datetime.now(),
            )
            
            # Write to registry
            await self._doc_registry.write_document(spec, priority=2)
            
            self.logger.info(
                "test_spec_written",
                spec_id=spec.id,
                routes_tested=len(result.routes_tested),
                console_errors=result.console_errors,
                success=result.success,
            )
            
        except Exception as e:
            self.logger.warning("failed_to_write_test_spec", error=str(e))

    async def run(self) -> TeamResult:
        """
        Führt den kompletten Deploy & Test Zyklus durch.
        
        Returns:
            TeamResult mit allen Ergebnissen
        """
        import time
        start_time = time.time()
        
        result = TeamResult(success=False)
        iteration_count = 0
        
        try:
            # Phase 1: Detection
            self._report_progress("detection", {"status": "starting"})
            
            self._detector = EntrypointDetector(str(self.working_dir))
            self._config = await self._detector.detect()
            
            result.project_config = self._config
            result.detected_stack = self._config.detected_stack
            
            self._report_progress("detection", {
                "status": "complete",
                "stack": self._config.detected_stack,
                "has_frontend": self._config.frontend is not None,
                "has_backend": self._config.backend is not None,
            })
            
            self.logger.info(
                "detection_complete",
                stack=self._config.detected_stack,
                routes=len(self._config.routes),
            )
            
            # Phase 2: Start Services
            self._report_progress("services", {"status": "starting"})
            
            self._runner = ParallelRunner(
                str(self.working_dir),
                self._config,
                startup_timeout=self.startup_timeout,
                on_log=self._handle_log,
            )
            
            runner_result = await self._runner.start()
            
            if runner_result.frontend:
                result.frontend_running = runner_result.frontend.running
                result.frontend_port = runner_result.frontend.port
            
            if runner_result.backend:
                result.backend_running = runner_result.backend.running
                result.backend_port = runner_result.backend.port
            
            if not runner_result.success:
                result.all_errors.extend(runner_result.all_errors)
                self.logger.warning("services_start_failed")
                
                # Trotzdem versuchen weiterzumachen wenn mindestens ein Service läuft
                if not result.frontend_running and not result.backend_running:
                    self._report_progress("services", {
                        "status": "failed",
                        "errors": runner_result.all_errors[:5],
                    })
                    return result
            
            self._report_progress("services", {
                "status": "running",
                "frontend_port": result.frontend_port,
                "backend_port": result.backend_port,
            })
            
            # Phase 3: Browser Testing Loop
            for iteration in range(self.max_fix_iterations + 1):
                iteration_count = iteration
                is_retry = iteration > 0
                
                self._report_progress("testing", {
                    "status": "running",
                    "iteration": iteration + 1,
                    "is_retry": is_retry,
                })
                
                # Browser Tests durchführen
                test_errors = await self._run_browser_tests(result)
                
                # Backend Logs prüfen
                backend_errors = await self._runner.get_errors()
                result.backend_errors = len([e for e in backend_errors if "[Backend]" in e])
                result.all_errors.extend(backend_errors)
                
                # Gesamtfehler zählen
                total_errors = (
                    result.console_errors + 
                    result.network_errors + 
                    result.backend_errors
                )
                
                self.logger.info(
                    "test_iteration_complete",
                    iteration=iteration + 1,
                    console_errors=result.console_errors,
                    network_errors=result.network_errors,
                    backend_errors=result.backend_errors,
                    total_errors=total_errors,
                )
                
                # Erfolg?
                if total_errors == 0:
                    result.success = True
                    self._report_progress("testing", {
                        "status": "success",
                        "routes_tested": result.routes_tested,
                    })
                    break
                
                # Max Iterations erreicht?
                if iteration >= self.max_fix_iterations:
                    self._report_progress("testing", {
                        "status": "failed",
                        "errors": result.all_errors[:10],
                    })
                    break
                
                # Phase 4: Fix Attempt
                self._report_progress("fixing", {
                    "status": "running",
                    "iteration": iteration + 1,
                })
                
                result.fixes_attempted += 1
                
                fix_success = await self._attempt_fix(test_errors, backend_errors)
                
                if fix_success:
                    result.fixes_successful += 1
                    self._report_progress("fixing", {"status": "applied"})
                    
                    # Warten auf HMR / Server Reload
                    await asyncio.sleep(3)
                else:
                    self._report_progress("fixing", {"status": "failed"})
            
        except Exception as e:
            self.logger.error("team_run_failed", error=str(e))
            result.all_errors.append(str(e))
        
        finally:
            # Cleanup
            if self._runner:
                await self._runner.stop()
            
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Write TestSpec to DocumentRegistry
            await self._write_test_spec(result, iteration_count)
        
        self._report_progress("complete", {
            "success": result.success,
            "execution_time_ms": result.execution_time_ms,
        })
        
        return result
    
    async def _run_browser_tests(self, result: TeamResult) -> list[str]:
        """Führt Browser Tests durch und aktualisiert Result."""
        test_errors = []
        
        # Frontend URL
        frontend_url = None
        if result.frontend_running and result.frontend_port:
            frontend_url = f"http://localhost:{result.frontend_port}"
        
        if not frontend_url:
            self.logger.warning("no_frontend_url")
            return test_errors
        
        try:
            self._browser_agent = BrowserConsoleAgent(browser=self.browser)
            
            # Routes aus Config oder Discovery
            routes = self._config.routes if self._config else ["/"]
            
            # Multi-Route Test
            if len(routes) > 1:
                # Crawl alle Routes
                for route in routes:
                    url = f"{frontend_url}{route}"
                    try:
                        capture = await self._browser_agent.capture_console(
                            url=url,
                            wait_seconds=3.0,
                        )
                        
                        result.routes_tested.append(route)
                        result.console_errors += len(capture.errors)
                        result.console_warnings += len(capture.warnings)
                        result.network_errors += len(capture.failed_requests)
                        
                        # Errors sammeln
                        for error in capture.errors:
                            test_errors.append(f"[Console] {route}: {getattr(error, 'text', str(error))}")
                        
                        for req in capture.failed_requests:
                            test_errors.append(f"[Network] {route}: {getattr(req, 'url', '')} - {getattr(req, 'failure', None) or 'failed'}")
                        
                    except Exception as e:
                        self.logger.warning("route_test_failed", route=route, error=str(e))
            else:
                # Single Page Test
                capture = await self._browser_agent.capture_console(
                    url=frontend_url,
                    wait_seconds=5.0,
                )
                
                result.routes_tested = ["/"]
                result.console_errors = len(capture.errors)
                result.console_warnings = len(capture.warnings)
                result.network_errors = len(capture.failed_requests)
                
                for error in capture.errors:
                    test_errors.append(f"[Console] /: {getattr(error, 'text', str(error))}")
                
                for req in capture.failed_requests:
                    test_errors.append(f"[Network] /: {getattr(req, 'url', '')} - {getattr(req, 'failure', None) or 'failed'}")
            
        except Exception as e:
            self.logger.error("browser_tests_failed", error=str(e))
            test_errors.append(f"Browser test error: {str(e)}")
        
        result.all_errors.extend(test_errors)
        return test_errors
    
    async def _attempt_fix(
        self,
        browser_errors: list[str],
        backend_errors: list[str],
    ) -> bool:
        """Versucht Fehler via Claude CLI zu fixen."""
        if not browser_errors and not backend_errors:
            return False
        
        # Claude CLI initialisieren
        if not self._claude_cli:
            self._claude_cli = ClaudeCLI(
                working_dir=str(self.working_dir),
                agent_name="DeployTestTeam",
            )
        
        # Prompt erstellen
        prompt = self._create_fix_prompt(browser_errors, backend_errors)
        
        try:
            response = await self._claude_cli.execute(prompt)
            return response.success
        except Exception as e:
            self.logger.error("fix_attempt_failed", error=str(e))
            return False
    
    def _create_fix_prompt(
        self,
        browser_errors: list[str],
        backend_errors: list[str],
    ) -> str:
        """Erstellt den Fix-Prompt für Claude CLI."""
        parts = ["Die App hat Runtime-Fehler. Bitte analysiere und behebe sie:\n"]
        
        if browser_errors:
            parts.append("## Browser/Frontend Errors\n```")
            parts.extend(browser_errors[:10])
            parts.append("```\n")
        
        if backend_errors:
            parts.append("## Backend Errors\n```")
            parts.extend(backend_errors[:10])
            parts.append("```\n")
        
        parts.append("""
## Anweisungen
1. Analysiere die Fehlermeldungen genau
2. Identifiziere die Ursache im Source Code
3. Behebe die Fehler direkt in den betroffenen Dateien

Häufige Fixes:
- **Hydration Errors**: Verwende `suppressHydrationWarning` oder markiere als `"use client"`
- **API 404**: Erstelle Mock-Daten oder korrigiere API-Pfade
- **Import Errors**: Korrigiere Imports oder installiere fehlende Packages
- **Type Errors**: Korrigiere TypeScript Types

Behebe die Fehler jetzt.""")
        
        return "\n".join(parts)
    
    def _handle_log(self, service_name: str, log_line: str) -> None:
        """Callback für Service Logs."""
        # Optional: Can be used for real-time log streaming
        pass
    
    def _report_progress(self, phase: str, data: dict) -> None:
        """Reportet Fortschritt an Callback."""
        if self.on_progress:
            self.on_progress(phase, data)
    
        # Convenience Function
async def deploy_and_test(
    working_dir: str,
    max_iterations: int = 3,
    on_progress: Optional[Callable[[str, dict], None]] = None,
) -> TeamResult:
    """
    Convenience Function für Deploy & Test.
    
    Args:
        working_dir: Projekt-Verzeichnis
        max_iterations: Max Fix-Iterationen
        on_progress: Optional Progress Callback
        
    Returns:
        TeamResult mit allen Ergebnissen
    """
    team = DeployTestTeam(
        working_dir=working_dir,
        max_fix_iterations=max_iterations,
        on_progress=on_progress,
    )
    return await team.run()