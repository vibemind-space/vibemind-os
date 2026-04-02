"""
Phase 30: LLM-assisted Task Mapping.

Takes a ProjectSchema + task list and maps each task to its related
documentation artifacts (requirements, user stories, screens, components)
via a single LLM call with semantic understanding.

This solves the fundamental problem of matching tasks written in any
language/naming convention to structured documentation:
- German task titles -> English requirement IDs
- Generic task types ("development") -> specific types ("api_controller")
- Cross-domain linking without hardcoded patterns

Entry point: TaskMapper(project_path, schema).map_tasks(tasks) -> TaskMappingResult
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import structlog

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from src.llm_config import get_model
from src.autogen.schema_discoverer import ProjectSchema

logger = structlog.get_logger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA STRUCTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class TaskMapping:
    """Mapping for a single task to documentation artifacts."""
    task_id: str
    inferred_type: str = ""  # e.g. "api_controller", "fe_page", "schema_model"
    requirement_ids: List[str] = field(default_factory=list)
    user_story_ids: List[str] = field(default_factory=list)
    screen_ids: List[str] = field(default_factory=list)
    component_ids: List[str] = field(default_factory=list)
    feature_files: List[str] = field(default_factory=list)  # Gherkin .feature files
    keywords: List[str] = field(default_factory=list)


@dataclass
class TaskMappingResult:
    """Complete mapping result for all tasks."""
    mappings: Dict[str, TaskMapping] = field(default_factory=dict)  # task_id -> TaskMapping
    llm_used: bool = False
    error: str = ""

    def to_dict(self) -> Dict:
        """Serialize to JSON dict."""
        return {
            "llm_used": self.llm_used,
            "error": self.error,
            "mappings": {
                k: {
                    "task_id": v.task_id,
                    "inferred_type": v.inferred_type,
                    "requirement_ids": v.requirement_ids,
                    "user_story_ids": v.user_story_ids,
                    "screen_ids": v.screen_ids,
                    "component_ids": v.component_ids,
                    "feature_files": v.feature_files,
                    "keywords": v.keywords,
                }
                for k, v in self.mappings.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "TaskMappingResult":
        """Deserialize from JSON dict."""
        result = cls(
            llm_used=data.get("llm_used", False),
            error=data.get("error", ""),
        )
        for task_id, mapping_data in data.get("mappings", {}).items():
            result.mappings[task_id] = TaskMapping(
                task_id=mapping_data.get("task_id", task_id),
                inferred_type=mapping_data.get("inferred_type", ""),
                requirement_ids=mapping_data.get("requirement_ids", []),
                user_story_ids=mapping_data.get("user_story_ids", []),
                screen_ids=mapping_data.get("screen_ids", []),
                component_ids=mapping_data.get("component_ids", []),
                feature_files=mapping_data.get("feature_files", []),
                keywords=mapping_data.get("keywords", []),
            )
        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TASK MAPPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Valid inferred types (matching TaskEnricher's enrichment steps)
_VALID_TYPES = {
    "schema_model", "schema_relations", "schema_migration",
    "api_controller", "api_service", "api_dto", "api_guard", "api_validation",
    "fe_page", "fe_component",
    "test_unit", "test_e2e_happy", "test_e2e_negative", "test_integration",
    "verify_build", "verify_deploy",
    "infra_docker", "infra_ci", "infra_env",
    "docs_api", "docs_readme",
    "design_ui", "design_ux",
    "devops_pipeline", "devops_monitoring",
}

_SYSTEM_PROMPT = """You are a task-to-documentation mapper for a software project. Given:
1. A list of tasks (with IDs, titles, descriptions, types)
2. Available documentation artifacts (requirement IDs, user story IDs, screen IDs, component IDs, feature files)

Your job is to map EACH task to the documentation artifacts that are relevant to it.

Rules:
- "inferred_type" must be one of: {valid_types}
- Match tasks to requirements/stories/screens based on SEMANTIC understanding, not just string matching
- A task titled "Phone Registration Backend" should map to requirements about phone registration
- A task titled "2FA Frontend" should map to screens and components about 2FA
- Tasks with "testing" type should map to the Gherkin feature files that test the same functionality
- Tasks with "design" type should map to relevant screens and components
- Leave arrays empty if no match found - do NOT hallucinate IDs

Respond with ONLY valid JSON:
{{
  "mappings": {{
    "TASK-001": {{
      "inferred_type": "api_controller",
      "requirement_ids": ["WA-AUTH-001"],
      "user_story_ids": ["US-001"],
      "screen_ids": [],
      "component_ids": [],
      "feature_files": ["us_001.feature"],
      "keywords": ["registration", "phone", "OTP"]
    }},
    ...one entry per task...
  }}
}}"""


class TaskMapper:
    """
    Maps tasks to documentation artifacts via LLM semantic understanding.

    Single LLM call for ALL tasks (batch processing for efficiency).
    """

    def __init__(
        self,
        project_path: Path,
        schema: ProjectSchema,
        model: str = None,
        api_key: Optional[str] = None,
    ):
        self.project_path = Path(project_path)
        self.schema = schema
        self.model = model or get_model("enrichment")
        # Priority: explicit key > OPENROUTER > ANTHROPIC
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
        self._use_openrouter = bool(os.getenv("OPENROUTER_API_KEY")) and not api_key

    def map_tasks(self, tasks: List[Any]) -> TaskMappingResult:
        """
        Map all tasks to documentation artifacts.

        Args:
            tasks: List of task objects (must have id, title, description, type)

        Returns:
            TaskMappingResult with mappings for each task
        """
        if not tasks:
            return TaskMappingResult()

        # Gather available artifact IDs from the project
        artifacts = self._gather_artifact_ids()

        # Build task summaries for the LLM
        task_summaries = self._build_task_summaries(tasks)

        # Call LLM
        result = self._call_llm(task_summaries, artifacts)

        # Save mapping
        self._save_mapping(result)

        logger.info(
            "task_mapping_complete",
            tasks=len(tasks),
            mapped=len(result.mappings),
            llm_used=result.llm_used,
        )
        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ARTIFACT GATHERING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _gather_artifact_ids(self) -> Dict[str, List[str]]:
        """Gather all available artifact IDs from the project documentation."""
        import re
        artifacts: Dict[str, List[str]] = {
            "requirement_ids": [],
            "user_story_ids": [],
            "screen_ids": [],
            "component_ids": [],
            "feature_files": [],
        }

        # User stories → requirement IDs and story IDs
        us_source = self.schema.sources.get("user_stories")
        if us_source:
            us_path = self.project_path / us_source.file
            if us_path.exists():
                try:
                    raw = json.loads(us_path.read_text(encoding="utf-8"))
                    stories = raw if isinstance(raw, list) else raw.get("user_stories", [])
                    for story in stories:
                        story_id = story.get(us_source.key_fields.get("id", "id"), "")
                        if story_id:
                            artifacts["user_story_ids"].append(story_id)
                        # Extract requirement links
                        req_field = us_source.key_fields.get("requirement_link", "linked_requirement_ids")
                        req_ids = story.get(req_field, [])
                        if isinstance(req_ids, str):
                            req_ids = [req_ids] if req_ids else []
                        elif isinstance(req_ids, list):
                            pass
                        else:
                            # Try parent_requirement_id
                            alt = story.get("parent_requirement_id", "")
                            req_ids = [alt] if alt else []
                        artifacts["requirement_ids"].extend(req_ids)
                except Exception as e:
                    logger.warning("artifact_gather_user_stories_failed", error=str(e))

        # Deduplicate requirement IDs
        artifacts["requirement_ids"] = sorted(set(artifacts["requirement_ids"]))

        # Screens
        screen_source = self.schema.sources.get("screens")
        if screen_source:
            screen_dir = self.project_path / screen_source.file
            if screen_dir.is_dir():
                for f in screen_dir.glob("*.md"):
                    content = f.read_text(encoding="utf-8")[:500]
                    id_match = re.search(
                        screen_source.id_pattern.replace("\\d+", r"\d+") if screen_source.id_pattern
                        else r"(SCREEN-\d+)",
                        content,
                    )
                    if id_match:
                        artifacts["screen_ids"].append(id_match.group(0))

        # Components
        comp_source = self.schema.sources.get("components")
        if comp_source:
            comp_path = self.project_path / comp_source.file
            if comp_path.exists():
                content = comp_path.read_text(encoding="utf-8")
                pattern = comp_source.id_pattern.replace("\\d+", r"\d+") if comp_source.id_pattern else r"COMP-\d+"
                artifacts["component_ids"] = sorted(set(re.findall(pattern, content)))

        # Gherkin feature files
        gherkin_source = self.schema.sources.get("gherkin_features")
        if gherkin_source:
            gherkin_dir = self.project_path / gherkin_source.file
            if gherkin_dir.is_dir():
                artifacts["feature_files"] = sorted([
                    f.name for f in gherkin_dir.glob("*.feature")
                ])

        logger.debug(
            "artifacts_gathered",
            requirements=len(artifacts["requirement_ids"]),
            stories=len(artifacts["user_story_ids"]),
            screens=len(artifacts["screen_ids"]),
            components=len(artifacts["component_ids"]),
            features=len(artifacts["feature_files"]),
        )
        return artifacts

    def _build_task_summaries(self, tasks: List[Any]) -> List[Dict]:
        """Build compact task summaries for the LLM prompt."""
        summaries = []
        for task in tasks:
            summary = {
                "id": getattr(task, "id", ""),
                "title": getattr(task, "title", ""),
                "type": getattr(task, "type", ""),
            }
            desc = getattr(task, "description", "")
            if desc:
                summary["description"] = desc[:200]
            # Include acceptance criteria if available
            criteria = getattr(task, "acceptance_criteria", None)
            if criteria and isinstance(criteria, list):
                summary["acceptance_criteria"] = criteria[:3]
            summaries.append(summary)
        return summaries

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LLM CALL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _call_llm(self, task_summaries: List[Dict], artifacts: Dict) -> TaskMappingResult:
        """Send tasks + artifacts to LLM for semantic mapping."""
        if not self.api_key:
            logger.warning("no_api_key_skipping_task_mapping")
            return TaskMappingResult(error="no_api_key")

        # Build the prompt
        system = _SYSTEM_PROMPT.format(valid_types=", ".join(sorted(_VALID_TYPES)))

        user_msg = (
            "## Available Documentation Artifacts\n\n"
            f"**Requirement IDs:** {json.dumps(artifacts['requirement_ids'])}\n\n"
            f"**User Story IDs:** {json.dumps(artifacts['user_story_ids'])}\n\n"
            f"**Screen IDs:** {json.dumps(artifacts['screen_ids'])}\n\n"
            f"**Component IDs:** {json.dumps(artifacts['component_ids'])}\n\n"
            f"**Gherkin Feature Files:** {json.dumps(artifacts['feature_files'])}\n\n"
            f"## Tasks to Map\n\n"
            f"```json\n{json.dumps(task_summaries, indent=2, ensure_ascii=False)}\n```\n\n"
            f"Map each task to its relevant artifacts. Use semantic understanding - "
            f"task titles are in {self.schema.language.upper()} language."
        )

        try:
            if self._use_openrouter:
                response_text = self._call_openrouter(system, user_msg)
            else:
                response_text = self._call_anthropic(system, user_msg)

            json_text = self._extract_json(response_text)
            raw = json.loads(json_text)

            result = TaskMappingResult(llm_used=True)

            for task_id, mapping_data in raw.get("mappings", {}).items():
                # Validate inferred_type
                inferred_type = mapping_data.get("inferred_type", "")
                if inferred_type not in _VALID_TYPES:
                    inferred_type = ""

                # Validate artifact IDs exist
                req_ids = [r for r in mapping_data.get("requirement_ids", [])
                           if r in set(artifacts["requirement_ids"])]
                us_ids = [u for u in mapping_data.get("user_story_ids", [])
                          if u in set(artifacts["user_story_ids"])]
                screen_ids = [s for s in mapping_data.get("screen_ids", [])
                              if s in set(artifacts["screen_ids"])]
                comp_ids = [c for c in mapping_data.get("component_ids", [])
                            if c in set(artifacts["component_ids"])]
                feat_files = [f for f in mapping_data.get("feature_files", [])
                              if f in set(artifacts["feature_files"])]

                result.mappings[task_id] = TaskMapping(
                    task_id=task_id,
                    inferred_type=inferred_type,
                    requirement_ids=req_ids,
                    user_story_ids=us_ids,
                    screen_ids=screen_ids,
                    component_ids=comp_ids,
                    feature_files=feat_files,
                    keywords=mapping_data.get("keywords", []),
                )

            logger.info("task_mapping_via_llm", mapped=len(result.mappings))
            return result

        except Exception as e:
            logger.warning("llm_task_mapping_failed", error=str(e))
            return TaskMappingResult(error=str(e))

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response."""
        import re
        match = re.search(r"```(?:json)?\s*\n(.+?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return text[start:end]
        return text

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LLM PROVIDERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _call_anthropic(self, system: str, user_msg: str) -> str:
        """Call Anthropic API directly."""
        if anthropic is None:
            raise RuntimeError("anthropic SDK not installed")
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text

    def _call_openrouter(self, system: str, user_msg: str) -> str:
        """Call OpenRouter API (OpenAI-compatible)."""
        import httpx

        model = get_model("enrichment")
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PERSISTENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _save_mapping(self, result: TaskMappingResult):
        """Save mapping result to .enrichment_cache/task_mapping.json."""
        cache_dir = self.project_path / ".enrichment_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_path = cache_dir / "task_mapping.json"

        try:
            output_path.write_text(
                json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug("task_mapping_saved", path=str(output_path))
        except Exception as e:
            logger.warning("task_mapping_save_failed", error=str(e))
