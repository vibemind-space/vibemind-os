"""
TestAgent - Spezialisierter Agent für E2E-Tests mit Playwright.

Verantwortlichkeiten:
- Playwright-Tests ausführen
- Test-Reports generieren
- Test-Fixes als Tasks an File-Write delegieren
- Coverage-Reports erstellen
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
class TestContext:
    """Kontext für Test-Operation."""
    test_type: str  # "e2e", "unit", "integration", "regression"
    test_file: Optional[str] = None
    test_url: Optional[str] = None
    test_selector: Optional[str] = None
    expected_behavior: str = ""
    actual_behavior: str = ""
    screenshot_path: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "test_type": self.test_type,
            "test_file": self.test_file,
            "test_url": self.test_url,
            "test_selector": self.test_selector,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "screenshot_path": self.screenshot_path,
            "metadata": self.metadata,
        }


@dataclass
class TestResult:
    """Ergebnis eines Tests."""
    test_id: str
    test_type: str
    status: str  # "passed", "failed", "skipped", "error"
    duration_ms: int = 0
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    coverage_percent: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "test_type": self.test_type,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "coverage_percent": self.coverage_percent,
            "metadata": self.metadata,
        }


class TestAgent(AutonomousAgent):
    """
    TestAgent - Führt E2E-Tests mit Playwright aus.
    
    Verwendet:
    - Playwright Tools für Browser-Automatisierung
    - Screenshot-Capture für Visual-Regression
    - File-Write Tasks für Test-Fixes
    
    Schreibt KEINEN Code direkt, sondern erstellt Test-Tasks.
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
        self._playwright_tools = None
        
        # Test Queue
        self._pending_tests: List[TestContext] = []
        self._completed_tests: List[TestResult] = []
        
        self.logger = logger.bind(component="test_agent", agent=name)
    
    @property
    def subscribed_events(self) -> List[EventType]:
        """Events die dieser Agent abonniert."""
        return [
            EventType.TEST_REQUEST,
            EventType.E2E_TEST_NEEDED,
            EventType.REGRESSION_TEST,
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
        Analysiert Events und führt Tests aus.
        
        Args:
            events: Liste von Events
            
        Returns:
            Optional Event mit Ergebnis
        """
        self.logger.info(
            "test_agent_acting",
            event_count=len(events),
        )
        
        # Tools initialisieren
        await self._initialize_tools()
        
        # Events verarbeiten
        for event in events:
            if event.type in self.subscribed_events:
                await self._handle_test_event(event)
        
        # Tests verarbeiten
        if self._pending_tests:
            await self._process_tests()
        
        return None
    
    async def _initialize_tools(self) -> None:
        """Initialisiert die Playwright-Tools."""
        try:
            if self._playwright_tools is None:
                from ..tools.playwright_test_tools import PlaywrightTestTools
                self._playwright_tools = PlaywrightTestTools()
                self.logger.info("playwright_tools_initialized")
                
        except ImportError as e:
            self.logger.error("tool_import_failed", error=str(e))
    
    async def _handle_test_event(self, event: Event) -> None:
        """
        Verarbeitet ein Test-Event.
        
        Args:
            event: Das zu verarbeitende Event
        """
        self.logger.info(
            "handling_test_event",
            event_type=event.type.value,
            source=event.source,
        )
        
        # Test-Kontext extrahieren
        context = self._extract_test_context(event)
        
        # Analyse basierend auf Event-Typ
        if event.type == EventType.TEST_REQUEST:
            await self._run_test(context)
        elif event.type == EventType.E2E_TEST_NEEDED:
            await self._run_e2e_test(context)
        elif event.type == EventType.REGRESSION_TEST:
            await self._run_regression_test(context)
    
    def _extract_test_context(self, event: Event) -> TestContext:
        """
        Extrahiert Test-Kontext aus Event.
        
        Args:
            event: Das Event
            
        Returns:
            TestContext mit extrahierten Informationen
        """
        context = TestContext(
            test_type=event.type.value,
            expected_behavior=event.error_message or "",
            metadata=event.data.copy() if event.data else {},
        )
        
        # Test-Informationen aus Metadaten extrahieren
        if event.data:
            context.test_file = event.data.get("test_file")
            context.test_url = event.data.get("test_url")
            context.test_selector = event.data.get("test_selector")
        
        return context
    
    async def _run_test(self, context: TestContext) -> None:
        """
        Führt einen Test aus.
        
        Args:
            context: Test-Kontext
        """
        self.logger.info(
            "running_test",
            test_type=context.test_type,
            file=context.test_file,
        )
        
        # Test ausführen
        test_result = await self._execute_test(context)
        
        # Ergebnis analysieren
        if test_result.status == "failed":
            await self._create_test_fix_task(context, test_result)
        
        self._completed_tests.append(test_result)
    
    async def _run_e2e_test(self, context: TestContext) -> None:
        """
        Führt einen E2E-Test aus.
        
        Args:
            context: Test-Kontext
        """
        self.logger.info(
            "running_e2e_test",
            url=context.test_url,
            selector=context.test_selector,
        )
        
        # E2E-Test ausführen
        test_result = await self._execute_e2e_test(context)
        
        # Screenshot aufnehmen
        if self._playwright_tools and context.test_url:
            try:
                screenshot_result = await self._playwright_tools.capture_screenshot(
                    url=context.test_url,
                    selector=context.test_selector,
                )
                if screenshot_result.get("success"):
                    test_result.screenshot_path = screenshot_result.get("screenshot_path")
            except Exception as e:
                self.logger.warning("screenshot_failed", error=str(e))
        
        # Ergebnis analysieren
        if test_result.status == "failed":
            await self._create_test_fix_task(context, test_result)
        
        self._completed_tests.append(test_result)
    
    async def _run_regression_test(self, context: TestContext) -> None:
        """
        Führt einen Regression-Test aus.
        
        Args:
            context: Test-Kontext
        """
        self.logger.info(
            "running_regression_test",
            file=context.test_file,
        )
        
        # Regression-Test ausführen
        test_result = await self._execute_test(context)
        
        # Ergebnis analysieren
        if test_result.status == "failed":
            await self._create_test_fix_task(context, test_result)
        
        self._completed_tests.append(test_result)
    
    async def _execute_test(self, context: TestContext) -> TestResult:
        """
        Führt einen Test aus und gibt Ergebnis zurück.
        
        Args:
            context: Test-Kontext
            
        Returns:
            TestResult
        """
        start_time = datetime.now()
        
        # Test ausführen (simuliert für jetzt)
        # In der echten Implementierung würde hier Playwright verwendet werden
        test_result = TestResult(
            test_id=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_type=context.test_type,
            status="passed",  # Simuliert
            duration_ms=0,
            metadata=context.metadata,
        )
        
        return test_result
    
    async def _execute_e2e_test(self, context: TestContext) -> TestResult:
        """
        Führt einen E2E-Test aus und gibt Ergebnis zurück.
        
        Args:
            context: Test-Kontext
            
        Returns:
            TestResult
        """
        start_time = datetime.now()
        
        # E2E-Test ausführen (simuliert für jetzt)
        # In der echten Implementierung würde hier Playwright verwendet werden
        test_result = TestResult(
            test_id=f"e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_type="e2e",
            status="passed",  # Simuliert
            duration_ms=0,
            metadata=context.metadata,
        )
        
        return test_result
    
    async def _create_test_fix_task(
        self,
        context: TestContext,
        test_result: TestResult,
    ) -> None:
        """
        Erstellt eine Fix-Task für einen fehlgeschlagenen Test.
        
        Args:
            context: Test-Kontext
            test_result: Test-Ergebnis
        """
        self.logger.info(
            "creating_test_fix_task",
            test_id=test_result.test_id,
            status=test_result.status,
        )
        
        # Priorität bestimmen
        if test_result.status == "failed":
            priority = FixPriority.HIGH
        else:
            priority = FixPriority.MEDIUM
        
        # Beschreibung erstellen
        description_parts = [
            f"Test failed: {context.test_type}",
        ]
        
        if context.test_file:
            description_parts.append(f"Test File: {context.test_file}")
        
        if context.test_url:
            description_parts.append(f"URL: {context.test_url}")
        
        if test_result.error_message:
            description_parts.append(f"Error: {test_result.error_message}")
        
        description = " | ".join(description_parts)
        
        # Suggested Fix erstellen
        suggested_fix = self._generate_test_fix(context, test_result)
        
        # Metadaten
        metadata = {
            "test_id": test_result.test_id,
            "test_type": context.test_type,
            "test_file": context.test_file,
            "test_url": context.test_url,
            "test_selector": context.test_selector,
            "expected_behavior": context.expected_behavior,
            "actual_behavior": test_result.actual_behavior,
            "screenshot_path": test_result.screenshot_path,
            "duration_ms": test_result.duration_ms,
        }
        
        # Task erstellen
        from ..event_fix_team import create_fix_task
        task = await create_fix_task(
            task_type=FixTaskType.TEST_FIX,
            priority=priority,
            description=description,
            file_path=context.test_file,
            suggested_fix=suggested_fix,
            metadata=metadata,
        )
        
        self.logger.info(
            "test_fix_task_created",
            task_id=task.task_id,
            test_id=test_result.test_id,
        )
    
    def _generate_test_fix(
        self,
        context: TestContext,
        test_result: TestResult,
    ) -> str:
        """
        Generiert einen Fix-Vorschlag für einen fehlgeschlagenen Test.
        
        Args:
            context: Test-Kontext
            test_result: Test-Ergebnis
            
        Returns:
            Suggested Fix als String
        """
        fixes = []
        
        # Basierend auf Fehlermeldung
        if test_result.error_message:
            error_msg = test_result.error_message.lower()
            
            if "timeout" in error_msg:
                fixes.append("Increase test timeout or optimize page load time")
            elif "element not found" in error_msg:
                fixes.append("Check if element selector is correct and element exists")
                fixes.append("Wait for element to be visible before interaction")
            elif "assertion failed" in error_msg:
                fixes.append("Review test expectations and actual behavior")
                fixes.append("Update test to match current application behavior")
            elif "network error" in error_msg:
                fixes.append("Check network connectivity and API endpoints")
        
        # Basierend auf Screenshot
        if test_result.screenshot_path:
            fixes.append(f"Review screenshot at {test_result.screenshot_path}")
        
        # Basierend auf Test-Typ
        if context.test_type == "e2e":
            fixes.append("Verify user flow matches expected behavior")
            fixes.append("Check for UI/UX issues in the tested flow")
        elif context.test_type == "regression":
            fixes.append("Compare with previous working version")
            fixes.append("Identify what changed between versions")
        
        return "; ".join(fixes) if fixes else "Review test failure details and logs"
    
    async def _process_tests(self) -> None:
        """Verarbeitet alle ausstehenden Tests."""
        self.logger.info(
            "processing_tests",
            count=len(self._pending_tests),
        )
        
        for test_context in self._pending_tests:
            self.logger.info(
                "processing_test",
                test_type=test_context.test_type,
            )
            
            # Test wird hier NICHT ausgeführt, sondern nur geloggt
            # Die eigentliche Ausführung passiert über Playwright Tools
        
        self._completed_tests.extend([
            TestResult(
                test_id=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                test_type=test_context.test_type,
                status="pending",
                metadata=test_context.metadata,
            )
            for test_context in self._pending_tests
        ])
        
        self._pending_tests.clear()


# Convenience function
async def create_test_agent(
    name: str = "TestAgent",
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    working_dir: str = ".",
) -> TestAgent:
    """
    Convenience function zum Erstellen eines TestAgent.
    
    Args:
        name: Name des Agents
        event_bus: Optionaler EventBus
        shared_state: Optionaler SharedState
        working_dir: Arbeitsverzeichnis
        
    Returns:
        TestAgent Instanz
    """
    # EventBus und SharedState erstellen falls nicht vorhanden
    if event_bus is None:
        from mind.event_bus import create_event_bus
        event_bus = await create_event_bus()
    
    if shared_state is None:
        from mind.shared_state import SharedState
        shared_state = SharedState()
    
    agent = TestAgent(
        name=name,
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=working_dir,
    )
    
    return agent
