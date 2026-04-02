#!/usr/bin/env python3
"""
Recovery Strategies - Iteration 4

Automatische Recovery-Strategien basierend auf Fehlertyp.

Features:
- Retry mit Exponential Backoff
- Resource-Erstellung bei NOT_FOUND
- Dependency-Installation bei fehlenden Paketen
- Escalation bei kritischen Fehlern
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
import logging
import random

from error_classifier import ErrorType, ClassifiedError, ErrorSeverity

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Ergebnis eines Recovery-Versuchs"""
    success: bool
    error_type: ErrorType
    strategy_used: str
    attempts: int = 1
    recovered_value: Any = None
    error: Optional[str] = None
    escalated: bool = False
    duration_ms: int = 0


@dataclass
class RecoveryContext:
    """Kontext für Recovery-Versuche"""
    original_error: ClassifiedError
    tool_name: str
    tool_args: Dict[str, Any]
    attempt_number: int = 0
    max_attempts: int = 3
    previous_results: List[RecoveryResult] = field(default_factory=list)


class RecoveryStrategy(ABC):
    """Abstrakte Basis-Klasse für Recovery-Strategien"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name der Strategie"""
        pass

    @property
    @abstractmethod
    def handles(self) -> List[ErrorType]:
        """Welche Fehlertypen diese Strategie behandelt"""
        pass

    @abstractmethod
    async def execute(
        self,
        context: RecoveryContext,
        retry_fn: Optional[Callable] = None
    ) -> RecoveryResult:
        """Führt die Recovery-Strategie aus"""
        pass


class RetryWithBackoffStrategy(RecoveryStrategy):
    """
    Retry mit Exponential Backoff.

    Für transiente Fehler, Timeouts und Connection-Errors.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: float = 0.5
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    @property
    def name(self) -> str:
        return "RetryWithBackoff"

    @property
    def handles(self) -> List[ErrorType]:
        return [ErrorType.TRANSIENT, ErrorType.TIMEOUT, ErrorType.CONNECTION]

    def _calculate_delay(self, attempt: int) -> float:
        """Berechnet Delay mit Exponential Backoff + Jitter"""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        # Jitter hinzufügen
        jitter = delay * self.jitter * random.random()
        return delay + jitter

    async def execute(
        self,
        context: RecoveryContext,
        retry_fn: Optional[Callable] = None
    ) -> RecoveryResult:
        start_time = time.time()

        if not retry_fn:
            return RecoveryResult(
                success=False,
                error_type=context.original_error.error_type,
                strategy_used=self.name,
                error="No retry function provided"
            )

        attempt = context.attempt_number

        if attempt >= context.max_attempts:
            return RecoveryResult(
                success=False,
                error_type=context.original_error.error_type,
                strategy_used=self.name,
                attempts=attempt,
                error=f"Max attempts ({context.max_attempts}) reached",
                escalated=True
            )

        # Backoff warten
        delay = self._calculate_delay(attempt)
        logger.info(f"RetryWithBackoff: Waiting {delay:.2f}s before attempt {attempt + 1}")
        await asyncio.sleep(delay)

        try:
            result = await retry_fn(context.tool_name, context.tool_args)

            return RecoveryResult(
                success=True,
                error_type=context.original_error.error_type,
                strategy_used=self.name,
                attempts=attempt + 1,
                recovered_value=result,
                duration_ms=int((time.time() - start_time) * 1000)
            )

        except Exception as e:
            return RecoveryResult(
                success=False,
                error_type=context.original_error.error_type,
                strategy_used=self.name,
                attempts=attempt + 1,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )


class CreateResourceStrategy(RecoveryStrategy):
    """
    Erstellt fehlende Ressourcen.

    Für NOT_FOUND Fehler bei Dateien/Verzeichnissen.
    """

    @property
    def name(self) -> str:
        return "CreateResource"

    @property
    def handles(self) -> List[ErrorType]:
        return [ErrorType.NOT_FOUND]

    async def execute(
        self,
        context: RecoveryContext,
        retry_fn: Optional[Callable] = None
    ) -> RecoveryResult:
        start_time = time.time()

        # Pfad aus Kontext oder Arguments
        path = context.original_error.context.get("file")
        if not path:
            path = context.tool_args.get("path") or context.tool_args.get("file_path")

        if not path:
            return RecoveryResult(
                success=False,
                error_type=ErrorType.NOT_FOUND,
                strategy_used=self.name,
                error="No path found in context"
            )

        # Versuchen die Resource zu erstellen
        # In echtem System: MCP Tool aufrufen
        logger.info(f"CreateResource: Would create {path}")

        # Für jetzt: Signalisieren dass wir eine Erstellung brauchen
        return RecoveryResult(
            success=False,  # Wir können hier nicht direkt erstellen
            error_type=ErrorType.NOT_FOUND,
            strategy_used=self.name,
            error=f"Resource needs to be created: {path}",
            escalated=True,  # Agent muss übernehmen
            duration_ms=int((time.time() - start_time) * 1000)
        )


class InstallDependencyStrategy(RecoveryStrategy):
    """
    Installiert fehlende Dependencies.

    Für DEPENDENCY Fehler.
    """

    @property
    def name(self) -> str:
        return "InstallDependency"

    @property
    def handles(self) -> List[ErrorType]:
        return [ErrorType.DEPENDENCY]

    async def execute(
        self,
        context: RecoveryContext,
        retry_fn: Optional[Callable] = None
    ) -> RecoveryResult:
        start_time = time.time()

        # Module-Name extrahieren
        error_msg = context.original_error.original_message
        module_match = None

        # Verschiedene Patterns für Module-Namen
        import re
        patterns = [
            r"Cannot find module ['\"]([^'\"]+)['\"]",
            r"module ['\"]([^'\"]+)['\"] not found",
            r"npm ERR!.*['\"]([^'\"]+)['\"]",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_msg, re.IGNORECASE)
            if match:
                module_match = match.group(1)
                break

        if not module_match:
            return RecoveryResult(
                success=False,
                error_type=ErrorType.DEPENDENCY,
                strategy_used=self.name,
                error="Could not extract module name from error"
            )

        logger.info(f"InstallDependency: Would install {module_match}")

        # Signalisieren dass Installation nötig ist
        return RecoveryResult(
            success=False,
            error_type=ErrorType.DEPENDENCY,
            strategy_used=self.name,
            error=f"Need to install: npm install {module_match}",
            escalated=True,
            duration_ms=int((time.time() - start_time) * 1000)
        )


class EscalateStrategy(RecoveryStrategy):
    """
    Eskaliert an den User/Agent.

    Für nicht automatisch behebbare Fehler.
    """

    @property
    def name(self) -> str:
        return "Escalate"

    @property
    def handles(self) -> List[ErrorType]:
        return [ErrorType.PERMISSION, ErrorType.RESOURCE_LIMIT, ErrorType.UNKNOWN]

    async def execute(
        self,
        context: RecoveryContext,
        retry_fn: Optional[Callable] = None
    ) -> RecoveryResult:
        logger.warning(f"Escalating error: {context.original_error.error_type.value}")

        return RecoveryResult(
            success=False,
            error_type=context.original_error.error_type,
            strategy_used=self.name,
            error=f"Escalated: {context.original_error.suggested_action}",
            escalated=True
        )


class FixCodeStrategy(RecoveryStrategy):
    """
    Signalisiert dass Code-Fixes nötig sind.

    Für SYNTAX und TYPE_ERROR Fehler.
    """

    @property
    def name(self) -> str:
        return "FixCode"

    @property
    def handles(self) -> List[ErrorType]:
        return [ErrorType.SYNTAX, ErrorType.TYPE_ERROR]

    async def execute(
        self,
        context: RecoveryContext,
        retry_fn: Optional[Callable] = None
    ) -> RecoveryResult:
        start_time = time.time()

        # Datei und Zeile aus Kontext
        file_path = context.original_error.context.get("file", "unknown")
        line = context.original_error.context.get("line", "?")
        ts_code = context.original_error.context.get("ts_code", "")

        fix_hint = f"Fix needed in {file_path}:{line}"
        if ts_code:
            fix_hint += f" ({ts_code})"

        return RecoveryResult(
            success=False,
            error_type=context.original_error.error_type,
            strategy_used=self.name,
            error=fix_hint,
            escalated=True,  # Agent muss fixen
            duration_ms=int((time.time() - start_time) * 1000)
        )


class RecoveryOrchestrator:
    """
    Orchestriert Recovery-Strategien basierend auf Fehlertyp.

    Wählt die passende Strategie und führt sie aus.
    """

    def __init__(self):
        self.strategies: Dict[ErrorType, RecoveryStrategy] = {}

        # Strategies registrieren
        self._register_default_strategies()

        logger.info(f"RecoveryOrchestrator initialized with {len(self.strategies)} strategies")

    def _register_default_strategies(self):
        """Registriert die Standard-Strategien"""
        strategies = [
            RetryWithBackoffStrategy(),
            CreateResourceStrategy(),
            InstallDependencyStrategy(),
            EscalateStrategy(),
            FixCodeStrategy(),
        ]

        for strategy in strategies:
            for error_type in strategy.handles:
                self.strategies[error_type] = strategy

    def register_strategy(self, error_type: ErrorType, strategy: RecoveryStrategy):
        """Registriert eine benutzerdefinierte Strategie"""
        self.strategies[error_type] = strategy
        logger.info(f"Registered strategy {strategy.name} for {error_type.value}")

    def get_strategy(self, error_type: ErrorType) -> Optional[RecoveryStrategy]:
        """Gibt die Strategie für einen Fehlertyp zurück"""
        return self.strategies.get(error_type)

    async def handle_error(
        self,
        error: ClassifiedError,
        tool_name: str,
        tool_args: Dict[str, Any],
        retry_fn: Optional[Callable] = None,
        max_attempts: int = 3
    ) -> RecoveryResult:
        """
        Behandelt einen klassifizierten Fehler.

        Args:
            error: Der klassifizierte Fehler
            tool_name: Name des fehlgeschlagenen Tools
            tool_args: Arguments des Tools
            retry_fn: Funktion zum Retry
            max_attempts: Maximale Versuche

        Returns:
            RecoveryResult mit Ergebnis
        """
        strategy = self.get_strategy(error.error_type)

        if not strategy:
            logger.warning(f"No strategy for error type: {error.error_type.value}")
            return RecoveryResult(
                success=False,
                error_type=error.error_type,
                strategy_used="none",
                error="No recovery strategy available",
                escalated=True
            )

        context = RecoveryContext(
            original_error=error,
            tool_name=tool_name,
            tool_args=tool_args,
            max_attempts=max_attempts
        )

        logger.info(f"Executing recovery strategy: {strategy.name} for {error.error_type.value}")

        # Für Retry-Strategien: Mehrere Versuche
        if isinstance(strategy, RetryWithBackoffStrategy):
            for attempt in range(max_attempts):
                context.attempt_number = attempt
                result = await strategy.execute(context, retry_fn)

                if result.success:
                    return result

                context.previous_results.append(result)

            # Alle Versuche fehlgeschlagen
            return RecoveryResult(
                success=False,
                error_type=error.error_type,
                strategy_used=strategy.name,
                attempts=max_attempts,
                error=f"All {max_attempts} retry attempts failed",
                escalated=True
            )
        else:
            # Andere Strategien: Einmaliger Versuch
            return await strategy.execute(context, retry_fn)

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken über registrierte Strategien"""
        return {
            "strategies": {
                error_type.value: strategy.name
                for error_type, strategy in self.strategies.items()
            },
            "total_types_covered": len(self.strategies)
        }


# =============================================================================
# Test
# =============================================================================

async def test_recovery():
    """Test der Recovery-Strategien"""
    print("=== Recovery Strategies Test ===\n")

    from error_classifier import ErrorClassifier
    classifier = ErrorClassifier()
    orchestrator = RecoveryOrchestrator()

    # Test 1: Retry Strategy
    print("1. Retry Strategy (Transient Error):")
    error = classifier.classify("Error: connection reset, try again")

    call_count = 0
    async def mock_retry(tool, args):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise Exception("Still failing")
        return "Success!"

    result = await orchestrator.handle_error(
        error=error,
        tool_name="fetch_request",
        tool_args={"url": "http://example.com"},
        retry_fn=mock_retry,
        max_attempts=3
    )
    print(f"   Success: {result.success}")
    print(f"   Attempts: {result.attempts}")
    print(f"   Strategy: {result.strategy_used}")

    # Test 2: Not Found Strategy
    print("\n2. Not Found Strategy:")
    error = classifier.classify("Error: ENOENT: no such file '/app/config.json'")

    result = await orchestrator.handle_error(
        error=error,
        tool_name="filesystem_read_file",
        tool_args={"path": "/app/config.json"}
    )
    print(f"   Success: {result.success}")
    print(f"   Escalated: {result.escalated}")
    print(f"   Error: {result.error}")

    # Test 3: Type Error Strategy
    print("\n3. Type Error Strategy:")
    error = classifier.classify("TS2339: Property 'foo' does not exist on type 'Bar' at src/App.tsx:42")

    result = await orchestrator.handle_error(
        error=error,
        tool_name="build",
        tool_args={}
    )
    print(f"   Success: {result.success}")
    print(f"   Escalated: {result.escalated}")
    print(f"   Error: {result.error}")

    # Test 4: Stats
    print("\n4. Orchestrator Stats:")
    print(f"   {orchestrator.get_stats()}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_recovery())
