"""
Project Template System — Quick bootstrapping of new code generation projects.

Provides:
- Template definitions with file structure, dependencies, and configuration
- Built-in templates for common project types (Python, Node.js, API, etc.)
- Custom template creation and management
- Template variables with substitution
- Dry-run mode for preview
- Template validation and listing

Usage:
    templates = ProjectTemplateManager()

    # List available templates
    templates.list_templates()

    # Create a project from template
    result = templates.create_project(
        template_name="python-package",
        project_name="my-lib",
        variables={"author": "Dev", "description": "My library"},
    )
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TemplateFile:
    """A file within a project template."""
    path: str               # Relative path with variable placeholders
    content: str            # Content with variable placeholders
    is_directory: bool = False
    executable: bool = False


@dataclass
class TemplateDependency:
    """A dependency for a template."""
    name: str
    version: str = ""
    dev: bool = False


@dataclass
class ProjectTemplate:
    """A project template definition."""
    template_id: str
    name: str
    description: str = ""
    language: str = ""
    category: str = "general"
    files: List[TemplateFile] = field(default_factory=list)
    dependencies: List[TemplateDependency] = field(default_factory=list)
    variables: Dict[str, str] = field(default_factory=dict)  # name -> default_value
    tags: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "language": self.language,
            "category": self.category,
            "file_count": len(self.files),
            "dependency_count": len(self.dependencies),
            "variables": self.variables,
            "tags": sorted(self.tags),
        }


@dataclass
class ProjectCreateResult:
    """Result of creating a project from a template."""
    success: bool
    project_name: str
    template_name: str
    files_created: List[str] = field(default_factory=list)
    directories_created: List[str] = field(default_factory=list)
    variables_used: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "project_name": self.project_name,
            "template_name": self.template_name,
            "files_created": self.files_created,
            "directories_created": self.directories_created,
            "variables_used": self.variables_used,
            "warnings": self.warnings,
        }


class ProjectTemplateManager:
    """Manages project templates for quick bootstrapping."""

    def __init__(self):
        self._templates: Dict[str, ProjectTemplate] = {}
        self._total_created = 0
        self._total_projects = 0

        # Register built-in templates
        self._register_builtins()

    # ── Template Management ──────────────────────────────────────────

    def register_template(
        self,
        name: str,
        files: List[Dict[str, Any]],
        description: str = "",
        language: str = "",
        category: str = "general",
        dependencies: Optional[List[Dict[str, Any]]] = None,
        variables: Optional[Dict[str, str]] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new project template."""
        template_id = f"tpl-{uuid.uuid4().hex[:8]}"

        template_files = [
            TemplateFile(
                path=f["path"],
                content=f.get("content", ""),
                is_directory=f.get("is_directory", False),
                executable=f.get("executable", False),
            )
            for f in files
        ]

        template_deps = [
            TemplateDependency(
                name=d["name"],
                version=d.get("version", ""),
                dev=d.get("dev", False),
            )
            for d in (dependencies or [])
        ]

        template = ProjectTemplate(
            template_id=template_id,
            name=name,
            description=description,
            language=language,
            category=category,
            files=template_files,
            dependencies=template_deps,
            variables=variables or {},
            tags=set(tags) if tags else set(),
            metadata=metadata or {},
        )

        self._templates[name] = template
        self._total_created += 1

        logger.info(
            "template_registered",
            component="project_template",
            name=name,
            files=len(template_files),
            deps=len(template_deps),
        )

        return template_id

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a template definition."""
        tpl = self._templates.get(name)
        return tpl.to_dict() if tpl else None

    def list_templates(
        self,
        language: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List available templates with optional filters."""
        results = list(self._templates.values())

        if language:
            results = [t for t in results if t.language == language]
        if category:
            results = [t for t in results if t.category == category]
        if tags:
            results = [t for t in results if tags.issubset(t.tags)]

        return [t.to_dict() for t in sorted(results, key=lambda t: t.name)]

    def delete_template(self, name: str) -> bool:
        """Delete a template."""
        return self._templates.pop(name, None) is not None

    # ── Project Creation ─────────────────────────────────────────────

    def create_project(
        self,
        template_name: str,
        project_name: str,
        variables: Optional[Dict[str, str]] = None,
        dry_run: bool = False,
    ) -> ProjectCreateResult:
        """Create a project from a template (returns file manifest)."""
        template = self._templates.get(template_name)
        if not template:
            return ProjectCreateResult(
                success=False,
                project_name=project_name,
                template_name=template_name,
                warnings=[f"Template '{template_name}' not found"],
            )

        # Merge variables: defaults + user overrides
        merged_vars = dict(template.variables)
        merged_vars["project_name"] = project_name
        if variables:
            merged_vars.update(variables)

        # Check for missing required variables
        warnings = []
        for var_name, default_val in template.variables.items():
            if not default_val and var_name not in (variables or {}):
                warnings.append(f"Variable '{var_name}' has no value")

        # Process files
        files_created = []
        dirs_created = []

        for tpl_file in template.files:
            processed_path = self._substitute(tpl_file.path, merged_vars)

            if tpl_file.is_directory:
                dirs_created.append(processed_path)
            else:
                processed_content = self._substitute(tpl_file.content, merged_vars)
                files_created.append(processed_path)

        if not dry_run:
            self._total_projects += 1

        logger.info(
            "project_created" if not dry_run else "project_dry_run",
            component="project_template",
            template=template_name,
            project=project_name,
            files=len(files_created),
            dirs=len(dirs_created),
        )

        return ProjectCreateResult(
            success=True,
            project_name=project_name,
            template_name=template_name,
            files_created=files_created,
            directories_created=dirs_created,
            variables_used=merged_vars,
            warnings=warnings,
        )

    def preview_project(
        self,
        template_name: str,
        project_name: str,
        variables: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Preview what a project creation would produce."""
        result = self.create_project(
            template_name, project_name, variables, dry_run=True
        )
        if not result.success:
            return None

        template = self._templates[template_name]
        merged_vars = dict(template.variables)
        merged_vars["project_name"] = project_name
        if variables:
            merged_vars.update(variables)

        file_previews = []
        for tpl_file in template.files:
            if not tpl_file.is_directory:
                file_previews.append({
                    "path": self._substitute(tpl_file.path, merged_vars),
                    "content": self._substitute(tpl_file.content, merged_vars),
                })

        return {
            "project_name": project_name,
            "template": template_name,
            "files": file_previews,
            "directories": result.directories_created,
            "variables": merged_vars,
            "dependencies": [
                {"name": d.name, "version": d.version, "dev": d.dev}
                for d in template.dependencies
            ],
        }

    def get_template_variables(self, name: str) -> Optional[Dict[str, str]]:
        """Get the variables required by a template."""
        tpl = self._templates.get(name)
        if not tpl:
            return None
        return dict(tpl.variables)

    # ── Stats ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get template manager statistics."""
        categories = {}
        languages = {}
        for t in self._templates.values():
            categories[t.category] = categories.get(t.category, 0) + 1
            if t.language:
                languages[t.language] = languages.get(t.language, 0) + 1

        return {
            "total_templates": len(self._templates),
            "total_registered": self._total_created,
            "total_projects_created": self._total_projects,
            "categories": categories,
            "languages": languages,
        }

    def reset(self):
        """Reset all templates."""
        self._templates.clear()
        self._total_created = 0
        self._total_projects = 0

    # ── Internal ─────────────────────────────────────────────────────

    def _substitute(self, text: str, variables: Dict[str, str]) -> str:
        """Replace {{variable}} placeholders in text."""
        result = text
        for key, value in variables.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result

    def _register_builtins(self):
        """Register built-in project templates."""

        # Python Package
        self.register_template(
            name="python-package",
            description="Python package with tests and CI",
            language="python",
            category="library",
            variables={
                "author": "",
                "description": "A Python package",
                "python_version": "3.11",
            },
            tags={"python", "package", "library"},
            dependencies=[
                {"name": "pytest", "version": ">=7.0", "dev": True},
                {"name": "structlog", "version": ">=23.0"},
            ],
            files=[
                {"path": "{{project_name}}/", "is_directory": True},
                {"path": "{{project_name}}/src/", "is_directory": True},
                {"path": "{{project_name}}/src/{{project_name}}/", "is_directory": True},
                {"path": "{{project_name}}/tests/", "is_directory": True},
                {
                    "path": "{{project_name}}/src/{{project_name}}/__init__.py",
                    "content": '"""{{description}}"""\n\n__version__ = "0.1.0"\n',
                },
                {
                    "path": "{{project_name}}/src/{{project_name}}/main.py",
                    "content": '"""Main module for {{project_name}}."""\n\n\ndef main():\n    print("Hello from {{project_name}}!")\n',
                },
                {
                    "path": "{{project_name}}/tests/__init__.py",
                    "content": "",
                },
                {
                    "path": "{{project_name}}/tests/test_main.py",
                    "content": '"""Tests for {{project_name}}."""\nfrom {{project_name}}.main import main\n\n\ndef test_main():\n    main()\n',
                },
                {
                    "path": "{{project_name}}/pyproject.toml",
                    "content": '[project]\nname = "{{project_name}}"\nversion = "0.1.0"\ndescription = "{{description}}"\nauthors = [{name = "{{author}}"}]\nrequires-python = ">={{python_version}}"\n',
                },
            ],
        )

        # Python API Service
        self.register_template(
            name="python-api",
            description="Python FastAPI service with Docker",
            language="python",
            category="service",
            variables={
                "author": "",
                "description": "An API service",
                "port": "8000",
            },
            tags={"python", "api", "fastapi", "service"},
            dependencies=[
                {"name": "fastapi", "version": ">=0.100.0"},
                {"name": "uvicorn", "version": ">=0.23.0"},
                {"name": "pytest", "version": ">=7.0", "dev": True},
            ],
            files=[
                {"path": "{{project_name}}/", "is_directory": True},
                {"path": "{{project_name}}/app/", "is_directory": True},
                {"path": "{{project_name}}/tests/", "is_directory": True},
                {
                    "path": "{{project_name}}/app/__init__.py",
                    "content": "",
                },
                {
                    "path": "{{project_name}}/app/main.py",
                    "content": '"""{{description}}"""\nfrom fastapi import FastAPI\n\napp = FastAPI(title="{{project_name}}")\n\n\n@app.get("/")\ndef root():\n    return {"service": "{{project_name}}", "status": "ok"}\n',
                },
                {
                    "path": "{{project_name}}/Dockerfile",
                    "content": 'FROM python:{{python_version}}-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nEXPOSE {{port}}\nCMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "{{port}}"]\n',
                },
            ],
        )

        # Node.js Package
        self.register_template(
            name="nodejs-package",
            description="Node.js package with TypeScript",
            language="nodejs",
            category="library",
            variables={
                "author": "",
                "description": "A Node.js package",
                "node_version": "18",
            },
            tags={"nodejs", "typescript", "package"},
            dependencies=[
                {"name": "typescript", "version": "^5.0", "dev": True},
                {"name": "jest", "version": "^29.0", "dev": True},
            ],
            files=[
                {"path": "{{project_name}}/", "is_directory": True},
                {"path": "{{project_name}}/src/", "is_directory": True},
                {"path": "{{project_name}}/tests/", "is_directory": True},
                {
                    "path": "{{project_name}}/src/index.ts",
                    "content": '/**\n * {{description}}\n */\nexport function hello(): string {\n  return "Hello from {{project_name}}!";\n}\n',
                },
                {
                    "path": "{{project_name}}/package.json",
                    "content": '{\n  "name": "{{project_name}}",\n  "version": "0.1.0",\n  "description": "{{description}}",\n  "main": "dist/index.js",\n  "scripts": {\n    "build": "tsc",\n    "test": "jest"\n  }\n}\n',
                },
                {
                    "path": "{{project_name}}/tsconfig.json",
                    "content": '{\n  "compilerOptions": {\n    "target": "ES2020",\n    "module": "commonjs",\n    "outDir": "./dist",\n    "strict": true\n  },\n  "include": ["src/**/*"]\n}\n',
                },
            ],
        )

        logger.debug(
            "builtin_templates_registered",
            component="project_template",
            count=len(self._templates),
        )
