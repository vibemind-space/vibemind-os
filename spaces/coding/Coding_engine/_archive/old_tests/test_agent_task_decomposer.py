"""Test agent task decomposer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_task_decomposer import AgentTaskDecomposer


def test_create_task():
    td = AgentTaskDecomposer()
    tid = td.create_task("build_auth", description="Build auth module", complexity=8, estimated_effort=10.0)
    assert tid.startswith("tsk-")
    t = td.get_task("build_auth")
    assert t["name"] == "build_auth"
    assert t["complexity"] == 8
    assert t["estimated_effort"] == 10.0
    assert t["is_leaf"] is True
    assert td.create_task("build_auth") == ""  # dup
    print("OK: create task")


def test_decompose():
    td = AgentTaskDecomposer()
    td.create_task("build_auth", complexity=8, estimated_effort=10.0)
    subtask_ids = td.decompose("build_auth", [
        {"name": "login_form", "description": "Login UI", "complexity": 3, "estimated_effort": 3.0},
        {"name": "jwt_handler", "description": "JWT logic", "complexity": 5, "estimated_effort": 5.0},
    ])
    assert len(subtask_ids) == 2
    assert all(sid.startswith("tsk-") for sid in subtask_ids)
    parent = td.get_task("build_auth")
    assert parent["subtask_count"] == 2
    assert parent["is_leaf"] is False
    child = td.get_task("login_form")
    assert child is not None
    assert child["is_leaf"] is True
    print("OK: decompose")


def test_decomposition_tree():
    td = AgentTaskDecomposer()
    td.create_task("root")
    td.decompose("root", [
        {"name": "a", "description": "", "complexity": 3, "estimated_effort": 2.0},
        {"name": "b", "description": "", "complexity": 4, "estimated_effort": 3.0},
    ])
    tree = td.get_decomposition_tree("root")
    assert tree["name"] == "root"
    assert len(tree["children"]) == 2
    print("OK: decomposition tree")


def test_parallelizable():
    td = AgentTaskDecomposer()
    td.create_task("task1")
    assert td.mark_parallelizable("task1", parallel=True) is True
    t = td.get_task("task1")
    assert t["parallelizable"] is True
    print("OK: parallelizable")


def test_get_leaves():
    td = AgentTaskDecomposer()
    td.create_task("root")
    td.decompose("root", [
        {"name": "a", "description": "", "complexity": 1, "estimated_effort": 1.0},
        {"name": "b", "description": "", "complexity": 1, "estimated_effort": 2.0},
    ])
    leaves = td.get_leaves("root")
    assert len(leaves) == 2
    leaf_names = [l["name"] for l in leaves]
    assert "a" in leaf_names
    assert "b" in leaf_names
    print("OK: get leaves")


def test_complete_task():
    td = AgentTaskDecomposer()
    td.create_task("task1")
    assert td.complete_task("task1") is True
    assert td.get_task("task1")["status"] == "completed"
    assert td.complete_task("task1") is False  # already done
    print("OK: complete task")


def test_completion_pct():
    td = AgentTaskDecomposer()
    td.create_task("root")
    td.decompose("root", [
        {"name": "a", "description": "", "complexity": 1, "estimated_effort": 1.0},
        {"name": "b", "description": "", "complexity": 1, "estimated_effort": 1.0},
    ])
    td.complete_task("a")
    pct = td.get_completion_pct("root")
    assert pct == 50.0
    print("OK: completion pct")


def test_list_tasks():
    td = AgentTaskDecomposer()
    td.create_task("t1", tags=["core"])
    td.create_task("t2")
    assert len(td.list_tasks()) == 2
    assert len(td.list_tasks(tag="core")) == 1
    print("OK: list tasks")


def test_remove_task():
    td = AgentTaskDecomposer()
    td.create_task("t1")
    assert td.remove_task("t1") is True
    assert td.remove_task("t1") is False
    print("OK: remove task")


def test_history():
    td = AgentTaskDecomposer()
    td.create_task("t1")
    hist = td.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    td = AgentTaskDecomposer()
    fired = []
    td.on_change("mon", lambda a, d: fired.append(a))
    td.create_task("t1")
    assert len(fired) >= 1
    assert td.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    td = AgentTaskDecomposer()
    td.create_task("t1")
    stats = td.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    td = AgentTaskDecomposer()
    td.create_task("t1")
    td.reset()
    assert td.list_tasks() == []
    print("OK: reset")


def main():
    print("=== Agent Task Decomposer Tests ===\n")
    test_create_task()
    test_decompose()
    test_decomposition_tree()
    test_parallelizable()
    test_get_leaves()
    test_complete_task()
    test_completion_pct()
    test_list_tasks()
    test_remove_task()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
