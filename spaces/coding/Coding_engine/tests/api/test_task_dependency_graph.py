"""
Tests for Task Dependency Graph logic.

Tests the dependency graph building, critical path finding,
blocked task detection, and layer computation.
These are pure Python tests that validate the algorithms
used in the dashboard TaskDependencyBoard component.
NO MOCKS — real computations only.
"""

import pytest
from typing import List, Dict, Optional


# ── Replicate the core graph algorithms (same logic as TypeScript) ──────

def build_dependency_graph(tasks: List[Dict]) -> Dict[str, Dict]:
    """Build dependency graph from task list — Python version of TS logic."""
    task_map = {t["id"]: t for t in tasks}

    # Build reverse dependency map
    blocks_map: Dict[str, List[str]] = {}
    for t in tasks:
        for dep_id in t.get("dependencies", []):
            if dep_id not in blocks_map:
                blocks_map[dep_id] = []
            blocks_map[dep_id].append(t["id"])

    # Calculate depths via BFS
    depths: Dict[str, int] = {}
    queue: List[str] = []

    for t in tasks:
        if not t.get("dependencies"):
            depths[t["id"]] = 0
            queue.append(t["id"])

    while queue:
        current = queue.pop(0)
        current_depth = depths.get(current, 0)
        for child_id in blocks_map.get(current, []):
            if current_depth + 1 > depths.get(child_id, 0):
                depths[child_id] = current_depth + 1
            if child_id not in queue:
                queue.append(child_id)

    # Unresolved tasks get max depth + 1
    max_depth = max(depths.values()) if depths else 0
    for t in tasks:
        if t["id"] not in depths:
            depths[t["id"]] = max_depth + 1

    # Blocked detection
    def is_blocked(task: Dict) -> List[str]:
        return [
            dep_id for dep_id in task.get("dependencies", [])
            if dep_id in task_map and task_map[dep_id].get("status") not in ("completed", "skipped")
        ]

    # Critical path
    critical_path = find_critical_path(tasks, task_map, blocks_map)

    nodes = {}
    for t in tasks:
        blocked_by = is_blocked(t)
        nodes[t["id"]] = {
            "task": t,
            "depth": depths.get(t["id"], 0),
            "blocked": len(blocked_by) > 0 and t.get("status") == "pending",
            "blocked_by": blocked_by,
            "blocks": blocks_map.get(t["id"], []),
            "critical_path": t["id"] in critical_path,
        }

    return nodes


def find_critical_path(tasks, task_map, blocks_map) -> set:
    """Find the longest path through the dependency graph."""
    memo = {}

    def longest_path(task_id):
        if task_id in memo:
            return memo[task_id]
        children = blocks_map.get(task_id, [])
        if not children:
            memo[task_id] = 1
            return 1
        result = 1 + max(longest_path(c) for c in children)
        memo[task_id] = result
        return result

    roots = [t for t in tasks if not t.get("dependencies")]
    max_len = 0
    best_root = None
    for r in roots:
        length = longest_path(r["id"])
        if length > max_len:
            max_len = length
            best_root = r["id"]

    path = set()
    def trace(task_id):
        path.add(task_id)
        children = blocks_map.get(task_id, [])
        if not children:
            return
        best_child = max(children, key=lambda c: memo.get(c, 0))
        trace(best_child)

    if best_root:
        trace(best_root)
    return path


# ── Test Data ───────────────────────────────────────────────────────────

def make_task(id: str, deps: List[str] = None, status: str = "pending", task_type: str = "api") -> Dict:
    return {
        "id": id,
        "epic_id": "EPIC-001",
        "type": task_type,
        "title": f"Task {id}",
        "description": f"Description for {id}",
        "status": status,
        "dependencies": deps or [],
        "estimated_minutes": 30,
        "actual_minutes": None,
        "error_message": None,
        "output_files": [],
    }


# ── Tests ───────────────────────────────────────────────────────────────

class TestBuildDependencyGraph:
    """Test dependency graph construction."""

    def test_empty_tasks(self):
        """Empty task list produces empty graph."""
        graph = build_dependency_graph([])
        assert len(graph) == 0

    def test_single_task_no_deps(self):
        """Single task with no dependencies → depth 0, not blocked."""
        tasks = [make_task("T1")]
        graph = build_dependency_graph(tasks)
        assert len(graph) == 1
        assert graph["T1"]["depth"] == 0
        assert graph["T1"]["blocked"] is False
        assert graph["T1"]["blocks"] == []

    def test_linear_chain(self):
        """Linear dependency chain A → B → C."""
        tasks = [
            make_task("A"),
            make_task("B", deps=["A"]),
            make_task("C", deps=["B"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["A"]["depth"] == 0
        assert graph["B"]["depth"] == 1
        assert graph["C"]["depth"] == 2

    def test_diamond_dependency(self):
        """Diamond: A → B, A → C, B → D, C → D."""
        tasks = [
            make_task("A"),
            make_task("B", deps=["A"]),
            make_task("C", deps=["A"]),
            make_task("D", deps=["B", "C"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["A"]["depth"] == 0
        assert graph["B"]["depth"] == 1
        assert graph["C"]["depth"] == 1
        assert graph["D"]["depth"] == 2

    def test_multiple_roots(self):
        """Multiple independent roots with separate chains."""
        tasks = [
            make_task("R1"),
            make_task("R2"),
            make_task("A", deps=["R1"]),
            make_task("B", deps=["R2"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["R1"]["depth"] == 0
        assert graph["R2"]["depth"] == 0
        assert graph["A"]["depth"] == 1
        assert graph["B"]["depth"] == 1


class TestBlockedDetection:
    """Test blocked task detection."""

    def test_not_blocked_when_dep_completed(self):
        """Task with completed dependency is not blocked."""
        tasks = [
            make_task("A", status="completed"),
            make_task("B", deps=["A"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["B"]["blocked"] is False

    def test_blocked_when_dep_pending(self):
        """Task with pending dependency is blocked."""
        tasks = [
            make_task("A", status="pending"),
            make_task("B", deps=["A"], status="pending"),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["B"]["blocked"] is True
        assert graph["B"]["blocked_by"] == ["A"]

    def test_not_blocked_when_dep_skipped(self):
        """Task with skipped dependency is not blocked."""
        tasks = [
            make_task("A", status="skipped"),
            make_task("B", deps=["A"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["B"]["blocked"] is False

    def test_blocked_by_multiple_deps(self):
        """Task blocked by multiple incomplete dependencies."""
        tasks = [
            make_task("A", status="pending"),
            make_task("B", status="running"),
            make_task("C", deps=["A", "B"], status="pending"),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["C"]["blocked"] is True
        assert set(graph["C"]["blocked_by"]) == {"A", "B"}

    def test_running_task_not_counted_as_blocked(self):
        """Running task is not considered blocked even with pending deps."""
        tasks = [
            make_task("A", status="pending"),
            make_task("B", deps=["A"], status="running"),
        ]
        graph = build_dependency_graph(tasks)
        # blocked = len(blocked_by) > 0 AND status == "pending"
        assert graph["B"]["blocked"] is False

    def test_completed_task_not_blocked(self):
        """Completed task is never blocked."""
        tasks = [
            make_task("A", status="pending"),
            make_task("B", deps=["A"], status="completed"),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["B"]["blocked"] is False


class TestBlocksTracking:
    """Test reverse dependency (blocks) tracking."""

    def test_root_blocks_children(self):
        """Root task's blocks list contains its dependents."""
        tasks = [
            make_task("A"),
            make_task("B", deps=["A"]),
            make_task("C", deps=["A"]),
        ]
        graph = build_dependency_graph(tasks)
        assert set(graph["A"]["blocks"]) == {"B", "C"}

    def test_leaf_has_no_blocks(self):
        """Leaf task blocks nothing."""
        tasks = [
            make_task("A"),
            make_task("B", deps=["A"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["B"]["blocks"] == []


class TestCriticalPath:
    """Test critical path detection."""

    def test_single_task_is_critical(self):
        """Single task is on the critical path."""
        tasks = [make_task("A")]
        graph = build_dependency_graph(tasks)
        assert graph["A"]["critical_path"] is True

    def test_linear_chain_all_critical(self):
        """Linear chain: all tasks on critical path."""
        tasks = [
            make_task("A"),
            make_task("B", deps=["A"]),
            make_task("C", deps=["B"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["A"]["critical_path"] is True
        assert graph["B"]["critical_path"] is True
        assert graph["C"]["critical_path"] is True

    def test_parallel_paths_longest_is_critical(self):
        """Parallel paths: only the longest is critical."""
        tasks = [
            make_task("R"),
            make_task("A", deps=["R"]),  # Short path: R → A
            make_task("B", deps=["R"]),  # Long path: R → B → C → D
            make_task("C", deps=["B"]),
            make_task("D", deps=["C"]),
        ]
        graph = build_dependency_graph(tasks)
        assert graph["R"]["critical_path"] is True
        assert graph["B"]["critical_path"] is True
        assert graph["C"]["critical_path"] is True
        assert graph["D"]["critical_path"] is True
        # A is on the shorter path
        assert graph["A"]["critical_path"] is False

    def test_diamond_critical_path(self):
        """Diamond: critical path goes through the deeper branch."""
        tasks = [
            make_task("root"),
            make_task("left", deps=["root"]),
            make_task("right", deps=["root"]),
            make_task("right_child", deps=["right"]),
            make_task("merge", deps=["left", "right_child"]),
        ]
        graph = build_dependency_graph(tasks)
        # Critical path: root → right → right_child → merge
        assert graph["root"]["critical_path"] is True
        assert graph["right"]["critical_path"] is True
        assert graph["right_child"]["critical_path"] is True
        assert graph["merge"]["critical_path"] is True
        # Left is shorter branch
        assert graph["left"]["critical_path"] is False


class TestDepthCalculation:
    """Test layer/depth assignments."""

    def test_wide_tree(self):
        """Wide tree with many roots at depth 0."""
        tasks = [make_task(f"R{i}") for i in range(5)]
        graph = build_dependency_graph(tasks)
        for i in range(5):
            assert graph[f"R{i}"]["depth"] == 0

    def test_deep_chain(self):
        """Deep chain assigns sequential depths."""
        n = 10
        tasks = [make_task("T0")]
        for i in range(1, n):
            tasks.append(make_task(f"T{i}", deps=[f"T{i-1}"]))
        graph = build_dependency_graph(tasks)
        for i in range(n):
            assert graph[f"T{i}"]["depth"] == i

    def test_convergent_depths(self):
        """When multiple paths converge, depth = max path length."""
        tasks = [
            make_task("A"),
            make_task("B"),
            make_task("C", deps=["A"]),
            make_task("D", deps=["B", "C"]),  # D depends on both B (depth 0) and C (depth 1)
        ]
        graph = build_dependency_graph(tasks)
        # D should be at depth 2 (max of B+1=1, C+1=2)
        assert graph["D"]["depth"] == 2


class TestRealWorldScenario:
    """Test with a realistic task list resembling a software project."""

    def test_backend_frontend_pipeline(self):
        """Schema → API → Frontend → Tests pipeline."""
        tasks = [
            make_task("schema_user", task_type="schema_migration"),
            make_task("schema_auth", task_type="schema_migration"),
            make_task("api_user", deps=["schema_user"], task_type="api_endpoint"),
            make_task("api_auth", deps=["schema_auth", "schema_user"], task_type="api_endpoint"),
            make_task("fe_login", deps=["api_auth"], task_type="fe_component"),
            make_task("fe_profile", deps=["api_user"], task_type="fe_component"),
            make_task("test_auth", deps=["fe_login", "api_auth"], task_type="test_e2e"),
            make_task("test_profile", deps=["fe_profile", "api_user"], task_type="test_e2e"),
        ]
        graph = build_dependency_graph(tasks)

        # Schema tasks at layer 0
        assert graph["schema_user"]["depth"] == 0
        assert graph["schema_auth"]["depth"] == 0

        # API tasks at layer 1
        assert graph["api_user"]["depth"] == 1
        assert graph["api_auth"]["depth"] == 1

        # Frontend at layer 2
        assert graph["fe_login"]["depth"] == 2
        assert graph["fe_profile"]["depth"] == 2

        # Tests at layer 3
        assert graph["test_auth"]["depth"] == 3
        assert graph["test_profile"]["depth"] == 3

        # All pending → blocked tasks should have upstream deps unmet
        assert graph["api_auth"]["blocked"] is True
        assert graph["fe_login"]["blocked"] is True
        assert graph["test_auth"]["blocked"] is True

        # Schema tasks are root → not blocked
        assert graph["schema_user"]["blocked"] is False
        assert graph["schema_auth"]["blocked"] is False

    def test_partial_completion(self):
        """Some tasks completed, check blocked/unblocked correctly."""
        tasks = [
            make_task("A", status="completed"),
            make_task("B", status="completed"),
            make_task("C", deps=["A"], status="completed"),
            make_task("D", deps=["B", "C"], status="pending"),  # Both deps done
            make_task("E", deps=["D"], status="pending"),  # D not done yet
        ]
        graph = build_dependency_graph(tasks)

        assert graph["D"]["blocked"] is False  # All deps completed
        assert graph["E"]["blocked"] is True  # D is pending
        assert graph["E"]["blocked_by"] == ["D"]
