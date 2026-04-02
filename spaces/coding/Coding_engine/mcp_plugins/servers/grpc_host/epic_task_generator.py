#!/usr/bin/env python3
"""
Epic Task Generator - Phase 3.5 Enhanced

Generiert GRANULARE Tasks basierend auf echten Daten aus dem Projekt.

Features:
- Parst api_documentation.md für API-spezifische Tasks
- Parst test_documentation.md für Test-spezifische Tasks
- Generiert ~1270 Tasks statt 133 (granular pro Entity/API/Scenario)
- Vollständige Traceability: Requirement → Entity → API → Test
- Mermaid-Diagramme für Visualisierung
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

# Import our parsers
try:
    from epic_parser import Epic, EpicParser, UserStory
    from api_documentation_parser import APIDocumentationParser, APIEndpoint
    from test_documentation_parser import TestDocumentationParser, GherkinFeature, GherkinScenario
    from env_requirements_parser import EnvRequirementsParser, EnvRequirement
except ImportError:
    from mcp_plugins.servers.grpc_host.epic_parser import Epic, EpicParser, UserStory
    from mcp_plugins.servers.grpc_host.api_documentation_parser import APIDocumentationParser, APIEndpoint
    from mcp_plugins.servers.grpc_host.test_documentation_parser import TestDocumentationParser, GherkinFeature, GherkinScenario
    from mcp_plugins.servers.grpc_host.env_requirements_parser import EnvRequirementsParser, EnvRequirement

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Granulare Task-Typen für die Generierung - Phase 3.6 Extended"""

    # =========================================================================
    # Phase 0: Setup Tasks (am Anfang, nur für EPIC-001)
    # =========================================================================
    SETUP_PROJECT = "setup_project"         # npm init, package.json
    SETUP_ENV = "setup_env"                 # .env Datei erstellen
    SETUP_SECRETS = "setup_secrets"         # User für Secrets fragen
    SETUP_DATABASE = "setup_database"       # DB Connection String
    SETUP_DOCKER = "setup_docker"           # docker-compose.yml
    SETUP_DEPENDENCIES = "setup_deps"       # npm install

    # =========================================================================
    # Phase 1: Schema Tasks (pro Entity)
    # =========================================================================
    SCHEMA_MODEL = "schema_model"           # Prisma model erstellen
    SCHEMA_RELATIONS = "schema_relations"   # Relations definieren
    SCHEMA_MIGRATION = "schema_migration"   # Migration ausführen

    # =========================================================================
    # Phase 2: API Tasks (pro Endpoint)
    # =========================================================================
    API_CONTROLLER = "api_controller"       # Controller method
    API_SERVICE = "api_service"             # Service method
    API_DTO = "api_dto"                     # Request/Response DTO
    API_GUARD = "api_guard"                 # Auth guard
    API_VALIDATION = "api_validation"       # Input validation

    # =========================================================================
    # Phase 3: Frontend Tasks (pro User Story)
    # =========================================================================
    FE_PAGE = "fe_page"                     # Page component
    FE_COMPONENT = "fe_component"           # Reusable component
    FE_HOOK = "fe_hook"                     # Custom hook
    FE_API_CLIENT = "fe_api_client"         # API client call
    FE_FORM = "fe_form"                     # Form component

    # =========================================================================
    # Phase 4: Test Tasks (pro Scenario)
    # =========================================================================
    TEST_UNIT = "test_unit"                 # Unit test
    TEST_INTEGRATION = "test_integration"   # Integration test
    TEST_E2E_HAPPY = "test_e2e_happy"       # E2E happy path
    TEST_E2E_NEGATIVE = "test_e2e_negative" # E2E negative case
    TEST_E2E_BOUNDARY = "test_e2e_boundary" # E2E boundary case

    # =========================================================================
    # Docker Tasks (Container Management)
    # =========================================================================
    DOCKER_BUILD = "docker_build"           # Container bauen
    DOCKER_START = "docker_start"           # Container starten
    DOCKER_HEALTH = "docker_health"         # Health Check
    DOCKER_LOGS = "docker_logs"             # Logs prüfen
    DOCKER_STOP = "docker_stop"             # Container stoppen

    # =========================================================================
    # Verification Tasks (nach jeder Phase)
    # =========================================================================
    VERIFY_SCHEMA = "verify_schema"         # prisma validate
    VERIFY_BUILD = "verify_build"           # npm run build
    VERIFY_LINT = "verify_lint"             # eslint
    VERIFY_TYPECHECK = "verify_typecheck"   # tsc --noEmit
    VERIFY_UNIT_TESTS = "verify_unit"       # vitest run
    VERIFY_INTEGRATION = "verify_integration"  # API Tests
    VERIFY_E2E = "verify_e2e"               # Playwright E2E

    # =========================================================================
    # Checkpoint Tasks (User-Approval)
    # =========================================================================
    CHECKPOINT_SCHEMA = "checkpoint_schema" # Nach Schema: User prüft
    CHECKPOINT_API = "checkpoint_api"       # Nach API: User prüft
    CHECKPOINT_FRONTEND = "checkpoint_fe"   # Nach Frontend: User prüft
    CHECKPOINT_DEPLOY = "checkpoint_deploy" # Vor Deploy: User prüft

    # =========================================================================
    # Notification Tasks (User-Input nötig)
    # =========================================================================
    NOTIFY_SECRET_NEEDED = "notify_secret"  # Secret fehlt
    NOTIFY_CONFIG_NEEDED = "notify_config"  # Config fehlt
    NOTIFY_REVIEW_NEEDED = "notify_review"  # Code Review nötig
    NOTIFY_ERROR = "notify_error"           # Fehler aufgetreten

    # =========================================================================
    # Legacy types (for backwards compatibility)
    # =========================================================================
    SCHEMA = "schema"
    API = "api"
    FRONTEND = "frontend"
    TEST = "test"
    INTEGRATION = "integration"


class TaskStatus(Enum):
    """Task-Status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskPhase(Enum):
    """Task-Phasen für Gruppierung"""
    SETUP = "setup"                 # Phase 0: Project Setup
    SCHEMA = "schema"               # Phase 1: Database Schema
    API = "api"                     # Phase 2: Backend APIs
    FRONTEND = "frontend"           # Phase 3: Frontend Components
    TEST = "test"                   # Phase 4: Testing
    VERIFICATION = "verification"   # Phase 5: Build + TypeCheck
    DEPLOY = "deploy"               # Phase 6: Deployment


@dataclass
class Task:
    """Einzelne Task - Phase 3.6 Extended"""
    id: str
    epic_id: str
    type: str  # TaskType.value
    title: str
    description: str
    status: str = "pending"  # TaskStatus.value
    dependencies: List[str] = field(default_factory=list)
    estimated_minutes: int = 5
    actual_minutes: Optional[int] = None
    error_message: Optional[str] = None
    output_files: List[str] = field(default_factory=list)
    related_requirements: List[str] = field(default_factory=list)
    related_user_stories: List[str] = field(default_factory=list)

    # Phase 3.6: Extended Fields
    requires_user_input: bool = False       # Braucht User-Eingabe
    user_prompt: Optional[str] = None       # Frage an User
    user_response: Optional[str] = None     # Antwort vom User
    checkpoint: bool = False                # Ist Checkpoint-Task
    auto_retry: bool = True                 # Bei Fehler auto-retry?
    max_retries: int = 3                    # Max Retry-Versuche
    retry_count: int = 0                    # Aktuelle Retry-Anzahl
    timeout_seconds: int = 300              # Task-Timeout
    phase: str = "code"                     # setup, schema, api, frontend, test, deploy
    command: Optional[str] = None           # Shell-Befehl (für Verify/Docker Tasks)
    success_criteria: Optional[str] = None  # Wie wird Erfolg gemessen?

    # Phase 22: Dashboard Task UI Fields
    tested: bool = False                              # True when related test task passes
    user_fix_instructions: Optional[str] = None       # User-provided fix context for reruns

    # Phase 29: Task Enrichment Context
    enrichment_context: Optional[Dict[str, Any]] = None  # Diagrams, gaps, DTOs from docs


@dataclass
class EpicTaskList:
    """Task-Liste fuer einen Epic"""
    epic_id: str
    epic_name: str
    tasks: List[Task] = field(default_factory=list)
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    progress_percent: float = 0.0
    run_count: int = 0
    last_run_at: Optional[str] = None
    created_at: str = ""
    estimated_total_minutes: int = 0


class EpicTaskGenerator:
    """
    Generiert GRANULARE Tasks fuer jeden Epic.

    Phase 3.5 Enhanced Version:
    - Nutzt APIDocumentationParser für API-Tasks (359 Endpoints)
    - Nutzt TestDocumentationParser für Test-Tasks (1130 Test Cases)
    - Generiert ~1270 Tasks mit vollständiger Traceability

    Erstellt strukturierte Task-Listen basierend auf:
    - User Stories aus dem Epic
    - Entities aus dem Data Dictionary
    - API Endpoints aus api_documentation.md
    - Test Scenarios aus test_documentation.md
    """

    # Zeit-Schaetzungen pro Task-Typ (Minuten) - Phase 3.6 Extended
    TASK_ESTIMATES = {
        # =====================================================================
        # Setup Tasks (Phase 0)
        # =====================================================================
        TaskType.SETUP_PROJECT: 2,
        TaskType.SETUP_ENV: 3,
        TaskType.SETUP_SECRETS: 5,      # User-Input Zeit
        TaskType.SETUP_DATABASE: 3,
        TaskType.SETUP_DOCKER: 5,
        TaskType.SETUP_DEPENDENCIES: 10,

        # =====================================================================
        # Schema Tasks (Phase 1)
        # =====================================================================
        TaskType.SCHEMA_MODEL: 5,
        TaskType.SCHEMA_RELATIONS: 3,
        TaskType.SCHEMA_MIGRATION: 2,

        # =====================================================================
        # API Tasks (Phase 2)
        # =====================================================================
        TaskType.API_CONTROLLER: 10,
        TaskType.API_SERVICE: 8,
        TaskType.API_DTO: 5,
        TaskType.API_GUARD: 5,
        TaskType.API_VALIDATION: 5,

        # =====================================================================
        # Frontend Tasks (Phase 3)
        # =====================================================================
        TaskType.FE_PAGE: 20,
        TaskType.FE_COMPONENT: 15,
        TaskType.FE_HOOK: 10,
        TaskType.FE_API_CLIENT: 5,
        TaskType.FE_FORM: 15,

        # =====================================================================
        # Test Tasks (Phase 4)
        # =====================================================================
        TaskType.TEST_UNIT: 5,
        TaskType.TEST_INTEGRATION: 10,
        TaskType.TEST_E2E_HAPPY: 15,
        TaskType.TEST_E2E_NEGATIVE: 10,
        TaskType.TEST_E2E_BOUNDARY: 10,

        # =====================================================================
        # Docker Tasks
        # =====================================================================
        TaskType.DOCKER_BUILD: 5,
        TaskType.DOCKER_START: 2,
        TaskType.DOCKER_HEALTH: 1,
        TaskType.DOCKER_LOGS: 1,
        TaskType.DOCKER_STOP: 1,

        # =====================================================================
        # Verification Tasks
        # =====================================================================
        TaskType.VERIFY_SCHEMA: 1,
        TaskType.VERIFY_BUILD: 3,
        TaskType.VERIFY_LINT: 2,
        TaskType.VERIFY_TYPECHECK: 2,
        TaskType.VERIFY_UNIT_TESTS: 5,
        TaskType.VERIFY_INTEGRATION: 10,
        TaskType.VERIFY_E2E: 15,

        # =====================================================================
        # Checkpoint Tasks (Wartezeit auf User)
        # =====================================================================
        TaskType.CHECKPOINT_SCHEMA: 5,
        TaskType.CHECKPOINT_API: 10,
        TaskType.CHECKPOINT_FRONTEND: 10,
        TaskType.CHECKPOINT_DEPLOY: 15,

        # =====================================================================
        # Notification Tasks
        # =====================================================================
        TaskType.NOTIFY_SECRET_NEEDED: 5,
        TaskType.NOTIFY_CONFIG_NEEDED: 3,
        TaskType.NOTIFY_REVIEW_NEEDED: 10,
        TaskType.NOTIFY_ERROR: 2,

        # =====================================================================
        # Legacy types (backwards compatibility)
        # =====================================================================
        TaskType.SCHEMA: 5,
        TaskType.API: 15,
        TaskType.FRONTEND: 20,
        TaskType.TEST: 10,
        TaskType.INTEGRATION: 15,
    }

    def __init__(self, project_path: str, granular: bool = True, consolidation_mode: str = "feature"):
        """
        Args:
            project_path: Pfad zum Input-Projekt
            granular: If True, use granular task generation (Phase 3.5)
            consolidation_mode: How to group API tasks:
                "granular" = 5 tasks per endpoint (controller/service/dto/guard/validation) — original
                "endpoint" = 1 task per endpoint (all layers in one task)
                "feature" = 1 task per feature group (all auth endpoints in one task) — RECOMMENDED
        """
        self.project_path = Path(project_path)
        self.parser = EpicParser(str(project_path))
        self.granular = granular
        self.consolidation_mode = consolidation_mode

        # Initialize enhanced parsers for granular mode
        self.api_parser: Optional[APIDocumentationParser] = None
        self.test_parser: Optional[TestDocumentationParser] = None
        self.env_parser: Optional[EnvRequirementsParser] = None

        if self.granular:
            try:
                self.api_parser = APIDocumentationParser(str(project_path))
                self.test_parser = TestDocumentationParser(str(project_path))
                self.env_parser = EnvRequirementsParser(str(project_path))
                logger.info("Granular mode enabled with API, Test, and Env parsers")
            except Exception as e:
                logger.warning(f"Could not initialize enhanced parsers: {e}")
                self.granular = False

        logger.info(f"EpicTaskGenerator initialized for: {project_path} (granular={self.granular})")

    def generate_tasks_for_epic(self, epic_id: str) -> EpicTaskList:
        """
        Generiert alle Tasks fuer einen spezifischen Epic.

        In granular mode (Phase 3.5):
        - Parses actual API endpoints from api_documentation.md
        - Parses actual test scenarios from test_documentation.md
        - Generates ~80-300 tasks per Epic

        Args:
            epic_id: z.B. "EPIC-001"

        Returns:
            EpicTaskList mit allen generierten Tasks
        """
        epic = self.parser.get_epic_by_id(epic_id)
        if not epic:
            raise ValueError(f"Epic not found: {epic_id}")

        if self.granular and self.api_parser and self.test_parser:
            return self._generate_granular_tasks(epic)
        else:
            return self._generate_legacy_tasks(epic)

    def _generate_granular_tasks(self, epic: Epic) -> EpicTaskList:
        """
        Generiert GRANULARE Tasks aus echten Daten - Phase 3.6 Extended.

        Task breakdown per Epic:
        - Setup: 6 tasks (project, env, secrets, database, docker, deps) - nur EPIC-001
        - Schema: 3 tasks per Entity (model, relations, migration)
        - Verify Schema: 1 task (prisma validate)
        - Checkpoint Schema: 1 task (user approval)
        - API: 5 tasks per Endpoint (controller, service, dto, guard, validation)
        - Verify API: 3 tasks (build, typecheck, integration)
        - Docker API: 3 tasks (build, start, health)
        - Checkpoint API: 1 task (user approval)
        - Frontend: 5 tasks per User Story (page, component, hook, api_client, form)
        - Verify Frontend: 4 tasks (build, lint, typecheck, unit)
        - Checkpoint Frontend: 1 task (user approval)
        - Tests: 1 task per Gherkin Scenario (happy, negative, boundary)
        - Verify E2E: 1 task (playwright)
        - Docker Deploy: 4 tasks (build-prod, start-prod, health-prod, logs)
        - Checkpoint Deploy: 1 task (final approval)
        """
        tasks: List[Task] = []

        # =====================================================================
        # PHASE 0: SETUP (nur für EPIC-001)
        # =====================================================================
        setup_tasks = self._generate_setup_tasks(epic)
        tasks.extend(setup_tasks)
        setup_task_ids = [t.id for t in setup_tasks]

        # Determine first dependency for schema tasks
        if setup_task_ids:
            schema_deps = [setup_task_ids[-1]]  # Last setup task
        else:
            schema_deps = []

        # =====================================================================
        # PHASE 1: SCHEMA
        # =====================================================================
        schema_tasks = self._generate_granular_schema_tasks(epic)
        # Add setup dependency to first schema task
        for task in schema_tasks:
            if not task.dependencies and schema_deps:
                task.dependencies = schema_deps
        tasks.extend(schema_tasks)
        schema_task_ids = [t.id for t in schema_tasks]

        # =====================================================================
        # PHASE 2: API (depends on schema)
        # =====================================================================
        api_tasks = self._generate_granular_api_tasks(epic, schema_task_ids[-1:] if schema_task_ids else schema_deps)
        tasks.extend(api_tasks)
        api_task_ids = [t.id for t in api_tasks]

        # =====================================================================
        # PHASE 3: FRONTEND (depends on API)
        # =====================================================================
        fe_deps = api_task_ids[-1:] if api_task_ids else schema_task_ids[-1:]
        if self.consolidation_mode == "feature":
            frontend_tasks = self._generate_feature_consolidated_frontend_tasks(epic, fe_deps)
        else:
            frontend_tasks = self._generate_granular_frontend_tasks(epic, fe_deps)
        tasks.extend(frontend_tasks)
        frontend_task_ids = [t.id for t in frontend_tasks]

        # =====================================================================
        # PHASE 4: TESTS (depends on frontend)
        # =====================================================================
        test_deps = frontend_task_ids[-1:] if frontend_task_ids else api_task_ids[-1:]
        if self.consolidation_mode == "feature":
            test_tasks = self._generate_feature_consolidated_test_tasks(epic, test_deps)
        else:
            test_tasks = self._generate_granular_test_tasks(epic, test_deps)
        tasks.extend(test_tasks)
        test_task_ids = [t.id for t in test_tasks]

        # =====================================================================
        # PHASE 5: SINGLE VERIFICATION (replaces per-phase verify+docker+checkpoint)
        # One verify task at the end: tsc + build + prisma generate
        # This replaces ~13 overhead tasks per epic with 1.
        # =====================================================================
        all_code_ids = schema_task_ids + api_task_ids + frontend_task_ids + test_task_ids
        verify_task = Task(
            id=f"{epic.id}-VERIFY-all",
            epic_id=epic.id,
            type=TaskType.VERIFY_BUILD.value,
            title=f"Verify {epic.id}: build + typecheck",
            description=(
                f"Run all verification steps for {epic.id}:\n"
                f"1. npx prisma generate\n"
                f"2. npx tsc --noEmit (must pass with 0 errors)\n"
                f"3. npm run build\n"
                f"4. cd frontend && npx vite build (if frontend exists)\n"
                f"Fix any errors found."
            ),
            status=TaskStatus.PENDING.value,
            dependencies=all_code_ids[-3:] if all_code_ids else [],
            estimated_minutes=5,
            phase=TaskPhase.VERIFICATION.value,
            command="npx tsc --noEmit && npm run build",
            success_criteria="Zero TypeScript errors, build succeeds"
        )
        tasks.append(verify_task)

        # Integration task depends on verify
        integration_task = self._generate_integration_task(epic, [verify_task.id])
        tasks.append(integration_task)

        # Calculate totals
        total_estimated = sum(t.estimated_minutes for t in tasks)

        task_list = EpicTaskList(
            epic_id=epic.id,
            epic_name=epic.name,
            tasks=tasks,
            total_tasks=len(tasks),
            completed_tasks=0,
            failed_tasks=0,
            progress_percent=0.0,
            run_count=0,
            last_run_at=None,
            created_at=datetime.now().isoformat(),
            estimated_total_minutes=total_estimated
        )

        logger.info(f"Generated {len(tasks)} GRANULAR tasks for {epic.id} (est. {total_estimated} min)")
        return task_list

    def _generate_legacy_tasks(self, epic: Epic) -> EpicTaskList:
        """Legacy task generation (Phase 3 style)"""
        tasks: List[Task] = []

        # 1. Schema Tasks (fuer jede Entity)
        schema_tasks = self._generate_schema_tasks(epic)
        tasks.extend(schema_tasks)
        schema_task_ids = [t.id for t in schema_tasks]

        # 2. API Tasks (fuer jeden Endpoint oder User Story)
        api_tasks = self._generate_api_tasks(epic, schema_task_ids)
        tasks.extend(api_tasks)
        api_task_ids = [t.id for t in api_tasks]

        # 3. Frontend Tasks (fuer jeden User Story)
        frontend_tasks = self._generate_frontend_tasks(epic, api_task_ids)
        tasks.extend(frontend_tasks)
        frontend_task_ids = [t.id for t in frontend_tasks]

        # 4. Test Tasks
        test_tasks = self._generate_test_tasks(epic, frontend_task_ids + api_task_ids)
        tasks.extend(test_tasks)

        # 5. Integration Task (am Ende)
        integration_task = self._generate_integration_task(epic, [t.id for t in tasks])
        tasks.append(integration_task)

        # Calculate totals
        total_estimated = sum(t.estimated_minutes for t in tasks)

        task_list = EpicTaskList(
            epic_id=epic.id,
            epic_name=epic.name,
            tasks=tasks,
            total_tasks=len(tasks),
            completed_tasks=0,
            failed_tasks=0,
            progress_percent=0.0,
            run_count=0,
            last_run_at=None,
            created_at=datetime.now().isoformat(),
            estimated_total_minutes=total_estimated
        )

        logger.info(f"Generated {len(tasks)} legacy tasks for {epic.id} (est. {total_estimated} min)")
        return task_list

    def _generate_granular_schema_tasks(self, epic: Epic) -> List[Task]:
        """Generate ONE consolidated schema task per Epic instead of 3 per entity.

        Previously: 3 tasks per entity (model, relations, migration) = 51 tasks for 17 entities.
        Now: 1 task per epic that creates ALL models + relations + runs migration.
        This reduces schema tasks from ~51 to ~7 (one per epic).
        """
        tasks = []
        processed_entities: Set[str] = set()
        entity_list = []

        for entity in epic.entities:
            if entity in processed_entities:
                continue
            processed_entities.add(entity)
            entity_list.append(entity)

        if not entity_list:
            return tasks

        entities_str = ", ".join(entity_list)
        entity_descriptions = "\n".join(
            f"- {entity}: Define model with all attributes, types, and relations to other entities"
            for entity in entity_list
        )

        # ONE consolidated schema task for the entire epic
        tasks.append(Task(
            id=f"{epic.id}-SCHEMA-all",
            epic_id=epic.id,
            type=TaskType.SCHEMA_MODEL.value,
            title=f"Prisma schema: {entities_str[:80]}{'...' if len(entities_str) > 80 else ''}",
            description=(
                f"Create ALL Prisma models for {epic.id} in prisma/schema.prisma.\n\n"
                f"Models to create:\n{entity_descriptions}\n\n"
                f"Include:\n"
                f"- All model fields with correct Prisma types (@id, @default, @unique, @db.*)\n"
                f"- All relations between models (1:1, 1:N, N:M)\n"
                f"- @@map() table name annotations\n"
                f"- Run: npx prisma generate after schema changes"
            ),
            status=TaskStatus.PENDING.value,
            dependencies=[],
            estimated_minutes=max(5, len(entity_list) * 2),
            related_requirements=[r for r in epic.requirements][:5],
            output_files=["prisma/schema.prisma"]
        ))

        return tasks

    def _generate_granular_api_tasks(self, epic: Epic, schema_dependencies: List[str]) -> List[Task]:
        """Generiert API Tasks — consolidation_mode bestimmt Granularität."""

        # ── Feature-Consolidation: 1 Task pro Feature-Gruppe ──
        if self.consolidation_mode == "feature":
            return self._generate_feature_consolidated_api_tasks(epic, schema_dependencies)

        # ── Endpoint-Consolidation: 1 Task pro Endpoint ──
        if self.consolidation_mode == "endpoint":
            return self._generate_endpoint_consolidated_api_tasks(epic, schema_dependencies)

        # ── Granular (original): 5 Tasks pro Endpoint ──
        return self._generate_granular_api_tasks_original(epic, schema_dependencies)

    def _generate_feature_consolidated_api_tasks(self, epic: Epic, schema_dependencies: List[str]) -> List[Task]:
        """1 Task pro Feature-Gruppe (z.B. alle /auth/* Endpoints in einem Task)."""
        tasks = []
        if not self.api_parser:
            return self._generate_api_tasks(epic, schema_dependencies)

        # Collect all endpoints for this epic
        all_endpoints = []
        for req in epic.requirements:
            endpoints = self.api_parser.get_endpoints_by_requirement(req)
            all_endpoints.extend(endpoints)

        # Group by resource (URL path segment 3: /api/v1/{resource}/...)
        from collections import defaultdict
        groups = defaultdict(list)
        seen = set()
        for ep in all_endpoints:
            key = f"{ep.method}_{ep.path}"
            if key in seen:
                continue
            seen.add(key)
            groups[ep.resource].append(ep)

        # 1 task per feature group
        for resource, endpoints in groups.items():
            methods = ", ".join(sorted(set(f"{e.method}" for e in endpoints)))
            all_paths = "\n".join(f"  {e.method} {e.path} — {e.summary}" for e in endpoints)
            all_reqs = list(set(e.requirement for e in endpoints if e.requirement))

            tasks.append(Task(
                id=f"{epic.id}-API-{resource}-feature",
                epic_id=epic.id,
                type=TaskType.API_CONTROLLER.value,
                title=f"Feature: {resource} ({len(endpoints)} endpoints: {methods})",
                description=(
                    f"Generate the COMPLETE NestJS module for '{resource}' with ALL layers:\n"
                    f"- Controller (all {len(endpoints)} endpoints)\n"
                    f"- Service (business logic)\n"
                    f"- DTOs (request/response types)\n"
                    f"- Guards (JWT auth where needed)\n"
                    f"- Validators (input validation)\n"
                    f"- Module registration\n\n"
                    f"Endpoints:\n{all_paths}"
                ),
                status=TaskStatus.PENDING.value,
                dependencies=schema_dependencies[:3] if schema_dependencies else [],
                estimated_minutes=max(10, len(endpoints) * 3),
                related_requirements=all_reqs[:5],
                output_files=[
                    f"src/modules/{resource}/{resource}.controller.ts",
                    f"src/modules/{resource}/{resource}.service.ts",
                    f"src/modules/{resource}/{resource}.module.ts",
                    f"src/modules/{resource}/dto/",
                ]
            ))

        logger.info(f"Feature consolidation: {len(all_endpoints)} endpoints → {len(tasks)} feature tasks")
        return tasks

    def _generate_endpoint_consolidated_api_tasks(self, epic: Epic, schema_dependencies: List[str]) -> List[Task]:
        """1 Task pro Endpoint (controller+service+dto+guard in einem Task)."""
        tasks = []
        if not self.api_parser:
            return self._generate_api_tasks(epic, schema_dependencies)

        processed = set()
        for req in epic.requirements:
            endpoints = self.api_parser.get_endpoints_by_requirement(req)
            for endpoint in endpoints:
                key = f"{endpoint.method}_{endpoint.path}"
                if key in processed:
                    continue
                processed.add(key)

                tasks.append(Task(
                    id=f"{epic.id}-API-{endpoint.method}-{endpoint.safe_id}",
                    epic_id=epic.id,
                    type=TaskType.API_CONTROLLER.value,
                    title=f"Endpoint: {endpoint.method} {endpoint.path}",
                    description=(
                        f"{endpoint.summary}\n\n"
                        f"Generate ALL layers for this endpoint:\n"
                        f"- Controller method\n"
                        f"- Service method with business logic\n"
                        f"- Request/Response DTOs\n"
                        f"- Auth guard (if 401 response)\n"
                        f"- Input validation\n"
                    ),
                    status=TaskStatus.PENDING.value,
                    dependencies=schema_dependencies[:3] if schema_dependencies else [],
                    estimated_minutes=8,
                    related_requirements=[endpoint.requirement],
                    output_files=[
                        f"src/modules/{endpoint.resource}/{endpoint.resource}.controller.ts",
                        f"src/modules/{endpoint.resource}/{endpoint.resource}.service.ts",
                    ]
                ))

        logger.info(f"Endpoint consolidation: {len(processed)} endpoints → {len(tasks)} tasks")
        return tasks

    def _generate_granular_api_tasks_original(self, epic: Epic, schema_dependencies: List[str]) -> List[Task]:
        """Original granulare Tasks — 5 Tasks pro API Endpoint."""
        tasks = []
        processed_endpoints: Set[str] = set()

        if not self.api_parser:
            return self._generate_api_tasks(epic, schema_dependencies)

        # Get actual endpoints from api_documentation.md
        for req in epic.requirements:
            endpoints = self.api_parser.get_endpoints_by_requirement(req)

            for endpoint in endpoints:
                endpoint_key = f"{endpoint.method}_{endpoint.path}"
                if endpoint_key in processed_endpoints:
                    continue
                processed_endpoints.add(endpoint_key)

                safe_id = endpoint.safe_id

                # Task 1: Controller
                tasks.append(Task(
                    id=f"{epic.id}-API-{endpoint.method}-{safe_id}-controller",
                    epic_id=epic.id,
                    type=TaskType.API_CONTROLLER.value,
                    title=f"Controller: {endpoint.method} {endpoint.path}",
                    description=f"{endpoint.summary}\nImplement controller method with {len(endpoint.parameters)} parameters.",
                    status=TaskStatus.PENDING.value,
                    dependencies=schema_dependencies[:3] if schema_dependencies else [],
                    estimated_minutes=self.TASK_ESTIMATES[TaskType.API_CONTROLLER],
                    related_requirements=[endpoint.requirement],
                    output_files=[f"src/modules/{endpoint.resource}/{endpoint.resource}.controller.ts"]
                ))

                # Task 2: Service
                tasks.append(Task(
                    id=f"{epic.id}-API-{endpoint.method}-{safe_id}-service",
                    epic_id=epic.id,
                    type=TaskType.API_SERVICE.value,
                    title=f"Service: {endpoint.method} {endpoint.path}",
                    description=f"Business logic for {endpoint.summary}",
                    status=TaskStatus.PENDING.value,
                    dependencies=[f"{epic.id}-API-{endpoint.method}-{safe_id}-controller"],
                    estimated_minutes=self.TASK_ESTIMATES[TaskType.API_SERVICE],
                    related_requirements=[endpoint.requirement],
                    output_files=[f"src/modules/{endpoint.resource}/{endpoint.resource}.service.ts"]
                ))

                # Task 3: DTO (if has request body)
                if endpoint.request_body or endpoint.method in ["POST", "PUT", "PATCH"]:
                    dto_name = endpoint.request_body or f"{endpoint.method}{endpoint.resource.title()}Request"
                    tasks.append(Task(
                        id=f"{epic.id}-API-{endpoint.method}-{safe_id}-dto",
                        epic_id=epic.id,
                        type=TaskType.API_DTO.value,
                        title=f"DTO: {dto_name}",
                        description=f"Request/Response DTO for {endpoint.method} {endpoint.path}",
                        status=TaskStatus.PENDING.value,
                        dependencies=[f"{epic.id}-API-{endpoint.method}-{safe_id}-controller"],
                        estimated_minutes=self.TASK_ESTIMATES[TaskType.API_DTO],
                        related_requirements=[endpoint.requirement],
                        output_files=[f"src/modules/{endpoint.resource}/dto/{dto_name.lower()}.dto.ts"]
                    ))

                # Task 4: Auth Guard (for protected endpoints)
                if any(r.status_code == 401 for r in endpoint.responses):
                    tasks.append(Task(
                        id=f"{epic.id}-API-{endpoint.method}-{safe_id}-guard",
                        epic_id=epic.id,
                        type=TaskType.API_GUARD.value,
                        title=f"Auth Guard: {endpoint.path}",
                        description=f"JWT authentication guard for {endpoint.method} {endpoint.path}",
                        status=TaskStatus.PENDING.value,
                        dependencies=[f"{epic.id}-API-{endpoint.method}-{safe_id}-controller"],
                        estimated_minutes=self.TASK_ESTIMATES[TaskType.API_GUARD],
                        related_requirements=[endpoint.requirement],
                        output_files=[f"src/guards/jwt-auth.guard.ts"]
                    ))

                # Task 5: Input Validation
                if endpoint.parameters:
                    tasks.append(Task(
                        id=f"{epic.id}-API-{endpoint.method}-{safe_id}-validation",
                        epic_id=epic.id,
                        type=TaskType.API_VALIDATION.value,
                        title=f"Validation: {endpoint.method} {endpoint.path}",
                        description=f"Input validation for {len(endpoint.parameters)} parameters",
                        status=TaskStatus.PENDING.value,
                        dependencies=[f"{epic.id}-API-{endpoint.method}-{safe_id}-dto"] if endpoint.request_body else [f"{epic.id}-API-{endpoint.method}-{safe_id}-controller"],
                        estimated_minutes=self.TASK_ESTIMATES[TaskType.API_VALIDATION],
                        related_requirements=[endpoint.requirement],
                        output_files=[f"src/modules/{endpoint.resource}/validators/"]
                    ))

        return tasks

    def _generate_granular_frontend_tasks(self, epic: Epic, api_dependencies: List[str]) -> List[Task]:
        """Generiert granulare Frontend Tasks pro User Story"""
        tasks = []

        components = self._derive_components_from_epic(epic)

        for component, user_stories in components.items():
            component_safe = component.replace(' ', '_')

            # Task 1: Page Component
            tasks.append(Task(
                id=f"{epic.id}-FE-{component_safe}-page",
                epic_id=epic.id,
                type=TaskType.FE_PAGE.value,
                title=f"Page: {component}",
                description=f"Create {component} page component implementing {len(user_stories)} user stories.",
                status=TaskStatus.PENDING.value,
                dependencies=api_dependencies[:3] if api_dependencies else [],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.FE_PAGE],
                related_user_stories=user_stories,
                output_files=[f"src/pages/{component}/{component}.tsx"]
            ))

            # Task 2: Reusable Components
            tasks.append(Task(
                id=f"{epic.id}-FE-{component_safe}-components",
                epic_id=epic.id,
                type=TaskType.FE_COMPONENT.value,
                title=f"Components: {component}",
                description=f"Create reusable components for {component}",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-FE-{component_safe}-page"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.FE_COMPONENT],
                output_files=[f"src/components/{component}/"]
            ))

            # Task 3: Custom Hook
            tasks.append(Task(
                id=f"{epic.id}-FE-{component_safe}-hook",
                epic_id=epic.id,
                type=TaskType.FE_HOOK.value,
                title=f"Hook: use{component}",
                description=f"Create custom hook for {component} state and logic",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-FE-{component_safe}-page"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.FE_HOOK],
                output_files=[f"src/hooks/use{component}.ts"]
            ))

            # Task 4: API Client
            tasks.append(Task(
                id=f"{epic.id}-FE-{component_safe}-api",
                epic_id=epic.id,
                type=TaskType.FE_API_CLIENT.value,
                title=f"API Client: {component}",
                description=f"Create API client functions for {component}",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-FE-{component_safe}-hook"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.FE_API_CLIENT],
                output_files=[f"src/api/{component.lower()}API.ts"]
            ))

            # Task 5: Forms (if applicable)
            if any(kw in component.lower() for kw in ['register', 'login', 'edit', 'create', 'form', 'settings']):
                tasks.append(Task(
                    id=f"{epic.id}-FE-{component_safe}-form",
                    epic_id=epic.id,
                    type=TaskType.FE_FORM.value,
                    title=f"Form: {component}Form",
                    description=f"Create form component with validation for {component}",
                    status=TaskStatus.PENDING.value,
                    dependencies=[f"{epic.id}-FE-{component_safe}-components"],
                    estimated_minutes=self.TASK_ESTIMATES[TaskType.FE_FORM],
                    output_files=[f"src/components/{component}/{component}Form.tsx"]
                ))

        return tasks

    def _generate_feature_consolidated_frontend_tasks(self, epic: Epic, api_dependencies: List[str]) -> List[Task]:
        """1 Task pro Frontend-Component (Page+Components+Hook+API+Form zusammen)."""
        tasks = []
        components = self._derive_components_from_epic(epic)

        for component, user_stories in components.items():
            component_safe = component.replace(' ', '_')
            has_form = any(kw in component.lower() for kw in ['register', 'login', 'edit', 'create', 'form', 'settings'])

            output_files = [
                f"src/pages/{component}/{component}.tsx",
                f"src/components/{component}/",
                f"src/hooks/use{component}.ts",
                f"src/api/{component.lower()}API.ts",
            ]
            if has_form:
                output_files.append(f"src/components/{component}/{component}Form.tsx")

            tasks.append(Task(
                id=f"{epic.id}-FE-{component_safe}-feature",
                epic_id=epic.id,
                type=TaskType.FE_PAGE.value,
                title=f"Frontend Feature: {component} (all layers)",
                description=(
                    f"Generate COMPLETE frontend feature for '{component}':\n"
                    f"- Page component with routing\n"
                    f"- Reusable sub-components\n"
                    f"- Custom hook (use{component})\n"
                    f"- API client functions\n"
                    + (f"- Form with validation\n" if has_form else "")
                    + f"\nUser Stories: {', '.join(user_stories[:5])}"
                ),
                status=TaskStatus.PENDING.value,
                dependencies=api_dependencies[:3] if api_dependencies else [],
                estimated_minutes=max(15, len(user_stories) * 5),
                related_user_stories=user_stories,
                output_files=output_files
            ))

        logger.info(f"FE feature consolidation: {sum(len(v) for v in components.values())} stories → {len(tasks)} feature tasks")
        return tasks

    def _generate_feature_consolidated_test_tasks(self, epic: Epic, code_dependencies: List[str]) -> List[Task]:
        """1-3 Test Tasks pro Epic statt 1 pro Gherkin Scenario."""
        tasks = []

        if not self.test_parser:
            return self._generate_test_tasks(epic, code_dependencies)

        # Collect all scenarios grouped by user story
        us_scenarios = {}
        for us_id in epic.user_stories:
            features = self.test_parser.get_features_by_user_story(us_id)
            scenarios = []
            for feature in features:
                scenarios.extend(feature.scenarios)
            if scenarios:
                us_scenarios[us_id] = scenarios

        if not us_scenarios:
            return self._generate_test_tasks(epic, code_dependencies)

        # Group into max 3 tasks: happy-path, negative/boundary, integration
        happy = []
        negative = []
        integration = []
        for us_id, scenarios in us_scenarios.items():
            for s in scenarios:
                if s.is_happy_path:
                    happy.append((us_id, s))
                elif s.is_negative or s.is_boundary:
                    negative.append((us_id, s))
                else:
                    integration.append((us_id, s))

        for label, group, task_type in [
            ("Happy Path", happy, TaskType.TEST_E2E_HAPPY),
            ("Negative & Boundary", negative, TaskType.TEST_E2E_NEGATIVE),
            ("Integration", integration, TaskType.TEST_INTEGRATION),
        ]:
            if not group:
                continue
            scenario_list = "\n".join(f"  - [{us}] {s.name[:50]}" for us, s in group[:20])
            us_ids = list(set(us for us, _ in group))
            tasks.append(Task(
                id=f"{epic.id}-TEST-{label.replace(' ', '_').replace('&', 'and')}",
                epic_id=epic.id,
                type=task_type.value,
                title=f"Tests: {label} ({len(group)} scenarios)",
                description=(
                    f"Generate {label} test suite for {epic.id}:\n"
                    f"{len(group)} scenarios covering {len(us_ids)} user stories.\n\n"
                    f"Scenarios:\n{scenario_list}"
                    + (f"\n  ... and {len(group) - 20} more" if len(group) > 20 else "")
                ),
                status=TaskStatus.PENDING.value,
                dependencies=code_dependencies[-3:] if code_dependencies else [],
                estimated_minutes=max(10, len(group) * 2),
                related_user_stories=us_ids[:5],
                output_files=[f"e2e/{epic.id.lower()}/{label.lower().replace(' ', '-')}.spec.ts"]
            ))

        logger.info(f"Test feature consolidation: {sum(len(v) for v in us_scenarios.values())} scenarios → {len(tasks)} test tasks")
        return tasks

    def _generate_granular_test_tasks(self, epic: Epic, code_dependencies: List[str]) -> List[Task]:
        """Generiert granulare Test Tasks pro Gherkin Scenario"""
        tasks = []

        if not self.test_parser:
            return self._generate_test_tasks(epic, code_dependencies)

        # Get actual test scenarios from test_documentation.md
        for us_id in epic.user_stories:
            features = self.test_parser.get_features_by_user_story(us_id)

            for feature in features:
                for i, scenario in enumerate(feature.scenarios):
                    scenario_safe = scenario.name[:30].replace(' ', '_').replace('-', '_').replace("'", "")

                    # Determine task type based on scenario tags
                    if scenario.is_happy_path:
                        task_type = TaskType.TEST_E2E_HAPPY
                    elif scenario.is_negative:
                        task_type = TaskType.TEST_E2E_NEGATIVE
                    elif scenario.is_boundary:
                        task_type = TaskType.TEST_E2E_BOUNDARY
                    else:
                        task_type = TaskType.TEST_INTEGRATION

                    tasks.append(Task(
                        id=f"{epic.id}-TEST-{us_id}-{i:03d}",
                        epic_id=epic.id,
                        type=task_type.value,
                        title=f"Test: {scenario.name[:50]}",
                        description=f"Feature: {feature.name}\nTags: {', '.join(scenario.tags)}\nSteps: {len(scenario.steps)}",
                        status=TaskStatus.PENDING.value,
                        dependencies=code_dependencies[-5:] if code_dependencies else [],
                        estimated_minutes=self.TASK_ESTIMATES[task_type],
                        related_user_stories=[us_id],
                        output_files=[f"e2e/{us_id.lower()}/{scenario_safe}.spec.ts"]
                    ))

        # Add unit test task if no scenarios found
        if not tasks:
            tasks = self._generate_test_tasks(epic, code_dependencies)

        return tasks

    # =========================================================================
    # Phase 3.6: Extended Task Generation Methods
    # =========================================================================

    def _generate_setup_tasks(self, epic: Epic) -> List[Task]:
        """
        Generiert Setup-Tasks (Phase 0) - NUR für EPIC-001 oder ersten Epic.

        Setup Tasks werden nur einmal generiert und beinhalten:
        - Project initialization (package.json, tsconfig.json)
        - Environment configuration (.env)
        - Secrets collection (user input needed)
        - Database setup (connection string)
        - Docker configuration (docker-compose.yml)
        - Dependencies installation (npm install)
        """
        tasks = []

        # Setup Tasks nur für ersten Epic generieren
        if epic.id != "EPIC-001":
            return tasks

        # 1. Project Setup
        tasks.append(Task(
            id=f"{epic.id}-SETUP-project",
            epic_id=epic.id,
            type=TaskType.SETUP_PROJECT.value,
            title="Initialize project structure",
            description="Create package.json, tsconfig.json, and project folder structure.",
            status=TaskStatus.PENDING.value,
            dependencies=[],
            estimated_minutes=self.TASK_ESTIMATES[TaskType.SETUP_PROJECT],
            phase=TaskPhase.SETUP.value,
            output_files=["package.json", "tsconfig.json", "src/", "prisma/"],
            requires_user_input=False,
            command="npm init -y && npx tsc --init",
            success_criteria="package.json and tsconfig.json exist"
        ))

        # 2. Environment Setup
        env_requirements = []
        if self.env_parser:
            env_requirements = self.env_parser.detect_required_env_vars()

        env_description = f"Setup {len(env_requirements)} environment variables"
        if env_requirements:
            env_names = [r.name for r in env_requirements[:5]]
            env_description += f": {', '.join(env_names)}"
            if len(env_requirements) > 5:
                env_description += f", ... (+{len(env_requirements) - 5} more)"

        tasks.append(Task(
            id=f"{epic.id}-SETUP-env",
            epic_id=epic.id,
            type=TaskType.SETUP_ENV.value,
            title="Create .env configuration",
            description=env_description,
            status=TaskStatus.PENDING.value,
            dependencies=[f"{epic.id}-SETUP-project"],
            estimated_minutes=self.TASK_ESTIMATES[TaskType.SETUP_ENV],
            phase=TaskPhase.SETUP.value,
            output_files=[".env", ".env.example"],
            requires_user_input=False,
            success_criteria=".env and .env.example files created"
        ))

        # 3. Secrets Collection (wenn User-Input nötig)
        secrets_needed = []
        if self.env_parser:
            secrets_needed = self.env_parser.get_secrets_requiring_input()

        if secrets_needed:
            secret_names = [s.name for s in secrets_needed]
            user_prompt = self._generate_secrets_prompt(secrets_needed)

            tasks.append(Task(
                id=f"{epic.id}-SETUP-secrets",
                epic_id=epic.id,
                type=TaskType.SETUP_SECRETS.value,
                title=f"Configure {len(secrets_needed)} secrets",
                description=f"User input needed for: {', '.join(secret_names)}",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-SETUP-env"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.SETUP_SECRETS],
                phase=TaskPhase.SETUP.value,
                requires_user_input=True,
                user_prompt=user_prompt,
                success_criteria="All required secrets configured in .env"
            ))
            secrets_dep = f"{epic.id}-SETUP-secrets"
        else:
            secrets_dep = f"{epic.id}-SETUP-env"

        # 4. Database Setup (wenn DATABASE_URL benötigt)
        needs_database = any(
            r.name == "DATABASE_URL"
            for r in env_requirements
        ) if env_requirements else True  # Default: assume DB needed

        if needs_database:
            tasks.append(Task(
                id=f"{epic.id}-SETUP-database",
                epic_id=epic.id,
                type=TaskType.SETUP_DATABASE.value,
                title="Configure database connection",
                description="Setup DATABASE_URL in .env and run initial Prisma setup.",
                status=TaskStatus.PENDING.value,
                dependencies=[secrets_dep],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.SETUP_DATABASE],
                phase=TaskPhase.SETUP.value,
                output_files=["prisma/schema.prisma"],
                command="npx prisma generate",
                success_criteria="Prisma initialized and DATABASE_URL configured"
            ))
            db_dep = f"{epic.id}-SETUP-database"
        else:
            db_dep = secrets_dep

        # 5. Docker Setup
        tasks.append(Task(
            id=f"{epic.id}-SETUP-docker",
            epic_id=epic.id,
            type=TaskType.SETUP_DOCKER.value,
            title="Create Docker configuration",
            description="Generate docker-compose.yml with all required services (database, redis, etc.).",
            status=TaskStatus.PENDING.value,
            dependencies=[db_dep],
            estimated_minutes=self.TASK_ESTIMATES[TaskType.SETUP_DOCKER],
            phase=TaskPhase.SETUP.value,
            output_files=["docker-compose.yml", "Dockerfile"],
            success_criteria="docker-compose.yml created with all services"
        ))

        # 6. Dependencies Installation
        tasks.append(Task(
            id=f"{epic.id}-SETUP-deps",
            epic_id=epic.id,
            type=TaskType.SETUP_DEPENDENCIES.value,
            title="Install dependencies",
            description="Run npm install for all required packages.",
            status=TaskStatus.PENDING.value,
            dependencies=[f"{epic.id}-SETUP-docker"],
            estimated_minutes=self.TASK_ESTIMATES[TaskType.SETUP_DEPENDENCIES],
            phase=TaskPhase.SETUP.value,
            command="npm install",
            success_criteria="node_modules created, no npm install errors"
        ))

        return tasks

    def _generate_secrets_prompt(self, secrets: List['EnvRequirement']) -> str:
        """Generiert User-Prompt für Secrets-Eingabe"""
        lines = [
            "Please provide the following secrets for your project:",
            "",
        ]

        for secret in secrets:
            lines.append(f"**{secret.name}**")
            if secret.description:
                lines.append(f"  Description: {secret.description}")
            if secret.example_value:
                lines.append(f"  Example: {secret.example_value}")
            lines.append("")

        lines.append("You can skip optional secrets by leaving them empty.")
        return "\n".join(lines)

    def _generate_verification_tasks(self, epic: Epic, phase: str, dependencies: List[str]) -> List[Task]:
        """
        Generiert Verification-Tasks nach einer Phase.

        Args:
            epic: Der aktuelle Epic
            phase: 'schema', 'api', 'frontend', oder 'tests'
            dependencies: Task-IDs von denen diese Tasks abhängen

        Returns:
            Liste von Verification Tasks
        """
        tasks = []

        if phase == "schema":
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-schema",
                epic_id=epic.id,
                type=TaskType.VERIFY_SCHEMA.value,
                title="Validate Prisma schema",
                description="Run prisma validate to check schema integrity.",
                status=TaskStatus.PENDING.value,
                dependencies=dependencies[-3:] if dependencies else [],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_SCHEMA],
                phase=TaskPhase.SCHEMA.value,
                command="npx prisma validate",
                success_criteria="prisma validate exits with code 0"
            ))

        elif phase == "api":
            # Build verification
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-build-api",
                epic_id=epic.id,
                type=TaskType.VERIFY_BUILD.value,
                title="Build backend",
                description="Run npm run build for NestJS backend.",
                status=TaskStatus.PENDING.value,
                dependencies=dependencies[-5:] if dependencies else [],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_BUILD],
                phase=TaskPhase.API.value,
                command="npm run build",
                success_criteria="Build completes without errors"
            ))

            # TypeScript type check
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-typecheck-api",
                epic_id=epic.id,
                type=TaskType.VERIFY_TYPECHECK.value,
                title="TypeScript type check (API)",
                description="Run tsc --noEmit to verify TypeScript types.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-VERIFY-build-api"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_TYPECHECK],
                phase=TaskPhase.API.value,
                command="npx tsc --noEmit",
                success_criteria="No TypeScript errors"
            ))

            # Integration tests
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-integration",
                epic_id=epic.id,
                type=TaskType.VERIFY_INTEGRATION.value,
                title="Run API integration tests",
                description="Execute integration tests against API endpoints.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-VERIFY-typecheck-api"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_INTEGRATION],
                phase=TaskPhase.API.value,
                command="npm run test:integration",
                success_criteria="All integration tests pass"
            ))

        elif phase == "frontend":
            # Build verification
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-build-fe",
                epic_id=epic.id,
                type=TaskType.VERIFY_BUILD.value,
                title="Build frontend",
                description="Run npm run build for React frontend.",
                status=TaskStatus.PENDING.value,
                dependencies=dependencies[-5:] if dependencies else [],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_BUILD],
                phase=TaskPhase.FRONTEND.value,
                command="npm run build",
                success_criteria="Frontend build completes without errors"
            ))

            # Lint check
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-lint",
                epic_id=epic.id,
                type=TaskType.VERIFY_LINT.value,
                title="Run ESLint",
                description="Check code quality with ESLint.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-VERIFY-build-fe"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_LINT],
                phase=TaskPhase.FRONTEND.value,
                command="npm run lint",
                success_criteria="No linting errors"
            ))

            # TypeScript type check
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-typecheck-fe",
                epic_id=epic.id,
                type=TaskType.VERIFY_TYPECHECK.value,
                title="TypeScript type check (Frontend)",
                description="Run tsc --noEmit for frontend.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-VERIFY-lint"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_TYPECHECK],
                phase=TaskPhase.FRONTEND.value,
                command="npx tsc --noEmit",
                success_criteria="No TypeScript errors"
            ))

            # Unit tests
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-unit",
                epic_id=epic.id,
                type=TaskType.VERIFY_UNIT_TESTS.value,
                title="Run unit tests",
                description="Execute vitest unit tests.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-VERIFY-typecheck-fe"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_UNIT_TESTS],
                phase=TaskPhase.FRONTEND.value,
                command="npm run test:unit",
                success_criteria="All unit tests pass"
            ))

        elif phase == "tests":
            # E2E tests
            tasks.append(Task(
                id=f"{epic.id}-VERIFY-e2e",
                epic_id=epic.id,
                type=TaskType.VERIFY_E2E.value,
                title="Run E2E tests",
                description="Execute Playwright E2E test suite.",
                status=TaskStatus.PENDING.value,
                dependencies=dependencies[-5:] if dependencies else [],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.VERIFY_E2E],
                phase=TaskPhase.TEST.value,
                command="npm run test:e2e",
                success_criteria="All E2E tests pass"
            ))

        return tasks

    def _generate_docker_tasks(self, epic: Epic, phase: str, dependencies: List[str]) -> List[Task]:
        """
        Generiert Docker-Tasks für eine Phase.

        Args:
            epic: Der aktuelle Epic
            phase: 'api' oder 'deploy'
            dependencies: Task-IDs von denen diese Tasks abhängen

        Returns:
            Liste von Docker Tasks
        """
        tasks = []

        if phase == "api":
            # Build Docker image for API
            tasks.append(Task(
                id=f"{epic.id}-DOCKER-build-api",
                epic_id=epic.id,
                type=TaskType.DOCKER_BUILD.value,
                title="Build API Docker image",
                description="Build Docker image for NestJS backend.",
                status=TaskStatus.PENDING.value,
                dependencies=dependencies[-2:] if dependencies else [],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.DOCKER_BUILD],
                phase=TaskPhase.API.value,
                command="docker-compose build api",
                success_criteria="Docker image built successfully"
            ))

            # Start container
            tasks.append(Task(
                id=f"{epic.id}-DOCKER-start-api",
                epic_id=epic.id,
                type=TaskType.DOCKER_START.value,
                title="Start API container",
                description="Start backend container with docker-compose.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-DOCKER-build-api"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.DOCKER_START],
                phase=TaskPhase.API.value,
                command="docker-compose up -d api",
                success_criteria="API container running"
            ))

            # Health check
            tasks.append(Task(
                id=f"{epic.id}-DOCKER-health-api",
                epic_id=epic.id,
                type=TaskType.DOCKER_HEALTH.value,
                title="API health check",
                description="Verify API container is healthy via /health endpoint.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-DOCKER-start-api"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.DOCKER_HEALTH],
                phase=TaskPhase.API.value,
                command="curl -f http://localhost:3000/health",
                success_criteria="Health endpoint returns 200 OK"
            ))

        elif phase == "deploy":
            # Build production image
            tasks.append(Task(
                id=f"{epic.id}-DOCKER-build-prod",
                epic_id=epic.id,
                type=TaskType.DOCKER_BUILD.value,
                title="Build production image",
                description="Build optimized production Docker image.",
                status=TaskStatus.PENDING.value,
                dependencies=dependencies[-2:] if dependencies else [],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.DOCKER_BUILD],
                phase=TaskPhase.DEPLOY.value,
                command="docker-compose -f docker-compose.prod.yml build",
                success_criteria="Production image built"
            ))

            # Start production container
            tasks.append(Task(
                id=f"{epic.id}-DOCKER-start-prod",
                epic_id=epic.id,
                type=TaskType.DOCKER_START.value,
                title="Start production container",
                description="Start full stack in production mode.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-DOCKER-build-prod"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.DOCKER_START],
                phase=TaskPhase.DEPLOY.value,
                command="docker-compose -f docker-compose.prod.yml up -d",
                success_criteria="All containers running"
            ))

            # Production health check
            tasks.append(Task(
                id=f"{epic.id}-DOCKER-health-prod",
                epic_id=epic.id,
                type=TaskType.DOCKER_HEALTH.value,
                title="Production health check",
                description="Verify all services are healthy.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-DOCKER-start-prod"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.DOCKER_HEALTH],
                phase=TaskPhase.DEPLOY.value,
                command="docker-compose -f docker-compose.prod.yml ps",
                success_criteria="All containers healthy"
            ))

            # Collect logs (optional, for debugging)
            tasks.append(Task(
                id=f"{epic.id}-DOCKER-logs-prod",
                epic_id=epic.id,
                type=TaskType.DOCKER_LOGS.value,
                title="Collect production logs",
                description="Collect logs from all production containers.",
                status=TaskStatus.PENDING.value,
                dependencies=[f"{epic.id}-DOCKER-health-prod"],
                estimated_minutes=self.TASK_ESTIMATES[TaskType.DOCKER_LOGS],
                phase=TaskPhase.DEPLOY.value,
                command="docker-compose -f docker-compose.prod.yml logs --tail=100",
                success_criteria="Logs collected, no critical errors"
            ))

        return tasks

    def _generate_checkpoint_task(self, epic: Epic, phase: str, dependencies: List[str]) -> Task:
        """
        Generiert Checkpoint-Task für User-Approval.

        Args:
            epic: Der aktuelle Epic
            phase: 'schema', 'api', 'frontend', oder 'deploy'
            dependencies: Task-IDs von denen dieser Task abhängt

        Returns:
            Checkpoint Task
        """
        prompts = {
            "schema": (
                "Review the generated Prisma schema.\n\n"
                "Please verify:\n"
                "- All entities are correctly defined\n"
                "- Relations between entities are correct\n"
                "- Field types and constraints are appropriate\n"
                "- Indexes are defined where needed\n\n"
                "Approve to continue with API generation."
            ),
            "api": (
                "Review the generated APIs.\n\n"
                "Please verify:\n"
                "- All endpoints are implemented\n"
                "- Authentication and authorization work\n"
                "- Input validation is correct\n"
                "- Error handling is appropriate\n\n"
                "Approve to continue with Frontend generation."
            ),
            "frontend": (
                "Review the generated UI.\n\n"
                "Please verify:\n"
                "- All pages and components are created\n"
                "- UI matches design requirements\n"
                "- Navigation works correctly\n"
                "- Forms have proper validation\n\n"
                "Approve to continue with Testing."
            ),
            "deploy": (
                "Review the complete application.\n\n"
                "Final verification:\n"
                "- All features are implemented\n"
                "- All tests are passing\n"
                "- Docker containers are healthy\n"
                "- Ready for production deployment\n\n"
                "Approve to complete this Epic."
            ),
        }

        checkpoint_types = {
            "schema": TaskType.CHECKPOINT_SCHEMA,
            "api": TaskType.CHECKPOINT_API,
            "frontend": TaskType.CHECKPOINT_FRONTEND,
            "deploy": TaskType.CHECKPOINT_DEPLOY,
        }

        phase_mapping = {
            "schema": TaskPhase.SCHEMA,
            "api": TaskPhase.API,
            "frontend": TaskPhase.FRONTEND,
            "deploy": TaskPhase.DEPLOY,
        }

        task_type = checkpoint_types.get(phase, TaskType.CHECKPOINT_DEPLOY)
        task_phase = phase_mapping.get(phase, TaskPhase.DEPLOY)

        return Task(
            id=f"{epic.id}-CHECKPOINT-{phase}",
            epic_id=epic.id,
            type=task_type.value,
            title=f"Checkpoint: Review {phase.capitalize()}",
            description=f"User approval required before continuing. Review the {phase} phase results.",
            status=TaskStatus.PENDING.value,
            dependencies=dependencies[-3:] if dependencies else [],
            estimated_minutes=self.TASK_ESTIMATES[task_type],
            phase=task_phase.value,
            requires_user_input=True,
            checkpoint=True,
            user_prompt=prompts.get(phase, f"Review {phase} and approve to continue."),
            success_criteria="User approved checkpoint"
        )

    def _generate_schema_tasks(self, epic: Epic) -> List[Task]:
        """Generiert Schema Tasks fuer alle Entities des Epics"""
        tasks = []

        for entity in epic.entities:
            task = Task(
                id=f"{epic.id}-SCHEMA-{entity}",
                epic_id=epic.id,
                type=TaskType.SCHEMA.value,
                title=f"Generate Prisma model for {entity}",
                description=f"Create or update prisma/schema.prisma entry for {entity} entity with all required fields and relations.",
                status=TaskStatus.PENDING.value,
                dependencies=[],  # Schema tasks have no dependencies
                estimated_minutes=self.TASK_ESTIMATES[TaskType.SCHEMA],
                related_requirements=[r for r in epic.requirements if entity.lower() in r.lower()],
                output_files=[f"prisma/schema.prisma"]
            )
            tasks.append(task)

        return tasks

    def _generate_api_tasks(self, epic: Epic, schema_dependencies: List[str]) -> List[Task]:
        """Generiert API Tasks basierend auf User Stories oder Endpoints"""
        tasks = []

        # Wenn wir API Endpoints haben, nutze diese
        if epic.api_endpoints:
            for endpoint in epic.api_endpoints:
                # Extract method and path
                parts = endpoint.split(" ", 1)
                method = parts[0] if len(parts) > 1 else "GET"
                path = parts[-1]

                # Create safe ID from path
                safe_path = path.replace("/", "_").replace("{", "").replace("}", "").strip("_")

                task = Task(
                    id=f"{epic.id}-API-{safe_path}",
                    epic_id=epic.id,
                    type=TaskType.API.value,
                    title=f"Generate API: {method} {path}",
                    description=f"Create NestJS controller, service, and DTO for {method} {path} endpoint.",
                    status=TaskStatus.PENDING.value,
                    dependencies=schema_dependencies,
                    estimated_minutes=self.TASK_ESTIMATES[TaskType.API],
                    output_files=[
                        f"src/modules/{safe_path.split('_')[1] if '_' in safe_path else 'api'}/{safe_path.split('_')[1] if '_' in safe_path else 'api'}.controller.ts",
                        f"src/modules/{safe_path.split('_')[1] if '_' in safe_path else 'api'}/{safe_path.split('_')[1] if '_' in safe_path else 'api'}.service.ts",
                    ]
                )
                tasks.append(task)
        else:
            # Fallback: Generiere API Tasks basierend auf User Stories
            # Gruppiere User Stories zu API Modulen
            us_count = len(epic.user_stories)
            api_modules = self._derive_api_modules_from_epic(epic)

            for module in api_modules:
                task = Task(
                    id=f"{epic.id}-API-{module}",
                    epic_id=epic.id,
                    type=TaskType.API.value,
                    title=f"Generate API module: {module}",
                    description=f"Create NestJS module for {module} with CRUD operations based on {us_count} user stories.",
                    status=TaskStatus.PENDING.value,
                    dependencies=schema_dependencies,
                    estimated_minutes=self.TASK_ESTIMATES[TaskType.API],
                    related_user_stories=epic.user_stories[:5],  # First 5 related US
                    output_files=[
                        f"src/modules/{module}/{module}.module.ts",
                        f"src/modules/{module}/{module}.controller.ts",
                        f"src/modules/{module}/{module}.service.ts",
                    ]
                )
                tasks.append(task)

        return tasks

    def _derive_api_modules_from_epic(self, epic: Epic) -> List[str]:
        """Leitet API Module Namen aus Epic-Name und Entities ab"""
        modules = set()

        # Aus Epic-Name (z.B. "Identity, Auth & Device" -> ["auth", "device"])
        name_lower = epic.name.lower()
        if "auth" in name_lower:
            modules.add("auth")
        if "profile" in name_lower or "user" in name_lower:
            modules.add("users")
        if "contact" in name_lower:
            modules.add("contacts")
        if "message" in name_lower or "messaging" in name_lower:
            modules.add("messages")
        if "media" in name_lower:
            modules.add("media")
        if "group" in name_lower:
            modules.add("groups")
        if "call" in name_lower:
            modules.add("calls")
        if "status" in name_lower:
            modules.add("status")
        if "notification" in name_lower:
            modules.add("notifications")
        if "business" in name_lower:
            modules.add("business")
        if "ai" in name_lower:
            modules.add("ai")
        if "security" in name_lower:
            modules.add("security")

        # Fallback: Aus erstem Entity
        if not modules and epic.entities:
            modules.add(epic.entities[0].lower())

        return sorted(list(modules)) if modules else ["api"]

    def _generate_frontend_tasks(self, epic: Epic, api_dependencies: List[str]) -> List[Task]:
        """Generiert Frontend Tasks fuer User Stories"""
        tasks = []

        # Gruppiere User Stories in Komponenten
        components = self._derive_components_from_epic(epic)

        for component, user_stories in components.items():
            task = Task(
                id=f"{epic.id}-FE-{component}",
                epic_id=epic.id,
                type=TaskType.FRONTEND.value,
                title=f"Generate component: {component}",
                description=f"Create React component {component} implementing {len(user_stories)} user stories.",
                status=TaskStatus.PENDING.value,
                dependencies=api_dependencies[:3] if api_dependencies else [],  # Limit dependencies
                estimated_minutes=self.TASK_ESTIMATES[TaskType.FRONTEND],
                related_user_stories=user_stories,
                output_files=[
                    f"src/components/{component}/{component}.tsx",
                    f"src/components/{component}/{component}.styles.ts",
                ]
            )
            tasks.append(task)

        return tasks

    def _derive_components_from_epic(self, epic: Epic) -> Dict[str, List[str]]:
        """Leitet React Komponenten aus Epic ab"""
        components: Dict[str, List[str]] = {}

        # Basis-Komponenten aus Epic-Name
        name_lower = epic.name.lower()

        if "auth" in name_lower:
            components["LoginPage"] = []
            components["RegisterPage"] = []
            components["TwoFactorAuth"] = []

        if "profile" in name_lower:
            components["ProfilePage"] = []
            components["ProfileEditor"] = []

        if "contact" in name_lower:
            components["ContactList"] = []
            components["ContactDetails"] = []

        if "message" in name_lower or "messaging" in name_lower:
            components["ChatList"] = []
            components["ChatRoom"] = []
            components["MessageInput"] = []

        if "media" in name_lower:
            components["MediaViewer"] = []
            components["MediaUploader"] = []

        if "group" in name_lower:
            components["GroupList"] = []
            components["GroupSettings"] = []
            components["GroupMembers"] = []

        if "call" in name_lower:
            components["CallScreen"] = []
            components["CallControls"] = []

        if "status" in name_lower:
            components["StatusView"] = []
            components["StatusCreator"] = []

        if "notification" in name_lower:
            components["NotificationList"] = []
            components["NotificationSettings"] = []

        if "business" in name_lower:
            components["BusinessProfile"] = []
            components["ProductCatalog"] = []

        if "ai" in name_lower:
            components["AIAssistant"] = []
            components["SmartSuggestions"] = []

        if "security" in name_lower:
            components["SecuritySettings"] = []
            components["PrivacyControls"] = []

        # Fallback
        if not components:
            components[f"{epic.id.replace('-', '')}Page"] = []

        # Verteile User Stories auf Komponenten
        us_per_component = max(1, len(epic.user_stories) // len(components))
        us_index = 0

        for component in components:
            end_index = min(us_index + us_per_component, len(epic.user_stories))
            components[component] = epic.user_stories[us_index:end_index]
            us_index = end_index

        return components

    def _generate_test_tasks(self, epic: Epic, code_dependencies: List[str]) -> List[Task]:
        """Generiert Test Tasks"""
        tasks = []

        # Unit Tests
        tasks.append(Task(
            id=f"{epic.id}-TEST-unit",
            epic_id=epic.id,
            type=TaskType.TEST.value,
            title=f"Generate unit tests for {epic.id}",
            description=f"Create Vitest unit tests for all {epic.id} services and utilities. NO MOCKS - use real implementations.",
            status=TaskStatus.PENDING.value,
            dependencies=code_dependencies[:5],  # Limit
            estimated_minutes=self.TASK_ESTIMATES[TaskType.TEST],
            output_files=[f"__tests__/unit/{epic.id.lower().replace('-', '_')}/"]
        ))

        # Integration Tests
        tasks.append(Task(
            id=f"{epic.id}-TEST-integration",
            epic_id=epic.id,
            type=TaskType.TEST.value,
            title=f"Generate integration tests for {epic.id}",
            description=f"Create Vitest integration tests for {epic.id} API endpoints with real database.",
            status=TaskStatus.PENDING.value,
            dependencies=[f"{epic.id}-TEST-unit"],
            estimated_minutes=self.TASK_ESTIMATES[TaskType.TEST] + 5,
            output_files=[f"__tests__/integration/{epic.id.lower().replace('-', '_')}/"]
        ))

        # E2E Tests (basierend auf User Stories)
        tasks.append(Task(
            id=f"{epic.id}-TEST-e2e",
            epic_id=epic.id,
            type=TaskType.TEST.value,
            title=f"Generate E2E tests for {epic.id}",
            description=f"Create Playwright E2E tests for {len(epic.user_stories)} user stories in {epic.id}.",
            status=TaskStatus.PENDING.value,
            dependencies=[f"{epic.id}-TEST-integration"],
            estimated_minutes=self.TASK_ESTIMATES[TaskType.TEST] + 10,
            related_user_stories=epic.user_stories,
            output_files=[f"e2e/{epic.id.lower().replace('-', '_')}.spec.ts"]
        ))

        return tasks

    def _generate_integration_task(self, epic: Epic, all_task_ids: List[str]) -> Task:
        """Generiert den abschliessenden Integration Task"""
        return Task(
            id=f"{epic.id}-INTEGRATION",
            epic_id=epic.id,
            type=TaskType.INTEGRATION.value,
            title=f"Validate and integrate {epic.id}",
            description=f"Run all {epic.id} tests, validate build, and verify all {len(epic.user_stories)} user stories are implemented.",
            status=TaskStatus.PENDING.value,
            dependencies=all_task_ids[-3:] if len(all_task_ids) >= 3 else all_task_ids,  # Last 3 tasks
            estimated_minutes=self.TASK_ESTIMATES[TaskType.INTEGRATION],
        )

    def generate_all_epic_tasks(self) -> Dict[str, EpicTaskList]:
        """
        Generiert Tasks fuer alle Epics.

        Returns:
            Dict mit epic_id -> EpicTaskList
        """
        epics = self.parser.parse_all_epics()
        all_task_lists = {}

        for epic in epics:
            task_list = self.generate_tasks_for_epic(epic.id)
            all_task_lists[epic.id] = task_list

        return all_task_lists

    def save_epic_tasks(self, epic_id: str, output_dir: Optional[str] = None) -> str:
        """
        Speichert Tasks fuer einen Epic als JSON.

        Args:
            epic_id: z.B. "EPIC-001"
            output_dir: Ausgabe-Verzeichnis. Default: {project}/tasks/

        Returns:
            Pfad zur erstellten Datei
        """
        task_list = self.generate_tasks_for_epic(epic_id)

        if output_dir is None:
            output_dir = self.project_path / "tasks"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Filename: epic-001-tasks.json
        filename = f"{epic_id.lower()}-tasks.json"
        output_path = output_dir / filename

        # Convert to dict
        def to_dict(obj):
            if hasattr(obj, '__dataclass_fields__'):
                return {k: to_dict(v) for k, v in asdict(obj).items()}
            elif isinstance(obj, list):
                return [to_dict(item) for item in obj]
            return obj

        output_data = to_dict(task_list)

        output_path.write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        logger.info(f"Saved {epic_id} tasks to: {output_path}")
        return str(output_path)

    def save_all_epic_tasks(self, output_dir: Optional[str] = None) -> List[str]:
        """
        Speichert Tasks fuer alle Epics.

        Returns:
            Liste der erstellten Dateipfade
        """
        epics = self.parser.parse_all_epics()
        saved_files = []

        for epic in epics:
            path = self.save_epic_tasks(epic.id, output_dir)
            saved_files.append(path)

        # Also save epics.json summary
        self.parser.save_epics_json()

        return saved_files

    def load_epic_tasks(self, epic_id: str) -> Optional[EpicTaskList]:
        """
        Laedt Tasks fuer einen Epic aus JSON.

        Args:
            epic_id: z.B. "EPIC-001"

        Returns:
            EpicTaskList oder None wenn nicht gefunden
        """
        filename = f"{epic_id.lower()}-tasks.json"
        task_path = self.project_path / "tasks" / filename

        if not task_path.exists():
            return None

        data = json.loads(task_path.read_text(encoding="utf-8"))

        # Convert tasks back to Task objects
        tasks = []
        for t in data.get("tasks", []):
            tasks.append(Task(**t))

        return EpicTaskList(
            epic_id=data["epic_id"],
            epic_name=data["epic_name"],
            tasks=tasks,
            total_tasks=data.get("total_tasks", len(tasks)),
            completed_tasks=data.get("completed_tasks", 0),
            failed_tasks=data.get("failed_tasks", 0),
            progress_percent=data.get("progress_percent", 0.0),
            run_count=data.get("run_count", 0),
            last_run_at=data.get("last_run_at"),
            created_at=data.get("created_at", ""),
            estimated_total_minutes=data.get("estimated_total_minutes", 0)
        )

    def reset_epic_tasks(self, epic_id: str) -> EpicTaskList:
        """
        Setzt alle Tasks eines Epics auf pending zurueck.

        Args:
            epic_id: z.B. "EPIC-001"

        Returns:
            Zurueckgesetzte EpicTaskList
        """
        task_list = self.load_epic_tasks(epic_id)

        if task_list is None:
            # Generate fresh tasks
            return self.generate_tasks_for_epic(epic_id)

        # Reset all tasks
        for task in task_list.tasks:
            task.status = TaskStatus.PENDING.value
            task.actual_minutes = None
            task.error_message = None

        task_list.completed_tasks = 0
        task_list.failed_tasks = 0
        task_list.progress_percent = 0.0
        task_list.run_count += 1
        task_list.last_run_at = datetime.now().isoformat()

        # Save updated tasks
        self.save_epic_tasks(epic_id)

        logger.info(f"Reset {len(task_list.tasks)} tasks for {epic_id}")
        return task_list


# =============================================================================
# Test
# =============================================================================

def test_epic_task_generator():
    """Test der EpicTaskGenerator Funktionalitaet - Phase 3.5 Enhanced"""
    print("=== Epic Task Generator Test (Phase 3.5 Granular) ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    # Test 1: Legacy mode (for comparison)
    print("1. Legacy mode (Phase 3):")
    generator_legacy = EpicTaskGenerator(str(test_path), granular=False)
    task_list_legacy = generator_legacy.generate_tasks_for_epic("EPIC-001")
    print(f"   Total tasks: {task_list_legacy.total_tasks}")
    print(f"   Estimated time: {task_list_legacy.estimated_total_minutes} minutes")

    # Test 2: Granular mode (Phase 3.5)
    print("\n2. Granular mode (Phase 3.5):")
    generator = EpicTaskGenerator(str(test_path), granular=True)
    task_list = generator.generate_tasks_for_epic("EPIC-001")
    print(f"   Epic: {task_list.epic_name}")
    print(f"   Total tasks: {task_list.total_tasks}")
    print(f"   Estimated time: {task_list.estimated_total_minutes} minutes")

    # Task breakdown by granular type
    print("\n   Tasks breakdown by type:")
    type_counts = {}
    for task in task_list.tasks:
        type_counts[task.type] = type_counts.get(task.type, 0) + 1

    for task_type, count in sorted(type_counts.items()):
        print(f"      {task_type}: {count} tasks")

    # Test 3: Show sample granular tasks
    print("\n3. Sample granular tasks:")

    # Schema tasks
    schema_tasks = [t for t in task_list.tasks if "SCHEMA" in t.type.upper() or "schema" in t.type]
    if schema_tasks:
        print(f"\n   Schema Tasks ({len(schema_tasks)}):")
        for task in schema_tasks[:3]:
            print(f"      {task.id}: {task.title}")

    # API tasks
    api_tasks = [t for t in task_list.tasks if "API" in t.type.upper() or "api" in t.type]
    if api_tasks:
        print(f"\n   API Tasks ({len(api_tasks)}):")
        for task in api_tasks[:3]:
            print(f"      {task.id}: {task.title}")

    # Test tasks
    test_tasks = [t for t in task_list.tasks if "TEST" in t.type.upper() or "test" in t.type]
    if test_tasks:
        print(f"\n   Test Tasks ({len(test_tasks)}):")
        for task in test_tasks[:3]:
            print(f"      {task.id}: {task.title}")

    # Test 4: Save granular tasks
    print("\n4. Save granular tasks:")
    saved_path = generator.save_epic_tasks("EPIC-001")
    print(f"   Saved to: {saved_path}")

    # Test 5: Generate all epic tasks (granular)
    print("\n5. Generate all epic tasks (granular):")
    all_lists = generator.generate_all_epic_tasks()
    total_tasks = sum(tl.total_tasks for tl in all_lists.values())
    total_time = sum(tl.estimated_total_minutes for tl in all_lists.values())

    print(f"   Total epics: {len(all_lists)}")
    print(f"   Total tasks: {total_tasks}")
    print(f"   Estimated total time: {total_time} minutes ({total_time // 60}h {total_time % 60}m)")

    print("\n   Per-epic breakdown:")
    for epic_id, tl in sorted(all_lists.items()):
        print(f"      {epic_id}: {tl.total_tasks} tasks ({tl.estimated_total_minutes} min)")

    # Test 6: Comparison
    print("\n6. Comparison (Legacy vs Granular):")
    legacy_total = sum(EpicTaskGenerator(str(test_path), granular=False).generate_tasks_for_epic(e.id).total_tasks for e in generator.parser.parse_all_epics())
    print(f"   Legacy tasks:   {legacy_total}")
    print(f"   Granular tasks: {total_tasks}")
    print(f"   Increase:       {total_tasks - legacy_total} tasks ({((total_tasks - legacy_total) / legacy_total * 100):.1f}%)")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_epic_task_generator()
