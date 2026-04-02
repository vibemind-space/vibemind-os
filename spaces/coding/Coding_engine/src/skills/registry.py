"""
Skill Registry.

Central registry for managing Agent Skills.
Maps events to skills, provides skill injection to agents.
"""

import structlog
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .skill import Skill
from .loader import SkillLoader

if TYPE_CHECKING:
    from src.mind.event_bus import EventType


logger = structlog.get_logger(__name__)


class SkillRegistry:
    """
    Central registry for all Agent Skills.

    Responsibilities:
    - Load skills from .claude/skills/ on initialization
    - Map events to skills for routing
    - Provide skill injection to agents
    - Track token usage (metadata vs full instructions)

    Usage:
        registry = SkillRegistry(project_root="./output")
        num_skills = registry.initialize()

        # Get skill by name
        skill = registry.get_skill("code-generation")

        # Get skills for an event
        skills = registry.get_skills_for_event(EventType.BUILD_FAILED)

        # Inject skill into agent
        agent.skill = registry.get_skill("code-generation")
    """

    # Default mapping of agent types to skill names
    AGENT_SKILL_MAPPING = {
        # Core Code Generation
        "Generator": "code-generation",
        "GeneratorAgent": "code-generation",

        # Validation & Testing
        "ValidationTeam": "validation",
        "ValidationTeamAgent": "validation",
        "TesterTeam": "test-generation",
        "TesterTeamAgent": "test-generation",

        # Deployment & Debugging
        "DeploymentTeam": "docker-sandbox",
        "DeploymentTeamAgent": "docker-sandbox",
        "ContinuousDebug": "debugging",
        "ContinuousDebugAgent": "debugging",

        # E2E & UX
        "PlaywrightE2E": "e2e-testing",
        "PlaywrightE2EAgent": "e2e-testing",
        "UXDesign": "ux-review",
        "UXDesignAgent": "ux-review",

        # Planning
        "ChunkPlanner": "chunk-planning",
        "ChunkPlannerAgent": "chunk-planning",

        # =========================================================================
        # Full-Stack Autonomy Agents (NEW - Database, API, Auth, Infrastructure)
        # =========================================================================

        # Database Schema Generation (Prisma, SQLAlchemy, Drizzle)
        "Database": "database-schema-generation",
        "DatabaseAgent": "database-schema-generation",
        "DatabaseSchemaAgent": "database-schema-generation",
        "SchemaGenerator": "database-schema-generation",

        # API Generation (REST endpoints from contracts)
        "API": "api-generation",
        "APIAgent": "api-generation",
        "APIGeneratorAgent": "api-generation",
        "RestAPIAgent": "api-generation",

        # Authentication & Authorization (JWT, OAuth2, RBAC)
        "Auth": "auth-setup",
        "AuthAgent": "auth-setup",
        "AuthSetupAgent": "auth-setup",
        "AuthenticationAgent": "auth-setup",
        "AuthorizationAgent": "auth-setup",
        "RBACAgent": "auth-setup",

        # Environment & Infrastructure (Docker, CI/CD, .env)
        "Infra": "environment-config",
        "InfraAgent": "environment-config",
        "InfrastructureAgent": "environment-config",
        "EnvironmentAgent": "environment-config",
        "ConfigAgent": "environment-config",
        "DockerConfigAgent": "environment-config",
        "CICDAgent": "environment-config",

        # =========================================================================
        # Security & Dependency Management (NEW - OWASP, npm audit, Licenses)
        # =========================================================================

        # Security Scanning (OWASP, Vulnerability Detection)
        "SecurityScanner": "security-scanning",
        "SecurityScannerAgent": "security-scanning",
        "SecurityAgent": "security-scanning",
        "VulnerabilityScanner": "security-scanning",

        # Dependency Management (npm audit, License Compliance)
        "DependencyManager": "dependency-management",
        "DependencyManagerAgent": "dependency-management",
        "DependencyAgent": "dependency-management",
        "PackageManager": "dependency-management",

        # =========================================================================
        # Performance, Accessibility & Documentation (NEW)
        # =========================================================================

        # Performance Analysis (Bundle Size, Lighthouse, Core Web Vitals)
        "Performance": "performance-analysis",
        "PerformanceAgent": "performance-analysis",
        "PerformanceAnalyzer": "performance-analysis",
        "BundleAnalyzer": "performance-analysis",

        # Accessibility Testing (WCAG, axe-core)
        "Accessibility": "accessibility-testing",
        "AccessibilityAgent": "accessibility-testing",
        "A11yAgent": "accessibility-testing",
        "WCAGAgent": "accessibility-testing",

        # API Documentation (OpenAPI, Swagger)
        "APIDocumentation": "api-documentation",
        "APIDocumentationAgent": "api-documentation",
        "SwaggerAgent": "api-documentation",
        "OpenAPIAgent": "api-documentation",

        # Database Migrations (Prisma, SQLAlchemy)
        "Migration": "database-migrations",
        "MigrationAgent": "database-migrations",
        "DBMigrationAgent": "database-migrations",

        # Localization (i18n, Translations)
        "Localization": "localization",
        "LocalizationAgent": "localization",
        "I18nAgent": "localization",
        "TranslationAgent": "localization",
    }

    def __init__(self, project_root: str | Path):
        """
        Initialize SkillRegistry.

        Args:
            project_root: Root directory containing .claude/skills/
        """
        self.project_root = Path(project_root)
        self.loader = SkillLoader(project_root)
        self._skills: dict[str, Skill] = {}
        self._event_to_skills: dict[str, list[str]] = {}
        self._initialized = False

    def initialize(self) -> int:
        """
        Load all skills and build event mappings.

        Returns:
            Number of skills loaded
        """
        if self._initialized:
            return len(self._skills)

        skills = self.loader.load_all_skills()

        for skill in skills:
            self._register_skill(skill)

        self._initialized = True

        logger.info(
            "skills_registry_initialized",
            skills_loaded=len(self._skills),
            total_metadata_tokens=self.total_metadata_tokens,
            event_mappings=len(self._event_to_skills),
        )

        return len(self._skills)

    def _register_skill(self, skill: Skill) -> None:
        """
        Register a skill and build event mapping.

        Args:
            skill: Skill to register
        """
        self._skills[skill.name] = skill

        # Build event-to-skill mapping
        for event in skill.trigger_events:
            event_key = event.upper()
            if event_key not in self._event_to_skills:
                self._event_to_skills[event_key] = []
            if skill.name not in self._event_to_skills[event_key]:
                self._event_to_skills[event_key].append(skill.name)

        logger.debug(
            "skill_registered",
            skill=skill.name,
            events=skill.trigger_events,
            tokens=skill.total_tokens,
        )

    def get_skill(self, name: str) -> Optional[Skill]:
        """
        Get a skill by name.

        Args:
            name: Skill name (e.g., "code-generation")

        Returns:
            Skill or None if not found
        """
        return self._skills.get(name)

    def get_skill_for_agent(self, agent_type: str) -> Optional[Skill]:
        """
        Get the appropriate skill for an agent type.

        Args:
            agent_type: Agent class name or type identifier

        Returns:
            Matching Skill or None
        """
        skill_name = self.AGENT_SKILL_MAPPING.get(agent_type)
        if skill_name:
            return self.get_skill(skill_name)
        return None

    def get_skills_for_event(self, event_type: "EventType | str") -> list[Skill]:
        """
        Find all skills that should trigger for an event.

        Args:
            event_type: EventType enum or string

        Returns:
            List of matching Skills
        """
        if hasattr(event_type, "value"):
            event_key = event_type.value.upper()
        else:
            event_key = str(event_type).upper()

        skill_names = self._event_to_skills.get(event_key, [])
        return [self._skills[n] for n in skill_names if n in self._skills]

    def get_skill_instructions(self, skill_name: str) -> str:
        """
        Get full instructions for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Full instruction text or empty string
        """
        skill = self.get_skill(skill_name)
        if skill:
            return skill.instructions
        return ""

    def get_skill_prompt(self, skill_name: str) -> str:
        """
        Get formatted prompt for a skill (full instructions).

        Args:
            skill_name: Name of the skill

        Returns:
            Formatted prompt or empty string
        """
        skill = self.get_skill(skill_name)
        if skill:
            return skill.get_full_prompt()
        return ""

    def list_skills_metadata(self) -> list[dict]:
        """
        Get metadata for all skills (low token cost).

        Returns:
            List of skill metadata dicts
        """
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "trigger_events": skill.trigger_events,
                "metadata_tokens": skill.metadata_tokens,
                "instruction_tokens": skill.instruction_tokens,
            }
            for skill in self._skills.values()
        ]

    def get_skills_summary(self) -> str:
        """
        Get a markdown summary of all available skills.

        Returns:
            Markdown-formatted summary
        """
        if not self._skills:
            return "No skills loaded."

        lines = ["## Available Skills\n"]
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            lines.append(skill.get_metadata_prompt())

        return "\n".join(lines)

    @property
    def all_skills(self) -> list[Skill]:
        """Get all registered skills."""
        return list(self._skills.values())

    @property
    def skill_names(self) -> list[str]:
        """Get all registered skill names."""
        return list(self._skills.keys())

    @property
    def total_metadata_tokens(self) -> int:
        """
        Total tokens for all skill metadata (always loaded).

        This is the baseline token cost for skill awareness.
        """
        return sum(s.metadata_tokens for s in self._skills.values())

    @property
    def total_instruction_tokens(self) -> int:
        """
        Total tokens for all skill instructions.

        This would be the cost if all skills were fully loaded.
        """
        return sum(s.instruction_tokens for s in self._skills.values())

    def get_event_skill_mapping(self) -> dict[str, list[str]]:
        """
        Get the full event-to-skill mapping.

        Returns:
            Dict mapping event names to list of skill names
        """
        return dict(self._event_to_skills)

    def __len__(self) -> int:
        return len(self._skills)

    def __repr__(self) -> str:
        return (
            f"SkillRegistry(skills={len(self._skills)}, "
            f"metadata_tokens={self.total_metadata_tokens})"
        )
