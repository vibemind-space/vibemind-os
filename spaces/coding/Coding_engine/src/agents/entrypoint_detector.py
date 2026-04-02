"""
Entrypoint Detector - Verwendet Claude CLI um Projekt-Entrypoints zu erkennen.

Analysiert ein Projekt und erkennt automatisch:
- Frontend: Install + Dev Commands, Port
- Backend: Install + Dev Commands, Port
- Routen für Testing
"""
import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from src.autogen.cli_wrapper import ClaudeCLI

logger = structlog.get_logger(__name__)


@dataclass
class ServiceConfig:
    """Konfiguration für einen Service (Frontend oder Backend)."""
    install_cmd: Optional[str] = None
    dev_cmd: Optional[str] = None
    port: int = 3000
    health_url: Optional[str] = None
    working_dir: Optional[str] = None  # Subdirectory wie "backend/"
    
    def to_dict(self) -> dict:
        return {
            "install_cmd": self.install_cmd,
            "dev_cmd": self.dev_cmd,
            "port": self.port,
            "health_url": self.health_url,
            "working_dir": self.working_dir,
        }


@dataclass
class ProjectConfig:
    """Vollständige Projektkonfiguration."""
    frontend: Optional[ServiceConfig] = None
    backend: Optional[ServiceConfig] = None
    routes: list[str] = field(default_factory=list)
    detected_stack: str = "unknown"
    
    def to_dict(self) -> dict:
        return {
            "frontend": self.frontend.to_dict() if self.frontend else None,
            "backend": self.backend.to_dict() if self.backend else None,
            "routes": self.routes,
            "detected_stack": self.detected_stack,
        }


class EntrypointDetector:
    """
    Verwendet Claude CLI um Projekt-Entrypoints automatisch zu erkennen.
    
    Funktioniert mit jedem Tech Stack - Claude analysiert:
    - package.json, pyproject.toml, requirements.txt
    - README.md für Anweisungen
    - Dockerfile, docker-compose.yml
    - Source Code Struktur
    """
    
    DETECTION_PROMPT = """Analysiere dieses Projekt und gib mir ein JSON mit den Befehlen zum Starten.

WICHTIG: Antworte NUR mit dem JSON, kein anderer Text!

Format:
{
  "frontend": {
    "install_cmd": "npm install",
    "dev_cmd": "npm run dev",
    "port": 3000,
    "health_url": "http://localhost:3000",
    "working_dir": null
  },
  "backend": {
    "install_cmd": "pip install -r requirements.txt",
    "dev_cmd": "uvicorn main:app --reload --port 8000",
    "port": 8000,
    "health_url": "http://localhost:8000/health",
    "working_dir": "backend"
  },
  "routes": ["/", "/api/health", "/dashboard"],
  "detected_stack": "Next.js + FastAPI"
}

Regeln:
1. Schau in package.json für npm/yarn/pnpm scripts
2. Schau in pyproject.toml für uv/poetry Befehle
3. Schau in requirements.txt für pip install
4. Schau in README.md für spezielle Anweisungen
5. working_dir ist null wenn im Root, sonst der Subdirectory Name
6. Wenn kein Backend existiert, setze backend auf null
7. Wenn kein Frontend existiert, setze frontend auf null
8. routes sind die wichtigsten URLs zum Testen

Analysiere jetzt das Projekt und gib das JSON zurück."""

    ROUTE_DISCOVERY_PROMPT = """Analysiere dieses Projekt und finde alle testbaren Routes/URLs.

WICHTIG: Antworte NUR mit einem JSON Array, kein anderer Text!

Schau in:
- Next.js: app/ und pages/ Verzeichnisse
- React Router: Route Definitionen
- FastAPI: @app.get/@app.post Decorators
- Express: app.get/app.post Definitionen
- Vue Router: router.js

Format: ["/", "/about", "/api/users", "/dashboard", "/settings"]

Gib das Array zurück:"""

    def __init__(
        self,
        working_dir: str,
        timeout: int = 120,
    ):
        self.working_dir = Path(working_dir)
        self.timeout = timeout
        self.claude_cli = ClaudeCLI(
            working_dir=str(self.working_dir),
            timeout=timeout,
            agent_name="EntrypointDetector",
        )
        self.logger = logger.bind(
            component="entrypoint_detector",
            working_dir=str(working_dir),
        )
    
    async def detect(self) -> ProjectConfig:
        """
        Erkennt automatisch die Projekt-Entrypoints via Claude CLI.
        
        Returns:
            ProjectConfig mit frontend/backend Konfiguration
        """
        self.logger.info("detecting_entrypoints")
        
        # Claude CLI für Detection aufrufen
        response = await self.claude_cli.execute(
            self.DETECTION_PROMPT,
            use_mcp=False,  # Keine MCP Tools nötig für Analyse
        )
        
        if not response.success:
            self.logger.warning(
                "detection_failed_using_fallback",
                error=response.error,
            )
            return await self._fallback_detection()
        
        # JSON aus Response extrahieren
        config = self._parse_response(response.output)
        
        if config is None:
            self.logger.warning("json_parse_failed_using_fallback")
            return await self._fallback_detection()
        
        self.logger.info(
            "detection_complete",
            stack=config.detected_stack,
            has_frontend=config.frontend is not None,
            has_backend=config.backend is not None,
            routes_count=len(config.routes),
        )
        
        return config
    
    async def discover_routes(self) -> list[str]:
        """
        Entdeckt alle testbaren Routes im Projekt.
        
        Returns:
            Liste von URLs zum Testen
        """
        self.logger.info("discovering_routes")
        
        response = await self.claude_cli.execute(
            self.ROUTE_DISCOVERY_PROMPT,
            use_mcp=False,
        )
        
        if not response.success:
            self.logger.warning("route_discovery_failed")
            return ["/"]
        
        # JSON Array aus Response extrahieren
        routes = self._parse_routes(response.output)
        
        self.logger.info("routes_discovered", count=len(routes))
        return routes
    
    def _parse_response(self, output: str) -> Optional[ProjectConfig]:
        """Parst die Claude CLI Response und extrahiert das JSON."""
        try:
            # Versuche JSON direkt zu parsen
            json_match = re.search(r'\{[\s\S]*\}', output)
            if not json_match:
                return None
            
            data = json.loads(json_match.group())
            
            config = ProjectConfig(
                detected_stack=data.get("detected_stack", "unknown"),
                routes=data.get("routes", ["/"]),
            )
            
            # Frontend parsen
            if data.get("frontend"):
                fe = data["frontend"]
                config.frontend = ServiceConfig(
                    install_cmd=fe.get("install_cmd"),
                    dev_cmd=fe.get("dev_cmd"),
                    port=fe.get("port", 3000),
                    health_url=fe.get("health_url"),
                    working_dir=fe.get("working_dir"),
                )
            
            # Backend parsen
            if data.get("backend"):
                be = data["backend"]
                config.backend = ServiceConfig(
                    install_cmd=be.get("install_cmd"),
                    dev_cmd=be.get("dev_cmd"),
                    port=be.get("port", 8000),
                    health_url=be.get("health_url"),
                    working_dir=be.get("working_dir"),
                )
            
            return config
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.logger.error("json_parse_error", error=str(e))
            return None
    
    def _parse_routes(self, output: str) -> list[str]:
        """Parst die Routes aus der Claude Response."""
        try:
            # Suche nach JSON Array
            json_match = re.search(r'\[[\s\S]*?\]', output)
            if not json_match:
                return ["/"]
            
            routes = json.loads(json_match.group())
            
            # Validiere dass es Strings sind
            valid_routes = [r for r in routes if isinstance(r, str) and r.startswith("/")]
            
            return valid_routes if valid_routes else ["/"]
            
        except (json.JSONDecodeError, TypeError):
            return ["/"]
    
    async def _fallback_detection(self) -> ProjectConfig:
        """
        Fallback-Detection basierend auf Dateisystem-Analyse.
        
        Wird verwendet wenn Claude CLI nicht antwortet oder fehlschlägt.
        """
        self.logger.info("running_fallback_detection")
        
        config = ProjectConfig(detected_stack="unknown")
        
        # Check für Node.js Frontend
        package_json = self.working_dir / "package.json"
        if package_json.exists():
            try:
                with open(package_json) as f:
                    pkg = json.load(f)
                
                scripts = pkg.get("scripts", {})
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                all_deps = {**deps, **dev_deps}
                
                # Detect dev command
                dev_cmd = None
                for cmd in ["dev", "start", "serve"]:
                    if cmd in scripts:
                        dev_cmd = f"npm run {cmd}"
                        break
                
                # Detect framework
                framework = "Node.js"
                if "next" in all_deps:
                    framework = "Next.js"
                elif "react" in all_deps:
                    framework = "React"
                elif "vue" in all_deps:
                    framework = "Vue"
                elif "electron" in all_deps:
                    framework = "Electron"
                
                config.frontend = ServiceConfig(
                    install_cmd="npm install",
                    dev_cmd=dev_cmd or "npm run dev",
                    port=3000,
                    health_url="http://localhost:3000",
                )
                config.detected_stack = framework
                
            except Exception as e:
                self.logger.warning("package_json_parse_failed", error=str(e))
        
        # Check für Python Backend
        backend_dir = None
        for subdir in ["backend", "api", "server"]:
            if (self.working_dir / subdir).exists():
                backend_dir = subdir
                break
        
        # Check root oder subdirectory
        search_dirs = [self.working_dir]
        if backend_dir:
            search_dirs.insert(0, self.working_dir / backend_dir)
        
        for search_dir in search_dirs:
            # pyproject.toml für UV
            pyproject = search_dir / "pyproject.toml"
            requirements = search_dir / "requirements.txt"
            main_py = search_dir / "main.py"
            app_py = search_dir / "app.py"
            
            if pyproject.exists() or requirements.exists() or main_py.exists() or app_py.exists():
                install_cmd = "uv sync" if pyproject.exists() else "pip install -r requirements.txt"
                
                # Detect framework
                dev_cmd = "python main.py"
                if main_py.exists():
                    with open(main_py) as f:
                        content = f.read()
                    if "uvicorn" in content or "FastAPI" in content:
                        dev_cmd = "uvicorn main:app --reload --port 8000"
                    elif "flask" in content.lower():
                        dev_cmd = "flask run --port 8000"
                
                config.backend = ServiceConfig(
                    install_cmd=install_cmd,
                    dev_cmd=dev_cmd,
                    port=8000,
                    health_url="http://localhost:8000/health",
                    working_dir=backend_dir,
                )
                
                if config.detected_stack == "unknown":
                    config.detected_stack = "Python"
                else:
                    config.detected_stack += " + Python"
                
                break
        
        # Default Route
        config.routes = ["/"]
        
        self.logger.info(
            "fallback_detection_complete",
            stack=config.detected_stack,
            has_frontend=config.frontend is not None,
            has_backend=config.backend is not None,
        )
        
        return config