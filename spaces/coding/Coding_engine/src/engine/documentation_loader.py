"""
Documentation Loader - Parses Rich Documentation Format from project directories.

Supports loading structured documentation projects containing:
- MASTER_DOCUMENT.md - Central requirements specification
- tech_stack/tech_stack.json - Technology stack configuration
- user_stories/user_stories.md - Epics and user stories
- data/data_dictionary.md - Entity definitions
- api/api_documentation.md - API endpoint documentation
- diagrams/ - Mermaid diagrams (C4, sequence, flowchart, etc.)
- ui_design/design_tokens.json - Design system tokens
- work_breakdown/feature_breakdown.json - Feature groupings
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Entity:
    """Database entity definition."""
    name: str
    description: str
    source_requirements: List[str]
    attributes: List[Dict[str, Any]]

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "source_requirements": self.source_requirements,
            "attributes": self.attributes,
        }


@dataclass
class Epic:
    """Epic definition with linked requirements and user stories."""
    epic_id: str
    title: str
    description: str
    status: str
    linked_requirements: List[str]
    user_stories: List[str]

    def to_dict(self) -> Dict:
        return {
            "epic_id": self.epic_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "linked_requirements": self.linked_requirements,
            "user_stories": self.user_stories,
        }


@dataclass
class UserStory:
    """User story definition."""
    story_id: str
    title: str
    description: str
    epic_id: str
    acceptance_criteria: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "story_id": self.story_id,
            "title": self.title,
            "description": self.description,
            "epic_id": self.epic_id,
            "acceptance_criteria": self.acceptance_criteria,
        }


@dataclass
class Feature:
    """Feature grouping from work breakdown."""
    feature_id: str
    feature_name: str
    description: str
    requirements: List[str]
    priority: str
    complexity: str
    dependencies: List[str]

    def to_dict(self) -> Dict:
        return {
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
            "description": self.description,
            "requirements": self.requirements,
            "priority": self.priority,
            "complexity": self.complexity,
            "dependencies": self.dependencies,
        }


@dataclass
class Diagram:
    """Mermaid diagram definition."""
    diagram_type: str  # c4, sequence, flowchart, stateDiagram, classDiagram, etc.
    content: str
    related_feature: Optional[str] = None
    title: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "diagram_type": self.diagram_type,
            "content": self.content,
            "related_feature": self.related_feature,
            "title": self.title,
        }


@dataclass
class TechStack:
    """Technology stack configuration."""
    project_name: str
    frontend_framework: str
    frontend_languages: List[str]
    ui_library: str
    state_management: str
    backend_language: str
    backend_framework: str
    api_style: str
    primary_database: str
    cache_layer: str
    cloud_provider: str
    container_runtime: str
    orchestration: str
    ci_cd: str
    message_queue: str
    api_gateway: str
    architecture_pattern: str
    deployment_model: str
    rationale: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "project_name": self.project_name,
            "frontend": {
                "framework": self.frontend_framework,
                "languages": self.frontend_languages,
                "ui_library": self.ui_library,
                "state_management": self.state_management,
            },
            "backend": {
                "language": self.backend_language,
                "framework": self.backend_framework,
                "api_style": self.api_style,
            },
            "database": {
                "primary": self.primary_database,
                "cache": self.cache_layer,
            },
            "infrastructure": {
                "cloud_provider": self.cloud_provider,
                "container_runtime": self.container_runtime,
                "orchestration": self.orchestration,
                "ci_cd": self.ci_cd,
                "message_queue": self.message_queue,
                "api_gateway": self.api_gateway,
            },
            "architecture": {
                "pattern": self.architecture_pattern,
                "deployment_model": self.deployment_model,
            },
            "rationale": self.rationale,
        }


@dataclass
class DesignTokens:
    """UI design system tokens."""
    colors: Dict[str, Any] = field(default_factory=dict)
    typography: Dict[str, Any] = field(default_factory=dict)
    spacing: Dict[str, Any] = field(default_factory=dict)
    breakpoints: Dict[str, Any] = field(default_factory=dict)
    shadows: Dict[str, Any] = field(default_factory=dict)
    borders: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "colors": self.colors,
            "typography": self.typography,
            "spacing": self.spacing,
            "breakpoints": self.breakpoints,
            "shadows": self.shadows,
            "borders": self.borders,
        }


@dataclass
class DocumentationSpec:
    """
    Complete documentation specification loaded from a project directory.

    Contains all structured data extracted from the documentation project:
    - Tech stack configuration
    - Epics and user stories
    - Data entities and relationships
    - API endpoint definitions
    - Mermaid diagrams
    - Design tokens
    - Feature breakdowns
    """
    project_path: Path
    project_name: str
    tech_stack: TechStack
    epics: List[Epic]
    user_stories: List[UserStory]
    entities: List[Entity]
    entity_relations: List[Dict[str, str]]
    features: List[Feature]
    requirement_mapping: Dict[str, str]  # req_id -> feature_id
    diagrams: List[Diagram]
    design_tokens: DesignTokens
    api_endpoints: List[Dict[str, Any]]
    master_document: str
    quality_report: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            "project_name": self.project_name,
            "tech_stack": self.tech_stack.to_dict(),
            "epics": [e.to_dict() for e in self.epics],
            "user_stories": [s.to_dict() for s in self.user_stories],
            "entities": [e.to_dict() for e in self.entities],
            "entity_relations": self.entity_relations,
            "features": [f.to_dict() for f in self.features],
            "requirement_mapping": self.requirement_mapping,
            "diagram_count": len(self.diagrams),
            "api_endpoint_count": len(self.api_endpoints),
            "design_tokens": self.design_tokens.to_dict(),
        }

    def get_requirements_for_epic(self, epic_id: str) -> List[str]:
        """Get all requirement IDs linked to an epic."""
        for epic in self.epics:
            if epic.epic_id == epic_id:
                return epic.linked_requirements
        return []

    def get_diagrams_by_type(self, diagram_type: str) -> List[Diagram]:
        """Get all diagrams of a specific type."""
        return [d for d in self.diagrams if d.diagram_type == diagram_type]

    def get_entities_for_requirements(self, req_ids: List[str]) -> List[Entity]:
        """Get entities that are linked to specific requirements."""
        result = []
        for entity in self.entities:
            if any(req_id in entity.source_requirements for req_id in req_ids):
                result.append(entity)
        return result

    def get_diagrams_for_feature(self, feature_name: str) -> List[Diagram]:
        """Get diagrams related to a feature name."""
        feature_lower = feature_name.lower()
        result = []
        for diagram in self.diagrams:
            if diagram.related_feature and feature_lower in diagram.related_feature.lower():
                result.append(diagram)
            elif diagram.title and feature_lower in diagram.title.lower():
                result.append(diagram)
            elif feature_lower in diagram.content.lower():
                result.append(diagram)
        return result


class DocumentationLoader:
    """
    Loads Rich Documentation Format from a project directory.

    Usage:
        loader = DocumentationLoader()
        doc_spec = loader.load(Path("Data/all_services/unnamed_project_..."))

        # Access structured data
        print(f"Tech Stack: {doc_spec.tech_stack.backend_framework}")
        print(f"Epics: {len(doc_spec.epics)}")
        print(f"Diagrams: {len(doc_spec.diagrams)}")
    """

    def __init__(self):
        self._diagram_type_patterns = {
            "c4": re.compile(r"C4Context|C4Container|C4Component|C4Dynamic", re.IGNORECASE),
            "sequence": re.compile(r"sequenceDiagram", re.IGNORECASE),
            "flowchart": re.compile(r"flowchart\s+(TD|TB|BT|RL|LR)", re.IGNORECASE),
            "stateDiagram": re.compile(r"stateDiagram", re.IGNORECASE),
            "classDiagram": re.compile(r"classDiagram", re.IGNORECASE),
            "erDiagram": re.compile(r"erDiagram", re.IGNORECASE),
            "gantt": re.compile(r"gantt", re.IGNORECASE),
            "pie": re.compile(r"pie\s+title", re.IGNORECASE),
            "journey": re.compile(r"journey", re.IGNORECASE),
            "graph": re.compile(r"graph\s+(TD|TB|BT|RL|LR)", re.IGNORECASE),
        }

    def load(self, project_path: Path) -> DocumentationSpec:
        """Load complete documentation from a project directory."""
        project_path = Path(project_path)

        if not project_path.exists():
            raise FileNotFoundError(f"Documentation project not found: {project_path}")

        logger.info("loading_documentation", path=str(project_path))

        # Load all components
        tech_stack = self._load_tech_stack(project_path)
        epics, user_stories = self._load_user_stories(project_path)
        entities, relations = self._load_data_dictionary(project_path)
        features, req_mapping = self._load_feature_breakdown(project_path)
        diagrams = self._load_diagrams(project_path)
        design_tokens = self._load_design_tokens(project_path)
        api_endpoints = self._load_api_documentation(project_path)
        master_document = self._load_master_document(project_path)
        quality_report = self._load_quality_report(project_path)

        project_name = tech_stack.project_name if tech_stack else project_path.name

        spec = DocumentationSpec(
            project_path=project_path,
            project_name=project_name,
            tech_stack=tech_stack,
            epics=epics,
            user_stories=user_stories,
            entities=entities,
            entity_relations=relations,
            features=features,
            requirement_mapping=req_mapping,
            diagrams=diagrams,
            design_tokens=design_tokens,
            api_endpoints=api_endpoints,
            master_document=master_document,
            quality_report=quality_report,
        )

        logger.info(
            "documentation_loaded",
            epics=len(epics),
            user_stories=len(user_stories),
            entities=len(entities),
            features=len(features),
            diagrams=len(diagrams),
            api_endpoints=len(api_endpoints),
        )

        return spec

    def _load_tech_stack(self, project_path: Path) -> TechStack:
        """Load technology stack from tech_stack.json."""
        tech_stack_path = project_path / "tech_stack" / "tech_stack.json"

        if not tech_stack_path.exists():
            logger.warning("tech_stack_not_found", path=str(tech_stack_path))
            return self._default_tech_stack(project_path.name)

        with open(tech_stack_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return TechStack(
            project_name=data.get("project_name", project_path.name),
            frontend_framework=data.get("frontend_framework", "React"),
            frontend_languages=data.get("frontend_languages", ["TypeScript"]),
            ui_library=data.get("ui_library", ""),
            state_management=data.get("state_management", ""),
            backend_language=data.get("backend_language", "Node.js"),
            backend_framework=data.get("backend_framework", "Express"),
            api_style=data.get("api_style", "REST"),
            primary_database=data.get("primary_database", "PostgreSQL"),
            cache_layer=data.get("cache_layer", "Redis"),
            cloud_provider=data.get("cloud_provider", ""),
            container_runtime=data.get("container_runtime", "Docker"),
            orchestration=data.get("orchestration", ""),
            ci_cd=data.get("ci_cd", ""),
            message_queue=data.get("message_queue", ""),
            api_gateway=data.get("api_gateway", ""),
            architecture_pattern=data.get("architecture_pattern", ""),
            deployment_model=data.get("deployment_model", ""),
            rationale=data.get("rationale", {}),
        )

    def _default_tech_stack(self, project_name: str) -> TechStack:
        """Return default tech stack when not specified."""
        return TechStack(
            project_name=project_name,
            frontend_framework="React",
            frontend_languages=["TypeScript"],
            ui_library="",
            state_management="",
            backend_language="Node.js",
            backend_framework="Express",
            api_style="REST",
            primary_database="PostgreSQL",
            cache_layer="Redis",
            cloud_provider="",
            container_runtime="Docker",
            orchestration="",
            ci_cd="",
            message_queue="",
            api_gateway="",
            architecture_pattern="",
            deployment_model="",
        )

    def _load_user_stories(self, project_path: Path) -> Tuple[List[Epic], List[UserStory]]:
        """Parse user stories and epics from user_stories.md."""
        user_stories_path = project_path / "user_stories" / "user_stories.md"

        if not user_stories_path.exists():
            logger.warning("user_stories_not_found", path=str(user_stories_path))
            return [], []

        with open(user_stories_path, "r", encoding="utf-8") as f:
            content = f.read()

        epics = []
        user_stories = []

        # Parse epics
        epic_pattern = re.compile(
            r"# (EPIC-\d+):\s*(.+?)\n\n\*\*Status:\*\*\s*(\w+)\n\n## Description\n\n(.+?)\n\n## Linked Requirements\n\n((?:- .+\n)+)(?:\n## User Stories\n\n((?:- .+\n)+))?",
            re.MULTILINE | re.DOTALL
        )

        for match in epic_pattern.finditer(content):
            epic_id = match.group(1)
            title = match.group(2).strip()
            status = match.group(3)
            description = match.group(4).strip()

            # Parse linked requirements
            linked_reqs = []
            for line in match.group(5).strip().split("\n"):
                if line.startswith("- "):
                    linked_reqs.append(line[2:].strip())

            # Parse user stories
            story_ids = []
            if match.group(6):
                for line in match.group(6).strip().split("\n"):
                    if line.startswith("- "):
                        story_ids.append(line[2:].strip())

            epics.append(Epic(
                epic_id=epic_id,
                title=title,
                description=description,
                status=status,
                linked_requirements=linked_reqs,
                user_stories=story_ids,
            ))

        # Parse individual user stories
        story_pattern = re.compile(
            r"### (US-\d+):\s*(.+?)\n\n(.+?)(?=\n### US-|\n# EPIC-|\Z)",
            re.MULTILINE | re.DOTALL
        )

        current_epic_id = None
        for match in story_pattern.finditer(content):
            story_id = match.group(1)
            title = match.group(2).strip()
            description = match.group(3).strip()

            # Find which epic this story belongs to
            for epic in epics:
                if story_id in epic.user_stories:
                    current_epic_id = epic.epic_id
                    break

            user_stories.append(UserStory(
                story_id=story_id,
                title=title,
                description=description,
                epic_id=current_epic_id or "",
            ))

        return epics, user_stories

    def _load_data_dictionary(self, project_path: Path) -> Tuple[List[Entity], List[Dict[str, str]]]:
        """Parse entities and relationships from data_dictionary.md."""
        data_dict_path = project_path / "data" / "data_dictionary.md"

        if not data_dict_path.exists():
            logger.warning("data_dictionary_not_found", path=str(data_dict_path))
            return [], []

        with open(data_dict_path, "r", encoding="utf-8") as f:
            content = f.read()

        entities = []
        relations = []

        # Parse entities
        entity_pattern = re.compile(
            r"### (\w+)\n\n(.+?)\n\n\*Source Requirements:\*\s*(.+?)\n\n\| Attribute \| Type \| Required \| Description \|\n\|[-|]+\|\n((?:\| .+? \|.+?\n)+)",
            re.MULTILINE | re.DOTALL
        )

        for match in entity_pattern.finditer(content):
            entity_name = match.group(1)
            description = match.group(2).strip()
            source_reqs = [r.strip() for r in match.group(3).split(",")]

            # Parse attributes
            attributes = []
            attr_lines = match.group(4).strip().split("\n")
            for line in attr_lines:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    attributes.append({
                        "name": parts[0],
                        "type": parts[1],
                        "required": parts[2].lower() == "yes",
                        "description": parts[3] if len(parts) > 3 else "",
                    })

            entities.append(Entity(
                name=entity_name,
                description=description,
                source_requirements=source_reqs,
                attributes=attributes,
            ))

        # Parse relationships section
        rel_pattern = re.compile(
            r"## Relationships\n\n((?:\| .+? \|.+?\n)+)",
            re.MULTILINE
        )
        rel_match = rel_pattern.search(content)
        if rel_match:
            rel_lines = rel_match.group(1).strip().split("\n")
            for line in rel_lines:
                if line.startswith("|---"):
                    continue
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    relations.append({
                        "from_entity": parts[0],
                        "relationship": parts[1],
                        "to_entity": parts[2],
                    })

        return entities, relations

    def _load_feature_breakdown(self, project_path: Path) -> Tuple[List[Feature], Dict[str, str]]:
        """Load feature breakdown from feature_breakdown.json."""
        fb_path = project_path / "work_breakdown" / "feature_breakdown.json"

        if not fb_path.exists():
            logger.warning("feature_breakdown_not_found", path=str(fb_path))
            return [], {}

        with open(fb_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = []
        for feat_id, feat_data in data.get("features", {}).items():
            features.append(Feature(
                feature_id=feat_data.get("feature_id", feat_id),
                feature_name=feat_data.get("feature_name", ""),
                description=feat_data.get("description", ""),
                requirements=feat_data.get("requirements", []),
                priority=feat_data.get("priority", "medium"),
                complexity=feat_data.get("estimated_complexity", "medium"),
                dependencies=feat_data.get("dependencies", []),
            ))

        req_mapping = data.get("requirement_mapping", {})

        return features, req_mapping

    def _load_diagrams(self, project_path: Path) -> List[Diagram]:
        """Load all Mermaid diagrams from content_analysis.json or diagrams directory."""
        diagrams = []

        # First try content_analysis.json (contains indexed diagrams)
        content_analysis_path = project_path / "content_analysis.json"
        if content_analysis_path.exists():
            with open(content_analysis_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            diagram_items = data.get("artifact_summaries", {}).get("diagrams", {}).get("items", [])
            for diagram_content in diagram_items:
                diagram_type = self._detect_diagram_type(diagram_content)
                title = self._extract_diagram_title(diagram_content)
                diagrams.append(Diagram(
                    diagram_type=diagram_type,
                    content=diagram_content,
                    title=title,
                ))

        # Also check diagrams directory for additional diagrams
        diagrams_dir = project_path / "diagrams"
        if diagrams_dir.exists():
            for md_file in diagrams_dir.glob("*.md"):
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Extract mermaid blocks
                mermaid_pattern = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
                for match in mermaid_pattern.finditer(content):
                    diagram_content = match.group(1).strip()
                    diagram_type = self._detect_diagram_type(diagram_content)
                    diagrams.append(Diagram(
                        diagram_type=diagram_type,
                        content=diagram_content,
                        related_feature=md_file.stem,
                    ))

        return diagrams

    def _detect_diagram_type(self, content: str) -> str:
        """Detect the type of a Mermaid diagram."""
        for diagram_type, pattern in self._diagram_type_patterns.items():
            if pattern.search(content):
                return diagram_type
        return "unknown"

    def _extract_diagram_title(self, content: str) -> Optional[str]:
        """Extract title from a Mermaid diagram if present."""
        title_pattern = re.compile(r"title\s+(.+?)(?:\n|$)", re.IGNORECASE)
        match = title_pattern.search(content)
        if match:
            return match.group(1).strip()
        return None

    def _load_design_tokens(self, project_path: Path) -> DesignTokens:
        """Load design tokens from design_tokens.json."""
        tokens_path = project_path / "ui_design" / "design_tokens.json"

        if not tokens_path.exists():
            logger.warning("design_tokens_not_found", path=str(tokens_path))
            return DesignTokens()

        with open(tokens_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return DesignTokens(
            colors=data.get("colors", {}),
            typography=data.get("typography", {}),
            spacing=data.get("spacing", {}),
            breakpoints=data.get("breakpoints", {}),
            shadows=data.get("shadows", {}),
            borders=data.get("borders", data.get("borderRadius", {})),
        )

    def _load_api_documentation(self, project_path: Path) -> List[Dict[str, Any]]:
        """Parse API endpoints from api_documentation.md."""
        api_doc_path = project_path / "api" / "api_documentation.md"

        if not api_doc_path.exists():
            logger.warning("api_documentation_not_found", path=str(api_doc_path))
            return []

        with open(api_doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        endpoints = []

        # Parse API endpoints
        # Pattern: ### METHOD /path
        endpoint_pattern = re.compile(
            r"### (GET|POST|PUT|PATCH|DELETE)\s+(/[^\n]+)\n\n(.+?)(?=\n### |\n## |\Z)",
            re.MULTILINE | re.DOTALL
        )

        for match in endpoint_pattern.finditer(content):
            method = match.group(1)
            path = match.group(2).strip()
            details = match.group(3).strip()

            # Extract description
            desc_match = re.search(r"\*\*Description:\*\*\s*(.+?)(?:\n\n|\n\*\*)", details, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""

            # Extract auth requirement
            auth_match = re.search(r"\*\*Auth:\*\*\s*(\w+)", details)
            auth_required = auth_match.group(1).lower() != "none" if auth_match else True

            endpoints.append({
                "method": method,
                "path": path,
                "description": description,
                "auth_required": auth_required,
            })

        return endpoints

    def _load_master_document(self, project_path: Path) -> str:
        """Load the master document content."""
        master_doc_path = project_path / "MASTER_DOCUMENT.md"

        if not master_doc_path.exists():
            logger.warning("master_document_not_found", path=str(master_doc_path))
            return ""

        with open(master_doc_path, "r", encoding="utf-8") as f:
            return f.read()

    def _load_quality_report(self, project_path: Path) -> Optional[Dict]:
        """Load quality/self-critique report if available."""
        quality_path = project_path / "quality" / "self_critique_report.json"

        if not quality_path.exists():
            return None

        with open(quality_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def is_documentation_project(self, path: Path) -> bool:
        """Check if a path is a documentation format project."""
        path = Path(path)

        # Check for key indicators
        indicators = [
            path / "MASTER_DOCUMENT.md",
            path / "tech_stack" / "tech_stack.json",
            path / "user_stories" / "user_stories.md",
            path / "content_analysis.json",
        ]

        return any(indicator.exists() for indicator in indicators)


def load_documentation(path: Path) -> DocumentationSpec:
    """Convenience function to load documentation from a path."""
    return DocumentationLoader().load(path)
