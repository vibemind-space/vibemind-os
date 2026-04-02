"""Test pipeline stage orchestrator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_stage_orchestrator import PipelineStageOrchestrator


def test_create_pipeline():
    so = PipelineStageOrchestrator()
    pid = so.create_pipeline("build", tags=["ci"])
    assert pid.startswith("opl-")
    p = so.get_pipeline("build")
    assert p["name"] == "build"
    assert p["stage_count"] == 0
    assert so.create_pipeline("build") == ""  # dup
    print("OK: create pipeline")


def test_add_stage():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    sid = so.add_stage("build", "compile", handler=lambda ctx: {**ctx, "compiled": True})
    assert sid.startswith("ost-")
    assert so.add_stage("build", "compile") == ""  # dup
    p = so.get_pipeline("build")
    assert p["stage_count"] == 1
    print("OK: add stage")


def test_add_dependency():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    so.add_stage("build", "compile")
    so.add_stage("build", "test")
    assert so.add_dependency("build", "test", "compile") is True
    assert so.add_dependency("build", "test", "compile") is False  # dup
    print("OK: add dependency")


def test_execution_order():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    so.add_stage("build", "lint")
    so.add_stage("build", "compile")
    so.add_stage("build", "test")
    so.add_stage("build", "deploy")
    so.add_dependency("build", "compile", "lint")
    so.add_dependency("build", "test", "compile")
    so.add_dependency("build", "deploy", "test")
    order = so.get_execution_order("build")
    assert len(order) >= 1
    # lint should be in first wave
    assert "lint" in order[0]
    # deploy should be in last wave
    assert "deploy" in order[-1]
    print("OK: execution order")


def test_parallel_waves():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    so.add_stage("build", "lint")
    so.add_stage("build", "typecheck")
    so.add_stage("build", "test")
    # lint and typecheck are independent -> same wave
    so.add_dependency("build", "test", "lint")
    so.add_dependency("build", "test", "typecheck")
    order = so.get_execution_order("build")
    # first wave should have both lint and typecheck
    assert len(order[0]) == 2
    assert set(order[0]) == {"lint", "typecheck"}
    assert order[1] == ["test"]
    print("OK: parallel waves")


def test_execute():
    so = PipelineStageOrchestrator()
    so.create_pipeline("math")
    so.add_stage("math", "add", handler=lambda ctx: {**ctx, "val": ctx.get("val", 0) + 10})
    so.add_stage("math", "double", handler=lambda ctx: {**ctx, "val": ctx["val"] * 2})
    so.add_dependency("math", "double", "add")
    result = so.execute("math", {"val": 5})
    assert result["success"] is True
    assert result["stages_completed"] == 2
    assert result["results"]["double"]["val"] == 30  # (5+10)*2
    print("OK: execute")


def test_execute_failure():
    so = PipelineStageOrchestrator()
    so.create_pipeline("fail")
    so.add_stage("fail", "ok", handler=lambda ctx: ctx)
    so.add_stage("fail", "boom", handler=lambda ctx: (_ for _ in ()).throw(RuntimeError("kaboom")))
    so.add_dependency("fail", "boom", "ok")
    result = so.execute("fail", {})
    assert result["success"] is False
    assert "kaboom" in result.get("error", "")
    print("OK: execute failure")


def test_get_stage():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    so.add_stage("build", "compile", tags=["core"])
    s = so.get_stage("build", "compile")
    assert s is not None
    assert s["stage_name"] == "compile"
    print("OK: get stage")


def test_list_pipelines():
    so = PipelineStageOrchestrator()
    so.create_pipeline("a", tags=["ci"])
    so.create_pipeline("b")
    assert len(so.list_pipelines()) == 2
    assert len(so.list_pipelines(tag="ci")) == 1
    print("OK: list pipelines")


def test_list_stages():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    so.add_stage("build", "a")
    so.add_stage("build", "b")
    assert len(so.list_stages("build")) == 2
    print("OK: list stages")


def test_remove_pipeline():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    assert so.remove_pipeline("build") is True
    assert so.remove_pipeline("build") is False
    print("OK: remove pipeline")


def test_history():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    so.add_stage("build", "s1")
    hist = so.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    so = PipelineStageOrchestrator()
    fired = []
    so.on_change("mon", lambda a, d: fired.append(a))
    so.create_pipeline("build")
    assert len(fired) >= 1
    assert so.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    stats = so.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    so = PipelineStageOrchestrator()
    so.create_pipeline("build")
    so.reset()
    assert so.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Stage Orchestrator Tests ===\n")
    test_create_pipeline()
    test_add_stage()
    test_add_dependency()
    test_execution_order()
    test_parallel_waves()
    test_execute()
    test_execute_failure()
    test_get_stage()
    test_list_pipelines()
    test_list_stages()
    test_remove_pipeline()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")


if __name__ == "__main__":
    main()
