"""Test pipeline integration bus — unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_integration_bus import PipelineIntegrationBus


def test_register_chain():
    bus = PipelineIntegrationBus()
    cid = bus.register_chain("auth", tags=["security"])
    assert cid.startswith("chn-")
    c = bus.get_chain("auth")
    assert c["name"] == "auth"
    assert c["step_count"] == 0
    assert bus.register_chain("auth") == ""  # dup
    assert bus.remove_chain("auth") is True
    assert bus.remove_chain("auth") is False
    print("OK: register chain")


def test_max_chains():
    bus = PipelineIntegrationBus(max_chains=2)
    bus.register_chain("a")
    bus.register_chain("b")
    assert bus.register_chain("c") == ""
    print("OK: max chains")


def test_add_step():
    bus = PipelineIntegrationBus()
    bus.register_chain("auth")
    assert bus.add_step("auth", "token", lambda ctx: ctx, "token_manager") is True
    assert bus.add_step("auth", "token", lambda ctx: ctx) is False  # dup
    assert bus.add_step("nonexistent", "s", lambda ctx: ctx) is False
    c = bus.get_chain("auth")
    assert c["step_count"] == 1
    print("OK: add step")


def test_execute_success():
    bus = PipelineIntegrationBus()
    bus.register_chain("math")
    bus.add_step("math", "add_ten", lambda ctx: {**ctx, "val": ctx.get("val", 0) + 10})
    bus.add_step("math", "double", lambda ctx: {**ctx, "val": ctx["val"] * 2})

    result = bus.execute("math", {"val": 5})
    assert result["success"] is True
    assert result["steps_completed"] == 2
    assert result["context"]["val"] == 30  # (5+10)*2
    assert result["duration"] >= 0
    print("OK: execute success")


def test_execute_failure():
    bus = PipelineIntegrationBus()
    bus.register_chain("fail")
    bus.add_step("fail", "ok", lambda ctx: ctx)
    bus.add_step("fail", "boom", lambda ctx: (_ for _ in ()).throw(RuntimeError("kaboom")))
    bus.add_step("fail", "never", lambda ctx: ctx)

    result = bus.execute("fail", {})
    assert result["success"] is False
    assert result["steps_completed"] == 1
    assert result["failed_step"] == "boom"
    assert "kaboom" in result["error"]
    print("OK: execute failure")


def test_execute_nonexistent():
    bus = PipelineIntegrationBus()
    result = bus.execute("nonexistent")
    assert result["success"] is False
    print("OK: execute nonexistent")


def test_execute_empty_chain():
    bus = PipelineIntegrationBus()
    bus.register_chain("empty")
    result = bus.execute("empty")
    assert result["success"] is False
    assert result["error"] == "chain_empty"
    print("OK: execute empty chain")


def test_execute_step():
    bus = PipelineIntegrationBus()
    bus.register_chain("c1")
    bus.add_step("c1", "double", lambda ctx: {**ctx, "val": ctx.get("val", 0) * 2})

    result = bus.execute_step("c1", "double", {"val": 7})
    assert result["success"] is True
    assert result["context"]["val"] == 14

    result = bus.execute_step("c1", "nonexistent")
    assert result["success"] is False
    print("OK: execute step")


def test_context_flows_through():
    """Context accumulates through chain steps."""
    bus = PipelineIntegrationBus()
    bus.register_chain("flow")
    bus.add_step("flow", "s1", lambda ctx: {**ctx, "a": 1})
    bus.add_step("flow", "s2", lambda ctx: {**ctx, "b": ctx["a"] + 1})
    bus.add_step("flow", "s3", lambda ctx: {**ctx, "c": ctx["b"] + 1})

    result = bus.execute("flow", {})
    assert result["success"] is True
    assert result["context"]["a"] == 1
    assert result["context"]["b"] == 2
    assert result["context"]["c"] == 3
    print("OK: context flows through")


def test_list_chains():
    bus = PipelineIntegrationBus()
    bus.register_chain("auth", tags=["sec"])
    bus.register_chain("exec")
    assert len(bus.list_chains()) == 2
    assert len(bus.list_chains(tag="sec")) == 1
    assert sorted(bus.get_chain_names()) == ["auth", "exec"]
    print("OK: list chains")


def test_history():
    bus = PipelineIntegrationBus()
    bus.register_chain("c1")
    bus.add_step("c1", "s1", lambda ctx: ctx)
    bus.execute("c1", {})

    hist = bus.get_history()
    assert len(hist) >= 2  # step_completed + chain_completed

    by_chain = bus.get_history(chain_name="c1")
    assert len(by_chain) >= 2

    by_action = bus.get_history(action="chain_completed")
    assert len(by_action) == 1

    limited = bus.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    bus = PipelineIntegrationBus()
    fired = []
    bus.on_change("mon", lambda a, d: fired.append(a))

    bus.register_chain("c1")
    assert "chain_registered" in fired

    bus.add_step("c1", "s1", lambda ctx: ctx)
    bus.execute("c1", {})
    assert "chain_started" in fired
    assert "chain_completed" in fired
    print("OK: callback")


def test_callbacks():
    bus = PipelineIntegrationBus()
    assert bus.on_change("m", lambda a, d: None) is True
    assert bus.on_change("m", lambda a, d: None) is False
    assert bus.remove_callback("m") is True
    assert bus.remove_callback("m") is False
    print("OK: callbacks")


def test_stats():
    bus = PipelineIntegrationBus()
    bus.register_chain("c1")
    bus.add_step("c1", "s1", lambda ctx: ctx)
    bus.add_step("c1", "s2", lambda ctx: ctx)
    bus.execute("c1", {})

    stats = bus.get_stats()
    assert stats["total_chains"] == 1
    assert stats["total_executions"] == 1
    assert stats["total_step_executions"] == 2
    assert stats["total_failures"] == 0
    print("OK: stats")


def test_reset():
    bus = PipelineIntegrationBus()
    bus.register_chain("c1")
    bus.reset()
    assert bus.list_chains() == []
    assert bus.get_stats()["total_chains"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Integration Bus Tests ===\n")
    test_register_chain()
    test_max_chains()
    test_add_step()
    test_execute_success()
    test_execute_failure()
    test_execute_nonexistent()
    test_execute_empty_chain()
    test_execute_step()
    test_context_flows_through()
    test_list_chains()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")


if __name__ == "__main__":
    main()
