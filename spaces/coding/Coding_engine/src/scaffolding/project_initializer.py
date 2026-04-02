"""
Project Initializer - Creates complete project structure before code generation.

Ensures that all essential files exist:
- package.json with dependencies
- tsconfig.json / vite.config.ts
- Entry points (main.ts, index.html, App.tsx)
- Directory structure (src/, tests/, public/)
- Runs npm install automatically
"""

import asyncio
import json
import os
import subprocess
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class ProjectType(Enum):
    """Supported project types."""
    REACT_VITE = "react_vite"
    REACT_ELECTRON = "react_electron"
    NODE_EXPRESS = "node_express"
    FULLSTACK = "fullstack"  # React frontend + Express backend
    NESTJS_FULLSTACK = "nestjs_fullstack"  # React frontend + NestJS backend + Prisma
    PYTHON_FASTAPI = "python_fastapi"
    UNKNOWN = "unknown"


class ThemeType(Enum):
    """Supported UI themes for React projects."""
    DEFAULT = "default"  # Basic Vite dark theme
    VIBEMIND_SPACE = "vibemind_space"  # VibeMind Space Theme with Purple/Violet accents


@dataclass
class ScaffoldResult:
    """Result of project scaffolding."""
    success: bool
    project_type: ProjectType
    files_created: list[str] = field(default_factory=list)
    files_verified: list[str] = field(default_factory=list)
    dependencies_installed: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "project_type": self.project_type.value,
            "files_created": self.files_created,
            "files_verified": self.files_verified,
            "dependencies_installed": self.dependencies_installed,
            "errors": self.errors,
        }


class ProjectInitializer:
    """
    Initializes project structure before code generation.

    Ensures all essential files exist and dependencies are installed.
    Supports theming via ThemeType - VibeMind Space Theme for modern dark UI.
    """

    # Essential files per project type (always includes .claude/CLAUDE.md for Claude Code integration)
    ESSENTIAL_FILES = {
        ProjectType.REACT_VITE: [
            "package.json",
            "tsconfig.json",
            "vite.config.ts",
            "index.html",
            "src/main.tsx",
            "src/App.tsx",
            "src/index.css",  # Base styles for React app
            ".claude/CLAUDE.md",
        ],
        ProjectType.REACT_ELECTRON: [
            "package.json",
            "tsconfig.json",
            "vite.config.ts",
            "electron.vite.config.ts",
            "src/renderer/index.html",
            "src/renderer/main.tsx",
            "src/renderer/App.tsx",
            "src/main/main.ts",
            "src/preload/preload.ts",
            ".claude/CLAUDE.md",
        ],
        ProjectType.NODE_EXPRESS: [
            "package.json",
            "tsconfig.json",
            "src/index.ts",
            "src/app.ts",
            ".claude/CLAUDE.md",
        ],
        ProjectType.FULLSTACK: [
            "package.json",
            "tsconfig.json",
            "vite.config.ts",
            "index.html",
            ".env",
            "src/main.tsx",
            "src/App.tsx",
            "src/index.css",  # Base styles for React app
            "src/server.ts",
            "src/lib/prisma.ts",
            "prisma/schema.prisma",
            "prisma/seed.ts",
            ".claude/CLAUDE.md",
        ],
        ProjectType.NESTJS_FULLSTACK: [
            "package.json",
            "tsconfig.json",
            "tsconfig.build.json",
            ".env",
            "nest-cli.json",
            "src/main.ts",
            "src/app.module.ts",
            "src/app.controller.ts",
            "src/app.service.ts",
            "src/prisma.service.ts",
            "src/prisma/prisma.module.ts",
            "src/gateway/events.gateway.ts",
            "src/gateway/events.module.ts",
            "prisma/schema.prisma",
            "frontend/package.json",
            "frontend/tsconfig.json",
            "frontend/vite.config.ts",
            "frontend/index.html",
            "frontend/src/main.tsx",
            "frontend/src/App.tsx",
            "frontend/.env",
            "Dockerfile",
            ".github/workflows/ci.yml",
            ".claude/CLAUDE.md",
        ],
        ProjectType.PYTHON_FASTAPI: [
            "requirements.txt",
            "pyproject.toml",
            "src/main.py",
            "src/app.py",
            ".claude/CLAUDE.md",
        ],
    }

    # Essential directories per project type (always includes .claude for Claude Code integration)
    ESSENTIAL_DIRS = {
        ProjectType.REACT_VITE: ["src", "src/components", "src/hooks", "src/utils", "public", "tests", ".claude"],
        ProjectType.REACT_ELECTRON: ["src", "src/main", "src/preload", "src/renderer", "src/components", "public", "tests", ".claude"],
        ProjectType.NODE_EXPRESS: ["src", "src/routes", "src/middleware", "src/utils", "tests", ".claude"],
        ProjectType.FULLSTACK: ["src", "src/components", "src/hooks", "src/api", "src/api/routes", "src/services", "src/types", "src/lib", "public", "tests", "prisma", ".claude"],
        ProjectType.NESTJS_FULLSTACK: [
            "src", "src/modules", "src/guards", "src/gateway", "prisma",
            "frontend/src", "frontend/src/pages", "frontend/src/components",
            "frontend/src/hooks", "frontend/src/api", "frontend/public",
            "tests", "__tests__", "__tests__/unit", "__tests__/integration",
            ".claude",
        ],
        ProjectType.PYTHON_FASTAPI: ["src", "src/routers", "src/models", "src/utils", "tests", ".claude"],
    }

    def __init__(self, output_dir: str, theme: ThemeType = ThemeType.VIBEMIND_SPACE):
        self.output_dir = Path(output_dir)
        self.theme = theme
        self.logger = logger.bind(component="project_initializer")

    def detect_project_type(self, requirements: dict) -> ProjectType:
        """Detect project type from requirements."""
        req_text = json.dumps(requirements).lower()

        # Check for Electron first (highest priority)
        if "electron" in req_text or "desktop" in req_text:
            return ProjectType.REACT_ELECTRON

        # Check for Fullstack (has both frontend AND backend indicators)
        frontend_indicators = ["react", "frontend", "ui", "dashboard", "component", "tsx"]
        backend_indicators = ["api", "express", "backend", "server", "endpoint", "route", "service", "database", "prisma"]

        has_frontend = any(ind in req_text for ind in frontend_indicators)
        has_backend = any(ind in req_text for ind in backend_indicators)

        # Check for NestJS specifically
        nestjs_indicators = ["nestjs", "nest.js", "nest ", "@nestjs"]
        if any(ind in req_text for ind in nestjs_indicators) and has_frontend:
            return ProjectType.NESTJS_FULLSTACK

        if has_frontend and has_backend:
            return ProjectType.FULLSTACK

        # Check for React only
        if "react" in req_text or "vite" in req_text or "frontend" in req_text:
            return ProjectType.REACT_VITE

        # Check for Python
        if "python" in req_text or "fastapi" in req_text or "django" in req_text:
            return ProjectType.PYTHON_FASTAPI

        # Check for Node/Express only
        if "node" in req_text or "express" in req_text or "api" in req_text:
            return ProjectType.NODE_EXPRESS

        # Default to React Vite
        return ProjectType.REACT_VITE

    async def initialize(
        self,
        requirements: dict,
        project_type: Optional[ProjectType] = None,
        install_deps: bool = True,
        theme: Optional[ThemeType] = None,
    ) -> ScaffoldResult:
        """
        Initialize project structure.

        Args:
            requirements: Parsed requirements dict
            project_type: Override project type detection
            install_deps: Whether to run npm/pip install
            theme: Override theme selection (defaults to VIBEMIND_SPACE)

        Returns:
            ScaffoldResult with details
        """
        detected_type = project_type or self.detect_project_type(requirements)
        active_theme = theme or self.theme

        self.logger.info(
            "initializing_project",
            output_dir=str(self.output_dir),
            project_type=detected_type.value,
            theme=active_theme.value,
        )

        result = ScaffoldResult(
            success=False,
            project_type=detected_type,
        )

        try:
            # Create output directory
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Create essential directories
            await self._create_directories(detected_type, result)

            # Create/verify essential files
            await self._create_essential_files(detected_type, requirements, result, active_theme)

            # Install dependencies
            if install_deps:
                await self._install_dependencies(detected_type, result)

            # Initialize git repository
            await self._init_git_repository(result)

            result.success = len(result.errors) == 0

        except Exception as e:
            result.errors.append(f"Initialization failed: {str(e)}")
            self.logger.error("initialization_failed", error=str(e))

        self.logger.info(
            "initialization_complete",
            success=result.success,
            files_created=len(result.files_created),
            errors=len(result.errors),
        )

        return result

    async def _create_directories(self, project_type: ProjectType, result: ScaffoldResult) -> None:
        """Create essential directories."""
        dirs = self.ESSENTIAL_DIRS.get(project_type, [])

        for dir_path in dirs:
            full_path = self.output_dir / dir_path
            if not full_path.exists():
                full_path.mkdir(parents=True, exist_ok=True)
                self.logger.debug("created_directory", path=str(full_path))

    async def _create_essential_files(
        self,
        project_type: ProjectType,
        requirements: dict,
        result: ScaffoldResult,
        theme: ThemeType = ThemeType.VIBEMIND_SPACE,
    ) -> None:
        """Create essential files if they don't exist."""
        files = list(self.ESSENTIAL_FILES.get(project_type, []))

        # Add tailwind.config.ts for VibeMind Space theme on React projects
        if theme == ThemeType.VIBEMIND_SPACE and project_type in (
            ProjectType.REACT_VITE,
            ProjectType.REACT_ELECTRON,
            ProjectType.FULLSTACK,
        ):
            files.append("tailwind.config.ts")
            files.append("postcss.config.js")

        for file_path in files:
            full_path = self.output_dir / file_path

            if full_path.exists():
                result.files_verified.append(file_path)
                continue

            # Generate content based on file type
            content = self._get_template_content(file_path, project_type, requirements, theme)

            if content:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
                result.files_created.append(file_path)
                self.logger.debug("created_file", path=file_path)
            else:
                self.logger.warning("no_template_for_file", path=file_path)

    def _get_template_content(
        self,
        file_path: str,
        project_type: ProjectType,
        requirements: dict,
        theme: ThemeType = ThemeType.VIBEMIND_SPACE,
    ) -> Optional[str]:
        """Get template content for a file."""
        project_name = requirements.get("project_name", "generated-app")

        # Use VibeMind Space Theme CSS for React projects with that theme
        use_vibemind = theme == ThemeType.VIBEMIND_SPACE and project_type in (
            ProjectType.REACT_VITE,
            ProjectType.REACT_ELECTRON,
            ProjectType.FULLSTACK,
        )

        templates = {
            "package.json": self._get_package_json(project_type, project_name, theme),
            "tsconfig.json": self._get_tsconfig(project_type),
            "vite.config.ts": self._get_vite_config(project_type, theme),  # Pass project_type for fullstack proxy
            "electron.vite.config.ts": self._get_electron_vite_config(),
            "index.html": self._get_index_html(project_name, theme),
            "src/main.tsx": self._get_main_tsx(),
            "src/App.tsx": self._get_app_tsx(theme),
            "src/index.css": self._get_vibemind_index_css() if use_vibemind else self._get_index_css(),
            "tailwind.config.ts": self._get_tailwind_config() if use_vibemind else None,
            "postcss.config.js": self._get_postcss_config() if use_vibemind else None,
            # Electron-vite renderer paths
            "src/renderer/index.html": self._get_electron_index_html(project_name),
            "src/renderer/main.tsx": self._get_main_tsx(),
            "src/renderer/App.tsx": self._get_app_tsx(),
            "src/main/main.ts": self._get_electron_main(),
            "src/preload/preload.ts": self._get_electron_preload(),
            "src/index.ts": self._get_node_index(),
            "src/app.ts": self._get_express_app(),
            "src/server.ts": self._get_fullstack_server(),
            ".env": self._get_env_file(project_type, project_name),
            "prisma/schema.prisma": self._get_prisma_schema(),
            "prisma/seed.ts": self._get_prisma_seed(project_name),
            "src/lib/prisma.ts": self._get_prisma_client(),
            "requirements.txt": self._get_python_requirements(),
            "pyproject.toml": self._get_pyproject_toml(project_name),
            "src/main.py": self._get_fastapi_main(),
            "src/app.py": self._get_fastapi_app(),
            # Claude Code integration
            ".claude/CLAUDE.md": self._get_claude_md(project_name, project_type, requirements),
            # NestJS Fullstack templates
            "tsconfig.build.json": self._get_nestjs_tsconfig_build() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "nest-cli.json": self._get_nestjs_cli_json() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/main.ts": self._get_nestjs_main() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/app.module.ts": self._get_nestjs_app_module() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/app.controller.ts": self._get_nestjs_app_controller(project_name) if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/app.service.ts": self._get_nestjs_app_service() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/prisma.service.ts": self._get_nestjs_prisma_service() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/prisma/prisma.module.ts": self._get_nestjs_prisma_module() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/gateway/events.gateway.ts": self._get_nestjs_events_gateway() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "src/gateway/events.module.ts": self._get_nestjs_events_module() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "frontend/package.json": self._get_nestjs_frontend_package_json(project_name) if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "frontend/tsconfig.json": self._get_nestjs_frontend_tsconfig() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "frontend/vite.config.ts": self._get_nestjs_frontend_vite_config() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "frontend/index.html": self._get_nestjs_frontend_index_html(project_name) if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "frontend/src/main.tsx": self._get_main_tsx() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "frontend/src/App.tsx": self._get_nestjs_frontend_app_tsx() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "frontend/.env": self._get_nestjs_frontend_env() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            "Dockerfile": self._get_nestjs_dockerfile() if project_type == ProjectType.NESTJS_FULLSTACK else None,
            ".github/workflows/ci.yml": self._get_nestjs_ci_yml() if project_type == ProjectType.NESTJS_FULLSTACK else None,
        }

        return templates.get(file_path)

    def _get_package_json(self, project_type: ProjectType, name: str, theme: ThemeType = ThemeType.VIBEMIND_SPACE) -> str:
        """Generate package.json based on project type."""
        base = {
            "name": name.lower().replace(" ", "-"),
            "version": "1.0.0",
            "private": True,
            "type": "module",
        }

        # Tailwind dependencies for VibeMind Space theme
        tailwind_deps = {}
        if theme == ThemeType.VIBEMIND_SPACE and project_type in (
            ProjectType.REACT_VITE,
            ProjectType.REACT_ELECTRON,
            ProjectType.FULLSTACK,
        ):
            tailwind_deps = {
                "tailwindcss": "^3.4.0",
                "postcss": "^8.4.0",
                "autoprefixer": "^10.4.0",
            }

        if project_type == ProjectType.REACT_VITE:
            return json.dumps({
                **base,
                "scripts": {
                    "dev": "vite",
                    "build": "tsc && vite build",
                    "preview": "vite preview",
                    "test": "vitest run",
                    "test:watch": "vitest",
                    "lint": "eslint . --ext ts,tsx",
                },
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                },
                "devDependencies": {
                    "@types/react": "^18.2.0",
                    "@types/react-dom": "^18.2.0",
                    "@vitejs/plugin-react": "^4.2.0",
                    "typescript": "^5.3.0",
                    "vite": "^5.0.0",
                    "vitest": "^1.0.0",
                    "@testing-library/react": "^14.0.0",
                    "@testing-library/jest-dom": "^6.0.0",
                    **tailwind_deps,
                },
            }, indent=2)

        elif project_type == ProjectType.REACT_ELECTRON:
            return json.dumps({
                **base,
                "main": "out/main/main.js",
                "scripts": {
                    "dev": "electron-vite dev",
                    "build": "electron-vite build",
                    "preview": "electron-vite preview",
                    "test": "vitest run",
                    "test:watch": "vitest",
                    "start": "electron out/main/main.js",
                },
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                },
                "devDependencies": {
                    "@types/react": "^18.2.0",
                    "@types/react-dom": "^18.2.0",
                    "@vitejs/plugin-react": "^4.2.0",
                    "electron": "^28.0.0",
                    "electron-vite": "^2.0.0",
                    "typescript": "^5.3.0",
                    "vite": "^5.0.0",
                    "vitest": "^1.0.0",
                    **tailwind_deps,
                },
            }, indent=2)

        elif project_type == ProjectType.NODE_EXPRESS:
            return json.dumps({
                **base,
                "scripts": {
                    "dev": "ts-node-dev src/index.ts",
                    "build": "tsc",
                    "start": "node dist/index.js",
                    "test": "vitest run",
                },
                "dependencies": {
                    "express": "^4.18.0",
                    "cors": "^2.8.0",
                },
                "devDependencies": {
                    "@types/express": "^4.17.0",
                    "@types/cors": "^2.8.0",
                    "@types/node": "^20.0.0",
                    "typescript": "^5.3.0",
                    "ts-node-dev": "^2.0.0",
                    "vitest": "^1.0.0",
                },
            }, indent=2)

        elif project_type == ProjectType.FULLSTACK:
            # Fullstack: React frontend + Express backend with Prisma database
            return json.dumps({
                **base,
                "description": "Fullstack application with React frontend, Express backend, and Prisma database",
                "scripts": {
                    "dev": "concurrently \"tsx watch src/server.ts\" \"vite\"",
                    "dev:backend": "tsx watch src/server.ts",
                    "dev:frontend": "vite",
                    "build": "tsc && vite build",
                    "start": "node dist/server.js",
                    "preview": "vite preview",
                    "test": "vitest run",
                    "test:watch": "vitest",
                    "lint": "eslint . --ext ts,tsx",
                    "typecheck": "tsc --noEmit",
                    "db:generate": "prisma generate",
                    "db:migrate": "prisma migrate dev",
                    "db:push": "prisma db push",
                    "db:seed": "prisma db seed",
                    "db:studio": "prisma studio",
                    "db:reset": "prisma migrate reset",
                },
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                    "express": "^4.18.0",
                    "cors": "^2.8.0",
                    "dotenv": "^16.3.0",
                    "zod": "^3.22.0",
                    "@prisma/client": "^5.0.0",
                    "bcryptjs": "^2.4.3",
                },
                "devDependencies": {
                    "concurrently": "^8.2.0",
                    "@types/react": "^18.2.0",
                    "@types/react-dom": "^18.2.0",
                    "@types/express": "^4.17.0",
                    "@types/cors": "^2.8.0",
                    "@types/node": "^20.0.0",
                    "@types/bcryptjs": "^2.4.6",
                    "@vitejs/plugin-react": "^4.2.0",
                    "typescript": "^5.3.0",
                    "tsx": "^4.7.0",
                    "vite": "^5.0.0",
                    "vitest": "^1.0.0",
                    "@testing-library/react": "^14.0.0",
                    "@testing-library/jest-dom": "^6.0.0",
                    "prisma": "^5.0.0",
                    **tailwind_deps,
                },
                "prisma": {
                    "seed": "tsx prisma/seed.ts"
                },
            }, indent=2)

        elif project_type == ProjectType.NESTJS_FULLSTACK:
            return self._get_nestjs_package_json(base.get("name", "app"))

        return json.dumps(base, indent=2)

    def _get_tsconfig(self, project_type: ProjectType) -> str:
        """Generate tsconfig.json."""
        base = {
            "compilerOptions": {
                "target": "ES2020",
                "useDefineForClassFields": True,
                "module": "ESNext",
                "lib": ["ES2020", "DOM", "DOM.Iterable"],
                "skipLibCheck": True,
                "moduleResolution": "bundler",
                "allowImportingTsExtensions": True,
                "resolveJsonModule": True,
                "isolatedModules": True,
                "noEmit": True,
                "strict": True,
                "noUnusedLocals": True,
                "noUnusedParameters": True,
                "noFallthroughCasesInSwitch": True,
            },
            "include": ["src"],
        }

        if project_type in (ProjectType.REACT_VITE, ProjectType.REACT_ELECTRON, ProjectType.FULLSTACK):
            base["compilerOptions"]["jsx"] = "react-jsx"
            # Disable noUnusedLocals for React projects - code generator may add
            # `import React` which isn't needed with react-jsx transform
            base["compilerOptions"]["noUnusedLocals"] = False

        if project_type == ProjectType.NODE_EXPRESS:
            base["compilerOptions"]["noEmit"] = False
            base["compilerOptions"]["outDir"] = "./dist"

        if project_type == ProjectType.NESTJS_FULLSTACK:
            return self._get_nestjs_tsconfig()

        return json.dumps(base, indent=2)

    def _get_vite_config(self, project_type: ProjectType, theme: ThemeType = ThemeType.VIBEMIND_SPACE) -> str:
        """Generate vite.config.ts."""
        if project_type == ProjectType.FULLSTACK:
            # Fullstack: Add proxy to backend API
            return '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
'''
        return '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
'''

    def _get_electron_vite_config(self) -> str:
        """Generate electron.vite.config.ts."""
        return '''import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
  },
  renderer: {
    plugins: [react()],
  },
})
'''

    def _get_index_html(self, title: str, theme: ThemeType = ThemeType.VIBEMIND_SPACE) -> str:
        """Generate index.html."""
        dark_class = ' class="dark"' if theme == ThemeType.VIBEMIND_SPACE else ''
        return f'''<!DOCTYPE html>
<html lang="en"{dark_class}>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
'''

    def _get_electron_index_html(self, title: str) -> str:
        """Generate index.html for electron-vite (in src/renderer/)."""
        return f'''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./main.tsx"></script>
  </body>
</html>
'''

    def _get_main_tsx(self) -> str:
        """Generate src/main.tsx."""
        return '''import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
'''

    def _get_app_tsx(self, theme: ThemeType = ThemeType.VIBEMIND_SPACE) -> str:
        """Generate src/App.tsx."""
        if theme == ThemeType.VIBEMIND_SPACE:
            return '''import React from 'react'

function App() {
  return (
    <div className="min-h-screen bg-gradient-nebula">
      {/* Navigation */}
      <nav className="glass-nav">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold gradient-text">VibeMind</h1>
          <div className="flex gap-4">
            <a href="#" className="text-slate-400 hover:text-neon-purple transition-colors">Home</a>
            <a href="#" className="text-slate-400 hover:text-neon-purple transition-colors">About</a>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="glass-card glass-card-hover p-8 text-center">
          <h2 className="text-4xl font-bold text-white mb-4">
            Welcome to <span className="gradient-text">VibeMind Space</span>
          </h2>
          <p className="text-slate-400 text-lg mb-8">
            A modern, dark space-themed application with glassmorphism effects
          </p>
          <div className="flex gap-4 justify-center">
            <button className="btn-primary">Get Started</button>
            <button className="btn-secondary">Learn More</button>
          </div>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
          <div className="glass-card glass-card-hover p-6">
            <div className="w-12 h-12 rounded-lg bg-neon-purple/20 flex items-center justify-center mb-4">
              <span className="text-2xl text-neon-purple">&#x2728;</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Modern Design</h3>
            <p className="text-slate-400">Sleek glassmorphism with purple accents</p>
          </div>
          <div className="glass-card glass-card-hover p-6">
            <div className="w-12 h-12 rounded-lg bg-neon-cyan/20 flex items-center justify-center mb-4">
              <span className="text-2xl text-neon-cyan">&#x26A1;</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Fast & Responsive</h3>
            <p className="text-slate-400">Built with React and Tailwind CSS</p>
          </div>
          <div className="glass-card glass-card-hover p-6">
            <div className="w-12 h-12 rounded-lg bg-neon-pink/20 flex items-center justify-center mb-4">
              <span className="text-2xl text-neon-pink">&#x1F680;</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Production Ready</h3>
            <p className="text-slate-400">TypeScript with full type safety</p>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
'''
        return '''import React from 'react'

function App() {
  return (
    <div className="app">
      <h1>Welcome to the App</h1>
    </div>
  )
}

export default App
'''

    def _get_index_css(self) -> str:
        """Generate src/index.css - base styles for React app."""
        return '''/* Base styles for the application */
:root {
  font-family: Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  font-weight: 400;

  color-scheme: light dark;
  color: rgba(255, 255, 255, 0.87);
  background-color: #242424;

  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  min-width: 320px;
  min-height: 100vh;
}

#root {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
}
'''

    def _get_vibemind_index_css(self) -> str:
        """Generate src/index.css with VibeMind Space Theme - dark glassmorphism with purple accents."""
        return '''/* VibeMind Space Theme - Global Styles */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Space Background */
    --bg-space-dark: #0a0a0f;
    --bg-space-mid: #12121a;
    --bg-space-light: #1a1a2e;
    --bg-card: rgba(20, 20, 35, 0.8);
    --bg-card-hover: rgba(30, 30, 50, 0.9);
    --bg-card-solid: #14141f;

    /* Neon Accents - Purple Dominant */
    --neon-purple: #a855f7;
    --neon-purple-dim: #7c3aed;
    --neon-cyan: #22d3ee;
    --neon-pink: #ec4899;
    --neon-blue: #3b82f6;

    /* Gradients */
    --gradient-cosmic: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #a855f7 100%);
    --gradient-aurora: linear-gradient(135deg, #22d3ee 0%, #a855f7 100%);
    --gradient-nebula: linear-gradient(180deg, #0a0a0f 0%, #1a1a2e 50%, #0a0a0f 100%);
    --gradient-glow: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

    /* Text */
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --text-dim: #475569;

    /* Status Colors */
    --status-success: #22c55e;
    --status-success-bg: rgba(34, 197, 94, 0.15);
    --status-warning: #f59e0b;
    --status-warning-bg: rgba(245, 158, 11, 0.15);
    --status-error: #ef4444;
    --status-error-bg: rgba(239, 68, 68, 0.15);
    --status-info: #3b82f6;
    --status-info-bg: rgba(59, 130, 246, 0.15);

    /* Glassmorphism */
    --glass-bg: rgba(255, 255, 255, 0.05);
    --glass-border: rgba(255, 255, 255, 0.1);
    --glass-border-hover: rgba(168, 85, 247, 0.3);

    /* Shadows */
    --shadow-glow: 0 0 20px rgba(168, 85, 247, 0.3);
    --shadow-glow-strong: 0 0 30px rgba(168, 85, 247, 0.5);
    --shadow-card: 0 8px 32px rgba(0, 0, 0, 0.4);

    /* Transitions */
    --transition-fast: 0.2s ease;
    --transition-normal: 0.3s ease;
    --transition-slow: 0.5s ease;

    /* Border Radius */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-xl: 24px;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    background: var(--gradient-nebula);
    background-attachment: fixed;
    color: var(--text-primary);
    min-height: 100vh;
  }

  #root {
    width: 100%;
    min-height: 100vh;
  }

  /* Global Link Styles */
  a {
    color: var(--neon-purple);
    text-decoration: none;
    transition: var(--transition-fast);
  }

  a:hover {
    color: var(--neon-cyan);
    text-shadow: var(--shadow-glow);
  }

  /* Scrollbar Styling */
  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    background: var(--bg-space-dark);
  }

  ::-webkit-scrollbar-thumb {
    background: var(--neon-purple-dim);
    border-radius: 4px;
  }

  ::-webkit-scrollbar-thumb:hover {
    background: var(--neon-purple);
  }

  /* Selection */
  ::selection {
    background: rgba(168, 85, 247, 0.3);
    color: var(--text-primary);
  }
}

@layer components {
  /* Glass Card */
  .glass-card {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card);
    transition: var(--transition-normal);
  }

  .glass-card-hover:hover {
    border-color: var(--glass-border-hover);
    box-shadow: var(--shadow-glow);
    transform: translateY(-2px);
  }

  /* Primary Button */
  .btn-primary {
    background: var(--gradient-cosmic);
    padding: 0.75rem 1.5rem;
    border-radius: var(--radius-md);
    font-weight: 600;
    color: white;
    border: none;
    cursor: pointer;
    box-shadow: var(--shadow-glow);
    transition: var(--transition-normal);
  }

  .btn-primary:hover {
    box-shadow: var(--shadow-glow-strong);
    transform: scale(1.05);
  }

  /* Secondary Button */
  .btn-secondary {
    background: transparent;
    padding: 0.75rem 1.5rem;
    border-radius: var(--radius-md);
    font-weight: 500;
    color: var(--text-secondary);
    border: 1px solid var(--glass-border);
    cursor: pointer;
    transition: var(--transition-normal);
  }

  .btn-secondary:hover {
    border-color: var(--neon-purple);
    color: var(--neon-purple);
    box-shadow: var(--shadow-glow);
  }

  /* Input Field */
  .input-field {
    width: 100%;
    background: rgba(10, 10, 15, 0.5);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-md);
    padding: 0.75rem 1rem;
    color: var(--text-primary);
    transition: var(--transition-fast);
  }

  .input-field::placeholder {
    color: var(--text-dim);
  }

  .input-field:focus {
    outline: none;
    border-color: var(--neon-purple);
    box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.2);
  }

  /* Glass Navigation */
  .glass-nav {
    background: rgba(10, 10, 15, 0.8);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--glass-border);
    position: sticky;
    top: 0;
    z-index: 50;
  }

  /* Status Badges */
  .badge-success {
    background: var(--status-success-bg);
    color: var(--status-success);
    border: 1px solid rgba(34, 197, 94, 0.3);
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .badge-warning {
    background: var(--status-warning-bg);
    color: var(--status-warning);
    border: 1px solid rgba(245, 158, 11, 0.3);
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .badge-error {
    background: var(--status-error-bg);
    color: var(--status-error);
    border: 1px solid rgba(239, 68, 68, 0.3);
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.875rem;
    font-weight: 500;
  }

  /* Utility Classes */
  .text-glow {
    text-shadow: 0 0 10px rgba(168, 85, 247, 0.5);
  }

  .border-glow {
    box-shadow: var(--shadow-glow);
  }

  .gradient-text {
    background: var(--gradient-cosmic);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .bg-gradient-nebula {
    background: var(--gradient-nebula);
    background-attachment: fixed;
  }

  .text-neon-purple { color: var(--neon-purple); }
  .text-neon-cyan { color: var(--neon-cyan); }
  .text-neon-pink { color: var(--neon-pink); }
  .bg-neon-purple\\/20 { background: rgba(168, 85, 247, 0.2); }
  .bg-neon-cyan\\/20 { background: rgba(34, 211, 238, 0.2); }
  .bg-neon-pink\\/20 { background: rgba(236, 72, 153, 0.2); }
}

/* Animations */
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 5px currentColor; }
  50% { box-shadow: 0 0 20px currentColor, 0 0 30px currentColor; }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@layer utilities {
  .animate-shimmer {
    animation: shimmer 2s linear infinite;
    background-size: 200% 100%;
  }

  .animate-pulse-glow {
    animation: pulse-glow 2s ease-in-out infinite;
  }

  .animate-fade-in {
    animation: fadeIn 0.5s ease forwards;
  }
}
'''

    def _get_tailwind_config(self) -> str:
        """Generate tailwind.config.ts for VibeMind Space Theme."""
        return '''import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        space: {
          dark: '#0a0a0f',
          mid: '#12121a',
          light: '#1a1a2e',
        },
        neon: {
          purple: '#a855f7',
          'purple-dim': '#7c3aed',
          cyan: '#22d3ee',
          pink: '#ec4899',
          blue: '#3b82f6',
        },
        glass: {
          bg: 'rgba(255, 255, 255, 0.05)',
          border: 'rgba(255, 255, 255, 0.1)',
        },
      },
      backgroundImage: {
        'gradient-cosmic': 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #a855f7 100%)',
        'gradient-aurora': 'linear-gradient(135deg, #22d3ee 0%, #a855f7 100%)',
        'gradient-nebula': 'linear-gradient(180deg, #0a0a0f 0%, #1a1a2e 50%, #0a0a0f 100%)',
      },
      boxShadow: {
        'glow': '0 0 20px rgba(168, 85, 247, 0.3)',
        'glow-strong': '0 0 30px rgba(168, 85, 247, 0.5)',
        'card': '0 8px 32px rgba(0, 0, 0, 0.4)',
      },
      animation: {
        'shimmer': 'shimmer 2s linear infinite',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'fade-in': 'fadeIn 0.5s ease forwards',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 5px currentColor' },
          '50%': { boxShadow: '0 0 20px currentColor, 0 0 30px currentColor' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
'''

    def _get_postcss_config(self) -> str:
        """Generate postcss.config.js for Tailwind CSS."""
        return '''export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
'''

    def _get_electron_main(self) -> str:
        """Generate src/main/main.ts for Electron."""
        # Use ESM imports - electron-vite's externalizeDepsPlugin handles electron properly
        return '''import { app, BrowserWindow } from 'electron'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
'''

    def _get_electron_preload(self) -> str:
        """Generate src/preload/preload.ts for Electron."""
        # Use ESM imports - electron-vite's externalizeDepsPlugin handles electron properly
        return '''import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  send: (channel: string, data: unknown) => {
    ipcRenderer.send(channel, data)
  },
  receive: (channel: string, func: (...args: unknown[]) => void) => {
    ipcRenderer.on(channel, (event, ...args) => func(...args))
  },
})
'''

    def _get_node_index(self) -> str:
        """Generate src/index.ts for Node."""
        return '''import { app } from './app'

const PORT = process.env.PORT || 3000

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`)
})
'''

    def _get_express_app(self) -> str:
        """Generate src/app.ts for Express."""
        return '''import express from 'express'
import cors from 'cors'

export const app = express()

app.use(cors())
app.use(express.json())

app.get('/health', (req, res) => {
  res.json({ status: 'ok' })
})

// Add your routes here
'''

    def _get_fullstack_server(self) -> str:
        """Generate src/server.ts for Fullstack projects with dynamic port fallback."""
        return '''import express from 'express'
import cors from 'cors'
import dotenv from 'dotenv'
import net from 'net'

dotenv.config()

const app = express()
const PORT = parseInt(process.env.PORT || '3001', 10)
const MAX_PORT_ATTEMPTS = 5

// Middleware
app.use(cors())
app.use(express.json())

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() })
})

// API routes placeholder
app.get('/api', (req, res) => {
  res.json({ message: 'API is running' })
})

// Dynamic port finder - prevents EADDRINUSE crashes
async function findAvailablePort(startPort: number): Promise<number> {
  for (let port = startPort; port < startPort + MAX_PORT_ATTEMPTS; port++) {
    const available = await new Promise<boolean>((resolve) => {
      const server = net.createServer()
      server.once('error', () => resolve(false))
      server.once('listening', () => {
        server.close(() => resolve(true))
      })
      server.listen(port)
    })
    if (available) return port
  }
  throw new Error(`No available port found starting from ${startPort}`)
}

// Start server with automatic port fallback
async function startServer() {
  const port = await findAvailablePort(PORT)

  if (port !== PORT) {
    console.log(`Port ${PORT} in use, using ${port} instead`)
  }

  app.listen(port, () => {
    console.log(`Server running at http://localhost:${port}`)
  })
}

startServer().catch(console.error)

export default app
'''

    def _get_env_file(self, project_type: ProjectType, project_name: str) -> str:
        """Generate .env for Fullstack projects with database configuration."""
        import secrets
        # Sanitize project name for database
        db_name = project_name.lower().replace(" ", "_").replace("-", "_")
        # Generate a random secret key for JWT
        secret_key = secrets.token_urlsafe(32)

        if project_type == ProjectType.NESTJS_FULLSTACK:
            return f'''# NestJS Backend
PORT=3000
NODE_ENV=development

# Database (PostgreSQL via Prisma) — separate DB per app
DATABASE_URL="postgresql://postgres:postgres@postgres:5432/{db_name}"

# JWT
JWT_SECRET="{secret_key}"
JWT_EXPIRY_HOURS=24

# Admin Seed
ADMIN_EMAIL="admin@{db_name}.com"
ADMIN_PASSWORD="admin123"
ADMIN_NAME="Admin User"
'''

        if project_type == ProjectType.FULLSTACK:
            return f'''# Server Configuration
PORT=3001
NODE_ENV=development

# Database Configuration (PostgreSQL via Prisma)
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/{db_name}"

# Security / JWT Configuration
SECRET_KEY="{secret_key}"
JWT_EXPIRY_HOURS=24

# Frontend (Vite)
VITE_API_URL=http://localhost:3001

# Admin User Seed (used by db:seed)
ADMIN_EMAIL="admin@{db_name}.com"
ADMIN_PASSWORD="admin123"
ADMIN_NAME="Admin User"
'''
        return '''# Server Configuration
PORT=3001
NODE_ENV=development

# Add your environment variables here
'''

    def _get_prisma_schema(self) -> str:
        """Generate default prisma/schema.prisma template for fullstack projects."""
        return '''// This is your Prisma schema file
// Documentation: https://pris.ly/d/prisma-schema

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

// Example model - replace with your actual data models
// Models will be generated based on your requirements

// model User {
//   id        String   @id @default(uuid())
//   email     String   @unique
//   name      String?
//   createdAt DateTime @default(now())
//   updatedAt DateTime @updatedAt
// }

// To generate Prisma Client after modifying this schema:
// 1. Run: npx prisma generate
// 2. To create/update database tables: npx prisma migrate dev
// 3. To explore data: npx prisma studio
'''

    def _get_prisma_seed(self, project_name: str) -> str:
        """Generate prisma/seed.ts for seeding the database with demo data."""
        db_name = project_name.lower().replace(" ", "_").replace("-", "_")
        return f'''/**
 * Database Seed Script
 *
 * Seeds the database with demo data including admin user and sample records.
 * Run with: npx prisma db seed
 *
 * Configure in package.json:
 * "prisma": {{
 *   "seed": "tsx prisma/seed.ts"
 * }}
 */

import {{ PrismaClient }} from '@prisma/client'
import * as bcrypt from 'bcryptjs'

const prisma = new PrismaClient()

async function main() {{
  console.log('Starting database seed...')

  // Create admin user
  const adminEmail = process.env.ADMIN_EMAIL || 'admin@{db_name}.com'
  const adminPassword = process.env.ADMIN_PASSWORD || 'admin123'
  const adminName = process.env.ADMIN_NAME || 'Admin User'

  const existingAdmin = await prisma.user.findUnique({{
    where: {{ email: adminEmail }},
  }})

  if (!existingAdmin) {{
    const hashedPassword = await bcrypt.hash(adminPassword, 10)
    const admin = await prisma.user.create({{
      data: {{
        email: adminEmail,
        name: adminName,
        password: hashedPassword,
      }},
    }})
    console.log(`Created admin user: ${{admin.email}}`)

    // Create sample tasks for admin
    const tasks = await prisma.task.createMany({{
      data: [
        {{
          title: 'Review project requirements',
          description: 'Go through all requirements and create analysis document.',
          status: 'DONE',
          priority: 'HIGH',
          userId: admin.id,
          dueDate: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
        }},
        {{
          title: 'Set up development environment',
          description: 'Install tools, configure IDE, set up database.',
          status: 'DONE',
          priority: 'HIGH',
          userId: admin.id,
          dueDate: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000),
        }},
        {{
          title: 'Implement authentication',
          description: 'Build JWT-based auth with login and register.',
          status: 'IN_PROGRESS',
          priority: 'HIGH',
          userId: admin.id,
          dueDate: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000),
        }},
        {{
          title: 'Write unit tests',
          description: 'Create test suite for all API endpoints.',
          status: 'TODO',
          priority: 'MEDIUM',
          userId: admin.id,
          dueDate: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000),
        }},
        {{
          title: 'Update documentation',
          description: 'Update README and API docs with new features.',
          status: 'TODO',
          priority: 'LOW',
          userId: admin.id,
          dueDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
        }},
      ],
    }})
    console.log(`Created ${{tasks.count}} sample tasks`)
  }} else {{
    console.log('Admin user already exists, skipping seed.')
  }}

  // Create demo user
  const demoEmail = 'demo@{db_name}.com'
  const existingDemo = await prisma.user.findUnique({{
    where: {{ email: demoEmail }},
  }})

  if (!existingDemo) {{
    const hashedPassword = await bcrypt.hash('demo123', 10)
    const demoUser = await prisma.user.create({{
      data: {{
        email: demoEmail,
        name: 'Demo User',
        password: hashedPassword,
      }},
    }})
    console.log(`Created demo user: ${{demoUser.email}}`)

    await prisma.task.createMany({{
      data: [
        {{
          title: 'Learn TypeScript',
          description: 'Complete TypeScript fundamentals course.',
          status: 'IN_PROGRESS',
          priority: 'MEDIUM',
          userId: demoUser.id,
          dueDate: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000),
        }},
        {{
          title: 'Build portfolio',
          description: 'Create personal portfolio website.',
          status: 'TODO',
          priority: 'LOW',
          userId: demoUser.id,
          dueDate: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
        }},
      ],
    }})
    console.log('Created sample tasks for demo user')
  }}

  console.log('\\nSeed completed!')
  console.log('\\nDemo Credentials:')
  console.log(`  Admin: ${{adminEmail}} / ${{adminPassword}}`)
  console.log(`  User:  ${{demoEmail}} / demo123`)
}}

main()
  .catch((e) => {{
    console.error('Seed failed:', e)
    process.exit(1)
  }})
  .finally(async () => {{
    await prisma.$disconnect()
  }})
'''

    def _get_prisma_client(self) -> str:
        """Generate src/lib/prisma.ts PrismaClient singleton for fullstack projects."""
        return '''import { PrismaClient } from '@prisma/client'

// PrismaClient singleton to prevent too many connections in development
// https://www.prisma.io/docs/guides/database/troubleshooting-orm/help-articles/nextjs-prisma-client-dev-practices

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

export const prisma = globalForPrisma.prisma ?? new PrismaClient({
  log: process.env.NODE_ENV === 'development' ? ['query', 'error', 'warn'] : ['error'],
})

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = prisma
}

export default prisma
'''

    def _get_python_requirements(self) -> str:
        """Generate requirements.txt."""
        return '''fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0
pytest>=7.4.0
httpx>=0.24.0
'''

    def _get_pyproject_toml(self, name: str) -> str:
        """Generate pyproject.toml."""
        return f'''[project]
name = "{name.lower().replace(" ", "-")}"
version = "1.0.0"
description = "Generated application"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
'''

    def _get_fastapi_main(self) -> str:
        """Generate src/main.py for FastAPI."""
        return '''import uvicorn
from src.app import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''

    def _get_fastapi_app(self) -> str:
        """Generate src/app.py for FastAPI."""
        return '''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

# Add your routes here
'''

    def _get_claude_md(self, project_name: str, project_type: ProjectType, requirements: dict) -> str:
        """Generate .claude/CLAUDE.md for Claude Code integration."""
        # Extract features list for documentation
        features = requirements.get("features", [])
        features_text = "\n".join([
            f"- {f.get('name', 'Unknown')}: {f.get('description', '')}"
            for f in features[:10]  # Limit to first 10 features
        ]) if features else "- See requirements.json for full feature list"

        # Get stack-specific commands
        if project_type == ProjectType.PYTHON_FASTAPI:
            commands = """```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn src.app:app --reload

# Run tests
pytest
```"""
        elif project_type == ProjectType.REACT_ELECTRON:
            commands = """```bash
# Install dependencies
npm install

# Run in development mode
npm run dev

# Build for production
npm run build

# Run tests
npm test
```"""
        else:
            commands = """```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run tests
npm test
```"""

        return f'''# CLAUDE.md - Claude Code Instructions for {project_name}

## Project Overview
This project was auto-generated by the Coding Engine.

**Project Type:** {project_type.value}

## Features
{features_text}

## Key Files & Structure
- `src/` - Main source code
- `tests/` - Test files
- `package.json` or `requirements.txt` - Dependencies

## Build & Run Commands
{commands}

## Architecture Notes
This project follows standard {project_type.value} patterns:
- Components/modules in `src/`
- Tests in `tests/`
- Configuration in root directory

## Important Guidelines
- Run tests before committing: `npm test` or `pytest`
- Follow existing code patterns
- Keep components small and focused
- Document any non-obvious logic

## API Documentation
- For FastAPI: Navigate to `/docs` for Swagger UI
- For Express/Node: Check `src/routes/` for endpoints

## Troubleshooting
- If build fails, try `npm install` or `pip install -r requirements.txt`
- Check `.env` for required environment variables
- For TypeScript errors, run `npx tsc --noEmit`
'''

    async def _install_dependencies(self, project_type: ProjectType, result: ScaffoldResult) -> None:
        """Install project dependencies."""
        self.logger.info("installing_dependencies")

        try:
            if project_type in (ProjectType.REACT_VITE, ProjectType.REACT_ELECTRON, ProjectType.NODE_EXPRESS, ProjectType.FULLSTACK):
                # Run npm install - use shutil.which to find npm.cmd on Windows
                npm_path = shutil.which("npm")
                if not npm_path:
                    result.errors.append("npm not found in PATH. Please install Node.js/npm.")
                    self.logger.error("npm_not_found")
                    return

                # EBUSY retry logic - previous Node.js process may have file handles open
                max_retries = 3
                for attempt in range(max_retries):
                    process = await asyncio.create_subprocess_exec(
                        npm_path, "install",
                        cwd=str(self.output_dir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

                    if process.returncode == 0:
                        result.dependencies_installed = True
                        self.logger.info("npm_install_success")

                        # Run prisma generate if schema exists
                        await self._run_prisma_generate_if_needed(result)
                        break
                    else:
                        error_msg = stderr.decode() if stderr else "Unknown error"

                        # Check for EBUSY error (file handle still open from previous process)
                        if "EBUSY" in error_msg and attempt < max_retries - 1:
                            self.logger.warning(
                                "npm_ebusy_retry",
                                attempt=attempt + 1,
                                max_retries=max_retries,
                            )
                            # Delete node_modules and wait for file handles to release
                            node_modules = self.output_dir / "node_modules"
                            if node_modules.exists():
                                try:
                                    shutil.rmtree(node_modules, ignore_errors=True)
                                except Exception:
                                    pass
                            # Wait for file handles to be released
                            await asyncio.sleep(2)
                            continue

                        # Not EBUSY or last retry - fail
                        result.errors.append(f"npm install failed: {error_msg[:500]}")
                        self.logger.error("npm_install_failed", error=error_msg[:200])
                        break

            elif project_type == ProjectType.PYTHON_FASTAPI:
                # Run pip install - use shutil.which for Windows compatibility
                req_file = self.output_dir / "requirements.txt"
                if req_file.exists():
                    pip_path = shutil.which("pip")
                    if not pip_path:
                        result.errors.append("pip not found in PATH. Please install Python/pip.")
                        self.logger.error("pip_not_found")
                        return

                    process = await asyncio.create_subprocess_exec(
                        pip_path, "install", "-r", str(req_file),
                        cwd=str(self.output_dir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

                    if process.returncode == 0:
                        result.dependencies_installed = True
                        self.logger.info("pip_install_success")
                    else:
                        error_msg = stderr.decode() if stderr else "Unknown error"
                        result.errors.append(f"pip install failed: {error_msg[:500]}")

        except asyncio.TimeoutError:
            result.errors.append("Dependency installation timed out after 5 minutes")
            self.logger.error("dependency_install_timeout")
        except Exception as e:
            result.errors.append(f"Dependency installation error: {str(e)}")
            self.logger.error("dependency_install_error", error=str(e))

    async def _run_prisma_generate_if_needed(self, result: ScaffoldResult) -> None:
        """
        Run prisma generate if a Prisma schema exists.

        This ensures the PrismaClient is built after npm install,
        preventing runtime errors when routes import PrismaClient.
        """
        # Check for prisma schema
        schema_path = self.output_dir / "prisma" / "schema.prisma"
        if not schema_path.exists():
            schema_path = self.output_dir / "schema.prisma"
            if not schema_path.exists():
                return  # No Prisma schema, nothing to do

        self.logger.info("running_prisma_generate")

        try:
            npx_path = shutil.which("npx")
            if not npx_path:
                self.logger.warning("npx_not_found", msg="Cannot run prisma generate")
                return

            # Load .env for DATABASE_URL
            env = os.environ.copy()
            env_file = self.output_dir / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env[key.strip()] = value.strip().strip('"').strip("'")

            process = await asyncio.create_subprocess_exec(
                npx_path, "prisma", "generate",
                cwd=str(self.output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode == 0:
                self.logger.info("prisma_generate_success")
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                self.logger.warning("prisma_generate_failed", error=error_msg[:200])
                # Don't fail the scaffold - Prisma can be generated later

        except asyncio.TimeoutError:
            self.logger.warning("prisma_generate_timeout")
        except Exception as e:
            self.logger.warning("prisma_generate_error", error=str(e))

    async def _init_git_repository(self, result: ScaffoldResult) -> None:
        """Initialize git repository in the output directory."""
        git_dir = self.output_dir / ".git"

        # Skip if already a git repo
        if git_dir.exists():
            self.logger.info("git_repo_already_exists")
            return

        self.logger.info("initializing_git_repository")

        try:
            # Find git executable
            git_path = shutil.which("git")
            if not git_path:
                self.logger.warning("git_not_found", msg="Git not found in PATH, skipping git init")
                return

            # Run git init
            process = await asyncio.create_subprocess_exec(
                git_path, "init",
                cwd=str(self.output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode == 0:
                self.logger.info("git_init_success")

                # Create initial .gitignore if it doesn't exist
                gitignore_path = self.output_dir / ".gitignore"
                if not gitignore_path.exists():
                    gitignore_content = """# Dependencies
node_modules/
.pnp/
.pnp.js

# Build outputs
dist/
build/
out/
.next/

# Environment files
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
logs/
*.log
npm-debug.log*

# Testing
coverage/

# Misc
*.tgz
.cache/
"""
                    gitignore_path.write_text(gitignore_content, encoding="utf-8")
                    self.logger.debug("created_gitignore")

                # Make initial commit
                await self._git_initial_commit()
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                self.logger.warning("git_init_failed", error=error_msg[:200])

        except asyncio.TimeoutError:
            self.logger.warning("git_init_timeout")
        except Exception as e:
            self.logger.warning("git_init_error", error=str(e))

    async def _git_initial_commit(self) -> None:
        """Create initial git commit."""
        try:
            git_path = shutil.which("git")
            if not git_path:
                return

            # git add .
            process = await asyncio.create_subprocess_exec(
                git_path, "add", ".",
                cwd=str(self.output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=30)

            # git commit
            process = await asyncio.create_subprocess_exec(
                git_path, "commit", "-m", "Initial commit from Coding Engine",
                cwd=str(self.output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**subprocess.os.environ, "GIT_AUTHOR_NAME": "Coding Engine", "GIT_AUTHOR_EMAIL": "engine@local", "GIT_COMMITTER_NAME": "Coding Engine", "GIT_COMMITTER_EMAIL": "engine@local"},
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode == 0:
                self.logger.info("git_initial_commit_success")
            else:
                self.logger.debug("git_commit_skipped", msg="No files to commit or commit failed")

        except Exception as e:
            self.logger.debug("git_commit_error", error=str(e))


    # ── NestJS Fullstack Templates ─────────────────────────────────────

    def _get_nestjs_package_json(self, name: str) -> str:
        return json.dumps({
            "name": name.lower().replace(" ", "-"),
            "version": "1.0.0",
            "private": True,
            "scripts": {
                "build": "nest build",
                "start": "nest start",
                "start:dev": "nest start --watch",
                "start:prod": "node dist/main",
                "test": "jest",
                "test:e2e": "jest --config ./test/jest-e2e.json",
                "db:generate": "prisma generate",
                "db:push": "prisma db push",
                "db:migrate": "prisma migrate dev",
            },
            "dependencies": {
                "@nestjs/common": "^10.0.0",
                "@nestjs/config": "^3.0.0",
                "@nestjs/core": "^10.0.0",
                "@nestjs/platform-express": "^10.0.0",
                "@nestjs/websockets": "^10.0.0",
                "@nestjs/platform-socket.io": "^10.0.0",
                "@prisma/client": "^5.0.0",
                "bcryptjs": "^2.4.3",
                "class-validator": "^0.14.0",
                "class-transformer": "^0.5.0",
                "reflect-metadata": "^0.1.13",
                "rxjs": "^7.8.0",
                "socket.io": "^4.7.0",
                "dotenv": "^16.3.0",
            },
            "devDependencies": {
                "@nestjs/cli": "^10.0.0",
                "@nestjs/schematics": "^10.0.0",
                "@nestjs/testing": "^10.0.0",
                "@types/bcryptjs": "^2.4.0",
                "@types/express": "^4.17.0",
                "@types/node": "^20.0.0",
                "prisma": "^5.0.0",
                "tsx": "^4.7.0",
                "typescript": "^5.3.0",
                "ts-loader": "^9.5.0",
                "ts-node": "^10.9.0",
            },
            "prisma": {"seed": "ts-node prisma/seed.ts"},
        }, indent=2)

    def _get_nestjs_tsconfig(self) -> str:
        return json.dumps({
            "compilerOptions": {
                "module": "commonjs",
                "declaration": True,
                "removeComments": True,
                "emitDecoratorMetadata": True,
                "experimentalDecorators": True,
                "allowSyntheticDefaultImports": True,
                "target": "ES2021",
                "sourceMap": True,
                "outDir": "./dist",
                "baseUrl": "./",
                "incremental": True,
                "skipLibCheck": True,
                "strictNullChecks": False,
                "noImplicitAny": False,
                "strictBindCallApply": False,
                "forceConsistentCasingInFileNames": False,
                "noFallthroughCasesInSwitch": False,
                "strictPropertyInitialization": False,
            },
        }, indent=2)

    def _get_nestjs_tsconfig_build(self) -> str:
        return json.dumps({
            "extends": "./tsconfig.json",
            "exclude": ["node_modules", "test", "dist", "**/*spec.ts", "frontend"],
        }, indent=2)

    def _get_nestjs_cli_json(self) -> str:
        return json.dumps({
            "$schema": "https://json.schemastore.org/nest-cli",
            "collection": "@nestjs/schematics",
            "sourceRoot": "src",
            "compilerOptions": {"deleteOutDir": True},
        }, indent=2)

    def _get_nestjs_main(self) -> str:
        return """import { ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create(AppModule);

  app.enableCors({
    origin: ['http://localhost:3100', 'http://localhost:3201'],
    credentials: true,
  });

  app.useGlobalPipes(
    new ValidationPipe({ transform: true, whitelist: true }),
  );

  const port = Number(process.env.PORT ?? 3000);
  await app.listen(port);
  console.log(`NestJS running on port ${port}`);
}

void bootstrap();
"""

    def _get_nestjs_events_gateway(self) -> str:
        """Generate WebSocket gateway for real-time events."""
        return """import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
  ConnectedSocket,
  MessageBody,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger } from '@nestjs/common';

@WebSocketGateway({
  cors: {
    origin: ['http://localhost:3100', 'http://localhost:3201'],
    credentials: true,
  },
  namespace: '/events',
})
export class EventsGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer() server: Server;
  private readonly logger = new Logger(EventsGateway.name);
  private connectedUsers = new Map<string, string>(); // socketId -> userId

  handleConnection(client: Socket) {
    this.logger.log(`Client connected: ${client.id}`);
  }

  handleDisconnect(client: Socket) {
    const userId = this.connectedUsers.get(client.id);
    this.connectedUsers.delete(client.id);
    if (userId) {
      this.server.emit('user:offline', { userId });
    }
    this.logger.log(`Client disconnected: ${client.id}`);
  }

  @SubscribeMessage('auth')
  handleAuth(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { userId: string },
  ) {
    this.connectedUsers.set(client.id, data.userId);
    client.join(`user:${data.userId}`);
    this.server.emit('user:online', { userId: data.userId });
    return { event: 'auth', data: { success: true } };
  }

  @SubscribeMessage('join:chat')
  handleJoinChat(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { chatId: string },
  ) {
    client.join(`chat:${data.chatId}`);
    return { event: 'join:chat', data: { chatId: data.chatId } };
  }

  @SubscribeMessage('leave:chat')
  handleLeaveChat(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { chatId: string },
  ) {
    client.leave(`chat:${data.chatId}`);
  }

  @SubscribeMessage('typing')
  handleTyping(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { chatId: string; userId: string },
  ) {
    client.to(`chat:${data.chatId}`).emit('typing', data);
  }

  // Utility: emit to specific user
  emitToUser(userId: string, event: string, data: unknown) {
    this.server.to(`user:${userId}`).emit(event, data);
  }

  // Utility: emit to chat room
  emitToChat(chatId: string, event: string, data: unknown) {
    this.server.to(`chat:${chatId}`).emit(event, data);
  }

  // Utility: broadcast new message
  notifyNewMessage(chatId: string, message: unknown) {
    this.emitToChat(chatId, 'message:new', message);
  }
}
"""

    def _get_nestjs_events_module(self) -> str:
        """Generate WebSocket events module."""
        return """import { Module, Global } from '@nestjs/common';
import { EventsGateway } from './events.gateway';

@Global()
@Module({
  providers: [EventsGateway],
  exports: [EventsGateway],
})
export class EventsModule {}
"""

    def _get_nestjs_app_module(self) -> str:
        return """import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { PrismaModule } from './prisma/prisma.module';
import { EventsModule } from './gateway/events.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, envFilePath: '.env' }),
    PrismaModule,
    EventsModule,
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
"""

    def _get_nestjs_app_controller(self, name: str) -> str:
        return f"""import {{ Controller, Get }} from '@nestjs/common';
import {{ AppService }} from './app.service';

@Controller()
export class AppController {{
  constructor(private readonly appService: AppService) {{}}

  @Get()
  getInfo() {{
    return {{ message: '{name} is running' }};
  }}

  @Get('health')
  health() {{
    return {{ status: 'ok', timestamp: new Date().toISOString() }};
  }}
}}
"""

    def _get_nestjs_app_service(self) -> str:
        return """import { Injectable } from '@nestjs/common';

@Injectable()
export class AppService {}
"""

    def _get_nestjs_prisma_service(self) -> str:
        return """import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
"""

    def _get_nestjs_prisma_module(self) -> str:
        return """import { Global, Module } from '@nestjs/common';
import { PrismaService } from '../prisma.service';

@Global()
@Module({
  providers: [PrismaService],
  exports: [PrismaService],
})
export class PrismaModule {}
"""

    def _get_nestjs_frontend_package_json(self, name: str) -> str:
        return json.dumps({
            "name": f"{name.lower().replace(' ', '-')}-frontend",
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
            },
            "dependencies": {
                "react": "^18.3.1",
                "react-dom": "^18.3.1",
                "react-router-dom": "^6.23.1",
            },
            "devDependencies": {
                "@types/react": "^18.3.3",
                "@types/react-dom": "^18.3.0",
                "@vitejs/plugin-react": "^4.3.1",
                "typescript": "^5.5.3",
                "vite": "^5.4.0",
            },
        }, indent=2)

    def _get_nestjs_frontend_tsconfig(self) -> str:
        return json.dumps({
            "compilerOptions": {
                "target": "ES2020",
                "useDefineForClassFields": True,
                "lib": ["ES2020", "DOM", "DOM.Iterable"],
                "module": "ESNext",
                "skipLibCheck": True,
                "moduleResolution": "bundler",
                "allowImportingTsExtensions": True,
                "resolveJsonModule": True,
                "isolatedModules": True,
                "noEmit": True,
                "jsx": "react-jsx",
                "strict": False,
            },
            "include": ["src"],
        }, indent=2)

    def _get_nestjs_frontend_vite_config(self) -> str:
        return """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0', port: 3100 },
});
"""

    def _get_nestjs_frontend_index_html(self, name: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{name}</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
"""

    def _get_nestjs_frontend_app_tsx(self) -> str:
        return """import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';

function Home() {
  return (
    <div style={{minHeight:'100vh',background:'#0a0a0a',color:'#fff',fontFamily:'system-ui',display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center'}}>
      <h1 style={{fontSize:'2rem',marginBottom:'1rem'}}>App</h1>
      <p style={{color:'#888'}}>Frontend pages will be generated here.</p>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </BrowserRouter>
  );
}
"""

    def _get_nestjs_frontend_env(self) -> str:
        return "VITE_API_BASE_URL=http://localhost:3201\n"

    def _get_nestjs_dockerfile(self) -> str:
        return '''# Multi-stage build for NestJS + React frontend
FROM node:20-alpine AS backend-build
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
COPY prisma ./prisma
RUN npx prisma generate
COPY tsconfig*.json nest-cli.json ./
COPY src ./src
RUN npm run build

FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM node:20-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
COPY --from=backend-build /app/dist ./dist
COPY --from=backend-build /app/node_modules ./node_modules
COPY --from=backend-build /app/prisma ./prisma
COPY --from=backend-build /app/package.json ./
COPY --from=frontend-build /app/dist ./frontend/dist
EXPOSE 3000
CMD ["node", "dist/main.js"]
'''

    def _get_nestjs_ci_yml(self) -> str:
        return '''name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci --legacy-peer-deps
      - run: npx prisma generate
      - run: npx tsc --noEmit
      - run: npm run build
      - run: npm test
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test_db

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run: { working-directory: frontend }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
      - run: npx vite build
'''


async def initialize_project(
    output_dir: str,
    requirements: dict,
    project_type: Optional[ProjectType] = None,
    install_deps: bool = True,
    theme: ThemeType = ThemeType.VIBEMIND_SPACE,
) -> ScaffoldResult:
    """
    Convenience function to initialize a project.

    Args:
        output_dir: Output directory path
        requirements: Parsed requirements dict
        project_type: Override project type detection
        install_deps: Whether to install dependencies
        theme: UI theme (default: VIBEMIND_SPACE for modern dark theme)

    Returns:
        ScaffoldResult with initialization details
    """
    initializer = ProjectInitializer(output_dir, theme=theme)
    return await initializer.initialize(requirements, project_type, install_deps, theme=theme)
