#!/usr/bin/env python3
"""
Circuit Breaker - Iteration 4

Schützt vor wiederholten Aufrufen fehlerhafter Tools.

Features:
- Blockiert Tools nach X Fehlern für Y Sekunden
- Half-Open State für Test-Aufrufe
- Automatisches Reset nach Erfolg
- Per-Tool und globale Limits
"""

import time
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Zustände des Circuit Breakers"""
    CLOSED = "closed"      # Normal - Aufrufe erlaubt
    OPEN = "open"          # Blockiert - Aufrufe abgelehnt
    HALF_OPEN = "half_open"  # Test-Phase - Ein Aufruf erlaubt


@dataclass
class CircuitStats:
    """Statistiken für einen Circuit"""
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    times_opened: int = 0
    times_half_opened: int = 0
    current_state: CircuitState = CircuitState.CLOSED


@dataclass
class CircuitConfig:
    """Konfiguration für einen Circuit Breaker"""
    failure_threshold: int = 3      # Nach X Fehlern öffnen
    success_threshold: int = 1      # Nach X Erfolgen schließen
    timeout_seconds: int = 60       # Zeit bis Half-Open
    half_open_max_calls: int = 1    # Max Calls in Half-Open


class ToolCircuitBreaker:
    """
    Circuit Breaker für einzelne Tools.

    Verhindert Ressourcenverschwendung durch wiederholte
    Aufrufe fehlerhafter Tools.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: int = 60,
        success_threshold: int = 1
    ):
        """
        Args:
            failure_threshold: Nach X Fehlern wird Circuit geöffnet
            timeout_seconds: Zeit bis Half-Open State
            success_threshold: Erfolge in Half-Open zum Schließen
        """
        self.default_config = CircuitConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout_seconds=timeout_seconds
        )

        # Per-Tool States
        self._circuits: Dict[str, CircuitStats] = {}
        self._tool_configs: Dict[str, CircuitConfig] = {}
        self._lock = Lock()

        # Half-Open Tracking
        self._half_open_calls: Dict[str, int] = {}

        logger.info(f"ToolCircuitBreaker initialized (threshold={failure_threshold}, timeout={timeout_seconds}s)")

    def _get_config(self, tool_name: str) -> CircuitConfig:
        """Gibt Konfiguration für ein Tool zurück"""
        return self._tool_configs.get(tool_name, self.default_config)

    def _get_stats(self, tool_name: str) -> CircuitStats:
        """Gibt Stats für ein Tool zurück (erstellt wenn nötig)"""
        if tool_name not in self._circuits:
            self._circuits[tool_name] = CircuitStats()
        return self._circuits[tool_name]

    def configure_tool(
        self,
        tool_name: str,
        failure_threshold: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        success_threshold: Optional[int] = None
    ):
        """
        Konfiguriert Tool-spezifische Schwellwerte.

        Args:
            tool_name: Name des Tools
            failure_threshold: Fehler bis Open
            timeout_seconds: Timeout bis Half-Open
            success_threshold: Erfolge bis Closed
        """
        config = CircuitConfig(
            failure_threshold=failure_threshold or self.default_config.failure_threshold,
            success_threshold=success_threshold or self.default_config.success_threshold,
            timeout_seconds=timeout_seconds or self.default_config.timeout_seconds
        )
        self._tool_configs[tool_name] = config
        logger.info(f"Configured circuit for {tool_name}: {config}")

    def get_state(self, tool_name: str) -> CircuitState:
        """
        Gibt den aktuellen State eines Tool-Circuits zurück.

        Berücksichtigt Timeout für automatischen Übergang zu Half-Open.
        """
        with self._lock:
            stats = self._get_stats(tool_name)
            config = self._get_config(tool_name)

            # Prüfen ob Open -> Half-Open
            if stats.current_state == CircuitState.OPEN:
                time_since_failure = time.time() - stats.last_failure_time

                if time_since_failure >= config.timeout_seconds:
                    stats.current_state = CircuitState.HALF_OPEN
                    stats.times_half_opened += 1
                    self._half_open_calls[tool_name] = 0
                    logger.info(f"Circuit {tool_name}: OPEN -> HALF_OPEN (timeout reached)")

            return stats.current_state

    def is_open(self, tool_name: str) -> bool:
        """
        Prüft ob ein Tool blockiert ist.

        Returns:
            True wenn der Circuit OPEN ist (Aufrufe blockiert)
        """
        state = self.get_state(tool_name)
        return state == CircuitState.OPEN

    def can_execute(self, tool_name: str) -> bool:
        """
        Prüft ob ein Tool-Aufruf erlaubt ist.

        In HALF_OPEN State werden begrenzte Test-Aufrufe erlaubt.

        Returns:
            True wenn Aufruf erlaubt
        """
        state = self.get_state(tool_name)

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.OPEN:
            return False

        # Half-Open: Begrenzte Aufrufe
        with self._lock:
            config = self._get_config(tool_name)
            current_calls = self._half_open_calls.get(tool_name, 0)

            if current_calls < config.half_open_max_calls:
                self._half_open_calls[tool_name] = current_calls + 1
                return True

            return False

    def record_success(self, tool_name: str):
        """
        Meldet einen erfolgreichen Tool-Aufruf.

        In HALF_OPEN: Wechsel zu CLOSED nach success_threshold Erfolgen.
        """
        with self._lock:
            stats = self._get_stats(tool_name)
            config = self._get_config(tool_name)

            stats.successes += 1
            stats.last_success_time = time.time()

            if stats.current_state == CircuitState.HALF_OPEN:
                # Erfolg in Half-Open: Schließen
                stats.current_state = CircuitState.CLOSED
                stats.failures = 0
                self._half_open_calls[tool_name] = 0
                logger.info(f"Circuit {tool_name}: HALF_OPEN -> CLOSED (success)")

            elif stats.current_state == CircuitState.CLOSED:
                # Im Closed State: Failure Counter zurücksetzen
                stats.failures = 0

    def record_failure(self, tool_name: str, error: Optional[str] = None):
        """
        Meldet einen fehlgeschlagenen Tool-Aufruf.

        Nach failure_threshold Fehlern: Wechsel zu OPEN.
        """
        with self._lock:
            stats = self._get_stats(tool_name)
            config = self._get_config(tool_name)

            stats.failures += 1
            stats.last_failure_time = time.time()

            if stats.current_state == CircuitState.HALF_OPEN:
                # Fehler in Half-Open: Sofort wieder öffnen
                stats.current_state = CircuitState.OPEN
                stats.times_opened += 1
                logger.warning(f"Circuit {tool_name}: HALF_OPEN -> OPEN (failure in half-open)")

            elif stats.current_state == CircuitState.CLOSED:
                # Prüfen ob Threshold erreicht
                if stats.failures >= config.failure_threshold:
                    stats.current_state = CircuitState.OPEN
                    stats.times_opened += 1
                    logger.warning(
                        f"Circuit {tool_name}: CLOSED -> OPEN "
                        f"({stats.failures} failures, threshold={config.failure_threshold})"
                    )
                    if error:
                        logger.warning(f"  Last error: {error[:100]}")

    def reset(self, tool_name: str):
        """Setzt einen Circuit manuell zurück"""
        with self._lock:
            if tool_name in self._circuits:
                self._circuits[tool_name] = CircuitStats()
                logger.info(f"Circuit {tool_name} manually reset")

    def reset_all(self):
        """Setzt alle Circuits zurück"""
        with self._lock:
            self._circuits.clear()
            self._half_open_calls.clear()
            logger.info("All circuits reset")

    def get_stats(self, tool_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Gibt Statistiken zurück.

        Args:
            tool_name: Optional - nur für dieses Tool

        Returns:
            Dict mit Statistiken
        """
        with self._lock:
            if tool_name:
                stats = self._get_stats(tool_name)
                return {
                    "tool": tool_name,
                    "state": stats.current_state.value,
                    "failures": stats.failures,
                    "successes": stats.successes,
                    "times_opened": stats.times_opened,
                    "times_half_opened": stats.times_half_opened,
                }
            else:
                # Alle Tools
                return {
                    tool: {
                        "state": s.current_state.value,
                        "failures": s.failures,
                        "successes": s.successes,
                        "times_opened": s.times_opened,
                    }
                    for tool, s in self._circuits.items()
                }

    def get_open_circuits(self) -> List[str]:
        """Gibt Liste aller offenen Circuits zurück"""
        return [
            tool for tool in self._circuits
            if self.get_state(tool) == CircuitState.OPEN
        ]

    def get_health_summary(self) -> Dict[str, Any]:
        """Gibt eine Gesundheitsübersicht zurück"""
        with self._lock:
            total = len(self._circuits)
            open_count = len(self.get_open_circuits())
            half_open = sum(
                1 for tool in self._circuits
                if self.get_state(tool) == CircuitState.HALF_OPEN
            )

            return {
                "total_circuits": total,
                "closed": total - open_count - half_open,
                "open": open_count,
                "half_open": half_open,
                "health_percentage": f"{((total - open_count) / max(total, 1) * 100):.1f}%",
                "open_tools": self.get_open_circuits(),
            }


class CircuitBreakerMiddleware:
    """
    Middleware die Circuit Breaker in Tool-Aufrufe integriert.

    Kann als Wrapper für MCP Tool-Aufrufe verwendet werden.
    """

    def __init__(self, breaker: ToolCircuitBreaker):
        self.breaker = breaker

    async def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        execute_fn
    ) -> Any:
        """
        Führt einen Tool-Aufruf mit Circuit Breaker Schutz aus.

        Args:
            tool_name: Name des Tools
            args: Tool-Arguments
            execute_fn: Async Funktion die das Tool ausführt

        Returns:
            Tool-Ergebnis

        Raises:
            CircuitOpenError: Wenn Circuit offen ist
        """
        if not self.breaker.can_execute(tool_name):
            raise CircuitOpenError(
                f"Circuit for {tool_name} is OPEN. "
                f"Retry after {self.breaker._get_config(tool_name).timeout_seconds}s"
            )

        try:
            result = await execute_fn(tool_name, args)
            self.breaker.record_success(tool_name)
            return result

        except Exception as e:
            self.breaker.record_failure(tool_name, str(e))
            raise


class CircuitOpenError(Exception):
    """Fehler wenn ein Circuit offen ist"""
    pass


# =============================================================================
# Test
# =============================================================================

def test_circuit_breaker():
    """Test der Circuit Breaker Funktionalität"""
    print("=== Circuit Breaker Test ===\n")

    breaker = ToolCircuitBreaker(
        failure_threshold=3,
        timeout_seconds=2,
        success_threshold=1
    )

    tool = "filesystem_write_file"

    # Test 1: Normal State
    print("1. Initial state:")
    print(f"   State: {breaker.get_state(tool).value}")
    print(f"   Can execute: {breaker.can_execute(tool)}")

    # Test 2: Record failures
    print("\n2. Recording failures:")
    for i in range(3):
        breaker.record_failure(tool, f"Error {i+1}")
        print(f"   After failure {i+1}: {breaker.get_state(tool).value}")

    # Test 3: Circuit should be open
    print("\n3. Circuit open:")
    print(f"   State: {breaker.get_state(tool).value}")
    print(f"   Can execute: {breaker.can_execute(tool)}")
    print(f"   Is open: {breaker.is_open(tool)}")

    # Test 4: Wait for timeout
    print("\n4. Waiting for timeout...")
    import time
    time.sleep(2.5)

    print(f"   State after wait: {breaker.get_state(tool).value}")
    print(f"   Can execute: {breaker.can_execute(tool)}")

    # Test 5: Success in half-open
    print("\n5. Success in half-open:")
    breaker.record_success(tool)
    print(f"   State: {breaker.get_state(tool).value}")

    # Test 6: Stats
    print("\n6. Stats:")
    print(f"   Tool stats: {breaker.get_stats(tool)}")
    print(f"   Health: {breaker.get_health_summary()}")

    # Test 7: Multiple tools
    print("\n7. Multiple tools:")
    breaker.record_failure("docker_compose_up")
    breaker.record_failure("docker_compose_up")
    breaker.record_failure("docker_compose_up")
    breaker.record_success("filesystem_read_file")

    print(f"   Open circuits: {breaker.get_open_circuits()}")
    print(f"   All stats: {breaker.get_stats()}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_circuit_breaker()
