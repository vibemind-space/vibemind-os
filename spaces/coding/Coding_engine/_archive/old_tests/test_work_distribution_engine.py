"""Test work distribution engine."""
import sys
sys.path.insert(0, ".")

from src.services.work_distribution_engine import WorkDistributionEngine


def test_register_worker():
    """Register and unregister workers."""
    eng = WorkDistributionEngine()
    assert eng.register_worker("Builder", skills={"python", "build"},
                                capacity=5.0) is True
    assert eng.register_worker("Builder") is False

    w = eng.get_worker("Builder")
    assert w is not None
    assert w["capacity"] == 5.0
    assert "python" in w["skills"]

    assert eng.unregister_worker("Builder") is True
    assert eng.unregister_worker("Builder") is False
    print("OK: register worker")


def test_worker_status():
    """Set worker status."""
    eng = WorkDistributionEngine()
    eng.register_worker("A")

    assert eng.set_worker_status("A", "offline") is True
    assert eng.get_worker("A")["status"] == "offline"
    assert eng.set_worker_status("A", "available") is True
    assert eng.set_worker_status("A", "invalid") is False
    assert eng.set_worker_status("fake", "available") is False
    print("OK: worker status")


def test_list_workers():
    """List workers with filters."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", skills={"python"}, capacity=3.0)
    eng.register_worker("B", skills={"java"}, capacity=5.0)
    eng.set_worker_status("B", "offline")

    all_w = eng.list_workers()
    assert len(all_w) == 2

    avail = eng.list_workers(status="available")
    assert len(avail) == 1

    java = eng.list_workers(skill="java")
    assert len(java) == 1
    print("OK: list workers")


def test_create_item():
    """Create work items."""
    eng = WorkDistributionEngine()
    wid = eng.create_item("Build module", priority=80,
                           required_skills={"python"},
                           estimated_effort=2.0, category="build")
    assert wid.startswith("work-")

    item = eng.get_item(wid)
    assert item is not None
    assert item["name"] == "Build module"
    assert item["priority"] == 80
    assert item["status"] == "pending"

    assert eng.get_item("fake") is None
    print("OK: create item")


def test_distribute_simple():
    """Basic distribution."""
    eng = WorkDistributionEngine(strategy="least_loaded")
    eng.register_worker("A", capacity=5.0)
    wid = eng.create_item("Task", estimated_effort=1.0)

    assignments = eng.distribute()
    assert len(assignments) == 1
    assert assignments[0]["work_id"] == wid
    assert assignments[0]["worker"] == "A"

    item = eng.get_item(wid)
    assert item["status"] == "assigned"
    assert item["assigned_to"] == "A"
    print("OK: distribute simple")


def test_distribute_skill_match():
    """Skill-based distribution."""
    eng = WorkDistributionEngine(strategy="skill_match")
    eng.register_worker("Python", skills={"python"}, capacity=5.0)
    eng.register_worker("Java", skills={"java"}, capacity=5.0)

    wid = eng.create_item("Python task", required_skills={"python"})
    assignments = eng.distribute()

    assert len(assignments) == 1
    assert assignments[0]["worker"] == "Python"
    print("OK: distribute skill match")


def test_distribute_capacity():
    """Respect capacity limits."""
    eng = WorkDistributionEngine(strategy="least_loaded")
    eng.register_worker("Small", capacity=1.0)

    eng.create_item("Big task", estimated_effort=2.0)
    assignments = eng.distribute()
    assert len(assignments) == 0  # No worker with enough capacity
    print("OK: distribute capacity")


def test_distribute_priority():
    """Higher priority items assigned first."""
    eng = WorkDistributionEngine(strategy="least_loaded")
    eng.register_worker("A", capacity=10.0)

    eng.create_item("Low", priority=10, estimated_effort=1.0)
    eng.create_item("High", priority=90, estimated_effort=1.0)

    assignments = eng.distribute()
    assert len(assignments) == 2
    assert assignments[0]["priority"] == 90  # High first
    print("OK: distribute priority")


def test_distribute_dependencies():
    """Items with unmet deps are skipped."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", capacity=10.0)

    dep_id = eng.create_item("Dependency")
    main_id = eng.create_item("Main", dependencies={dep_id})

    # Main can't be assigned yet
    assignments = eng.distribute()
    assigned_ids = {a["work_id"] for a in assignments}
    assert dep_id in assigned_ids
    assert main_id not in assigned_ids

    # Complete dependency
    eng.complete_work(dep_id)
    assignments2 = eng.distribute()
    assert len(assignments2) == 1
    assert assignments2[0]["work_id"] == main_id
    print("OK: distribute dependencies")


def test_work_lifecycle():
    """Complete work lifecycle."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", capacity=5.0)
    wid = eng.create_item("Task", estimated_effort=1.0)

    eng.distribute()
    assert eng.start_work(wid) is True
    assert eng.get_item(wid)["status"] == "in_progress"

    assert eng.complete_work(wid) is True
    assert eng.get_item(wid)["status"] == "completed"

    w = eng.get_worker("A")
    assert w["current_load"] == 0.0
    assert w["total_completed"] == 1
    print("OK: work lifecycle")


def test_fail_and_retry():
    """Fail and retry work."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", capacity=5.0)
    wid = eng.create_item("Task", estimated_effort=1.0)

    eng.distribute()
    assert eng.fail_work(wid) is True
    assert eng.get_item(wid)["status"] == "failed"

    assert eng.retry_work(wid) is True
    assert eng.get_item(wid)["status"] == "pending"

    assert eng.retry_work("fake") is False
    print("OK: fail and retry")


def test_cancel_item():
    """Cancel a pending item."""
    eng = WorkDistributionEngine()
    wid = eng.create_item("Task")

    assert eng.cancel_item(wid) is True
    assert eng.get_item(wid)["status"] == "failed"
    assert eng.cancel_item(wid) is False  # Not pending anymore
    print("OK: cancel item")


def test_rebalance():
    """Rebalance from offline workers."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", capacity=5.0)
    wid = eng.create_item("Task", estimated_effort=1.0)

    eng.distribute()
    assert eng.get_item(wid)["status"] == "assigned"

    # Worker goes offline
    eng.set_worker_status("A", "offline")
    moved = eng.rebalance()
    assert moved == 1
    assert eng.get_item(wid)["status"] == "pending"
    print("OK: rebalance")


def test_list_items():
    """List items with filters."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", capacity=10.0)
    eng.create_item("A", category="build", priority=80)
    eng.create_item("B", category="test", priority=60)

    eng.distribute()

    all_items = eng.list_items()
    assert len(all_items) == 2

    by_status = eng.list_items(status="assigned")
    assert len(by_status) == 2

    by_cat = eng.list_items(category="build")
    assert len(by_cat) == 1

    by_worker = eng.list_items(assigned_to="A")
    assert len(by_worker) == 2

    limited = eng.list_items(limit=1)
    assert len(limited) == 1
    print("OK: list items")


def test_worker_load():
    """Get worker load summary."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", capacity=5.0)
    eng.create_item("Task", estimated_effort=2.0)
    eng.distribute()

    load = eng.get_worker_load()
    assert len(load) == 1
    assert load[0]["current_load"] == 2.0
    assert load[0]["utilization"] == 40.0
    assert load[0]["assigned_items"] == 1
    print("OK: worker load")


def test_pending_count():
    """Count pending items."""
    eng = WorkDistributionEngine()
    eng.create_item("A", category="build")
    eng.create_item("B", category="test")
    eng.create_item("C", category="build")

    assert eng.pending_count() == 3
    assert eng.pending_count(category="build") == 2
    print("OK: pending count")


def test_stats():
    """Stats are accurate."""
    eng = WorkDistributionEngine()
    eng.register_worker("A", capacity=10.0)
    w1 = eng.create_item("Task1")
    w2 = eng.create_item("Task2")
    eng.distribute()
    eng.complete_work(w1)
    eng.fail_work(w2)

    stats = eng.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_assigned"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_workers"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    eng = WorkDistributionEngine()
    eng.register_worker("A")
    eng.create_item("Task")

    eng.reset()
    assert eng.list_workers() == []
    assert eng.list_items() == []
    stats = eng.get_stats()
    assert stats["total_items"] == 0
    print("OK: reset")


def main():
    print("=== Work Distribution Engine Tests ===\n")
    test_register_worker()
    test_worker_status()
    test_list_workers()
    test_create_item()
    test_distribute_simple()
    test_distribute_skill_match()
    test_distribute_capacity()
    test_distribute_priority()
    test_distribute_dependencies()
    test_work_lifecycle()
    test_fail_and_retry()
    test_cancel_item()
    test_rebalance()
    test_list_items()
    test_worker_load()
    test_pending_count()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
