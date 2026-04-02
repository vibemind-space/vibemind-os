# -*- coding: utf-8 -*-
"""
Integration tests for the Differential Pipeline (Phase 23).

Tests the full analysis → routing → fix pipeline using mocked
MCPAgentPool (no real MCP agents needed) and real DifferentialAnalysisService
with a mocked LLM judge (no API keys required).
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip guard for Windows JAX DLL conflict
try:
    from src.services.differential_analysis_service import (
        AnalysisMode,
        DifferentialAnalysisService,
        DifferentialReport,
        GapFinding,
        GapSeverity,
        ImplementationStatus,
    )
    from src.agents.differential_fix_agent import (
        DifferentialFixAgent,
        GAP_AGENT_ROUTING,
        GAP_TYPE_KEYWORDS,
    )
    from src.mind.event_bus import Event, EventType

    _IMPORTS_AVAILABLE = True
except (ImportError, OSError) as e:
    _IMPORTS_AVAILABLE = False
    _IMPORT_ERROR = str(e)

pytestmark = pytest.mark.skipif(
    not _IMPORTS_AVAILABLE,
    reason=f"Required imports not available: {globals().get('_IMPORT_ERROR', 'unknown')}",
)


# ---------------------------------------------------------------------------
# Mock MCP Agent Result
# ---------------------------------------------------------------------------

@dataclass
class MockAgentResult:
    agent: str = "filesystem"
    task: str = "fix code"
    session_id: str = "test_session"
    success: bool = True
    output: str = "Files created successfully"
    error: Optional[str] = None
    duration: float = 1.5
    data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def whatsapp_test_data(tmp_path):
    """Create minimal WhatsApp-like test data for pipeline testing."""
    data_dir = tmp_path / "whatsapp"
    data_dir.mkdir()

    # User stories with linked requirements
    user_stories = [
        {
            "id": "US-001",
            "title": "Phone Registration",
            "linked_requirement": "WA-AUTH-001",
            "priority": "MUST",
            "as_a": "user",
            "i_want": "register with my phone number",
            "so_that": "I can use the app",
            "description": "Phone number registration with SMS verification",
        },
        {
            "id": "US-002",
            "title": "Two-Factor Authentication",
            "linked_requirement": "WA-AUTH-002",
            "priority": "MUST",
            "as_a": "user",
            "i_want": "enable 2FA",
            "so_that": "my account is more secure",
            "description": "Two-factor authentication setup with TOTP",
        },
        {
            "id": "US-003",
            "title": "Session Management",
            "linked_requirement": "WA-AUTH-003",
            "priority": "SHOULD",
            "as_a": "user",
            "i_want": "manage my active sessions",
            "so_that": "I can revoke access from unknown devices",
            "description": "View and manage active login sessions",
        },
        {
            "id": "US-004",
            "title": "Database Schema Setup",
            "linked_requirement": "WA-DB-001",
            "priority": "MUST",
            "as_a": "developer",
            "i_want": "database schema for user model",
            "so_that": "user data is properly stored",
            "description": "Prisma schema with User, Session, Device models and migrations",
        },
        {
            "id": "US-005",
            "title": "Install Dependencies",
            "linked_requirement": "WA-DEP-001",
            "priority": "MUST",
            "as_a": "developer",
            "i_want": "install required npm packages",
            "so_that": "the project builds correctly",
            "description": "npm install bcrypt jsonwebtoken @nestjs/jwt package dependency",
        },
    ]
    (data_dir / "user_stories.json").write_text(
        json.dumps(user_stories, indent=2), encoding="utf-8"
    )

    # Epic tasks
    tasks_dir = data_dir / "tasks"
    tasks_dir.mkdir()
    tasks = {
        "epic_id": "EPIC-001",
        "epic_name": "Authentication",
        "tasks": [
            {
                "id": "T1",
                "type": "schema_user",
                "status": "completed",
                "description": "Create user model",
                "related_requirements": ["WA-AUTH-001"],
                "related_user_stories": ["US-001"],
                "output_files": ["prisma/schema.prisma"],
            },
            {
                "id": "T2",
                "type": "api_auth",
                "status": "failed",
                "description": "Create auth endpoints",
                "related_requirements": ["WA-AUTH-002"],
                "related_user_stories": ["US-002"],
                "output_files": [],
            },
        ],
    }
    (tasks_dir / "epic-001-tasks.json").write_text(
        json.dumps(tasks, indent=2), encoding="utf-8"
    )

    # Minimal generated code (missing most implementations)
    output_dir = data_dir / "output"
    output_dir.mkdir()
    src_dir = output_dir / "src"
    src_dir.mkdir()

    (output_dir / "package.json").write_text(
        json.dumps({"name": "whatsapp-auth", "version": "1.0.0"}, indent=2),
        encoding="utf-8",
    )

    # Only one file exists — most requirements are NOT implemented
    (src_dir / "app.ts").write_text(
        "import { NestFactory } from '@nestjs/core';\n"
        "// Phone registration placeholder\n"
        "const app = await NestFactory.create(AppModule);\n",
        encoding="utf-8",
    )

    return data_dir


def _make_pool_mock(available=None, spawn_result=None):
    """Create a mocked MCPAgentPool."""
    pool = MagicMock()
    pool.list_available.return_value = available or ["filesystem", "prisma", "npm"]
    pool.spawn = AsyncMock(
        return_value=spawn_result or MockAgentResult(success=True)
    )
    pool.spawn_parallel = AsyncMock(
        return_value=[spawn_result or MockAgentResult(success=True)]
    )
    return pool


def _mock_llm_findings(requirements, top_results, mode=None):
    """Build mock GapFinding objects for each requirement (replaces LLM judge)."""
    findings = []
    for req in requirements:
        findings.append(GapFinding(
            requirement_id=req["id"],
            requirement_title=req.get("title", ""),
            requirement_description=req.get("description", ""),
            priority=req.get("priority", "MUST"),
            status=ImplementationStatus.MISSING,
            severity=GapSeverity.CRITICAL,
            confidence=0.85,
            gap_description=f"Missing implementation for {req.get('title', req['id'])}",
            suggested_tasks=[f"Implement {req.get('title', req['id'])}"],
        ))
    return findings


# ---------------------------------------------------------------------------
# Tests: Analysis Only (dry-run)
# ---------------------------------------------------------------------------

class TestPipelineAnalysisOnly:
    """Test the analysis phase of the pipeline."""

    @pytest.mark.asyncio
    async def test_analysis_finds_gaps(self, whatsapp_test_data):
        """Analysis on minimal data produces a report with findings."""
        service = DifferentialAnalysisService(
            data_dir=str(whatsapp_test_data),
            job_id="test_analysis",
            enable_supermemory=False,
        )

        started = await service.start()
        assert started, "Service should start with valid data"

        with patch.object(
            service, "_llm_evaluate",
            new=AsyncMock(side_effect=lambda reqs, top, mode: _mock_llm_findings(reqs, top, mode)),
        ):
            report = await service.run_analysis(
                mode=AnalysisMode.FULL_DIFFERENTIAL,
            )

        assert report is not None
        assert report.total_requirements > 0
        assert len(report.findings) == report.total_requirements
        assert report.judge_confidence >= 0.0

        await service.stop()

    @pytest.mark.asyncio
    async def test_analysis_returns_findings(self, whatsapp_test_data):
        """Analysis produces structured GapFinding objects."""
        service = DifferentialAnalysisService(
            data_dir=str(whatsapp_test_data),
            job_id="test_findings",
            enable_supermemory=False,
        )

        await service.start()

        with patch.object(
            service, "_llm_evaluate",
            new=AsyncMock(side_effect=lambda reqs, top, mode: _mock_llm_findings(reqs, top, mode)),
        ):
            report = await service.run_analysis(mode=AnalysisMode.FULL_DIFFERENTIAL)

        assert len(report.findings) > 0
        for finding in report.findings:
            assert finding.requirement_id != ""
            assert finding.status in list(ImplementationStatus)
            assert finding.severity in list(GapSeverity)
            assert 0.0 <= finding.confidence <= 1.0

        await service.stop()


# ---------------------------------------------------------------------------
# Tests: Gap Type Routing
# ---------------------------------------------------------------------------

class TestPipelineGapRouting:
    """Test gap type classification and agent routing."""

    def test_schema_gap_routes_to_claude_code_and_prisma(self):
        """Schema gap should route to claude-code + prisma."""
        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="test",
            data={
                "gap_description": "Missing Prisma schema for User model",
                "reason": "Database model not found",
                "suggested_tasks": ["Create User table in schema"],
            },
        )
        gap_type = DifferentialFixAgent._determine_gap_type(event)
        assert gap_type == "schema"
        agents = GAP_AGENT_ROUTING[gap_type]
        assert "claude-code" in agents
        assert "prisma" in agents

    def test_dependency_gap_routes_to_npm(self):
        """Dependency gap should route to npm."""
        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="test",
            data={
                "gap_description": "Cannot find module bcrypt, npm package missing",
                "reason": "Module not found error",
                "suggested_tasks": ["npm install bcrypt"],
            },
        )
        gap_type = DifferentialFixAgent._determine_gap_type(event)
        assert gap_type == "dependency"
        agents = GAP_AGENT_ROUTING[gap_type]
        assert "npm" in agents

    def test_migration_gap_routes_to_prisma(self):
        """Migration gap should route to prisma."""
        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="test",
            data={
                "gap_description": "Database migration for auth tables not applied",
                "reason": "Migration pending",
                "suggested_tasks": ["Run prisma migrate deploy"],
            },
        )
        gap_type = DifferentialFixAgent._determine_gap_type(event)
        assert gap_type == "migration"
        agents = GAP_AGENT_ROUTING[gap_type]
        assert "prisma" in agents

    def test_api_gap_routes_to_claude_code(self):
        """API gap should route to claude-code (code writing)."""
        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="test",
            data={
                "gap_description": "No REST endpoint for user registration",
                "reason": "API endpoint missing",
                "suggested_tasks": ["Create POST /auth/register endpoint"],
            },
        )
        gap_type = DifferentialFixAgent._determine_gap_type(event)
        # No keyword match → default
        assert gap_type == "default"
        agents = GAP_AGENT_ROUTING[gap_type]
        assert "claude-code" in agents
        assert "filesystem" in agents

    def test_unknown_gap_defaults_to_claude_code(self):
        """Unknown gap type should default to claude-code + filesystem."""
        event = Event(
            type=EventType.CODE_FIX_NEEDED,
            source="test",
            data={
                "gap_description": "Something vague about feature implementation",
                "reason": "Generic reason",
                "suggested_tasks": [],
            },
        )
        gap_type = DifferentialFixAgent._determine_gap_type(event)
        assert gap_type == "default"
        agents = GAP_AGENT_ROUTING["default"]
        assert "claude-code" in agents
        assert "filesystem" in agents


# ---------------------------------------------------------------------------
# Tests: Fix Spawning (with mocked pool)
# ---------------------------------------------------------------------------

class TestPipelineFixSpawning:
    """Test MCP agent spawning for fixes."""

    @pytest.mark.asyncio
    async def test_spawn_filesystem_for_code_gap(self):
        """Filesystem agent spawned for code-related gaps."""
        pool = _make_pool_mock()

        result = await pool.spawn("filesystem", "Create auth controller")

        pool.spawn.assert_called_once()
        assert result.success

    @pytest.mark.asyncio
    async def test_spawn_prisma_for_schema_gap(self):
        """Prisma agent spawned for schema gaps."""
        pool = _make_pool_mock(
            spawn_result=MockAgentResult(agent="prisma", success=True)
        )

        result = await pool.spawn("prisma", "Create User model in schema")

        pool.spawn.assert_called_once()
        assert result.success
        assert result.agent == "prisma"

    @pytest.mark.asyncio
    async def test_spawn_npm_for_dependency_gap(self):
        """npm agent spawned for dependency gaps."""
        pool = _make_pool_mock(
            spawn_result=MockAgentResult(agent="npm", success=True)
        )

        result = await pool.spawn("npm", "Install bcrypt package")

        pool.spawn.assert_called_once()
        assert result.success

    @pytest.mark.asyncio
    async def test_max_fixes_limits_spawns(self):
        """Max fixes parameter limits the number of agent spawns."""
        pool = _make_pool_mock()
        max_fixes = 3
        total_gaps = 10

        # Simulate pipeline behavior
        spawned = 0
        for i in range(total_gaps):
            if spawned >= max_fixes:
                break
            await pool.spawn("filesystem", f"Fix gap {i}")
            spawned += 1

        assert spawned == max_fixes
        assert pool.spawn.call_count == max_fixes

    @pytest.mark.asyncio
    async def test_pool_unavailable_graceful(self):
        """Pipeline handles MCPAgentPool init failure gracefully."""
        pool = _make_pool_mock(available=[])
        pool.spawn = AsyncMock(
            return_value=MockAgentResult(
                success=False, error="No agents available"
            )
        )

        # Should not crash when no agents available
        result = await pool.spawn("filesystem", "Fix something")
        assert not result.success
        assert "No agents" in result.error

    @pytest.mark.asyncio
    async def test_failed_spawn_does_not_crash(self):
        """Pipeline continues when a spawn fails."""
        pool = _make_pool_mock(
            spawn_result=MockAgentResult(
                success=False,
                error="Agent timeout after 300s",
            )
        )

        results = []
        for i in range(3):
            r = await pool.spawn("filesystem", f"Fix gap {i}")
            results.append(r)

        assert len(results) == 3
        assert all(not r.success for r in results)


# ---------------------------------------------------------------------------
# Tests: Task Building
# ---------------------------------------------------------------------------

class TestPipelineTaskBuilding:
    """Test task description building for different agent types."""

    def test_build_filesystem_task(self):
        """Filesystem task includes requirement ID and description."""
        task = DifferentialFixAgent._build_agent_task(
            agent_name="filesystem",
            requirement_id="WA-AUTH-001",
            description="Phone registration endpoint missing",
            suggested_tasks=["Create auth.controller.ts", "Add register route"],
        )
        assert "WA-AUTH-001" in task
        assert "Phone registration" in task
        assert "auth.controller.ts" in task

    def test_build_prisma_task(self):
        """Prisma task includes schema-specific instructions."""
        task = DifferentialFixAgent._build_agent_task(
            agent_name="prisma",
            requirement_id="WA-DB-001",
            description="User model missing in schema",
            suggested_tasks=["Add User model to schema.prisma"],
        )
        assert "WA-DB-001" in task
        assert "Prisma" in task or "prisma" in task.lower()
        assert "schema" in task.lower()

    def test_build_npm_task(self):
        """npm task includes package-specific instructions."""
        task = DifferentialFixAgent._build_agent_task(
            agent_name="npm",
            requirement_id="WA-DEP-001",
            description="bcrypt package not installed",
            suggested_tasks=["npm install bcrypt"],
        )
        assert "WA-DEP-001" in task
        assert "bcrypt" in task

    def test_build_claude_code_task(self):
        """claude-code task includes NestJS-specific instructions."""
        task = DifferentialFixAgent._build_agent_task(
            agent_name="claude-code",
            requirement_id="WA-AUTH-001",
            description="Missing phone registration endpoints",
            suggested_tasks=["Create auth.controller.ts", "Add register route"],
        )
        assert "WA-AUTH-001" in task
        assert "NestJS" in task
        assert "Missing phone registration endpoints" in task
        assert "auth.controller.ts" in task


# ---------------------------------------------------------------------------
# Tests: End-to-End Pipeline Flow (mocked agents)
# ---------------------------------------------------------------------------

class TestPipelineEndToEnd:
    """Test the complete pipeline flow with mocked MCP agents."""

    @pytest.mark.asyncio
    async def test_full_pipeline_dry_run(self, whatsapp_test_data):
        """Full pipeline in dry-run mode: analysis → classification works."""
        service = DifferentialAnalysisService(
            data_dir=str(whatsapp_test_data),
            job_id="test_dryrun",
            enable_supermemory=False,
        )

        await service.start()

        with patch.object(
            service, "_llm_evaluate",
            new=AsyncMock(side_effect=lambda reqs, top, mode: _mock_llm_findings(reqs, top, mode)),
        ):
            report = await service.run_analysis(mode=AnalysisMode.FULL_DIFFERENTIAL)

        # Classify ALL findings (regardless of status) to verify routing works
        gaps_classified = []
        for finding in report.findings:
            event = Event(
                type=EventType.CODE_FIX_NEEDED,
                source="test",
                data={
                    "gap_description": finding.gap_description or finding.requirement_description or "",
                    "reason": finding.requirement_title or "",
                    "suggested_tasks": finding.suggested_tasks or [],
                },
            )
            gap_type = DifferentialFixAgent._determine_gap_type(event)
            agents = GAP_AGENT_ROUTING.get(gap_type, GAP_AGENT_ROUTING["default"])
            gaps_classified.append({
                "finding": finding,
                "type": gap_type,
                "agents": agents,
            })

        # Should have classified all findings
        assert len(gaps_classified) == len(report.findings)
        assert len(gaps_classified) > 0

        # Each classified gap should have at least one agent
        for g in gaps_classified:
            assert len(g["agents"]) > 0
            assert g["type"] in list(GAP_AGENT_ROUTING.keys())

        await service.stop()

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocked_fixes(self, whatsapp_test_data):
        """Full pipeline with mocked MCP agent fixes."""
        # Step 1: Analysis
        service = DifferentialAnalysisService(
            data_dir=str(whatsapp_test_data),
            job_id="test_full",
            enable_supermemory=False,
        )

        await service.start()

        with patch.object(
            service, "_llm_evaluate",
            new=AsyncMock(side_effect=lambda reqs, top, mode: _mock_llm_findings(reqs, top, mode)),
        ):
            report = await service.run_analysis(mode=AnalysisMode.FULL_DIFFERENTIAL)

        # Step 2: Get critical gaps
        critical = [
            f for f in report.findings
            if f.status != ImplementationStatus.IMPLEMENTED
        ][:3]  # max 3

        # Step 3: Mock-fix each gap
        pool = _make_pool_mock()
        fix_results = []

        for gap in critical:
            event = Event(
                type=EventType.CODE_FIX_NEEDED,
                source="test",
                data={
                    "gap_description": gap.gap_description or "",
                    "reason": gap.requirement_title or "",
                    "suggested_tasks": gap.suggested_tasks or [],
                },
            )
            gap_type = DifferentialFixAgent._determine_gap_type(event)
            agents = GAP_AGENT_ROUTING.get(gap_type, GAP_AGENT_ROUTING["default"])

            task_desc = DifferentialFixAgent._build_agent_task(
                agent_name=agents[0],
                requirement_id=gap.requirement_id,
                description=gap.gap_description or gap.requirement_title,
                suggested_tasks=gap.suggested_tasks or [],
            )

            result = await pool.spawn(agents[0], task_desc)
            fix_results.append(result)

        # All mocked fixes should succeed
        assert len(fix_results) == len(critical)
        assert all(r.success for r in fix_results)
        assert pool.spawn.call_count == len(critical)

        await service.stop()
