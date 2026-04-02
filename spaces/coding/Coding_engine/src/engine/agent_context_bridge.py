"""
Agent Context Bridge - Combines static RichContextProvider with dynamic Fungus/RAG search.

This module bridges the gap between:
1. Static context from DocumentationSpec (diagrams, entities, design tokens)
2. Dynamic context from Fungus/RAG semantic search (code patterns, examples)

The AgentContextBridge provides a unified API for agents to retrieve relevant context
for their specific tasks, combining the best of both worlds.

Usage:
    from src.engine.agent_context_bridge import AgentContextBridge
    from src.engine.rich_context_provider import RichContextProvider

    provider = RichContextProvider(doc_spec)
    bridge = AgentContextBridge(provider, fungus_agent=fungus)

    # Get context for database task
    ctx = await bridge.get_context_for_task("database", query="schema entities")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import structlog
import hashlib
import asyncio

if TYPE_CHECKING:
    from src.engine.rich_context_provider import RichContextProvider, AgentContext
    from src.agents.fungus_context_agent import FungusContextAgent

logger = structlog.get_logger(__name__)


@dataclass
class MergedContext:
    """Combined context from static provider and dynamic RAG search."""

    # From RichContextProvider
    tech_stack: Dict[str, Any] = field(default_factory=dict)
    requirements: List[Dict] = field(default_factory=list)
    diagrams: List[Dict] = field(default_factory=list)
    entities: List[Dict] = field(default_factory=list)
    design_tokens: Dict = field(default_factory=dict)
    api_endpoints: List[Dict] = field(default_factory=list)
    epic_info: Optional[Dict] = None
    feature_info: Optional[Dict] = None

    # From Fungus/RAG
    rag_results: List[Dict] = field(default_factory=list)
    code_examples: List[Dict] = field(default_factory=list)

    def get_prompt_context(
        self,
        max_diagrams: int = 3,
        max_entities: int = 10,
        max_rag_results: int = 5,
    ) -> str:
        """Generate a comprehensive prompt-friendly context string."""
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

        # Entities with relationships
        if self.entities:
            parts.append(f"\n## Data Entities ({len(self.entities)})")
            for entity in self.entities[:max_entities]:
                name = entity.get("name", "Unknown")
                description = entity.get("description", "")[:100]
                attrs = entity.get("attributes", [])
                attr_names = [a.get("name", "") for a in attrs[:5]]
                parts.append(f"- **{name}**: {description}")
                if attr_names:
                    parts.append(f"  Attributes: {', '.join(attr_names)}")

        # Diagrams (Mermaid)
        if self.diagrams:
            parts.append(f"\n## Relevant Diagrams ({len(self.diagrams)})")
            for diagram in self.diagrams[:max_diagrams]:
                dtype = diagram.get("diagram_type", "unknown")
                title = diagram.get("title", "Untitled")
                content = diagram.get("content", "")
                # Truncate long diagrams
                if len(content) > 1500:
                    content = content[:1500] + "\n... (truncated)"
                parts.append(f"\n### {title} ({dtype})")
                parts.append(f"```mermaid\n{content}\n```")

        # Design tokens for frontend
        if self.design_tokens:
            parts.append("\n## Design System")
            colors = self.design_tokens.get("colors", {})
            typography = self.design_tokens.get("typography", {})
            spacing = self.design_tokens.get("spacing", {})

            if colors:
                parts.append(f"- Primary: {colors.get('primary', 'N/A')}")
                parts.append(f"- Secondary: {colors.get('secondary', 'N/A')}")
            if typography:
                parts.append(f"- Font: {typography.get('fontFamily', typography.get('font_family', 'N/A'))}")
            if spacing:
                parts.append(f"- Spacing: {spacing}")

        # RAG code examples
        if self.rag_results:
            parts.append(f"\n## Relevant Code Examples ({len(self.rag_results)})")
            for result in self.rag_results[:max_rag_results]:
                file_path = result.get("relative_path", result.get("file_path", "unknown"))
                content = result.get("content", "")[:800]
                score = result.get("score", 0)
                parts.append(f"\n### {file_path} (score: {score:.2f})")
                parts.append(f"```\n{content}\n```")

        return "\n".join(parts)

    def to_dict(self) -> Dict:
        """Return summary dict for logging."""
        return {
            "entities_count": len(self.entities),
            "diagrams_count": len(self.diagrams),
            "rag_results_count": len(self.rag_results),
            "has_design_tokens": bool(self.design_tokens),
            "api_endpoints_count": len(self.api_endpoints),
            "epic": self.epic_info.get("epic_id") if self.epic_info else None,
        }


class AgentContextBridge:
    """
    Bridges RichContextProvider (static) with Fungus/RAG (dynamic) for optimal context delivery.

    Features:
    - Combines documentation-based context (diagrams, entities, design tokens)
    - Adds semantic search results for code patterns
    - Caches results for performance
    - Supports task-type-specific context extraction
    """

    def __init__(
        self,
        context_provider: "RichContextProvider",
        fungus_agent: Optional["FungusContextAgent"] = None,
        enable_rag: bool = True,
        cache_ttl: int = 300,  # 5 minutes
    ):
        """
        Initialize the context bridge.

        Args:
            context_provider: RichContextProvider with loaded DocumentationSpec
            fungus_agent: Optional FungusContextAgent for RAG search
            enable_rag: Whether to enable RAG search (default True)
            cache_ttl: Cache time-to-live in seconds
        """
        self.provider = context_provider
        self.fungus = fungus_agent
        self.enable_rag = enable_rag and fungus_agent is not None
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # key -> (timestamp, result)

        logger.info(
            "agent_context_bridge_initialized",
            has_provider=context_provider is not None,
            has_fungus=fungus_agent is not None,
            rag_enabled=self.enable_rag,
        )

    async def get_context_for_task(
        self,
        task_type: str,
        query: Optional[str] = None,
        epic_id: Optional[str] = None,
        feature_id: Optional[str] = None,
        top_k: int = 5,
    ) -> MergedContext:
        """
        Get combined context for a specific task.

        Args:
            task_type: Type of task ("database", "api", "frontend", "auth", "infra")
            query: Optional search query for RAG (enhances context)
            epic_id: Optional epic ID to scope context
            feature_id: Optional feature ID to scope context
            top_k: Number of RAG results to include

        Returns:
            MergedContext with static + dynamic context
        """
        # Check cache
        cache_key = self._make_cache_key(task_type, query, epic_id, feature_id)
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug("context_cache_hit", task_type=task_type)
            return cached

        # 1. Get static context from RichContextProvider
        static_ctx = self._get_static_context(task_type, epic_id, feature_id)

        # 2. Get dynamic context from Fungus/RAG (if query provided)
        rag_results = []
        if query and self.enable_rag:
            rag_results = await self._get_rag_context(query, top_k)

        # 3. Merge contexts
        merged = self._merge_contexts(static_ctx, rag_results)

        # Cache result
        self._set_cached(cache_key, merged)

        logger.info(
            "context_retrieved",
            task_type=task_type,
            diagrams=len(merged.diagrams),
            entities=len(merged.entities),
            rag_results=len(merged.rag_results),
        )

        return merged

    def _get_static_context(
        self,
        task_type: str,
        epic_id: Optional[str] = None,
        feature_id: Optional[str] = None,
    ) -> Optional["AgentContext"]:
        """Get static context from RichContextProvider."""
        try:
            # Try task-specific method first
            method_name = f"for_{task_type}_agent"
            method = getattr(self.provider, method_name, None)

            if method:
                return method()

            # Try epic-specific context
            if epic_id and hasattr(self.provider, "for_epic"):
                return self.provider.for_epic(epic_id)

            # Try feature-specific context
            if feature_id and hasattr(self.provider, "for_feature_generation"):
                return self.provider.for_feature_generation(feature_id)

            # Fallback to generic context
            if hasattr(self.provider, "for_generator"):
                return self.provider.for_generator()

            logger.warning("no_context_method_found", task_type=task_type)
            return None

        except Exception as e:
            logger.error("static_context_error", task_type=task_type, error=str(e))
            return None

    async def _get_rag_context(self, query: str, top_k: int) -> List[Dict]:
        """Get dynamic context from Fungus/RAG search."""
        if not self.fungus:
            return []

        try:
            # Use Fungus semantic search
            results = await self.fungus._search_context(
                query=query,
                top_k=top_k,
                mode="steering",  # Use steering mode for general context
            )

            logger.debug(
                "rag_search_complete",
                query=query[:50],
                results_count=len(results) if results else 0,
            )

            return results if results else []

        except Exception as e:
            logger.warning("rag_search_error", query=query[:50], error=str(e))
            return []

    def _merge_contexts(
        self,
        static_ctx: Optional["AgentContext"],
        rag_results: List[Dict],
    ) -> MergedContext:
        """Merge static and dynamic contexts into MergedContext."""
        merged = MergedContext()

        # Copy static context
        if static_ctx:
            merged.tech_stack = static_ctx.tech_stack or {}
            merged.requirements = static_ctx.requirements or []
            merged.diagrams = [d if isinstance(d, dict) else d.to_dict() if hasattr(d, "to_dict") else {"content": str(d)} for d in (static_ctx.diagrams or [])]
            merged.entities = [e if isinstance(e, dict) else e.to_dict() if hasattr(e, "to_dict") else {"name": str(e)} for e in (static_ctx.entities or [])]
            merged.design_tokens = static_ctx.design_tokens or {}
            merged.api_endpoints = static_ctx.api_endpoints or []
            merged.epic_info = static_ctx.epic_info
            merged.feature_info = static_ctx.feature_info

        # Add RAG results
        merged.rag_results = rag_results

        # Extract code examples from RAG results
        merged.code_examples = [
            r for r in rag_results
            if r.get("impl_score", 0) > 0.5 or r.get("has_fetch", False)
        ]

        return merged

    def _make_cache_key(
        self,
        task_type: str,
        query: Optional[str],
        epic_id: Optional[str],
        feature_id: Optional[str],
    ) -> str:
        """Generate cache key for context request."""
        key_parts = [task_type, query or "", epic_id or "", feature_id or ""]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[MergedContext]:
        """Get cached context if still valid."""
        import time

        if key not in self._cache:
            return None

        timestamp, result = self._cache[key]
        if time.time() - timestamp > self.cache_ttl:
            del self._cache[key]
            return None

        return result

    def _set_cached(self, key: str, result: MergedContext) -> None:
        """Cache context result."""
        import time
        self._cache[key] = (time.time(), result)

    def clear_cache(self) -> None:
        """Clear all cached contexts."""
        self._cache.clear()
        logger.debug("context_cache_cleared")

    # Convenience methods for common task types

    async def for_database(self, query: Optional[str] = None) -> MergedContext:
        """Get context optimized for database schema generation."""
        default_query = query or "database schema entities relations prisma"
        return await self.get_context_for_task("database", query=default_query)

    async def for_api(self, query: Optional[str] = None) -> MergedContext:
        """Get context optimized for API generation."""
        default_query = query or "API endpoints REST routes controllers"
        return await self.get_context_for_task("api", query=default_query)

    async def for_frontend(self, query: Optional[str] = None) -> MergedContext:
        """Get context optimized for frontend/UI generation."""
        default_query = query or "UI components React design system"
        return await self.get_context_for_task("frontend", query=default_query)

    async def for_auth(self, query: Optional[str] = None) -> MergedContext:
        """Get context optimized for authentication setup."""
        default_query = query or "authentication JWT RBAC permissions"
        return await self.get_context_for_task("auth", query=default_query)

    async def for_infrastructure(self, query: Optional[str] = None) -> MergedContext:
        """Get context optimized for infrastructure configuration."""
        default_query = query or "Docker compose CI/CD deployment"
        return await self.get_context_for_task("infra", query=default_query)


# Factory function for easy creation
def create_context_bridge(
    doc_spec: Any,
    fungus_agent: Optional["FungusContextAgent"] = None,
    enable_rag: bool = True,
) -> AgentContextBridge:
    """
    Factory function to create AgentContextBridge from DocumentationSpec.

    Args:
        doc_spec: DocumentationSpec loaded from project
        fungus_agent: Optional FungusContextAgent for RAG
        enable_rag: Whether to enable RAG search

    Returns:
        Configured AgentContextBridge
    """
    from src.engine.rich_context_provider import RichContextProvider

    provider = RichContextProvider(doc_spec)
    return AgentContextBridge(
        context_provider=provider,
        fungus_agent=fungus_agent,
        enable_rag=enable_rag,
    )
