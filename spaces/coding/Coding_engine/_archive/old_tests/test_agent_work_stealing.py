"""Test agent work stealing."""
import sys
sys.path.insert(0, ".")

from src.services.agent_work_stealing import AgentWorkStealing


def test_create_queue():
    """Create and remove queues."""
    ws = AgentWorkStealing()
    assert ws.create_queue("A", max_size=50) is True
    assert ws.create_queue("A") is False  # Duplicate

    q = ws.get_queue("A")
    assert q is not None
    assert q["max_size"] == 50
    assert q["size"] == 0

    assert ws.remove_queue("A") is True
    assert ws.remove_queue("A") is False
    print("OK: create queue")


def test_add_item():
    """Add items to queue."""
    ws = AgentWorkStealing()
    ws.create_queue("A", max_size=10)

    iid = ws.add_item("A", "task-1", priority=80)
    assert iid.startswith("wi-")

    item = ws.get_item(iid)
    assert item is not None
    assert item["name"] == "task-1"
    assert item["owner"] == "A"
    assert item["priority"] == 80

    assert ws.get_queue("A")["size"] == 1
    assert ws.add_item("fake", "x") == ""
    print("OK: add item")


def test_queue_full():
    """Can't add to full queue."""
    ws = AgentWorkStealing()
    ws.create_queue("A", max_size=2)

    ws.add_item("A", "t1")
    ws.add_item("A", "t2")
    assert ws.add_item("A", "t3") == ""
    print("OK: queue full")


def test_complete_item():
    """Complete work item."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    iid = ws.add_item("A", "task")

    assert ws.complete_item(iid) is True
    assert ws.get_item(iid)["status"] == "completed"
    assert ws.get_queue("A")["size"] == 0

    assert ws.complete_item(iid) is False
    print("OK: complete item")


def test_start_item():
    """Start working on item."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    iid = ws.add_item("A", "task")

    assert ws.start_item(iid) is True
    assert ws.get_item(iid)["status"] == "running"
    assert ws.start_item(iid) is False
    print("OK: start item")


def test_steal():
    """Steal items between queues."""
    ws = AgentWorkStealing()
    ws.create_queue("A", max_size=10)
    ws.create_queue("B", max_size=10)

    # Add items to A
    i1 = ws.add_item("A", "low", priority=20)
    i2 = ws.add_item("A", "high", priority=90)
    i3 = ws.add_item("A", "med", priority=50)

    # B steals 1 item from A (lowest priority first)
    stolen = ws.steal("B", "A", count=1)
    assert len(stolen) == 1
    assert stolen[0] == i1  # Lowest priority stolen

    assert ws.get_item(i1)["owner"] == "B"
    assert ws.get_item(i1)["stolen_from"] == "A"
    assert ws.get_queue("A")["size"] == 2
    assert ws.get_queue("B")["size"] == 1
    print("OK: steal")


def test_steal_respects_stealable():
    """Can't steal from non-stealable queues."""
    ws = AgentWorkStealing()
    ws.create_queue("A", stealable=False)
    ws.create_queue("B")
    ws.add_item("A", "task")

    stolen = ws.steal("B", "A")
    assert len(stolen) == 0
    print("OK: steal respects stealable")


def test_steal_non_stealable_items():
    """Non-stealable items are skipped."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.create_queue("B")

    ws.add_item("A", "locked", stealable=False)
    ws.add_item("A", "open", stealable=True)

    stolen = ws.steal("B", "A", count=2)
    assert len(stolen) == 1  # Only the stealable one
    print("OK: steal non stealable items")


def test_steal_running_items_skipped():
    """Running items can't be stolen."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.create_queue("B")

    iid = ws.add_item("A", "task")
    ws.start_item(iid)

    stolen = ws.steal("B", "A")
    assert len(stolen) == 0
    print("OK: steal running items skipped")


def test_cant_steal_from_self():
    """Can't steal from own queue."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.add_item("A", "task")

    stolen = ws.steal("A", "A")
    assert len(stolen) == 0
    print("OK: cant steal from self")


def test_auto_steal():
    """Auto-steal from most loaded queue."""
    ws = AgentWorkStealing(steal_threshold=0.5)
    ws.create_queue("A", max_size=10)
    ws.create_queue("B", max_size=10)

    # Load A above threshold
    for i in range(8):
        ws.add_item("A", f"task-{i}")

    stolen = ws.auto_steal("B")
    assert len(stolen) > 0
    assert ws.get_queue("B")["size"] > 0
    print("OK: auto steal")


def test_auto_steal_no_overloaded():
    """Auto-steal does nothing when no queues overloaded."""
    ws = AgentWorkStealing(steal_threshold=0.8)
    ws.create_queue("A", max_size=10)
    ws.create_queue("B", max_size=10)

    ws.add_item("A", "task-1")

    stolen = ws.auto_steal("B")
    assert len(stolen) == 0
    print("OK: auto steal no overloaded")


def test_balance_all():
    """Balance all queues."""
    ws = AgentWorkStealing()
    ws.create_queue("A", max_size=20)
    ws.create_queue("B", max_size=20)
    ws.create_queue("C", max_size=20)

    # Load A heavily
    for i in range(10):
        ws.add_item("A", f"task-{i}")

    moved = ws.balance_all()
    assert moved > 0

    # Should be more balanced now
    a_size = ws.get_queue("A")["size"]
    b_size = ws.get_queue("B")["size"]
    c_size = ws.get_queue("C")["size"]
    assert a_size <= 10  # A should have fewer
    assert b_size + c_size > 0
    print("OK: balance all")


def test_set_stealable():
    """Set queue stealable flag."""
    ws = AgentWorkStealing()
    ws.create_queue("A")

    assert ws.set_stealable("A", False) is True
    assert ws.get_queue("A")["stealable"] is False
    assert ws.set_stealable("fake", True) is False
    print("OK: set stealable")


def test_load_distribution():
    """Get load distribution."""
    ws = AgentWorkStealing()
    ws.create_queue("A", max_size=10)
    ws.create_queue("B", max_size=10)
    ws.add_item("A", "t1")
    ws.add_item("A", "t2")

    dist = ws.get_load_distribution()
    assert dist["A"]["size"] == 2
    assert dist["A"]["fullness"] == 20.0
    assert dist["B"]["size"] == 0
    print("OK: load distribution")


def test_imbalance():
    """Get imbalance ratio."""
    ws = AgentWorkStealing()
    ws.create_queue("A", max_size=10)
    ws.create_queue("B", max_size=10)

    assert ws.get_imbalance() == 0.0  # Both empty

    for i in range(6):
        ws.add_item("A", f"t{i}")

    imb = ws.get_imbalance()
    assert imb > 0  # A has 6, B has 0
    print("OK: imbalance")


def test_overloaded():
    """Get overloaded queues."""
    ws = AgentWorkStealing(steal_threshold=0.5)
    ws.create_queue("A", max_size=10)
    ws.create_queue("B", max_size=10)

    for i in range(6):
        ws.add_item("A", f"t{i}")

    overloaded = ws.get_overloaded()
    assert "A" in overloaded
    assert "B" not in overloaded
    print("OK: overloaded")


def test_idle():
    """Get idle queues."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.create_queue("B")
    ws.add_item("A", "task")

    idle = ws.get_idle()
    assert "B" in idle
    assert "A" not in idle
    print("OK: idle")


def test_cant_remove_nonempty():
    """Can't remove non-empty queue."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.add_item("A", "task")

    assert ws.remove_queue("A") is False
    print("OK: cant remove nonempty")


def test_callbacks():
    """Steal callbacks fire."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.create_queue("B")
    ws.add_item("A", "task")

    fired = []
    assert ws.on_steal("mon", lambda act, iid, v, t: fired.append((v, t))) is True
    assert ws.on_steal("mon", lambda a, i, v, t: None) is False

    ws.steal("B", "A")
    assert len(fired) == 1
    assert fired[0] == ("A", "B")

    assert ws.remove_callback("mon") is True
    assert ws.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.create_queue("B")
    iid = ws.add_item("A", "task")
    ws.steal("B", "A")
    ws.complete_item(iid)

    stats = ws.get_stats()
    assert stats["total_queues"] == 2
    assert stats["total_items_added"] == 1
    assert stats["total_steals"] == 1
    assert stats["total_completed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ws = AgentWorkStealing()
    ws.create_queue("A")
    ws.add_item("A", "task")

    ws.reset()
    assert ws.list_queues() == []
    stats = ws.get_stats()
    assert stats["total_queues"] == 0
    print("OK: reset")


def main():
    print("=== Agent Work Stealing Tests ===\n")
    test_create_queue()
    test_add_item()
    test_queue_full()
    test_complete_item()
    test_start_item()
    test_steal()
    test_steal_respects_stealable()
    test_steal_non_stealable_items()
    test_steal_running_items_skipped()
    test_cant_steal_from_self()
    test_auto_steal()
    test_auto_steal_no_overloaded()
    test_balance_all()
    test_set_stealable()
    test_load_distribution()
    test_imbalance()
    test_overloaded()
    test_idle()
    test_cant_remove_nonempty()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
