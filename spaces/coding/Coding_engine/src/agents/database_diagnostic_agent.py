"""
DatabaseDiagnosticAgent - LLM-Powered Schema Error Analysis.

Uses Claude to:
1. Analyze database schema errors (Prisma, Drizzle, etc.)
2. Understand the root cause of schema mismatches
3. Suggest specific fixes to the schema
4. Generate migration commands
5. Assess risk of data loss

This agent provides intelligent diagnosis that goes beyond pattern matching,
using LLM understanding of database schemas and relationships.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType
from src.tools.claude_code_tool import ClaudeCodeTool


logger = structlog.get_logger(__name__)


@dataclass
class SchemaDiagnosis:
    """Result of LLM schema error analysis."""
    root_cause: str
    affected_model: Optional[str] = None
    affected_field: Optional[str] = None
    suggested_fix: str = ""
    schema_patch: str = ""
    migration_cmd: str = ""
    risk_level: str = "low"  # low, medium, high
    data_loss_warning: Optional[str] = None
    related_models: list[str] = field(default_factory=list)


class DatabaseDiagnosticAgent(AutonomousAgent):
    """
    LLM-powered autonomous agent for diagnosing database schema errors.

    Uses Claude to:
    1. Parse and understand database error messages
    2. Analyze Prisma/Drizzle/TypeORM schemas
    3. Identify root cause of schema mismatches
    4. Suggest specific fixes with code patches
    5. Generate safe migration commands
    6. Warn about potential data loss

    Publishes SCHEMA_FIX_SUGGESTED event with diagnosis for GeneratorAgent to apply.
    """

    COOLDOWN_SECONDS = 10.0  # Allow rapid diagnosis

    # Database error patterns that trigger diagnosis
    DATABASE_ERROR_PATTERNS = [
        r"column .* does not exist",
        r"relation .* does not exist",
        r"table .* does not exist",
        r"P2002.*Unique constraint",
        r"P2003.*Foreign key constraint",
        r"P2025.*Record to .* not found",
        r"P1001.*Can't reach database",
        r"PrismaClientKnownRequestError",
        r"Invalid.*prisma.*invocation",
        r"Unknown arg",
        r"missing.*required.*field",
        r"type mismatch",
    ]

    def __init__(
        self,
        name: str = "DatabaseDiagnosticAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.claude_tool = ClaudeCodeTool(working_dir=working_dir)
        self._diagnosed_errors: set[str] = set()  # Track already diagnosed errors
        self.logger = logger.bind(agent=name)

        self.logger.info(
            "database_diagnostic_agent_initialized",
            working_dir=working_dir,
            subscribed_events=[e.value for e in self.subscribed_events],
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.VALIDATION_ERROR,  # Schema-related validation errors
            EventType.BUILD_FAILED,       # Build failures that might be DB-related
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Determine if any event contains a database error worth diagnosing."""
        for event in events:
            if not event.data:
                continue

            # Check for database error flag
            if event.data.get("is_database_error"):
                return True

            # Check error content for database patterns
            error_content = str(event.data.get("build_output", "")) + str(event.data.get("error", ""))

            for pattern in self.DATABASE_ERROR_PATTERNS:
                if re.search(pattern, error_content, re.IGNORECASE):
                    # Create hash to avoid re-diagnosing same error
                    error_hash = hash(error_content[:500])
                    if error_hash in self._diagnosed_errors:
                        self.logger.debug("error_already_diagnosed", hash=error_hash)
                        continue
                    self._diagnosed_errors.add(error_hash)
                    return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Diagnose database error using LLM."""
        # Find the first event with database error
        event = None
        for e in events:
            if e.data and (e.data.get("is_database_error") or e.data.get("build_output") or e.data.get("error")):
                event = e
                break

        if not event or not event.data:
            return

        self.logger.info(
            "diagnosing_database_error",
            event_type=event.type.value,
            project_id=event.data.get("project_id"),
        )

        try:
            # Extract error information
            error_output = event.data.get("build_output", "") or event.data.get("error", "")

            # Load schema files
            schema_content = await self._load_schema_files()

            if not schema_content:
                self.logger.warning("no_schema_files_found")
                return

            # Perform LLM diagnosis
            diagnosis = await self._analyze_database_error(error_output, schema_content)

            if diagnosis:
                self.logger.info(
                    "diagnosis_complete",
                    root_cause=diagnosis.root_cause,
                    affected_model=diagnosis.affected_model,
                    risk_level=diagnosis.risk_level,
                )

                # Publish diagnosis for GeneratorAgent to apply
                await self.event_bus.publish(Event(
                    type=EventType.DOCUMENT_CREATED,  # Use DOCUMENT_CREATED as signal
                    source=self.name,
                    data={
                        "document_type": "schema_diagnosis",
                        "project_id": event.data.get("project_id"),
                        "diagnosis": {
                            "root_cause": diagnosis.root_cause,
                            "affected_model": diagnosis.affected_model,
                            "affected_field": diagnosis.affected_field,
                            "suggested_fix": diagnosis.suggested_fix,
                            "schema_patch": diagnosis.schema_patch,
                            "migration_cmd": diagnosis.migration_cmd,
                            "risk_level": diagnosis.risk_level,
                            "data_loss_warning": diagnosis.data_loss_warning,
                            "related_models": diagnosis.related_models,
                        },
                        "original_error": error_output[:1000],
                    }
                ))

                # Also update shared state with diagnosis
                if self.shared_state:
                    self.shared_state.set(
                        f"schema_diagnosis_{event.data.get('project_id', 'default')}",
                        diagnosis.__dict__
                    )

        except Exception as e:
            self.logger.error("diagnosis_failed", error=str(e))

    async def _load_schema_files(self) -> str:
        """Load Prisma/Drizzle/TypeORM schema files."""
        schema_content = ""
        schema_files = [
            "prisma/schema.prisma",
            "drizzle/schema.ts",
            "src/db/schema.ts",
            "src/entity/*.ts",
            "src/models/*.ts",
        ]

        working_path = Path(self.working_dir)

        # Check for Prisma schema
        prisma_path = working_path / "prisma" / "schema.prisma"
        if prisma_path.exists():
            schema_content += f"=== PRISMA SCHEMA (prisma/schema.prisma) ===\n"
            schema_content += prisma_path.read_text()
            schema_content += "\n\n"

        # Check for Drizzle schema
        for drizzle_path in [
            working_path / "drizzle" / "schema.ts",
            working_path / "src" / "db" / "schema.ts",
        ]:
            if drizzle_path.exists():
                schema_content += f"=== DRIZZLE SCHEMA ({drizzle_path.relative_to(working_path)}) ===\n"
                schema_content += drizzle_path.read_text()
                schema_content += "\n\n"
                break

        # Check for TypeORM entities
        entities_dir = working_path / "src" / "entity"
        if entities_dir.exists():
            for entity_file in entities_dir.glob("*.ts"):
                schema_content += f"=== TYPEORM ENTITY ({entity_file.name}) ===\n"
                schema_content += entity_file.read_text()
                schema_content += "\n\n"

        return schema_content

    async def _analyze_database_error(
        self, error_output: str, schema_content: str
    ) -> Optional[SchemaDiagnosis]:
        """Use LLM to analyze database error and suggest fix."""

        prompt = f"""Analyze this database error and provide a detailed diagnosis.

## ERROR OUTPUT:
```
{error_output[:2000]}
```

## CURRENT SCHEMA:
```
{schema_content[:4000]}
```

## ANALYSIS REQUIRED:

1. **Root Cause**: What is the exact cause of this error?
2. **Affected Model/Table**: Which model or table is affected?
3. **Affected Field/Column**: Which specific field is missing or wrong?
4. **Suggested Fix**: What change should be made to fix this?
5. **Schema Patch**: Provide the exact code to add/modify in the schema
6. **Migration Command**: What command should be run after fixing?
7. **Risk Level**: low/medium/high - how risky is this fix?
8. **Data Loss Warning**: Will this fix cause any data loss?
9. **Related Models**: What other models might be affected?

Respond in this exact JSON format:
```json
{{
    "root_cause": "Clear explanation of what's wrong",
    "affected_model": "ModelName or null",
    "affected_field": "fieldName or null",
    "suggested_fix": "Human-readable fix description",
    "schema_patch": "Exact code to add/change in schema file",
    "migration_cmd": "npx prisma db push --accept-data-loss or similar",
    "risk_level": "low|medium|high",
    "data_loss_warning": "Warning message or null if safe",
    "related_models": ["Model1", "Model2"]
}}
```
"""

        try:
            result = await self.claude_tool.execute(
                prompt=prompt,
                skill="database-schema-generation",
                skill_tier="standard",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                diagnosis_data = json.loads(json_match.group(1))
                return SchemaDiagnosis(
                    root_cause=diagnosis_data.get("root_cause", "Unknown"),
                    affected_model=diagnosis_data.get("affected_model"),
                    affected_field=diagnosis_data.get("affected_field"),
                    suggested_fix=diagnosis_data.get("suggested_fix", ""),
                    schema_patch=diagnosis_data.get("schema_patch", ""),
                    migration_cmd=diagnosis_data.get("migration_cmd", "npx prisma db push"),
                    risk_level=diagnosis_data.get("risk_level", "medium"),
                    data_loss_warning=diagnosis_data.get("data_loss_warning"),
                    related_models=diagnosis_data.get("related_models", []),
                )
            else:
                # Try to extract useful info even without JSON
                self.logger.warning("json_parse_failed_using_fallback")
                return SchemaDiagnosis(
                    root_cause=f"LLM analysis: {result[:500]}",
                    suggested_fix="Review the schema and error manually",
                    migration_cmd="npx prisma db push",
                    risk_level="medium",
                )

        except Exception as e:
            self.logger.error("llm_analysis_failed", error=str(e))
            return None

    async def _apply_schema_fix(self, diagnosis: SchemaDiagnosis) -> bool:
        """Apply the suggested schema fix (if auto-fix is enabled)."""
        # This method could be used for auto-applying fixes
        # For now, we just publish the diagnosis for GeneratorAgent
        return True
