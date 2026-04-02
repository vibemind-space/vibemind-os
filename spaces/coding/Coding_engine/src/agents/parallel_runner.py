"""
Parallel Runner - Startet Frontend und Backend Services parallel.

Funktionen:
1. Port Allokation mit Konflikt-Handling
2. Paralleler Start von Frontend + Backend
3. Health Checks für beide Services
4. Log Capturing für Error Detection
5. Graceful Shutdown
"""
import asyncio
import os
import subprocess
import socket
import threading
import queue as queue_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable
import structlog

from src.agents.entrypoint_detector import ProjectConfig, ServiceConfig

logger = structlog.get_logger(__name__)


@dataclass
class ServiceStatus:
    """Status eines laufenden Services."""
    name: str
    running: bool = False
    port: int = 0
    pid: Optional[int] = None
    health_ok: bool = False
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "running": self.running,
            "port": self.port,
            "pid": self.pid,
            "health_ok": self.health_ok,
            "error_count": self.error_count,
            "errors": self.errors[:10],
        }


@dataclass
class RunnerResult:
    """Ergebnis des Parallel Runners."""
    success: bool
    frontend: Optional[ServiceStatus] = None
    backend: Optional[ServiceStatus] = None
    total_errors: int = 0
    all_errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "frontend": self.frontend.to_dict() if self.frontend else None,
            "backend": self.backend.to_dict() if self.backend else None,
            "total_errors": self.total_errors,
            "all_errors": self.all_errors[:20],
        }


class ParallelRunner:
    """
    Startet Frontend und Backend Services parallel mit Health Checks.
    
    Features:
    - Port Pool Management (3000-3010 für Frontend, 8000-8010 für Backend)
    - Health Check mit Retry
    - Log Capturing für Error Detection
    - Graceful Shutdown
    """
    
    # Port Pools
    FRONTEND_PORTS = list(range(3000, 3011))
    BACKEND_PORTS = list(range(8000, 8011))
    
    # Error Patterns für Log Analysis
    ERROR_PATTERNS = [
        # Python
        'ERROR', 'Traceback', 'Exception', 'ImportError', 'ModuleNotFoundError',
        'AttributeError', 'TypeError', 'ValueError', 'KeyError', 'NameError',
        'SyntaxError', 'IndentationError', 'RuntimeError', 'FileNotFoundError',
        # Node.js
        'Error:', 'ENOENT', 'EADDRINUSE', 'ReferenceError', 'UnhandledPromiseRejection',
        # General
        'FATAL', 'CRITICAL', 'failed to', 'could not',
    ]
    
    def __init__(
        self,
        working_dir: str,
        config: ProjectConfig,
        startup_timeout: float = 60.0,
        health_check_interval: float = 2.0,
        on_log: Optional[Callable[[str, str], None]] = None,
    ):
        self.working_dir = Path(working_dir)
        self.config = config
        self.startup_timeout = startup_timeout
        self.health_check_interval = health_check_interval
        self.on_log = on_log  # Callback: (service_name, log_line)
        
        # Process Management
        self._frontend_process: Optional[subprocess.Popen] = None
        self._backend_process: Optional[subprocess.Popen] = None
        
        # Log Queues
        self._frontend_logs: queue_module.Queue = queue_module.Queue()
        self._backend_logs: queue_module.Queue = queue_module.Queue()
        
        # Log Threads
        self._log_threads: list[threading.Thread] = []
        
        # Allocated Ports
        self._frontend_port: int = 0
        self._backend_port: int = 0
        
        self.logger = logger.bind(
            component="parallel_runner",
            working_dir=str(working_dir),
        )
    
    async def start(self) -> RunnerResult:
        """
        Startet alle konfigurierten Services und wartet auf Health.
        
        Returns:
            RunnerResult mit Status beider Services
        """
        result = RunnerResult(success=False)
        
        try:
            # Services parallel starten
            tasks = []
            
            if self.config.frontend:
                tasks.append(self._start_frontend())
            
            if self.config.backend:
                tasks.append(self._start_backend())
            
            if not tasks:
                self.logger.warning("no_services_to_start")
                result.success = True
                return result
            
            # Parallel starten
            statuses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Ergebnisse verarbeiten
            for status in statuses:
                if isinstance(status, Exception):
                    self.logger.error("service_start_exception", error=str(status))
                    result.all_errors.append(str(status))
                    continue
                
                if status.name == "frontend":
                    result.frontend = status
                elif status.name == "backend":
                    result.backend = status
            
            # Erfolg bestimmen
            frontend_ok = result.frontend is None or result.frontend.health_ok
            backend_ok = result.backend is None or result.backend.health_ok
            result.success = frontend_ok and backend_ok
            
            # Errors zählen
            if result.frontend:
                result.total_errors += result.frontend.error_count
                result.all_errors.extend(result.frontend.errors)
            if result.backend:
                result.total_errors += result.backend.error_count
                result.all_errors.extend(result.backend.errors)
            
            self.logger.info(
                "services_started",
                success=result.success,
                frontend_ok=frontend_ok,
                backend_ok=backend_ok,
                total_errors=result.total_errors,
            )
            
        except Exception as e:
            self.logger.error("start_failed", error=str(e))
            result.all_errors.append(str(e))
        
        return result
    
    async def stop(self) -> None:
        """Stoppt alle laufenden Services."""
        self.logger.info("stopping_services")
        
        tasks = []
        
        if self._frontend_process:
            tasks.append(self._stop_process(self._frontend_process, "frontend"))
        
        if self._backend_process:
            tasks.append(self._stop_process(self._backend_process, "backend"))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Cleanup
        self._frontend_process = None
        self._backend_process = None
        
        self.logger.info("services_stopped")
    
    async def get_errors(self) -> list[str]:
        """Sammelt alle Errors aus den Log Queues."""
        errors = []
        
        # Frontend Logs
        while not self._frontend_logs.empty():
            try:
                line = self._frontend_logs.get_nowait()
                if self._is_error_line(line):
                    errors.append(f"[Frontend] {line}")
            except queue_module.Empty:
                break
        
        # Backend Logs
        while not self._backend_logs.empty():
            try:
                line = self._backend_logs.get_nowait()
                if self._is_error_line(line):
                    errors.append(f"[Backend] {line}")
            except queue_module.Empty:
                break
        
        return errors
    
    def _is_error_line(self, line: str) -> bool:
        """Prüft ob eine Log-Zeile ein Error ist."""
        return any(pattern.lower() in line.lower() for pattern in self.ERROR_PATTERNS)
    
    async def _start_frontend(self) -> ServiceStatus:
        """Startet den Frontend Service."""
        status = ServiceStatus(name="frontend")
        
        if not self.config.frontend:
            return status
        
        config = self.config.frontend
        
        try:
            # Port allokieren
            self._frontend_port = await self._allocate_port(self.FRONTEND_PORTS)
            status.port = self._frontend_port
            
            # Working Directory
            work_dir = self.working_dir
            if config.working_dir:
                work_dir = self.working_dir / config.working_dir
            
            # Environment
            env = os.environ.copy()
            env["PORT"] = str(self._frontend_port)
            env["VITE_PORT"] = str(self._frontend_port)
            env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{self._backend_port}" if self._backend_port else ""
            
            # Process starten
            use_shell = os.name == 'nt'
            cmd = config.dev_cmd or "npm run dev"
            
            # Port explizit für Frontend Commands anhängen (analog zu Backend)
            if "--port" not in cmd and "-- --port" not in cmd:
                if "npm run dev" in cmd or "vite" in cmd:
                    cmd += f" -- --port {self._frontend_port}"
                elif "next dev" in cmd:
                    cmd += f" -p {self._frontend_port}"
            
            self._frontend_process = subprocess.Popen(
                cmd,
                cwd=str(work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=use_shell,
                env=env,
            )
            
            status.pid = self._frontend_process.pid
            status.running = True
            
            # Log Thread starten
            self._start_log_thread(
                self._frontend_process.stdout,
                self._frontend_logs,
                "frontend",
            )
            
            self.logger.info(
                "frontend_starting",
                port=self._frontend_port,
                pid=status.pid,
                cmd=cmd,
            )
            
            # Health Check
            health_url = config.health_url or f"http://localhost:{self._frontend_port}"
            status.health_ok = await self._wait_for_health(health_url)
            
            if not status.health_ok:
                status.errors.append("Frontend Health Check failed")
            
        except Exception as e:
            self.logger.error("frontend_start_failed", error=str(e))
            status.errors.append(str(e))
        
        return status
    
    async def _start_backend(self) -> ServiceStatus:
        """Startet den Backend Service."""
        status = ServiceStatus(name="backend")
        
        if not self.config.backend:
            return status
        
        config = self.config.backend
        
        try:
            # Port allokieren
            self._backend_port = await self._allocate_port(self.BACKEND_PORTS)
            status.port = self._backend_port
            
            # Working Directory - wichtig für Backend!
            work_dir = self.working_dir
            if config.working_dir:
                work_dir = self.working_dir / config.working_dir
                # Stelle sicher dass das Verzeichnis existiert
                if not work_dir.exists():
                    self.logger.warning("backend_dir_not_found", dir=str(work_dir))
                    status.errors.append(f"Backend directory not found: {work_dir}")
                    return status
            
            # Environment
            env = os.environ.copy()
            env["PORT"] = str(self._backend_port)
            env["PYTHONPATH"] = str(work_dir)  # Wichtig für Python Module
            
            # Dev Command anpassen für Port
            dev_cmd = config.dev_cmd or "python main.py"
            
            # Port in Command ersetzen wenn möglich
            if "--port" in dev_cmd:
                import re
                dev_cmd = re.sub(r'--port\s+\d+', f'--port {self._backend_port}', dev_cmd)
            elif "uvicorn" in dev_cmd and "--port" not in dev_cmd:
                dev_cmd += f" --port {self._backend_port}"
            
            # Process starten
            use_shell = os.name == 'nt'
            
            self._backend_process = subprocess.Popen(
                dev_cmd,
                cwd=str(work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=use_shell,
                env=env,
            )
            
            status.pid = self._backend_process.pid
            status.running = True
            
            # Log Thread starten
            self._start_log_thread(
                self._backend_process.stdout,
                self._backend_logs,
                "backend",
            )
            
            self.logger.info(
                "backend_starting",
                port=self._backend_port,
                pid=status.pid,
                cmd=dev_cmd,
            )
            
            # Health Check
            health_url = config.health_url or f"http://localhost:{self._backend_port}"
            # Ersetze Port in health_url
            if config.health_url:
                import re
                health_url = re.sub(r'localhost:\d+', f'localhost:{self._backend_port}', health_url)
            
            status.health_ok = await self._wait_for_health(health_url)
            
            if not status.health_ok:
                status.errors.append("Backend Health Check failed")
            
        except Exception as e:
            self.logger.error("backend_start_failed", error=str(e))
            status.errors.append(str(e))
        
        return status
    
    def _start_log_thread(
        self,
        pipe,
        log_queue: queue_module.Queue,
        service_name: str,
    ) -> None:
        """Startet einen Thread zum Lesen von Prozess-Logs."""
        def read_logs():
            try:
                for line in iter(pipe.readline, b''):
                    try:
                        decoded = line.decode('utf-8', errors='replace').strip()
                        if decoded:
                            log_queue.put(decoded)
                            if self.on_log:
                                self.on_log(service_name, decoded)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass
        
        thread = threading.Thread(target=read_logs, daemon=True)
        thread.start()
        self._log_threads.append(thread)
    
    async def _allocate_port(self, port_pool: list[int]) -> int:
        """Allokiert einen freien Port aus dem Pool."""
        for port in port_pool:
            if await self._is_port_free(port):
                return port
        
        # Fallback: Ersten Port nehmen
        return port_pool[0]
    
    async def _is_port_free(self, port: int) -> bool:
        """Prüft ob ein Port frei ist."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return True
        except OSError:
            return False
    
    async def _wait_for_health(self, url: str) -> bool:
        """Wartet bis ein Service healthy ist."""
        import httpx
        
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < self.startup_timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, timeout=5.0, follow_redirects=True)
                    if response.status_code < 500:
                        return True
            except Exception:
                pass
            
            await asyncio.sleep(self.health_check_interval)
        
        return False
    
    async def _stop_process(self, process: subprocess.Popen, name: str) -> None:
        """Stoppt einen Prozess graceful."""
        try:
            if os.name == 'nt':
                # Windows: taskkill mit /F /T für Prozessbaum
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(process.pid)],
                    capture_output=True,
                )
            else:
                # Unix: SIGTERM, dann SIGKILL
                process.terminate()
                await asyncio.sleep(2)
                if process.poll() is None:
                    process.kill()
            
            self.logger.info(f"{name}_stopped", pid=process.pid)
            
        except Exception as e:
            self.logger.warning(f"{name}_stop_failed", error=str(e))
    
    @property
    def frontend_port(self) -> int:
        """Gibt den allokierten Frontend Port zurück."""
        return self._frontend_port
    
    @property
    def backend_port(self) -> int:
        """Gibt den allokierten Backend Port zurück."""
        return self._backend_port