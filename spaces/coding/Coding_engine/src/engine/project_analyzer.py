"""
Project Analyzer - Detects project type and technology stack from requirements.

Analyzes the requirements JSON to understand what kind of project is being built,
enabling dynamic agent specialization and appropriate validator selection.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import structlog

from .dag_parser import RequirementsData, DAGNode
from src.utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)


logger = structlog.get_logger(__name__)

# Lazy import to avoid circular dependency
_claude_tool = None

def _get_claude_tool():
    """Lazily import ClaudeCodeTool to avoid circular imports."""
    global _claude_tool
    if _claude_tool is None:
        try:
            from src.tools.claude_code_tool import ClaudeCodeTool
            _claude_tool = ClaudeCodeTool()
        except ImportError:
            pass
    return _claude_tool


class ProjectType(Enum):
    """High-level project type classification."""
    ELECTRON_APP = "electron-app"
    WEB_APP = "web-app"
    API_SERVER = "api-server"
    CLI_TOOL = "cli-tool"
    MOBILE_APP = "mobile-app"
    DESKTOP_APP = "desktop-app"
    GAME = "game"
    LIBRARY = "library"
    FULLSTACK = "fullstack"
    UNKNOWN = "unknown"


class Technology(Enum):
    """Technology stack components."""
    # Frontend frameworks
    REACT = "react"
    VUE = "vue"
    SVELTE = "svelte"
    ANGULAR = "angular"

    # Desktop/Mobile
    ELECTRON = "electron"
    TAURI = "tauri"
    REACT_NATIVE = "react-native"
    FLUTTER = "flutter"

    # Backend frameworks
    FASTAPI = "fastapi"
    DJANGO = "django"
    EXPRESS = "express"
    NESTJS = "nestjs"
    FLASK = "flask"

    # Languages
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    PYTHON = "python"
    RUST = "rust"
    GO = "go"

    # Databases
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    SQLITE = "sqlite"
    REDIS = "redis"

    # Build tools
    VITE = "vite"
    WEBPACK = "webpack"
    ESBUILD = "esbuild"

    # Game engines
    PYGAME = "pygame"
    PHASER = "phaser"
    UNITY = "unity"

    # Other
    GRAPHQL = "graphql"
    WEBSOCKET = "websocket"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"


class Domain(Enum):
    """Functional domains in the project."""
    UI = "ui"
    API = "api"
    DATABASE = "database"
    AUTH = "auth"
    FILE_SYSTEM = "file-system"
    NETWORKING = "networking"
    IPC = "ipc"  # Inter-process communication (Electron)
    GRAPHICS = "graphics"
    AUDIO = "audio"
    TESTING = "testing"
    DEVOPS = "devops"
    SECURITY = "security"


@dataclass
class ProjectProfile:
    """
    Complete profile of the project being built.

    This is used to:
    1. Select appropriate agents
    2. Compose system prompts
    3. Register relevant tools
    4. Choose validators
    """
    project_type: ProjectType
    technologies: list[Technology] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)  # windows, macos, linux, web
    domains: list[Domain] = field(default_factory=list)
    complexity: str = "medium"  # simple, medium, complex
    primary_language: str = "typescript"
    has_backend: bool = False
    has_frontend: bool = False
    has_database: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "project_type": self.project_type.value,
            "technologies": [t.value for t in self.technologies],
            "platforms": self.platforms,
            "domains": [d.value for d in self.domains],
            "complexity": self.complexity,
            "primary_language": self.primary_language,
            "has_backend": self.has_backend,
            "has_frontend": self.has_frontend,
            "has_database": self.has_database,
            "description": self.description,
        }

    def get_agent_types(self) -> list[str]:
        """Get specialized agent types for this profile."""
        agent_types = []

        if self.project_type == ProjectType.ELECTRON_APP:
            agent_types.extend(["electron-main", "electron-renderer", "electron-preload"])

        if self.has_frontend:
            agent_types.append("frontend")

        if self.has_backend:
            agent_types.append("backend")

        if self.has_database:
            agent_types.append("database")

        if Domain.TESTING in self.domains:
            agent_types.append("testing")

        if Domain.DEVOPS in self.domains:
            agent_types.append("devops")

        if Domain.SECURITY in self.domains:
            agent_types.append("security")

        # Always have a general agent as fallback
        if not agent_types:
            agent_types.append("general")

        return agent_types

    def get_validators(self) -> list[str]:
        """Get validator types for this profile."""
        validators = ["dependencies"]  # Always check dependencies

        if Technology.TYPESCRIPT in self.technologies:
            validators.append("typescript")

        if self.project_type == ProjectType.ELECTRON_APP:
            validators.extend(["electron", "build"])

        elif self.project_type in [ProjectType.WEB_APP, ProjectType.FULLSTACK]:
            validators.append("build")

        elif self.project_type == ProjectType.API_SERVER:
            validators.append("python" if self.primary_language == "python" else "build")

        return validators


class ProjectAnalyzer:
    """
    Analyzes requirements to determine project profile.

    Uses keyword analysis, pattern matching, and heuristics to understand
    what kind of project is being built.
    """

    # Keywords for project type detection
    PROJECT_TYPE_KEYWORDS = {
        ProjectType.ELECTRON_APP: [
            "electron", "desktop app", "desktop application", "native app",
            "system tray", "menu bar", "ipc", "main process", "renderer",
            "browserwindow", "cross-platform desktop",
        ],
        ProjectType.WEB_APP: [
            "web app", "web application", "website", "spa", "single page",
            "responsive", "browser", "html", "css",
        ],
        ProjectType.API_SERVER: [
            "api", "rest", "graphql", "server", "backend", "endpoint",
            "microservice", "webhook",
        ],
        ProjectType.CLI_TOOL: [
            "cli", "command line", "terminal", "console app", "shell",
            "argv", "argparse", "click",
        ],
        ProjectType.MOBILE_APP: [
            "mobile", "ios", "android", "react native", "flutter",
            "smartphone", "tablet",
        ],
        ProjectType.GAME: [
            "game", "pygame", "phaser", "unity", "sprite", "collision",
            "player", "enemy", "score", "level",
        ],
        ProjectType.LIBRARY: [
            "library", "package", "module", "sdk", "npm package",
            "pip package", "reusable",
        ],
    }

    # Keywords for technology detection
    TECHNOLOGY_KEYWORDS = {
        Technology.ELECTRON: ["electron", "electron-vite", "electronbuilder"],
        Technology.REACT: ["react", "jsx", "tsx", "hooks", "usestate", "useeffect", "component"],
        Technology.VUE: ["vue", "vuex", "pinia", "vue3"],
        Technology.TYPESCRIPT: ["typescript", "ts", ".ts", "types", "interface"],
        Technology.PYTHON: ["python", "pip", "pytest", "fastapi", "django", "flask"],
        Technology.FASTAPI: ["fastapi", "pydantic", "uvicorn"],
        Technology.DJANGO: ["django", "drf", "django rest"],
        Technology.POSTGRESQL: ["postgresql", "postgres", "pg"],
        Technology.MONGODB: ["mongodb", "mongoose", "mongo"],
        Technology.SQLITE: ["sqlite", "sqlite3"],
        Technology.DOCKER: ["docker", "dockerfile", "container"],
        Technology.VITE: ["vite", "electron-vite"],
        Technology.WEBSOCKET: ["websocket", "socket.io", "ws://", "wss://"],
        Technology.GRAPHQL: ["graphql", "apollo", "gql"],
        Technology.PYGAME: ["pygame"],
        Technology.PHASER: ["phaser"],
    }

    # Keywords for domain detection
    DOMAIN_KEYWORDS = {
        Domain.UI: ["ui", "button", "display", "render", "visual", "component", "layout", "style"],
        Domain.API: ["api", "endpoint", "route", "request", "response", "http"],
        Domain.DATABASE: ["database", "db", "query", "table", "model", "migration", "storage"],
        Domain.AUTH: ["auth", "login", "logout", "session", "token", "jwt", "oauth", "permission"],
        Domain.FILE_SYSTEM: ["file", "directory", "path", "read", "write", "fs", "io"],
        Domain.NETWORKING: ["network", "socket", "http", "fetch", "download", "upload"],
        Domain.IPC: ["ipc", "ipcmain", "ipcrenderer", "invoke", "handle", "contextbridge"],
        Domain.GRAPHICS: ["canvas", "webgl", "opengl", "graphics", "draw", "render", "sprite"],
        Domain.AUDIO: ["audio", "sound", "music", "volume", "play", "mp3", "wav"],
        Domain.TESTING: ["test", "spec", "jest", "pytest", "mocha", "unittest"],
        Domain.DEVOPS: ["deploy", "ci", "cd", "docker", "kubernetes", "pipeline"],
        Domain.SECURITY: ["security", "encrypt", "decrypt", "hash", "ssl", "tls", "sanitize"],
    }

    def __init__(self):
        self.logger = logger.bind(component="project_analyzer")

    def analyze(self, req_data: RequirementsData) -> ProjectProfile:
        """
        Analyze requirements and return a ProjectProfile.

        Args:
            req_data: Parsed requirements data

        Returns:
            ProjectProfile with detected characteristics
        """
        self.logger.info("analyzing_project", req_count=len(req_data.requirements))

        # Collect all text for analysis
        all_text = self._collect_text(req_data)
        all_text_lower = all_text.lower()

        # Detect project type
        project_type = self._detect_project_type(all_text_lower, req_data)

        # Detect technologies
        technologies = self._detect_technologies(all_text_lower)

        # Detect domains
        domains = self._detect_domains(all_text_lower)

        # Detect platforms
        platforms = self._detect_platforms(all_text_lower, project_type)

        # Determine complexity
        complexity = self._assess_complexity(req_data)

        # Determine primary language
        primary_language = self._detect_primary_language(technologies, project_type)

        # Create profile
        description = req_data.summary.get("description", "") if req_data.summary else ""
        profile = ProjectProfile(
            project_type=project_type,
            technologies=technologies,
            platforms=platforms,
            domains=domains,
            complexity=complexity,
            primary_language=primary_language,
            has_backend=Domain.API in domains or Domain.DATABASE in domains,
            has_frontend=Domain.UI in domains,
            has_database=Domain.DATABASE in domains,
            description=description,
        )

        self.logger.info(
            "project_analyzed",
            project_type=profile.project_type.value,
            technologies=[t.value for t in profile.technologies],
            domains=[d.value for d in profile.domains],
            complexity=profile.complexity,
        )

        return profile

    def _collect_text(self, req_data: RequirementsData) -> str:
        """Collect all text from requirements for analysis."""
        parts = []

        # Get project name and description from summary dict
        if req_data.summary:
            if req_data.summary.get("project_name"):
                parts.append(req_data.summary["project_name"])
            if req_data.summary.get("description"):
                parts.append(req_data.summary["description"])

        # Collect from requirements (list of dicts)
        for req in req_data.requirements:
            if isinstance(req, dict):
                if req.get("name"):
                    parts.append(req["name"])
                if req.get("description"):
                    parts.append(req["description"])
                if req.get("details"):
                    parts.append(req["details"])
            else:
                # Handle DAGNode objects
                parts.append(str(req.name if hasattr(req, 'name') else req))

        # Also collect from nodes
        for node in req_data.nodes:
            parts.append(node.name)
            if node.payload:
                for key, value in node.payload.items():
                    if isinstance(value, str):
                        parts.append(value)

        return " ".join(parts)

    def _detect_project_type(
        self,
        text: str,
        req_data: RequirementsData
    ) -> ProjectType:
        """Detect the primary project type."""
        scores: dict[ProjectType, int] = {pt: 0 for pt in ProjectType}

        # Score based on keywords
        project_description = req_data.summary.get("description", "") if req_data.summary else ""
        for project_type, keywords in self.PROJECT_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    scores[project_type] += 1
                    # Bonus for exact matches in project description
                    if project_description and keyword in project_description.lower():
                        scores[project_type] += 2

        # Check for specific patterns
        if "electron" in text:
            scores[ProjectType.ELECTRON_APP] += 5

        if "react native" in text or "flutter" in text:
            scores[ProjectType.MOBILE_APP] += 5

        # If has both frontend and backend indicators, might be fullstack
        frontend_indicators = ["react", "vue", "component", "ui", "css"]
        backend_indicators = ["api", "server", "database", "endpoint"]

        has_frontend = any(ind in text for ind in frontend_indicators)
        has_backend = any(ind in text for ind in backend_indicators)

        if has_frontend and has_backend:
            scores[ProjectType.FULLSTACK] += 3

        # Find the highest scoring type
        best_type = max(scores.keys(), key=lambda k: scores[k])

        if scores[best_type] == 0:
            return ProjectType.UNKNOWN

        return best_type

    def _detect_technologies(self, text: str) -> list[Technology]:
        """Detect technologies mentioned in requirements."""
        detected = []

        for tech, keywords in self.TECHNOLOGY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    if tech not in detected:
                        detected.append(tech)
                    break

        # Infer related technologies
        if Technology.ELECTRON in detected:
            if Technology.TYPESCRIPT not in detected:
                detected.append(Technology.TYPESCRIPT)
            if Technology.VITE not in detected:
                detected.append(Technology.VITE)

        if Technology.REACT in detected and Technology.TYPESCRIPT not in detected:
            # React projects often use TypeScript
            detected.append(Technology.TYPESCRIPT)

        return detected

    def _detect_domains(self, text: str) -> list[Domain]:
        """Detect functional domains in the project."""
        detected = []

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    if domain not in detected:
                        detected.append(domain)
                    break

        return detected

    def _detect_platforms(
        self,
        text: str,
        project_type: ProjectType
    ) -> list[str]:
        """Detect target platforms."""
        platforms = []

        if "windows" in text:
            platforms.append("windows")
        if "macos" in text or "mac os" in text or "osx" in text:
            platforms.append("macos")
        if "linux" in text:
            platforms.append("linux")
        if "web" in text or "browser" in text:
            platforms.append("web")
        if "ios" in text:
            platforms.append("ios")
        if "android" in text:
            platforms.append("android")

        # Default platforms based on project type
        if not platforms:
            if project_type == ProjectType.ELECTRON_APP:
                platforms = ["windows", "macos", "linux"]
            elif project_type == ProjectType.WEB_APP:
                platforms = ["web"]
            elif project_type == ProjectType.MOBILE_APP:
                platforms = ["ios", "android"]
            elif project_type in [ProjectType.API_SERVER, ProjectType.CLI_TOOL]:
                platforms = ["linux", "windows", "macos"]

        return platforms

    def _assess_complexity(self, req_data: RequirementsData) -> str:
        """Assess project complexity based on requirements."""
        req_count = len(req_data.requirements)

        # Count depth of DAG
        max_depth = 0
        for req in req_data.requirements:
            # Handle both object and dict formats
            if hasattr(req, 'depends_on'):
                deps = req.depends_on
            elif isinstance(req, dict):
                deps = req.get('depends_on', [])
            else:
                deps = []
            max_depth = max(max_depth, len(deps) if deps else 0)

        if req_count <= 10 and max_depth <= 2:
            return "simple"
        elif req_count <= 30 and max_depth <= 5:
            return "medium"
        else:
            return "complex"

    def _detect_primary_language(
        self,
        technologies: list[Technology],
        project_type: ProjectType
    ) -> str:
        """Determine the primary programming language."""
        if Technology.PYTHON in technologies:
            return "python"

        if Technology.RUST in technologies:
            return "rust"

        if Technology.GO in technologies:
            return "go"

        if Technology.TYPESCRIPT in technologies:
            return "typescript"

        # Default based on project type
        if project_type in [ProjectType.ELECTRON_APP, ProjectType.WEB_APP, ProjectType.FULLSTACK]:
            return "typescript"
        elif project_type == ProjectType.API_SERVER:
            return "python"
        elif project_type == ProjectType.CLI_TOOL:
            return "python"

        return "typescript"

    # -------------------------------------------------------------------------
    # Cached Pattern Classification Methods
    # -------------------------------------------------------------------------

    def _pattern_classify_project_type(self, text: str) -> ClassificationResult:
        """
        Pattern-based project type classification with scoring.

        Args:
            text: Lowercase project text for analysis

        Returns:
            ClassificationResult with project type and confidence
        """
        scores: dict[str, int] = {}

        for project_type, keywords in self.PROJECT_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[project_type.value] = score

        # Boost for specific high-confidence patterns
        if "electron" in text:
            scores[ProjectType.ELECTRON_APP.value] = scores.get(ProjectType.ELECTRON_APP.value, 0) + 5
        if "react native" in text or "flutter" in text:
            scores[ProjectType.MOBILE_APP.value] = scores.get(ProjectType.MOBILE_APP.value, 0) + 5
        if "pygame" in text or "phaser" in text:
            scores[ProjectType.GAME.value] = scores.get(ProjectType.GAME.value, 0) + 5

        # Check for fullstack indicators
        frontend_indicators = ["react", "vue", "component", "ui", "css"]
        backend_indicators = ["api", "server", "database", "endpoint"]
        has_frontend = any(ind in text for ind in frontend_indicators)
        has_backend = any(ind in text for ind in backend_indicators)
        if has_frontend and has_backend:
            scores[ProjectType.FULLSTACK.value] = scores.get(ProjectType.FULLSTACK.value, 0) + 3

        if not scores:
            return ClassificationResult(
                category=ProjectType.UNKNOWN.value,
                confidence=0.2,
                source=ClassificationSource.PATTERN,
                metadata={},
            )

        best_type = max(scores.keys(), key=lambda k: scores[k])
        best_score = scores[best_type]
        confidence = min(1.0, 0.4 + (best_score * 0.1))

        return ClassificationResult(
            category=best_type,
            confidence=confidence,
            source=ClassificationSource.PATTERN,
            metadata={"scores": scores, "best_score": best_score},
        )

    async def _llm_classify_project_type(self, text: str) -> ClassificationResult:
        """
        LLM-based project type classification for ambiguous cases.

        Args:
            text: Project text for analysis

        Returns:
            ClassificationResult with project type and confidence
        """
        claude_tool = _get_claude_tool()
        if not claude_tool:
            return ClassificationResult(
                category=ProjectType.UNKNOWN.value,
                confidence=0.3,
                source=ClassificationSource.LLM,
                metadata={"error": "claude_tool_unavailable"},
            )

        prompt = f"""Classify this project description into ONE type:

Description: {text[:800]}

Types:
- electron-app: Desktop app with Electron
- web-app: Web application (React/Vue/Svelte SPA)
- api-server: Backend API service
- cli-tool: Command-line tool
- mobile-app: iOS/Android app
- game: Video game
- library: Reusable package/SDK
- fullstack: Combined frontend + backend + database

Return JSON: {{"type": "...", "confidence": 0.0-1.0, "reasoning": "..."}}
"""
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(claude_tool.execute, prompt, skill="environment-config"),
                timeout=30.0,
            )
            if result:
                json_match = re.search(r'\{[^{}]*\}', str(result))
                if json_match:
                    data = json.loads(json_match.group())
                    return ClassificationResult(
                        category=data.get("type", "unknown"),
                        confidence=data.get("confidence", 0.7),
                        source=ClassificationSource.LLM,
                        metadata={"reasoning": data.get("reasoning", "")},
                    )
        except Exception as e:
            self.logger.debug("llm_project_type_failed", error=str(e))

        return ClassificationResult(
            category=ProjectType.UNKNOWN.value,
            confidence=0.3,
            source=ClassificationSource.LLM,
        )

    async def classify_project_type_cached(self, text: str) -> ProjectType:
        """
        Classify project type with caching and LLM fallback.

        Args:
            text: Lowercase project text for analysis

        Returns:
            ProjectType enum value
        """
        cache = get_classification_cache()
        key = cache._generate_key(text[:500], "project_type")

        # Check cache
        cached = await cache.get(key)
        if cached:
            try:
                return ProjectType(cached.category)
            except ValueError:
                pass

        # Try pattern classification
        pattern_result = self._pattern_classify_project_type(text)
        if pattern_result.confidence >= 0.7:
            await cache.set(key, pattern_result)
            try:
                return ProjectType(pattern_result.category)
            except ValueError:
                return ProjectType.UNKNOWN

        # LLM fallback for low confidence
        llm_result = await self._llm_classify_project_type(text)
        if llm_result.confidence > pattern_result.confidence:
            await cache.set(key, llm_result)
            try:
                return ProjectType(llm_result.category)
            except ValueError:
                return ProjectType.UNKNOWN

        await cache.set(key, pattern_result)
        try:
            return ProjectType(pattern_result.category)
        except ValueError:
            return ProjectType.UNKNOWN

    def _pattern_classify_technologies(self, text: str) -> list[Technology]:
        """
        Pattern-based technology detection.

        Args:
            text: Lowercase project text for analysis

        Returns:
            List of detected Technology enum values
        """
        detected = []

        for tech, keywords in self.TECHNOLOGY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    if tech not in detected:
                        detected.append(tech)
                    break

        # Infer related technologies
        if Technology.ELECTRON in detected:
            if Technology.TYPESCRIPT not in detected:
                detected.append(Technology.TYPESCRIPT)
            if Technology.VITE not in detected:
                detected.append(Technology.VITE)

        if Technology.REACT in detected and Technology.TYPESCRIPT not in detected:
            detected.append(Technology.TYPESCRIPT)

        return detected

    def _pattern_classify_domains(self, text: str) -> list[Domain]:
        """
        Pattern-based domain detection.

        Args:
            text: Lowercase project text for analysis

        Returns:
            List of detected Domain enum values
        """
        detected = []

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    if domain not in detected:
                        detected.append(domain)
                    break

        return detected

    async def detect_project_type_with_llm(
        self,
        file_list: list[str],
        package_contents: Optional[dict] = None,
        requirements_txt: Optional[str] = None,
    ) -> dict:
        """
        Use LLM to analyze project structure and determine its type.

        This provides semantic understanding beyond simple keyword matching,
        handling hybrid projects, monorepos, and edge cases.

        Args:
            file_list: List of file paths in the project
            package_contents: Contents of package.json if available
            requirements_txt: Contents of requirements.txt if available

        Returns:
            Dict with type, framework, monorepo info, build_cmd, test_cmd
        """
        claude_tool = _get_claude_tool()
        if not claude_tool:
            self.logger.warning("llm_project_detection_unavailable", reason="claude_tool_not_found")
            return self._fallback_project_detection(file_list, package_contents, requirements_txt)

        # Prepare file structure summary (limit to avoid token issues)
        file_summary = "\n".join(file_list[:100])
        if len(file_list) > 100:
            file_summary += f"\n... and {len(file_list) - 100} more files"

        # Format package.json if available
        package_json_str = ""
        if package_contents:
            # Only include relevant fields to save tokens
            relevant_keys = ["name", "type", "main", "scripts", "dependencies", "devDependencies"]
            filtered_package = {k: v for k, v in package_contents.items() if k in relevant_keys}
            package_json_str = json.dumps(filtered_package, indent=2)[:2000]

        prompt = f"""Analyze this project structure and determine its type:

FILES:
{file_summary}

PACKAGE.JSON:
{package_json_str if package_json_str else "N/A"}

REQUIREMENTS.TXT:
{requirements_txt[:500] if requirements_txt else "N/A"}

Determine:
1. Primary type: electron | react | fullstack | node | python | vue | svelte | nextjs | fastapi | django | flask | cli | library
2. Framework: vite | next | express | fastapi | django | flask | electron-vite | none
3. Is it a monorepo? If so, list package names
4. Build system: npm | yarn | pnpm | pip | poetry | none
5. Test framework: vitest | jest | pytest | playwright | none

Return ONLY valid JSON in this exact format:
{{"type": "string", "framework": "string", "monorepo": false, "packages": [], "build_cmd": "string", "test_cmd": "string", "confidence": 0.9}}"""

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    claude_tool.execute,
                    prompt,
                    skill="environment-config",
                ),
                timeout=45.0,
            )

            if result and isinstance(result, str):
                # Extract JSON from response
                json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    self.logger.info(
                        "llm_project_type_detected",
                        project_type=parsed.get("type"),
                        framework=parsed.get("framework"),
                        confidence=parsed.get("confidence", 0),
                    )
                    return parsed

            self.logger.warning("llm_project_detection_parse_failed", result_preview=str(result)[:200])
            return self._fallback_project_detection(file_list, package_contents, requirements_txt)

        except asyncio.TimeoutError:
            self.logger.warning("llm_project_detection_timeout")
            return self._fallback_project_detection(file_list, package_contents, requirements_txt)
        except Exception as e:
            self.logger.warning("llm_project_detection_error", error=str(e))
            return self._fallback_project_detection(file_list, package_contents, requirements_txt)

    def _fallback_project_detection(
        self,
        file_list: list[str],
        package_contents: Optional[dict] = None,
        requirements_txt: Optional[str] = None,
    ) -> dict:
        """
        Rule-based project detection as fallback when LLM is unavailable.

        Uses file patterns and package.json analysis for detection.
        """
        result = {
            "type": "unknown",
            "framework": "none",
            "monorepo": False,
            "packages": [],
            "build_cmd": "npm run build",
            "test_cmd": "npm test",
            "confidence": 0.5,
        }

        files_str = " ".join(file_list).lower()

        # Detect monorepo patterns
        if any(f in files_str for f in ["packages/", "apps/", "lerna.json", "pnpm-workspace"]):
            result["monorepo"] = True
            # Extract package names
            for f in file_list:
                if "/packages/" in f or "/apps/" in f:
                    parts = f.split("/")
                    for i, p in enumerate(parts):
                        if p in ("packages", "apps") and i + 1 < len(parts):
                            pkg_name = parts[i + 1]
                            if pkg_name not in result["packages"]:
                                result["packages"].append(pkg_name)

        # Check package.json for hints
        if package_contents:
            deps = {
                **package_contents.get("dependencies", {}),
                **package_contents.get("devDependencies", {}),
            }
            scripts = package_contents.get("scripts", {})

            # Detect type from dependencies
            if "electron" in deps or "electron-vite" in deps:
                result["type"] = "electron"
                result["framework"] = "electron-vite" if "electron-vite" in deps else "electron"
            elif "next" in deps:
                result["type"] = "nextjs"
                result["framework"] = "next"
            elif "react" in deps:
                result["type"] = "react"
                result["framework"] = "vite" if "vite" in deps else "none"
            elif "vue" in deps:
                result["type"] = "vue"
                result["framework"] = "vite" if "vite" in deps else "none"
            elif "svelte" in deps:
                result["type"] = "svelte"
                result["framework"] = "vite" if "vite" in deps else "none"
            elif "express" in deps or "fastify" in deps:
                result["type"] = "node"
                result["framework"] = "express" if "express" in deps else "fastify"

            # Detect test framework
            if "vitest" in deps:
                result["test_cmd"] = "npm run test" if "test" in scripts else "npx vitest"
            elif "jest" in deps:
                result["test_cmd"] = "npm run test" if "test" in scripts else "npx jest"
            elif "playwright" in deps:
                result["test_cmd"] = "npx playwright test"

            # Get build command from scripts
            if "build" in scripts:
                result["build_cmd"] = "npm run build"

        # Check for Python project
        if requirements_txt or "requirements.txt" in files_str or "pyproject.toml" in files_str:
            result["type"] = "python"
            result["build_cmd"] = "pip install -r requirements.txt"
            result["test_cmd"] = "pytest"

            if requirements_txt:
                if "fastapi" in requirements_txt.lower():
                    result["framework"] = "fastapi"
                elif "django" in requirements_txt.lower():
                    result["framework"] = "django"
                elif "flask" in requirements_txt.lower():
                    result["framework"] = "flask"

        # Detect fullstack from file patterns
        if result["type"] in ("react", "vue", "svelte"):
            backend_patterns = ["api/", "server/", "backend/", "prisma/", "routes/"]
            if any(p in files_str for p in backend_patterns):
                result["type"] = "fullstack"

        self.logger.info(
            "fallback_project_detection_complete",
            project_type=result["type"],
            framework=result["framework"],
        )
        return result

    async def analyze_with_llm(
        self,
        req_data: RequirementsData,
        project_dir: Optional[Path] = None,
    ) -> ProjectProfile:
        """
        Analyze requirements with LLM enhancement for better detection.

        Args:
            req_data: Parsed requirements data
            project_dir: Optional project directory to scan

        Returns:
            ProjectProfile with LLM-enhanced detection
        """
        # First do standard analysis
        profile = self.analyze(req_data)

        # If project directory provided, use LLM for deeper analysis
        if project_dir and project_dir.exists():
            try:
                # Collect file list
                file_list = [
                    str(f.relative_to(project_dir))
                    for f in project_dir.rglob("*")
                    if f.is_file() and not any(
                        p in str(f) for p in ["node_modules", ".git", "__pycache__", ".next", "dist"]
                    )
                ][:200]

                # Read package.json if exists
                package_contents = None
                package_json = project_dir / "package.json"
                if package_json.exists():
                    package_contents = json.loads(package_json.read_text())

                # Read requirements.txt if exists
                requirements_txt = None
                req_file = project_dir / "requirements.txt"
                if req_file.exists():
                    requirements_txt = req_file.read_text()[:1000]

                # Get LLM detection
                llm_result = await self.detect_project_type_with_llm(
                    file_list, package_contents, requirements_txt
                )

                # Merge LLM insights with standard analysis
                if llm_result.get("confidence", 0) > 0.7:
                    type_mapping = {
                        "electron": ProjectType.ELECTRON_APP,
                        "react": ProjectType.WEB_APP,
                        "vue": ProjectType.WEB_APP,
                        "svelte": ProjectType.WEB_APP,
                        "nextjs": ProjectType.FULLSTACK,
                        "fullstack": ProjectType.FULLSTACK,
                        "node": ProjectType.API_SERVER,
                        "python": ProjectType.API_SERVER,
                        "fastapi": ProjectType.API_SERVER,
                        "django": ProjectType.API_SERVER,
                        "flask": ProjectType.API_SERVER,
                        "cli": ProjectType.CLI_TOOL,
                        "library": ProjectType.LIBRARY,
                    }
                    llm_type = llm_result.get("type", "").lower()
                    if llm_type in type_mapping:
                        profile.project_type = type_mapping[llm_type]

                    # Update technologies from framework detection
                    framework = llm_result.get("framework", "").lower()
                    framework_tech = {
                        "vite": Technology.VITE,
                        "next": Technology.REACT,
                        "express": Technology.EXPRESS,
                        "fastapi": Technology.FASTAPI,
                        "django": Technology.DJANGO,
                        "flask": Technology.FLASK,
                        "electron-vite": Technology.ELECTRON,
                    }
                    if framework in framework_tech:
                        tech = framework_tech[framework]
                        if tech not in profile.technologies:
                            profile.technologies.append(tech)

                    self.logger.info(
                        "llm_enhanced_analysis_complete",
                        project_type=profile.project_type.value,
                        llm_confidence=llm_result.get("confidence", 0),
                    )

            except Exception as e:
                self.logger.warning("llm_enhanced_analysis_failed", error=str(e))

        return profile


def analyze_requirements(req_data: RequirementsData) -> ProjectProfile:
    """
    Convenience function to analyze requirements.

    Args:
        req_data: Parsed requirements data

    Returns:
        ProjectProfile
    """
    analyzer = ProjectAnalyzer()
    return analyzer.analyze(req_data)
