"""
Documentation Agent - Auto-generates CLAUDE.md for generated projects.

This agent:
1. Uses Claude CLI /init to analyze and document the project (preferred)
2. Falls back to manual analysis if CLI not available
3. Extracts build/run/test commands from package.json
4. Documents the architecture and key files
5. Includes Reports-Section with current project status from DocumentRegistry

The generated CLAUDE.md is project-specific, not the Coding Engine's architecture.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from ..tools.claude_init_tool import ClaudeInitTool, ClaudeInitResult

# Lazy imports to avoid circular dependencies
def _get_document_registry():
    """Lazy import DocumentRegistry."""
    try:
        from src.registry.document_registry import DocumentRegistry
        from src.registry.document_types import DocumentType
        return DocumentRegistry, DocumentType
    except ImportError:
        return None, None

logger = structlog.get_logger(__name__)


@dataclass
class ProjectAnalysis:
    """Analysis of a generated project."""
    project_name: str = ""
    project_type: str = ""  # electron, react, node, python, etc.
    description: str = ""

    # Commands
    build_command: str = ""
    dev_command: str = ""
    test_command: str = ""
    start_command: str = ""

    # Structure
    source_dirs: list[str] = field(default_factory=list)
    key_files: dict[str, str] = field(default_factory=dict)  # path -> description

    # Architecture
    components: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)

    # Dependencies
    main_dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)


@dataclass
class ReportsSnapshot:
    """Snapshot of current reports for CLAUDE.md."""
    debug_summary: str = ""
    implementation_plan: str = ""
    test_results: str = ""
    last_updated: Optional[datetime] = None


class DocumentationAgent(AutonomousAgent):
    """
    Agent that generates CLAUDE.md documentation for output projects.

    Triggers on:
    - BUILD_SUCCEEDED: Generate/update docs after successful build
    - CODE_FIXED: Update docs when code changes
    - CONVERGENCE_UPDATE: Update docs periodically
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        requirements: Optional[list[str]] = None,
        use_claude_init: bool = True,
    ):
        super().__init__(name, event_bus, shared_state, working_dir)
        self.requirements = requirements or []
        self._last_docs_update: Optional[datetime] = None
        self._docs_generated = False
        self._doc_registry = None
        self._use_claude_init = use_claude_init
        self._claude_init_tool = ClaudeInitTool(working_dir=working_dir)
        self.logger = logger.bind(agent=name)

        # Initialize DocumentRegistry if available
        try:
            DocumentRegistry, _ = _get_document_registry()
            if DocumentRegistry:
                self._doc_registry = DocumentRegistry(working_dir)
        except Exception as e:
            self.logger.debug("doc_registry_init_failed", error=str(e))

    async def _publish_event(self, event_type: EventType, data: dict) -> None:
        """Publish an event to the event bus."""
        await self.event_bus.publish(Event(
            type=event_type,
            source=self.name,
            data=data,
        ))

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.CODE_FIXED,
            EventType.CONVERGENCE_UPDATE,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Decide whether to generate/update documentation."""
        # Don't act too frequently
        if self._last_docs_update:
            elapsed = (datetime.now() - self._last_docs_update).total_seconds()
            if elapsed < 30:  # At least 30 seconds between updates
                return False

        # Always generate on first build success
        if not self._docs_generated:
            for event in events:
                if event.type == EventType.BUILD_SUCCEEDED:
                    return True

        # Update periodically on convergence updates (every 5th iteration)
        for event in events:
            if event.type == EventType.CONVERGENCE_UPDATE:
                iteration = event.data.get("iteration", 0)
                if iteration > 0 and iteration % 5 == 0:
                    return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Generate or update CLAUDE.md documentation."""
        await self._publish_event(EventType.DOCS_GENERATION_STARTED, {})

        try:
            claude_md_path = Path(self.working_dir) / "CLAUDE.md"
            is_update = claude_md_path.exists()
            used_claude_init = False

            # Try Claude CLI /init first (preferred - generates AI-analyzed docs)
            if self._use_claude_init:
                result = await self._run_claude_init()
                if result.success:
                    used_claude_init = True
                    self.logger.info(
                        "claude_init_succeeded",
                        path=str(result.claude_md_path),
                        content_length=len(result.content) if result.content else 0,
                    )
                else:
                    self.logger.warning(
                        "claude_init_failed_fallback",
                        error=result.error,
                    )

            # Fallback to manual analysis if Claude /init failed
            if not used_claude_init:
                # Analyze the project
                analysis = await self._analyze_project()

                # Load current reports
                reports = await self._load_reports_snapshot()

                # Generate CLAUDE.md content with reports
                content = self._generate_claude_md(analysis, reports)

                # Write the file
                claude_md_path.write_text(content, encoding="utf-8")

            self._last_docs_update = datetime.now()
            self._docs_generated = True

            # Get project info for event
            analysis = await self._analyze_project()

            event_type = EventType.DOCS_UPDATED if is_update else EventType.DOCS_GENERATED
            await self._publish_event(event_type, {
                "path": str(claude_md_path),
                "project_name": analysis.project_name,
                "project_type": analysis.project_type,
                "used_claude_init": used_claude_init,
            })

            self.logger.info(
                "docs_generated",
                path=str(claude_md_path),
                is_update=is_update,
                used_claude_init=used_claude_init,
            )

        except Exception as e:
            self.logger.error("docs_generation_failed", error=str(e))

    async def _run_claude_init(self) -> ClaudeInitResult:
        """
        Run Claude CLI /init to generate project documentation.

        Returns:
            ClaudeInitResult with success status and content
        """
        self.logger.info("claude_init_starting", working_dir=self.working_dir)
        return await self._claude_init_tool.run_init()

    async def _analyze_project(self) -> ProjectAnalysis:
        """Analyze the project structure and extract information."""
        analysis = ProjectAnalysis()
        working_path = Path(self.working_dir)

        # Check for package.json (Node/Electron projects)
        package_json = working_path / "package.json"
        if package_json.exists():
            await self._analyze_package_json(package_json, analysis)

        # Check for pyproject.toml (Python projects)
        pyproject = working_path / "pyproject.toml"
        if pyproject.exists():
            await self._analyze_pyproject(pyproject, analysis)

        # Analyze directory structure
        await self._analyze_structure(working_path, analysis)

        # Identify key files
        await self._identify_key_files(working_path, analysis)

        return analysis

    async def _analyze_package_json(self, path: Path, analysis: ProjectAnalysis) -> None:
        """Extract information from package.json."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                pkg = json.load(f)

            analysis.project_name = pkg.get("name", "unknown")
            analysis.description = pkg.get("description", "")

            # Detect project type
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})
            all_deps = {**deps, **dev_deps}

            if "electron" in all_deps:
                analysis.project_type = "electron"
            elif "react" in all_deps:
                analysis.project_type = "react"
            elif "vue" in all_deps:
                analysis.project_type = "vue"
            elif "express" in all_deps:
                analysis.project_type = "node-express"
            else:
                analysis.project_type = "node"

            # Extract scripts
            scripts = pkg.get("scripts", {})
            analysis.build_command = f"npm run {self._find_script(scripts, ['build', 'compile'])}"
            analysis.dev_command = f"npm run {self._find_script(scripts, ['dev', 'start:dev', 'serve'])}"
            analysis.test_command = f"npm run {self._find_script(scripts, ['test', 'test:unit'])}"
            analysis.start_command = f"npm run {self._find_script(scripts, ['start', 'serve'])}"

            # Main dependencies
            analysis.main_dependencies = list(deps.keys())[:10]
            analysis.dev_dependencies = list(dev_deps.keys())[:10]

        except Exception as e:
            self.logger.warning("package_json_parse_error", error=str(e))

    def _find_script(self, scripts: dict, candidates: list[str]) -> str:
        """Find the first matching script name."""
        for candidate in candidates:
            if candidate in scripts:
                return candidate
        return candidates[0] if candidates else "start"

    async def _analyze_pyproject(self, path: Path, analysis: ProjectAnalysis) -> None:
        """Extract information from pyproject.toml."""
        try:
            content = path.read_text(encoding="utf-8")
            analysis.project_type = "python"

            # Basic parsing - just extract name
            for line in content.split("\n"):
                if line.strip().startswith("name"):
                    parts = line.split("=")
                    if len(parts) == 2:
                        analysis.project_name = parts[1].strip().strip('"\'')
                        break

            analysis.build_command = "pip install -e ."
            analysis.dev_command = "python -m src.main"
            analysis.test_command = "pytest"
            analysis.start_command = "python -m src.main"

        except Exception as e:
            self.logger.warning("pyproject_parse_error", error=str(e))

    async def _analyze_structure(self, working_path: Path, analysis: ProjectAnalysis) -> None:
        """Analyze directory structure."""
        # Find source directories
        common_src_dirs = ["src", "lib", "app", "components", "pages", "renderer", "main", "preload"]
        for dir_name in common_src_dirs:
            dir_path = working_path / dir_name
            if dir_path.is_dir():
                analysis.source_dirs.append(dir_name)

        # Find entry points
        entry_candidates = [
            "src/main.ts", "src/main.tsx", "src/index.ts", "src/index.tsx",
            "src/main/main.ts", "src/main/index.ts",
            "main.py", "src/main.py", "app.py",
            "index.js", "main.js",
        ]
        for candidate in entry_candidates:
            if (working_path / candidate).exists():
                analysis.entry_points.append(candidate)

    async def _identify_key_files(self, working_path: Path, analysis: ProjectAnalysis) -> None:
        """Identify and describe key files."""
        key_file_patterns = {
            "package.json": "Project configuration and dependencies",
            "tsconfig.json": "TypeScript configuration",
            "electron.vite.config.ts": "Electron-Vite build configuration",
            "vite.config.ts": "Vite build configuration",
            "electron-builder.json": "Electron packaging configuration",
            "tailwind.config.js": "Tailwind CSS configuration",
            ".env": "Environment variables",
            ".env.example": "Environment variables template",
        }

        for pattern, description in key_file_patterns.items():
            if (working_path / pattern).exists():
                analysis.key_files[pattern] = description

        # Electron-specific
        if analysis.project_type == "electron":
            electron_files = {
                "src/main/main.ts": "Electron main process entry",
                "src/preload/preload.ts": "Electron preload script (IPC bridge)",
                "src/renderer/index.html": "Renderer process HTML",
                "src/renderer/App.tsx": "Main React application component",
            }
            for path, desc in electron_files.items():
                if (working_path / path).exists():
                    analysis.key_files[path] = desc

        # Find components
        components_dir = working_path / "src" / "renderer" / "components"
        if not components_dir.exists():
            components_dir = working_path / "src" / "components"

        if components_dir.exists():
            for comp_file in components_dir.glob("*.tsx"):
                analysis.components.append(comp_file.stem)
            for comp_file in components_dir.glob("*.ts"):
                if not comp_file.name.endswith(".d.ts"):
                    analysis.components.append(comp_file.stem)

    async def _load_reports_snapshot(self) -> ReportsSnapshot:
        """
        Load current reports from DocumentRegistry for inclusion in CLAUDE.md.
        
        Returns:
            ReportsSnapshot with summaries of current reports
        """
        snapshot = ReportsSnapshot()
        
        if not self._doc_registry:
            return snapshot
            
        try:
            _, DocumentType = _get_document_registry()
            if not DocumentType:
                return snapshot
            
            # Load all reports in parallel
            results = await asyncio.gather(
                self._load_debug_report_summary(DocumentType),
                self._load_impl_plan_summary(DocumentType),
                self._load_test_results_summary(DocumentType),
                return_exceptions=True,
            )
            
            # Process results
            if isinstance(results[0], str):
                snapshot.debug_summary = results[0]
            if isinstance(results[1], str):
                snapshot.implementation_plan = results[1]
            if isinstance(results[2], str):
                snapshot.test_results = results[2]
            
            snapshot.last_updated = datetime.now()
            
        except Exception as e:
            self.logger.debug("reports_load_failed", error=str(e))
        
        return snapshot

    async def _load_debug_report_summary(self, DocumentType) -> str:
        """Load and summarize latest debug report."""
        try:
            doc = await self._doc_registry.get_latest_by_type(DocumentType.DEBUG_REPORT)
            if not doc:
                return ""
            
            parts = []
            if hasattr(doc, 'timestamp') and doc.timestamp:
                parts.append(f"**Last Debug:** {doc.timestamp.strftime('%Y-%m-%d %H:%M')}")
            if hasattr(doc, 'console_errors') and doc.console_errors:
                parts.append(f"- Console errors: {len(doc.console_errors)}")
                for err in doc.console_errors[:2]:
                    parts.append(f"  - `{err[:80]}...`")
            if hasattr(doc, 'root_cause_hypothesis') and doc.root_cause_hypothesis:
                parts.append(f"- Root cause: {doc.root_cause_hypothesis[:150]}")
            if hasattr(doc, 'suggested_fixes') and doc.suggested_fixes:
                parts.append(f"- Suggested fixes: {len(doc.suggested_fixes)}")
            
            return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    async def _load_impl_plan_summary(self, DocumentType) -> str:
        """Load and summarize latest implementation plan."""
        try:
            doc = await self._doc_registry.get_latest_by_type(DocumentType.IMPLEMENTATION_PLAN)
            if not doc:
                return ""
            
            parts = []
            if hasattr(doc, 'summary') and doc.summary:
                parts.append(f"**Plan:** {doc.summary[:200]}")
            if hasattr(doc, 'fixes_planned') and doc.fixes_planned:
                parts.append(f"- Planned tasks: {len(doc.fixes_planned)}")
                for fix in doc.fixes_planned[:3]:
                    if hasattr(fix, 'description'):
                        parts.append(f"  - {fix.description[:60]}")
            if hasattr(doc, 'test_focus_areas') and doc.test_focus_areas:
                parts.append(f"- Focus areas: {', '.join(doc.test_focus_areas[:3])}")
            
            return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    async def _load_test_results_summary(self, DocumentType) -> str:
        """Load and summarize latest test results."""
        try:
            doc = await self._doc_registry.get_latest_by_type(DocumentType.TEST_SPEC)
            if not doc:
                return ""
            
            parts = []
            if hasattr(doc, 'results') and doc.results:
                r = doc.results
                status = "✅ PASSING" if r.failed == 0 else f"❌ {r.failed} FAILING"
                parts.append(f"**Tests:** {status} ({r.passed}/{r.total} passed)")
                if r.failures:
                    parts.append("- Recent failures:")
                    for f in r.failures[:2]:
                        parts.append(f"  - {f.get('type', 'error')}: `{str(f.get('samples', []))[:60]}`")
            if hasattr(doc, 'coverage_targets') and doc.coverage_targets:
                parts.append(f"- Coverage targets: {', '.join(doc.coverage_targets[:3])}")
            
            return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    def _generate_claude_md(self, analysis: ProjectAnalysis, reports: Optional[ReportsSnapshot] = None) -> str:
        """Generate CLAUDE.md content from analysis and reports."""
        lines = [
            "# CLAUDE.md",
            "",
            "This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.",
            "",
            "## For Claude Code - Read This First",
            "",
            "When starting work on this codebase:",
            "",
            "1. **Review this CLAUDE.md** - Understand the project structure, commands, and architecture.",
            "2. **Check the Commands section** - Know how to build, run, and test the project.",
            "3. **Review Key Files** - Understand the main entry points and configuration.",
            "4. **Check Current Status** - Review the Reports section for current issues and plans.",
            "",
        ]

        # Add project-type specific advice
        if analysis.project_type == "electron":
            lines.extend([
                "**Electron-specific:**",
                "- Main process: `src/main/` - Node.js environment",
                "- Renderer process: `src/renderer/` - Browser/React environment",
                "- IPC bridge: `src/preload/` - Secure communication between processes",
                "",
            ])
        elif analysis.project_type in ["react", "vue"]:
            lines.extend([
                f"**{analysis.project_type.capitalize()}-specific:**",
                "- Components are in `src/components/`",
                "- Check for state management (Redux, Vuex, Context)",
                "- Review routing configuration if present",
                "",
            ])

        # === NEW: Reports Section ===
        if reports and (reports.debug_summary or reports.implementation_plan or reports.test_results):
            lines.extend([
                "## Current Project Status",
                "",
                "This section is auto-updated with the latest reports from the development pipeline.",
                "",
            ])
            
            if reports.test_results:
                lines.extend([
                    "### Test Status",
                    "",
                    reports.test_results,
                    "",
                ])
            
            if reports.debug_summary:
                lines.extend([
                    "### Debug Report",
                    "",
                    reports.debug_summary,
                    "",
                ])
            
            if reports.implementation_plan:
                lines.extend([
                    "### Implementation Plan",
                    "",
                    reports.implementation_plan,
                    "",
                ])
            
            if reports.last_updated:
                lines.append(f"*Reports last updated: {reports.last_updated.strftime('%Y-%m-%d %H:%M:%S')}*")
                lines.append("")

        # Project overview
        if analysis.project_name or analysis.description:
            lines.extend([
                "## Project Overview",
                "",
            ])
            if analysis.project_name:
                lines.append(f"**Name:** {analysis.project_name}")
            if analysis.project_type:
                lines.append(f"**Type:** {analysis.project_type.capitalize()}")
            if analysis.description:
                lines.append(f"**Description:** {analysis.description}")
            lines.append("")

        # Commands
        lines.extend([
            "## Commands",
            "",
        ])

        if analysis.dev_command:
            lines.append(f"- **Development:** `{analysis.dev_command}`")
        if analysis.build_command:
            lines.append(f"- **Build:** `{analysis.build_command}`")
        if analysis.test_command:
            lines.append(f"- **Test:** `{analysis.test_command}`")
        if analysis.start_command and analysis.start_command != analysis.dev_command:
            lines.append(f"- **Start:** `{analysis.start_command}`")

        lines.append("")

        # Architecture
        if analysis.source_dirs or analysis.entry_points:
            lines.extend([
                "## Architecture",
                "",
            ])

            if analysis.source_dirs:
                lines.append("**Source Directories:**")
                for src_dir in analysis.source_dirs:
                    lines.append(f"- `{src_dir}/`")
                lines.append("")

            if analysis.entry_points:
                lines.append("**Entry Points:**")
                for entry in analysis.entry_points:
                    lines.append(f"- `{entry}`")
                lines.append("")

        # Key files
        if analysis.key_files:
            lines.extend([
                "## Key Files",
                "",
            ])
            for path, desc in analysis.key_files.items():
                lines.append(f"- `{path}` - {desc}")
            lines.append("")

        # Components
        if analysis.components:
            lines.extend([
                "## Components",
                "",
            ])
            for comp in sorted(analysis.components)[:15]:
                lines.append(f"- `{comp}`")
            if len(analysis.components) > 15:
                lines.append(f"- ... and {len(analysis.components) - 15} more")
            lines.append("")

        # Dependencies
        if analysis.main_dependencies:
            lines.extend([
                "## Key Dependencies",
                "",
            ])
            for dep in analysis.main_dependencies[:10]:
                lines.append(f"- `{dep}`")
            lines.append("")

        # Project-type specific notes
        if analysis.project_type == "electron":
            lines.extend([
                "## Electron Notes",
                "",
                "- Main process runs in Node.js environment",
                "- Renderer process runs in Chromium browser context",
                "- IPC communication via preload script (contextBridge)",
                "- Use `ipcMain.handle()` in main, `ipcRenderer.invoke()` in renderer",
                "",
            ])

        # Add generation timestamp
        lines.extend([
            "---",
            f"*Auto-generated by DocumentationAgent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
        ])

        return "\n".join(lines)
