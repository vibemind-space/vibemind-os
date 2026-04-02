"""Test deadlock detection for agent dependencies."""
import asyncio
import sys
import time
sys.path.insert(0, ".")

from src.services.deadlock_detector import (
    DeadlockDetector,
    DeadlockCycle,
    WaitEdge,
    WaitState,
)


async def test_register_and_resolve_wait():
    """Basic wait registration and resolution."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B", resource="build_output")

    graph = dd.get_wait_graph()
    assert "A" in graph
    assert graph["A"][0]["blocker"] == "B"

    resolved = dd.resolve_wait("A", "B")
    assert resolved is True

    graph2 = dd.get_wait_graph()
    assert "A" not in graph2  # No active waits
    print("OK: register and resolve wait")


async def test_no_deadlock():
    """Linear wait chain has no deadlock."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B", resource="output_B")
    dd.register_wait("B", "C", resource="output_C")

    cycles = dd.detect_deadlocks()
    assert len(cycles) == 0
    print("OK: no deadlock in linear chain")


async def test_simple_deadlock():
    """Two agents waiting on each other = deadlock."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B", resource="data_from_B")
    dd.register_wait("B", "A", resource="data_from_A")

    cycles = dd.detect_deadlocks()
    assert len(cycles) >= 1

    cycle = cycles[0]
    assert set(cycle.agents) == {"A", "B"}
    assert "->" in cycle.cycle_str
    print("OK: simple two-agent deadlock")


async def test_three_agent_cycle():
    """A -> B -> C -> A creates a 3-agent cycle."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B")
    dd.register_wait("B", "C")
    dd.register_wait("C", "A")

    cycles = dd.detect_deadlocks()
    assert len(cycles) >= 1

    # All three should be in the cycle
    all_agents = set()
    for c in cycles:
        all_agents.update(c.agents)
    assert {"A", "B", "C"}.issubset(all_agents)
    print("OK: three-agent cycle")


async def test_resolve_deadlock_break_longest():
    """Deadlock resolved by breaking longest wait."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B")
    # Make A's wait older
    dd._waits["A"][0].registered_at = time.time() - 100

    dd.register_wait("B", "A")

    cycles = dd.detect_deadlocks()
    assert len(cycles) >= 1

    dd.resolve_deadlock(cycles[0], strategy="break_longest_wait")
    assert cycles[0].resolved is True
    assert "Broke wait" in cycles[0].resolution
    print("OK: resolve deadlock break longest")


async def test_resolve_deadlock_break_all():
    """Deadlock resolved by breaking all edges."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B")
    dd.register_wait("B", "A")

    cycles = dd.detect_deadlocks()
    dd.resolve_deadlock(cycles[0], strategy="break_all")

    assert cycles[0].resolved is True
    assert "all" in cycles[0].resolution.lower()

    # All edges should be broken
    for edge in cycles[0].edges:
        assert edge.state == WaitState.BROKEN
    print("OK: resolve deadlock break all")


async def test_duplicate_wait_ignored():
    """Duplicate active wait registration is ignored."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B")
    dd.register_wait("A", "B")  # Duplicate

    graph = dd.get_wait_graph()
    assert len(graph["A"]) == 1
    print("OK: duplicate wait ignored")


async def test_wait_timeout():
    """Timed-out waits are detected."""
    dd = DeadlockDetector(default_timeout=0.1)
    dd.register_wait("A", "B")

    # Wait for timeout
    await asyncio.sleep(0.2)

    dd._check_timeouts()

    edge = dd._waits["A"][0]
    assert edge.state == WaitState.TIMED_OUT

    # No longer in active graph
    graph = dd.get_wait_graph()
    assert "A" not in graph
    print("OK: wait timeout")


async def test_agent_waits_query():
    """get_agent_waits shows both directions."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B", resource="data")
    dd.register_wait("C", "B", resource="config")

    waits = dd.get_agent_waits("B")
    assert waits["agent"] == "B"
    assert len(waits["waiting_for"]) == 0  # B isn't waiting for anyone
    assert len(waits["waited_by"]) == 2  # A and C are waiting for B
    print("OK: agent waits query")


async def test_deadlock_history():
    """Deadlock history is maintained."""
    dd = DeadlockDetector()

    # Create first deadlock
    dd.register_wait("A", "B")
    dd.register_wait("B", "A")
    dd.detect_deadlocks()

    # Resolve and create another
    dd.resolve_wait("A", "B")
    dd.resolve_wait("B", "A")
    dd.register_wait("X", "Y")
    dd.register_wait("Y", "X")
    dd.detect_deadlocks()

    history = dd.get_deadlock_history()
    assert len(history) >= 2
    print("OK: deadlock history")


async def test_stats():
    """Stats report correctly."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B")
    dd.register_wait("B", "C")
    dd.register_wait("C", "A")

    dd.detect_deadlocks()

    stats = dd.get_stats()
    assert stats["total_agents"] == 3
    assert stats["total_waits_registered"] == 3
    assert stats["active_waits"] == 3
    assert stats["total_deadlocks_detected"] >= 1
    print("OK: stats")


async def test_deadlock_cycle_to_dict():
    """DeadlockCycle serialization."""
    edge = WaitEdge(waiter="A", blocker="B", resource="data")
    cycle = DeadlockCycle(agents=["A", "B"], edges=[edge])

    d = cycle.to_dict()
    assert d["agents"] == ["A", "B"]
    assert d["cycle"] == "A -> B -> A"
    assert len(d["edges"]) == 1
    assert d["edges"][0]["waiter"] == "A"
    assert d["resolved"] is False
    print("OK: cycle to_dict")


async def test_wait_edge_properties():
    """WaitEdge computed properties."""
    edge = WaitEdge(
        waiter="A",
        blocker="B",
        registered_at=time.time() - 10.0,
        timeout_seconds=5.0,
    )

    assert edge.is_active is True
    assert edge.elapsed_seconds >= 9.5
    assert edge.is_timed_out is True
    print("OK: wait edge properties")


async def test_clear():
    """Clear removes all tracking data."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B")
    dd.register_wait("B", "A")
    dd.detect_deadlocks()

    dd.clear()

    assert dd.get_wait_graph() == {}
    assert dd.get_stats()["total_agents"] == 0
    assert dd.get_deadlock_history() == []
    print("OK: clear")


async def test_on_deadlock_callback():
    """Deadlock callbacks fire during periodic check."""
    dd = DeadlockDetector(check_interval=0.1, auto_resolve=False)
    detected_cycles = []

    async def on_deadlock(cycle):
        detected_cycles.append(cycle)

    dd.on_deadlock(on_deadlock)

    dd.register_wait("A", "B")
    dd.register_wait("B", "A")

    dd.start()
    await asyncio.sleep(0.3)
    dd.stop()

    assert len(detected_cycles) >= 1
    print("OK: deadlock callback")


async def test_mixed_active_resolved():
    """Only active waits contribute to deadlock detection."""
    dd = DeadlockDetector()
    dd.register_wait("A", "B")
    dd.register_wait("B", "A")

    # Resolve one edge
    dd.resolve_wait("A", "B")

    cycles = dd.detect_deadlocks()
    # No cycle since A->B is resolved
    assert len(cycles) == 0
    print("OK: mixed active/resolved waits")


async def test_no_self_deadlock():
    """Agent waiting on itself doesn't cause issues."""
    dd = DeadlockDetector()
    dd.register_wait("A", "A")

    cycles = dd.detect_deadlocks()
    # Self-loop is technically a cycle
    assert len(cycles) >= 1
    assert "A" in cycles[0].agents
    print("OK: self-loop detected")


async def main():
    print("=== Deadlock Detector Tests ===\n")
    await test_register_and_resolve_wait()
    await test_no_deadlock()
    await test_simple_deadlock()
    await test_three_agent_cycle()
    await test_resolve_deadlock_break_longest()
    await test_resolve_deadlock_break_all()
    await test_duplicate_wait_ignored()
    await test_wait_timeout()
    await test_agent_waits_query()
    await test_deadlock_history()
    await test_stats()
    await test_deadlock_cycle_to_dict()
    await test_wait_edge_properties()
    await test_clear()
    await test_on_deadlock_callback()
    await test_mixed_active_resolved()
    await test_no_self_deadlock()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
