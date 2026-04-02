"""
MigrationAgent - Spezialisierter Agent für Schema-Migrationen.

Verantwortlichkeiten:
- Schema-Migrationen planen
- Datenbank-Backups erstellen
- Migration-Skripte generieren (als Tasks)
- Rollback-Strategien definieren
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import structlog

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from mind.event_bus import EventBus, Event, EventType
from mind.shared_state import SharedState
from agents.autonomous_base import AutonomousAgent, AgentStatus
from ..event_fix_team import FixTask, FixTaskType, FixPriority

logger = structlog.get_logger(__name__)


@dataclass
class MigrationPlan:
    """Plan für eine Datenbank-Migration."""
    migration_id: str
    migration_type: str  # "schema", "data", "rollback"
    source_schema: str
    target_schema: str
    description: str
    rollback_plan: str
    estimated_duration: str = "5m"
    dependencies: List[str] = None
    created_at: str = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.dependencies is None:
            self.dependencies = []
    
    def to_dict(self) -> dict:
        return {
            "migration_id": self.migration_id,
            "migration_type": self.migration_type,
            "source_schema": self.source_schema,
            "target_schema": self.target_schema,
            "description": self.description,
            "rollback_plan": self.rollback_plan,
            "estimated_duration": self.estimated_duration,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
        }


@dataclass
class MigrationContext:
    """Kontext für Migrations-Operation."""
    migration_type: str
    schema_name: str
    change_description: str
    affected_tables: List[str] = None
    backup_required: bool = True
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.affected_tables is None:
            self.affected_tables = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "migration_type": self.migration_type,
            "schema_name": self.schema_name,
            "change_description": self.change_description,
            "affected_tables": self.affected_tables,
            "backup_required": self.backup_required,
            "metadata": self.metadata,
        }


class MigrationAgent(AutonomousAgent):
    """
    MigrationAgent - Plant und erstellt Migrations-Tasks.
    
    Verwendet:
    - PostgreSQL Tools für Schema-Analyse
    - Backup-Tools für Datenbank-Sicherungen
    - File-Write Tasks für Migration-Skripte
    
    Schreibt KEINEN Code direkt, sondern erstellt Migrations-Tasks.
    """
    
    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
    ):
        super().__init__(name, event_bus, shared_state, working_dir)
        
        # Tools (werden lazy geladen)
        self._postgres_tools = None
        self._backup_tools = None
        
        # Migration Queue
        self._pending_migrations: List[MigrationPlan] = []
        self._completed_migrations: List[MigrationPlan] = []
        
        self.logger = logger.bind(component="migration_agent", agent=name)
    
    @property
    def subscribed_events(self) -> List[EventType]:
        """Events die dieser Agent abonniert."""
        return [
            EventType.MIGRATION_NEEDED,
            EventType.SCHEMA_CHANGE,
            EventType.DATA_MIGRATION,
        ]
    
    async def should_act(self, events: List[Event]) -> bool:
        """Entscheidet ob der Agent agieren soll."""
        if not events:
            return False
        
        # Prüfen ob relevante Events vorhanden sind
        relevant_events = [
            e for e in events
            if e.type in self.subscribed_events
        ]
        
        return len(relevant_events) > 0
    
    async def act(self, events: List[Event]) -> Optional[Event]:
        """
        Analysiert Events und erstellt Migrations-Tasks.
        
        Args:
            events: Liste von Events
            
        Returns:
            Optional Event mit Ergebnis
        """
        self.logger.info(
            "migration_agent_acting",
            event_count=len(events),
        )
        
        # Tools initialisieren
        await self._initialize_tools()
        
        # Events verarbeiten
        for event in events:
            if event.type in self.subscribed_events:
                await self._handle_migration_event(event)
        
        # Migrations verarbeiten
        if self._pending_migrations:
            await self._process_migrations()
        
        return None
    
    async def _initialize_tools(self) -> None:
        """Initialisiert die Migrations-Tools."""
        try:
            if self._postgres_tools is None:
                from ..tools.postgres_debug_tools import PostgresDebugTools
                self._postgres_tools = PostgresDebugTools()
                self.logger.info("postgres_tools_initialized")
                
        except ImportError as e:
            self.logger.error("tool_import_failed", error=str(e))
    
    async def _handle_migration_event(self, event: Event) -> None:
        """
        Verarbeitet ein Migrations-Event.
        
        Args:
            event: Das zu verarbeitende Event
        """
        self.logger.info(
            "handling_migration_event",
            event_type=event.type.value,
            source=event.source,
        )
        
        # Migrations-Kontext extrahieren
        context = self._extract_migration_context(event)
        
        # Analyse basierend auf Event-Typ
        if event.type == EventType.MIGRATION_NEEDED:
            await self._plan_migration(context)
        elif event.type == EventType.SCHEMA_CHANGE:
            await self._plan_schema_change(context)
        elif event.type == EventType.DATA_MIGRATION:
            await self._plan_data_migration(context)
    
    def _extract_migration_context(self, event: Event) -> MigrationContext:
        """
        Extrahiert Migrations-Kontext aus Event.
        
        Args:
            event: Das Event
            
        Returns:
            MigrationContext mit extrahierten Informationen
        """
        context = MigrationContext(
            migration_type=event.type.value,
            change_description=event.error_message or "",
            metadata=event.data.copy() if event.data else {},
        )
        
        # Schema-Name aus Metadaten extrahieren
        if event.data:
            context.schema_name = event.data.get("schema_name", "public")
            context.affected_tables = event.data.get("affected_tables", [])
            context.backup_required = event.data.get("backup_required", True)
        
        return context
    
    async def _plan_migration(self, context: MigrationContext) -> None:
        """
        Plant eine Migration und erstellt Tasks.
        
        Args:
            context: Migrations-Kontext
        """
        self.logger.info(
            "planning_migration",
            schema=context.schema_name,
            type=context.migration_type,
        )
        
        # Schema-Analyse
        schema_info = {}
        if self._postgres_tools:
            try:
                tables_result = await self._postgres_tools.get_table_sizes(
                    schema=context.schema_name,
                )
                if tables_result.get("success"):
                    schema_info["tables"] = tables_result.get("tables", [])
            except Exception as e:
                self.logger.warning("schema_analysis_failed", error=str(e))
        
        # Migration-Plan erstellen
        migration_plan = MigrationPlan(
            migration_id=f"mig_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            migration_type="schema",
            source_schema=context.schema_name,
            target_schema=context.schema_name,
            description=context.change_description,
            rollback_plan=self._generate_rollback_plan(context),
            dependencies=self._identify_dependencies(context, schema_info),
        )
        
        self._pending_migrations.append(migration_plan)
        
        # Fix-Task erstellen
        await self._create_migration_task(migration_plan, context)
    
    async def _plan_schema_change(self, context: MigrationContext) -> None:
        """
        Plant eine Schema-Änderung und erstellt Tasks.
        
        Args:
            context: Migrations-Kontext
        """
        self.logger.info(
            "planning_schema_change",
            schema=context.schema_name,
            tables=context.affected_tables,
        )
        
        # Schema-Change Plan erstellen
        migration_plan = MigrationPlan(
            migration_id=f"schema_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            migration_type="schema",
            source_schema=context.schema_name,
            target_schema=context.schema_name,
            description=f"Schema change: {context.change_description}",
            rollback_plan=self._generate_rollback_plan(context),
            dependencies=context.affected_tables,
        )
        
        self._pending_migrations.append(migration_plan)
        
        # Fix-Task erstellen
        await self._create_migration_task(migration_plan, context)
    
    async def _plan_data_migration(self, context: MigrationContext) -> None:
        """
        Plant eine Daten-Migration und erstellt Tasks.
        
        Args:
            context: Migrations-Kontext
        """
        self.logger.info(
            "planning_data_migration",
            schema=context.schema_name,
            tables=context.affected_tables,
        )
        
        # Data-Migration Plan erstellen
        migration_plan = MigrationPlan(
            migration_id=f"data_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            migration_type="data",
            source_schema=context.schema_name,
            target_schema=context.schema_name,
            description=f"Data migration: {context.change_description}",
            rollback_plan=self._generate_rollback_plan(context),
            dependencies=context.affected_tables,
        )
        
        self._pending_migrations.append(migration_plan)
        
        # Fix-Task erstellen
        await self._create_migration_task(migration_plan, context)
    
    def _generate_rollback_plan(self, context: MigrationContext) -> str:
        """
        Generiert einen Rollback-Plan.
        
        Args:
            context: Migrations-Kontext
            
        Returns:
            Rollback-Plan als String
        """
        rollback_steps = []
        
        # Backup-Restore
        if context.backup_required:
            rollback_steps.append("Restore database from backup created before migration")
        
        # Schema-Rollback
        rollback_steps.append(f"Revert schema changes to {context.schema_name}")
        
        # Data-Rollback
        if context.affected_tables:
            for table in context.affected_tables:
                rollback_steps.append(f"Restore data in table {table}")
        
        return "; ".join(rollback_steps)
    
    def _identify_dependencies(
        self,
        context: MigrationContext,
        schema_info: Dict[str, Any]
    ) -> List[str]:
        """
        Identifiziert Abhängigkeiten für die Migration.
        
        Args:
            context: Migrations-Kontext
            schema_info: Schema-Informationen
            
        Returns:
            Liste von Abhängigkeiten
        """
        dependencies = []
        
        # Tabellen-Abhängigkeiten
        if context.affected_tables:
            for table in context.affected_tables:
                # Foreign Keys prüfen
                dependencies.append(f"Check foreign key constraints for {table}")
        
        # Index-Abhängigkeiten
        dependencies.append("Verify indexes on affected tables")
        
        # Trigger-Abhängigkeiten
        dependencies.append("Check triggers that reference affected tables")
        
        return dependencies
    
    async def _create_migration_task(
        self,
        migration_plan: MigrationPlan,
        context: MigrationContext,
    ) -> None:
        """
        Erstellt eine Fix-Task für die Migration.
        
        Args:
            migration_plan: Der Migrations-Plan
            context: Migrations-Kontext
        """
        # Priorität bestimmen
        if context.backup_required:
            priority = FixPriority.HIGH
        else:
            priority = FixPriority.MEDIUM
        
        # Beschreibung erstellen
        description_parts = [
            f"Migration: {migration_plan.description}",
            f"Type: {migration_plan.migration_type}",
            f"Schema: {migration_plan.source_schema}",
        ]
        
        if migration_plan.dependencies:
            description_parts.append(f"Dependencies: {', '.join(migration_plan.dependencies)}")
        
        description = " | ".join(description_parts)
        
        # Suggested Fix erstellen
        suggested_fix = self._generate_migration_fix(migration_plan, context)
        
        # Metadaten
        metadata = {
            "migration_id": migration_plan.migration_id,
            "migration_type": migration_plan.migration_type,
            "source_schema": migration_plan.source_schema,
            "target_schema": migration_plan.target_schema,
            "rollback_plan": migration_plan.rollback_plan,
            "dependencies": migration_plan.dependencies,
            "estimated_duration": migration_plan.estimated_duration,
            "affected_tables": context.affected_tables,
            "backup_required": context.backup_required,
        }
        
        # Task erstellen
        from ..event_fix_team import create_fix_task
        task = await create_fix_task(
            task_type=FixTaskType.MIGRATION,
            priority=priority,
            description=description,
            file_path=None,  # Migrations sind oft multi-file
            suggested_fix=suggested_fix,
            metadata=metadata,
        )
        
        self.logger.info(
            "migration_task_created",
            migration_id=migration_plan.migration_id,
            task_id=task.task_id,
        )
    
    def _generate_migration_fix(
        self,
        migration_plan: MigrationPlan,
        context: MigrationContext,
    ) -> str:
        """
        Generiert einen Fix-Vorschlag für die Migration.
        
        Args:
            migration_plan: Der Migrations-Plan
            context: Migrations-Kontext
            
        Returns:
            Suggested Fix als String
        """
        fixes = []
        
        # Backup erstellen
        if context.backup_required:
            fixes.append("Create database backup before migration")
        
        # Migration-Skript erstellen
        fixes.append(f"Generate migration script for {migration_plan.migration_type}")
        
        # Rollback vorbereiten
        fixes.append("Prepare rollback script based on rollback plan")
        
        # Dependencies prüfen
        if migration_plan.dependencies:
            fixes.append("Verify all dependencies are satisfied before migration")
        
        # Test-Plan
        fixes.append("Create test plan to verify migration success")
        
        return "; ".join(fixes)
    
    async def _process_migrations(self) -> None:
        """Verarbeitet alle ausstehenden Migrations."""
        self.logger.info(
            "processing_migrations",
            count=len(self._pending_migrations),
        )
        
        for migration in self._pending_migrations:
            self.logger.info(
                "processing_migration",
                migration_id=migration.migration_id,
                type=migration.migration_type,
            )
            
            # Migration wird hier NICHT ausgeführt, sondern nur geloggt
            # Die eigentliche Ausführung passiert über File-Write Tasks
        
        self._completed_migrations.extend(self._pending_migrations)
        self._pending_migrations.clear()


# Convenience function
async def create_migration_agent(
    name: str = "MigrationAgent",
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    working_dir: str = ".",
) -> MigrationAgent:
    """
    Convenience function zum Erstellen eines MigrationAgent.
    
    Args:
        name: Name des Agents
        event_bus: Optionaler EventBus
        shared_state: Optionaler SharedState
        working_dir: Arbeitsverzeichnis
        
    Returns:
        MigrationAgent Instanz
    """
    # EventBus und SharedState erstellen falls nicht vorhanden
    if event_bus is None:
        from mind.event_bus import create_event_bus
        event_bus = await create_event_bus()
    
    if shared_state is None:
        from mind.shared_state import SharedState
        shared_state = SharedState()
    
    agent = MigrationAgent(
        name=name,
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=working_dir,
    )
    
    return agent
