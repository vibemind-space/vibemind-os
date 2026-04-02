"""
InterpretationGenerator - Generate Interpretations for Ambiguous Requirements.

When ambiguities are detected, this generates possible interpretations
with trade-offs so the user can choose.

Each interpretation includes:
- A clear description of what it means
- Technical approach to implement it
- Trade-offs and complexity
"""

from dataclasses import dataclass, field
from typing import Optional

import structlog

from src.engine.ambiguity_detector import (
    AmbiguityType,
    DetectedAmbiguity,
)

logger = structlog.get_logger(__name__)


@dataclass
class Interpretation:
    """A possible interpretation of an ambiguous requirement."""

    id: str  # e.g., "AMB-0001-A"
    ambiguity_id: str  # Parent ambiguity ID
    label: str  # Short label (e.g., "JWT Authentication")
    description: str  # Full description of this interpretation
    technical_approach: str  # How it would be implemented
    trade_offs: list[str] = field(default_factory=list)
    complexity: str = "medium"  # "low", "medium", "high"
    is_recommended: bool = False  # Default recommendation
    likelihood_rank: int = 1  # 1 = most likely intended


@dataclass
class InterpretationSet:
    """Set of interpretations for a single ambiguity."""

    ambiguity: DetectedAmbiguity
    interpretations: list[Interpretation]
    recommended_id: Optional[str] = None  # ID of recommended interpretation

    @property
    def has_recommendation(self) -> bool:
        return self.recommended_id is not None


# Pre-defined interpretations for common ambiguities
VAGUE_TERM_INTERPRETATIONS: dict[str, list[dict]] = {
    "authentication": [
        {
            "label": "JWT + Session",
            "description": "JWT tokens with refresh tokens and session management",
            "technical_approach": "Use jose for JWT, HTTP-only cookies for refresh tokens",
            "trade_offs": ["More secure", "Requires more setup"],
            "complexity": "medium",
            "is_recommended": True,
        },
        {
            "label": "Simple JWT",
            "description": "Stateless JWT-only authentication",
            "technical_approach": "JWT stored in localStorage, no server-side sessions",
            "trade_offs": ["Simpler", "Less secure for sensitive apps"],
            "complexity": "low",
        },
        {
            "label": "OAuth2 Social Login",
            "description": "Login via Google, GitHub, etc.",
            "technical_approach": "Use next-auth or passport.js with OAuth providers",
            "trade_offs": ["No password management", "Depends on third parties"],
            "complexity": "medium",
        },
    ],
    "user_management": [
        {
            "label": "Full User System",
            "description": "Registration, login, profile, password reset, roles",
            "technical_approach": "User model with roles, email verification, profile editing",
            "trade_offs": ["Complete solution", "More development time"],
            "complexity": "high",
            "is_recommended": True,
        },
        {
            "label": "Basic Auth Only",
            "description": "Just login/logout, no registration",
            "technical_approach": "Admin-created users only, simple login form",
            "trade_offs": ["Simpler", "No self-registration"],
            "complexity": "low",
        },
        {
            "label": "Role-Based Access",
            "description": "Users with admin/user/viewer roles",
            "technical_approach": "RBAC with permission-based access control",
            "trade_offs": ["Flexible permissions", "More complex UI"],
            "complexity": "medium",
        },
    ],
    "real-time": [
        {
            "label": "WebSocket",
            "description": "Persistent WebSocket connection for live updates",
            "technical_approach": "socket.io or native WebSocket with heartbeat",
            "trade_offs": ["True real-time", "More infrastructure"],
            "complexity": "high",
            "is_recommended": True,
        },
        {
            "label": "Server-Sent Events",
            "description": "One-way server push for updates",
            "technical_approach": "SSE endpoint for streaming updates",
            "trade_offs": ["Simpler than WebSocket", "One-direction only"],
            "complexity": "medium",
        },
        {
            "label": "Polling",
            "description": "Regular interval API polling",
            "technical_approach": "setInterval with API calls every N seconds",
            "trade_offs": ["Simplest", "Not true real-time, more bandwidth"],
            "complexity": "low",
        },
    ],
    "dashboard": [
        {
            "label": "Analytics Dashboard",
            "description": "Charts, metrics, and KPIs with data visualization",
            "technical_approach": "Chart.js or Recharts with data aggregation APIs",
            "trade_offs": ["Rich visualization", "More complex backend"],
            "complexity": "high",
            "is_recommended": True,
        },
        {
            "label": "Simple Stats",
            "description": "Basic counts and lists without charts",
            "technical_approach": "Simple API returning aggregated numbers",
            "trade_offs": ["Quick to build", "Less visual"],
            "complexity": "low",
        },
        {
            "label": "Admin CRUD",
            "description": "Data management tables with filtering",
            "technical_approach": "DataTable with server-side pagination and filters",
            "trade_offs": ["Functional", "Not visual analytics"],
            "complexity": "medium",
        },
    ],
    "notifications": [
        {
            "label": "In-App Only",
            "description": "Notifications within the application",
            "technical_approach": "Notification component with unread count, mark-as-read",
            "trade_offs": ["No external dependencies", "Only visible in app"],
            "complexity": "low",
            "is_recommended": True,
        },
        {
            "label": "Email + In-App",
            "description": "Email notifications plus in-app",
            "technical_approach": "SendGrid/SES for email, in-app notification center",
            "trade_offs": ["Better reach", "Email setup required"],
            "complexity": "medium",
        },
        {
            "label": "Full Omnichannel",
            "description": "Email, SMS, push, and in-app",
            "technical_approach": "Notification service with multiple channels",
            "trade_offs": ["Maximum reach", "Complex and costly"],
            "complexity": "high",
        },
    ],
    "admin panel": [
        {
            "label": "Basic Admin",
            "description": "CRUD operations for main entities",
            "technical_approach": "Admin routes with data tables and forms",
            "trade_offs": ["Essential functionality", "Limited features"],
            "complexity": "low",
            "is_recommended": True,
        },
        {
            "label": "Full Admin Suite",
            "description": "Analytics, audit logs, user management, settings",
            "technical_approach": "Dedicated admin module with dashboard",
            "trade_offs": ["Comprehensive", "Significant dev time"],
            "complexity": "high",
        },
    ],
    "multi-tenant": [
        {
            "label": "Row-Level Isolation",
            "description": "Single DB, tenant_id on all rows",
            "technical_approach": "Add tenantId to all models, filter in queries",
            "trade_offs": ["Simple, cost-effective", "Shared infrastructure"],
            "complexity": "medium",
            "is_recommended": True,
        },
        {
            "label": "Schema-Level Isolation",
            "description": "Separate schema per tenant",
            "technical_approach": "Dynamic schema switching based on tenant",
            "trade_offs": ["Better isolation", "More complex migrations"],
            "complexity": "high",
        },
    ],
}

# Interpretations for technology choices
TECHNOLOGY_INTERPRETATIONS: dict[str, list[dict]] = {
    "database type": [
        {
            "label": "PostgreSQL",
            "description": "Relational database with strong consistency",
            "technical_approach": "Prisma ORM with PostgreSQL",
            "trade_offs": ["ACID compliance", "Requires setup"],
            "complexity": "medium",
            "is_recommended": True,
        },
        {
            "label": "SQLite",
            "description": "File-based database for simple projects",
            "technical_approach": "Prisma or Drizzle with SQLite",
            "trade_offs": ["Zero setup", "Limited concurrency"],
            "complexity": "low",
        },
        {
            "label": "MongoDB",
            "description": "Document database for flexible schemas",
            "technical_approach": "Mongoose or native MongoDB driver",
            "trade_offs": ["Flexible schema", "Eventual consistency"],
            "complexity": "medium",
        },
    ],
    "state management approach": [
        {
            "label": "Zustand",
            "description": "Lightweight state management",
            "technical_approach": "Zustand stores with TypeScript",
            "trade_offs": ["Simple API", "Less structured"],
            "complexity": "low",
            "is_recommended": True,
        },
        {
            "label": "Redux Toolkit",
            "description": "Full-featured state management",
            "technical_approach": "RTK with slices and thunks",
            "trade_offs": ["Powerful DevTools", "More boilerplate"],
            "complexity": "medium",
        },
        {
            "label": "React Context",
            "description": "Built-in React state sharing",
            "technical_approach": "Context + useReducer",
            "trade_offs": ["No dependencies", "Can cause re-renders"],
            "complexity": "low",
        },
    ],
    "styling approach": [
        {
            "label": "Tailwind CSS",
            "description": "Utility-first CSS framework",
            "technical_approach": "Tailwind with PostCSS",
            "trade_offs": ["Fast development", "Verbose classes"],
            "complexity": "low",
            "is_recommended": True,
        },
        {
            "label": "CSS Modules",
            "description": "Scoped CSS per component",
            "technical_approach": "*.module.css files",
            "trade_offs": ["No runtime", "More files"],
            "complexity": "low",
        },
        {
            "label": "Styled Components",
            "description": "CSS-in-JS with component styles",
            "technical_approach": "styled-components or emotion",
            "trade_offs": ["Dynamic styles", "Runtime overhead"],
            "complexity": "medium",
        },
    ],
    "API style": [
        {
            "label": "REST API",
            "description": "Traditional RESTful endpoints",
            "technical_approach": "Express/Fastify with resource routes",
            "trade_offs": ["Simple, well-understood", "Can be chatty"],
            "complexity": "low",
            "is_recommended": True,
        },
        {
            "label": "GraphQL",
            "description": "Flexible query language",
            "technical_approach": "Apollo Server with type definitions",
            "trade_offs": ["Flexible queries", "More complex setup"],
            "complexity": "high",
        },
        {
            "label": "tRPC",
            "description": "End-to-end type safety",
            "technical_approach": "tRPC with React Query",
            "trade_offs": ["Great DX", "TypeScript only"],
            "complexity": "medium",
        },
    ],
}


class InterpretationGenerator:
    """
    Generates possible interpretations for ambiguous requirements.

    For each ambiguity, creates 2-4 possible interpretations
    with descriptions, trade-offs, and recommendations.
    """

    def __init__(self) -> None:
        self.logger = logger.bind(component="InterpretationGenerator")

    def generate(
        self,
        ambiguities: list[DetectedAmbiguity],
    ) -> list[InterpretationSet]:
        """
        Generate interpretation sets for all ambiguities.

        Args:
            ambiguities: List of detected ambiguities

        Returns:
            List of InterpretationSets, one per ambiguity
        """
        results = []

        for ambiguity in ambiguities:
            interpretations = self._generate_for_ambiguity(ambiguity)
            if interpretations:
                recommended_id = self._find_recommended(interpretations)
                results.append(
                    InterpretationSet(
                        ambiguity=ambiguity,
                        interpretations=interpretations,
                        recommended_id=recommended_id,
                    )
                )

        self.logger.info(
            "interpretations_generated",
            ambiguities_processed=len(ambiguities),
            sets_created=len(results),
        )

        return results

    def _generate_for_ambiguity(
        self,
        ambiguity: DetectedAmbiguity,
    ) -> list[Interpretation]:
        """Generate interpretations for a single ambiguity."""
        interpretations = []
        term = ambiguity.detected_term.lower().replace(" ", "_").replace("-", "_")

        # Check pre-defined interpretations based on ambiguity type
        if ambiguity.ambiguity_type == AmbiguityType.VAGUE_TERM:
            if term in VAGUE_TERM_INTERPRETATIONS:
                interpretations = self._create_from_template(
                    ambiguity.id,
                    VAGUE_TERM_INTERPRETATIONS[term],
                )
        elif ambiguity.ambiguity_type == AmbiguityType.TECHNOLOGY_CHOICE:
            if term in TECHNOLOGY_INTERPRETATIONS:
                interpretations = self._create_from_template(
                    ambiguity.id,
                    TECHNOLOGY_INTERPRETATIONS[term],
                )

        # If no pre-defined, generate generic interpretations
        if not interpretations:
            interpretations = self._generate_generic(ambiguity)

        return interpretations

    def _create_from_template(
        self,
        ambiguity_id: str,
        templates: list[dict],
    ) -> list[Interpretation]:
        """Create Interpretation objects from template dicts."""
        interpretations = []

        for i, template in enumerate(templates):
            interp_id = f"{ambiguity_id}-{chr(65 + i)}"  # A, B, C, etc.
            interpretations.append(
                Interpretation(
                    id=interp_id,
                    ambiguity_id=ambiguity_id,
                    label=template.get("label", f"Option {i + 1}"),
                    description=template.get("description", ""),
                    technical_approach=template.get("technical_approach", ""),
                    trade_offs=template.get("trade_offs", []),
                    complexity=template.get("complexity", "medium"),
                    is_recommended=template.get("is_recommended", False),
                    likelihood_rank=i + 1,
                )
            )

        return interpretations

    def _generate_generic(
        self,
        ambiguity: DetectedAmbiguity,
    ) -> list[Interpretation]:
        """Generate generic interpretations when no template exists."""
        # Create simple minimal/standard/comprehensive options
        return [
            Interpretation(
                id=f"{ambiguity.id}-A",
                ambiguity_id=ambiguity.id,
                label="Minimal Implementation",
                description=f"Basic implementation of {ambiguity.detected_term}",
                technical_approach="Implement core functionality only",
                trade_offs=["Quick to build", "May need expansion later"],
                complexity="low",
                is_recommended=True,
                likelihood_rank=1,
            ),
            Interpretation(
                id=f"{ambiguity.id}-B",
                ambiguity_id=ambiguity.id,
                label="Standard Implementation",
                description=f"Balanced implementation of {ambiguity.detected_term}",
                technical_approach="Implement common patterns and features",
                trade_offs=["Good balance", "Moderate effort"],
                complexity="medium",
                likelihood_rank=2,
            ),
            Interpretation(
                id=f"{ambiguity.id}-C",
                ambiguity_id=ambiguity.id,
                label="Comprehensive Implementation",
                description=f"Full-featured implementation of {ambiguity.detected_term}",
                technical_approach="Implement all anticipated features",
                trade_offs=["Complete solution", "More development time"],
                complexity="high",
                likelihood_rank=3,
            ),
        ]

    def _find_recommended(
        self,
        interpretations: list[Interpretation],
    ) -> Optional[str]:
        """Find the recommended interpretation ID."""
        for interp in interpretations:
            if interp.is_recommended:
                return interp.id

        # Default to first if none marked
        return interpretations[0].id if interpretations else None

    def format_for_user(
        self,
        interpretation_sets: list[InterpretationSet],
    ) -> str:
        """Format interpretation sets as user-friendly text."""
        if not interpretation_sets:
            return "No interpretations generated."

        lines = ["# Clarification Required\n"]
        lines.append("Please choose an interpretation for each ambiguous requirement:\n")

        for i, iset in enumerate(interpretation_sets, 1):
            lines.append(f"## {i}. {iset.ambiguity.description}\n")
            lines.append(f"*Requirement: {iset.ambiguity.requirement_text[:100]}...*\n")

            for interp in iset.interpretations:
                recommended = " **(Recommended)**" if interp.is_recommended else ""
                lines.append(f"### [{interp.id}] {interp.label}{recommended}")
                lines.append(f"{interp.description}")
                lines.append(f"- Approach: {interp.technical_approach}")
                lines.append(f"- Complexity: {interp.complexity}")
                if interp.trade_offs:
                    lines.append(f"- Trade-offs: {'; '.join(interp.trade_offs)}")
                lines.append("")

            lines.append("---\n")

        return "\n".join(lines)

    def get_interpretation_by_id(
        self,
        interpretation_sets: list[InterpretationSet],
        interpretation_id: str,
    ) -> Optional[Interpretation]:
        """Find a specific interpretation by ID."""
        for iset in interpretation_sets:
            for interp in iset.interpretations:
                if interp.id == interpretation_id:
                    return interp
        return None

    def apply_selections(
        self,
        interpretation_sets: list[InterpretationSet],
        selections: dict[str, str],  # ambiguity_id -> interpretation_id
    ) -> dict[str, Interpretation]:
        """
        Apply user selections and return the chosen interpretations.

        Args:
            interpretation_sets: All generated interpretation sets
            selections: Map of ambiguity_id to chosen interpretation_id

        Returns:
            Map of ambiguity_id to selected Interpretation
        """
        results = {}

        for iset in interpretation_sets:
            amb_id = iset.ambiguity.id
            selected_id = selections.get(amb_id)

            if selected_id:
                # Find the selected interpretation
                for interp in iset.interpretations:
                    if interp.id == selected_id:
                        results[amb_id] = interp
                        break
            elif iset.recommended_id:
                # Use recommended if no selection
                for interp in iset.interpretations:
                    if interp.id == iset.recommended_id:
                        results[amb_id] = interp
                        break

        return results
