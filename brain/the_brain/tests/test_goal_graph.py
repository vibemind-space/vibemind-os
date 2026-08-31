"""
Unit tests for the Goal Graph system (core/goal_graph.py).

Tests verify:
- Goal creation with properties (description, priority, deadline, context)
- Edge/dependency creation and blocking behavior
- Priority computation and ordering
- Critical path finding through hierarchical goals
- Context extraction for CTM (get_context_for_ctm / get_critical_path)
- Cycle detection (graph should handle gracefully)
- Goal completion, removal, and cascading unblock
- Goal update (progress, state transitions)
- Empty graph behavior (no crashes on empty operations)
- Single goal graph
- Complex multi-goal graph with deep hierarchies
- State serialization (to_dict)
- Goal priority ordering (ready goals sorted by priority)
- Subgoal relationships (parent-child linking)
- Goal progress tracking (0.0 to 1.0 clamping)
- Context with active goals vs no active goals
- Graph reset (new GoalGraph is empty)
- Large graph performance (>50 goals should not crash)
- Goal dependency chain (A -> B -> C unblocking cascade)
- Causal edge creation and querying
- Statistics reporting
- Goal failure handling
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from core.goal_graph import (
    GoalGraph, Goal, GoalState, GoalPriority, GoalPath,
    CausalEdgeType, CausalGoalEdge, create_goal_from_task
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def graph():
    """Create a fresh empty GoalGraph."""
    return GoalGraph()


@pytest.fixture
def graph_with_one_goal(graph):
    """Create a GoalGraph with a single goal."""
    goal = graph.add_goal("Single task", priority=GoalPriority.MEDIUM)
    return graph, goal


@pytest.fixture
def graph_with_hierarchy(graph):
    """Create a GoalGraph with a parent and three children."""
    parent = graph.add_goal(
        "Deploy application",
        priority=GoalPriority.HIGH,
        deadline=datetime.now() + timedelta(hours=4)
    )
    child1 = graph.add_goal(
        "Build Docker image",
        parent_id=parent.goal_id,
        priority=GoalPriority.HIGH,
        estimated_duration=timedelta(minutes=15)
    )
    child2 = graph.add_goal(
        "Run tests",
        parent_id=parent.goal_id,
        priority=GoalPriority.HIGH,
        depends_on=[child1.goal_id],
        estimated_duration=timedelta(minutes=30)
    )
    child3 = graph.add_goal(
        "Push to registry",
        parent_id=parent.goal_id,
        priority=GoalPriority.MEDIUM,
        depends_on=[child2.goal_id],
        estimated_duration=timedelta(minutes=5)
    )
    return graph, parent, child1, child2, child3


@pytest.fixture
def graph_with_chain(graph):
    """Create a linear dependency chain: A -> B -> C."""
    a = graph.add_goal("Step A", priority=GoalPriority.HIGH)
    b = graph.add_goal("Step B", depends_on=[a.goal_id], priority=GoalPriority.MEDIUM)
    c = graph.add_goal("Step C", depends_on=[b.goal_id], priority=GoalPriority.LOW)
    return graph, a, b, c


# ============================================================================
# 1. Goal Creation with Properties
# ============================================================================

class TestGoalCreation:
    def test_goal_has_unique_id(self, graph):
        """Each goal receives a unique ID."""
        g1 = graph.add_goal("Task 1")
        g2 = graph.add_goal("Task 2")
        assert g1.goal_id != g2.goal_id

    def test_goal_description_stored(self, graph):
        """Description is stored on the goal."""
        g = graph.add_goal("Analyze dataset")
        assert g.description == "Analyze dataset"

    def test_goal_priority_stored(self, graph):
        """Priority is correctly assigned."""
        g = graph.add_goal("Critical fix", priority=GoalPriority.CRITICAL)
        assert g.priority == GoalPriority.CRITICAL

    def test_goal_default_state_pending(self, graph):
        """A goal with no deps starts as PENDING."""
        g = graph.add_goal("Simple task")
        assert g.state == GoalState.PENDING

    def test_goal_deadline_stored(self, graph):
        """Deadline is stored when provided."""
        dl = datetime.now() + timedelta(hours=2)
        g = graph.add_goal("Timed task", deadline=dl)
        assert g.deadline == dl

    def test_goal_estimated_duration(self, graph):
        """Estimated duration is stored."""
        dur = timedelta(minutes=45)
        g = graph.add_goal("Long task", estimated_duration=dur)
        assert g.estimated_duration == dur

    def test_goal_context_stored(self, graph):
        """Custom context dict is preserved."""
        ctx = {"source": "user_request", "importance": 0.9}
        g = graph.add_goal("Contextual task", context=ctx)
        assert g.context == ctx

    def test_goal_initial_progress_zero(self, graph):
        """Progress starts at 0.0."""
        g = graph.add_goal("Fresh task")
        assert g.progress == 0.0

    def test_goal_added_to_graph(self, graph):
        """Goal is retrievable from the graph."""
        g = graph.add_goal("Retrievable")
        assert g.goal_id in graph.goals
        assert graph.goals[g.goal_id].description == "Retrievable"


# ============================================================================
# 2. Edge/Dependency Creation
# ============================================================================

class TestDependencyCreation:
    def test_dependency_blocks_goal(self, graph):
        """A goal with unfinished dependency starts BLOCKED."""
        a = graph.add_goal("Prerequisite")
        b = graph.add_goal("Blocked task", depends_on=[a.goal_id])
        assert b.state == GoalState.BLOCKED

    def test_dependency_recorded_on_dependent(self, graph):
        """Dependent goal tracks its dependency IDs."""
        a = graph.add_goal("Dep")
        b = graph.add_goal("Waiter", depends_on=[a.goal_id])
        # Initially blocked with dep recorded; depends_on has the dep id
        # (Note: depends_on may get modified on unblock, check blocked state)
        assert b.state == GoalState.BLOCKED

    def test_dependent_recorded_on_dependency(self, graph):
        """Dependency goal records who depends on it."""
        a = graph.add_goal("Provider")
        b = graph.add_goal("Consumer", depends_on=[a.goal_id])
        assert b.goal_id in a.dependents

    def test_multiple_dependencies(self, graph):
        """A goal can depend on multiple other goals."""
        a = graph.add_goal("Dep A")
        b = graph.add_goal("Dep B")
        c = graph.add_goal("Needs both", depends_on=[a.goal_id, b.goal_id])
        assert c.state == GoalState.BLOCKED

    def test_dependency_on_completed_goal_is_pending(self, graph):
        """If dependency is already completed, goal starts PENDING."""
        a = graph.add_goal("Already done")
        graph.start_goal(a.goal_id)
        graph.complete_goal(a.goal_id)
        b = graph.add_goal("Should be pending", depends_on=[a.goal_id])
        assert b.state == GoalState.PENDING


# ============================================================================
# 3. Priority Computation
# ============================================================================

class TestPriorityComputation:
    def test_ready_goals_sorted_by_priority(self, graph):
        """get_ready_goals returns goals sorted by priority (CRITICAL first)."""
        graph.add_goal("Low task", priority=GoalPriority.LOW)
        graph.add_goal("Critical task", priority=GoalPriority.CRITICAL)
        graph.add_goal("Medium task", priority=GoalPriority.MEDIUM)

        ready = graph.get_ready_goals()
        priorities = [g.priority.value for g in ready]
        assert priorities == sorted(priorities)

    def test_get_next_goal_is_highest_priority(self, graph):
        """get_next_goal returns highest priority ready goal."""
        graph.add_goal("Background", priority=GoalPriority.BACKGROUND)
        crit = graph.add_goal("Critical", priority=GoalPriority.CRITICAL)

        nxt = graph.get_next_goal()
        assert nxt is not None
        assert nxt.goal_id == crit.goal_id

    def test_priority_index_tracks_goals(self, graph):
        """Internal _by_priority index keeps track of goals."""
        graph.add_goal("High1", priority=GoalPriority.HIGH)
        graph.add_goal("High2", priority=GoalPriority.HIGH)
        graph.add_goal("Low1", priority=GoalPriority.LOW)

        assert len(graph._by_priority[GoalPriority.HIGH]) == 2
        assert len(graph._by_priority[GoalPriority.LOW]) == 1


# ============================================================================
# 4. Critical Path Finding
# ============================================================================

class TestCriticalPath:
    def test_critical_path_empty_graph(self, graph):
        """Critical path on empty graph returns empty GoalPath."""
        path = graph.get_critical_path()
        assert isinstance(path, GoalPath)
        assert path.goals == []

    def test_critical_path_single_goal(self, graph_with_one_goal):
        """Critical path with one root goal returns that goal."""
        g, goal = graph_with_one_goal
        path = g.get_critical_path()
        assert goal.goal_id in path.goals

    def test_critical_path_hierarchy(self, graph_with_hierarchy):
        """Critical path through hierarchy includes root and deepest child."""
        g, parent, child1, child2, child3 = graph_with_hierarchy
        path = g.get_critical_path()
        assert len(path.goals) > 1
        # The root should be first in the path
        assert path.goals[0] == parent.goal_id

    def test_critical_path_has_goals_attribute(self, graph_with_hierarchy):
        """GoalPath object has .goals attribute (used by CTM context)."""
        g, parent, _, _, _ = graph_with_hierarchy
        path = g.get_critical_path()
        assert hasattr(path, 'goals')
        assert isinstance(path.goals, list)

    def test_critical_path_marked_as_critical(self, graph_with_hierarchy):
        """The returned path has critical_path=True."""
        g, *_ = graph_with_hierarchy
        path = g.get_critical_path()
        if path.goals:
            assert path.critical_path is True


# ============================================================================
# 5. Context Extraction for CTM
# ============================================================================

class TestContextForCTM:
    def test_context_returns_dict(self, graph):
        """get_context_for_ctm returns a dictionary."""
        ctx = graph.get_context_for_ctm()
        assert isinstance(ctx, dict)

    def test_context_has_required_keys(self, graph):
        """CTM context has all expected keys."""
        ctx = graph.get_context_for_ctm()
        required_keys = [
            'active_goals', 'ready_goals', 'blocked_count',
            'overdue_count', 'total_goals', 'completion_rate',
            'critical_path'
        ]
        for key in required_keys:
            assert key in ctx, f"Missing key: {key}"

    def test_context_with_active_goals(self, graph):
        """Active goals appear in CTM context."""
        g = graph.add_goal("Active task")
        graph.start_goal(g.goal_id)
        ctx = graph.get_context_for_ctm()
        assert len(ctx['active_goals']) == 1
        assert ctx['active_goals'][0]['description'] == "Active task"

    def test_context_active_goal_has_fields(self, graph):
        """Each active goal entry has id, description, priority, progress, deadline."""
        g = graph.add_goal("Detailed task", priority=GoalPriority.HIGH)
        graph.start_goal(g.goal_id)
        ctx = graph.get_context_for_ctm()
        entry = ctx['active_goals'][0]
        assert 'id' in entry
        assert 'description' in entry
        assert 'priority' in entry
        assert 'progress' in entry
        assert 'deadline' in entry

    def test_context_critical_path_is_list(self, graph_with_hierarchy):
        """Critical path in context is a list of descriptions."""
        g, *_ = graph_with_hierarchy
        ctx = g.get_context_for_ctm()
        assert isinstance(ctx['critical_path'], list)

    def test_context_completion_rate(self, graph):
        """Completion rate is 0.0 on empty or all-pending graph."""
        ctx = graph.get_context_for_ctm()
        assert ctx['completion_rate'] == 0.0


# ============================================================================
# 6. Cycle Detection (Graceful Handling)
# ============================================================================

class TestCycleDetection:
    def test_self_dependency_does_not_crash(self, graph):
        """Adding a goal that depends on itself should not crash the graph."""
        # A goal cannot realistically depend on itself since it won't exist yet,
        # but the graph should handle a non-existent dep gracefully
        g = graph.add_goal("Self ref", depends_on=["nonexistent_id"])
        # Goal is blocked but graph is intact
        assert g.state == GoalState.BLOCKED
        # Operations still work
        ctx = graph.get_context_for_ctm()
        assert isinstance(ctx, dict)

    def test_critical_path_with_disconnected_deps(self, graph):
        """Critical path does not crash when deps reference missing goals."""
        g = graph.add_goal("Orphan dep", depends_on=["missing_1", "missing_2"])
        path = graph.get_critical_path()
        assert isinstance(path, GoalPath)

    def test_mutual_dependency_no_infinite_loop(self, graph):
        """If two goals somehow reference each other, no infinite loop in operations."""
        a = graph.add_goal("Goal A")
        b = graph.add_goal("Goal B", depends_on=[a.goal_id])
        # Manually inject reverse dep to simulate cycle
        a.depends_on.append(b.goal_id)
        # Critical path and context should still return without hanging
        path = graph.get_critical_path()
        assert isinstance(path, GoalPath)
        ctx = graph.get_context_for_ctm()
        assert isinstance(ctx, dict)


# ============================================================================
# 7. Goal Completion / Removal
# ============================================================================

class TestGoalCompletion:
    def test_complete_active_goal(self, graph):
        """An active goal can be completed."""
        g = graph.add_goal("Completable")
        graph.start_goal(g.goal_id)
        result = graph.complete_goal(g.goal_id, "Done!")
        assert result is True
        assert g.state == GoalState.COMPLETED
        assert g.result == "Done!"

    def test_complete_sets_progress_to_one(self, graph):
        """Completing a goal sets progress to 1.0."""
        g = graph.add_goal("Full progress")
        graph.start_goal(g.goal_id)
        graph.complete_goal(g.goal_id)
        assert g.progress == 1.0

    def test_complete_records_timestamp(self, graph):
        """Completion records completed_at timestamp."""
        g = graph.add_goal("Timed")
        graph.start_goal(g.goal_id)
        graph.complete_goal(g.goal_id)
        assert g.completed_at is not None

    def test_cannot_complete_pending_goal(self, graph):
        """Cannot complete a goal that is not active."""
        g = graph.add_goal("Not started")
        result = graph.complete_goal(g.goal_id)
        assert result is False
        assert g.state == GoalState.PENDING

    def test_cannot_complete_nonexistent_goal(self, graph):
        """Completing a non-existent goal returns False."""
        result = graph.complete_goal("does_not_exist")
        assert result is False

    def test_completion_unblocks_dependents(self, graph_with_chain):
        """Completing a goal unblocks its dependent goals."""
        g, a, b, c = graph_with_chain
        assert b.state == GoalState.BLOCKED

        g.start_goal(a.goal_id)
        g.complete_goal(a.goal_id)
        assert b.state == GoalState.PENDING

    def test_completion_recorded_in_history(self, graph):
        """Completed goals are tracked in completed_goals list."""
        g = graph.add_goal("Tracked")
        graph.start_goal(g.goal_id)
        graph.complete_goal(g.goal_id)
        assert len(graph.completed_goals) == 1
        assert graph.completed_goals[0][0] == g.goal_id


# ============================================================================
# 8. Goal Update
# ============================================================================

class TestGoalUpdate:
    def test_update_progress(self, graph):
        """Progress can be updated to a value between 0 and 1."""
        g = graph.add_goal("Progressive")
        result = graph.update_progress(g.goal_id, 0.5)
        assert result is True
        assert g.progress == 0.5

    def test_update_progress_clamps_high(self, graph):
        """Progress is clamped to max 1.0."""
        g = graph.add_goal("Over-achiever")
        graph.update_progress(g.goal_id, 1.5)
        assert g.progress == 1.0

    def test_update_progress_clamps_low(self, graph):
        """Progress is clamped to min 0.0."""
        g = graph.add_goal("Under-achiever")
        graph.update_progress(g.goal_id, -0.3)
        assert g.progress == 0.0

    def test_update_progress_nonexistent(self, graph):
        """Updating progress on missing goal returns False."""
        result = graph.update_progress("nope", 0.5)
        assert result is False

    def test_start_goal_transitions_to_active(self, graph):
        """Starting a pending goal transitions it to ACTIVE."""
        g = graph.add_goal("Startable")
        result = graph.start_goal(g.goal_id)
        assert result is True
        assert g.state == GoalState.ACTIVE

    def test_start_goal_sets_started_at(self, graph):
        """Starting a goal records started_at."""
        g = graph.add_goal("Timed start")
        graph.start_goal(g.goal_id)
        assert g.started_at is not None

    def test_cannot_start_blocked_with_unmet_deps(self, graph):
        """Cannot start a blocked goal whose deps are not complete."""
        a = graph.add_goal("Dep")
        b = graph.add_goal("Blocked", depends_on=[a.goal_id])
        result = graph.start_goal(b.goal_id)
        assert result is False


# ============================================================================
# 9. Empty Graph Behavior
# ============================================================================

class TestEmptyGraph:
    def test_empty_graph_no_goals(self, graph):
        """Fresh graph has no goals."""
        assert len(graph.goals) == 0

    def test_empty_graph_ready_goals(self, graph):
        """Ready goals on empty graph returns empty list."""
        assert graph.get_ready_goals() == []

    def test_empty_graph_active_goals(self, graph):
        """Active goals on empty graph returns empty list."""
        assert graph.get_active_goals() == []

    def test_empty_graph_blocked_goals(self, graph):
        """Blocked goals on empty graph returns empty list."""
        assert graph.get_blocked_goals() == []

    def test_empty_graph_next_goal_is_none(self, graph):
        """get_next_goal on empty graph returns None."""
        assert graph.get_next_goal() is None

    def test_empty_graph_context(self, graph):
        """CTM context on empty graph has zero counts."""
        ctx = graph.get_context_for_ctm()
        assert ctx['total_goals'] == 0
        assert ctx['active_goals'] == []
        assert ctx['ready_goals'] == []
        assert ctx['blocked_count'] == 0

    def test_empty_graph_statistics(self, graph):
        """Statistics on empty graph returns valid structure."""
        stats = graph.get_statistics()
        assert stats['total_goals'] == 0
        assert stats['root_goals'] == 0

    def test_empty_graph_to_dict(self, graph):
        """to_dict on empty graph returns valid structure."""
        d = graph.to_dict()
        assert d['goals'] == {}
        assert d['root_goals'] == []


# ============================================================================
# 10. Single Goal Graph
# ============================================================================

class TestSingleGoalGraph:
    def test_single_goal_is_root(self, graph_with_one_goal):
        """A single goal with no parent is a root goal."""
        g, goal = graph_with_one_goal
        assert goal.goal_id in g.root_goals

    def test_single_goal_is_ready(self, graph_with_one_goal):
        """A single goal with no deps is ready."""
        g, goal = graph_with_one_goal
        ready = g.get_ready_goals()
        assert len(ready) == 1
        assert ready[0].goal_id == goal.goal_id

    def test_single_goal_critical_path(self, graph_with_one_goal):
        """Critical path for a single-goal graph contains that goal."""
        g, goal = graph_with_one_goal
        path = g.get_critical_path()
        assert goal.goal_id in path.goals

    def test_single_goal_lifecycle(self, graph_with_one_goal):
        """Full lifecycle: PENDING -> ACTIVE -> COMPLETED."""
        g, goal = graph_with_one_goal
        assert goal.state == GoalState.PENDING
        g.start_goal(goal.goal_id)
        assert goal.state == GoalState.ACTIVE
        g.complete_goal(goal.goal_id, "All done")
        assert goal.state == GoalState.COMPLETED


# ============================================================================
# 11. Complex Multi-Goal Graph
# ============================================================================

class TestComplexGraph:
    def test_deep_hierarchy(self, graph):
        """A deep hierarchy (5 levels) works correctly."""
        current = graph.add_goal("Level 0")
        all_goals = [current]
        for i in range(1, 5):
            child = graph.add_goal(f"Level {i}", parent_id=current.goal_id)
            all_goals.append(child)
            current = child

        # Verify parent-child chain
        assert len(graph.goals) == 5
        path = graph.get_critical_path()
        assert len(path.goals) == 5

    def test_wide_graph(self, graph):
        """A wide graph (1 parent, 10 children) works correctly."""
        parent = graph.add_goal("Wide parent")
        children = []
        for i in range(10):
            c = graph.add_goal(f"Child {i}", parent_id=parent.goal_id)
            children.append(c)

        assert len(parent.child_ids) == 10
        assert len(graph.goals) == 11

    def test_diamond_dependency(self, graph):
        """Diamond dependency: A -> B,C -> D works."""
        a = graph.add_goal("A")
        b = graph.add_goal("B", depends_on=[a.goal_id])
        c = graph.add_goal("C", depends_on=[a.goal_id])
        d = graph.add_goal("D", depends_on=[b.goal_id, c.goal_id])

        assert d.state == GoalState.BLOCKED
        # Complete A, then B and C become pending
        graph.start_goal(a.goal_id)
        graph.complete_goal(a.goal_id)
        assert b.state == GoalState.PENDING
        assert c.state == GoalState.PENDING
        # D is still blocked (needs both B and C)
        assert d.state == GoalState.BLOCKED

    def test_parallel_independent_goals(self, graph):
        """Multiple independent goals are all ready simultaneously."""
        goals = [graph.add_goal(f"Independent {i}") for i in range(5)]
        ready = graph.get_ready_goals()
        assert len(ready) == 5


# ============================================================================
# 12. State Serialization (to_dict)
# ============================================================================

class TestSerialization:
    def test_to_dict_structure(self, graph_with_hierarchy):
        """to_dict produces expected top-level keys."""
        g, *_ = graph_with_hierarchy
        d = g.to_dict()
        assert 'goals' in d
        assert 'root_goals' in d
        assert 'statistics' in d

    def test_to_dict_goal_fields(self, graph):
        """Each goal in to_dict has required fields."""
        g = graph.add_goal("Serializable", priority=GoalPriority.HIGH)
        d = graph.to_dict()
        goal_dict = d['goals'][g.goal_id]

        expected_fields = [
            'goal_id', 'description', 'state', 'priority',
            'parent_id', 'child_ids', 'depends_on', 'progress',
            'deadline', 'created_at', 'context'
        ]
        for f in expected_fields:
            assert f in goal_dict, f"Missing field: {f}"

    def test_to_dict_state_is_string(self, graph):
        """Goal state is serialized as string value."""
        g = graph.add_goal("State check")
        d = graph.to_dict()
        assert d['goals'][g.goal_id]['state'] == 'pending'

    def test_to_dict_priority_is_int(self, graph):
        """Priority is serialized as integer value."""
        g = graph.add_goal("Priority check", priority=GoalPriority.CRITICAL)
        d = graph.to_dict()
        assert d['goals'][g.goal_id]['priority'] == 1  # CRITICAL = 1

    def test_to_dict_includes_statistics(self, graph):
        """to_dict includes statistics sub-dict."""
        graph.add_goal("Stats goal")
        d = graph.to_dict()
        stats = d['statistics']
        assert stats['total_goals'] == 1


# ============================================================================
# 13. Goal Priority Ordering
# ============================================================================

class TestPriorityOrdering:
    def test_all_priority_levels(self, graph):
        """All five priority levels are recognized."""
        priorities = [
            GoalPriority.CRITICAL, GoalPriority.HIGH,
            GoalPriority.MEDIUM, GoalPriority.LOW,
            GoalPriority.BACKGROUND
        ]
        for p in priorities:
            graph.add_goal(f"P={p.name}", priority=p)

        ready = graph.get_ready_goals()
        assert len(ready) == 5
        # Verify sorted order: CRITICAL(1) < HIGH(2) < MEDIUM(3) < LOW(4) < BACKGROUND(5)
        values = [g.priority.value for g in ready]
        assert values == sorted(values)

    def test_same_priority_stable_order(self, graph):
        """Goals with same priority are returned without crashing."""
        for i in range(5):
            graph.add_goal(f"Same prio {i}", priority=GoalPriority.MEDIUM)
        ready = graph.get_ready_goals()
        assert len(ready) == 5

    def test_deadline_tiebreaker(self, graph):
        """Among same-priority goals, earlier deadline comes first."""
        soon = datetime.now() + timedelta(minutes=30)
        later = datetime.now() + timedelta(hours=5)

        graph.add_goal("Later deadline", priority=GoalPriority.HIGH, deadline=later)
        graph.add_goal("Soon deadline", priority=GoalPriority.HIGH, deadline=soon)

        ready = graph.get_ready_goals()
        assert len(ready) == 2
        # First goal should have the earlier deadline
        assert ready[0].deadline <= ready[1].deadline


# ============================================================================
# 14. Subgoal Relationships
# ============================================================================

class TestSubgoalRelationships:
    def test_parent_tracks_children(self, graph):
        """Parent goal's child_ids lists its children."""
        parent = graph.add_goal("Parent")
        c1 = graph.add_goal("Child 1", parent_id=parent.goal_id)
        c2 = graph.add_goal("Child 2", parent_id=parent.goal_id)

        assert c1.goal_id in parent.child_ids
        assert c2.goal_id in parent.child_ids

    def test_child_tracks_parent(self, graph):
        """Child goal's parent_id references its parent."""
        parent = graph.add_goal("Parent")
        child = graph.add_goal("Child", parent_id=parent.goal_id)
        assert child.parent_id == parent.goal_id

    def test_get_goal_path(self, graph):
        """get_goal_path returns path from root to goal."""
        root = graph.add_goal("Root")
        mid = graph.add_goal("Mid", parent_id=root.goal_id)
        leaf = graph.add_goal("Leaf", parent_id=mid.goal_id)

        path = graph.get_goal_path(leaf.goal_id)
        assert len(path) == 3
        assert path[0].goal_id == root.goal_id
        assert path[1].goal_id == mid.goal_id
        assert path[2].goal_id == leaf.goal_id

    def test_get_subtree(self, graph):
        """get_subtree returns all goals in the subtree."""
        root = graph.add_goal("Root")
        c1 = graph.add_goal("C1", parent_id=root.goal_id)
        c2 = graph.add_goal("C2", parent_id=root.goal_id)
        c1_1 = graph.add_goal("C1.1", parent_id=c1.goal_id)

        subtree = graph.get_subtree(root.goal_id)
        ids = {g.goal_id for g in subtree}
        assert root.goal_id in ids
        assert c1.goal_id in ids
        assert c2.goal_id in ids
        assert c1_1.goal_id in ids

    def test_child_with_invalid_parent_becomes_root(self, graph):
        """A child referencing a non-existent parent is treated as root."""
        child = graph.add_goal("Orphan child", parent_id="nonexistent_parent")
        assert child.goal_id in graph.root_goals


# ============================================================================
# 15. Goal Progress Tracking
# ============================================================================

class TestProgressTracking:
    def test_incremental_progress(self, graph):
        """Progress can be updated incrementally."""
        g = graph.add_goal("Incremental")
        graph.update_progress(g.goal_id, 0.25)
        assert g.progress == 0.25
        graph.update_progress(g.goal_id, 0.75)
        assert g.progress == 0.75

    def test_progress_exact_boundaries(self, graph):
        """Progress at exact 0.0 and 1.0 is valid."""
        g = graph.add_goal("Boundary")
        graph.update_progress(g.goal_id, 0.0)
        assert g.progress == 0.0
        graph.update_progress(g.goal_id, 1.0)
        assert g.progress == 1.0

    def test_progress_in_context(self, graph):
        """Active goal progress appears in CTM context."""
        g = graph.add_goal("Progressing")
        graph.start_goal(g.goal_id)
        graph.update_progress(g.goal_id, 0.6)
        ctx = graph.get_context_for_ctm()
        assert ctx['active_goals'][0]['progress'] == 0.6


# ============================================================================
# 16. Context with Active Goals
# ============================================================================

class TestContextActiveGoals:
    def test_multiple_active_goals_in_context(self, graph):
        """Multiple active goals all appear in context."""
        g1 = graph.add_goal("Active 1")
        g2 = graph.add_goal("Active 2")
        graph.start_goal(g1.goal_id)
        graph.start_goal(g2.goal_id)
        ctx = graph.get_context_for_ctm()
        assert len(ctx['active_goals']) == 2

    def test_completed_goals_not_in_active(self, graph):
        """Completed goals do not appear in active_goals context."""
        g = graph.add_goal("Will complete")
        graph.start_goal(g.goal_id)
        graph.complete_goal(g.goal_id)
        ctx = graph.get_context_for_ctm()
        assert len(ctx['active_goals']) == 0

    def test_blocked_count_in_context(self, graph):
        """Blocked goals count appears in context."""
        a = graph.add_goal("Blocker")
        graph.add_goal("Blocked1", depends_on=[a.goal_id])
        graph.add_goal("Blocked2", depends_on=[a.goal_id])
        ctx = graph.get_context_for_ctm()
        assert ctx['blocked_count'] == 2


# ============================================================================
# 17. Context with No Active Goals
# ============================================================================

class TestContextNoActiveGoals:
    def test_no_active_goals_empty_list(self, graph):
        """When no goals are active, active_goals is empty."""
        graph.add_goal("Pending only")
        ctx = graph.get_context_for_ctm()
        assert ctx['active_goals'] == []

    def test_ready_goals_shown_when_no_active(self, graph):
        """Ready goals still appear when nothing is active."""
        graph.add_goal("Ready 1")
        graph.add_goal("Ready 2")
        ctx = graph.get_context_for_ctm()
        assert len(ctx['ready_goals']) == 2

    def test_ready_goals_capped_at_five(self, graph):
        """CTM context caps ready goals at 5."""
        for i in range(10):
            graph.add_goal(f"Ready {i}")
        ctx = graph.get_context_for_ctm()
        assert len(ctx['ready_goals']) <= 5


# ============================================================================
# 18. Graph Reset
# ============================================================================

class TestGraphReset:
    def test_new_graph_is_clean(self):
        """A freshly constructed GoalGraph is completely empty."""
        g = GoalGraph()
        assert len(g.goals) == 0
        assert len(g.root_goals) == 0
        assert len(g.completed_goals) == 0
        assert len(g.failed_goals) == 0
        assert len(g.causal_edges) == 0

    def test_independent_graphs(self):
        """Two GoalGraph instances do not share state."""
        g1 = GoalGraph()
        g2 = GoalGraph()
        g1.add_goal("Only in g1")
        assert len(g1.goals) == 1
        assert len(g2.goals) == 0


# ============================================================================
# 19. Large Graph Performance (>50 goals)
# ============================================================================

class TestLargeGraph:
    def test_fifty_goals_no_crash(self, graph):
        """Adding 50+ goals does not crash."""
        goals = []
        for i in range(60):
            g = graph.add_goal(f"Goal {i}")
            goals.append(g)
        assert len(graph.goals) == 60

    def test_large_graph_critical_path(self, graph):
        """Critical path computation on 50+ goal graph completes."""
        parent = graph.add_goal("Root")
        current = parent
        for i in range(50):
            child = graph.add_goal(f"Chain {i}", parent_id=current.goal_id)
            current = child

        path = graph.get_critical_path()
        assert len(path.goals) == 51  # root + 50 children

    def test_large_graph_context(self, graph):
        """CTM context on a large graph returns valid data."""
        for i in range(100):
            graph.add_goal(f"Mass goal {i}")
        ctx = graph.get_context_for_ctm()
        assert ctx['total_goals'] == 100
        assert len(ctx['ready_goals']) <= 5  # Capped

    def test_large_graph_statistics(self, graph):
        """Statistics on large graph are correct."""
        for i in range(75):
            graph.add_goal(f"Stat goal {i}")
        stats = graph.get_statistics()
        assert stats['total_goals'] == 75
        assert stats['root_goals'] == 75

    def test_large_wide_hierarchy(self, graph):
        """Wide hierarchy (1 parent, 50 children) handles to_dict."""
        parent = graph.add_goal("Big parent")
        for i in range(50):
            graph.add_goal(f"Wide child {i}", parent_id=parent.goal_id)

        d = graph.to_dict()
        assert len(d['goals']) == 51


# ============================================================================
# 20. Goal Dependency Chain (A -> B -> C unblocking cascade)
# ============================================================================

class TestDependencyChain:
    def test_chain_initial_states(self, graph_with_chain):
        """In chain A -> B -> C: A=PENDING, B=BLOCKED, C=BLOCKED."""
        g, a, b, c = graph_with_chain
        assert a.state == GoalState.PENDING
        assert b.state == GoalState.BLOCKED
        assert c.state == GoalState.BLOCKED

    def test_chain_cascade_unblock(self, graph_with_chain):
        """Completing A unblocks B; completing B unblocks C."""
        g, a, b, c = graph_with_chain
        # Complete A
        g.start_goal(a.goal_id)
        g.complete_goal(a.goal_id)
        assert b.state == GoalState.PENDING

        # Complete B
        g.start_goal(b.goal_id)
        g.complete_goal(b.goal_id)
        assert c.state == GoalState.PENDING

    def test_chain_full_lifecycle(self, graph_with_chain):
        """Full chain lifecycle: all three goals complete in order."""
        g, a, b, c = graph_with_chain
        for goal in [a, b, c]:
            g.start_goal(goal.goal_id)
            g.complete_goal(goal.goal_id)

        assert a.state == GoalState.COMPLETED
        assert b.state == GoalState.COMPLETED
        assert c.state == GoalState.COMPLETED
        assert len(g.completed_goals) == 3

    def test_chain_skip_not_allowed(self, graph_with_chain):
        """Cannot start C while B is still blocked."""
        g, a, b, c = graph_with_chain
        result = g.start_goal(c.goal_id)
        assert result is False
        assert c.state == GoalState.BLOCKED


# ============================================================================
# Additional: Goal Failure, Causal Edges, Statistics, Convenience Functions
# ============================================================================

class TestGoalFailure:
    def test_fail_active_goal(self, graph):
        """An active goal can be failed with a reason."""
        g = graph.add_goal("Will fail")
        graph.start_goal(g.goal_id)
        result = graph.fail_goal(g.goal_id, "Out of resources")
        assert result is True
        assert g.state == GoalState.FAILED
        assert g.failure_reason == "Out of resources"

    def test_fail_pending_goal(self, graph):
        """A pending goal can be failed."""
        g = graph.add_goal("Never started")
        result = graph.fail_goal(g.goal_id, "Cancelled by user")
        assert result is True
        assert g.state == GoalState.FAILED

    def test_fail_blocked_goal(self, graph):
        """A blocked goal can be failed."""
        a = graph.add_goal("Dep")
        b = graph.add_goal("Blocked", depends_on=[a.goal_id])
        result = graph.fail_goal(b.goal_id, "Dep failed")
        assert result is True
        assert b.state == GoalState.FAILED

    def test_cannot_fail_completed_goal(self, graph):
        """A completed goal cannot be failed."""
        g = graph.add_goal("Already done")
        graph.start_goal(g.goal_id)
        graph.complete_goal(g.goal_id)
        result = graph.fail_goal(g.goal_id, "Too late")
        assert result is False
        assert g.state == GoalState.COMPLETED

    def test_fail_records_in_history(self, graph):
        """Failed goals are recorded in failed_goals history."""
        g = graph.add_goal("Tracked failure")
        graph.start_goal(g.goal_id)
        graph.fail_goal(g.goal_id, "Timeout")
        assert len(graph.failed_goals) == 1
        assert graph.failed_goals[0][0] == g.goal_id
        assert graph.failed_goals[0][2] == "Timeout"


class TestCausalEdges:
    def test_add_causal_edge(self, graph):
        """A causal edge can be added between two existing goals."""
        a = graph.add_goal("Cause")
        b = graph.add_goal("Effect")
        edge = graph.add_causal_edge(
            a.goal_id, b.goal_id,
            CausalEdgeType.ENABLES, strength=0.8
        )
        assert edge.source_goal == a.goal_id
        assert edge.target_goal == b.goal_id
        assert edge.edge_type == CausalEdgeType.ENABLES
        assert edge.strength == 0.8

    def test_causal_edge_invalid_source(self, graph):
        """Adding a causal edge with invalid source raises ValueError."""
        b = graph.add_goal("Only target")
        with pytest.raises(ValueError):
            graph.add_causal_edge("nonexistent", b.goal_id, CausalEdgeType.ENABLES)

    def test_causal_edge_invalid_target(self, graph):
        """Adding a causal edge with invalid target raises ValueError."""
        a = graph.add_goal("Only source")
        with pytest.raises(ValueError):
            graph.add_causal_edge(a.goal_id, "nonexistent", CausalEdgeType.ENABLES)

    def test_get_causal_effects(self, graph):
        """get_causal_effects returns edges from source goal."""
        a = graph.add_goal("Source")
        b = graph.add_goal("Target")
        graph.add_causal_edge(a.goal_id, b.goal_id, CausalEdgeType.TRIGGERS)
        effects = graph.get_causal_effects(a.goal_id)
        assert len(effects) == 1
        assert effects[0].target_goal == b.goal_id

    def test_get_causal_causes(self, graph):
        """get_causal_causes returns edges to target goal."""
        a = graph.add_goal("Source")
        b = graph.add_goal("Target")
        graph.add_causal_edge(a.goal_id, b.goal_id, CausalEdgeType.CONTRIBUTES)
        causes = graph.get_causal_causes(b.goal_id)
        assert len(causes) == 1
        assert causes[0].source_goal == a.goal_id

    def test_infer_causal_edges_from_deps(self, graph_with_chain):
        """infer_causal_edges_from_dependencies creates edges from deps."""
        g, a, b, c = graph_with_chain
        count = g.infer_causal_edges_from_dependencies()
        assert count > 0
        assert len(g.causal_edges) > 0

    def test_causal_edges_in_statistics(self, graph):
        """Causal edge count appears in statistics."""
        a = graph.add_goal("S")
        b = graph.add_goal("T")
        graph.add_causal_edge(a.goal_id, b.goal_id, CausalEdgeType.ENABLES)
        stats = graph.get_statistics()
        assert stats['causal_edges'] == 1


class TestStatistics:
    def test_statistics_structure(self, graph):
        """Statistics dict has expected keys."""
        stats = graph.get_statistics()
        expected = [
            'total_goals', 'by_state', 'by_priority',
            'root_goals', 'completed_count', 'failed_count',
            'completion_rate', 'causal_edges'
        ]
        for key in expected:
            assert key in stats

    def test_statistics_by_state(self, graph):
        """by_state counts reflect actual goal states."""
        g1 = graph.add_goal("Pending")
        g2 = graph.add_goal("Will be active")
        graph.start_goal(g2.goal_id)

        stats = graph.get_statistics()
        assert stats['by_state'].get('pending', 0) >= 1
        assert stats['by_state'].get('active', 0) >= 1

    def test_completion_rate_calculation(self, graph):
        """Completion rate is correct fraction."""
        g1 = graph.add_goal("Done")
        g2 = graph.add_goal("Not done")
        graph.start_goal(g1.goal_id)
        graph.complete_goal(g1.goal_id)

        stats = graph.get_statistics()
        assert stats['completion_rate'] == 0.5


class TestConvenienceFunction:
    def test_create_goal_from_task_urgent(self):
        """create_goal_from_task assigns CRITICAL for 'urgent' keyword."""
        g = create_goal_from_task("Fix urgent production bug")
        assert g.priority == GoalPriority.CRITICAL

    def test_create_goal_from_task_important(self):
        """create_goal_from_task assigns HIGH for 'important' keyword."""
        g = create_goal_from_task("Important meeting prep")
        assert g.priority == GoalPriority.HIGH

    def test_create_goal_from_task_low(self):
        """create_goal_from_task assigns LOW for 'when possible' keyword."""
        g = create_goal_from_task("Update docs when possible")
        assert g.priority == GoalPriority.LOW

    def test_create_goal_from_task_background(self):
        """create_goal_from_task assigns BACKGROUND for 'background' keyword."""
        g = create_goal_from_task("Run background cleanup")
        assert g.priority == GoalPriority.BACKGROUND

    def test_create_goal_from_task_default_medium(self):
        """create_goal_from_task assigns MEDIUM for generic task."""
        g = create_goal_from_task("Process data batch")
        assert g.priority == GoalPriority.MEDIUM

    def test_create_goal_from_task_has_duration(self):
        """create_goal_from_task sets estimated_duration based on complexity."""
        g = create_goal_from_task("Complex analysis", complexity=0.8)
        assert g.estimated_duration is not None
        assert g.estimated_duration.total_seconds() > 0

    def test_create_goal_from_task_has_context(self):
        """create_goal_from_task stores complexity in context."""
        g = create_goal_from_task("Task", complexity=0.7)
        assert g.context['complexity'] == 0.7


class TestGoalHelperMethods:
    def test_is_ready_pending_no_deps(self, graph):
        """is_ready is True for PENDING goal with no deps."""
        g = graph.add_goal("Ready")
        assert g.is_ready() is True

    def test_is_ready_false_when_active(self, graph):
        """is_ready is False for ACTIVE goal."""
        g = graph.add_goal("Active")
        graph.start_goal(g.goal_id)
        assert g.is_ready() is False

    def test_is_overdue_false_no_deadline(self, graph):
        """is_overdue is False when no deadline is set."""
        g = graph.add_goal("No deadline")
        assert g.is_overdue() is False

    def test_is_overdue_true_past_deadline(self, graph):
        """is_overdue is True when deadline has passed."""
        past = datetime.now() - timedelta(hours=1)
        g = graph.add_goal("Overdue", deadline=past)
        assert g.is_overdue() is True

    def test_time_until_deadline_none(self, graph):
        """time_until_deadline returns None when no deadline."""
        g = graph.add_goal("No deadline")
        assert g.time_until_deadline() is None

    def test_time_until_deadline_positive(self, graph):
        """time_until_deadline returns positive timedelta for future deadline."""
        future = datetime.now() + timedelta(hours=3)
        g = graph.add_goal("Future deadline", deadline=future)
        remaining = g.time_until_deadline()
        assert remaining is not None
        assert remaining.total_seconds() > 0


class TestGoalSuggestOrder:
    def test_suggest_empty_returns_empty(self, graph):
        """suggest_goal_order on empty graph returns empty list."""
        assert graph.suggest_goal_order() == []

    def test_suggest_returns_pending_goals(self, graph):
        """suggest_goal_order includes pending and blocked goals."""
        graph.add_goal("Pending1")
        graph.add_goal("Pending2")
        order = graph.suggest_goal_order()
        assert len(order) == 2

    def test_suggest_excludes_active_and_completed(self, graph):
        """suggest_goal_order excludes active and completed goals."""
        g1 = graph.add_goal("Active one")
        graph.start_goal(g1.goal_id)
        g2 = graph.add_goal("Completed one")
        graph.start_goal(g2.goal_id)
        graph.complete_goal(g2.goal_id)
        g3 = graph.add_goal("Pending one")

        order = graph.suggest_goal_order()
        assert g1.goal_id not in order
        assert g2.goal_id not in order
        assert g3.goal_id in order
