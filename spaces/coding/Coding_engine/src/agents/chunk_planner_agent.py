"""
ChunkPlannerAgent - LLM-based Intelligent Requirement Chunking.

This agent analyzes requirements and creates an optimal execution plan by:
1. Grouping requirements by service/domain (auth, user, payment, etc.)
2. Analyzing dependencies between services (DAG)
3. Scoring complexity (simple/medium/complex)
4. Creating balanced chunks for parallel execution
5. Computing execution waves respecting dependencies
6. Assigning workers for load balancing

Key Principle: Instead of fixed 3-chunk rule, LLM decides optimal distribution
based on services, dependencies, and available resources!

Reference: Plan file - "LLM-basierter Chunk Planner für Phase 2"
"""

import asyncio
import json
import hashlib
import re
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

import structlog

from src.engine.execution_plan import (
    ExecutionPlan,
    ServiceGroup,
    RequirementChunk,
    WorkerAssignment,
    Wave,
    ComplexityLevel,
    ServiceDomain,
    DEFAULT_TIME_ESTIMATES,
    estimate_chunk_time,
)
from src.utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)

logger = structlog.get_logger(__name__)


# Map 12 logical domains to 8 actual microservices
# This enables proper service isolation for cloud deployment
DOMAIN_TO_SERVICE_MAP = {
    "auth": "auth-service",
    "user": "user-service",
    "payment": "billing-service",
    "dashboard": "transport-service",
    "admin": "auth-service",        # Merged: Admin RBAC into auth
    "notifications": "user-service",  # Merged: Notifications into user
    "search": "gateway-service",
    "reports": "pod-service",
    "settings": "user-service",     # Merged: Settings into user
    "api": "gateway-service",
    "storage": "pod-service",
    "other": "gateway-service",     # Default fallback
}


@dataclass
class ChunkPlannerConfig:
    """Configuration for the ChunkPlannerAgent."""
    max_concurrent: int = 10             # Maximum parallel workers (increased for better parallelism)
    max_requirements_per_chunk: int = 10 # Larger batches for better efficiency
    min_requirements_per_chunk: int = 1  # Allow single-req chunks for complex items
    estimated_time_simple: int = 3       # Minutes per simple requirement
    estimated_time_medium: int = 5       # Minutes per medium requirement
    estimated_time_complex: int = 10     # Minutes per complex requirement
    enable_llm_analysis: bool = True     # Use LLM for grouping (vs heuristics)
    balance_threshold: float = 0.2       # Max load imbalance between workers (20%)


class ChunkPlannerAgent:
    """
    LLM-based agent for intelligent requirement chunking.

    Analyzes requirements and creates optimal ExecutionPlan based on:
    - Service grouping (related features together)
    - Dependency graph (what must be built first)
    - Complexity scoring (time estimates)
    - Worker availability (max_concurrent)
    - Load balancing (even distribution)
    """

    def __init__(
        self,
        config: Optional[ChunkPlannerConfig] = None,
        llm_client=None,
    ):
        self.config = config or ChunkPlannerConfig()
        self.llm_client = llm_client
        self.logger = logger.bind(agent="ChunkPlannerAgent")

    async def create_execution_plan(
        self,
        requirements: list[dict],
        tech_stack: Optional[dict] = None,
    ) -> ExecutionPlan:
        """
        Create optimal execution plan for requirements.

        Args:
            requirements: List of requirement dicts from JSON
            tech_stack: Optional tech stack info for better grouping

        Returns:
            ExecutionPlan with waves and worker assignments
        """
        self.logger.info(
            "creating_execution_plan",
            requirement_count=len(requirements),
            max_concurrent=self.config.max_concurrent,
        )

        # Calculate hash for caching
        req_hash = self._hash_requirements(requirements)

        # 1. Analyze and group requirements by service
        if self.config.enable_llm_analysis and self.llm_client:
            service_groups = await self._llm_analyze_and_group(requirements, tech_stack)
        else:
            service_groups = self._heuristic_group(requirements)

        self.logger.info(
            "service_groups_created",
            group_count=len(service_groups),
            groups=[g.service_name for g in service_groups],
        )

        # 2. Score complexity for each group
        if self.config.enable_llm_analysis and self.llm_client:
            scored_groups = await self._llm_score_complexity(service_groups, requirements)
        else:
            scored_groups = self._heuristic_score_complexity(service_groups, requirements)

        # 3. Build dependency graph
        if self.config.enable_llm_analysis and self.llm_client:
            dependency_graph = await self._llm_build_dependency_graph(scored_groups)
        else:
            dependency_graph = self._heuristic_dependency_graph(scored_groups)

        # 4. Create balanced chunks
        chunks = self._create_balanced_chunks(scored_groups, dependency_graph)

        self.logger.info(
            "chunks_created",
            chunk_count=len(chunks),
        )

        # 5. Compute execution waves (topological sort)
        waves = self._compute_execution_waves(chunks, dependency_graph)

        self.logger.info(
            "waves_computed",
            wave_count=len(waves),
        )

        # 6. Assign chunks to workers
        worker_assignments = self._assign_to_workers(waves, chunks)

        # 7. Calculate metrics
        total_estimated = sum(w.estimated_minutes for w in waves)
        sequential_estimated = sum(c.estimated_minutes for c in chunks)
        parallelization_factor = sequential_estimated / total_estimated if total_estimated > 0 else 1.0

        # 8. Generate reasoning
        if self.config.enable_llm_analysis and self.llm_client:
            reasoning = await self._generate_reasoning(chunks, waves, service_groups)
        else:
            reasoning = self._heuristic_reasoning(chunks, waves, service_groups)

        plan = ExecutionPlan(
            waves=waves,
            worker_assignments=worker_assignments,
            chunks=chunks,
            service_groups=scored_groups,
            total_requirements=sum(len(g.requirements) for g in scored_groups),
            total_chunks=len(chunks),
            total_waves=len(waves),
            total_workers=self.config.max_concurrent,
            total_estimated_minutes=total_estimated,
            sequential_estimated_minutes=sequential_estimated,
            parallelization_factor=parallelization_factor,
            reasoning=reasoning,
            created_at=datetime.now(),
            requirements_hash=req_hash,
        )

        self.logger.info(
            "execution_plan_complete",
            total_minutes=total_estimated,
            sequential_minutes=sequential_estimated,
            speedup=f"{parallelization_factor:.1f}x",
        )

        return plan

    # -------------------------------------------------------------------------
    # LLM-based Analysis Methods
    # -------------------------------------------------------------------------

    async def _llm_analyze_and_group(
        self,
        requirements: list[dict],
        tech_stack: Optional[dict] = None,
    ) -> list[ServiceGroup]:
        """Use LLM to analyze and group requirements by service."""

        # Format requirements for LLM
        req_text = json.dumps(requirements, indent=2, ensure_ascii=False)
        tech_text = json.dumps(tech_stack, indent=2) if tech_stack else "Not specified"

        prompt = f"""Analysiere diese Requirements und gruppiere sie nach Service/Domäne.

Requirements:
{req_text}

Tech Stack:
{tech_text}

Gruppiere nach logischen Services wie:
- auth (Login, Logout, Register, Password Reset, Session)
- user (Profile, Settings, CRUD, Avatar)
- payment (Checkout, History, Refunds, Subscriptions)
- dashboard (Layout, Widgets, Charts, Analytics)
- admin (User Management, System Config, Roles)
- notifications (Push, Email, In-app)
- search (Basic, Filters, Advanced)
- reports (Export, Analytics, PDF/CSV)
- settings (Theme, Language, Preferences)
- api (External integrations, Webhooks)
- storage (File upload, Media management)

Für jede Gruppe gib an:
1. service_name: Name der Service-Domäne
2. requirements: Liste der Requirement-IDs die dazu gehören
3. estimated_files: Geschätzte Dateien die erstellt/geändert werden
4. depends_on: Andere Services von denen dieser abhängt

Antworte NUR mit validem JSON im Format:
{{
  "groups": [
    {{
      "service_name": "auth",
      "requirements": ["req_1", "req_2"],
      "estimated_files": ["src/auth/login.tsx", "src/auth/api.ts"],
      "depends_on": []
    }}
  ]
}}"""

        try:
            response = await self.llm_client.generate(prompt)
            return self._parse_service_groups_response(response)
        except Exception as e:
            self.logger.warning("llm_grouping_failed", error=str(e))
            return self._heuristic_group(requirements)

    async def _llm_score_complexity(
        self,
        groups: list[ServiceGroup],
        requirements: list[dict],
    ) -> list[ServiceGroup]:
        """Use LLM to score complexity of each group."""

        groups_text = json.dumps([g.to_dict() for g in groups], indent=2, ensure_ascii=False)
        req_text = json.dumps(requirements, indent=2, ensure_ascii=False)

        prompt = f"""Bewerte die Komplexität jeder Service-Gruppe.

Service-Gruppen:
{groups_text}

Original Requirements:
{req_text}

Komplexitäts-Kriterien:
- simple: 1-2 Dateien, keine externen APIs, Standard-CRUD, einfache UI
- medium: 3-5 Dateien, einfache Logik, lokale State, moderate UI
- complex: 5+ Dateien, externe APIs, komplexe Logik, Sicherheit, Charts/Visualisierungen

Schätze auch die Zeit in Minuten:
- simple: ~3 Minuten
- medium: ~5 Minuten
- complex: ~10 Minuten

Antworte NUR mit validem JSON:
{{
  "scores": [
    {{
      "service_name": "auth",
      "complexity": "medium",
      "estimated_minutes": 5,
      "reasoning": "Login/Logout mit Session Management"
    }}
  ]
}}"""

        try:
            response = await self.llm_client.generate(prompt)
            return self._apply_complexity_scores(groups, response)
        except Exception as e:
            self.logger.warning("llm_scoring_failed", error=str(e))
            return self._heuristic_score_complexity(groups, requirements)

    async def _llm_build_dependency_graph(
        self,
        groups: list[ServiceGroup],
    ) -> dict[str, list[str]]:
        """Use LLM to determine dependencies between services."""

        groups_text = json.dumps([g.to_dict() for g in groups], indent=2, ensure_ascii=False)

        prompt = f"""Analysiere die Abhängigkeiten zwischen diesen Service-Gruppen.

Service-Gruppen:
{groups_text}

Typische Abhängigkeiten:
- user HÄNGT AB VON auth (User braucht Login)
- payment HÄNGT AB VON user (Payment braucht User-Account)
- dashboard HÄNGT AB VON user (Dashboard zeigt User-Daten)
- reports HÄNGT AB VON dashboard (Reports nutzen Dashboard-Daten)
- admin HÄNGT AB VON auth, user (Admin verwaltet User)

Erstelle einen Dependency-Graph.
ACHTUNG: Vermeide zyklische Abhängigkeiten!

Antworte NUR mit validem JSON:
{{
  "dependencies": {{
    "auth": [],
    "user": ["auth"],
    "payment": ["user"],
    "dashboard": ["user"],
    "admin": ["auth", "user"]
  }}
}}"""

        try:
            response = await self.llm_client.generate(prompt)
            return self._parse_dependency_graph(response)
        except Exception as e:
            self.logger.warning("llm_dependency_failed", error=str(e))
            return self._heuristic_dependency_graph(groups)

    async def _generate_reasoning(
        self,
        chunks: list[RequirementChunk],
        waves: list[Wave],
        groups: list[ServiceGroup],
    ) -> str:
        """Generate human-readable reasoning for the plan."""

        plan_summary = {
            "total_chunks": len(chunks),
            "total_waves": len(waves),
            "services": [g.service_name for g in groups],
            "wave_distribution": [len(w.chunks) for w in waves],
        }

        prompt = f"""Erkläre kurz den Ausführungsplan:

Plan-Zusammenfassung:
{json.dumps(plan_summary, indent=2)}

Erkläre in 2-3 Sätzen:
1. Warum diese Service-Gruppierung?
2. Warum diese Wave-Aufteilung?
3. Erwarteter Speedup gegenüber sequentieller Ausführung?

Antworte auf Deutsch, kurz und prägnant."""

        try:
            return await self.llm_client.generate(prompt)
        except Exception as e:
            return self._heuristic_reasoning(chunks, waves, groups)

    # -------------------------------------------------------------------------
    # Heuristic Fallback Methods (when LLM not available)
    # -------------------------------------------------------------------------

    def _heuristic_group(
        self,
        requirements: list[dict],
        microservice_mode: bool = False,
    ) -> list[ServiceGroup]:
        """Group requirements using keyword heuristics.

        Args:
            requirements: List of requirement dictionaries
            microservice_mode: If True, map domains to actual microservices (8 services)
                             If False, use logical domains (12 domains)
        """

        # Keywords for each service domain (DE/EN bilingual support)
        domain_keywords = {
            "auth": ["login", "logout", "register", "password", "auth", "session", "token", "signup",
                     "rolle", "berechtigung", "permission", "access", "jwt", "oauth", "security"],
            "user": ["user", "profile", "avatar", "account", "settings", "benutzer", "profil",
                     "preferences", "personal", "identity"],
            "payment": ["payment", "checkout", "cart", "order", "subscription", "billing", "invoice",
                        "rechnung", "faktur", "abrechnung", "discount", "pricing", "credit"],
            "dashboard": ["dashboard", "widget", "chart", "analytics", "overview", "metric",
                          "disposition", "tour", "route", "visualization", "kpi", "statistics"],
            "admin": ["admin", "manage", "role", "permission", "system", "verwaltung",
                      "configuration", "maintenance", "audit", "logging"],
            "notifications": ["notification", "alert", "message", "email", "push", "benachrichtigung",
                              "reminder", "webhook", "event"],
            "search": ["search", "filter", "query", "find", "suche", "index", "elasticsearch"],
            "reports": ["report", "export", "csv", "pdf", "download", "pod", "liefernachweis",
                        "dokument", "generate", "template", "schedule"],
            "settings": ["setting", "preference", "theme", "language", "config", "einstellung",
                         "customization", "option"],
            "api": ["api", "integration", "webhook", "external", "gateway", "schnittstelle",
                    "endpoint", "rest", "graphql", "sync"],
            "storage": ["upload", "file", "media", "image", "document", "datei", "speicher",
                        "attachment", "blob", "s3", "cdn"],
        }

        groups: dict[str, ServiceGroup] = {}

        for req in requirements:
            req_id = req.get("id", str(hash(json.dumps(req))))
            req_text = f"{req.get('name', '')} {req.get('description', '')} {req.get('title', '')} {req.get('text', '')}".lower()

            # Check for service hint in requirement metadata
            service_hint = req.get("service", "").lower()

            # Find matching domain using pattern classifier
            matched_domain = self._classify_requirement_domain(
                req_text, service_hint, domain_keywords
            )

            # In microservice mode, map domain to actual service name
            if microservice_mode:
                service_name = DOMAIN_TO_SERVICE_MAP.get(matched_domain, "gateway-service")
            else:
                service_name = matched_domain

            # Add to group
            if service_name not in groups:
                groups[service_name] = ServiceGroup(
                    service_name=service_name,
                    requirements=[],
                    estimated_files=[],
                    complexity=ComplexityLevel.MEDIUM,
                    depends_on=[],
                )
            groups[service_name].requirements.append(req_id)

        return list(groups.values())

    def _classify_requirement_domain(
        self,
        req_text: str,
        service_hint: str,
        domain_keywords: dict[str, list[str]],
    ) -> str:
        """
        Classify requirement into a domain using pattern-based detection.

        Uses multi-tier approach:
        1. Direct service hint from metadata
        2. Pattern-based keyword matching
        3. Default fallback to "other"

        Args:
            req_text: Concatenated requirement text (name + description)
            service_hint: Optional service hint from requirement metadata
            domain_keywords: Dictionary mapping domains to keyword lists

        Returns:
            Domain string (e.g., "auth", "user", "payment", "other")
        """
        # Tier 1: Use service hint if explicitly provided
        if service_hint and service_hint in domain_keywords:
            return service_hint

        # Tier 2: Pattern-based keyword matching
        req_lower = req_text.lower()

        # Score each domain by keyword matches
        domain_scores: dict[str, int] = {}
        for domain, keywords in domain_keywords.items():
            score = sum(1 for kw in keywords if kw in req_lower)
            if score > 0:
                domain_scores[domain] = score

        # Return domain with highest score
        if domain_scores:
            best_domain = max(domain_scores, key=lambda d: domain_scores[d])
            return best_domain

        # Tier 3: Fallback to "other"
        return "other"

    def _heuristic_score_complexity(
        self,
        groups: list[ServiceGroup],
        requirements: list[dict],
    ) -> list[ServiceGroup]:
        """Score complexity using heuristics."""

        # Complexity by domain
        domain_complexity = {
            "auth": ComplexityLevel.MEDIUM,      # Security-sensitive
            "payment": ComplexityLevel.COMPLEX,  # External APIs, security
            "dashboard": ComplexityLevel.MEDIUM, # Charts, state
            "admin": ComplexityLevel.COMPLEX,    # RBAC, permissions
            "user": ComplexityLevel.SIMPLE,      # Standard CRUD
            "settings": ComplexityLevel.SIMPLE,  # Key-value storage
            "notifications": ComplexityLevel.MEDIUM,
            "search": ComplexityLevel.MEDIUM,
            "reports": ComplexityLevel.MEDIUM,
            "storage": ComplexityLevel.MEDIUM,
            "api": ComplexityLevel.COMPLEX,
            "other": ComplexityLevel.MEDIUM,
        }

        for group in groups:
            base_complexity = domain_complexity.get(group.service_name, ComplexityLevel.MEDIUM)

            # Adjust by number of requirements
            if len(group.requirements) > 5:
                # More requirements = likely more complex
                if base_complexity == ComplexityLevel.SIMPLE:
                    base_complexity = ComplexityLevel.MEDIUM
                elif base_complexity == ComplexityLevel.MEDIUM:
                    base_complexity = ComplexityLevel.COMPLEX

            group.complexity = base_complexity
            group.estimated_minutes = DEFAULT_TIME_ESTIMATES.get(base_complexity, 5)

        return groups

    def _heuristic_dependency_graph(
        self,
        groups: list[ServiceGroup],
    ) -> dict[str, list[str]]:
        """Build dependency graph using common patterns."""

        # Standard dependencies
        standard_deps = {
            "user": ["auth"],
            "payment": ["user", "auth"],
            "dashboard": ["user", "auth"],
            "admin": ["auth", "user"],
            "reports": ["dashboard", "user"],
            "notifications": ["user"],
            "settings": ["user"],
            "search": [],
            "auth": [],
            "api": ["auth"],
            "storage": ["auth"],
            "other": [],
        }

        existing_services = {g.service_name for g in groups}
        dependencies = {}

        for group in groups:
            service = group.service_name
            deps = standard_deps.get(service, [])
            # Only include dependencies that exist
            dependencies[service] = [d for d in deps if d in existing_services]

        return dependencies

    def _heuristic_reasoning(
        self,
        chunks: list[RequirementChunk],
        waves: list[Wave],
        groups: list[ServiceGroup],
    ) -> str:
        """Generate reasoning without LLM."""
        services = [g.service_name for g in groups]
        return (
            f"Automatische Gruppierung in {len(groups)} Services ({', '.join(services)}). "
            f"Aufgeteilt in {len(waves)} parallele Waves mit {len(chunks)} Chunks. "
            f"Abhängigkeiten werden respektiert (z.B. auth vor user)."
        )

    # -------------------------------------------------------------------------
    # Chunk Creation and Scheduling
    # -------------------------------------------------------------------------

    def _create_balanced_chunks(
        self,
        groups: list[ServiceGroup],
        dependency_graph: dict[str, list[str]],
    ) -> list[RequirementChunk]:
        """Create balanced chunks from service groups."""

        chunks = []
        chunk_counter = 0

        for group in groups:
            reqs = group.requirements
            complexity = group.complexity

            # Determine chunk size based on complexity
            # Larger batches = more context for Claude = better code quality
            if complexity == ComplexityLevel.COMPLEX:
                # Complex: moderate chunks (5-6 reqs)
                max_per_chunk = 6
            elif complexity == ComplexityLevel.MEDIUM:
                # Medium: larger chunks (8 reqs)
                max_per_chunk = 8
            else:
                # Simple: largest chunks (10 reqs)
                max_per_chunk = 10

            max_per_chunk = min(max_per_chunk, self.config.max_requirements_per_chunk)

            # Split requirements into chunks
            for i in range(0, len(reqs), max_per_chunk):
                chunk_reqs = reqs[i:i + max_per_chunk]
                chunk_counter += 1
                chunk_id = f"chunk_{chunk_counter:03d}"

                # Dependencies: this chunk depends on all chunks from dependency services
                depends_on = []
                for dep_service in dependency_graph.get(group.service_name, []):
                    # Find all chunks from the dependency service
                    for other_chunk in chunks:
                        if other_chunk.service_group == dep_service:
                            depends_on.append(other_chunk.chunk_id)

                chunk = RequirementChunk(
                    chunk_id=chunk_id,
                    requirements=chunk_reqs,
                    service_group=group.service_name,
                    complexity=complexity,
                    depends_on_chunks=depends_on,
                    estimated_minutes=estimate_chunk_time(
                        RequirementChunk(
                            chunk_id="temp",
                            requirements=chunk_reqs,
                            complexity=complexity,
                        )
                    ),
                )
                chunks.append(chunk)

        return chunks

    def _compute_execution_waves(
        self,
        chunks: list[RequirementChunk],
        dependency_graph: dict[str, list[str]],
    ) -> list[Wave]:
        """Compute execution waves using topological sort."""

        # Build chunk dependency map
        chunk_deps = {c.chunk_id: set(c.depends_on_chunks) for c in chunks}
        remaining = set(c.chunk_id for c in chunks)
        completed = set()
        waves = []
        wave_id = 0

        while remaining:
            wave_id += 1
            # Find all chunks with satisfied dependencies
            ready = []
            for chunk_id in remaining:
                deps = chunk_deps[chunk_id]
                if deps.issubset(completed):
                    ready.append(chunk_id)

            if not ready:
                # Circular dependency - break by taking first remaining
                self.logger.warning(
                    "circular_dependency_detected",
                    remaining=list(remaining)[:5],
                )
                ready = [list(remaining)[0]]

            # Limit wave size to max_concurrent
            if len(ready) > self.config.max_concurrent:
                ready = ready[:self.config.max_concurrent]

            # Create wave
            blocked_by = list(completed) if wave_id > 1 else []
            wave_chunks = [c for c in chunks if c.chunk_id in ready]
            wave_time = max((c.estimated_minutes for c in wave_chunks), default=0)

            wave = Wave(
                wave_id=wave_id,
                chunks=ready,
                blocked_by=blocked_by,
                estimated_minutes=wave_time,
            )
            waves.append(wave)

            # Update state
            for chunk_id in ready:
                remaining.remove(chunk_id)
                completed.add(chunk_id)

            # Update chunk wave assignments
            for chunk in chunks:
                if chunk.chunk_id in ready:
                    chunk.wave_id = wave_id

        return waves

    def _assign_to_workers(
        self,
        waves: list[Wave],
        chunks: list[RequirementChunk],
    ) -> list[WorkerAssignment]:
        """Assign chunks to workers for load balancing."""

        # Create worker assignments
        workers = [
            WorkerAssignment(worker_id=i, chunks=[], estimated_duration_minutes=0)
            for i in range(1, self.config.max_concurrent + 1)
        ]

        # Assign chunks per wave
        for wave in waves:
            wave_chunks = [c for c in chunks if c.chunk_id in wave.chunks]

            # Sort by estimated time (longest first) for better balancing
            wave_chunks.sort(key=lambda c: c.estimated_minutes, reverse=True)

            for chunk in wave_chunks:
                # Find worker with lowest load
                min_worker = min(workers, key=lambda w: w.calculate_load())
                min_worker.chunks.append(chunk)
                chunk.worker_id = min_worker.worker_id

        # Update worker durations
        for worker in workers:
            worker.estimated_duration_minutes = worker.calculate_load()

        return workers

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _hash_requirements(self, requirements: list[dict]) -> str:
        """Generate hash for cache invalidation."""
        req_str = json.dumps(requirements, sort_keys=True)
        return hashlib.md5(req_str.encode()).hexdigest()[:12]

    def _parse_service_groups_response(self, response: str) -> list[ServiceGroup]:
        """Parse LLM response into ServiceGroup list."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group())
            groups = []

            for g in data.get("groups", []):
                groups.append(ServiceGroup(
                    service_name=g.get("service_name", "other"),
                    requirements=g.get("requirements", []),
                    estimated_files=g.get("estimated_files", []),
                    depends_on=g.get("depends_on", []),
                ))

            return groups
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning("parse_groups_failed", error=str(e))
            return []

    def _apply_complexity_scores(
        self,
        groups: list[ServiceGroup],
        response: str,
    ) -> list[ServiceGroup]:
        """Apply complexity scores from LLM response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return groups

            data = json.loads(json_match.group())
            scores = {s["service_name"]: s for s in data.get("scores", [])}

            for group in groups:
                if group.service_name in scores:
                    score_data = scores[group.service_name]
                    complexity_str = score_data.get("complexity", "medium")
                    group.complexity = ComplexityLevel(complexity_str)
                    group.estimated_minutes = score_data.get(
                        "estimated_minutes",
                        DEFAULT_TIME_ESTIMATES.get(group.complexity, 5)
                    )

            return groups
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning("apply_scores_failed", error=str(e))
            return groups

    def _parse_dependency_graph(self, response: str) -> dict[str, list[str]]:
        """Parse dependency graph from LLM response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return {}

            data = json.loads(json_match.group())
            return data.get("dependencies", {})
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning("parse_deps_failed", error=str(e))
            return {}


# Convenience function for quick usage
async def create_execution_plan(
    requirements: list[dict],
    max_concurrent: int = 5,
    llm_client=None,
) -> ExecutionPlan:
    """
    Create execution plan with default settings.

    Args:
        requirements: List of requirements from JSON
        max_concurrent: Maximum parallel workers
        llm_client: Optional LLM client for intelligent planning

    Returns:
        ExecutionPlan ready for execution
    """
    config = ChunkPlannerConfig(max_concurrent=max_concurrent)
    planner = ChunkPlannerAgent(config=config, llm_client=llm_client)
    return await planner.create_execution_plan(requirements)
