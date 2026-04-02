"""
Code Quality Agent - Autonomous agent for code cleanup, refactoring, and documentation.

Analyzes the codebase after tests pass to:
- Generate documentation (README, CLAUDE.md, JSDoc)
- Identify unused/orphan files for cleanup
- Find large files (>3000 lines) needing refactoring
- Produce QualityReports for Generator to implement
"""

import asyncio
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
from uuid import uuid4
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    quality_report_event,
    code_fix_needed_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool
from ..registry.document_registry import DocumentRegistry
from ..registry.documents import (
    TestSpec,
    QualityReport,
    DocumentationTask,
    CleanupTask,
    RefactorTask,
)
from ..registry.document_types import DocumentType
from .autonomous_base import AutonomousAgent


logger = structlog.get_logger(__name__)


# File extensions to analyze
CODE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go",
    ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp",
}

# Files to skip during analysis
SKIP_PATTERNS = {
    "node_modules", ".git", "dist", "build", "out",
    "__pycache__", ".venv", "venv", ".next",
}


class CodeQualityAgent(AutonomousAgent):
    """
    Autonomous agent that analyzes code quality and produces improvement plans.

    Subscribes to:
    - TEST_SPEC_CREATED: When TesterTeam finishes and tests pass

    Publishes:
    - QUALITY_REPORT_CREATED: When analysis is complete
    - CODE_FIX_NEEDED: For high-priority refactoring tasks

    Workflow:
    1. Waits for tests to pass (TEST_SPEC_CREATED with passed results)
    2. Analyzes codebase for documentation gaps, unused files, large files
    3. Uses Claude to intelligently identify orphan files
    4. Writes QualityReport to document registry
    5. Generator picks up QualityReport and implements improvements
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        document_registry: Optional[DocumentRegistry] = None,
        max_file_lines: int = 3000,
        cleanup_confidence_threshold: float = 0.9,
        timeout: int = 300,
    ):
        """
        Initialize the CodeQualityAgent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project working directory
            document_registry: Document registry for inter-agent communication
            max_file_lines: Maximum lines before suggesting refactor (default 3000)
            cleanup_confidence_threshold: Minimum confidence for deletion suggestions
            timeout: Claude CLI timeout in seconds
        """
        super().__init__(name, event_bus, shared_state, working_dir)
        self.document_registry = document_registry
        self.max_file_lines = max_file_lines
        self.cleanup_confidence_threshold = cleanup_confidence_threshold
        self.timeout = timeout
        self.tool = ClaudeCodeTool(working_dir=working_dir, timeout=timeout)
        self._pending_test_specs: list[TestSpec] = []
        self._last_analysis_time: Optional[float] = None
        self._analysis_cooldown = 60.0  # Minimum seconds between analyses

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.TEST_SPEC_CREATED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if we should run quality analysis.

        Acts when:
        - TEST_SPEC_CREATED event received with passing tests
        - Not in cooldown period
        """
        import time

        # Check cooldown
        if self._last_analysis_time:
            elapsed = time.time() - self._last_analysis_time
            if elapsed < self._analysis_cooldown:
                return False

        # Check for TEST_SPEC_CREATED events
        test_spec_events = [e for e in events if e.type == EventType.TEST_SPEC_CREATED]

        if not test_spec_events and not self._pending_test_specs:
            # Also check document registry for pending TestSpecs
            if self.document_registry:
                pending = await self.document_registry.get_pending_for_agent("CodeQuality")
                self._pending_test_specs = [d for d in pending if isinstance(d, TestSpec)]
            return len(self._pending_test_specs) > 0

        # Load test specs from events
        if self.document_registry:
            for event in test_spec_events:
                doc_id = event.data.get("doc_id")
                if doc_id:
                    doc = await self.document_registry.read_document(doc_id)
                    if doc and isinstance(doc, TestSpec):
                        # Only act if tests passed
                        if doc.results and doc.results.failed == 0:
                            self._pending_test_specs.append(doc)
                            self.logger.info(
                                "test_spec_loaded",
                                doc_id=doc_id,
                                tests_passed=doc.results.passed,
                            )

        return len(self._pending_test_specs) > 0

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Run quality analysis on the codebase.

        1. Find documentation gaps
        2. Find unused/orphan files
        3. Find large files needing refactoring
        4. Write QualityReport to registry
        """
        import time
        self._last_analysis_time = time.time()

        self.logger.info("starting_quality_analysis", working_dir=self.working_dir)

        # Analyze codebase
        documentation_tasks = await self._find_documentation_gaps()
        cleanup_tasks = await self._find_unused_files()
        refactor_tasks = await self._find_large_files()

        # Count statistics
        total_files = self._count_code_files()

        # Determine if action is required
        requires_action = (
            len(documentation_tasks) > 0 or
            len(cleanup_tasks) > 0 or
            len(refactor_tasks) > 0
        )

        # Write QualityReport
        timestamp = datetime.now()
        doc_id = f"quality_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

        quality_report = QualityReport(
            id=doc_id,
            timestamp=timestamp,
            source_agent=self.name,
            responding_to=self._pending_test_specs[0].id if self._pending_test_specs else None,
            documentation_tasks=documentation_tasks,
            cleanup_tasks=cleanup_tasks,
            refactor_tasks=refactor_tasks,
            total_files_analyzed=total_files,
            unused_files_found=len(cleanup_tasks),
            large_files_found=len(refactor_tasks),
            documentation_gaps=len(documentation_tasks),
            requires_action=requires_action,
        )

        # Write to registry
        if self.document_registry:
            await self.document_registry.write_document(quality_report, priority=3)

            # Mark test specs as consumed
            for spec in self._pending_test_specs:
                await self.document_registry.mark_consumed(spec.id, "CodeQuality")

            self.logger.info(
                "quality_report_written",
                doc_id=doc_id,
                documentation_gaps=len(documentation_tasks),
                cleanup_tasks=len(cleanup_tasks),
                refactor_tasks=len(refactor_tasks),
                requires_action=requires_action,
            )

        # Clear pending test specs
        self._pending_test_specs = []

        # Publish event using typed factory function
        await self.event_bus.publish(quality_report_event(
            source=self.name,
            doc_id=doc_id,
            requires_action=requires_action,
            cleanup_tasks=len(cleanup_tasks),
            refactor_tasks=len(refactor_tasks),
            cleanup_items=[{"id": t.id, "file_path": t.file_path, "reason": t.reason} for t in cleanup_tasks],
            refactor_items=[{"id": t.id, "file_path": t.file_path, "current_lines": t.current_lines} for t in refactor_tasks],
        ))

        # For high-priority refactoring tasks, also trigger CODE_FIX_NEEDED
        for task in refactor_tasks:
            if task.current_lines > self.max_file_lines * 2:  # Very large files
                await self.event_bus.publish(code_fix_needed_event(
                    source=self.name,
                    file_path=task.file_path,
                    error_message=f"File has {task.current_lines} lines, needs refactoring",
                    fix_type="refactor",
                    task_id=task.id,
                    data={
                        "quality_report_id": doc_id,
                        "suggested_splits": task.suggested_splits,
                    },
                ))

        return quality_report_event(
            source=self.name,
            doc_id=doc_id,
            requires_action=requires_action,
            cleanup_tasks=len(cleanup_tasks),
            refactor_tasks=len(refactor_tasks),
        )

    async def _find_documentation_gaps(self) -> list[DocumentationTask]:
        """Find missing or outdated documentation."""
        tasks = []
        task_id = 0

        # Check for README.md
        readme_path = Path(self.working_dir) / "README.md"
        if not readme_path.exists():
            task_id += 1
            tasks.append(DocumentationTask(
                id=f"doc_{task_id:03d}",
                task_type="readme",
                target_path="README.md",
                scope=["project root"],
                priority=1,
                description="Create project README with setup instructions and overview",
            ))
        elif readme_path.stat().st_size < 500:
            task_id += 1
            tasks.append(DocumentationTask(
                id=f"doc_{task_id:03d}",
                task_type="readme",
                target_path="README.md",
                scope=["project root"],
                priority=2,
                description="README is minimal, consider expanding with more details",
            ))

        # Check for CLAUDE.md
        claude_path = Path(self.working_dir) / "CLAUDE.md"
        if not claude_path.exists():
            task_id += 1
            tasks.append(DocumentationTask(
                id=f"doc_{task_id:03d}",
                task_type="claudemd",
                target_path="CLAUDE.md",
                scope=["project root"],
                priority=1,
                description="Create CLAUDE.md for AI assistant guidance",
            ))

        # Check src directory for JSDoc coverage
        src_dir = Path(self.working_dir) / "src"
        if src_dir.exists():
            undocumented = await self._find_undocumented_exports(src_dir)
            if undocumented:
                task_id += 1
                tasks.append(DocumentationTask(
                    id=f"doc_{task_id:03d}",
                    task_type="jsdoc",
                    target_path="src/",
                    scope=undocumented[:10],  # Top 10 files
                    priority=3,
                    description=f"Add JSDoc comments to {len(undocumented)} exported functions/classes",
                ))

        return tasks

    async def _find_undocumented_exports(self, src_dir: Path) -> list[str]:
        """Find TypeScript/JavaScript files with undocumented exports."""
        undocumented = []

        for root, dirs, files in os.walk(src_dir):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS]

            for file in files:
                if file.endswith(('.ts', '.tsx', '.js', '.jsx')):
                    file_path = Path(root) / file
                    rel_path = str(file_path.relative_to(self.working_dir))

                    try:
                        content = file_path.read_text(encoding='utf-8')

                        # Simple heuristic: check for exports without JSDoc
                        has_export = 'export ' in content
                        has_jsdoc = '/**' in content

                        if has_export and not has_jsdoc:
                            undocumented.append(rel_path)
                    except Exception:
                        pass

        return undocumented

    async def _find_unused_files(self) -> list[CleanupTask]:
        """
        Find files that appear to be unused.

        Uses Claude to analyze import/require statements and determine
        which files are not referenced anywhere.
        """
        tasks = []

        # Get all code files
        code_files = list(self._iter_code_files())

        if len(code_files) < 5:
            # Too few files to analyze
            return tasks

        # Build a simple import graph
        import_map = {}
        for file_path in code_files:
            try:
                content = Path(file_path).read_text(encoding='utf-8')
                imports = self._extract_imports(content)
                import_map[file_path] = imports
            except Exception:
                pass

        # Find files that are never imported
        all_imported = set()
        for imports in import_map.values():
            all_imported.update(imports)

        # Entry points that don't need to be imported
        entry_points = {'main.ts', 'main.tsx', 'index.ts', 'index.tsx', 'App.tsx', 'app.ts'}

        task_id = 0
        for file_path in code_files:
            rel_path = Path(file_path).relative_to(self.working_dir)
            file_name = rel_path.name

            # Skip entry points
            if file_name in entry_points:
                continue

            # Check if this file is imported anywhere
            is_imported = any(
                str(rel_path.with_suffix('')) in imp or file_name in imp
                for imp in all_imported
            )

            if not is_imported:
                # Use Claude to confirm if file is truly unused
                confidence = await self._analyze_file_usage(file_path)

                if confidence >= self.cleanup_confidence_threshold:
                    task_id += 1
                    stat = Path(file_path).stat()
                    tasks.append(CleanupTask(
                        id=f"cleanup_{task_id:03d}",
                        file_path=str(rel_path),
                        reason="orphan_file",
                        confidence=confidence,
                        references_found=0,
                        last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        size_bytes=stat.st_size,
                    ))

        return tasks[:20]  # Limit to 20 cleanup suggestions

    def _extract_imports(self, content: str) -> set[str]:
        """Extract import paths from file content."""
        imports = set()
        lines = content.split('\n')

        for line in lines:
            line = line.strip()

            # ES6 imports
            if line.startswith('import ') and ' from ' in line:
                try:
                    path = line.split(' from ')[1].strip().strip(';').strip('"\'')
                    imports.add(path)
                except Exception:
                    pass

            # CommonJS requires
            if 'require(' in line:
                try:
                    start = line.index('require(') + 8
                    end = line.index(')', start)
                    path = line[start:end].strip('"\'')
                    imports.add(path)
                except Exception:
                    pass

        return imports

    async def _analyze_file_usage(self, file_path: str) -> float:
        """
        Use Claude to analyze if a file is truly unused.

        Returns confidence score (0.0-1.0) that file can be safely deleted.
        """
        # First, get quick heuristic result
        heuristic_confidence = self._quick_usage_heuristic(file_path)

        # If heuristic is uncertain (0.4-0.8), use LLM for deeper analysis
        if 0.4 < heuristic_confidence < 0.8:
            try:
                llm_result = await self._analyze_file_usage_with_llm(file_path)
                if llm_result is not None:
                    return llm_result
            except Exception as e:
                self.logger.warning("llm_file_analysis_failed", file=file_path, error=str(e))

        return heuristic_confidence

    def _quick_usage_heuristic(self, file_path: str) -> float:
        """Quick heuristic check for file usage."""
        try:
            content = Path(file_path).read_text(encoding='utf-8')

            # Lower confidence for files with side effects
            has_side_effects = any(marker in content for marker in [
                'addEventListener',
                'window.',
                'document.',
                'global.',
                'process.env',
            ])

            if has_side_effects:
                return 0.5

            # Lower confidence for test files (they might be needed)
            if '.test.' in file_path or '.spec.' in file_path:
                return 0.3

            # Lower confidence for config files
            if 'config' in file_path.lower():
                return 0.4

            # Lower confidence for index/barrel files
            file_name = Path(file_path).name
            if file_name.startswith('index.'):
                return 0.3

            return 0.9

        except Exception:
            return 0.0

    async def _analyze_file_usage_with_llm(self, file_path: str) -> Optional[float]:
        """
        Use LLM to analyze if a file can be safely deleted.

        This provides deeper analysis by understanding:
        - Import chain relationships
        - Barrel exports and re-exports
        - Dynamic imports and lazy loading
        - Entry point files
        - Side effect files
        """
        import json
        import re

        try:
            rel_path = Path(file_path).relative_to(self.working_dir)
            content = Path(file_path).read_text(encoding='utf-8')

            # Get import context from other files
            import_context = self._gather_import_context(str(rel_path))

            prompt = f"""Analyze if this file can be safely deleted from the codebase.

## FILE TO ANALYZE: {rel_path}

## FILE CONTENT (first 2000 chars):
```
{content[:2000]}
```

## FILES THAT MIGHT IMPORT THIS:
{import_context}

## ANALYSIS REQUIRED:

Consider these factors:
1. **Direct imports**: Is this file imported directly by any other file?
2. **Barrel exports**: Is this an index.ts that re-exports for other modules?
3. **Dynamic imports**: Could it be loaded via lazy loading (import() or require())?
4. **Entry point**: Is this a webpack/vite entry point or script target?
5. **Side effects**: Does it register global handlers, modify prototypes, etc.?
6. **Config file**: Is it a configuration file loaded by name convention?

## COMMON FALSE POSITIVES (files that SEEM unused but aren't):
- index.ts/index.tsx (barrel exports)
- Files imported dynamically: `import('./path')`
- Webpack entry points
- Test setup files
- CSS/style modules
- Public assets

Respond with this JSON:
```json
{{
    "safe_to_delete": true,
    "confidence": 0.9,
    "reason": "Brief explanation",
    "potential_dependents": [],
    "risk_factors": []
}}
```
"""

            result = await self.tool.execute(
                prompt=prompt,
                skill="code-generation",
                skill_tier="minimal",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                llm_result = json.loads(json_match.group(1))

                if llm_result.get("safe_to_delete", False):
                    return llm_result.get("confidence", 0.7)
                else:
                    # Not safe to delete
                    return 0.2

            return None

        except Exception as e:
            self.logger.warning("llm_file_usage_analysis_failed", error=str(e))
            return None

    def _gather_import_context(self, target_file: str) -> str:
        """Gather import statements from the codebase that might reference the target file."""
        context_lines = []
        target_stem = Path(target_file).stem
        target_parent = str(Path(target_file).parent)

        for file_path in self._iter_code_files():
            try:
                content = Path(file_path).read_text(encoding='utf-8')
                rel_path = str(Path(file_path).relative_to(self.working_dir))

                # Find lines that might import our target
                for line_num, line in enumerate(content.split('\n'), 1):
                    if 'import' in line or 'require' in line:
                        # Check if line references our target
                        if target_stem in line or target_parent in line:
                            context_lines.append(f"{rel_path}:{line_num}: {line.strip()}")

            except Exception:
                pass

        if context_lines:
            return "\n".join(context_lines[:20])  # Limit to 20 lines
        return "No imports found that reference this file"

    async def _find_large_files(self) -> list[RefactorTask]:
        """Find files that exceed the line limit and need refactoring."""
        tasks = []
        task_id = 0

        for file_path in self._iter_code_files():
            try:
                content = Path(file_path).read_text(encoding='utf-8')
                lines = content.count('\n') + 1

                if lines > self.max_file_lines:
                    rel_path = str(Path(file_path).relative_to(self.working_dir))

                    # Generate suggested splits based on content analysis
                    suggested_splits = self._suggest_file_splits(file_path, content)

                    task_id += 1
                    tasks.append(RefactorTask(
                        id=f"refactor_{task_id:03d}",
                        file_path=rel_path,
                        reason="too_large",
                        current_lines=lines,
                        target_lines=500,
                        suggested_splits=suggested_splits,
                        complexity_score=lines / self.max_file_lines,
                        description=f"File has {lines} lines, consider splitting into {len(suggested_splits)} files",
                    ))

            except Exception:
                pass

        # Sort by line count descending
        tasks.sort(key=lambda t: t.current_lines, reverse=True)
        return tasks[:10]  # Top 10 largest files

    def _suggest_file_splits(self, file_path: str, content: str) -> list[str]:
        """Suggest how to split a large file based on its content."""
        suggestions = []
        file_name = Path(file_path).stem
        ext = Path(file_path).suffix

        # Look for class definitions
        classes = []
        for line in content.split('\n'):
            if line.strip().startswith('class ') or line.strip().startswith('export class '):
                try:
                    class_name = line.split('class ')[1].split()[0].strip('{:')
                    classes.append(class_name)
                except Exception:
                    pass

        # Suggest separate files for each class
        for cls in classes[:5]:  # Limit to 5
            suggestions.append(f"{cls.lower()}{ext}")

        # If no classes found, suggest by function groups
        if not suggestions:
            suggestions = [
                f"{file_name}.types{ext}",
                f"{file_name}.utils{ext}",
                f"{file_name}.hooks{ext}" if ext in ['.tsx', '.jsx'] else f"{file_name}.helpers{ext}",
            ]

        return suggestions

    def _iter_code_files(self):
        """Iterate over all code files in the working directory."""
        for root, dirs, files in os.walk(self.working_dir):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS]

            for file in files:
                if Path(file).suffix.lower() in CODE_EXTENSIONS:
                    yield os.path.join(root, file)

    def _count_code_files(self) -> int:
        """Count total code files in the project."""
        return sum(1 for _ in self._iter_code_files())

    # =========================================================================
    # Phase 8: LLM-Enhanced Circular Import Detection
    # =========================================================================

    async def detect_circular_imports(self) -> list[dict]:
        """
        Detect circular import dependencies using LLM analysis.

        Circular imports cause:
        - Runtime errors (undefined imports)
        - Hard-to-debug initialization issues
        - Module loading order problems

        Returns:
            List of circular dependency cycles with fix suggestions
        """
        import json
        import re

        # Build import graph
        import_graph = self._build_import_graph()

        if not import_graph:
            return []

        # First, try algorithmic cycle detection
        algorithmic_cycles = self._find_cycles_dfs(import_graph)

        # If we found obvious cycles, return them
        if algorithmic_cycles:
            return [
                {
                    "cycle": cycle,
                    "break_at": cycle[len(cycle) // 2],  # Suggest breaking in middle
                    "fix": f"Move shared types to a separate file or use lazy imports",
                    "detection_method": "algorithmic",
                }
                for cycle in algorithmic_cycles[:5]  # Limit to 5
            ]

        # Use LLM for complex pattern detection
        return await self._detect_circular_imports_with_llm(import_graph)

    def _build_import_graph(self) -> dict[str, list[str]]:
        """Build a graph of file imports."""
        graph = {}

        for file_path in self._iter_code_files():
            try:
                rel_path = str(Path(file_path).relative_to(self.working_dir))
                content = Path(file_path).read_text(encoding='utf-8')
                imports = self._extract_local_imports(content, rel_path)

                if imports:
                    graph[rel_path] = imports

            except Exception:
                pass

        return graph

    def _extract_local_imports(self, content: str, source_file: str) -> list[str]:
        """Extract local (relative) import paths from file content."""
        imports = []
        source_dir = str(Path(source_file).parent)

        for line in content.split('\n'):
            line = line.strip()

            # ES6 imports
            if line.startswith('import ') and ' from ' in line:
                try:
                    path = line.split(' from ')[1].strip().strip(';').strip('"\'')

                    # Only local imports
                    if path.startswith('.'):
                        resolved = self._resolve_import_path(path, source_dir)
                        if resolved:
                            imports.append(resolved)
                except Exception:
                    pass

            # CommonJS requires
            if 'require(' in line:
                try:
                    start = line.index('require(') + 8
                    end = line.index(')', start)
                    path = line[start:end].strip('"\'')

                    if path.startswith('.'):
                        resolved = self._resolve_import_path(path, source_dir)
                        if resolved:
                            imports.append(resolved)
                except Exception:
                    pass

        return imports

    def _resolve_import_path(self, import_path: str, source_dir: str) -> Optional[str]:
        """Resolve relative import to actual file path."""
        import os

        # Handle relative paths
        if import_path.startswith('./'):
            resolved = os.path.normpath(os.path.join(source_dir, import_path[2:]))
        elif import_path.startswith('../'):
            resolved = os.path.normpath(os.path.join(source_dir, import_path))
        else:
            return None

        # Try common extensions
        for ext in ['.ts', '.tsx', '.js', '.jsx', '']:
            candidate = resolved + ext if not resolved.endswith(ext) else resolved

            # Check for index files
            if Path(self.working_dir, candidate).exists():
                return candidate

            # Check for index file in directory
            index_candidate = os.path.join(candidate, 'index.ts')
            if Path(self.working_dir, index_candidate).exists():
                return index_candidate

            index_candidate = os.path.join(candidate, 'index.tsx')
            if Path(self.working_dir, index_candidate).exists():
                return index_candidate

        return resolved  # Return unresolved path

    def _find_cycles_dfs(self, graph: dict[str, list[str]]) -> list[list[str]]:
        """Find cycles in import graph using DFS."""
        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node: str):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if len(cycle) >= 2:  # At least 2 nodes
                        cycles.append(cycle)
                elif neighbor not in visited and neighbor in graph:
                    dfs(neighbor)

            path.pop()
            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    async def _detect_circular_imports_with_llm(
        self,
        import_graph: dict[str, list[str]],
    ) -> list[dict]:
        """
        Use LLM to detect complex circular import patterns.

        This catches:
        - Indirect cycles (A -> B -> C -> A)
        - Barrel export cycles
        - Type-only circular imports (safe but worth noting)
        - Dynamic import cycles
        """
        import json
        import re

        # Format graph for LLM
        graph_text = json.dumps(import_graph, indent=2)[:4000]

        prompt = f"""Analyze this import graph for circular dependencies:

## IMPORT GRAPH:
```json
{graph_text}
```

## TASK:

Find ALL circular import dependencies. A cycle exists when file A imports file B,
which (directly or indirectly) imports file A again.

Types of cycles to find:
1. **Direct cycles**: A -> B -> A
2. **Indirect cycles**: A -> B -> C -> A
3. **Barrel export cycles**: index.ts files re-exporting each other
4. **Type-only cycles**: Only types are imported (less severe but note them)

For each cycle found, provide:
1. Full path of the cycle
2. Which file to break the cycle at (usually the "leaf" node)
3. Specific fix suggestion

## RESPONSE FORMAT:

```json
{{
  "cycles": [
    {{
      "cycle": ["src/a.ts", "src/b.ts", "src/a.ts"],
      "break_at": "src/b.ts",
      "fix": "Move shared types to src/types/shared.ts",
      "severity": "high",
      "type": "direct"
    }}
  ],
  "summary": "Found X cycles, Y high severity"
}}
```

If no cycles found, return: {{"cycles": [], "summary": "No circular imports detected"}}
"""

        try:
            result = await self.tool.execute(
                prompt=prompt,
                skill="code-generation",
                skill_tier="minimal",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))
                return analysis.get("cycles", [])

        except Exception as e:
            self.logger.warning("llm_circular_import_detection_failed", error=str(e))

        return []

    async def analyze_import_health(self) -> dict:
        """
        Comprehensive import health analysis.

        Returns summary of:
        - Total imports analyzed
        - Circular dependencies found
        - Barrel export issues
        - Recommended refactorings
        """
        import_graph = self._build_import_graph()
        cycles = await self.detect_circular_imports()

        # Count statistics
        total_files = len(import_graph)
        total_imports = sum(len(imports) for imports in import_graph.values())

        # Identify barrel exports (index.ts files)
        barrel_files = [f for f in import_graph.keys() if f.endswith(('index.ts', 'index.tsx', 'index.js'))]

        return {
            "total_files_analyzed": total_files,
            "total_import_edges": total_imports,
            "circular_dependencies": len(cycles),
            "cycles": cycles,
            "barrel_exports": len(barrel_files),
            "health_score": max(0, 10 - len(cycles) * 2),  # Deduct 2 per cycle
            "recommendations": [
                "Fix circular imports by extracting shared types"
                if cycles else "Import structure is healthy"
            ],
        }

    def _get_action_description(self) -> str:
        return "Analyzing code quality"


async def create_code_quality_agent(
    event_bus: EventBus,
    shared_state: SharedState,
    working_dir: str,
    document_registry: Optional[DocumentRegistry] = None,
) -> CodeQualityAgent:
    """Create and start a CodeQualityAgent."""
    agent = CodeQualityAgent(
        name="CodeQuality",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=working_dir,
        document_registry=document_registry,
    )
    await agent.start()
    return agent
