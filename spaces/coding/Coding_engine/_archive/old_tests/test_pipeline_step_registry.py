"""Test pipeline step registry -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_registry import PipelineStepRegistry


def test_register_step():
    sr = PipelineStepRegistry()
    sid = sr.register_step("transform", lambda ctx: {**ctx, "transformed": True}, description="Transform data", tags=["core"])
    assert len(sid) > 0
    s = sr.get_step("transform")
    assert s is not None
    assert s["name"] == "transform"
    assert sr.register_step("transform", lambda ctx: ctx) == ""  # dup
    print("OK: register step")


def test_execute_step():
    sr = PipelineStepRegistry()
    sr.register_step("add_key", lambda ctx: {**ctx, "added": True})
    result = sr.execute_step("add_key", {"initial": True})
    assert result["success"] is True
    assert result["result"]["added"] is True
    print("OK: execute step")


def test_execute_step_error():
    sr = PipelineStepRegistry()
    def bad_step(ctx):
        raise RuntimeError("boom")
    sr.register_step("bad", bad_step)
    result = sr.execute_step("bad", {})
    assert result["success"] is False
    assert len(result["error"]) > 0
    print("OK: execute step error")


def test_list_steps():
    sr = PipelineStepRegistry()
    sr.register_step("s1", lambda ctx: ctx, tags=["core"])
    sr.register_step("s2", lambda ctx: ctx)
    assert len(sr.list_steps()) == 2
    assert len(sr.list_steps(tag="core")) == 1
    print("OK: list steps")


def test_remove_step():
    sr = PipelineStepRegistry()
    sr.register_step("temp", lambda ctx: ctx)
    assert sr.remove_step("temp") is True
    assert sr.remove_step("temp") is False
    print("OK: remove step")


def test_execution_stats():
    sr = PipelineStepRegistry()
    sr.register_step("inc", lambda ctx: {**ctx, "n": ctx.get("n", 0) + 1})
    sr.execute_step("inc", {})
    sr.execute_step("inc", {"n": 5})
    stats = sr.get_execution_stats("inc")
    assert stats["call_count"] == 2
    assert stats["success_count"] == 2
    print("OK: execution stats")


def test_compose():
    sr = PipelineStepRegistry()
    sr.register_step("step_a", lambda ctx: {**ctx, "a": True})
    sr.register_step("step_b", lambda ctx: {**ctx, "b": True})
    cid = sr.compose(["step_a", "step_b"], "combined")
    assert len(cid) > 0
    result = sr.execute_step("combined", {})
    assert result["success"] is True
    # Composed steps return results list or merged context
    r = result["result"]
    if "results" in r:
        assert len(r["results"]) == 2
    else:
        assert r.get("a") is True or r.get("b") is True
    print("OK: compose")


def test_callbacks():
    sr = PipelineStepRegistry()
    fired = []
    sr.on_change("mon", lambda a, d: fired.append(a))
    sr.register_step("s1", lambda ctx: ctx)
    assert len(fired) >= 1
    assert sr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sr = PipelineStepRegistry()
    sr.register_step("s1", lambda ctx: ctx)
    stats = sr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sr = PipelineStepRegistry()
    sr.register_step("s1", lambda ctx: ctx)
    sr.reset()
    assert sr.list_steps() == []
    print("OK: reset")


def main():
    print("=== Pipeline Step Registry Tests ===\n")
    test_register_step()
    test_execute_step()
    test_execute_step_error()
    test_list_steps()
    test_remove_step()
    test_execution_stats()
    test_compose()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
