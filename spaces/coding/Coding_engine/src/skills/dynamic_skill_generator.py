"""
Dynamic Skill Generator - Generates skills on-demand via LLM calls.

Instead of static .claude/skills/*/SKILL.md files, this module generates
context-aware skills dynamically before agent execution.

Features:
- LLM-based skill generation tailored to task context
- Session-level caching to avoid redundant LLM calls
- Optional Redis cache for multi-worker scenarios
- Integration with DocumentationSpec for rich context injection
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
import structlog

from src.skills.skill import Skill

logger = structlog.get_logger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM client interface."""

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> "LLMResponse":
        """Generate text from prompt."""
        ...


@dataclass
class LLMResponse:
    """LLM response container."""
    content: str
    tokens_used: int = 0
    model: str = ""


@dataclass
class GeneratedSkill:
    """A dynamically generated skill."""
    name: str
    instructions: str
    task_type: str
    tier: str = "full"  # Dynamic skills are always full tier
    generated_at: datetime = field(default_factory=datetime.now)
    cache_key: str = ""
    token_estimate: int = 0

    def to_skill(self) -> Skill:
        """Convert to standard Skill object for agent injection."""
        return Skill(
            name=self.name,
            description=f"Dynamically generated skill for {self.task_type}",
            instructions=self.instructions,
            path=Path(".generated"),
            trigger_events=[],
            tier_boundaries={},
        )

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "task_type": self.task_type,
            "tier": self.tier,
            "generated_at": self.generated_at.isoformat(),
            "cache_key": self.cache_key,
            "token_estimate": self.token_estimate,
        }


class SkillCache(Protocol):
    """Protocol for skill caching backends."""

    async def get(self, key: str) -> Optional[GeneratedSkill]:
        """Get cached skill by key."""
        ...

    async def set(self, key: str, skill: GeneratedSkill, ttl: int = 3600) -> None:
        """Cache a skill with optional TTL."""
        ...


class InMemorySkillCache:
    """In-memory skill cache for single-worker scenarios."""

    def __init__(self):
        self._cache: Dict[str, GeneratedSkill] = {}
        self._timestamps: Dict[str, datetime] = {}

    async def get(self, key: str) -> Optional[GeneratedSkill]:
        if key in self._cache:
            logger.debug("skill_cache_hit", key=key[:32])
            return self._cache[key]
        return None

    async def set(self, key: str, skill: GeneratedSkill, ttl: int = 3600) -> None:
        self._cache[key] = skill
        self._timestamps[key] = datetime.now()
        logger.debug("skill_cached", key=key[:32], name=skill.name)

    def clear(self) -> None:
        self._cache.clear()
        self._timestamps.clear()


class RedisSkillCache:
    """Redis-backed skill cache for multi-worker scenarios."""

    def __init__(self, redis_client):
        self._redis = redis_client
        self._prefix = "dynamic_skill:"

    async def get(self, key: str) -> Optional[GeneratedSkill]:
        data = await self._redis.get(f"{self._prefix}{key}")
        if data:
            parsed = json.loads(data)
            return GeneratedSkill(
                name=parsed["name"],
                instructions=parsed["instructions"],
                task_type=parsed["task_type"],
                tier=parsed.get("tier", "full"),
                generated_at=datetime.fromisoformat(parsed["generated_at"]),
                cache_key=key,
                token_estimate=parsed.get("token_estimate", 0),
            )
        return None

    async def set(self, key: str, skill: GeneratedSkill, ttl: int = 3600) -> None:
        data = {
            "name": skill.name,
            "instructions": skill.instructions,
            "task_type": skill.task_type,
            "tier": skill.tier,
            "generated_at": skill.generated_at.isoformat(),
            "token_estimate": skill.token_estimate,
        }
        await self._redis.setex(
            f"{self._prefix}{key}",
            ttl,
            json.dumps(data),
        )


class DynamicSkillGenerator:
    """
    Generates skills dynamically via LLM before agent injection.

    Usage:
        generator = DynamicSkillGenerator(llm_client)

        skill = await generator.generate(
            task_type="nestjs_websocket",
            tech_stack={"backend": {"framework": "NestJS"}},
            context_diagrams=[sequence_diagram],
            requirements=epic_003_reqs,
        )

        # Inject into agent
        agent.inject_skill(skill.to_skill())
    """

    # Task type to skill template mapping
    TASK_TEMPLATES = {
        "nestjs_controller": "NestJS REST Controller with decorators",
        "nestjs_websocket": "NestJS WebSocket Gateway with Socket.io",
        "nestjs_guard": "NestJS Authentication Guard with JWT",
        "nestjs_module": "NestJS Module with dependency injection",
        "prisma_schema": "Prisma database schema from entities",
        "react_component": "React functional component with TypeScript",
        "react_hook": "Custom React hook with TypeScript",
        "redis_pubsub": "Redis Pub/Sub integration for real-time",
        "api_endpoint": "REST API endpoint implementation",
        "auth_flow": "Authentication flow with JWT and RBAC",
        "database_migration": "Database migration script",
        "e2e_test": "End-to-end test with Playwright",
        "unit_test": "Unit test with Vitest/Jest",
    }

    def __init__(
        self,
        llm_client: LLMClient,
        cache: Optional[SkillCache] = None,
        system_prompt: Optional[str] = None,
    ):
        self.llm_client = llm_client
        self._cache = cache or InMemorySkillCache()
        self._system_prompt = system_prompt or self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        return """Du bist ein Skill-Autor für autonome Code-Generierung.

Deine Aufgabe ist es, präzise, actionable Skill-Instructions zu erstellen,
die ein Code-Generierungs-Agent direkt umsetzen kann.

REGELN:
1. Sei KONKRET - keine vagen Anweisungen
2. Zeige CODE-BEISPIELE für das spezifische Framework
3. Liste KRITISCHE REGELN die nicht verletzt werden dürfen
4. Beschreibe FEHLER-PATTERNS und wie man sie vermeidet
5. Definiere VALIDATION-SCHRITTE zur Prüfung des Outputs

AUSGABE-FORMAT:
Strukturiere den Skill mit folgenden Abschnitten:
- TRIGGER_EVENTS: Welche Events aktivieren diesen Skill
- CRITICAL_RULES: Unbedingt einzuhaltende Regeln
- WORKFLOW: Schritt-für-Schritt Anleitung (nummeriert)
- CODE_PATTERNS: Konkrete Code-Beispiele
- ERROR_PATTERNS: Häufige Fehler und Fixes
- VALIDATION: Wie verifiziert man den Output"""

    def _generate_cache_key(
        self,
        task_type: str,
        tech_stack: Dict,
        requirements: List[Dict],
    ) -> str:
        """Generate a stable cache key from inputs."""
        key_data = {
            "task_type": task_type,
            "tech_stack_hash": hashlib.md5(
                json.dumps(tech_stack, sort_keys=True).encode()
            ).hexdigest()[:16],
            "req_count": len(requirements),
            "req_ids": sorted([r.get("req_id", r.get("id", "")) for r in requirements[:10]]),
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:48]

    async def generate(
        self,
        task_type: str,
        tech_stack: Dict[str, Any],
        context_diagrams: Optional[List[Dict]] = None,
        requirements: Optional[List[Dict]] = None,
        force_regenerate: bool = False,
    ) -> GeneratedSkill:
        """
        Generate a skill dynamically based on task context.

        Args:
            task_type: Type of task (e.g., "nestjs_websocket", "prisma_schema")
            tech_stack: Technology stack configuration
            context_diagrams: Optional Mermaid diagrams for context
            requirements: Optional requirements being implemented
            force_regenerate: Skip cache and regenerate

        Returns:
            GeneratedSkill ready for agent injection
        """
        requirements = requirements or []
        context_diagrams = context_diagrams or []

        cache_key = self._generate_cache_key(task_type, tech_stack, requirements)

        # Check cache
        if not force_regenerate:
            cached = await self._cache.get(cache_key)
            if cached:
                logger.info("using_cached_skill", task_type=task_type, cache_key=cache_key[:16])
                return cached

        # Build prompt
        prompt = self._build_skill_generation_prompt(
            task_type, tech_stack, context_diagrams, requirements
        )

        logger.info("generating_dynamic_skill", task_type=task_type)

        # Generate via LLM
        response = await self.llm_client.generate(
            prompt=prompt,
            system=self._system_prompt,
            max_tokens=4096,
        )

        # Create skill
        skill_name = f"dynamic_{task_type}"
        skill = GeneratedSkill(
            name=skill_name,
            instructions=response.content,
            task_type=task_type,
            tier="full",
            generated_at=datetime.now(),
            cache_key=cache_key,
            token_estimate=len(response.content) // 4,
        )

        # Cache for future use
        await self._cache.set(cache_key, skill)

        logger.info(
            "skill_generated",
            task_type=task_type,
            tokens=skill.token_estimate,
            cache_key=cache_key[:16],
        )

        return skill

    def _build_skill_generation_prompt(
        self,
        task_type: str,
        tech_stack: Dict,
        diagrams: List[Dict],
        requirements: List[Dict],
    ) -> str:
        """Build the prompt for skill generation."""

        # Get task template description
        task_description = self.TASK_TEMPLATES.get(
            task_type,
            f"Implementation for {task_type}"
        )

        # Format tech stack
        tech_stack_str = self._format_tech_stack(tech_stack)

        # Format diagrams (limit to most relevant)
        diagrams_str = self._format_diagrams(diagrams[:5])

        # Format requirements
        requirements_str = self._format_requirements(requirements[:10])

        return f"""Generiere einen Skill für folgende Aufgabe:

## Task Type
**{task_type}**: {task_description}

## Tech Stack
{tech_stack_str}

## Relevante Diagramme
{diagrams_str}

## Requirements
{requirements_str}

## Anweisungen
Erstelle einen vollständigen Skill mit:

1. **TRIGGER_EVENTS** - Welche Events aktivieren diesen Skill

2. **CRITICAL_RULES** - Unbedingt einzuhaltende Regeln:
   - NO MOCKS: Nur echte Integrationen
   - Typ-Sicherheit mit TypeScript
   - Fehlerbehandlung immer implementieren
   - Framework-spezifische Best Practices

3. **WORKFLOW** - Schritt-für-Schritt Anleitung (nummeriert)

4. **CODE_PATTERNS** - Konkrete Code-Beispiele für den spezifischen Tech-Stack

5. **ERROR_PATTERNS** - Häufige Fehler und wie man sie vermeidet

6. **VALIDATION** - Wie verifiziert man den Output

Sei KONKRET und verwende das spezifische Framework: {tech_stack.get('backend', {}).get('framework', 'Node.js')}"""

    def _format_tech_stack(self, tech_stack: Dict) -> str:
        """Format tech stack for prompt."""
        lines = []

        if "frontend" in tech_stack:
            fe = tech_stack["frontend"]
            lines.append(f"- Frontend: {fe.get('framework', 'React')} + {fe.get('ui_library', 'N/A')}")

        if "backend" in tech_stack:
            be = tech_stack["backend"]
            lines.append(f"- Backend: {be.get('framework', 'Express')} ({be.get('language', 'Node.js')})")
            lines.append(f"- API Style: {be.get('api_style', 'REST')}")

        if "database" in tech_stack:
            db = tech_stack["database"]
            lines.append(f"- Database: {db.get('primary', 'PostgreSQL')}")
            if db.get("cache"):
                lines.append(f"- Cache: {db.get('cache')}")

        if "infrastructure" in tech_stack:
            infra = tech_stack["infrastructure"]
            if infra.get("message_queue"):
                lines.append(f"- Message Queue: {infra.get('message_queue')}")
            if infra.get("container_runtime"):
                lines.append(f"- Container: {infra.get('container_runtime')}")

        return "\n".join(lines) if lines else "Nicht spezifiziert"

    def _format_diagrams(self, diagrams: List[Dict]) -> str:
        """Format diagrams for prompt context."""
        if not diagrams:
            return "Keine Diagramme verfügbar"

        formatted = []
        for i, diagram in enumerate(diagrams, 1):
            if isinstance(diagram, dict):
                dtype = diagram.get("diagram_type", "unknown")
                title = diagram.get("title", f"Diagram {i}")
                content = diagram.get("content", "")[:500]  # Truncate
            else:
                # Assume it's a Diagram object
                dtype = getattr(diagram, "diagram_type", "unknown")
                title = getattr(diagram, "title", f"Diagram {i}") or f"Diagram {i}"
                content = getattr(diagram, "content", "")[:500]

            formatted.append(f"### {title} ({dtype})\n```mermaid\n{content}\n```")

        return "\n\n".join(formatted)

    def _format_requirements(self, requirements: List[Dict]) -> str:
        """Format requirements for prompt context."""
        if not requirements:
            return "Keine spezifischen Requirements"

        lines = []
        for req in requirements:
            req_id = req.get("req_id", req.get("id", "REQ-???"))
            title = req.get("title", req.get("name", "Unnamed"))
            desc = req.get("description", "")[:200]

            lines.append(f"- **{req_id}**: {title}")
            if desc:
                lines.append(f"  {desc}")

        return "\n".join(lines)

    def get_supported_task_types(self) -> List[str]:
        """Get list of supported task types."""
        return list(self.TASK_TEMPLATES.keys())

    def infer_task_type(self, context: Dict) -> str:
        """
        Infer the appropriate task type from context.

        Args:
            context: Dict with keys like 'epic_id', 'requirements', 'event_type'

        Returns:
            Inferred task type string
        """
        # Check event type
        event_type = context.get("event_type", "").upper()

        if "DATABASE" in event_type or "SCHEMA" in event_type:
            return "prisma_schema"
        if "API" in event_type or "ROUTES" in event_type:
            return "api_endpoint"
        if "AUTH" in event_type:
            return "auth_flow"
        if "WEBSOCKET" in event_type:
            return "nestjs_websocket"
        if "TEST" in event_type:
            if "E2E" in event_type:
                return "e2e_test"
            return "unit_test"

        # Check requirements content
        requirements = context.get("requirements", [])
        for req in requirements:
            title = str(req.get("title", "")).lower()
            if "websocket" in title or "real-time" in title or "echtzeit" in title:
                return "nestjs_websocket"
            if "auth" in title or "login" in title or "anmeld" in title:
                return "auth_flow"
            if "database" in title or "datenbank" in title:
                return "prisma_schema"

        # Check tech stack
        tech_stack = context.get("tech_stack", {})
        backend_framework = tech_stack.get("backend", {}).get("framework", "")

        if "nest" in backend_framework.lower():
            return "nestjs_controller"

        return "api_endpoint"  # Default

    async def generate_for_context(self, context: Dict) -> GeneratedSkill:
        """
        Generate skill from a context dictionary.

        Convenience method that infers task type and extracts relevant data.
        """
        task_type = context.get("task_type") or self.infer_task_type(context)
        tech_stack = context.get("tech_stack", {})
        diagrams = context.get("diagrams", [])
        requirements = context.get("requirements", [])

        return await self.generate(
            task_type=task_type,
            tech_stack=tech_stack,
            context_diagrams=diagrams,
            requirements=requirements,
        )
