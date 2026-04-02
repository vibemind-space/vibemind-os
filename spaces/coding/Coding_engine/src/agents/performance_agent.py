"""
Performance Agent - Autonomous agent for performance analysis and optimization.

Analyzes generated applications for:
- Bundle size optimization (webpack/vite bundle analysis)
- Lighthouse CI integration (Core Web Vitals)
- Memory leak detection hints
- Load time optimization suggestions

Publishes:
- PERFORMANCE_ANALYSIS_STARTED: Analysis initiated
- PERFORMANCE_BENCHMARK_PASSED: All metrics within thresholds
- PERFORMANCE_ISSUE_DETECTED: Performance problem found
- BUNDLE_SIZE_WARNING: Bundle exceeds size threshold
- LIGHTHOUSE_SCORE_LOW: Lighthouse score below threshold
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    performance_analysis_started_event,
    bundle_size_warning_event,
    lighthouse_score_low_event,
    performance_issue_detected_event,
    performance_benchmark_passed_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool
from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin


logger = structlog.get_logger(__name__)


# Performance thresholds
BUNDLE_SIZE_THRESHOLDS = {
    "js_main_kb": 250,      # Main JS bundle max size (KB)
    "css_main_kb": 50,      # Main CSS bundle max size (KB)
    "total_kb": 500,        # Total bundle size (KB)
    "chunk_kb": 100,        # Individual chunk max size (KB)
}

LIGHTHOUSE_THRESHOLDS = {
    "performance": 70,      # Minimum performance score
    "accessibility": 80,    # Minimum accessibility score
    "best_practices": 80,   # Minimum best practices score
    "seo": 70,              # Minimum SEO score
}

# Patterns indicating potential performance issues
PERFORMANCE_ANTIPATTERNS = {
    "large_imports": {
        "pattern": r"import\s+\*\s+as\s+\w+\s+from\s+['\"](?:lodash|moment|rxjs)['\"]",
        "description": "Full library import - use specific imports for tree-shaking",
        "severity": "medium",
    },
    "sync_require": {
        "pattern": r"require\(['\"].*?['\"]\.(?:json|css|scss)['\"]?\)",
        "description": "Synchronous require - consider dynamic import for code splitting",
        "severity": "low",
    },
    "inline_styles": {
        "pattern": r"style\s*=\s*\{\s*\{[^}]{200,}",
        "description": "Large inline styles - consider CSS modules or styled-components",
        "severity": "low",
    },
    "missing_memo": {
        "pattern": r"export\s+(?:default\s+)?function\s+\w+.*\breturn\s*\(\s*<",
        "description": "Functional component without memo - consider React.memo for expensive renders",
        "severity": "low",
    },
    "useeffect_deps": {
        "pattern": r"useEffect\s*\(\s*\(\)\s*=>\s*\{[^}]+\}\s*\)",
        "description": "useEffect without dependency array - may cause infinite loops",
        "severity": "high",
    },
    "large_state": {
        "pattern": r"useState\s*\(\s*\{[^}]{500,}\}",
        "description": "Large initial state object - consider splitting or using reducer",
        "severity": "medium",
    },
    "memory_leak_interval": {
        "pattern": r"setInterval\s*\([^)]+\)[^}]*(?!clearInterval)",
        "description": "setInterval without cleanup - potential memory leak",
        "severity": "high",
    },
    "memory_leak_listener": {
        "pattern": r"addEventListener\s*\([^)]+\)[^}]*(?!removeEventListener)",
        "description": "Event listener without cleanup - potential memory leak",
        "severity": "medium",
    },
}


class PerformanceAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for performance analysis.

    Triggers on:
    - BUILD_SUCCEEDED: Analyze bundle after successful build
    - E2E_TEST_PASSED: Run Lighthouse after UI tests pass
    - DEPLOY_SUCCEEDED: Measure production performance

    Analyzes:
    - Bundle sizes (JS, CSS, chunks)
    - Lighthouse scores (if available)
    - Code patterns indicating performance issues
    - Memory leak indicators
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        claude_tool: Optional[ClaudeCodeTool] = None,
        bundle_thresholds: Optional[dict] = None,
        lighthouse_thresholds: Optional[dict] = None,
        enable_lighthouse: bool = True,
        enable_pattern_scan: bool = True,
    ):
        """
        Initialize PerformanceAgent.

        Args:
            event_bus: EventBus for pub/sub
            shared_state: SharedState for metrics
            working_dir: Project directory to analyze
            claude_tool: Optional Claude tool for AI analysis
            bundle_thresholds: Custom bundle size thresholds
            lighthouse_thresholds: Custom Lighthouse thresholds
            enable_lighthouse: Whether to run Lighthouse CI
            enable_pattern_scan: Whether to scan for anti-patterns
        """
        super().__init__(
            name="PerformanceAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.working_dir = Path(working_dir)
        self.claude_tool = claude_tool
        self.bundle_thresholds = bundle_thresholds or BUNDLE_SIZE_THRESHOLDS
        self.lighthouse_thresholds = lighthouse_thresholds or LIGHTHOUSE_THRESHOLDS
        self.enable_lighthouse = enable_lighthouse
        self.enable_pattern_scan = enable_pattern_scan

        self._last_analysis: Optional[datetime] = None
        self._issues_found: list[dict] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens for."""
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.E2E_TEST_PASSED,
            EventType.DEPLOY_SUCCEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Determine if agent should act on these events.

        Acts when:
        - Build succeeded (analyze bundle)
        - E2E tests passed (run Lighthouse if available)
        - Deploy succeeded (production performance check)
        """
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Rate limit: Don't analyze more than once per 60 seconds
            if self._last_analysis:
                elapsed = (datetime.now() - self._last_analysis).total_seconds()
                if elapsed < 60:
                    logger.debug(
                        "performance_analysis_skipped",
                        reason="rate_limited",
                        seconds_since_last=elapsed,
                    )
                    continue

            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Perform performance analysis.

        Uses autogen team if available, falls back to direct analysis.
        """
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> None:
        """Run performance analysis using autogen PerfOperator + PerfValidator team."""
        event = events[0] if events else None
        trigger_event = event.type.value if event else "unknown"

        self._last_analysis = datetime.now()
        self._issues_found = []

        await self.event_bus.publish(performance_analysis_started_event(
            source=self.name,
            working_dir=str(self.working_dir),
            trigger=trigger_event,
        ))

        try:
            task = self.build_task_prompt(events, extra_context=f"""
## Performance Analysis Task

Analyze the project at {self.working_dir} for performance issues:

1. Analyze bundle sizes (JS main < 250KB, CSS < 50KB, total < 500KB)
2. Run Lighthouse CI if available (performance > 70, accessibility > 80)
3. Scan source code for performance anti-patterns:
   - Full library imports (lodash, moment) instead of specific imports
   - useEffect without dependency array
   - Memory leak indicators (setInterval/addEventListener without cleanup)
   - Missing React.memo on expensive components
   - Inline functions/objects in JSX props

Trigger: {trigger_event}
""")

            team = self.create_team(
                operator_name="PerfOperator",
                operator_prompt="""You are a web performance optimization expert.

Your role is to analyze application performance:
- Analyze bundle sizes from dist/build output
- Run Lighthouse CI for Core Web Vitals
- Detect React performance anti-patterns (missing memo, inline functions)
- Check for memory leaks (setInterval, addEventListener without cleanup)
- Identify tree-shaking opportunities

Report each issue with: file, line, severity, description, and suggested fix.
When done, say TASK_COMPLETE.""",
                validator_name="PerfValidator",
                validator_prompt="""You are a performance review validator.

Review the performance analysis results and verify:
1. Bundle size thresholds are correctly applied
2. Anti-pattern detections are accurate (not false positives)
3. Suggested fixes are actionable and correct
4. All critical areas were analyzed (bundle, runtime, code patterns)

If the analysis is comprehensive, say TASK_COMPLETE.
If areas were missed, describe what needs additional analysis.""",
                tool_categories=["npm"],
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                await self.event_bus.publish(performance_benchmark_passed_event(
                    source=self.name,
                    total_issues=0, critical=0, high=0, medium=0, low=0,
                    issues=[],
                ))
                logger.info("performance_benchmarks_passed", mode="autogen")
            else:
                await self.event_bus.publish(performance_issue_detected_event(
                    source=self.name,
                    total_issues=0, critical=0, high=0, medium=0, low=0,
                    issues=[],
                ))
                logger.warning("performance_issues_detected", mode="autogen")

        except Exception as e:
            logger.error("performance_autogen_error", error=str(e))

    async def _act_legacy(self, events: list[Event]) -> None:
        """Run performance analysis using direct scanning (legacy)."""
        event = events[0] if events else None
        trigger_event = event.type.value if event else "unknown"

        self._last_analysis = datetime.now()
        self._issues_found = []

        logger.info(
            "performance_analysis_started",
            working_dir=str(self.working_dir),
            trigger_event=trigger_event,
        )

        await self.event_bus.publish(performance_analysis_started_event(
            source=self.name,
            working_dir=str(self.working_dir),
            trigger=trigger_event,
        ))

        bundle_issues = await self._analyze_bundle_sizes()
        self._issues_found.extend(bundle_issues)

        if self.enable_lighthouse and event.type == EventType.DEPLOY_SUCCEEDED:
            lighthouse_issues = await self._run_lighthouse()
            self._issues_found.extend(lighthouse_issues)

        if self.enable_pattern_scan:
            pattern_issues = await self._scan_antipatterns()
            self._issues_found.extend(pattern_issues)

        await self._publish_results()

    async def _analyze_bundle_sizes(self) -> list[dict]:
        """
        Analyze bundle sizes from build output.

        Returns:
            List of bundle size issues
        """
        issues = []

        # Check common build output directories
        build_dirs = [
            self.working_dir / "dist",
            self.working_dir / "build",
            self.working_dir / ".next",
            self.working_dir / "out",
        ]

        build_dir = None
        for dir_path in build_dirs:
            if dir_path.exists():
                build_dir = dir_path
                break

        if not build_dir:
            logger.debug("no_build_directory_found")
            return issues

        # Analyze JS files
        js_files = list(build_dir.rglob("*.js"))
        total_js_size = 0

        for js_file in js_files:
            size_kb = js_file.stat().st_size / 1024
            total_js_size += size_kb

            # Check individual chunk size
            if size_kb > self.bundle_thresholds["chunk_kb"]:
                issues.append({
                    "type": "bundle_size",
                    "severity": "medium",
                    "file": str(js_file.relative_to(self.working_dir)),
                    "size_kb": round(size_kb, 2),
                    "threshold_kb": self.bundle_thresholds["chunk_kb"],
                    "description": f"JS chunk exceeds {self.bundle_thresholds['chunk_kb']}KB threshold",
                })

        # Check main bundle size
        main_bundles = [f for f in js_files if "main" in f.name or "index" in f.name]
        for main_bundle in main_bundles:
            size_kb = main_bundle.stat().st_size / 1024
            if size_kb > self.bundle_thresholds["js_main_kb"]:
                issues.append({
                    "type": "bundle_size",
                    "severity": "high",
                    "file": str(main_bundle.relative_to(self.working_dir)),
                    "size_kb": round(size_kb, 2),
                    "threshold_kb": self.bundle_thresholds["js_main_kb"],
                    "description": f"Main JS bundle exceeds {self.bundle_thresholds['js_main_kb']}KB threshold",
                })

        # Analyze CSS files
        css_files = list(build_dir.rglob("*.css"))
        total_css_size = sum(f.stat().st_size / 1024 for f in css_files)

        if total_css_size > self.bundle_thresholds["css_main_kb"]:
            issues.append({
                "type": "bundle_size",
                "severity": "medium",
                "file": "css/*",
                "size_kb": round(total_css_size, 2),
                "threshold_kb": self.bundle_thresholds["css_main_kb"],
                "description": f"Total CSS exceeds {self.bundle_thresholds['css_main_kb']}KB threshold",
            })

        # Check total bundle size
        total_size = total_js_size + total_css_size
        if total_size > self.bundle_thresholds["total_kb"]:
            issues.append({
                "type": "bundle_size",
                "severity": "high",
                "file": "total",
                "size_kb": round(total_size, 2),
                "threshold_kb": self.bundle_thresholds["total_kb"],
                "description": f"Total bundle exceeds {self.bundle_thresholds['total_kb']}KB threshold",
            })

            # Publish bundle size warning
            await self.event_bus.publish(bundle_size_warning_event(
                source=self.name,
                total_size_kb=round(total_size, 2),
                js_size_kb=round(total_js_size, 2),
                css_size_kb=round(total_css_size, 2),
                threshold_kb=self.bundle_thresholds["total_kb"],
            ))

        logger.info(
            "bundle_analysis_complete",
            total_js_kb=round(total_js_size, 2),
            total_css_kb=round(total_css_size, 2),
            issues_found=len(issues),
        )

        return issues

    async def _run_lighthouse(self) -> list[dict]:
        """
        Run Lighthouse CI if available.

        Returns:
            List of Lighthouse score issues
        """
        issues = []

        # Check if lighthouse CLI is available
        try:
            result = await self.call_tool(
                "npm.npx", command="lighthouse", args="--version",
                cwd=str(self.working_dir),
            )
            if not result.get("success"):
                logger.debug("lighthouse_not_available")
                return issues
        except Exception:
            logger.debug("lighthouse_not_installed")
            return issues

        # Get the app URL (default to localhost:5173)
        app_url = "http://localhost:5173"

        try:
            # Run Lighthouse with JSON output
            lighthouse_args = (
                f"{app_url} --output=json --output-path=./lighthouse-report.json "
                f"--chrome-flags='--headless --no-sandbox' "
                f"--only-categories=performance,accessibility,best-practices,seo"
            )
            await self.call_tool(
                "npm.npx", command="lighthouse", args=lighthouse_args,
                cwd=str(self.working_dir),
            )

            # Parse results
            report_path = self.working_dir / "lighthouse-report.json"
            if report_path.exists():
                with open(report_path) as f:
                    report = json.load(f)

                categories = report.get("categories", {})

                for category, threshold in self.lighthouse_thresholds.items():
                    cat_data = categories.get(category, {})
                    score = (cat_data.get("score") or 0) * 100

                    if score < threshold:
                        issues.append({
                            "type": "lighthouse",
                            "severity": "high" if score < threshold - 20 else "medium",
                            "category": category,
                            "score": round(score),
                            "threshold": threshold,
                            "description": f"Lighthouse {category} score ({score:.0f}) below threshold ({threshold})",
                        })

                # Check for low performance specifically
                perf_score = (categories.get("performance", {}).get("score") or 0) * 100
                if perf_score < self.lighthouse_thresholds["performance"]:
                    await self.event_bus.publish(lighthouse_score_low_event(
                        source=self.name,
                        score=round(perf_score),
                        threshold=self.lighthouse_thresholds["performance"],
                        categories={k: round((v.get("score") or 0) * 100) for k, v in categories.items()},
                    ))

                logger.info(
                    "lighthouse_analysis_complete",
                    performance=round(perf_score),
                    issues_found=len(issues),
                )

        except Exception as e:
            logger.error("lighthouse_error", error=str(e))

        return issues

    async def _scan_antipatterns(self) -> list[dict]:
        """
        Scan source code for performance anti-patterns.

        Uses a hybrid approach:
        - Regex patterns for all files (fast, basic detection)
        - LLM semantic analysis for complex components (>100 lines)

        Returns:
            List of anti-pattern issues
        """
        import re
        issues = []
        llm_analyzed_count = 0

        # Source directories to scan
        src_dirs = [
            self.working_dir / "src",
            self.working_dir / "app",
            self.working_dir / "pages",
            self.working_dir / "components",
        ]

        files_to_scan = []
        for src_dir in src_dirs:
            if src_dir.exists():
                files_to_scan.extend(src_dir.rglob("*.ts"))
                files_to_scan.extend(src_dir.rglob("*.tsx"))
                files_to_scan.extend(src_dir.rglob("*.js"))
                files_to_scan.extend(src_dir.rglob("*.jsx"))

        for file_path in files_to_scan:
            try:
                content = file_path.read_text(encoding="utf-8")
                rel_path = str(file_path.relative_to(self.working_dir))
                line_count = content.count("\n")

                # For complex components, use LLM semantic analysis
                # Limit to 10 files to avoid excessive LLM calls
                if line_count > 100 and llm_analyzed_count < 10 and self.claude_tool:
                    try:
                        llm_result = await self.detect_performance_antipatterns_with_llm(
                            component_code=content,
                            file_path=rel_path,
                        )
                        llm_analyzed_count += 1

                        # Convert LLM issues to standard format
                        for issue in llm_result.get("issues", []):
                            issues.append({
                                "type": "antipattern",
                                "severity": issue.get("severity", "medium"),
                                "pattern": issue.get("pattern", "llm_detected"),
                                "file": rel_path,
                                "line": issue.get("line", 0),
                                "description": issue.get("description", ""),
                                "fix": issue.get("fix", ""),
                                "detection": llm_result.get("detection_method", "unknown"),
                            })

                        # Skip regex for this file - LLM already includes regex results
                        continue

                    except Exception as e:
                        logger.debug(
                            "llm_analysis_failed_fallback_to_regex",
                            file=rel_path,
                            error=str(e),
                        )
                        # Fall through to regex analysis

                # Standard regex-based detection
                for pattern_name, pattern_info in PERFORMANCE_ANTIPATTERNS.items():
                    matches = re.finditer(pattern_info["pattern"], content)

                    for match in matches:
                        # Find line number
                        line_num = content[:match.start()].count("\n") + 1

                        issues.append({
                            "type": "antipattern",
                            "severity": pattern_info["severity"],
                            "pattern": pattern_name,
                            "file": rel_path,
                            "line": line_num,
                            "description": pattern_info["description"],
                            "detection": "regex",
                        })

            except Exception as e:
                logger.debug("file_scan_error", file=str(file_path), error=str(e))

        logger.info(
            "antipattern_scan_complete",
            files_scanned=len(files_to_scan),
            issues_found=len(issues),
        )

        return issues

    # =========================================================================
    # Phase 8: LLM-Enhanced Performance Anti-Pattern Detection
    # =========================================================================

    async def detect_performance_antipatterns_with_llm(
        self,
        component_code: str,
        file_path: str = "unknown",
    ) -> dict:
        """
        Use LLM to detect React performance anti-patterns semantically.

        This method detects issues that regex can't catch:
        1. Missing useMemo/useCallback for expensive computations
        2. Inline objects/functions causing unnecessary re-renders
        3. N+1 API calls in loops
        4. Large component bundles that should code-split
        5. Context overuse causing cascading re-renders
        6. Prop drilling that could use context
        7. State updates in render causing infinite loops

        Args:
            component_code: Component source code to analyze
            file_path: Path for context in results

        Returns:
            Dict with issues, severity, and suggested fixes
        """
        import re as regex_module

        # First, run quick regex-based checks
        regex_issues = []
        for pattern_name, pattern_info in PERFORMANCE_ANTIPATTERNS.items():
            matches = list(regex_module.finditer(pattern_info["pattern"], component_code))
            for match in matches:
                line_num = component_code[:match.start()].count("\n") + 1
                regex_issues.append({
                    "pattern": pattern_name,
                    "line": line_num,
                    "severity": pattern_info["severity"],
                    "description": pattern_info["description"],
                })

        # For small files or if regex found many issues, skip LLM
        if len(component_code) < 500 or len(regex_issues) > 10:
            return {
                "issues": regex_issues,
                "detection_method": "regex_only",
                "file_path": file_path,
                "confidence": 0.7 if regex_issues else 0.5,
                "llm_skipped": True,
                "skip_reason": "file_too_small" if len(component_code) < 500 else "many_regex_issues",
            }

        # Use LLM for semantic analysis
        try:
            prompt = f"""Analyze this React/TypeScript code for performance anti-patterns:

FILE: {file_path}
CODE:
{component_code[:3500]}

Check for these performance issues:

1. **Missing Memoization**
   - Expensive calculations in render without useMemo
   - Functions recreated every render without useCallback
   - Pure components without React.memo

2. **Re-render Triggers**
   - Inline object literals in JSX props (style={{{{}}}} )
   - Arrow functions in JSX props (onClick={{() => ...)
   - Creating arrays/objects inside render

3. **State Management Issues**
   - State updates during render (causes infinite loop)
   - Unnecessary state (can be derived)
   - State too high in tree (causes cascade re-renders)

4. **Data Fetching Problems**
   - API calls in loops (N+1 problem)
   - Missing request deduplication
   - No loading/error states

5. **Bundle Size Issues**
   - Large imports that should be lazy loaded
   - Unused imports
   - Heavy dependencies in critical path

6. **Context Overuse**
   - Context changes causing wide re-renders
   - Single context with unrelated data

IMPORTANT: Only report ACTUAL issues found in the code. Don't guess or assume.

Respond with JSON:
```json
{{
  "issues": [
    {{
      "line": 42,
      "pattern": "inline_function",
      "severity": "medium",
      "description": "Arrow function in onClick recreates on every render",
      "fix": "Extract to useCallback: const handleClick = useCallback(() => ..., [])"
    }}
  ],
  "overall_severity": "low|medium|high",
  "confidence": 0.0-1.0,
  "summary": "Brief summary of main issues"
}}
```
"""

            if self.claude_tool:
                result = await self.claude_tool.execute(
                    prompt=prompt,
                    context="Performance anti-pattern analysis",
                    agent_type="performance_analyzer",
                )

                # Parse JSON response
                json_match = regex_module.search(
                    r'```json\s*(.*?)\s*```',
                    result.output or "",
                    regex_module.DOTALL
                )

                if json_match:
                    import json
                    analysis = json.loads(json_match.group(1))

                    # Merge regex and LLM issues
                    all_issues = regex_issues + analysis.get("issues", [])

                    # Deduplicate by line number
                    seen_lines = set()
                    unique_issues = []
                    for issue in all_issues:
                        line = issue.get("line", 0)
                        if line not in seen_lines:
                            seen_lines.add(line)
                            unique_issues.append(issue)

                    return {
                        "issues": unique_issues,
                        "detection_method": "llm+regex",
                        "file_path": file_path,
                        "overall_severity": analysis.get("overall_severity", "medium"),
                        "confidence": analysis.get("confidence", 0.8),
                        "summary": analysis.get("summary", ""),
                        "regex_count": len(regex_issues),
                        "llm_count": len(analysis.get("issues", [])),
                    }

            # No Claude tool available
            return self._fallback_antipattern_detection(component_code, file_path, regex_issues)

        except Exception as e:
            logger.warning(
                "llm_performance_detection_failed",
                file=file_path,
                error=str(e),
            )
            return self._fallback_antipattern_detection(component_code, file_path, regex_issues)

    def _fallback_antipattern_detection(
        self,
        component_code: str,
        file_path: str,
        regex_issues: list[dict],
    ) -> dict:
        """
        Fallback detection when LLM is unavailable.

        Uses enhanced heuristics beyond basic regex patterns.

        Args:
            component_code: Source code
            file_path: File path for context
            regex_issues: Issues already found by regex

        Returns:
            Dict with issues and metadata
        """
        import re as regex_module

        additional_issues = []

        # Heuristic: Detect inline arrow functions in JSX
        jsx_arrow_pattern = r'on\w+\s*=\s*\{\s*\(\s*[^)]*\)\s*=>'
        for match in regex_module.finditer(jsx_arrow_pattern, component_code):
            line_num = component_code[:match.start()].count("\n") + 1
            additional_issues.append({
                "pattern": "jsx_inline_arrow",
                "line": line_num,
                "severity": "medium",
                "description": "Inline arrow function in JSX event handler - recreates on every render",
                "fix": "Extract to useCallback or define outside component",
            })

        # Heuristic: Detect inline style objects
        inline_style_pattern = r'style\s*=\s*\{\s*\{'
        for match in regex_module.finditer(inline_style_pattern, component_code):
            line_num = component_code[:match.start()].count("\n") + 1
            additional_issues.append({
                "pattern": "inline_style_object",
                "line": line_num,
                "severity": "low",
                "description": "Inline style object creates new reference every render",
                "fix": "Move style object outside component or use useMemo",
            })

        # Heuristic: Detect fetch/axios in component body (not in useEffect)
        if "useEffect" not in component_code:
            fetch_pattern = r'(fetch|axios|api\.)\s*\('
            for match in regex_module.finditer(fetch_pattern, component_code):
                line_num = component_code[:match.start()].count("\n") + 1
                additional_issues.append({
                    "pattern": "fetch_in_render",
                    "line": line_num,
                    "severity": "high",
                    "description": "API call outside useEffect - may cause infinite requests",
                    "fix": "Move API call inside useEffect with proper dependencies",
                })

        # Heuristic: Large useState with object
        large_state_pattern = r'useState\s*\(\s*\{[^}]{300,}'
        for match in regex_module.finditer(large_state_pattern, component_code, regex_module.DOTALL):
            line_num = component_code[:match.start()].count("\n") + 1
            additional_issues.append({
                "pattern": "large_initial_state",
                "line": line_num,
                "severity": "medium",
                "description": "Large state object - consider useReducer or splitting",
                "fix": "Split into multiple useState calls or use useReducer",
            })

        # Heuristic: Detect .map() with key as index
        map_index_key = r'\.map\s*\(\s*\([^,)]+,\s*(\w+)\s*\)[^}]*key\s*=\s*\{\s*\1\s*\}'
        for match in regex_module.finditer(map_index_key, component_code):
            line_num = component_code[:match.start()].count("\n") + 1
            additional_issues.append({
                "pattern": "map_index_as_key",
                "line": line_num,
                "severity": "medium",
                "description": "Using array index as key - causes issues with reordering",
                "fix": "Use a unique identifier from the data as key",
            })

        # Combine all issues
        all_issues = regex_issues + additional_issues

        # Determine overall severity
        severities = [i.get("severity", "low") for i in all_issues]
        if "high" in severities:
            overall = "high"
        elif "medium" in severities:
            overall = "medium"
        else:
            overall = "low"

        return {
            "issues": all_issues,
            "detection_method": "regex_fallback",
            "file_path": file_path,
            "overall_severity": overall if all_issues else None,
            "confidence": 0.6,
            "regex_count": len(regex_issues),
            "heuristic_count": len(additional_issues),
        }

    async def analyze_component_performance(
        self,
        file_path: Path,
    ) -> dict:
        """
        Analyze a single component file for performance issues.

        Combines regex patterns with LLM semantic analysis for
        comprehensive performance anti-pattern detection.

        Args:
            file_path: Path to component file

        Returns:
            Dict with issues, severity, and fixes
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            rel_path = str(file_path.relative_to(self.working_dir))
        except Exception as e:
            logger.warning(
                "component_read_failed",
                file=str(file_path),
                error=str(e),
            )
            return {"issues": [], "error": str(e)}

        # Use LLM for semantic analysis on larger components
        if len(content) > 100:
            return await self.detect_performance_antipatterns_with_llm(
                component_code=content,
                file_path=rel_path,
            )
        else:
            # Small files - regex only
            return self._fallback_antipattern_detection(content, rel_path, [])

    async def _publish_results(self) -> None:
        """Publish analysis results based on issues found."""

        # Categorize issues by severity
        critical_issues = [i for i in self._issues_found if i["severity"] == "critical"]
        high_issues = [i for i in self._issues_found if i["severity"] == "high"]
        medium_issues = [i for i in self._issues_found if i["severity"] == "medium"]
        low_issues = [i for i in self._issues_found if i["severity"] == "low"]

        result_data = {
            "total_issues": len(self._issues_found),
            "critical": len(critical_issues),
            "high": len(high_issues),
            "medium": len(medium_issues),
            "low": len(low_issues),
            "issues": self._issues_found,
        }

        if critical_issues or high_issues:
            # Performance issues detected
            await self.event_bus.publish(performance_issue_detected_event(
                source=self.name,
                total_issues=len(self._issues_found),
                critical=len(critical_issues),
                high=len(high_issues),
                medium=len(medium_issues),
                low=len(low_issues),
                issues=self._issues_found,
            ))

            logger.warning(
                "performance_issues_detected",
                critical=len(critical_issues),
                high=len(high_issues),
            )
        else:
            # All benchmarks passed
            await self.event_bus.publish(performance_benchmark_passed_event(
                source=self.name,
                total_issues=len(self._issues_found),
                critical=len(critical_issues),
                high=len(high_issues),
                medium=len(medium_issues),
                low=len(low_issues),
                issues=self._issues_found,
            ))

            logger.info("performance_benchmarks_passed")

        # Update shared state with performance metrics
        await self.shared_state.set("performance_issues", len(self._issues_found))
        await self.shared_state.set("performance_critical", len(critical_issues))
        await self.shared_state.set("performance_high", len(high_issues))

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Remove temporary Lighthouse report if exists
        report_path = self.working_dir / "lighthouse-report.json"
        if report_path.exists():
            try:
                report_path.unlink()
            except Exception:
                pass

        logger.info("performance_agent_cleanup_complete")
