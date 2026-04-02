"""
Phase 29: Task Enrichment Pipeline.

Enriches epic tasks with context from all available project documentation
BEFORE they are sent to Claude CLI for execution. This bridges the gap
between rich input data (OpenAPI, Data Dictionary, Diagrams, Self-Critique,
User Stories) and the task definitions that drive code generation.

Uses DocumentationLoader's DocumentationSpec as data source, plus direct
file reads for artifacts not covered by DocumentationLoader (e.g. .mmd
diagram files, user_stories.json, openapi_spec.yaml schemas).

Entry point: TaskEnricher.enrich_all(task_list) called from
EpicOrchestrator.run_epic() after loading tasks.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class EnrichmentStats:
    """Statistics from the enrichment run."""
    total_tasks: int = 0
    tasks_with_requirements: int = 0
    tasks_with_user_stories: int = 0
    tasks_with_diagrams: int = 0
    tasks_with_warnings: int = 0
    tasks_with_dtos: int = 0
    tasks_with_success_criteria: int = 0
    tasks_with_test_scenarios: int = 0
    tasks_with_component_specs: int = 0
    tasks_with_screen_specs: int = 0
    tasks_with_accessibility: int = 0
    tasks_with_routes: int = 0
    tasks_with_design_tokens: int = 0


class TaskEnricher:
    """
    Enriches tasks with context from project documentation.

    Runs ONCE before task execution. Builds cross-reference indices
    from documentation artifacts and fills in missing fields on each task:
    - related_requirements (from Data Dictionary source_requirements)
    - related_user_stories (from user_stories.json linked_requirement)
    - enrichment_context.diagrams (from diagrams/*.mmd files)
    - enrichment_context.known_gaps (from self_critique_report.json)
    - enrichment_context.related_dtos (from openapi_spec.yaml schemas)
    - success_criteria (from task type + user story acceptance criteria)
    """

    def __init__(self, project_path: Path, doc_spec: Any = None, task_mapping: Any = None):
        self.project_path = Path(project_path)
        self.doc_spec = doc_spec
        self.stats = EnrichmentStats()

        # Phase 30: LLM-assisted task mapping (pre-computed)
        # If provided, used as PRIMARY source for requirement/story/screen linkage
        self._task_mapping = task_mapping  # TaskMappingResult or None

        # Cross-reference indices (built once)
        self._entity_to_reqs: Dict[str, List[str]] = {}
        self._req_to_user_stories: Dict[str, List[Dict]] = {}
        self._req_to_diagrams: Dict[str, List[Dict]] = {}
        self._req_to_critique: Dict[str, List[Dict]] = {}
        self._openapi_schemas: Dict[str, Dict] = {}
        self._tasks_by_id: Dict[str, Any] = {}

        # Phase 29b: Additional indices
        self._us_to_gherkin: Dict[str, str] = {}          # US-ID -> Gherkin feature block
        self._comp_specs: Dict[str, Dict] = {}             # COMP-ID -> component spec
        self._screen_specs: Dict[str, Dict] = {}           # SCREEN-ID -> screen spec
        self._us_to_screen: Dict[str, str] = {}            # US-ID -> SCREEN-ID
        self._route_map: List[Dict] = []                   # [{route, name, content}]
        self._accessibility_rules: List[str] = []          # WCAG checklist items
        self._design_tokens: Dict[str, Any] = {}           # Phase 29c: design system tokens

        self._build_indices()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INDEX BUILDING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_indices(self):
        """Build all cross-reference indices from documentation."""
        self._build_entity_requirement_index()
        self._build_requirement_user_story_index()
        self._build_requirement_diagram_index()
        self._build_requirement_critique_index()
        self._build_openapi_schema_index()
        # Phase 29b: Additional indices
        self._build_gherkin_index()
        self._build_component_spec_index()
        self._build_screen_spec_index()
        self._build_route_index()
        self._build_accessibility_rules()
        # Phase 29c: Design tokens
        self._build_design_tokens_index()

    def _build_entity_requirement_index(self):
        """Entity name → requirement IDs (from data_dictionary.md Source Requirements)."""
        if self.doc_spec and self.doc_spec.entities:
            for entity in self.doc_spec.entities:
                self._entity_to_reqs[entity.name.lower()] = list(entity.source_requirements)
            logger.debug("entity_req_index_built", count=len(self._entity_to_reqs))
            return

        # Fallback: parse data_dictionary.md directly
        data_dict_path = self.project_path / "data" / "data_dictionary.md"
        if not data_dict_path.exists():
            return

        try:
            content = data_dict_path.read_text(encoding="utf-8")
            pattern = re.compile(
                r"### (\w+)\n\n.+?\n\n\*Source Requirements:\*\s*(.+?)(?:\n\n|\n\|)",
                re.DOTALL,
            )
            for match in pattern.finditer(content):
                entity_name = match.group(1).lower()
                reqs = [r.strip() for r in match.group(2).split(",")]
                self._entity_to_reqs[entity_name] = reqs
            logger.debug("entity_req_index_built_fallback", count=len(self._entity_to_reqs))
        except Exception as e:
            logger.warning("entity_req_index_failed", error=str(e))

    def _build_requirement_user_story_index(self):
        """Requirement ID -> user story dicts (from user_stories.json)."""
        # Prefer JSON source (richer data than markdown)
        us_json_path = self.project_path / "user_stories.json"
        if us_json_path.exists():
            try:
                raw = json.loads(us_json_path.read_text(encoding="utf-8"))
                # Handle both formats: bare list or {"user_stories": [...]}
                stories = raw if isinstance(raw, list) else raw.get("user_stories", [])

                for story in stories:
                    # Phase 30: Support multiple formats for requirement links
                    req_ids = []
                    # Format A: linked_requirement_ids (array) — new format
                    linked_ids = story.get("linked_requirement_ids", [])
                    if isinstance(linked_ids, list):
                        req_ids.extend(linked_ids)
                    # Format B: linked_requirement (string) — old format
                    linked_single = story.get("linked_requirement", "")
                    if linked_single:
                        req_ids.append(linked_single)
                    # Format C: parent_requirement_id (string)
                    parent_req = story.get("parent_requirement_id", "")
                    if parent_req and parent_req not in req_ids:
                        req_ids.append(parent_req)

                    # Phase 30: Support both BDD field naming conventions
                    story_dict = {
                        "id": story.get("id", ""),
                        "title": story.get("title", ""),
                        "priority": story.get("priority", ""),
                        "description": story.get("description", ""),
                        # Old format fields
                        "as_a": story.get("as_a", "") or story.get("persona", ""),
                        "i_want": story.get("i_want", "") or story.get("action", ""),
                        "so_that": story.get("so_that", "") or story.get("benefit", ""),
                    }

                    for req_id in req_ids:
                        if req_id:
                            self._req_to_user_stories.setdefault(req_id, []).append(story_dict)

                logger.debug("user_story_index_built", count=len(self._req_to_user_stories))
                return
            except Exception as e:
                logger.warning("user_story_json_parse_failed", error=str(e))

        # Fallback: use DocumentationSpec user stories
        if self.doc_spec and self.doc_spec.user_stories:
            for story in self.doc_spec.user_stories:
                # DocumentationSpec UserStory doesn't have linked_requirement directly
                # but we can infer from epic->requirements mapping
                pass

    def _build_requirement_diagram_index(self):
        """Requirement ID → diagram dicts (from diagrams/*.mmd filenames)."""
        diagrams_dir = self.project_path / "diagrams"
        if not diagrams_dir.exists():
            return

        # Diagram naming pattern: WA-AUTH-001_sequence.mmd
        req_pattern = re.compile(r"^(WA-[A-Z]+-\d+)_(\w+)\.mmd$")

        for mmd_file in diagrams_dir.glob("*.mmd"):
            match = req_pattern.match(mmd_file.name)
            if not match:
                continue

            req_id = match.group(1)  # e.g. "WA-AUTH-001"
            diagram_type = match.group(2)  # e.g. "sequence"

            try:
                content = mmd_file.read_text(encoding="utf-8")
                # Truncate large diagrams to save tokens
                truncated = content[:600] if len(content) > 600 else content

                self._req_to_diagrams.setdefault(req_id, []).append({
                    "type": diagram_type,
                    "content": truncated,
                    "file": mmd_file.name,
                })
            except Exception:
                pass

        total_diagrams = sum(len(v) for v in self._req_to_diagrams.values())
        logger.debug("diagram_index_built", requirements=len(self._req_to_diagrams), diagrams=total_diagrams)

    def _build_requirement_critique_index(self):
        """Requirement ID → self-critique issue dicts."""
        critique = None

        # From DocumentationSpec
        if self.doc_spec and self.doc_spec.quality_report:
            critique = self.doc_spec.quality_report
        else:
            # Fallback: read directly
            critique_path = self.project_path / "quality" / "self_critique_report.json"
            if critique_path.exists():
                try:
                    critique = json.loads(critique_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

        if not critique:
            return

        for issue in critique.get("issues", []):
            for artifact in issue.get("affected_artifacts", []):
                self._req_to_critique.setdefault(artifact, []).append({
                    "id": issue.get("id", ""),
                    "severity": issue.get("severity", ""),
                    "title": issue.get("title", ""),
                    "suggestion": issue.get("suggestion", ""),
                })

        logger.debug("critique_index_built", requirements=len(self._req_to_critique))

    def _build_openapi_schema_index(self):
        """Load OpenAPI component schemas for DTO cross-referencing."""
        spec_path = self.project_path / "api" / "openapi_spec.yaml"
        if not spec_path.exists():
            return

        try:
            import yaml
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            self._openapi_schemas = spec.get("components", {}).get("schemas", {})
            logger.debug("openapi_schema_index_built", count=len(self._openapi_schemas))
        except ImportError:
            logger.warning("yaml_not_installed_skipping_openapi_schemas")
        except Exception as e:
            logger.warning("openapi_schema_parse_failed", error=str(e))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PHASE 29b: ADDITIONAL INDEX BUILDERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_gherkin_index(self):
        """User Story ID -> Gherkin feature block.

        Phase 30: Supports both formats:
        A) Individual .feature files: testing/us_001.feature (preferred)
        B) Embedded in test_documentation.md (legacy)
        """
        # Format A: Individual .feature files (Phase 30)
        for test_dir in ["testing", "tests"]:
            feature_dir = self.project_path / test_dir
            if not feature_dir.exists():
                continue
            for feature_file in sorted(feature_dir.glob("us_*.feature")):
                # Extract US-ID from filename: us_001.feature -> US-001
                stem = feature_file.stem  # "us_001"
                match = re.match(r"us_(\d+)", stem)
                if not match:
                    continue
                us_id = f"US-{match.group(1).lstrip('0') or '0'}"
                # Normalize: US-1 -> US-001 etc. is NOT needed
                # Actually keep the original numbering
                us_num = int(match.group(1))
                us_id = f"US-{us_num:03d}"

                try:
                    content = feature_file.read_text(encoding="utf-8")
                    # Truncate at 1500 chars to save tokens in index
                    if len(content) > 1500:
                        content = content[:1480] + "\n  # ... (truncated)"
                    self._us_to_gherkin[us_id] = content
                except Exception:
                    pass

        if self._us_to_gherkin:
            logger.debug("gherkin_index_built_from_features", count=len(self._us_to_gherkin))
            return

        # Format B: Embedded in test_documentation.md (legacy)
        test_doc = self.project_path / "testing" / "test_documentation.md"
        if not test_doc.exists():
            return

        try:
            content = test_doc.read_text(encoding="utf-8")
            # Split by ### Feature headers, each has *User Story:* US-XXX
            pattern = re.compile(
                r"### .+?\n\n\*User Story:\*\s*(US-\d+)\n\n```gherkin\n(.+?)```",
                re.DOTALL,
            )
            for match in pattern.finditer(content):
                us_id = match.group(1)
                gherkin_block = match.group(2).strip()
                self._us_to_gherkin[us_id] = gherkin_block

            logger.debug("gherkin_index_built_from_doc", count=len(self._us_to_gherkin))
        except Exception as e:
            logger.warning("gherkin_index_failed", error=str(e))

    def _build_component_spec_index(self):
        """COMP-ID → component spec dict (from ui_design/components.md)."""
        comp_path = self.project_path / "ui_design" / "components.md"
        if not comp_path.exists():
            return

        try:
            content = comp_path.read_text(encoding="utf-8")
            # Split by ## ComponentName sections
            sections = re.split(r"\n---\n", content)
            for section in sections:
                id_match = re.search(r"\*\*ID:\*\*\s*`(COMP-\d+)`", section)
                if not id_match:
                    continue
                comp_id = id_match.group(1)

                # Extract component name from ## header
                name_match = re.search(r"^## (\w+)", section, re.MULTILINE)
                comp_name = name_match.group(1) if name_match else comp_id

                # Extract props table
                props = []
                props_match = re.search(
                    r"### Props\n\n\|.+?\|.+?\|\n\|[-|]+\|\n(.+?)(?:\n\n|\n###)",
                    section, re.DOTALL,
                )
                if props_match:
                    for line in props_match.group(1).strip().split("\n"):
                        cells = [c.strip().strip("`") for c in line.split("|") if c.strip()]
                        if len(cells) >= 2:
                            props.append({"name": cells[0], "type": cells[1]})

                # Extract variants
                variants = []
                var_match = re.search(r"### Variants\n\n(.+?)(?:\n\n###|\n---)", section, re.DOTALL)
                if var_match:
                    variants = [v.strip().strip("`").strip("- ") for v in var_match.group(1).strip().split("\n")]
                    variants = [v for v in variants if v]

                # Extract accessibility
                accessibility = {}
                acc_match = re.search(r"### Accessibility\n\n(.+?)(?:\n\n###|\n---|\n```|$)", section, re.DOTALL)
                if acc_match:
                    for line in acc_match.group(1).strip().split("\n"):
                        kv = re.match(r"- \*\*(.+?):\*\*\s*(.+)", line)
                        if kv:
                            accessibility[kv.group(1)] = kv.group(2).strip()

                self._comp_specs[comp_id] = {
                    "id": comp_id,
                    "name": comp_name,
                    "props": props[:10],
                    "variants": variants[:6],
                    "accessibility": accessibility,
                }

            logger.debug("component_spec_index_built", count=len(self._comp_specs))
        except Exception as e:
            logger.warning("component_spec_index_failed", error=str(e))

    def _build_screen_spec_index(self):
        """SCREEN-ID → screen spec dict (from ui_design/screens/screen-*.md)."""
        screens_dir = self.project_path / "ui_design" / "screens"
        if not screens_dir.exists():
            return

        try:
            for screen_file in screens_dir.glob("screen-*.md"):
                content = screen_file.read_text(encoding="utf-8")

                id_match = re.search(r"\*\*ID:\*\*\s*`(SCREEN-\d+)`", content)
                if not id_match:
                    continue
                screen_id = id_match.group(1)

                # Extract route
                route_match = re.search(r"\*\*Route:\*\*\s*`(.+?)`", content)
                route = route_match.group(1) if route_match else ""

                # Extract title from # header
                title_match = re.search(r"^# (.+)", content, re.MULTILINE)
                title = title_match.group(1) if title_match else ""

                # Extract component IDs
                components = re.findall(r"`(COMP-\d+)`", content)
                # Deduplicate while preserving order
                seen: Set[str] = set()
                unique_comps = []
                for c in components:
                    if c not in seen:
                        seen.add(c)
                        unique_comps.append(c)

                # Extract API endpoints from Data Requirements
                api_endpoints = re.findall(r"`((?:GET|POST|PUT|PATCH|DELETE) /api/.+?)`", content)

                # Extract related user story
                us_match = re.search(r"## Related User Story\n\n`(US-\d+)`", content)
                user_story = us_match.group(1) if us_match else ""

                self._screen_specs[screen_id] = {
                    "id": screen_id,
                    "title": title,
                    "route": route,
                    "components": unique_comps,
                    "api_endpoints": api_endpoints,
                    "user_story": user_story,
                }

                # Also build US → Screen reverse index
                if user_story:
                    self._us_to_screen[user_story] = screen_id

            logger.debug("screen_spec_index_built", count=len(self._screen_specs))
        except Exception as e:
            logger.warning("screen_spec_index_failed", error=str(e))

    def _build_route_index(self):
        """Route hierarchy from ux_design/information_architecture.md."""
        ia_path = self.project_path / "ux_design" / "information_architecture.md"
        if not ia_path.exists():
            return

        try:
            content = ia_path.read_text(encoding="utf-8")
            # Pattern: - **Name** (`/path`)  \n    - Content: keywords
            pattern = re.compile(
                r"- \*\*(.+?)\*\*\s*\(`(.+?)`\)\s*\n\s*- Content:\s*(.+)",
            )
            for match in pattern.finditer(content):
                self._route_map.append({
                    "name": match.group(1),
                    "route": match.group(2),
                    "content": match.group(3).strip(),
                })

            logger.debug("route_index_built", count=len(self._route_map))
        except Exception as e:
            logger.warning("route_index_failed", error=str(e))

    def _build_accessibility_rules(self):
        """WCAG checklist items from ux_design/accessibility_checklist.md."""
        a11y_path = self.project_path / "ux_design" / "accessibility_checklist.md"
        if not a11y_path.exists():
            return

        try:
            content = a11y_path.read_text(encoding="utf-8")
            # Extract all checklist items: - [ ] or - [x]
            for line in content.split("\n"):
                match = re.match(r"- \[[ x]\] (.+)", line.strip())
                if match:
                    self._accessibility_rules.append(match.group(1))

            logger.debug("accessibility_rules_built", count=len(self._accessibility_rules))
        except Exception as e:
            logger.warning("accessibility_rules_failed", error=str(e))

    def _build_design_tokens_index(self):
        """Design tokens from ui_design/design_tokens.json (Phase 29c)."""
        tokens_path = self.project_path / "ui_design" / "design_tokens.json"
        if not tokens_path.exists():
            return

        try:
            raw = json.loads(tokens_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return

            # Compact representation: only keep the most useful sections
            tokens: Dict[str, Any] = {}

            # Colors — flatten to key: value
            colors = raw.get("colors", {})
            if colors and isinstance(colors, dict):
                tokens["colors"] = {k: v for k, v in list(colors.items())[:12]}

            # Typography — flatten to name: "size/weight"
            typo = raw.get("typography", {})
            if typo and isinstance(typo, dict):
                font_family = typo.get("font-family", {})
                if font_family:
                    tokens["font_family"] = font_family.get("base", "")
                typo_entries = {}
                for key, val in typo.items():
                    if key == "font-family":
                        continue
                    if isinstance(val, dict):
                        size = val.get("size", "")
                        weight = val.get("weight", "")
                        if size:
                            typo_entries[key] = f"{size}/{weight}" if weight else size
                if typo_entries:
                    tokens["typography"] = typo_entries

            # Spacing — keep as-is (small)
            spacing = raw.get("spacing", {})
            if spacing and isinstance(spacing, dict):
                tokens["spacing"] = dict(list(spacing.items())[:8])

            # Breakpoints — keep as-is (small)
            breakpoints = raw.get("breakpoints", {})
            if breakpoints and isinstance(breakpoints, dict):
                tokens["breakpoints"] = dict(list(breakpoints.items())[:6])

            # Border radius — compact
            border_radius = raw.get("border_radius", {})
            if border_radius and isinstance(border_radius, dict):
                tokens["border_radius"] = dict(list(border_radius.items())[:6])

            if tokens:
                self._design_tokens = tokens
                logger.debug("design_tokens_index_built", sections=list(tokens.keys()))
        except Exception as e:
            logger.warning("design_tokens_index_failed", error=str(e))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MAIN ENTRY POINT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def enrich_all(self, task_list: Any) -> Any:
        """
        Enrich all tasks with documentation context.

        Modifies tasks in-place, filling related_requirements,
        related_user_stories, enrichment_context, and success_criteria.

        Returns the same task_list (modified in-place).
        """
        # Build task lookup for cross-referencing (e.g. test→tested module)
        self._tasks_by_id = {t.id: t for t in task_list.tasks}
        self.stats.total_tasks = len(task_list.tasks)

        enriched_count = 0
        for task in task_list.tasks:
            changes = self._enrich_task(task)
            if changes > 0:
                enriched_count += 1

        logger.info(
            "task_enrichment_complete",
            total=self.stats.total_tasks,
            enriched=enriched_count,
            with_requirements=self.stats.tasks_with_requirements,
            with_user_stories=self.stats.tasks_with_user_stories,
            with_diagrams=self.stats.tasks_with_diagrams,
            with_warnings=self.stats.tasks_with_warnings,
            with_dtos=self.stats.tasks_with_dtos,
            with_success_criteria=self.stats.tasks_with_success_criteria,
            with_test_scenarios=self.stats.tasks_with_test_scenarios,
            with_component_specs=self.stats.tasks_with_component_specs,
            with_screen_specs=self.stats.tasks_with_screen_specs,
            with_accessibility=self.stats.tasks_with_accessibility,
            with_routes=self.stats.tasks_with_routes,
            with_design_tokens=self.stats.tasks_with_design_tokens,
        )

        # Save enriched version
        self._save_enriched_tasks(task_list)

        return task_list

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PER-TASK ENRICHMENT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _enrich_task(self, task: Any) -> int:
        """Enrich a single task. Returns number of fields changed."""
        changes = 0

        # Phase 30: Apply LLM task mapping FIRST (primary source)
        mapping = None
        if self._task_mapping and hasattr(self._task_mapping, 'mappings'):
            mapping = self._task_mapping.mappings.get(task.id)

        # Effective type: use LLM-inferred type if available, else task.type
        effective_type = task.type
        if mapping and mapping.inferred_type:
            effective_type = mapping.inferred_type
            # Store inferred type in enrichment context for downstream use
            if task.enrichment_context is None:
                task.enrichment_context = {}
            task.enrichment_context["inferred_type"] = mapping.inferred_type

        # Step 1: Fill related_requirements
        if not task.related_requirements:
            # Phase 30: Use LLM mapping as primary source
            if mapping and mapping.requirement_ids:
                task.related_requirements = mapping.requirement_ids
                self.stats.tasks_with_requirements += 1
                changes += 1
            else:
                # Fallback: regex-based inference
                reqs = self._infer_requirements(task)
                if reqs:
                    task.related_requirements = reqs
                    self.stats.tasks_with_requirements += 1
                    changes += 1

        # Step 2: Fill related_user_stories
        if not task.related_user_stories:
            # Phase 30: Use LLM mapping as primary source
            if mapping and mapping.user_story_ids:
                task.related_user_stories = mapping.user_story_ids
                self.stats.tasks_with_user_stories += 1
                changes += 1
            else:
                # Fallback: requirement -> user story chain
                stories = self._infer_user_stories(task)
                if stories:
                    task.related_user_stories = stories
                    self.stats.tasks_with_user_stories += 1
                    changes += 1

        # Initialize enrichment_context dict
        if task.enrichment_context is None:
            task.enrichment_context = {}

        # Step 3: Inject relevant diagrams
        diagrams = self._get_relevant_diagrams(task, effective_type=effective_type)
        if diagrams:
            task.enrichment_context["diagrams"] = diagrams
            self.stats.tasks_with_diagrams += 1
            changes += 1

        # Step 4: Inject self-critique warnings
        warnings = self._get_critique_warnings(task)
        if warnings:
            task.enrichment_context["known_gaps"] = warnings
            self.stats.tasks_with_warnings += 1
            changes += 1

        # Step 5: Cross-reference OpenAPI DTOs for schema tasks
        if effective_type.startswith("schema_"):
            dtos = self._get_related_dtos(task)
            if dtos:
                task.enrichment_context["related_dtos"] = dtos
                self.stats.tasks_with_dtos += 1
                changes += 1

        # Step 5b: Store user story details in enrichment_context (for ContextInjector)
        story_details = self._get_user_story_details(task)
        if story_details:
            task.enrichment_context["user_story_details"] = story_details

        # Step 7: Gherkin test scenarios for test_* tasks
        if effective_type.startswith("test_"):
            scenarios = self._get_gherkin_scenarios(task, mapping=mapping)
            if scenarios:
                task.enrichment_context["test_scenarios"] = scenarios
                self.stats.tasks_with_test_scenarios += 1
                changes += 1

        # Step 8: Component specs for fe_component tasks
        if effective_type == "fe_component":
            comp_spec = self._get_component_spec(task, mapping=mapping)
            if comp_spec:
                task.enrichment_context["component_spec"] = comp_spec
                self.stats.tasks_with_component_specs += 1
                changes += 1

        # Step 9: Screen spec for fe_page tasks
        if effective_type == "fe_page":
            screen_spec = self._get_screen_spec(task, mapping=mapping)
            if screen_spec:
                task.enrichment_context["screen_spec"] = screen_spec
                self.stats.tasks_with_screen_specs += 1
                changes += 1

        # Step 10: Accessibility rules for all fe_* tasks
        if (effective_type.startswith("fe_") or task.type.startswith("fe_")) and self._accessibility_rules:
            task.enrichment_context["accessibility_rules"] = self._accessibility_rules[:8]
            self.stats.tasks_with_accessibility += 1
            changes += 1

        # Step 11: Related routes for fe_page tasks
        if (effective_type == "fe_page" or task.type == "fe_page") and self._route_map:
            routes = self._get_related_routes(task)
            if routes:
                task.enrichment_context["routes"] = routes
                self.stats.tasks_with_routes += 1
                changes += 1

        # Step 12: Design tokens for all fe_* tasks (Phase 29c)
        if (effective_type.startswith("fe_") or task.type.startswith("fe_")) and self._design_tokens:
            task.enrichment_context["design_tokens"] = self._design_tokens
            self.stats.tasks_with_design_tokens += 1
            changes += 1

        # Step 6: Generate success_criteria if missing
        if not task.success_criteria:
            criteria = self._generate_success_criteria(task)
            if criteria:
                task.success_criteria = criteria
                self.stats.tasks_with_success_criteria += 1
                changes += 1

        # Clean up empty enrichment_context
        if not task.enrichment_context:
            task.enrichment_context = None

        return changes

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # REQUIREMENT INFERENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _infer_requirements(self, task: Any) -> List[str]:
        """Infer related requirements from task type and content."""
        reqs: Set[str] = set()

        # A) Schema tasks: Entity name → Requirements via Data Dictionary
        if task.type.startswith("schema_"):
            entity_name = self._extract_entity_name(task.id)
            if entity_name and entity_name.lower() in self._entity_to_reqs:
                reqs.update(self._entity_to_reqs[entity_name.lower()])

        # B) API tasks: Extract path from task ID, match to OpenAPI requirement tags
        elif task.type.startswith("api_"):
            # Task IDs like EPIC-001-API-POST-api_v1_auth_2fa_setup-controller
            # Also try matching entity name from the path
            entity_name = self._extract_entity_from_api_task(task.id)
            if entity_name and entity_name.lower() in self._entity_to_reqs:
                reqs.update(self._entity_to_reqs[entity_name.lower()])

            # Also keyword-match against requirement IDs
            keywords = self._extract_keywords_from_title(task.title)
            for req_id in self._req_to_user_stories:
                req_lower = req_id.lower()
                if any(kw in req_lower for kw in keywords):
                    reqs.add(req_id)

        # C) Frontend tasks: keyword matching
        elif task.type.startswith("fe_"):
            keywords = self._extract_keywords_from_title(task.title)
            for req_id in self._req_to_user_stories:
                req_lower = req_id.lower()
                if any(kw in req_lower for kw in keywords):
                    reqs.add(req_id)

        # D) Test tasks: inherit from the module being tested
        elif task.type.startswith("test_"):
            tested_entity = self._extract_entity_from_test_task(task)
            if tested_entity and tested_entity.lower() in self._entity_to_reqs:
                reqs.update(self._entity_to_reqs[tested_entity.lower()])

        # E) Verify tasks: inherit from what's being verified
        elif task.type.startswith("verify_"):
            # Try to match entity or module name from task title/description
            keywords = self._extract_keywords_from_title(task.title)
            for entity_name, entity_reqs in self._entity_to_reqs.items():
                if any(kw == entity_name for kw in keywords):
                    reqs.update(entity_reqs)

        return sorted(reqs)[:10]  # Cap at 10 requirements per task

    def _infer_user_stories(self, task: Any) -> List[str]:
        """Infer related user stories via requirement → user story mapping."""
        stories: Set[str] = set()

        for req_id in task.related_requirements:
            if req_id in self._req_to_user_stories:
                for story in self._req_to_user_stories[req_id]:
                    stories.add(story.get("id", ""))

        return sorted(s for s in stories if s)[:5]

    def _get_user_story_details(self, task: Any) -> List[Dict]:
        """Get full user story details for this task's linked requirements."""
        details = []
        seen_ids: Set[str] = set()

        for req_id in task.related_requirements[:5]:
            stories = self._req_to_user_stories.get(req_id, [])
            for story in stories:
                story_id = story.get("id", "")
                if story_id and story_id not in seen_ids:
                    seen_ids.add(story_id)
                    details.append(story)

        return details[:3]  # Cap at 3 for token budget

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DIAGRAM SELECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # Preferred diagram types per task type
    _DIAGRAM_PRIORITY = {
        "schema_model": ["erDiagram", "er", "class", "classDiagram", "state", "stateDiagram"],
        "schema_relations": ["erDiagram", "er", "class", "classDiagram"],
        "schema_migration": ["erDiagram", "er"],
        "api_controller": ["sequence", "flowchart"],
        "api_service": ["sequence", "state", "stateDiagram"],
        "api_dto": ["class", "classDiagram", "sequence"],
        "api_guard": ["sequence", "flowchart"],
        "api_validation": ["flowchart", "sequence"],
        "fe_page": ["flowchart", "sequence"],
        "fe_component": ["state", "stateDiagram", "flowchart"],
        "test_unit": ["sequence", "state", "stateDiagram"],
        "test_e2e_happy": ["flowchart", "sequence"],
        "test_e2e_negative": ["flowchart", "state", "stateDiagram"],
    }

    def _get_relevant_diagrams(self, task: Any, effective_type: str = "") -> List[Dict]:
        """Get the most relevant diagrams for a task (max 3)."""
        candidates = []

        for req_id in task.related_requirements:
            if req_id in self._req_to_diagrams:
                candidates.extend(self._req_to_diagrams[req_id])

        if not candidates:
            return []

        # Get preferred types for this task type (Phase 30: prefer effective_type)
        lookup_type = effective_type or task.type
        preferred = self._DIAGRAM_PRIORITY.get(lookup_type, ["sequence", "flowchart", "state"])

        def sort_key(d: Dict) -> int:
            dtype = d.get("type", "")
            try:
                return preferred.index(dtype)
            except ValueError:
                return 100

        candidates.sort(key=sort_key)

        # Deduplicate by (type, file)
        seen: Set[str] = set()
        result = []
        for d in candidates:
            key = d.get("file", d.get("type", ""))
            if key not in seen:
                seen.add(key)
                result.append(d)
                if len(result) >= 3:
                    break

        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SELF-CRITIQUE WARNINGS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_critique_warnings(self, task: Any) -> List[Dict]:
        """Get relevant self-critique warnings for this task."""
        warnings = []
        seen_ids: Set[str] = set()

        for req_id in task.related_requirements:
            if req_id in self._req_to_critique:
                for issue in self._req_to_critique[req_id]:
                    issue_id = issue.get("id", "")
                    if issue_id and issue_id not in seen_ids:
                        seen_ids.add(issue_id)
                        warnings.append(issue)

        # Sort by severity: high first
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        warnings.sort(key=lambda w: severity_order.get(w.get("severity", ""), 99))

        return warnings[:5]  # Cap at 5

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DTO CROSS-REFERENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_related_dtos(self, task: Any) -> List[Dict]:
        """Get OpenAPI DTOs related to this schema task's entity."""
        if not self._openapi_schemas:
            return []

        entity_name = self._extract_entity_name(task.id)
        if not entity_name:
            return []

        dtos = []
        entity_lower = entity_name.lower().replace("_", "")

        for schema_name, schema_def in self._openapi_schemas.items():
            schema_lower = schema_name.lower().replace("_", "")
            # Match: "CreateAuthMethodRequest" → "authmethod" in schema name
            if entity_lower in schema_lower:
                properties = self._extract_schema_properties(schema_def)
                if properties:
                    dtos.append({
                        "name": schema_name,
                        "properties": properties,
                    })

        return dtos[:5]

    def _extract_schema_properties(self, schema_def: Dict) -> List[Dict]:
        """Extract property list from an OpenAPI schema definition."""
        properties = []
        props = schema_def.get("properties", {})

        for prop_name, prop_def in props.items():
            prop_type = prop_def.get("type", "string")
            enum_values = prop_def.get("enum", [])
            description = prop_def.get("description", "")

            entry: Dict[str, Any] = {"name": prop_name, "type": prop_type}
            if enum_values:
                entry["enum"] = enum_values[:10]
            if description:
                entry["description"] = description[:100]
            properties.append(entry)

        return properties[:15]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SUCCESS CRITERIA GENERATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _TYPE_CRITERIA = {
        "schema_model": "Prisma model defined with all attributes, correct types, and @id field",
        "schema_relations": "All Prisma relations defined with correct cardinality and referential actions",
        "schema_migration": "Migration generated and validated with prisma validate",
        "api_controller": "NestJS controller with correct decorators, DTOs, and route paths",
        "api_service": "Service with Prisma CRUD operations, error handling, and proper return types",
        "api_dto": "DTOs with class-validator decorators matching OpenAPI schema",
        "api_guard": "Guard with JWT validation and role-based access control",
        "api_validation": "Validation pipe with all input constraints from the DTO",
        "fe_page": "React page component with routing, state management, and error boundaries",
        "fe_component": "Reusable React component with typed props interface",
        "test_unit": "Unit tests covering happy path, edge cases, and error scenarios",
        "test_e2e_happy": "E2E test validating the complete happy-path user flow",
        "test_e2e_negative": "E2E test validating error handling and edge cases",
    }

    def _generate_success_criteria(self, task: Any) -> Optional[str]:
        """Generate success criteria from task type, user stories, and gaps."""
        parts = []

        # Base criteria from task type
        base = self._TYPE_CRITERIA.get(task.type, "")
        if base:
            parts.append(base)

        # From user story descriptions (linked via requirements)
        for req_id in task.related_requirements[:3]:
            stories = self._req_to_user_stories.get(req_id, [])
            for story in stories[:1]:
                i_want = story.get("i_want", "")
                if i_want:
                    parts.append(f"User can: {i_want}")

        # From self-critique suggestions
        warnings = self._get_critique_warnings(task)
        for w in warnings[:2]:
            suggestion = w.get("suggestion", "")
            if suggestion:
                parts.append(f"Address: {suggestion[:120]}")

        return "; ".join(parts) if parts else None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GHERKIN TEST SCENARIOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_gherkin_scenarios(self, task: Any, mapping: Any = None) -> Optional[str]:
        """Get matching Gherkin feature block for test tasks via user story linkage."""
        # Phase 30: Try LLM-mapped feature files first
        if mapping and mapping.feature_files:
            for feature_file in mapping.feature_files:
                # Read the .feature file directly
                for test_dir in ["testing", "tests"]:
                    feature_path = self.project_path / test_dir / feature_file
                    if feature_path.exists():
                        try:
                            content = feature_path.read_text(encoding="utf-8")
                            if len(content) > 800:
                                content = content[:780] + "\n  # ... (truncated)"
                            return content
                        except Exception:
                            pass

        if not self._us_to_gherkin:
            # Phase 30: Also try reading .feature files by user story linkage
            if mapping and mapping.user_story_ids:
                for us_id in mapping.user_story_ids:
                    feature_name = f"us_{us_id.replace('US-', '').zfill(3)}.feature"
                    for test_dir in ["testing", "tests"]:
                        feature_path = self.project_path / test_dir / feature_name
                        if feature_path.exists():
                            try:
                                content = feature_path.read_text(encoding="utf-8")
                                if len(content) > 800:
                                    content = content[:780] + "\n  # ... (truncated)"
                                return content
                            except Exception:
                                pass
            return None

        # Find user stories linked to this task's requirements
        for req_id in task.related_requirements:
            stories = self._req_to_user_stories.get(req_id, [])
            for story in stories:
                us_id = story.get("id", "")
                if us_id in self._us_to_gherkin:
                    gherkin = self._us_to_gherkin[us_id]
                    # Truncate to ~800 chars for token budget
                    if len(gherkin) > 800:
                        gherkin = gherkin[:780] + "\n  # ... (truncated)"
                    return gherkin

        # Also try matching by keywords in task title against Gherkin feature names
        keywords = self._extract_keywords_from_title(task.title)
        for us_id, gherkin in self._us_to_gherkin.items():
            feature_lower = gherkin[:200].lower()
            if any(kw in feature_lower for kw in keywords if len(kw) > 3):
                if len(gherkin) > 800:
                    gherkin = gherkin[:780] + "\n  # ... (truncated)"
                return gherkin

        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # COMPONENT SPEC EXTRACTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_component_spec(self, task: Any, mapping: Any = None) -> Optional[Dict]:
        """Get matching component spec for fe_component tasks."""
        if not self._comp_specs:
            return None

        # Phase 30: Try LLM-mapped component IDs first
        if mapping and mapping.component_ids:
            for comp_id in mapping.component_ids:
                if comp_id in self._comp_specs:
                    return self._comp_specs[comp_id]

        # Try matching by component name in task title/ID
        text = f"{task.id} {task.title}".lower()
        for comp_id, spec in self._comp_specs.items():
            comp_name = spec.get("name", "").lower()
            if comp_name and comp_name in text:
                return spec

        # Try matching COMP-XXX reference in task description
        comp_refs = re.findall(r"COMP-\d+", f"{task.id} {task.title} {task.description}")
        for ref in comp_refs:
            if ref in self._comp_specs:
                return self._comp_specs[ref]

        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SCREEN SPEC EXTRACTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_screen_spec(self, task: Any, mapping: Any = None) -> Optional[Dict]:
        """Get matching screen spec for fe_page tasks, enriched with component details."""
        if not self._screen_specs:
            return None

        matched_screen = None

        # Phase 30: Try LLM-mapped screen IDs first
        if mapping and mapping.screen_ids:
            for screen_id in mapping.screen_ids:
                if screen_id in self._screen_specs:
                    matched_screen = self._screen_specs[screen_id]
                    break

        # A) Match via user story -> screen mapping
        if not matched_screen:
            for req_id in task.related_requirements:
                stories = self._req_to_user_stories.get(req_id, [])
                for story in stories:
                    us_id = story.get("id", "")
                    if us_id in self._us_to_screen:
                        screen_id = self._us_to_screen[us_id]
                        if screen_id in self._screen_specs:
                            matched_screen = self._screen_specs[screen_id]
                            break
                if matched_screen:
                    break

        # B) Match by route or screen name in task title
        if not matched_screen:
            text = f"{task.id} {task.title}".lower()
            for screen_id, spec in self._screen_specs.items():
                screen_title = spec.get("title", "").lower()
                if screen_title and screen_title.split()[0] in text:
                    matched_screen = spec
                    break

        if not matched_screen:
            return None

        # Enrich screen spec with component details
        enriched = dict(matched_screen)
        comp_details = []
        for comp_id in matched_screen.get("components", [])[:6]:
            if comp_id in self._comp_specs:
                cs = self._comp_specs[comp_id]
                comp_details.append({
                    "id": comp_id,
                    "name": cs.get("name", ""),
                    "props": cs.get("props", [])[:5],
                    "accessibility": cs.get("accessibility", {}),
                })
        if comp_details:
            enriched["component_details"] = comp_details

        return enriched

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ROUTE MATCHING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_related_routes(self, task: Any) -> List[Dict]:
        """Get routes related to this frontend page task."""
        if not self._route_map:
            return []

        keywords = self._extract_keywords_from_title(task.title)
        matched = []
        for route in self._route_map:
            route_lower = f"{route['name']} {route['content']}".lower()
            if any(kw in route_lower for kw in keywords if len(kw) > 3):
                matched.append(route)

        return matched[:5]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPER METHODS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _extract_entity_name(self, task_id: str) -> Optional[str]:
        """Extract entity name from task ID like EPIC-001-SCHEMA-AuthMethod-model."""
        # Pattern: EPIC-{NNN}-SCHEMA-{EntityName}-{subtype}
        match = re.search(r"SCHEMA-(\w+?)-(model|relations|migration)", task_id)
        if match:
            return match.group(1)
        return None

    def _extract_entity_from_api_task(self, task_id: str) -> Optional[str]:
        """Extract entity name from API task ID like EPIC-001-API-POST-api_v1_auth_2fa_setup-controller."""
        # Try to find known entity names in the task ID
        task_lower = task_id.lower()
        for entity_name in self._entity_to_reqs:
            if entity_name in task_lower:
                return entity_name
        return None

    def _extract_entity_from_test_task(self, task: Any) -> Optional[str]:
        """Extract entity being tested from a test task."""
        # Check task description or title for entity references
        text = f"{task.title} {task.description}".lower()
        for entity_name in self._entity_to_reqs:
            if entity_name in text:
                return entity_name
        return None

    def _extract_keywords_from_title(self, title: str) -> List[str]:
        """Extract searchable keywords from task title."""
        # Remove common noise words
        noise = {"create", "implement", "add", "update", "fix", "run", "define",
                 "setup", "configure", "generate", "test", "verify", "check",
                 "prisma", "model", "controller", "service", "dto", "guard",
                 "the", "for", "with", "and", "from", "all", "required"}

        words = re.findall(r"[a-z]+", title.lower())
        keywords = [w for w in words if len(w) > 2 and w not in noise]
        return keywords

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PERSISTENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _save_enriched_tasks(self, task_list: Any):
        """Save enriched tasks to epic-{id}-tasks-enriched.json.
        Preserves existing task status (completed/failed) from previous runs."""
        tasks_dir = self.project_path / "tasks"
        if not tasks_dir.exists():
            tasks_dir.mkdir(parents=True, exist_ok=True)

        output_path = tasks_dir / f"{task_list.epic_id.lower()}-tasks-enriched.json"

        # Preserve existing task statuses from previous runs
        existing_statuses = {}
        if output_path.exists():
            try:
                old_data = json.loads(output_path.read_text(encoding="utf-8"))
                for t in old_data.get("tasks", []):
                    tid = t.get("id", "")
                    status = t.get("status", "pending")
                    if status in ("completed", "verified"):
                        existing_statuses[tid] = status
            except Exception:
                pass

        # Apply preserved statuses to current task list
        for task in task_list.tasks:
            if task.id in existing_statuses and task.status not in ("completed", "verified"):
                task.status = existing_statuses[task.id]

        tasks_data = {
            "epic_id": task_list.epic_id,
            "epic_name": getattr(task_list, "epic_name", ""),
            "enrichment_timestamp": datetime.now().isoformat(),
            "enrichment_stats": {
                "total_tasks": self.stats.total_tasks,
                "tasks_with_requirements": self.stats.tasks_with_requirements,
                "tasks_with_user_stories": self.stats.tasks_with_user_stories,
                "tasks_with_diagrams": self.stats.tasks_with_diagrams,
                "tasks_with_warnings": self.stats.tasks_with_warnings,
                "tasks_with_dtos": self.stats.tasks_with_dtos,
                "tasks_with_success_criteria": self.stats.tasks_with_success_criteria,
                "tasks_with_test_scenarios": self.stats.tasks_with_test_scenarios,
                "tasks_with_component_specs": self.stats.tasks_with_component_specs,
                "tasks_with_screen_specs": self.stats.tasks_with_screen_specs,
                "tasks_with_accessibility": self.stats.tasks_with_accessibility,
                "tasks_with_routes": self.stats.tasks_with_routes,
                "tasks_with_design_tokens": self.stats.tasks_with_design_tokens,
            },
            "tasks": [self._task_to_dict(t) for t in task_list.tasks],
        }

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(tasks_data, f, indent=2, ensure_ascii=False)
            logger.info("enriched_tasks_saved", path=str(output_path))
        except Exception as e:
            logger.warning("enriched_tasks_save_failed", error=str(e))

    def _task_to_dict(self, task: Any) -> Dict:
        """Convert a Task to a serializable dict, including enrichment fields."""
        d = {
            "id": task.id,
            "epic_id": task.epic_id,
            "type": task.type,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "dependencies": task.dependencies,
            "estimated_minutes": task.estimated_minutes,
            "output_files": task.output_files,
            "related_requirements": task.related_requirements,
            "related_user_stories": task.related_user_stories,
            "phase": task.phase,
            "success_criteria": task.success_criteria,
        }
        if task.enrichment_context:
            d["enrichment_context"] = task.enrichment_context
        return d
