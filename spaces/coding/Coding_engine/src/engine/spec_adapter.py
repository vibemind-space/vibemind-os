"""
Universal Spec Adapter - Normalizes any requirements format to internal format.

Supports:
- Simple format: { requirements: [...] }
- Rich billing spec: { project: {...}, llms: {...}, agents: {...} }
- Legacy format: { meta: {...}, requirements: [...], tech_stack: {...} }
- Documentation format: Directory with MASTER_DOCUMENT.md, tech_stack/, user_stories/, etc.
- Markdown requirements (future)
"""

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


class SpecFormat(Enum):
    """Enumeration of supported specification formats."""
    DOCUMENTATION = "documentation"    # Directory with MASTER_DOCUMENT.md, tech_stack/, etc.
    RICH_BILLING = "rich_billing"      # { project: {...}, llms: {...}, agents: {...} }
    LEGACY_TECHSTACK = "legacy_techstack"  # { meta: {...}, requirements: [...], tech_stack: {...} }
    SIMPLE = "simple"                  # { requirements: [...] }

# Lazy import to avoid circular dependency
_documentation_loader = None


def _get_documentation_loader():
    """Lazy import of DocumentationLoader."""
    global _documentation_loader
    if _documentation_loader is None:
        from src.engine.documentation_loader import DocumentationLoader
        _documentation_loader = DocumentationLoader()
    return _documentation_loader


@dataclass
class Requirement:
    """Normalized requirement structure."""
    req_id: str
    title: str
    description: str = ""
    tag: str = "functional"  # functional, security, performance, autonomy, strategic
    priority: str = "medium"  # high, medium, low
    source: str = ""
    evidence_refs: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "req_id": self.req_id,
            "title": self.title,
            "description": self.description,
            "tag": self.tag,
            "priority": self.priority,
            "source": self.source,
            "evidence_refs": self.evidence_refs,
        }


@dataclass
class APIEndpoint:
    """Normalized API endpoint definition."""
    path: str
    method: str
    description: str = ""
    request_schema: Optional[Dict] = None
    response_schema: Optional[Dict] = None
    auth_required: bool = True

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "method": self.method,
            "description": self.description,
            "request_schema": self.request_schema,
            "response_schema": self.response_schema,
            "auth_required": self.auth_required,
        }


@dataclass
class ContextLayers:
    """Optional rich context extracted from detailed specs."""
    api_specs: List[APIEndpoint] = field(default_factory=list)
    db_schema: Dict = field(default_factory=dict)
    llm_config: Dict = field(default_factory=dict)
    agent_defs: List[Dict] = field(default_factory=list)
    workflows: List[Dict] = field(default_factory=list)
    frontend_specs: Dict = field(default_factory=dict)
    monitoring_config: Dict = field(default_factory=dict)
    # Documentation format extensions
    diagrams: List[Dict] = field(default_factory=list)  # Mermaid diagrams
    entities: List[Dict] = field(default_factory=list)  # Data entities
    epics: List[Dict] = field(default_factory=list)  # Epic definitions
    design_tokens: Dict = field(default_factory=dict)  # UI design tokens
    features: List[Dict] = field(default_factory=list)  # Feature breakdowns

    def to_dict(self) -> Dict:
        return {
            "api_specs": [e.to_dict() for e in self.api_specs],
            "db_schema": self.db_schema,
            "llm_config": self.llm_config,
            "agent_defs": self.agent_defs,
            "workflows": self.workflows,
            "frontend_specs": self.frontend_specs,
            "monitoring_config": self.monitoring_config,
            "diagrams": self.diagrams,
            "entities": self.entities,
            "epics": self.epics,
            "design_tokens": self.design_tokens,
            "features": self.features,
        }

    def has_content(self) -> bool:
        """Check if any context layer has content."""
        return bool(
            self.api_specs or self.db_schema or self.llm_config or
            self.agent_defs or self.workflows or self.frontend_specs or
            self.monitoring_config or self.diagrams or self.entities or
            self.epics or self.design_tokens or self.features
        )

    def get_diagrams_by_type(self, diagram_type: str) -> List[Dict]:
        """Get diagrams filtered by type (sequence, c4, flowchart, etc.)."""
        return [d for d in self.diagrams if d.get("diagram_type") == diagram_type]

    def get_entities_for_requirements(self, req_ids: List[str]) -> List[Dict]:
        """Get entities linked to specific requirements."""
        result = []
        for entity in self.entities:
            source_reqs = entity.get("source_requirements", [])
            if any(req_id in source_reqs for req_id in req_ids):
                result.append(entity)
        return result


@dataclass
class NormalizedSpec:
    """Fully normalized specification."""
    project_name: str
    project_description: str
    requirements: List[Requirement]
    tech_stack: Dict
    context_layers: ContextLayers
    raw_spec: Dict  # Original spec for reference

    def to_dict(self) -> Dict:
        return {
            "project_name": self.project_name,
            "project_description": self.project_description,
            "requirements": [r.to_dict() for r in self.requirements],
            "tech_stack": self.tech_stack,
            "context_layers": self.context_layers.to_dict(),
        }

    def to_simple_format(self) -> Dict:
        """Convert to simple format for backward compatibility."""
        return {
            "meta": {
                "project_name": self.project_name,
                "description": self.project_description,
            },
            "requirements": [r.to_dict() for r in self.requirements],
            "tech_stack": self.tech_stack,
        }


class SpecAdapter:
    """
    Universal adapter that normalizes any requirements format.

    Usage:
        adapter = SpecAdapter()
        normalized = adapter.load("path/to/spec.json")

        # Access requirements (always available)
        for req in normalized.requirements:
            print(req.title)

        # Access rich context (if available)
        if normalized.context_layers.api_specs:
            for endpoint in normalized.context_layers.api_specs:
                print(f"{endpoint.method} {endpoint.path}")

    Supported Formats:
        - Simple JSON: { requirements: [...] }
        - Rich billing: { project: {...}, llms: {...}, agents: {...} }
        - Legacy: { meta: {...}, requirements: [...], tech_stack: {...} }
        - Documentation: Directory with MASTER_DOCUMENT.md, tech_stack/, etc.
    """

    def __init__(self):
        self._format_detectors = [
            ("rich_billing", self._is_rich_billing_format),
            ("legacy_techstack", self._is_legacy_techstack_format),
            ("simple", self._is_simple_format),
        ]
        # Track the last detected format for external access
        self.last_format: Optional[SpecFormat] = None

    def load(self, path: Union[str, Path]) -> NormalizedSpec:
        """Load and normalize a spec file or documentation directory."""
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Spec path not found: {path}")

        # Check if path is a documentation project directory
        if path.is_dir():
            if self._is_documentation_project(path):
                self.last_format = SpecFormat.DOCUMENTATION
                logger.info("spec_format_detected", format="documentation", source=str(path))
                return self._normalize_documentation(path)
            else:
                # Try to find a spec file in the directory
                for spec_file in ["requirements.json", "spec.json", "project.json"]:
                    spec_path = path / spec_file
                    if spec_path.exists():
                        path = spec_path
                        break
                else:
                    raise FileNotFoundError(
                        f"No spec file found in directory: {path}. "
                        "Expected requirements.json, spec.json, or MASTER_DOCUMENT.md"
                    )

        with open(path, "r", encoding="utf-8") as f:
            raw_spec = json.load(f)

        return self.normalize(raw_spec, source_path=str(path))

    def _is_documentation_project(self, path: Path) -> bool:
        """Check if path is a documentation format project directory."""
        indicators = [
            path / "MASTER_DOCUMENT.md",
            path / "tech_stack" / "tech_stack.json",
            path / "user_stories" / "user_stories.md",
            path / "content_analysis.json",
        ]
        return any(indicator.exists() for indicator in indicators)

    def normalize(self, raw_spec: Dict, source_path: str = "") -> NormalizedSpec:
        """Normalize any spec format to internal format."""

        # Detect format
        format_type = self._detect_format(raw_spec)
        logger.info("spec_format_detected", format=format_type, source=source_path)

        # Track detected format
        format_map = {
            "rich_billing": SpecFormat.RICH_BILLING,
            "legacy_techstack": SpecFormat.LEGACY_TECHSTACK,
            "simple": SpecFormat.SIMPLE,
        }
        self.last_format = format_map.get(format_type, SpecFormat.SIMPLE)

        # Normalize based on format
        if format_type == "rich_billing":
            return self._normalize_rich_billing(raw_spec)
        elif format_type == "legacy_techstack":
            return self._normalize_legacy_techstack(raw_spec)
        else:
            return self._normalize_simple(raw_spec)

    def _detect_format(self, spec: Dict) -> str:
        """Detect the format of a spec."""
        for format_name, detector in self._format_detectors:
            if detector(spec):
                return format_name
        return "simple"

    def _is_rich_billing_format(self, spec: Dict) -> bool:
        """Check if spec is rich billing format."""
        return (
            "project" in spec and
            isinstance(spec.get("project"), dict) and
            any(key in spec for key in ["llms", "agents", "orchestration"])
        )

    def _is_legacy_techstack_format(self, spec: Dict) -> bool:
        """Check if spec is legacy format with tech_stack."""
        return (
            "requirements" in spec and
            isinstance(spec.get("requirements"), list) and
            "tech_stack" in spec
        )

    def _is_simple_format(self, spec: Dict) -> bool:
        """Check if spec is simple requirements list."""
        return "requirements" in spec and isinstance(spec.get("requirements"), list)

    # =========================================================================
    # RICH BILLING FORMAT NORMALIZER
    # =========================================================================

    def _normalize_rich_billing(self, spec: Dict) -> NormalizedSpec:
        """Normalize rich billing spec format."""
        project = spec.get("project", {})

        # Extract requirements from multiple sources
        requirements = []
        req_counter = 0

        # 1. From requirements.imported_requirements
        imported = spec.get("requirements", {}).get("imported_requirements", [])
        for req in imported:
            requirements.append(self._convert_imported_requirement(req, req_counter))
            req_counter += 1

        # 2. From requirements.autonomy_requirements
        autonomy = spec.get("requirements", {}).get("autonomy_requirements", [])
        for req in autonomy:
            if "id" in req:  # Named requirement
                requirements.append(self._convert_autonomy_requirement(req, req_counter))
                req_counter += 1
            elif "path" in req:  # API endpoint definition - extract as requirement
                requirements.append(self._api_to_requirement(req, req_counter))
                req_counter += 1

        # 3. From frontend_requirements (generate requirements from structure)
        frontend_reqs = project.get("frontend_requirements", {})
        for domain, domain_spec in frontend_reqs.items():
            if isinstance(domain_spec, dict):
                for feature, feature_spec in domain_spec.items():
                    if isinstance(feature_spec, dict) and "description" in feature_spec:
                        requirements.append(Requirement(
                            req_id=f"REQ-FE-{req_counter:03d}",
                            title=feature_spec.get("description", feature),
                            description=self._extract_feature_description(feature_spec),
                            tag="functional",
                            source=f"frontend_requirements.{domain}.{feature}",
                        ))
                        req_counter += 1

        # Extract context layers
        context = ContextLayers(
            api_specs=self._extract_api_specs(spec),
            db_schema=self._extract_db_schema(spec),
            llm_config=spec.get("llms", {}),
            agent_defs=self._extract_agent_defs(spec),
            workflows=self._extract_workflows(spec),
            frontend_specs=frontend_reqs,
            monitoring_config=spec.get("monitoring", {}),
        )

        # Detect tech stack from spec
        tech_stack = self._infer_tech_stack(spec)

        return NormalizedSpec(
            project_name=project.get("name", "Unnamed Project"),
            project_description=project.get("description", ""),
            requirements=requirements,
            tech_stack=tech_stack,
            context_layers=context,
            raw_spec=spec,
        )

    def _convert_imported_requirement(self, req: Dict, idx: int) -> Requirement:
        """Convert imported requirement to normalized format."""
        return Requirement(
            req_id=req.get("id", f"REQ-IMP-{idx:03d}"),
            title=req.get("title", req.get("text", "")),
            description=req.get("text", ""),
            tag=req.get("category", "functional"),
            source=req.get("source_file", ""),
        )

    def _convert_autonomy_requirement(self, req: Dict, idx: int) -> Requirement:
        """Convert autonomy requirement to normalized format."""
        return Requirement(
            req_id=req.get("id", f"REQ-AUTO-{idx:03d}"),
            title=req.get("title", ""),
            description=req.get("text", ""),
            tag=req.get("category", "autonomy"),
            source=req.get("source_file", ""),
        )

    def _api_to_requirement(self, api_spec: Dict, idx: int) -> Requirement:
        """Convert inline API spec to requirement."""
        method = api_spec.get("method", "GET")
        path = api_spec.get("path", "/unknown")
        return Requirement(
            req_id=f"REQ-API-{idx:03d}",
            title=f"API Endpoint: {method} {path}",
            description=api_spec.get("description", ""),
            tag="functional",
            source="api_definition",
        )

    def _extract_feature_description(self, feature_spec: Dict) -> str:
        """Extract detailed description from feature spec."""
        parts = []

        if "fields" in feature_spec:
            parts.append(f"Fields: {', '.join(feature_spec['fields'])}")

        if "features" in feature_spec:
            parts.append(f"Features: {', '.join(feature_spec['features'])}")

        if "validation_rules" in feature_spec:
            parts.append(f"Validation: {', '.join(feature_spec['validation_rules'])}")

        if "security_measures" in feature_spec:
            parts.append(f"Security: {', '.join(feature_spec['security_measures'])}")

        return " | ".join(parts)

    def _extract_api_specs(self, spec: Dict) -> List[APIEndpoint]:
        """Extract API endpoints from spec."""
        endpoints = []

        # From autonomy_requirements inline API definitions
        autonomy = spec.get("requirements", {}).get("autonomy_requirements", [])
        for item in autonomy:
            if "path" in item and "method" in item:
                endpoints.append(APIEndpoint(
                    path=item["path"],
                    method=item["method"],
                    description=item.get("description", ""),
                    request_schema=item.get("parameters", {}).get("body"),
                    response_schema=item.get("responses", {}),
                    auth_required=item.get("security", {}).get("authentication") is not None,
                ))

        # From data_persistence.api_endpoints
        persistence = spec.get("project", {}).get("frontend_requirements", {}).get("data_persistence", {})
        api_endpoints = persistence.get("api_endpoints", {})
        for entity, methods in api_endpoints.items():
            if isinstance(methods, dict):
                for method_name, endpoint in methods.items():
                    if isinstance(endpoint, str) and " " in endpoint:
                        method, path = endpoint.split(" ", 1)
                        endpoints.append(APIEndpoint(
                            path=path,
                            method=method,
                            description=f"{entity} {method_name}",
                        ))

        return endpoints

    def _extract_db_schema(self, spec: Dict) -> Dict:
        """Extract database schema from spec."""
        persistence = spec.get("project", {}).get("frontend_requirements", {}).get("data_persistence", {})
        db_design = persistence.get("database_design", {})

        return {
            "tables": db_design.get("user_data_tables", []),
            "integrity": db_design.get("data_integrity", {}),
        }

    def _extract_agent_defs(self, spec: Dict) -> List[Dict]:
        """Extract agent definitions from spec."""
        agents = spec.get("agents", {})
        return agents.get("types", [])

    def _extract_workflows(self, spec: Dict) -> List[Dict]:
        """Extract workflow definitions from spec."""
        orchestration = spec.get("orchestration", {})
        n8n = orchestration.get("n8n_integration", {})
        return n8n.get("workflows", [])

    def _infer_tech_stack(self, spec: Dict) -> Dict:
        """Infer tech stack from spec content."""
        # Default React/FastAPI stack
        tech_stack = {
            "id": "web_app_react",
            "name": "React + FastAPI",
            "frontend": {"framework": "React", "language": "TypeScript"},
            "backend": {"framework": "FastAPI", "language": "Python"},
            "database": {"type": "PostgreSQL"},
            "deployment": {"platform": "Docker"},
        }

        # Check for n8n workflows -> add n8n to stack
        if spec.get("orchestration", {}).get("n8n_integration"):
            tech_stack["workflow_engine"] = {"platform": "n8n"}

        # Check for autogen groups -> add autogen
        if spec.get("orchestration", {}).get("autogen_integration"):
            tech_stack["ai_framework"] = {"platform": "autogen"}

        return tech_stack

    # =========================================================================
    # DOCUMENTATION FORMAT NORMALIZER
    # =========================================================================

    def _try_structured_parse(self, project_path: Path) -> Optional["NormalizedSpec"]:
        """Attempt to parse using SpecParser if directory has architecture/ and api/ subdirs.

        Returns a NormalizedSpec built from the structured SpecParser output, or None
        if the directory does not match the expected structure or parsing fails.
        """
        has_architecture = (project_path / "architecture").is_dir()
        has_api = (project_path / "api").is_dir()
        if not (has_architecture and has_api):
            return None

        try:
            from src.engine.spec_parser import SpecParser
            parsed = SpecParser(project_path).parse()

            requirements = []
            req_counter = 0
            for svc_name, svc in parsed.services.items():
                for story in svc.stories:
                    for req_id in story.linked_requirements:
                        requirements.append(Requirement(
                            req_id=req_id,
                            title=story.title,
                            description=story.description,
                            tag="functional",
                            source=f"service:{svc_name}",
                        ))
                        req_counter += 1
                for ep in svc.endpoints:
                    if not any(r.req_id == f"EP-{ep.method}-{ep.path}" for r in requirements):
                        requirements.append(Requirement(
                            req_id=f"EP-{ep.method}-{ep.path}",
                            title=f"{ep.method} {ep.path}",
                            description=f"API endpoint for {svc_name}",
                            tag="functional",
                            source=f"service:{svc_name}",
                        ))

            tech_stack = {
                "id": "nestjs_structured",
                "name": "NestJS Microservices",
                "backend": {"framework": "NestJS", "language": "TypeScript"},
                "database": {"type": "PostgreSQL", "orm": "Prisma"},
                "deployment": {"platform": "Docker"},
            }

            logger.info(
                "structured_parse_succeeded",
                services=len(parsed.services),
                requirements=len(requirements),
                path=str(project_path),
            )

            return NormalizedSpec(
                project_name=parsed.project_name,
                project_description=f"Structured spec with {len(parsed.services)} services",
                requirements=requirements,
                tech_stack=tech_stack,
                context_layers=ContextLayers(),
                raw_spec={"format": "structured", "path": str(project_path)},
            )
        except Exception as e:
            logger.debug("structured_parse_failed", error=str(e), path=str(project_path))
            return None

    def _normalize_documentation(self, project_path: Path) -> NormalizedSpec:
        """
        Normalize documentation format project to internal format.

        Loads all structured documentation and converts to NormalizedSpec:
        - User stories → Requirements
        - Epics → Grouped requirements with dependencies
        - Data dictionary → DB schema context
        - API docs → API specs context
        - Diagrams → Workflow context
        """
        # Attempt structured parse first (SpecParser — faster, machine-readable)
        structured = self._try_structured_parse(project_path)
        if structured is not None:
            return structured

        loader = _get_documentation_loader()
        doc_spec = loader.load(project_path)

        # Convert user stories and epic requirements to Requirements
        requirements = []
        req_counter = 0

        # Add requirements from epics
        for epic in doc_spec.epics:
            for req_id in epic.linked_requirements:
                requirements.append(Requirement(
                    req_id=req_id,
                    title=f"[{epic.epic_id}] {req_id}",
                    description=f"Part of: {epic.title} - {epic.description}",
                    tag="functional",
                    priority="high" if "AUTH" in req_id or "SEC" in req_id else "medium",
                    source=f"epic:{epic.epic_id}",
                ))
                req_counter += 1

        # Add requirements from user stories
        for story in doc_spec.user_stories:
            requirements.append(Requirement(
                req_id=story.story_id,
                title=story.title,
                description=story.description,
                tag="functional",
                source=f"epic:{story.epic_id}" if story.epic_id else "user_story",
            ))

        # Convert tech stack to internal format
        tech_stack = {
            "id": "documentation_stack",
            "name": doc_spec.tech_stack.project_name,
            "frontend": {
                "framework": doc_spec.tech_stack.frontend_framework,
                "languages": doc_spec.tech_stack.frontend_languages,
                "ui_library": doc_spec.tech_stack.ui_library,
                "state_management": doc_spec.tech_stack.state_management,
            },
            "backend": {
                "language": doc_spec.tech_stack.backend_language,
                "framework": doc_spec.tech_stack.backend_framework,
                "api_style": doc_spec.tech_stack.api_style,
            },
            "database": {
                "type": doc_spec.tech_stack.primary_database,
                "cache": doc_spec.tech_stack.cache_layer,
            },
            "infrastructure": {
                "cloud_provider": doc_spec.tech_stack.cloud_provider,
                "container_runtime": doc_spec.tech_stack.container_runtime,
                "orchestration": doc_spec.tech_stack.orchestration,
                "message_queue": doc_spec.tech_stack.message_queue,
            },
            "deployment": {
                "platform": doc_spec.tech_stack.container_runtime or "Docker",
                "ci_cd": doc_spec.tech_stack.ci_cd,
            },
        }

        # Convert API endpoints
        api_specs = []
        for endpoint in doc_spec.api_endpoints:
            api_specs.append(APIEndpoint(
                path=endpoint.get("path", ""),
                method=endpoint.get("method", "GET"),
                description=endpoint.get("description", ""),
                auth_required=endpoint.get("auth_required", True),
            ))

        # Build context layers with all documentation data
        context = ContextLayers(
            api_specs=api_specs,
            db_schema={
                "entities": [e.to_dict() for e in doc_spec.entities],
                "relations": doc_spec.entity_relations,
            },
            diagrams=[d.to_dict() for d in doc_spec.diagrams],
            entities=[e.to_dict() for e in doc_spec.entities],
            epics=[e.to_dict() for e in doc_spec.epics],
            design_tokens=doc_spec.design_tokens.to_dict(),
            features=[f.to_dict() for f in doc_spec.features],
            frontend_specs=doc_spec.design_tokens.to_dict(),
        )

        logger.info(
            "documentation_normalized",
            requirements=len(requirements),
            epics=len(doc_spec.epics),
            entities=len(doc_spec.entities),
            diagrams=len(doc_spec.diagrams),
            api_endpoints=len(api_specs),
        )

        return NormalizedSpec(
            project_name=doc_spec.project_name,
            project_description=doc_spec.master_document[:500] if doc_spec.master_document else "",
            requirements=requirements,
            tech_stack=tech_stack,
            context_layers=context,
            raw_spec={
                "format": "documentation",
                "path": str(project_path),
                "epic_count": len(doc_spec.epics),
                "diagram_count": len(doc_spec.diagrams),
            },
        )

    # =========================================================================
    # LEGACY FORMAT NORMALIZER
    # =========================================================================

    def _normalize_legacy_techstack(self, spec: Dict) -> NormalizedSpec:
        """Normalize legacy format with tech_stack."""
        requirements = []

        for req in spec.get("requirements", []):
            requirements.append(Requirement(
                req_id=req.get("req_id", f"REQ-{len(requirements):03d}"),
                title=req.get("title", ""),
                description=req.get("description", req.get("title", "")),
                tag=req.get("tag", "functional"),
                evidence_refs=req.get("evidence_refs", []),
            ))

        meta = spec.get("meta", {})

        return NormalizedSpec(
            project_name=meta.get("project_name", meta.get("source_file", "Unnamed")),
            project_description=meta.get("description", ""),
            requirements=requirements,
            tech_stack=spec.get("tech_stack", {}),
            context_layers=ContextLayers(),  # No rich context in legacy format
            raw_spec=spec,
        )

    # =========================================================================
    # SIMPLE FORMAT NORMALIZER
    # =========================================================================

    def _normalize_simple(self, spec: Dict) -> NormalizedSpec:
        """Normalize simple requirements list format."""
        requirements = []

        raw_reqs = spec.get("requirements", [])
        if isinstance(raw_reqs, list):
            for i, req in enumerate(raw_reqs):
                if isinstance(req, str):
                    requirements.append(Requirement(
                        req_id=f"REQ-{i:03d}",
                        title=req,
                    ))
                elif isinstance(req, dict):
                    requirements.append(Requirement(
                        req_id=req.get("req_id", req.get("id", f"REQ-{i:03d}")),
                        title=req.get("title", req.get("name", "")),
                        description=req.get("description", req.get("text", "")),
                        tag=req.get("tag", req.get("category", "functional")),
                    ))

        return NormalizedSpec(
            project_name=spec.get("name", spec.get("project_name", "Unnamed")),
            project_description=spec.get("description", ""),
            requirements=requirements,
            tech_stack=spec.get("tech_stack", self._default_tech_stack()),
            context_layers=ContextLayers(),
            raw_spec=spec,
        )

    def _default_tech_stack(self) -> Dict:
        """Return default tech stack."""
        return {
            "id": "web_app_react",
            "name": "Default Stack",
            "frontend": {"framework": "React", "language": "TypeScript"},
            "backend": {"framework": "FastAPI", "language": "Python"},
            "database": {"type": "PostgreSQL"},
            "deployment": {"platform": "Docker"},
        }


# =============================================================================
# CONTEXT PROVIDER - Generates agent-specific context from layers
# =============================================================================

class ContextProvider:
    """
    Provides relevant context from NormalizedSpec to different agents.

    Usage:
        provider = ContextProvider(normalized_spec)

        # For ArchitectAgent - gets API specs and DB schema
        arch_context = provider.for_architect()

        # For GeneratorAgent - gets relevant code context
        gen_context = provider.for_generator(requirement_id="REQ-API-001")
    """

    def __init__(self, spec: NormalizedSpec):
        self.spec = spec

    def for_architect(self) -> Dict:
        """Context for ArchitectAgent - API design, DB schema."""
        return {
            "api_endpoints": [e.to_dict() for e in self.spec.context_layers.api_specs],
            "db_schema": self.spec.context_layers.db_schema,
            "frontend_specs": self.spec.context_layers.frontend_specs,
        }

    def for_database_agent(self) -> Dict:
        """Context for DatabaseAgent - schema details."""
        return {
            "tables": self.spec.context_layers.db_schema.get("tables", []),
            "integrity": self.spec.context_layers.db_schema.get("integrity", {}),
        }

    def for_api_agent(self) -> Dict:
        """Context for APIAgent - endpoint definitions."""
        return {
            "endpoints": [e.to_dict() for e in self.spec.context_layers.api_specs],
        }

    def for_generator(self, requirement_id: Optional[str] = None) -> Dict:
        """Context for GeneratorAgent - relevant specs for requirement."""
        context = {
            "project_name": self.spec.project_name,
            "tech_stack": self.spec.tech_stack,
        }

        if requirement_id:
            # Find related API endpoints
            for endpoint in self.spec.context_layers.api_specs:
                if requirement_id in endpoint.description or requirement_id.lower() in endpoint.path.lower():
                    context.setdefault("related_endpoints", []).append(endpoint.to_dict())

        return context

    def for_validation(self) -> Dict:
        """Context for ValidationAgent - all specs for completeness check."""
        return {
            "requirements": [r.to_dict() for r in self.spec.requirements],
            "api_endpoints": [e.to_dict() for e in self.spec.context_layers.api_specs],
            "expected_tables": [t.get("name") for t in self.spec.context_layers.db_schema.get("tables", [])],
        }

    def get_llm_config(self, task_type: str) -> Optional[Dict]:
        """Get LLM configuration for a specific task type."""
        llm_config = self.spec.context_layers.llm_config
        if not llm_config:
            return None

        # Check routing strategy
        routing = llm_config.get("routing_strategy", {}).get("rule_based", {})

        # Map task types to routing keys
        task_mapping = {
            "code_generation": "standard_invoice_generation",
            "complex_analysis": "complex_financial_calculations",
            "communication": "customer_communication",
            "planning": "strategic_planning",
        }

        routing_key = task_mapping.get(task_type)
        if routing_key and routing_key in routing:
            model_name = routing[routing_key]
            # Find model config
            for model in llm_config.get("models", []):
                if model.get("name") == model_name:
                    return model

        return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def load_spec(path: Union[str, Path]) -> NormalizedSpec:
    """Load and normalize a spec file."""
    return SpecAdapter().load(path)


def normalize_spec(raw_spec: Dict) -> NormalizedSpec:
    """Normalize a raw spec dict."""
    return SpecAdapter().normalize(raw_spec)
