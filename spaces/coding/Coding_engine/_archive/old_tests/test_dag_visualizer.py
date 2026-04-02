"""Test pipeline DAG visualizer."""
import sys
sys.path.insert(0, ".")

from src.services.dag_visualizer import DAGVisualizer, _colorize, Color


def test_pipeline_dag():
    """Pipeline DAG renders phases vertically."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_pipeline_dag(
        phases=["planning", "generation", "testing", "deployment"],
        status={
            "planning": "completed",
            "generation": "running",
            "testing": "pending",
            "deployment": "pending",
        },
    )
    assert "planning" in result
    assert "generation" in result
    assert "testing" in result
    assert "deployment" in result
    assert "completed" in result
    assert "running" in result
    assert "|" in result
    assert "v" in result
    print("OK: pipeline DAG")


def test_pipeline_dag_empty():
    """Empty pipeline shows message."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_pipeline_dag([])
    assert "empty" in result.lower()
    print("OK: empty pipeline DAG")


def test_wait_graph():
    """Wait-for graph renders agent dependencies."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_wait_graph({
        "Frontend": ["Backend", "Database"],
        "Backend": ["Database"],
    })
    assert "Frontend" in result
    assert "Backend" in result
    assert "Database" in result
    assert "waits for" in result
    assert "(free)" in result  # Database waits for nobody
    print("OK: wait graph")


def test_wait_graph_empty():
    """Empty wait graph shows message."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_wait_graph({})
    assert "no active" in result.lower()
    print("OK: empty wait graph")


def test_build_order():
    """Build order renders parallelizable batches."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_build_order([
        ["core-lib", "utils"],
        ["api-server", "web-client"],
        ["integration-tests"],
    ])
    assert "Level 0" in result
    assert "Level 1" in result
    assert "Level 2" in result
    assert "core-lib" in result
    assert "api-server" in result
    assert "5 packages in 3 levels" in result
    print("OK: build order")


def test_build_order_empty():
    """Empty build order shows message."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_build_order([])
    assert "no build" in result.lower()
    print("OK: empty build order")


def test_execution_timeline():
    """Execution timeline renders events."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_execution_timeline([
        {"time": 0.0, "agent": "Planner", "action": "started planning", "status": "running"},
        {"time": 2.5, "agent": "Planner", "action": "plan complete", "status": "completed"},
        {"time": 3.0, "agent": "Builder", "action": "started building", "status": "running"},
        {"time": 10.0, "agent": "Builder", "action": "build failed", "status": "failed"},
    ])
    assert "Planner" in result
    assert "Builder" in result
    assert "started planning" in result
    assert "build failed" in result
    print("OK: execution timeline")


def test_execution_timeline_empty():
    """Empty timeline shows message."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_execution_timeline([])
    assert "no events" in result.lower()
    print("OK: empty execution timeline")


def test_dependency_tree():
    """Dependency tree renders hierarchy."""
    viz = DAGVisualizer(use_color=False)
    children = {
        "app": ["api", "web"],
        "api": ["core", "db"],
        "web": ["core"],
        "core": [],
        "db": [],
    }
    result = viz.render_dependency_tree("app", children)
    assert "app" in result
    assert "api" in result
    assert "web" in result
    assert "core" in result
    assert "db" in result
    print("OK: dependency tree")


def test_system_overview():
    """System overview dashboard renders."""
    viz = DAGVisualizer(use_color=False)
    result = viz.render_system_overview(
        services={
            "EventBus": True,
            "Minibook": True,
            "WebSocket": False,
            "OpenClaw": True,
        },
        agents=[
            {"agent_name": "Frontend", "availability": "online", "current_tasks": 0},
            {"agent_name": "Backend", "availability": "busy", "current_tasks": 2},
            {"agent_name": "Tester", "availability": "offline", "current_tasks": 0},
        ],
        metrics={"total_tokens": 50000, "total_cost_usd": 0.45},
    )
    assert "System Overview" in result
    assert "EventBus" in result
    assert "Frontend" in result
    assert "Backend" in result
    assert "50000" in result
    print("OK: system overview")


def test_colorize():
    """Color function works with and without color."""
    colored = _colorize("test", Color.GREEN, use_color=True)
    assert "\033[32m" in colored
    assert "test" in colored

    plain = _colorize("test", Color.GREEN, use_color=False)
    assert plain == "test"
    print("OK: colorize")


def test_box_rendering():
    """Box rendering for phases."""
    viz = DAGVisualizer(use_color=False, box_width=20)
    lines = viz._render_box("planning", "completed")
    assert len(lines) == 4
    assert "+" in lines[0]
    assert "planning" in lines[1]
    assert "completed" in lines[2]
    print("OK: box rendering")


def test_legend():
    """Legend contains all statuses."""
    viz = DAGVisualizer(use_color=False)
    legend = viz._legend()
    assert "completed" in legend
    assert "running" in legend
    assert "pending" in legend
    assert "failed" in legend
    print("OK: legend")


def main():
    print("=== DAG Visualizer Tests ===\n")
    test_pipeline_dag()
    test_pipeline_dag_empty()
    test_wait_graph()
    test_wait_graph_empty()
    test_build_order()
    test_build_order_empty()
    test_execution_timeline()
    test_execution_timeline_empty()
    test_dependency_tree()
    test_system_overview()
    test_colorize()
    test_box_rendering()
    test_legend()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
