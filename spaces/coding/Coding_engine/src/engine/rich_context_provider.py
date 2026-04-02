"""
Rich Context Provider - Provides agent-specific context from DocumentationSpec.

Extends the basic ContextProvider to handle rich documentation data including:
- Mermaid diagrams (sequence, C4, flowchart, etc.)
- Entity definitions with relationships
- Epic-grouped requirements
- Design tokens for frontend
- Feature breakdowns

Usage:
    from src.engine.documentation_loader import DocumentationLoader
    from src.engine.rich_context_provider import RichContextProvider

    doc_spec = DocumentationLoader().load(project_path)
    provider = RichContextProvider(doc_spec)

    # Get context for database agent
    db_context = provider.for_database_agent()

    # Get context for specific epic
    epic_context = provider.for_epic("EPIC-001")

    # Get relevant diagrams for a feature
    diagrams = provider.get_diagrams_for_feature("authentication")
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from src.engine.documentation_loader import DocumentationSpec, Diagram, Entity

logger = structlog.get_logger(__name__)


@dataclass
class AgentContext:
    """Context bundle for agent execution."""
    tech_stack: Dict[str, Any]
    requirements: List[Dict]
    diagrams: List[Dict]
    entities: List[Dict]
    design_tokens: Dict
    api_endpoints: List[Dict]
    epic_info: Optional[Dict] = None
    feature_info: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            "tech_stack": self.tech_stack,
            "requirements_count": len(self.requirements),
            "diagrams_count": len(self.diagrams),
            "entities_count": len(self.entities),
            "has_design_tokens": bool(self.design_tokens),
            "api_endpoints_count": len(self.api_endpoints),
            "epic": self.epic_info.get("epic_id") if self.epic_info else None,
        }

    def get_prompt_context(self, max_diagrams: int = 3, max_entities: int = 10) -> str:
        """Generate a prompt-friendly context string."""
        parts = []

        # Tech stack summary
        parts.append("## Tech Stack")
        if self.tech_stack:
            be = self.tech_stack.get("backend", {})
            fe = self.tech_stack.get("frontend", {})
            db = self.tech_stack.get("database", {})
            parts.append(f"- Backend: {be.get('framework', 'N/A')} ({be.get('language', 'N/A')})")
            parts.append(f"- Frontend: {fe.get('framework', 'N/A')}")
            parts.append(f"- Database: {db.get('type', db.get('primary', 'N/A'))}")

        # Requirements
        if self.requirements:
            parts.append(f"\n## Requirements ({len(self.requirements)})")
            for req in self.requirements[:10]:
                parts.append(f"- **{req.get('req_id', 'N/A')}**: {req.get('title', 'Untitled')}")

        # Entities
        if self.entities:
            parts.append(f"\n## Data Entities ({len(self.entities)})")
            for entity in self.entities[:max_entities]:
                attrs = entity.get("attributes", [])
                attr_names = [a.get("name", "") for a in attrs[:5]]
                parts.append(f"- **{entity.get('name', 'Unknown')}**: {', '.join(attr_names)}")

        # Diagrams
        if self.diagrams:
            parts.append(f"\n## Relevant Diagrams ({len(self.diagrams)})")
            for diagram in self.diagrams[:max_diagrams]:
                dtype = diagram.get("diagram_type", "unknown")
                title = diagram.get("title", "Untitled")
                content = diagram.get("content", "")[:300]
                parts.append(f"\n### {title} ({dtype})")
                parts.append(f"```mermaid\n{content}\n```")

        return "\n".join(parts)


class RichContextProvider:
    """
    Provides rich context from DocumentationSpec to different agents.

    Extracts relevant subsets of documentation data based on:
    - Agent type (database, api, frontend, etc.)
    - Epic scope
    - Feature requirements
    - Diagram relevance
    """

    def __init__(self, doc_spec: "DocumentationSpec"):
        self.doc_spec = doc_spec
        self._diagram_index = self._build_diagram_index()
        self._entity_index = self._build_entity_index()

    def _build_diagram_index(self) -> Dict[str, List[int]]:
        """Build an index of diagrams by type and keywords."""
        index: Dict[str, List[int]] = {}

        for i, diagram in enumerate(self.doc_spec.diagrams):
            # Index by type
            dtype = diagram.diagram_type.lower()
            index.setdefault(f"type:{dtype}", []).append(i)

            # Index by title keywords
            if diagram.title:
                for word in diagram.title.lower().split():
                    if len(word) > 3:
                        index.setdefault(f"kw:{word}", []).append(i)

            # Index by content keywords (limited)
            content_lower = diagram.content.lower()
            for keyword in ["auth", "user", "message", "group", "call", "status", "backup"]:
                if keyword in content_lower:
                    index.setdefault(f"kw:{keyword}", []).append(i)

        return index

    def _build_entity_index(self) -> Dict[str, int]:
        """Build an index of entities by name and requirements."""
        index: Dict[str, int] = {}

        for i, entity in enumerate(self.doc_spec.entities):
            index[entity.name.lower()] = i
            for req_id in entity.source_requirements:
                index.setdefault(f"req:{req_id}", [])
                if isinstance(index[f"req:{req_id}"], int):
                    index[f"req:{req_id}"] = [index[f"req:{req_id}"]]
                index[f"req:{req_id}"].append(i)

        return index

    def for_architect(self) -> Dict:
        """
        Context for ArchitectAgent — API design, DB schema, frontend specs.

        Returns a plain Dict (not AgentContext) to match the interface
        expected by HybridPipeline.run() and ContextProvider.for_architect().
        """
        return {
            "api_endpoints": self.doc_spec.api_endpoints,
            "db_schema": {
                "entities": [e.to_dict() for e in self.doc_spec.entities],
            },
            "frontend_specs": self.doc_spec.design_tokens.to_dict()
                if self.doc_spec.design_tokens else {},
        }

    def for_database_agent(self) -> AgentContext:
        """Get context for DatabaseAgent - schema, entities, ER diagrams."""
        # Get ER and class diagrams
        diagrams = self._get_diagrams_by_types(["erDiagram", "classDiagram"])

        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict(),
            requirements=self._get_requirements_for_domain("database"),
            diagrams=[d.to_dict() for d in diagrams],
            entities=[e.to_dict() for e in self.doc_spec.entities],
            design_tokens={},
            api_endpoints=[],
        )

    def for_api_agent(self) -> AgentContext:
        """Get context for APIAgent - endpoints, sequence diagrams."""
        diagrams = self._get_diagrams_by_types(["sequence", "flowchart"])

        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict(),
            requirements=self._get_requirements_for_domain("api"),
            diagrams=[d.to_dict() for d in diagrams[:10]],  # Limit
            entities=[e.to_dict() for e in self.doc_spec.entities],
            design_tokens={},
            api_endpoints=self.doc_spec.api_endpoints,
        )

    def for_auth_agent(self) -> AgentContext:
        """Get context for AuthAgent - security requirements, auth flows."""
        auth_diagrams = self._get_diagrams_for_keywords(["auth", "login", "security", "token"])

        auth_reqs = []
        for epic in self.doc_spec.epics:
            if "auth" in epic.title.lower() or "security" in epic.title.lower():
                for req_id in epic.linked_requirements:
                    auth_reqs.append({"req_id": req_id, "epic": epic.epic_id})

        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict(),
            requirements=auth_reqs,
            diagrams=[d.to_dict() for d in auth_diagrams],
            entities=self._get_entities_for_keywords(["user", "auth", "session", "token"]),
            design_tokens={},
            api_endpoints=[ep for ep in self.doc_spec.api_endpoints if "auth" in ep.get("path", "").lower()],
        )

    def for_frontend_agent(self) -> AgentContext:
        """Get context for frontend agents - design tokens, UI components."""
        ui_diagrams = self._get_diagrams_by_types(["stateDiagram", "flowchart"])

        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict(),
            requirements=self._get_requirements_for_domain("frontend"),
            diagrams=[d.to_dict() for d in ui_diagrams[:5]],
            entities=[],
            design_tokens=self.doc_spec.design_tokens.to_dict(),
            api_endpoints=[],
        )

    def for_websocket_agent(self) -> AgentContext:
        """Get context for WebSocketAgent - real-time, messaging diagrams."""
        ws_diagrams = self._get_diagrams_for_keywords(
            ["message", "realtime", "websocket", "chat", "notification"]
        )

        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict(),
            requirements=self._get_requirements_for_domain("messaging"),
            diagrams=[d.to_dict() for d in ws_diagrams],
            entities=self._get_entities_for_keywords(["message", "chat", "notification"]),
            design_tokens={},
            api_endpoints=[],
        )

    def for_epic(self, epic_id: str) -> AgentContext:
        """Get context for a specific epic."""
        epic = None
        for e in self.doc_spec.epics:
            if e.epic_id == epic_id:
                epic = e
                break

        if not epic:
            logger.warning("epic_not_found", epic_id=epic_id)
            return self._empty_context()

        # Get requirements for this epic
        requirements = [{"req_id": req_id, "epic": epic_id} for req_id in epic.linked_requirements]

        # Get diagrams matching epic keywords
        keywords = epic.title.lower().split()[:3]  # First 3 words of title
        diagrams = self._get_diagrams_for_keywords(keywords)

        # Get entities for epic requirements
        entities = self._get_entities_for_requirements(epic.linked_requirements)

        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict(),
            requirements=requirements,
            diagrams=[d.to_dict() for d in diagrams],
            entities=entities,
            design_tokens={},
            api_endpoints=[],
            epic_info={
                "epic_id": epic.epic_id,
                "title": epic.title,
                "description": epic.description,
                "user_stories": epic.user_stories,
            },
        )

    def for_generator(
        self,
        requirement_ids: Optional[List[str]] = None,
        epic_id: Optional[str] = None,
        max_diagrams: int = 5,
    ) -> AgentContext:
        """Get context for GeneratorAgent with optional filtering."""
        if epic_id:
            return self.for_epic(epic_id)

        requirements = []
        if requirement_ids:
            for epic in self.doc_spec.epics:
                for req_id in epic.linked_requirements:
                    if req_id in requirement_ids:
                        requirements.append({"req_id": req_id, "epic": epic.epic_id, "title": epic.title})

        # Get relevant diagrams based on requirements
        diagrams = []
        if requirement_ids:
            entities = self._get_entities_for_requirements(requirement_ids)
            for entity in entities:
                entity_diagrams = self._get_diagrams_for_keywords([entity.get("name", "").lower()])
                diagrams.extend(entity_diagrams)
        else:
            diagrams = self._get_diagrams_by_types(["sequence", "flowchart"])[:max_diagrams]

        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict(),
            requirements=requirements,
            diagrams=[d.to_dict() for d in diagrams[:max_diagrams]],
            entities=self._get_entities_for_requirements(requirement_ids or []),
            design_tokens=self.doc_spec.design_tokens.to_dict(),
            api_endpoints=self.doc_spec.api_endpoints[:20],
        )

    def get_diagrams_for_feature(self, feature_name: str) -> List["Diagram"]:
        """Get all diagrams related to a feature name."""
        return self._get_diagrams_for_keywords([feature_name.lower()])

    def get_all_sequence_diagrams(self) -> List["Diagram"]:
        """Get all sequence diagrams for API flow understanding."""
        return self._get_diagrams_by_types(["sequence"])

    def get_all_er_diagrams(self) -> List["Diagram"]:
        """Get all ER diagrams for database understanding."""
        return self._get_diagrams_by_types(["erDiagram", "classDiagram"])

    def _get_diagrams_by_types(self, types: List[str]) -> List["Diagram"]:
        """Get diagrams of specified types."""
        result = []
        for dtype in types:
            indices = self._diagram_index.get(f"type:{dtype.lower()}", [])
            for idx in indices:
                if idx < len(self.doc_spec.diagrams):
                    result.append(self.doc_spec.diagrams[idx])
        return result

    def _get_diagrams_for_keywords(self, keywords: List[str]) -> List["Diagram"]:
        """Get diagrams matching any of the keywords."""
        result_indices = set()
        for kw in keywords:
            indices = self._diagram_index.get(f"kw:{kw.lower()}", [])
            result_indices.update(indices)

        return [
            self.doc_spec.diagrams[idx]
            for idx in sorted(result_indices)
            if idx < len(self.doc_spec.diagrams)
        ]

    def _get_entities_for_keywords(self, keywords: List[str]) -> List[Dict]:
        """Get entities matching any of the keywords."""
        result = []
        for entity in self.doc_spec.entities:
            entity_text = (entity.name + " " + entity.description).lower()
            if any(kw.lower() in entity_text for kw in keywords):
                result.append(entity.to_dict())
        return result

    def _get_entities_for_requirements(self, req_ids: List[str]) -> List[Dict]:
        """Get entities linked to specific requirements."""
        result = []
        for entity in self.doc_spec.entities:
            if any(req_id in entity.source_requirements for req_id in req_ids):
                result.append(entity.to_dict())
        return result

    def _get_requirements_for_domain(self, domain: str) -> List[Dict]:
        """Get requirements related to a domain."""
        domain_keywords = {
            "database": ["database", "db", "schema", "table", "entity", "model"],
            "api": ["api", "endpoint", "route", "rest", "http"],
            "frontend": ["ui", "component", "page", "view", "design"],
            "messaging": ["message", "chat", "send", "receive", "notification"],
            "auth": ["auth", "login", "security", "permission", "role"],
        }

        keywords = domain_keywords.get(domain.lower(), [domain.lower()])
        result = []

        for epic in self.doc_spec.epics:
            epic_text = (epic.title + " " + epic.description).lower()
            if any(kw in epic_text for kw in keywords):
                for req_id in epic.linked_requirements:
                    result.append({
                        "req_id": req_id,
                        "epic": epic.epic_id,
                        "epic_title": epic.title,
                    })

        return result

    def _empty_context(self) -> AgentContext:
        """Return an empty context."""
        return AgentContext(
            tech_stack=self.doc_spec.tech_stack.to_dict() if self.doc_spec.tech_stack else {},
            requirements=[],
            diagrams=[],
            entities=[],
            design_tokens={},
            api_endpoints=[],
        )
