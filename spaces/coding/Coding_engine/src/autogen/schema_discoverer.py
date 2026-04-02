"""
Phase 30: LLM-assisted Schema Discovery.

Discovers the documentation structure of ANY project by sampling file headers
and sending them to an LLM in a single call. Produces a project_schema.json
that tells TaskEnricher how to parse each file type dynamically.

This makes the enrichment pipeline project-agnostic: it works regardless of
ID naming conventions, file formats, or languages used in the documentation.

Entry point: SchemaDiscoverer(project_path).discover() -> ProjectSchema
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from src.llm_config import get_model

logger = structlog.get_logger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA STRUCTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class FileSource:
    """Description of a discovered documentation file."""
    file: str  # relative path from project root
    format: str  # "json", "markdown", "yaml", "gherkin", "mermaid"
    purpose: str  # "tasks", "user_stories", "components", etc.
    id_field: str = ""  # JSON field name or markdown pattern for IDs
    id_pattern: str = ""  # regex for ID values e.g. "TASK-\\d+"
    structure: str = ""  # "flat_array", "nested_by_feature", "markdown_sections"
    key_fields: Dict[str, str] = field(default_factory=dict)  # field mappings


@dataclass
class ProjectSchema:
    """Complete schema describing a project's documentation structure."""
    project_name: str = ""
    language: str = "en"  # primary language of documentation
    requirement_id_pattern: str = ""  # e.g. "WA-[A-Z]+-\\d+"
    sources: Dict[str, FileSource] = field(default_factory=dict)  # purpose -> FileSource
    diagram_naming: str = ""  # e.g. "{requirement_id}_{type}.mmd"
    schema_hash: str = ""  # for caching

    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dict."""
        return {
            "project_name": self.project_name,
            "language": self.language,
            "requirement_id_pattern": self.requirement_id_pattern,
            "diagram_naming": self.diagram_naming,
            "schema_hash": self.schema_hash,
            "sources": {
                k: {
                    "file": v.file,
                    "format": v.format,
                    "purpose": v.purpose,
                    "id_field": v.id_field,
                    "id_pattern": v.id_pattern,
                    "structure": v.structure,
                    "key_fields": v.key_fields,
                }
                for k, v in self.sources.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ProjectSchema":
        """Deserialize from JSON dict."""
        schema = cls(
            project_name=data.get("project_name", ""),
            language=data.get("language", "en"),
            requirement_id_pattern=data.get("requirement_id_pattern", ""),
            diagram_naming=data.get("diagram_naming", ""),
            schema_hash=data.get("schema_hash", ""),
        )
        for purpose, source_data in data.get("sources", {}).items():
            schema.sources[purpose] = FileSource(
                file=source_data.get("file", ""),
                format=source_data.get("format", ""),
                purpose=source_data.get("purpose", purpose),
                id_field=source_data.get("id_field", ""),
                id_pattern=source_data.get("id_pattern", ""),
                structure=source_data.get("structure", ""),
                key_fields=source_data.get("key_fields", {}),
            )
        return schema


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEMA DISCOVERER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Documentation directories to scan
_SCAN_DIRS = [
    "tasks", "user_stories", "ui_design", "ux_design", "testing",
    "data", "api", "diagrams", "architecture", "quality", "reports",
    "work_breakdown", "infrastructure", "state_machines", "tech_stack",
]

# File extensions to sample
_SAMPLE_EXTENSIONS = {".json", ".md", ".yaml", ".yml", ".feature", ".mmd"}

# Max bytes to sample per file header
_HEADER_BYTES = 1500

# LLM system prompt for schema discovery
_SYSTEM_PROMPT = """You are a documentation structure analyzer. Given file header samples from a software project's documentation, you must identify:

1. What each file contains (tasks, user stories, components, screens, tests, etc.)
2. The format and structure of each file
3. ID patterns used (e.g. TASK-001, US-001, COMP-001, WA-AUTH-001, etc.)
4. Field names and how entities cross-reference each other
5. The primary language (en, de, fr, etc.)

Respond with ONLY valid JSON matching this schema:
{
  "project_name": "string",
  "language": "en|de|fr|...",
  "requirement_id_pattern": "regex pattern for requirement IDs",
  "diagram_naming": "pattern like {requirement_id}_{type}.mmd or empty",
  "sources": {
    "tasks": {
      "file": "relative/path/to/file",
      "format": "json|markdown|yaml|csv",
      "purpose": "tasks",
      "id_field": "field name containing IDs (for JSON) or markdown pattern",
      "id_pattern": "regex for ID values",
      "structure": "flat_array|nested_by_feature|markdown_sections|directory",
      "key_fields": {
        "title": "actual_field_name",
        "description": "actual_field_name",
        "type": "actual_field_name",
        "dependencies": "actual_field_name",
        "parent_requirement": "actual_field_name",
        "parent_user_story": "actual_field_name",
        "parent_feature": "actual_field_name",
        "acceptance_criteria": "actual_field_name"
      }
    },
    "user_stories": { ... same structure ... },
    "components": { ... },
    "screens": { ... },
    "tests": { ... },
    "diagrams": { ... },
    "design_tokens": { ... },
    "accessibility": { ... },
    "routes": { ... },
    "data_dictionary": { ... },
    "openapi": { ... },
    "quality_report": { ... },
    "gherkin_features": { ... }
  }
}

Rules:
- Only include sources you actually found evidence for in the samples
- For "key_fields", map to the ACTUAL field names in the file (not ideal names)
- For user_stories, include the field that links to requirement IDs
- For screens, include the field that links to user stories and components
- If a source is a directory of files (e.g. screens/*.md), set structure to "directory"
- Be precise with regex patterns - match what you see in the samples
- Leave fields empty ("") if not applicable"""


class SchemaDiscoverer:
    """
    Discovers project documentation structure via LLM analysis.

    Samples headers from documentation files and sends them to an LLM
    in a single call to produce a ProjectSchema. Results are cached
    based on a hash of the file listing.
    """

    def __init__(
        self,
        project_path: Path,
        model: str = None,
        api_key: Optional[str] = None,
    ):
        self.project_path = Path(project_path)
        self.model = model or get_model("enrichment")
        # Priority: explicit key > OPENROUTER > ANTHROPIC
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
        self._use_openrouter = bool(os.getenv("OPENROUTER_API_KEY")) and not api_key
        self._cache_dir = self.project_path / ".enrichment_cache"

    def discover(self, force: bool = False) -> ProjectSchema:
        """
        Discover the project's documentation schema.

        Checks cache first (based on file listing hash).
        If cache hit and not forced, returns cached schema.
        Otherwise, samples files and calls LLM.

        Args:
            force: Skip cache and re-discover

        Returns:
            ProjectSchema with discovered structure
        """
        # Compute hash of current file listing
        current_hash = self._compute_file_hash()

        # Check cache
        if not force:
            cached = self._load_cache(current_hash)
            if cached:
                logger.info("schema_loaded_from_cache", hash=current_hash[:12])
                return cached

        # Sample file headers
        samples = self._sample_file_headers()
        if not samples:
            logger.warning("no_documentation_files_found")
            return ProjectSchema(schema_hash=current_hash)

        # Call LLM
        schema = self._call_llm(samples)
        schema.schema_hash = current_hash

        # Cache result
        self._save_cache(schema)

        logger.info(
            "schema_discovered",
            sources=len(schema.sources),
            language=schema.language,
            hash=current_hash[:12],
        )
        return schema

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FILE SAMPLING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _sample_file_headers(self) -> List[Dict[str, str]]:
        """Sample the first N bytes of each documentation file."""
        samples = []

        # Scan known documentation directories
        for dir_name in _SCAN_DIRS:
            dir_path = self.project_path / dir_name
            if not dir_path.exists():
                continue

            for file_path in sorted(dir_path.rglob("*")):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in _SAMPLE_EXTENSIONS:
                    continue
                # Skip very large directories (e.g. 374 diagram files)
                # Just sample first 3 of each type
                rel = file_path.relative_to(self.project_path).as_posix()

                try:
                    content = file_path.read_bytes()[:_HEADER_BYTES].decode("utf-8", errors="replace")
                    samples.append({
                        "path": rel,
                        "size_bytes": file_path.stat().st_size,
                        "header": content,
                    })
                except Exception:
                    pass

        # Also check root-level files
        for file_path in self.project_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in _SAMPLE_EXTENSIONS:
                try:
                    content = file_path.read_bytes()[:_HEADER_BYTES].decode("utf-8", errors="replace")
                    samples.append({
                        "path": file_path.name,
                        "size_bytes": file_path.stat().st_size,
                        "header": content,
                    })
                except Exception:
                    pass

        # Deduplicate similar files (e.g. screen-001.md..screen-020.md → keep 2)
        samples = self._deduplicate_samples(samples)

        logger.debug("files_sampled", count=len(samples))
        return samples

    def _deduplicate_samples(self, samples: List[Dict]) -> List[Dict]:
        """Keep max 3 samples per directory/pattern to avoid token waste."""
        from collections import defaultdict
        groups: Dict[str, List[Dict]] = defaultdict(list)

        for sample in samples:
            path = sample["path"]
            # Group by parent dir + extension
            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                group_key = parts[0] + "/*" + Path(path).suffix
            else:
                group_key = "*" + Path(path).suffix
            groups[group_key].append(sample)

        result = []
        for group_key, group_samples in groups.items():
            # Keep first 3 (sorted by path for determinism)
            group_samples.sort(key=lambda s: s["path"])
            result.extend(group_samples[:3])
            if len(group_samples) > 3:
                # Add a note about how many more exist
                result.append({
                    "path": f"... and {len(group_samples) - 3} more files matching {group_key}",
                    "size_bytes": 0,
                    "header": "",
                })

        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LLM CALL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _call_llm(self, samples: List[Dict]) -> ProjectSchema:
        """Send file samples to LLM and parse the structured response."""
        if not self.api_key:
            logger.warning("no_api_key_falling_back_to_heuristic")
            return self._heuristic_fallback(samples)

        # Build the user message with file samples
        sample_text = self._format_samples(samples)
        user_msg = f"Analyze these documentation file samples and discover the project schema:\n\n{sample_text}"

        try:
            if self._use_openrouter:
                response_text = self._call_openrouter(user_msg)
            else:
                response_text = self._call_anthropic(user_msg)

            # Extract JSON from response (handle markdown code blocks)
            json_text = self._extract_json(response_text)
            raw = json.loads(json_text)

            schema = ProjectSchema.from_dict(raw)
            logger.info("schema_discovered_via_llm", sources=len(schema.sources))
            return schema

        except Exception as e:
            logger.warning("llm_schema_discovery_failed", error=str(e))
            return self._heuristic_fallback(samples)

    def _call_anthropic(self, user_msg: str) -> str:
        """Call Anthropic API directly."""
        if anthropic is None:
            raise RuntimeError("anthropic SDK not installed")
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text

    def _call_openrouter(self, user_msg: str) -> str:
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
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _format_samples(self, samples: List[Dict]) -> str:
        """Format file samples into a readable prompt block."""
        parts = []
        for sample in samples:
            if not sample["header"]:
                parts.append(f"--- {sample['path']} ---")
                continue
            parts.append(
                f"--- {sample['path']} ({sample['size_bytes']} bytes) ---\n"
                f"{sample['header']}"
            )
        return "\n\n".join(parts)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Try to find ```json ... ``` block
        import re
        match = re.search(r"```(?:json)?\s*\n(.+?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try to find raw JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return text[start:end]

        return text

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HEURISTIC FALLBACK (no LLM available)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _heuristic_fallback(self, samples: List[Dict]) -> ProjectSchema:
        """Best-effort schema discovery without LLM using file patterns."""
        schema = ProjectSchema()
        import re

        for sample in samples:
            path = sample["path"]
            header = sample["header"]

            # Detect tasks
            if "task" in path.lower() and path.endswith(".json"):
                schema.sources["tasks"] = FileSource(
                    file=path, format="json", purpose="tasks",
                    id_pattern=self._find_id_pattern(header, r'["\']id["\']\s*:\s*["\']([A-Z]+-\d+)'),
                )

            # Detect user stories
            elif "user_stor" in path.lower() and path.endswith(".json"):
                schema.sources["user_stories"] = FileSource(
                    file=path, format="json", purpose="user_stories",
                    id_pattern=self._find_id_pattern(header, r'"id"\s*:\s*"(US-\d+)"'),
                )

            # Detect design tokens
            elif "design_token" in path.lower() and path.endswith(".json"):
                schema.sources["design_tokens"] = FileSource(
                    file=path, format="json", purpose="design_tokens",
                )

            # Detect components.md
            elif "component" in path.lower() and path.endswith(".md"):
                schema.sources["components"] = FileSource(
                    file=path, format="markdown", purpose="components",
                    id_pattern=self._find_id_pattern(header, r"(COMP-\d+)"),
                    structure="markdown_sections",
                )

            # Detect screen specs
            elif "screen" in path.lower() and path.endswith(".md"):
                if "screens" not in schema.sources:
                    parent = str(Path(path).parent)
                    schema.sources["screens"] = FileSource(
                        file=parent, format="markdown", purpose="screens",
                        id_pattern=self._find_id_pattern(header, r"(SCREEN-\d+)"),
                        structure="directory",
                    )

            # Detect Gherkin features
            elif path.endswith(".feature"):
                if "gherkin_features" not in schema.sources:
                    parent = str(Path(path).parent)
                    schema.sources["gherkin_features"] = FileSource(
                        file=parent, format="gherkin", purpose="gherkin_features",
                        structure="directory",
                    )

            # Detect accessibility
            elif "accessib" in path.lower() and path.endswith(".md"):
                schema.sources["accessibility"] = FileSource(
                    file=path, format="markdown", purpose="accessibility",
                )

            # Detect information architecture / routes
            elif "information_architecture" in path.lower() and path.endswith(".md"):
                schema.sources["routes"] = FileSource(
                    file=path, format="markdown", purpose="routes",
                )

            # Detect diagrams
            elif path.endswith(".mmd"):
                if "diagrams" not in schema.sources:
                    parent = str(Path(path).parent)
                    schema.sources["diagrams"] = FileSource(
                        file=parent, format="mermaid", purpose="diagrams",
                        structure="directory",
                    )
                    # Infer diagram naming pattern
                    name = Path(path).name
                    req_match = re.match(r"([A-Z]+-[A-Z]+-\d+)_(.+)\.mmd", name)
                    if req_match:
                        schema.diagram_naming = "{requirement_id}_{type}.mmd"
                        schema.requirement_id_pattern = re.sub(
                            r"\d+", r"\\d+",
                            req_match.group(1).replace(req_match.group(1).split("-")[-1], r"\d+"),
                        )

            # Detect OpenAPI
            elif ("openapi" in path.lower() or "swagger" in path.lower()) and path.endswith((".yaml", ".yml")):
                schema.sources["openapi"] = FileSource(
                    file=path, format="yaml", purpose="openapi",
                )

            # Detect data dictionary
            elif "data_dictionary" in path.lower() and path.endswith(".md"):
                schema.sources["data_dictionary"] = FileSource(
                    file=path, format="markdown", purpose="data_dictionary",
                )

            # Detect quality report
            elif "self_critique" in path.lower():
                schema.sources["quality_report"] = FileSource(
                    file=path, format="json" if path.endswith(".json") else "markdown",
                    purpose="quality_report",
                )

        # Try to detect language from task/story content
        for sample in samples:
            if any(de_word in sample["header"].lower() for de_word in
                   ["implementierung", "beschreibung", "benutzer", "registrierung", "authentifizierung"]):
                schema.language = "de"
                break

        logger.info("schema_discovered_via_heuristic", sources=len(schema.sources))
        return schema

    def _find_id_pattern(self, header: str, regex: str) -> str:
        """Find an ID pattern in a header sample."""
        import re
        match = re.search(regex, header)
        if match:
            # Generalize the pattern
            sample_id = match.group(1)
            # Replace digits with \d+
            pattern = re.sub(r"\d+", r"\\d+", sample_id)
            return pattern
        return ""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CACHING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _compute_file_hash(self) -> str:
        """Compute a hash of the project's documentation file listing."""
        hasher = hashlib.sha256()
        for dir_name in _SCAN_DIRS:
            dir_path = self.project_path / dir_name
            if not dir_path.exists():
                continue
            for file_path in sorted(dir_path.rglob("*")):
                if file_path.is_file() and file_path.suffix.lower() in _SAMPLE_EXTENSIONS:
                    rel = file_path.relative_to(self.project_path).as_posix()
                    size = file_path.stat().st_size
                    hasher.update(f"{rel}:{size}\n".encode())

        # Also hash root-level files
        for file_path in sorted(self.project_path.iterdir()):
            if file_path.is_file() and file_path.suffix.lower() in _SAMPLE_EXTENSIONS:
                size = file_path.stat().st_size
                hasher.update(f"{file_path.name}:{size}\n".encode())

        return hasher.hexdigest()

    def _load_cache(self, expected_hash: str) -> Optional[ProjectSchema]:
        """Load cached schema if hash matches."""
        cache_file = self._cache_dir / "project_schema.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("schema_hash") == expected_hash:
                return ProjectSchema.from_dict(data)
        except Exception:
            pass
        return None

    def _save_cache(self, schema: ProjectSchema):
        """Save schema to cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cache_dir / "project_schema.json"
        try:
            cache_file.write_text(
                json.dumps(schema.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug("schema_cached", path=str(cache_file))
        except Exception as e:
            logger.warning("schema_cache_failed", error=str(e))
