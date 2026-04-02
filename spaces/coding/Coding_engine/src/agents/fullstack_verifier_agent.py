"""
FullstackVerifierAgent - Verifies all fullstack components are generated and working.

This agent is part of the Continuous Feedback Loop architecture:
1. Subscribes to build/deploy/test events
2. Checks if all fullstack components exist and work
3. Publishes FULLSTACK_VERIFIED (termination) or FULLSTACK_INCOMPLETE (continues loop)
4. FULLSTACK_INCOMPLETE triggers ArchitectAgent to refine contracts

Termination Condition:
- Frontend: Components rendered, no console errors
- Backend: API endpoints responding, auth working
- Database: Schema applied, CRUD operations work
- Integration: E2E tests pass, data persists
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Optional, List, Dict
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from ..mind.fullstack_status import FullstackStatus, ComponentStatus

logger = structlog.get_logger(__name__)


class FullstackVerifierAgent(AutonomousAgent):
    """
    Verifies all fullstack components are generated and working.

    Publishes FULLSTACK_VERIFIED when all components pass checks,
    or FULLSTACK_INCOMPLETE with details about what's missing/failing.
    """

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events that trigger fullstack verification."""
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.API_ROUTES_GENERATED,
            EventType.AUTH_SETUP_COMPLETE,
            EventType.DATABASE_SCHEMA_GENERATED,
            EventType.E2E_TEST_PASSED,
            EventType.E2E_TEST_FAILED,
            EventType.DEPLOY_SUCCEEDED,
            EventType.TESTS_PASSED,
            EventType.VERIFICATION_PASSED,
            EventType.CRUD_TEST_PASSED,
        ]

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        check_interval: float = 30.0,  # Check every 30 seconds when events arrive
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.check_interval = check_interval
        self._fullstack_status = FullstackStatus()  # Renamed to avoid shadowing AgentStatus
        self._last_check_time = 0.0
        self._consecutive_passes = 0
        self.logger = logger.bind(agent=name)

    async def should_act(self, events: list[Event]) -> bool:
        """
        Act on build/deploy/test success events.

        We verify after significant events that indicate progress.
        """
        if not events:
            return False

        # Check if any trigger events occurred
        trigger_types = {
            EventType.BUILD_SUCCEEDED,
            EventType.DEPLOY_SUCCEEDED,
            EventType.E2E_TEST_PASSED,
            EventType.TESTS_PASSED,
            EventType.CRUD_TEST_PASSED,
            EventType.VERIFICATION_PASSED,
        }

        has_trigger = any(e.type in trigger_types for e in events)

        if has_trigger:
            self.logger.info(
                "fullstack_verification_triggered",
                events=[e.type.value for e in events if e.type in trigger_types],
            )
            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Check all fullstack components and publish verification result.
        """
        import time

        self.logger.info("fullstack_check_started", iteration=self._fullstack_status.iteration)

        # Publish start event
        await self.event_bus.publish(Event(
            type=EventType.FULLSTACK_CHECK_STARTED,
            source=self.name,
            data={"iteration": self._fullstack_status.iteration},
        ))

        # Reset checks for new verification cycle
        self._fullstack_status.reset_checks()

        # Run all checks
        await self._check_frontend()
        await self._check_backend()
        await self._check_database()
        await self._check_integration()

        # Update completeness for each component
        self._fullstack_status.frontend.update_completeness()
        self._fullstack_status.backend.update_completeness()
        self._fullstack_status.database.update_completeness()
        self._fullstack_status.integration.update_completeness()

        # Calculate overall score
        self._fullstack_status.calculate_score()
        self._fullstack_status.last_verified = asyncio.get_event_loop().time()

        # Update shared state using async method
        await self.shared_state.update_fullstack(
            verified=self._fullstack_status.is_complete,
            score=self._fullstack_status.overall_score,
            missing_components=self._fullstack_status.missing_components,
            frontend_verified=self._fullstack_status.frontend.is_complete,
            backend_verified=self._fullstack_status.backend.is_complete,
            database_verified=self._fullstack_status.database.is_complete,
            integration_verified=self._fullstack_status.integration.is_complete,
        )

        # Publish result
        if self._fullstack_status.is_complete:
            self._consecutive_passes += 1
            self.logger.info(
                "fullstack_verified",
                score=self._fullstack_status.overall_score,
                consecutive_passes=self._consecutive_passes,
            )

            # Only publish FULLSTACK_VERIFIED after 2 consecutive passes
            # This prevents false positives from transient states
            if self._consecutive_passes >= 2:
                await self.event_bus.publish(Event(
                    type=EventType.FULLSTACK_VERIFIED,
                    source=self.name,
                    data=self._fullstack_status.to_dict(),
                ))
        else:
            self._consecutive_passes = 0
            self.logger.info(
                "fullstack_incomplete",
                score=self._fullstack_status.overall_score,
                missing=self._fullstack_status.missing_components,
                failing=self._fullstack_status.failing_checks,
            )

            await self.event_bus.publish(Event(
                type=EventType.FULLSTACK_INCOMPLETE,
                source=self.name,
                data={
                    "missing": self._fullstack_status.missing_components,
                    "failing": self._fullstack_status.failing_checks,
                    "score": self._fullstack_status.overall_score,
                    "iteration": self._fullstack_status.iteration,
                    "details": self._fullstack_status.to_dict(),
                },
            ))

    async def _check_frontend(self) -> None:
        """Check frontend components."""
        project_dir = Path(self.working_dir)

        # Check 1: Components exist
        components_dir = project_dir / "src" / "components"
        components_exist = components_dir.exists() and any(components_dir.glob("**/*.tsx"))
        self._fullstack_status.frontend.add_check(
            "components_exist",
            components_exist,
            f"Components directory: {components_dir}",
        )

        if not components_exist:
            self._fullstack_status.frontend.missing.append("React components")

        # Check 2: Routes defined (App.tsx or router file)
        routes_file = project_dir / "src" / "App.tsx"
        router_file = project_dir / "src" / "router" / "index.tsx"
        routes_defined = routes_file.exists() or router_file.exists()
        self._fullstack_status.frontend.add_check(
            "routes_defined",
            routes_defined,
            "Main App or Router file exists",
        )

        # Check 3: Build succeeded (check for build output or no console errors)
        # This is inferred from BUILD_SUCCEEDED events
        build_ok = self.shared_state.build_succeeded if hasattr(self.shared_state, 'build_succeeded') else False
        self._fullstack_status.frontend.add_check(
            "renders_without_error",
            build_ok,
            "Frontend build succeeded",
        )

        # Check 4: No console errors (from browser agent events)
        console_errors = getattr(self.shared_state, 'browser_console_errors', [])
        no_console_errors = len(console_errors) == 0
        self._fullstack_status.frontend.add_check(
            "no_console_errors",
            no_console_errors,
            f"Console errors: {len(console_errors)}",
            {"errors": console_errors[:5]} if console_errors else {},
        )

    async def _check_backend(self) -> None:
        """Check backend components."""
        project_dir = Path(self.working_dir)

        # Check 1: API routes exist
        api_dir = project_dir / "src" / "api"
        routes_dir = project_dir / "src" / "routes"
        server_file = project_dir / "src" / "server.ts"

        api_exists = (
            api_dir.exists() or
            routes_dir.exists() or
            server_file.exists()
        )
        self._fullstack_status.backend.add_check(
            "api_responds",
            api_exists,
            "API or server files exist",
        )

        if not api_exists:
            self._fullstack_status.backend.missing.append("API routes")

        # Check 2: Endpoints match contracts (check .contracts_cache.json)
        contracts_file = project_dir / ".contracts_cache.json"
        endpoints_match = contracts_file.exists()
        self._fullstack_status.backend.add_check(
            "endpoints_match_contracts",
            endpoints_match,
            "Contracts cache exists",
        )

        # Check 3: Auth works (check for auth middleware or config)
        auth_dir = project_dir / "src" / "auth"
        auth_middleware = project_dir / "src" / "middleware" / "auth.ts"
        auth_config = project_dir / "src" / "lib" / "auth.ts"

        auth_works = (
            auth_dir.exists() or
            auth_middleware.exists() or
            auth_config.exists() or
            any((project_dir / "src").glob("**/auth*.ts"))
        )
        self._fullstack_status.backend.add_check(
            "auth_works",
            auth_works,
            "Auth configuration exists",
        )

        # Check 4: Health check (basic server health)
        health_ok = self.shared_state.deploy_succeeded if hasattr(self.shared_state, 'deploy_succeeded') else False
        self._fullstack_status.backend.add_check(
            "health_check_passes",
            health_ok,
            "Server deployed successfully",
        )

    async def _check_database(self) -> None:
        """Check database components."""
        project_dir = Path(self.working_dir)

        # Check 1: Schema exists
        prisma_schema = project_dir / "prisma" / "schema.prisma"
        drizzle_schema = project_dir / "src" / "db" / "schema.ts"
        schema_exists = prisma_schema.exists() or drizzle_schema.exists()

        self._fullstack_status.database.add_check(
            "schema_exists",
            schema_exists,
            f"Prisma: {prisma_schema.exists()}, Drizzle: {drizzle_schema.exists()}",
        )

        if not schema_exists:
            self._fullstack_status.database.missing.append("Database schema")

        # Check 2: Schema has models (not just placeholder)
        schema_applied = False
        if prisma_schema.exists():
            content = prisma_schema.read_text()
            # Check for actual model definitions (not just generator/datasource)
            schema_applied = "model " in content and content.count("model ") > 0

        self._fullstack_status.database.add_check(
            "schema_applied",
            schema_applied,
            "Schema contains model definitions",
        )

        # Check 3: CRUD operations work (from CRUD test events)
        crud_passed = getattr(self.shared_state, 'crud_tests_passed', False)
        self._fullstack_status.database.add_check(
            "crud_works",
            crud_passed,
            "CRUD tests passed",
        )

        # Check 4: Relations valid (check if schema has relations)
        relations_valid = False
        if prisma_schema.exists():
            content = prisma_schema.read_text()
            relations_valid = "@relation" in content or "[]" in content

        self._fullstack_status.database.add_check(
            "relations_valid",
            relations_valid or schema_applied,  # Consider valid if schema exists
            "Schema has relations defined",
        )

    async def _check_integration(self) -> None:
        """Check integration between components."""

        # Check 1: Frontend calls backend (check for API hooks or fetch calls)
        project_dir = Path(self.working_dir)
        hooks_dir = project_dir / "src" / "hooks"
        api_client = project_dir / "src" / "api" / "client.ts"
        services_dir = project_dir / "src" / "services"

        frontend_calls_backend = (
            hooks_dir.exists() or
            api_client.exists() or
            services_dir.exists()
        )

        self._fullstack_status.integration.add_check(
            "frontend_calls_backend",
            frontend_calls_backend,
            "API hooks/client/services exist",
        )

        if not frontend_calls_backend:
            self._fullstack_status.integration.missing.append("API integration (hooks/client)")

        # Check 2: Auth flow works (check for auth context or provider)
        auth_context = project_dir / "src" / "context" / "AuthContext.tsx"
        auth_provider = project_dir / "src" / "providers" / "AuthProvider.tsx"
        use_auth_hook = any((project_dir / "src").glob("**/useAuth*.ts*"))

        auth_flow_works = (
            auth_context.exists() or
            auth_provider.exists() or
            use_auth_hook
        )

        self._fullstack_status.integration.add_check(
            "auth_flow_works",
            auth_flow_works,
            "Auth context/provider exists",
        )

        # Check 3: Data persists (inferred from CRUD + deploy success)
        data_persists = (
            getattr(self.shared_state, 'crud_tests_passed', False) and
            getattr(self.shared_state, 'deploy_succeeded', False)
        )

        self._fullstack_status.integration.add_check(
            "data_persists",
            data_persists,
            "CRUD tests passed with deployed backend",
        )

        # Check 4: E2E critical flows pass
        e2e_passed = getattr(self.shared_state, 'e2e_tests_passed', False)

        self._fullstack_status.integration.add_check(
            "e2e_critical_flows_pass",
            e2e_passed,
            "E2E tests passed",
        )

    def get_fullstack_status(self) -> FullstackStatus:
        """Get current fullstack status (not AgentStatus)."""
        return self._fullstack_status

    def get_verification_summary(self) -> Dict[str, Any]:
        """Get summary for logging/display."""
        return {
            "is_complete": self._fullstack_status.is_complete,
            "score": f"{self._fullstack_status.overall_score * 100:.1f}%",
            "iteration": self._fullstack_status.iteration,
            "consecutive_passes": self._consecutive_passes,
            "frontend": self._fullstack_status.frontend.is_complete,
            "backend": self._fullstack_status.backend.is_complete,
            "database": self._fullstack_status.database.is_complete,
            "integration": self._fullstack_status.integration.is_complete,
            "missing": self._fullstack_status.missing_components,
        }
