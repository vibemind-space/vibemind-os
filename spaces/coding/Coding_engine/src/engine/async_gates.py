"""
AsyncGates - Robuste Parallelisierung mit logischen Gates.

Dieses Modul implementiert logische Gates für asynchrone Operationen:
- AND Gate: Alle Tasks müssen erfolgreich sein
- OR Gate: Mindestens ein Task muss erfolgreich sein (First Success Wins)
- XOR Gate: Genau ein Pfad gewinnt (Racing)
- MAJORITY Gate: Mindestens N von M erfolgreich
- RETRY Gate: Automatische Retries mit Backoff
- CIRCUIT_BREAKER: Verhindert übermäßige Fehler

Diese Gates ermöglichen robuste Parallelisierung ohne Stabilitätsverlust.
"""
import asyncio
from dataclasses import dataclass, field
from typing import (
    TypeVar, Generic, Callable, Awaitable, Optional, Any,
    Union, Sequence
)
from enum import Enum
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')
R = TypeVar('R')


class GateResult(Enum):
    """Ergebnis-Status eines Gates."""
    SUCCESS = "success"
    PARTIAL = "partial"  # Einige erfolgreich
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TaskResult(Generic[T]):
    """Ergebnis eines einzelnen Tasks."""
    task_id: str
    success: bool
    result: Optional[T] = None
    error: Optional[str] = None
    execution_time_ms: int = 0
    retries: int = 0


@dataclass
class GateOutput(Generic[T]):
    """Gesamtergebnis eines Gates."""
    gate_type: str
    status: GateResult
    results: list[TaskResult[T]] = field(default_factory=list)
    successful_count: int = 0
    failed_count: int = 0
    total_time_ms: int = 0
    
    @property
    def success(self) -> bool:
        return self.status in (GateResult.SUCCESS, GateResult.PARTIAL)
    
    @property
    def first_success(self) -> Optional[TaskResult[T]]:
        """Gibt das erste erfolgreiche Ergebnis zurück."""
        for r in self.results:
            if r.success:
                return r
        return None
    
    @property
    def all_successful(self) -> list[TaskResult[T]]:
        """Alle erfolgreichen Ergebnisse."""
        return [r for r in self.results if r.success]
    
    def to_dict(self) -> dict:
        return {
            "gate_type": self.gate_type,
            "status": self.status.value,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "total_time_ms": self.total_time_ms,
            "results": [
                {
                    "task_id": r.task_id,
                    "success": r.success,
                    "error": r.error,
                    "time_ms": r.execution_time_ms,
                }
                for r in self.results
            ],
        }


class CircuitBreaker:
    """
    Circuit Breaker Pattern für Fehlertoleranz.
    
    Verhindert übermäßige Fehler durch temporäres Blockieren
    bei zu vielen aufeinanderfolgenden Fehlern.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = "closed"  # closed, open, half_open
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    async def can_execute(self) -> bool:
        """Prüft ob Ausführung erlaubt ist."""
        async with self._lock:
            if self._state == "closed":
                return True
            
            if self._state == "open":
                # Check if recovery timeout has passed
                if self._last_failure_time:
                    elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                    if elapsed >= self.recovery_timeout:
                        self._state = "half_open"
                        self._half_open_calls = 0
                        return True
                return False
            
            if self._state == "half_open":
                if self._half_open_calls < self.half_open_max:
                    self._half_open_calls += 1
                    return True
                return False
            
            return True
    
    async def record_success(self) -> None:
        """Erfolgreich ausgeführt."""
        async with self._lock:
            if self._state == "half_open":
                self._state = "closed"
            self._failure_count = 0
    
    async def record_failure(self) -> None:
        """Fehler aufgetreten."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            
            if self._state == "half_open":
                self._state = "open"
            elif self._failure_count >= self.failure_threshold:
                self._state = "open"
    
    @property
    def state(self) -> str:
        return self._state


class AsyncGates:
    """
    Zentrale Klasse für asynchrone Gate-Operationen.
    
    Ermöglicht robuste Parallelisierung mit verschiedenen Strategien:
    - AND: Alle müssen erfolgreich sein (asyncio.gather mit Fehlerhandling)
    - OR: Erster Erfolg gewinnt (Racing mit Cancellation)
    - XOR: Genau einer von alternativen Pfaden
    - MAJORITY: Mindestens N von M erfolgreich
    """
    
    def __init__(
        self,
        max_concurrent: int = 10,
        default_timeout: float = 1800.0,  # 30 minutes for Claude CLI operations
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.logger = logger.bind(component="async_gates")
    
    async def _execute_with_tracking(
        self,
        task_id: str,
        coro: Callable[[], Awaitable[T]],
        timeout: Optional[float] = None,
    ) -> TaskResult[T]:
        """
        Führt eine Coroutine mit Tracking und Timeout aus.
        """
        import time
        start = time.time()
        
        try:
            # Semaphore für Concurrency-Limit
            async with self._semaphore:
                # Circuit Breaker Check
                if not await self.circuit_breaker.can_execute():
                    return TaskResult(
                        task_id=task_id,
                        success=False,
                        error="Circuit breaker open",
                        execution_time_ms=0,
                    )
                
                # Execute with timeout
                effective_timeout = timeout or self.default_timeout
                result = await asyncio.wait_for(coro(), timeout=effective_timeout)
                
                # Success
                await self.circuit_breaker.record_success()
                
                return TaskResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                    execution_time_ms=int((time.time() - start) * 1000),
                )
                
        except asyncio.TimeoutError:
            await self.circuit_breaker.record_failure()
            return TaskResult(
                task_id=task_id,
                success=False,
                error=f"Timeout after {timeout or self.default_timeout}s",
                execution_time_ms=int((time.time() - start) * 1000),
            )
        except asyncio.CancelledError:
            return TaskResult(
                task_id=task_id,
                success=False,
                error="Cancelled",
                execution_time_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            await self.circuit_breaker.record_failure()
            return TaskResult(
                task_id=task_id,
                success=False,
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000),
            )

    async def AND(
        self,
        tasks: list[tuple[str, Callable[[], Awaitable[T]]]],
        fail_fast: bool = False,
        timeout: Optional[float] = None,
    ) -> GateOutput[T]:
        """
        AND Gate: Alle Tasks müssen erfolgreich sein.
        
        Args:
            tasks: Liste von (task_id, coroutine_factory) Tupeln
            fail_fast: Bei erstem Fehler alle anderen abbrechen
            timeout: Optional timeout für jeden Task
            
        Returns:
            GateOutput mit SUCCESS nur wenn alle erfolgreich
        """
        import time
        start = time.time()
        
        self.logger.info("and_gate_start", task_count=len(tasks))
        
        if not tasks:
            return GateOutput(
                gate_type="AND",
                status=GateResult.SUCCESS,
                results=[],
                successful_count=0,
                failed_count=0,
            )
        
        results: list[TaskResult[T]] = []
        
        if fail_fast:
            # Fail-fast mode: Cancel remaining on first failure
            pending_tasks = {
                asyncio.create_task(
                    self._execute_with_tracking(tid, coro, timeout)
                ): tid
                for tid, coro in tasks
            }
            
            try:
                while pending_tasks:
                    done, pending = await asyncio.wait(
                        pending_tasks.keys(),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    
                    for task in done:
                        result = task.result()
                        results.append(result)
                        del pending_tasks[task]
                        
                        if not result.success and fail_fast:
                            # Cancel all pending
                            for p in pending:
                                p.cancel()
                            # Wait for cancellation
                            if pending:
                                await asyncio.gather(*pending, return_exceptions=True)
                            break
                    
                    if not all(r.success for r in results):
                        break
                        
            except Exception as e:
                self.logger.error("and_gate_error", error=str(e))
        else:
            # Standard mode: Execute all, gather results
            coros = [
                self._execute_with_tracking(tid, coro, timeout)
                for tid, coro in tasks
            ]
            results = await asyncio.gather(*coros, return_exceptions=False)
        
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        status = GateResult.SUCCESS if failed == 0 else GateResult.FAILURE
        
        self.logger.info(
            "and_gate_complete",
            status=status.value,
            successful=successful,
            failed=failed,
        )
        
        return GateOutput(
            gate_type="AND",
            status=status,
            results=results,
            successful_count=successful,
            failed_count=failed,
            total_time_ms=int((time.time() - start) * 1000),
        )

    async def OR(
        self,
        tasks: list[tuple[str, Callable[[], Awaitable[T]]]],
        min_success: int = 1,
        timeout: Optional[float] = None,
    ) -> GateOutput[T]:
        """
        OR Gate: Mindestens min_success Tasks müssen erfolgreich sein.
        
        Sobald min_success erreicht, werden restliche Tasks abgebrochen.
        
        Args:
            tasks: Liste von (task_id, coroutine_factory) Tupeln
            min_success: Mindestanzahl erfolgreicher Tasks
            timeout: Optional timeout für jeden Task
            
        Returns:
            GateOutput mit SUCCESS wenn min_success erreicht
        """
        import time
        start = time.time()
        
        self.logger.info("or_gate_start", task_count=len(tasks), min_success=min_success)
        
        if not tasks:
            status = GateResult.SUCCESS if min_success == 0 else GateResult.FAILURE
            return GateOutput(
                gate_type="OR",
                status=status,
                results=[],
            )
        
        results: list[TaskResult[T]] = []
        successful_count = 0
        
        pending_tasks = {
            asyncio.create_task(
                self._execute_with_tracking(tid, coro, timeout)
            ): tid
            for tid, coro in tasks
        }
        
        try:
            while pending_tasks and successful_count < min_success:
                done, pending = await asyncio.wait(
                    pending_tasks.keys(),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                
                for task in done:
                    result = task.result()
                    results.append(result)
                    del pending_tasks[task]
                    
                    if result.success:
                        successful_count += 1
                        
                        if successful_count >= min_success:
                            # Cancel remaining tasks
                            for p in pending_tasks.keys():
                                p.cancel()
                            break
            
            # Collect results from cancelled tasks
            if pending_tasks:
                cancelled_results = await asyncio.gather(
                    *pending_tasks.keys(), 
                    return_exceptions=True
                )
                for tid, task_result in zip(pending_tasks.values(), cancelled_results):
                    if isinstance(task_result, TaskResult):
                        results.append(task_result)
                    else:
                        results.append(TaskResult(
                            task_id=tid,
                            success=False,
                            error="Cancelled (not needed)",
                        ))
                        
        except Exception as e:
            self.logger.error("or_gate_error", error=str(e))
        
        failed = len([r for r in results if not r.success])
        status = GateResult.SUCCESS if successful_count >= min_success else GateResult.FAILURE
        
        self.logger.info(
            "or_gate_complete",
            status=status.value,
            successful=successful_count,
            failed=failed,
        )
        
        return GateOutput(
            gate_type="OR",
            status=status,
            results=results,
            successful_count=successful_count,
            failed_count=failed,
            total_time_ms=int((time.time() - start) * 1000),
        )

    async def XOR(
        self,
        tasks: list[tuple[str, Callable[[], Awaitable[T]]]],
        timeout: Optional[float] = None,
    ) -> GateOutput[T]:
        """
        XOR Gate: Erster erfolgreicher Task gewinnt.
        
        Racing-Pattern: Alle Tasks starten parallel, erster Erfolg
        cancelt alle anderen.
        
        Args:
            tasks: Liste von (task_id, coroutine_factory) Tupeln
            timeout: Optional timeout
            
        Returns:
            GateOutput mit Ergebnis des ersten erfolgreichen Tasks
        """
        import time
        start = time.time()
        
        self.logger.info("xor_gate_start", task_count=len(tasks))
        
        if not tasks:
            return GateOutput(
                gate_type="XOR",
                status=GateResult.FAILURE,
                results=[],
            )
        
        results: list[TaskResult[T]] = []
        winner: Optional[TaskResult[T]] = None
        
        pending_tasks = {
            asyncio.create_task(
                self._execute_with_tracking(tid, coro, timeout)
            ): tid
            for tid, coro in tasks
        }
        
        try:
            while pending_tasks and winner is None:
                done, pending = await asyncio.wait(
                    pending_tasks.keys(),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                
                for task in done:
                    result = task.result()
                    results.append(result)
                    del pending_tasks[task]
                    
                    if result.success and winner is None:
                        winner = result
                        # Cancel all remaining
                        for p in pending_tasks.keys():
                            p.cancel()
                        break
            
            # Wait for cancellations
            if pending_tasks:
                await asyncio.gather(*pending_tasks.keys(), return_exceptions=True)
                        
        except Exception as e:
            self.logger.error("xor_gate_error", error=str(e))
        
        status = GateResult.SUCCESS if winner else GateResult.FAILURE
        
        self.logger.info(
            "xor_gate_complete",
            status=status.value,
            winner=winner.task_id if winner else None,
        )
        
        return GateOutput(
            gate_type="XOR",
            status=status,
            results=[winner] if winner else results,
            successful_count=1 if winner else 0,
            failed_count=len(results) - (1 if winner else 0),
            total_time_ms=int((time.time() - start) * 1000),
        )

    async def MAJORITY(
        self,
        tasks: list[tuple[str, Callable[[], Awaitable[T]]]],
        threshold: Optional[float] = None,
        min_count: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> GateOutput[T]:
        """
        MAJORITY Gate: Mindestens threshold% oder min_count müssen erfolgreich sein.
        
        Args:
            tasks: Liste von (task_id, coroutine_factory) Tupeln
            threshold: Prozentsatz (0.0-1.0), default 0.5
            min_count: Absolute Mindestanzahl (überschreibt threshold)
            timeout: Optional timeout
            
        Returns:
            GateOutput mit SUCCESS wenn Mehrheit erreicht
        """
        import time
        start = time.time()
        
        # Bestimme Required Count
        if min_count is not None:
            required = min_count
        else:
            threshold = threshold or 0.5
            required = max(1, int(len(tasks) * threshold) + 1)
        
        self.logger.info(
            "majority_gate_start",
            task_count=len(tasks),
            required=required,
        )
        
        # Execute all tasks in parallel
        coros = [
            self._execute_with_tracking(tid, coro, timeout)
            for tid, coro in tasks
        ]
        results = await asyncio.gather(*coros, return_exceptions=False)
        
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        status = GateResult.SUCCESS if successful >= required else GateResult.PARTIAL if successful > 0 else GateResult.FAILURE
        
        self.logger.info(
            "majority_gate_complete",
            status=status.value,
            successful=successful,
            required=required,
        )
        
        return GateOutput(
            gate_type="MAJORITY",
            status=status,
            results=results,
            successful_count=successful,
            failed_count=failed,
            total_time_ms=int((time.time() - start) * 1000),
        )

    async def RETRY(
        self,
        task_id: str,
        coro_factory: Callable[[], Awaitable[T]],
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential: bool = True,
        timeout: Optional[float] = None,
    ) -> TaskResult[T]:
        """
        RETRY Gate: Automatische Wiederholungen mit exponential backoff.
        
        Args:
            task_id: ID des Tasks
            coro_factory: Callable das die Coroutine erstellt
            max_retries: Maximale Anzahl Versuche
            base_delay: Basis-Verzögerung in Sekunden
            max_delay: Maximale Verzögerung
            exponential: Exponentielles Backoff
            timeout: Timeout pro Versuch
            
        Returns:
            TaskResult mit erstem erfolgreichen oder letztem fehlgeschlagenen Ergebnis
        """
        import time
        total_start = time.time()
        
        last_result: Optional[TaskResult[T]] = None
        
        for attempt in range(max_retries):
            self.logger.debug(
                "retry_attempt",
                task_id=task_id,
                attempt=attempt + 1,
                max_retries=max_retries,
            )
            
            result = await self._execute_with_tracking(
                f"{task_id}_attempt_{attempt}",
                coro_factory,
                timeout,
            )
            
            if result.success:
                result.task_id = task_id
                result.retries = attempt
                return result
            
            last_result = result
            
            # Calculate delay
            if attempt < max_retries - 1:
                if exponential:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                else:
                    delay = base_delay
                
                self.logger.debug(
                    "retry_delay",
                    task_id=task_id,
                    delay=delay,
                )
                await asyncio.sleep(delay)
        
        # All retries exhausted
        self.logger.warning(
            "retry_exhausted",
            task_id=task_id,
            total_attempts=max_retries,
        )
        
        if last_result:
            last_result.task_id = task_id
            last_result.retries = max_retries
            last_result.execution_time_ms = int((time.time() - total_start) * 1000)
            return last_result
        
        return TaskResult(
            task_id=task_id,
            success=False,
            error=f"Failed after {max_retries} retries",
            retries=max_retries,
            execution_time_ms=int((time.time() - total_start) * 1000),
        )


# Convenience functions
async def parallel_and(
    tasks: list[tuple[str, Callable[[], Awaitable[T]]]],
    max_concurrent: int = 10,
    fail_fast: bool = True,
) -> GateOutput[T]:
    """Convenience: AND Gate mit Defaults."""
    gates = AsyncGates(max_concurrent=max_concurrent)
    return await gates.AND(tasks, fail_fast=fail_fast)


async def parallel_or(
    tasks: list[tuple[str, Callable[[], Awaitable[T]]]],
    max_concurrent: int = 10,
    min_success: int = 1,
) -> GateOutput[T]:
    """Convenience: OR Gate mit Defaults."""
    gates = AsyncGates(max_concurrent=max_concurrent)
    return await gates.OR(tasks, min_success=min_success)


async def parallel_first(
    tasks: list[tuple[str, Callable[[], Awaitable[T]]]],
    max_concurrent: int = 10,
) -> GateOutput[T]:
    """Convenience: XOR Gate - First Success Wins."""
    gates = AsyncGates(max_concurrent=max_concurrent)
    return await gates.XOR(tasks)


async def with_retry(
    task_id: str,
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 3,
) -> TaskResult[T]:
    """Convenience: Retry Gate mit Defaults."""
    gates = AsyncGates()
    return await gates.RETRY(task_id, coro_factory, max_retries=max_retries)