"""Tests for AgentTaskDependency service."""

import sys
import os
import types
import traceback
import importlib.util

# Provide a minimal structlog stub to avoid circular import issues in this project.
if "structlog" not in sys.modules:
    _stub = types.ModuleType("structlog")

    class _StubLogger:
        def exception(self, *a, **kw): pass
        def info(self, *a, **kw): pass
        def debug(self, *a, **kw): pass
        def warning(self, *a, **kw): pass
        def error(self, *a, **kw): pass

    _stub.get_logger = lambda *a, **kw: _StubLogger()
    sys.modules["structlog"] = _stub

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src",
                    "services", "agent_task_dependency.py")
_spec = importlib.util.spec_from_file_location("agent_task_dependency", _src)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["agent_task_dependency"] = _mod
_spec.loader.exec_module(_mod)
AgentTaskDependency = _mod.AgentTaskDependency
AgentTaskDependencyState = _mod.AgentTaskDependencyState


def test_register_task():
    dep = AgentTaskDependency()
    tid = dep.register_task("agent-1", "build")
    assert tid.startswith("atd-")
    assert len(tid) == 4 + 16  # prefix + 16 hex chars
    task = dep.get_task(tid)
    assert task is not None
    assert task["agent_id"] == "agent-1"
    assert task["task_name"] == "build"
    assert task["status"] == "pending"
    assert task["depends_on"] == []


def test_register_task_with_dependencies():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "test", depends_on=[t1])
    task = dep.get_task(t2)
    assert task["depends_on"] == [t1]


def test_add_dependency():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "test")
    assert dep.add_dependency(t2, t1) is True
    task = dep.get_task(t2)
    assert t1 in task["depends_on"]


def test_add_dependency_not_found():
    dep = AgentTaskDependency()
    assert dep.add_dependency("nonexistent", "other") is False


def test_remove_dependency():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "test", depends_on=[t1])
    assert dep.remove_dependency(t2, t1) is True
    task = dep.get_task(t2)
    assert t1 not in task["depends_on"]


def test_remove_dependency_not_found():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    # Remove dep that doesn't exist on the task
    assert dep.remove_dependency(t1, "nonexistent") is False
    # Remove from nonexistent task
    assert dep.remove_dependency("nonexistent", t1) is False


def test_get_task_none():
    dep = AgentTaskDependency()
    assert dep.get_task("nonexistent") is None


def test_get_tasks():
    dep = AgentTaskDependency()
    dep.register_task("agent-1", "build")
    dep.register_task("agent-1", "test")
    dep.register_task("agent-2", "deploy")
    tasks = dep.get_tasks("agent-1")
    assert len(tasks) == 2
    assert all(t["agent_id"] == "agent-1" for t in tasks)


def test_get_ready_tasks():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "test", depends_on=[t1])
    t3 = dep.register_task("agent-1", "lint")  # no deps

    ready = dep.get_ready_tasks("agent-1")
    ready_ids = [r["task_id"] for r in ready]
    assert t1 in ready_ids
    assert t3 in ready_ids
    assert t2 not in ready_ids

    dep.complete_task(t1)
    ready = dep.get_ready_tasks("agent-1")
    ready_ids = [r["task_id"] for r in ready]
    assert t2 in ready_ids
    assert t3 in ready_ids


def test_complete_task():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    assert dep.complete_task(t1) is True
    task = dep.get_task(t1)
    assert task["status"] == "completed"


def test_complete_task_not_found():
    dep = AgentTaskDependency()
    assert dep.complete_task("nonexistent") is False


def test_get_dependents():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "test", depends_on=[t1])
    t3 = dep.register_task("agent-1", "deploy", depends_on=[t1])
    dependents = dep.get_dependents(t1)
    dep_ids = [d["task_id"] for d in dependents]
    assert t2 in dep_ids
    assert t3 in dep_ids
    assert len(dep_ids) == 2


def test_get_dependencies():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "lint")
    t3 = dep.register_task("agent-1", "test", depends_on=[t1, t2])
    dependencies = dep.get_dependencies(t3)
    dep_ids = [d["task_id"] for d in dependencies]
    assert t1 in dep_ids
    assert t2 in dep_ids
    assert len(dep_ids) == 2


def test_get_dependencies_not_found():
    dep = AgentTaskDependency()
    assert dep.get_dependencies("nonexistent") == []


def test_has_circular_dependency():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "a")
    t2 = dep.register_task("agent-1", "b", depends_on=[t1])
    t3 = dep.register_task("agent-1", "c", depends_on=[t2])
    # No circular dep yet
    assert dep.has_circular_dependency(t3) is False

    # Create a cycle: t1 -> t3 (t3 -> t2 -> t1 -> t3)
    dep.add_dependency(t1, t3)
    assert dep.has_circular_dependency(t1) is True
    assert dep.has_circular_dependency(t2) is True
    assert dep.has_circular_dependency(t3) is True


def test_get_task_count():
    dep = AgentTaskDependency()
    dep.register_task("agent-1", "build")
    dep.register_task("agent-1", "test")
    dep.register_task("agent-2", "deploy")
    assert dep.get_task_count() == 3
    assert dep.get_task_count("agent-1") == 2
    assert dep.get_task_count("agent-2") == 1
    assert dep.get_task_count("agent-3") == 0


def test_get_stats():
    dep = AgentTaskDependency()
    t1 = dep.register_task("agent-1", "build")
    t2 = dep.register_task("agent-1", "test", depends_on=[t1])
    t3 = dep.register_task("agent-1", "deploy", depends_on=[t1, t2])
    dep.complete_task(t1)
    stats = dep.get_stats()
    assert stats["total_tasks"] == 3
    assert stats["completed_tasks"] == 1
    assert stats["pending_tasks"] == 2
    assert stats["total_dependencies"] == 3


def test_reset():
    dep = AgentTaskDependency()
    dep.register_task("agent-1", "build")
    dep.register_task("agent-1", "test")
    dep.reset()
    assert dep.get_task_count() == 0
    assert dep.get_stats()["total_tasks"] == 0


def test_on_change_and_callbacks():
    events = []

    def on_change(event, data):
        events.append(("on_change", event, data))

    def cb1(event, data):
        events.append(("cb1", event, data))

    dep = AgentTaskDependency()
    dep.on_change = on_change
    assert dep.on_change is on_change
    dep._callbacks["cb1"] = cb1

    dep.register_task("agent-1", "build")
    assert len(events) >= 2  # on_change + cb1
    assert events[0][0] == "on_change"
    assert events[1][0] == "cb1"


def test_remove_callback():
    dep = AgentTaskDependency()
    dep._callbacks["mycb"] = lambda e, d: None
    assert dep.remove_callback("mycb") is True
    assert dep.remove_callback("mycb") is False
    assert dep.remove_callback("nonexistent") is False


def test_prune():
    dep = AgentTaskDependency()
    dep.MAX_ENTRIES = 5
    for i in range(10):
        dep.register_task("agent-1", f"task-{i}")
    assert dep.get_task_count() <= 5


def test_generate_id_uniqueness():
    dep = AgentTaskDependency()
    ids = set()
    for i in range(100):
        tid = dep._generate_id(f"data-{i}")
        ids.add(tid)
    assert len(ids) == 100


def test_callback_exception_handling():
    """Callbacks that raise should not break the service."""
    dep = AgentTaskDependency()

    def bad_on_change(event, data):
        raise ValueError("boom")

    def bad_cb(event, data):
        raise RuntimeError("kaboom")

    dep.on_change = bad_on_change
    dep._callbacks["bad"] = bad_cb

    # Should not raise
    tid = dep.register_task("agent-1", "build")
    assert tid.startswith("atd-")


# -------------------------------------------------------------------
# Runner
# -------------------------------------------------------------------

def _collect_tests():
    return [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]


if __name__ == "__main__":
    tests = _collect_tests()
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception:
            failed += 1
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
            print()
    total = passed + failed
    print(f"{passed}/{total} tests passed")
    if failed:
        sys.exit(1)
