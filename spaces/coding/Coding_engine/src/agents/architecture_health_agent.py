"""
ArchitectureHealthAgent - LLM-powered architecture quality assessment.

This agent:
1. Evaluates overall codebase architecture quality
2. Scores separation of concerns, coupling, cohesion
3. Identifies architectural anti-patterns
4. Provides recommendations for improvement

Events:
- Subscribes to: GENERATION_COMPLETE, BUILD_SUCCEEDED
- Publishes: DOCUMENT_CREATED (architecture_health_report)
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType

logger = structlog.get_logger(__name__)


@dataclass
class ArchitectureScore:
    """Individual architecture metric score."""
    metric: str
    score: int  # 1-10
    explanation: str
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ArchitectureHealthReport:
    """Complete architecture health report for a project."""
    project_id: str
    overall_score: int = 0  # 1-10
    scores: list[ArchitectureScore] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    file_count: int = 0
    dependency_count: int = 0
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "overall_score": self.overall_score,
            "scores": [
                {
                    "metric": s.metric,
                    "score": s.score,
                    "explanation": s.explanation,
                    "issues": s.issues,
                    "recommendations": s.recommendations,
                }
                for s in self.scores
            ],
            "anti_patterns": self.anti_patterns,
            "recommendations": self.recommendations,
            "file_count": self.file_count,
            "dependency_count": self.dependency_count,
            "generated_at": self.generated_at.isoformat(),
        }


class ArchitectureHealthAgent(AutonomousAgent):
    """
    LLM-powered architecture quality assessment agent.

    Uses Claude to semantically analyze codebase structure,
    dependency patterns, and architectural health.
    """

    COOLDOWN_SECONDS = 120.0  # Run at most once per 2 minutes

    # Architecture metrics to evaluate
    METRICS = [
        "separation_of_concerns",
        "dependency_direction",
        "module_cohesion",
        "coupling",
        "testability",
    ]

    def __init__(
        self,
        name: str = "ArchitectureHealthAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self._last_report: Optional[ArchitectureHealthReport] = None
        self.logger = logger.bind(agent=name)

        self.logger.info(
            "architecture_health_agent_initialized",
            working_dir=working_dir,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.GENERATION_COMPLETE,
            EventType.BUILD_SUCCEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Decide if we should run architecture analysis."""
        for event in events:
            # Always act on GENERATION_COMPLETE
            if event.type == EventType.GENERATION_COMPLETE:
                return True

            # Act on BUILD_SUCCEEDED only periodically
            if event.type == EventType.BUILD_SUCCEEDED:
                # Check if we've analyzed recently
                if self._last_report:
                    elapsed = (datetime.now() - self._last_report.generated_at).total_seconds()
                    if elapsed > 300:  # Only re-analyze every 5 minutes
                        return True
                else:
                    return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Perform architecture health analysis."""
        # Find the first relevant event
        event = events[0] if events else None

        self.logger.info(
            "starting_architecture_analysis",
            event_type=event.type.value if event else "unknown",
            project_id=event.data.get("project_id") if event and event.data else None,
        )

        try:
            project_id = event.data.get("project_id", "default") if event and event.data else "default"

            # Discover file structure
            file_structure = self._discover_file_structure()
            if not file_structure:
                self.logger.warning("no_files_found_for_analysis")
                return

            # Build dependency graph
            dependency_graph = await self._build_dependency_graph(file_structure)

            # Perform LLM-based architecture analysis
            report = await self._assess_architecture(
                project_id,
                file_structure,
                dependency_graph,
            )

            self._last_report = report

            # Publish report
            if self.event_bus:
                await self.event_bus.publish(Event(
                    type=EventType.DOCUMENT_CREATED,
                    source=self.name,
                    data={
                        "document_type": "architecture_health_report",
                        "project_id": report.project_id,
                        "report": report.to_dict(),
                        "overall_score": report.overall_score,
                        "anti_patterns_count": len(report.anti_patterns),
                    },
                ))

            # Update shared state
            if self.shared_state:
                self.shared_state.set(
                    f"architecture_health_{project_id}",
                    {
                        "overall_score": report.overall_score,
                        "file_count": report.file_count,
                        "anti_patterns": report.anti_patterns[:5],  # Top 5
                    }
                )

            self.logger.info(
                "architecture_analysis_complete",
                overall_score=report.overall_score,
                file_count=report.file_count,
                anti_patterns=len(report.anti_patterns),
            )

        except Exception as e:
            self.logger.error("architecture_analysis_failed", error=str(e))

    def _discover_file_structure(self) -> dict:
        """Discover project file structure organized by directory."""
        working_path = Path(self.working_dir)
        src_dir = working_path / "src"

        if not src_dir.exists():
            src_dir = working_path

        structure = {}
        skip_dirs = {"node_modules", ".git", "dist", "build", "__pycache__", ".next", "coverage"}
        extensions = {".ts", ".tsx", ".js", ".jsx", ".py", ".vue", ".svelte"}

        for file_path in src_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if any(skip in file_path.parts for skip in skip_dirs):
                continue
            if file_path.suffix not in extensions:
                continue

            try:
                rel_path = str(file_path.relative_to(working_path))
                parent_dir = str(file_path.parent.relative_to(working_path))

                if parent_dir not in structure:
                    structure[parent_dir] = []
                structure[parent_dir].append(rel_path)
            except ValueError:
                pass

        return structure

    async def _build_dependency_graph(self, file_structure: dict) -> dict:
        """Build a simple dependency graph from imports."""
        graph = {}
        working_path = Path(self.working_dir)

        # Flatten files
        all_files = []
        for files in file_structure.values():
            all_files.extend(files)

        for file_path in all_files[:50]:  # Limit for performance
            full_path = working_path / file_path
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                imports = self._extract_imports(content, file_path)
                if imports:
                    graph[file_path] = imports
            except Exception:
                pass

        return graph

    def _extract_imports(self, content: str, file_path: str) -> list[str]:
        """Extract import statements from code."""
        imports = []

        # TypeScript/JavaScript imports
        ts_patterns = [
            r'import\s+.*?\s+from\s+[\'"](.+?)[\'"]',
            r'import\s*\([\'"](.+?)[\'"]\)',
            r'require\s*\([\'"](.+?)[\'"]\)',
        ]

        # Python imports
        py_patterns = [
            r'from\s+(\S+)\s+import',
            r'import\s+(\S+)',
        ]

        patterns = ts_patterns if file_path.endswith(('.ts', '.tsx', '.js', '.jsx')) else py_patterns

        for pattern in patterns:
            matches = re.findall(pattern, content)
            imports.extend(matches)

        # Filter to local imports only (not node_modules)
        local_imports = [
            imp for imp in imports
            if imp.startswith('.') or imp.startswith('@/') or imp.startswith('src/')
        ]

        return local_imports[:20]  # Limit per file

    async def _assess_architecture(
        self,
        project_id: str,
        file_structure: dict,
        dependency_graph: dict,
    ) -> ArchitectureHealthReport:
        """
        Use LLM to assess architecture health.

        Args:
            project_id: Project identifier
            file_structure: Directory -> files mapping
            dependency_graph: File -> imports mapping

        Returns:
            ArchitectureHealthReport with scores and recommendations
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        report = ArchitectureHealthReport(project_id=project_id)
        report.file_count = sum(len(files) for files in file_structure.values())
        report.dependency_count = sum(len(deps) for deps in dependency_graph.values())

        # Format structure for LLM
        structure_text = json.dumps(file_structure, indent=2)[:2000]
        deps_text = json.dumps(dependency_graph, indent=2)[:2000]

        prompt = f"""Assess the architecture health of this codebase:

## FILE STRUCTURE:
{structure_text}

## DEPENDENCY GRAPH:
{deps_text}

## ANALYSIS TASK:

Score each metric from 1-10 and provide analysis:

1. **Separation of Concerns** (UI/Logic/Data layers separated?)
2. **Dependency Direction** (no upward dependencies? layers respect boundaries?)
3. **Module Cohesion** (related code grouped together?)
4. **Coupling** (minimal cross-module dependencies?)
5. **Testability** (injectable dependencies? no hard-coded singletons?)

Also identify:
- Anti-patterns found (God components, circular deps, feature envy)
- Top 3 recommendations for improvement

## RESPONSE FORMAT:

Respond with JSON:
```json
{{
  "scores": [
    {{
      "metric": "separation_of_concerns",
      "score": 7,
      "explanation": "Good UI/Logic separation but data layer mixed with components",
      "issues": ["API calls in components", "State mixed with UI"],
      "recommendations": ["Move API calls to services", "Use custom hooks for state"]
    }}
  ],
  "anti_patterns": ["God component in App.tsx", "Circular dependency: A->B->A"],
  "overall_recommendations": ["Introduce service layer", "Split large components"]
}}
```

Be realistic. Most codebases score 4-7. Only exceptional code scores 8+.
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=120)
            result = await tool.execute(
                prompt=prompt,
                context="Architecture health assessment",
                agent_type="architecture_analyzer",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))

                # Extract scores
                for score_data in analysis.get("scores", []):
                    score = ArchitectureScore(
                        metric=score_data.get("metric", "unknown"),
                        score=score_data.get("score", 5),
                        explanation=score_data.get("explanation", ""),
                        issues=score_data.get("issues", []),
                        recommendations=score_data.get("recommendations", []),
                    )
                    report.scores.append(score)

                # Extract anti-patterns
                report.anti_patterns = analysis.get("anti_patterns", [])

                # Extract recommendations
                report.recommendations = analysis.get("overall_recommendations", [])

                # Calculate overall score
                if report.scores:
                    report.overall_score = round(
                        sum(s.score for s in report.scores) / len(report.scores)
                    )

        except Exception as e:
            self.logger.warning("llm_architecture_analysis_failed", error=str(e))
            # Provide fallback scores
            report.overall_score = 5
            report.anti_patterns = ["Analysis failed - manual review recommended"]

        return report

    def get_health_summary(self) -> dict:
        """Get summary of current architecture health."""
        if not self._last_report:
            return {
                "status": "no_report",
                "message": "No architecture health report generated yet",
            }

        return {
            "status": "available",
            "project_id": self._last_report.project_id,
            "overall_score": self._last_report.overall_score,
            "file_count": self._last_report.file_count,
            "anti_patterns_count": len(self._last_report.anti_patterns),
            "top_anti_patterns": self._last_report.anti_patterns[:3],
            "top_recommendations": self._last_report.recommendations[:3],
            "generated_at": self._last_report.generated_at.isoformat(),
        }

    async def analyze_specific_module(self, module_path: str) -> dict:
        """
        Analyze a specific module/directory for architecture issues.

        Args:
            module_path: Path to the module to analyze

        Returns:
            Dict with module-specific analysis
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        working_path = Path(self.working_dir)
        full_path = working_path / module_path

        if not full_path.exists():
            return {"error": f"Module not found: {module_path}"}

        # Collect files in module
        files = []
        for file_path in full_path.rglob("*"):
            if file_path.is_file() and file_path.suffix in {".ts", ".tsx", ".js", ".jsx", ".py"}:
                try:
                    rel = str(file_path.relative_to(working_path))
                    files.append(rel)
                except ValueError:
                    pass

        if not files:
            return {"error": f"No source files in module: {module_path}"}

        prompt = f"""Analyze this module for architecture issues:

MODULE: {module_path}
FILES: {json.dumps(files[:20], indent=2)}

Assess:
1. Is this module cohesive? (single responsibility)
2. Does it have appropriate boundaries?
3. Are dependencies minimal and explicit?
4. Can it be tested in isolation?

Return JSON:
```json
{{
  "cohesion_score": 7,
  "issues": ["Mixed concerns: UI and API in same files"],
  "suggestions": ["Split into components/ and services/"]
}}
```
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context=f"Module analysis: {module_path}",
                agent_type="module_analyzer",
            )

            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))

        except Exception as e:
            self.logger.warning("module_analysis_failed", module=module_path, error=str(e))

        return {"error": "Analysis failed"}
