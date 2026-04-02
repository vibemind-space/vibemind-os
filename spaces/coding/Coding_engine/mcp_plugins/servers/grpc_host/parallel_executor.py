#!/usr/bin/env python3
"""
Parallel Executor - Iteration 3

Parallele Ausführung unabhängiger Read-Operations für bessere Performance.

Features:
- Erkennt parallelisierbare Tool-Calls
- Batch-Ausführung mit asyncio.gather
- Respektiert Dependencies zwischen Calls
- Integrates mit ToolExecutionCache
"""

import asyncio
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


class ToolCallType(Enum):
    """Klassifikation von Tool-Calls"""
    READ_ONLY = "read_only"      # Kann parallel ausgeführt werden
    WRITE = "write"             # Muss sequentiell, invalidiert reads
    STATEFUL = "stateful"       # Hat Seiteneffekte auf State


# Tools die parallel ausgeführt werden können
PARALLELIZABLE_TOOLS = {
    # Filesystem reads
    "filesystem_read_file",
    "filesystem_list_directory",
    "filesystem_search_files",
    "filesystem_get_file_info",

    # Docker reads
    "docker_container_stats",
    "docker_container_logs",
    "docker_image_list",

    # Database reads
    "postgres_list_tables",
    "postgres_describe_table",
    "postgres_explain_query",

    # Git reads
    "git_status",
    "git_diff",
    "git_log",

    # Other reads
    "time_get_current_time",
    "memory_get_entity",
    "memory_search",
}

# Tools die NICHT parallel ausgeführt werden dürfen
SEQUENTIAL_ONLY_TOOLS = {
    # Alle writes
    "filesystem_write_file",
    "filesystem_create_directory",
    "filesystem_delete_file",
    "filesystem_move_file",

    # Docker mutations
    "docker_compose_up",
    "docker_compose_down",
    "docker_container_start",
    "docker_container_stop",

    # Database mutations
    "postgres_query",  # Könnte SELECT oder INSERT sein
    "prisma_generate",
    "prisma_migrate",

    # Git mutations
    "git_commit",
    "git_push",
    "git_pull",
}


@dataclass
class ToolCall:
    """Ein Tool-Call zur Ausführung"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str = ""
    depends_on: List[str] = field(default_factory=list)  # IDs von dependencies


@dataclass
class ToolResult:
    """Ergebnis eines Tool-Calls"""
    call_id: str
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    from_cache: bool = False
    duration_ms: int = 0


@dataclass
class ExecutionPlan:
    """Plan für parallele/sequentielle Ausführung"""
    batches: List[List[ToolCall]]  # Gruppen von parallel ausführbaren Calls
    total_calls: int
    parallelizable_count: int
    sequential_count: int

    def __repr__(self) -> str:
        return f"ExecutionPlan({self.total_calls} calls in {len(self.batches)} batches)"


class ParallelExecutor:
    """
    Führt Tool-Calls optimal parallel oder sequentiell aus.

    Analysiert eine Liste von Tool-Calls und gruppiert sie
    für optimale Ausführung.
    """

    def __init__(
        self,
        max_parallel: int = 5,
        cache = None,  # Optional: ToolExecutionCache
        timeout_per_call: int = 30
    ):
        """
        Args:
            max_parallel: Maximale parallele Ausführungen
            cache: Optional ToolExecutionCache für Caching
            timeout_per_call: Timeout pro Call in Sekunden
        """
        self.max_parallel = max_parallel
        self.cache = cache
        self.timeout_per_call = timeout_per_call

        self._stats = {
            "total_batches": 0,
            "total_calls": 0,
            "parallel_calls": 0,
            "sequential_calls": 0,
            "cache_hits": 0,
            "errors": 0
        }

        logger.info(f"ParallelExecutor initialized (max_parallel={max_parallel})")

    def classify_tool(self, tool_name: str) -> ToolCallType:
        """Klassifiziert einen Tool-Call"""
        if tool_name in PARALLELIZABLE_TOOLS:
            return ToolCallType.READ_ONLY
        elif tool_name in SEQUENTIAL_ONLY_TOOLS:
            return ToolCallType.WRITE
        else:
            # Default: Als stateful behandeln (sicher aber nicht optimal)
            return ToolCallType.STATEFUL

    def can_parallelize(self, tool_name: str) -> bool:
        """Prüft ob ein Tool parallelisiert werden kann"""
        return self.classify_tool(tool_name) == ToolCallType.READ_ONLY

    def create_execution_plan(self, calls: List[ToolCall]) -> ExecutionPlan:
        """
        Erstellt einen Ausführungsplan für eine Liste von Tool-Calls.

        Args:
            calls: Liste von ToolCalls

        Returns:
            ExecutionPlan mit gruppierten Batches
        """
        if not calls:
            return ExecutionPlan(batches=[], total_calls=0,
                                parallelizable_count=0, sequential_count=0)

        batches = []
        current_batch = []
        parallelizable_count = 0
        sequential_count = 0

        for call in calls:
            if self.can_parallelize(call.tool_name):
                # Kann zum aktuellen Batch hinzugefügt werden
                current_batch.append(call)
                parallelizable_count += 1

                # Batch-Size-Limit prüfen
                if len(current_batch) >= self.max_parallel:
                    batches.append(current_batch)
                    current_batch = []
            else:
                # Sequentieller Call - vorherigen Batch abschließen
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []

                # Einzelnen Call als eigenen Batch
                batches.append([call])
                sequential_count += 1

        # Letzten Batch hinzufügen
        if current_batch:
            batches.append(current_batch)

        return ExecutionPlan(
            batches=batches,
            total_calls=len(calls),
            parallelizable_count=parallelizable_count,
            sequential_count=sequential_count
        )

    async def execute_batch(
        self,
        batch: List[ToolCall],
        execute_fn: Callable
    ) -> List[ToolResult]:
        """
        Führt einen Batch von Tool-Calls parallel aus.

        Args:
            batch: Liste von ToolCalls im Batch
            execute_fn: Async Funktion zur Tool-Ausführung

        Returns:
            Liste von ToolResults
        """
        if len(batch) == 1:
            # Einzelner Call - direkt ausführen
            return [await self._execute_single(batch[0], execute_fn)]

        # Parallele Ausführung
        tasks = [
            self._execute_single(call, execute_fn)
            for call in batch
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Exceptions in ToolResults umwandeln
        final_results = []
        for call, result in zip(batch, results):
            if isinstance(result, Exception):
                final_results.append(ToolResult(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                    success=False,
                    error=str(result)
                ))
                self._stats["errors"] += 1
            else:
                final_results.append(result)

        return final_results

    async def _execute_single(
        self,
        call: ToolCall,
        execute_fn: Callable
    ) -> ToolResult:
        """Führt einen einzelnen Tool-Call aus"""
        start_time = time.time()

        try:
            # Cache prüfen
            if self.cache and self.cache.is_cacheable(call.tool_name):
                cached = self.cache.get(call.tool_name, call.arguments)
                if cached is not None:
                    self._stats["cache_hits"] += 1
                    return ToolResult(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        success=True,
                        result=cached,
                        from_cache=True,
                        duration_ms=int((time.time() - start_time) * 1000)
                    )

            # Tool ausführen mit Timeout
            result = await asyncio.wait_for(
                execute_fn(call.tool_name, call.arguments),
                timeout=self.timeout_per_call
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Cachen
            if self.cache:
                self.cache.set(call.tool_name, call.arguments, result)

            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=True,
                result=result,
                from_cache=False,
                duration_ms=duration_ms
            )

        except asyncio.TimeoutError:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                error=f"Timeout after {self.timeout_per_call}s",
                duration_ms=self.timeout_per_call * 1000
            )

        except Exception as e:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        execute_fn: Callable
    ) -> List[ToolResult]:
        """
        Führt einen kompletten Ausführungsplan aus.

        Args:
            plan: ExecutionPlan
            execute_fn: Async Funktion zur Tool-Ausführung

        Returns:
            Liste aller ToolResults in Reihenfolge
        """
        all_results = []

        self._stats["total_batches"] += len(plan.batches)
        self._stats["total_calls"] += plan.total_calls
        self._stats["parallel_calls"] += plan.parallelizable_count
        self._stats["sequential_calls"] += plan.sequential_count

        for i, batch in enumerate(plan.batches):
            logger.debug(f"Executing batch {i+1}/{len(plan.batches)} ({len(batch)} calls)")

            batch_results = await self.execute_batch(batch, execute_fn)
            all_results.extend(batch_results)

            # Cache invalidieren nach Write-Operations
            if self.cache:
                for call in batch:
                    if not self.can_parallelize(call.tool_name):
                        self.cache.invalidate_for_tool(call.tool_name, call.arguments)

        return all_results

    async def execute_calls(
        self,
        calls: List[ToolCall],
        execute_fn: Callable
    ) -> List[ToolResult]:
        """
        Convenience-Methode: Plant und führt Calls aus.

        Args:
            calls: Liste von ToolCalls
            execute_fn: Async Funktion zur Tool-Ausführung

        Returns:
            Liste aller ToolResults
        """
        plan = self.create_execution_plan(calls)
        logger.info(f"Execution plan: {plan}")
        return await self.execute_plan(plan, execute_fn)

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Ausführungsstatistiken zurück"""
        total = self._stats["total_calls"]
        parallel = self._stats["parallel_calls"]

        return {
            **self._stats,
            "parallel_rate": f"{(parallel / total * 100):.1f}%" if total > 0 else "0%",
            "cache_hit_rate": f"{(self._stats['cache_hits'] / total * 100):.1f}%" if total > 0 else "0%"
        }


# =============================================================================
# Utility Functions
# =============================================================================

def detect_parallel_opportunities(tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analysiert eine Liste von Tool-Calls auf Parallelisierungsmöglichkeiten.

    Args:
        tool_calls: Liste von Tool-Call Dicts

    Returns:
        Dict mit Analyse
    """
    parallelizable = []
    sequential = []

    for tc in tool_calls:
        tool_name = tc.get("tool") or tc.get("name", "")
        if tool_name in PARALLELIZABLE_TOOLS:
            parallelizable.append(tool_name)
        else:
            sequential.append(tool_name)

    return {
        "total": len(tool_calls),
        "parallelizable": len(parallelizable),
        "sequential": len(sequential),
        "parallelizable_tools": parallelizable,
        "sequential_tools": sequential,
        "potential_speedup": f"{len(parallelizable) / max(1, len(sequential) + 1):.1f}x"
    }


# =============================================================================
# Test
# =============================================================================

async def test_parallel_executor():
    """Test der ParallelExecutor Funktionalität"""
    print("=== Parallel Executor Test ===\n")

    executor = ParallelExecutor(max_parallel=3)

    # Mock execute function
    async def mock_execute(tool_name: str, args: Dict[str, Any]) -> str:
        await asyncio.sleep(0.1)  # Simuliere Latenz
        return f"Result for {tool_name}"

    # Test 1: Execution plan
    print("1. Execution plan creation:")
    calls = [
        ToolCall("filesystem_read_file", {"path": "/a.txt"}, "1"),
        ToolCall("filesystem_read_file", {"path": "/b.txt"}, "2"),
        ToolCall("filesystem_read_file", {"path": "/c.txt"}, "3"),
        ToolCall("filesystem_write_file", {"path": "/d.txt"}, "4"),  # Sequential
        ToolCall("filesystem_read_file", {"path": "/e.txt"}, "5"),
        ToolCall("filesystem_read_file", {"path": "/f.txt"}, "6"),
    ]

    plan = executor.create_execution_plan(calls)
    print(f"   {plan}")
    print(f"   Batches: {len(plan.batches)}")
    for i, batch in enumerate(plan.batches):
        tools = [c.tool_name for c in batch]
        print(f"   Batch {i+1}: {tools}")

    # Test 2: Execute plan
    print("\n2. Execute plan:")
    start = time.time()
    results = await executor.execute_plan(plan, mock_execute)
    duration = time.time() - start

    print(f"   Executed {len(results)} calls in {duration:.2f}s")
    for r in results:
        print(f"   - {r.tool_name}: success={r.success}, cached={r.from_cache}")

    # Test 3: Stats
    print("\n3. Stats:")
    print(f"   {executor.get_stats()}")

    # Test 4: Detect opportunities
    print("\n4. Detect parallel opportunities:")
    tool_calls = [
        {"tool": "filesystem_read_file"},
        {"tool": "filesystem_read_file"},
        {"tool": "filesystem_write_file"},
        {"tool": "docker_container_stats"},
    ]
    analysis = detect_parallel_opportunities(tool_calls)
    print(f"   {analysis}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_parallel_executor())
