"""
Runtime Test Agent - Testet generierte Apps zur Laufzeit via Browser Console Capture.

Führt nach erfolgreichem Build automatisch aus:
1. Dev Server starten
2. Auf Server-Ready warten
3. Multi-Route Browser Console Capture
4. Backend-Logs auf Errors prüfen
5. Bei Fehlern: Claude CLI Fix + Retry
6. Server stoppen
"""
import asyncio
import os
import subprocess
import socket
import json
import threading
import queue as queue_module
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import structlog

from src.autogen.cli_wrapper import ClaudeCLI

logger = structlog.get_logger(__name__)


@dataclass
class RuntimeResult:
    """Ergebnis des Runtime Tests"""
    success: bool
    server_started: bool = False
    console_errors: int = 0
    console_warnings: int = 0
    failed_requests: int = 0
    backend_errors: int = 0  # NEU: Backend-Fehler
    backend_error_details: list[str] = field(default_factory=list)  # NEU
    routes_tested: list[str] = field(default_factory=list)
    fixes_attempted: int = 0
    fixes_successful: int = 0
    error_details: list[str] = field(default_factory=list)
    execution_time_ms: int = 0
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "server_started": self.server_started,
            "console_errors": self.console_errors,
            "console_warnings": self.console_warnings,
            "failed_requests": self.failed_requests,
            "backend_errors": self.backend_errors,
            "backend_error_details": self.backend_error_details[:10],
            "routes_tested": self.routes_tested,
            "fixes_attempted": self.fixes_attempted,
            "fixes_successful": self.fixes_successful,
            "error_details": self.error_details[:10],
            "execution_time_ms": self.execution_time_ms,
        }


class RuntimeTestAgent:
    """
    Agent für Runtime-Tests generierter Apps.
    
    Verwendet BrowserConsoleAgent für Console/Network Capture.
    Fängt Backend-Logs (stderr/stdout) für Fehleranalyse.
    Integriert mit Claude CLI für automatische Fehlerbehebung.
    """
    
    def __init__(
        self,
        working_dir: str,
        port: int = 3000,
        max_fix_iterations: int = 3,
        server_timeout: float = 60.0,
        browser: str = "chrome",
    ):
        self.working_dir = Path(working_dir)
        self.port = port
        self.max_fix_iterations = max_fix_iterations
        self.server_timeout = server_timeout
        self.browser = browser
        
        self.claude_cli = ClaudeCLI(working_dir=str(self.working_dir))
        self._dev_process: Optional[subprocess.Popen] = None
        self._server_was_running = False
        self._log_queue: queue_module.Queue = queue_module.Queue()
        self._log_thread: Optional[threading.Thread] = None
        
        self.logger = logger.bind(
            component="runtime_test_agent",
            working_dir=str(working_dir),
        )
    
    def _read_logs(self, pipe, log_queue: queue_module.Queue):
        """Thread-Funktion zum Lesen von Prozess-Logs."""
        try:
            for line in iter(pipe.readline, b''):
                try:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if decoded:
                        log_queue.put(decoded)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            pipe.close()
    
    def _analyze_backend_logs(self) -> tuple[list[str], int]:
        """
        Analysiert gesammelte Backend-Logs auf Fehler mit Deduplizierung.

        Returns:
            Tuple von (unique_error_messages, unique_error_count)
            Now returns UNIQUE errors, not duplicates.
        """
        errors = []
        all_logs = []
        seen_error_hashes: set[str] = set()  # Track unique errors
        error_occurrence_count: dict[str, int] = {}  # Count occurrences

        # Alle Logs aus der Queue holen
        while not self._log_queue.empty():
            try:
                log_line = self._log_queue.get_nowait()
                all_logs.append(log_line)
            except queue_module.Empty:
                break

        # Error-Patterns für Python/FastAPI/uvicorn
        error_patterns = [
            'ERROR',
            'Traceback',
            'Exception',
            'ImportError',
            'ModuleNotFoundError',
            'AttributeError',
            'TypeError',
            'ValueError',
            'KeyError',
            'NameError',
            'SyntaxError',
            'IndentationError',
            'RuntimeError',
            'AssertionError',
            'FileNotFoundError',
            'ConnectionRefusedError',
            'WinError',
        ]

        collecting_traceback = False
        current_error = []

        def _add_unique_error(error_text: str):
            """Add error only if unique (based on hash of content)."""
            import hashlib
            # Normalize error text for deduplication
            normalized = error_text.strip()
            error_hash = hashlib.md5(normalized.encode('utf-8', errors='replace')).hexdigest()

            if error_hash not in seen_error_hashes:
                seen_error_hashes.add(error_hash)
                errors.append(error_text)
                error_occurrence_count[error_hash] = 1
            else:
                error_occurrence_count[error_hash] = error_occurrence_count.get(error_hash, 1) + 1

        for line in all_logs:
            # Traceback-Sammlung starten
            if 'Traceback' in line:
                collecting_traceback = True
                current_error = [line]
                continue

            # Traceback weitersammeln
            if collecting_traceback:
                current_error.append(line)
                # Ende des Tracebacks erkennen (Error-Zeile)
                if any(pattern in line for pattern in error_patterns[2:]):  # Skip ERROR, Traceback
                    _add_unique_error('\n'.join(current_error))
                    collecting_traceback = False
                    current_error = []
                continue

            # Einzelne Error-Zeilen
            if any(pattern in line for pattern in error_patterns):
                _add_unique_error(line)

        # Log deduplication results
        total_occurrences = sum(error_occurrence_count.values())
        if total_occurrences > len(errors):
            self.logger.info(
                "errors_deduplicated",
                unique_errors=len(errors),
                total_occurrences=total_occurrences,
                reduction=f"{100 - (len(errors) / total_occurrences * 100):.0f}%"
            )

        return errors, len(errors)  # Now returns UNIQUE count
    
    async def run_tests(self) -> RuntimeResult:
        """
        Führt den kompletten Runtime-Test-Zyklus durch.
        
        Returns:
            RuntimeResult mit Test-Ergebnissen
        """
        import time
        start_time = time.time()
        
        result = RuntimeResult(success=False)
        
        try:
            # 1. Prüfen ob Server bereits läuft
            self._server_was_running = await self._is_server_running()
            
            if self._server_was_running:
                self.logger.info("using_existing_server", port=self.port)
                result.server_started = True
            else:
                # Dev Server starten
                self.logger.info("starting_dev_server")
                if not await self._start_dev_server():
                    result.error_details.append("Dev Server konnte nicht gestartet werden")
                    
                    # Backend-Logs analysieren für Fehlerdetails
                    backend_errors, error_count = self._analyze_backend_logs()
                    result.backend_errors = error_count
                    result.backend_error_details = backend_errors
                    
                    if backend_errors:
                        self.logger.error(
                            "backend_startup_errors",
                            error_count=error_count,
                            first_error=backend_errors[0][:200] if backend_errors else None,
                        )
                    
                    return result
                
                result.server_started = True
            
            # 2. Browser Console Capture
            self.logger.info("running_browser_capture")
            capture_result = await self._run_browser_capture()
            
            if capture_result is None:
                result.error_details.append("Browser Capture fehlgeschlagen")
                return result
            
            result.routes_tested = capture_result.get("routes", [])
            result.console_errors = capture_result.get("errors", 0)
            result.console_warnings = capture_result.get("warnings", 0)
            result.failed_requests = capture_result.get("failed_requests", 0)
            
            # 3. Backend-Logs analysieren
            backend_errors, error_count = self._analyze_backend_logs()
            result.backend_errors = error_count
            result.backend_error_details = backend_errors
            
            if error_count > 0:
                self.logger.info(
                    "backend_errors_detected",
                    error_count=error_count,
                )
            
            # 4. Bei Fehlern: Fix-Loop
            total_errors = result.console_errors + result.failed_requests + result.backend_errors
            
            if total_errors > 0:
                self.logger.info(
                    "runtime_errors_detected",
                    console_errors=result.console_errors,
                    failed_requests=result.failed_requests,
                    backend_errors=result.backend_errors,
                )
                
                # Track stuck errors for detection
                stuck_error_count = 0

                for iteration in range(self.max_fix_iterations):
                    result.fixes_attempted += 1

                    # Capture error hashes BEFORE fix for verification
                    import hashlib
                    current_error_hashes = {
                        hashlib.md5(e.encode('utf-8', errors='replace')).hexdigest()
                        for e in backend_errors
                    }

                    self.logger.info(
                        "attempting_fix",
                        iteration=iteration + 1,
                        max_iterations=self.max_fix_iterations,
                        unique_errors=len(current_error_hashes),
                    )

                    # Kombinierten Error-Context erstellen
                    combined_context = self._create_combined_error_context(
                        capture_result.get("formatted", ""),
                        backend_errors,
                    )

                    # Fix mit Claude CLI
                    fix_success = await self._fix_runtime_errors(combined_context)

                    if fix_success:
                        # Server neu starten (nur wenn wir ihn gestartet haben)
                        if not self._server_was_running:
                            await self._stop_dev_server()
                            await asyncio.sleep(2)

                            if not await self._start_dev_server():
                                result.error_details.append("Server-Neustart fehlgeschlagen")
                                break
                        else:
                            # Bei bestehendem Server: kurz warten für HMR
                            await asyncio.sleep(3)

                        # Erneut testen
                        capture_result = await self._run_browser_capture()

                        if capture_result:
                            result.console_errors = capture_result.get("errors", 0)
                            result.console_warnings = capture_result.get("warnings", 0)
                            result.failed_requests = capture_result.get("failed_requests", 0)

                            # Backend-Logs erneut prüfen
                            backend_errors, error_count = self._analyze_backend_logs()
                            result.backend_errors = error_count
                            result.backend_error_details = backend_errors

                            # Verify fix by comparing error hashes
                            new_error_hashes = {
                                hashlib.md5(e.encode('utf-8', errors='replace')).hexdigest()
                                for e in backend_errors
                            }

                            # Check if any errors were actually resolved
                            resolved_errors = current_error_hashes - new_error_hashes
                            persisting_errors = current_error_hashes & new_error_hashes

                            if resolved_errors:
                                # At least some errors were actually fixed
                                result.fixes_successful += 1
                                stuck_error_count = 0  # Reset stuck counter
                                self.logger.info(
                                    "fix_verified",
                                    resolved=len(resolved_errors),
                                    remaining=len(new_error_hashes),
                                )
                            else:
                                # No errors were actually resolved - fix didn't work
                                stuck_error_count += 1
                                self.logger.warning(
                                    "fix_not_effective",
                                    same_errors=len(persisting_errors),
                                    stuck_count=stuck_error_count,
                                )

                                # If same errors persist 3 times, add warning to result
                                if stuck_error_count >= 3:
                                    result.error_details.append(
                                        f"Stuck on same error(s) after {stuck_error_count} fix attempts"
                                    )

                            total_errors = result.console_errors + result.failed_requests + result.backend_errors

                            if total_errors == 0:
                                self.logger.info("runtime_errors_fixed")
                                break
            
            # 5. Erfolg bestimmen
            result.success = (
                result.console_errors == 0 and 
                result.failed_requests == 0 and
                result.backend_errors == 0
            )
            
            self.logger.info(
                "runtime_test_complete",
                success=result.success,
                console_errors=result.console_errors,
                backend_errors=result.backend_errors,
                fixes_applied=result.fixes_successful,
            )
            
        except Exception as e:
            self.logger.error("runtime_test_failed", error=str(e))
            result.error_details.append(str(e))
        
        finally:
            # Server nur stoppen wenn wir ihn gestartet haben
            if not self._server_was_running:
                await self._stop_dev_server()
            result.execution_time_ms = int((time.time() - start_time) * 1000)
        
        return result
    
    def _create_combined_error_context(
        self,
        browser_context: str,
        backend_errors: list[str],
    ) -> str:
        """Kombiniert Browser- und Backend-Errors für Claude CLI."""
        parts = []
        
        if browser_context:
            parts.append("## Browser Console Errors\n" + browser_context)
        
        if backend_errors:
            parts.append("## Backend Errors (Python/FastAPI)\n```\n" + 
                        "\n---\n".join(backend_errors[:5]) + 
                        "\n```")
        
        return "\n\n".join(parts)
    
    async def _is_server_running(self) -> bool:
        """Prüft ob der Server bereits auf dem Port läuft."""
        import httpx
        
        url = f"http://127.0.0.1:{self.port}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5.0, follow_redirects=True)
                return response.status_code < 500
        except Exception:
            return False
    
    async def _start_dev_server(self) -> bool:
        """Startet den Dev Server und wartet auf Ready."""
        try:
            # Port finden
            self.port = await self._find_available_port(self.port)
            
            # Dev Command ermitteln
            dev_cmd = await self._detect_dev_command()
            if not dev_cmd:
                dev_cmd = ["npm", "run", "dev"]
            
            # Environment vorbereiten
            env = os.environ.copy()
            env["PORT"] = str(self.port)
            env["VITE_PORT"] = str(self.port)
            
            # Log-Queue leeren
            while not self._log_queue.empty():
                try:
                    self._log_queue.get_nowait()
                except queue_module.Empty:
                    break
            
            # Server starten mit Pipe für Logs
            use_shell = os.name == 'nt'
            
            self._dev_process = subprocess.Popen(
                dev_cmd,
                cwd=str(self.working_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=use_shell,
                env=env,
            )
            
            # Log-Thread starten
            self._log_thread = threading.Thread(
                target=self._read_logs,
                args=(self._dev_process.stdout, self._log_queue),
                daemon=True,
            )
            self._log_thread.start()
            
            self.logger.info(
                "dev_server_starting",
                command=" ".join(dev_cmd),
                port=self.port,
                pid=self._dev_process.pid,
            )
            
            # Auf Ready warten
            if await self._wait_for_server():
                self.logger.info("dev_server_ready", port=self.port)
                return True
            else:
                self.logger.warning("dev_server_timeout")
                return False
            
        except Exception as e:
            self.logger.error("dev_server_start_failed", error=str(e))
            return False
    
    async def _stop_dev_server(self) -> None:
        """Stoppt den Dev Server."""
        if not self._dev_process:
            return
        
        try:
            if os.name == 'nt':
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(self._dev_process.pid)],
                    capture_output=True,
                )
            else:
                self._dev_process.terminate()
                await asyncio.sleep(2)
                if self._dev_process.poll() is None:
                    self._dev_process.kill()
            
            self._dev_process = None
            self.logger.info("dev_server_stopped")
            
        except Exception as e:
            self.logger.error("dev_server_stop_failed", error=str(e))
    
    async def _wait_for_server(self) -> bool:
        """Wartet bis der Server bereit ist."""
        import httpx
        
        start_time = asyncio.get_event_loop().time()
        url = f"http://127.0.0.1:{self.port}"
        
        while asyncio.get_event_loop().time() - start_time < self.server_timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, timeout=5.0, follow_redirects=True)
                    if response.status_code < 500:
                        return True
            except Exception:
                pass
            
            # Prüfen ob Prozess noch läuft
            if self._dev_process and self._dev_process.poll() is not None:
                return False
            
            await asyncio.sleep(2)
        
        return False
    
    async def _run_browser_capture(self) -> Optional[dict]:
        """Führt Multi-Route Browser Capture durch."""
        try:
            from src.agents.browser_console_agent import BrowserConsoleAgent
            
            agent = BrowserConsoleAgent(browser=self.browser)
            base_url = f"http://127.0.0.1:{self.port}"
            
            # App Directory für Route Discovery
            app_dir = self.working_dir / "app"
            
            if app_dir.exists():
                # Multi-Route Crawling
                multi_capture = await agent.crawl_all_routes(
                    base_url=base_url,
                    app_dir=app_dir,
                    wait_seconds=5.0,
                )
                
                return {
                    "routes": multi_capture.routes_crawled,
                    "errors": multi_capture.total_errors,
                    "warnings": multi_capture.total_warnings,
                    "failed_requests": multi_capture.total_failed_requests,
                    "formatted": multi_capture.format_for_claude(),
                }
            else:
                # Single URL Capture
                capture = await agent.capture_console(
                    url=base_url,
                    wait_seconds=5.0,
                )
                
                return {
                    "routes": ["/"],
                    "errors": len(capture.errors),
                    "warnings": len(capture.warnings),
                    "failed_requests": len(capture.failed_requests),
                    "formatted": capture.format_for_claude(),
                }
            
        except Exception as e:
            self.logger.error("browser_capture_failed", error=str(e))
            return None
    
    async def _fix_runtime_errors(self, error_context: str) -> bool:
        """Versucht Runtime-Fehler mit Claude CLI zu fixen."""
        prompt = f"""Die App hat Runtime-Fehler im Browser. Bitte analysiere und behebe sie:

{error_context}

## Anweisungen
1. Analysiere die Console Errors und Failed Network Requests
2. Häufige Ursachen und Fixes:
   - **Hydration Errors**: Verwende `suppressHydrationWarning` oder `use client`
   - **API 404**: Erstelle Mock-Daten oder entferne API-Calls
   - **WebSocket 403**: Entferne WebSocket-Code oder mocke es
   - **favicon.ico 404**: Füge `public/favicon.ico` hinzu
3. Behebe die Ursache im Source Code
4. Der Dev Server wird automatisch neu gestartet"""
        
        try:
            result = await self.claude_cli.execute(prompt)
            return result.success
        except Exception as e:
            self.logger.error("fix_attempt_failed", error=str(e))
            return False
    
    async def _detect_dev_command(self) -> Optional[list[str]]:
        """Ermittelt den Dev-Befehl aus package.json."""
        package_json = self.working_dir / "package.json"
        if not package_json.exists():
            return None
        
        try:
            with open(package_json) as f:
                pkg = json.load(f)
            
            scripts = pkg.get("scripts", {})
            
            for cmd in ["dev", "start", "serve", "develop"]:
                if cmd in scripts:
                    return ["npm", "run", cmd]
            
            return None
        except Exception:
            return None
    
    async def _find_available_port(self, start_port: int) -> int:
        """Findet einen freien Port."""
        port = start_port
        max_attempts = 100
        
        for _ in range(max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('127.0.0.1', port))
                    return port
            except OSError:
                port += 1
        
        return start_port