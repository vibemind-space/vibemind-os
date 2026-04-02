"""Tests for PipelineStepHook service."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_hook import PipelineStepHook


def test_register_hook():
    svc = PipelineStepHook()
    hid = svc.register_hook("p1", "step_a", "pre", lambda ctx: None, label="my hook")
    assert hid.startswith("psh-")
    assert len(svc._state.hooks) == 1
    entry = svc._state.hooks[hid]
    assert entry["pipeline_id"] == "p1"
    assert entry["step_name"] == "step_a"
    assert entry["hook_type"] == "pre"
    assert entry["label"] == "my hook"
    print("PASSED test_register_hook")


def test_remove_hook():
    svc = PipelineStepHook()
    hid = svc.register_hook("p1", "step_a", "pre")
    assert svc.remove_hook(hid) is True
    assert svc.remove_hook(hid) is False
    assert len(svc._state.hooks) == 0
    print("PASSED test_remove_hook")


def test_get_hooks():
    svc = PipelineStepHook()
    svc.register_hook("p1", "step_a", "pre")
    svc.register_hook("p1", "step_b", "post")
    svc.register_hook("p2", "step_a", "pre")
    hooks = svc.get_hooks("p1")
    assert len(hooks) == 2
    hooks2 = svc.get_hooks("p2")
    assert len(hooks2) == 1
    print("PASSED test_get_hooks")


def test_get_hooks_filtered():
    svc = PipelineStepHook()
    svc.register_hook("p1", "step_a", "pre")
    svc.register_hook("p1", "step_a", "post")
    svc.register_hook("p1", "step_b", "pre")
    # Filter by step_name
    hooks = svc.get_hooks("p1", step_name="step_a")
    assert len(hooks) == 2
    # Filter by hook_type
    hooks = svc.get_hooks("p1", hook_type="pre")
    assert len(hooks) == 2
    # Filter by both
    hooks = svc.get_hooks("p1", step_name="step_a", hook_type="post")
    assert len(hooks) == 1
    print("PASSED test_get_hooks_filtered")


def test_execute_hooks():
    svc = PipelineStepHook()
    results = []
    svc.register_hook("p1", "s1", "pre", lambda ctx: results.append(ctx.get("val")))
    svc.register_hook("p1", "s1", "pre", lambda ctx: results.append(ctx.get("val") * 2))
    # Hook with None fn should be skipped
    svc.register_hook("p1", "s1", "pre", None)
    count = svc.execute_hooks("p1", "s1", "pre", {"val": 5})
    assert count == 2
    assert results == [5, 10]
    print("PASSED test_execute_hooks")


def test_execute_hooks_pre_post():
    svc = PipelineStepHook()
    order = []
    svc.register_hook("p1", "s1", "pre", lambda ctx: order.append("pre"))
    svc.register_hook("p1", "s1", "post", lambda ctx: order.append("post"))
    svc.execute_hooks("p1", "s1", "pre")
    svc.execute_hooks("p1", "s1", "post")
    assert order == ["pre", "post"]
    print("PASSED test_execute_hooks_pre_post")


def test_get_hook_count():
    svc = PipelineStepHook()
    assert svc.get_hook_count() == 0
    svc.register_hook("p1", "s1", "pre")
    svc.register_hook("p1", "s2", "post")
    svc.register_hook("p2", "s1", "pre")
    assert svc.get_hook_count() == 3
    assert svc.get_hook_count("p1") == 2
    assert svc.get_hook_count("p2") == 1
    assert svc.get_hook_count("p3") == 0
    print("PASSED test_get_hook_count")


def test_list_pipelines():
    svc = PipelineStepHook()
    assert svc.list_pipelines() == []
    svc.register_hook("beta", "s1", "pre")
    svc.register_hook("alpha", "s1", "pre")
    svc.register_hook("beta", "s2", "post")
    assert svc.list_pipelines() == ["alpha", "beta"]
    print("PASSED test_list_pipelines")


def test_callbacks():
    svc = PipelineStepHook()
    events = []
    svc.on_change("cb1", lambda action, detail: events.append((action, detail.get("hook_id", ""))))
    svc.register_hook("p1", "s1", "pre")
    assert len(events) == 1
    assert events[0][0] == "register_hook"
    assert events[0][1].startswith("psh-")
    # remove_callback returns True/False
    assert svc.remove_callback("cb1") is True
    assert svc.remove_callback("cb1") is False
    print("PASSED test_callbacks")


def test_stats():
    svc = PipelineStepHook()
    svc.register_hook("p1", "s1", "pre")
    svc.register_hook("p2", "s1", "post")
    svc.on_change("cb", lambda a, d: None)
    stats = svc.get_stats()
    assert stats["total_hooks"] == 2
    assert stats["pipelines"] == 2
    assert stats["callbacks"] == 1
    assert stats["max_entries"] == 10000
    print("PASSED test_stats")


def test_reset():
    svc = PipelineStepHook()
    svc.register_hook("p1", "s1", "pre")
    svc.on_change("cb", lambda a, d: None)
    svc.reset()
    assert svc.get_hook_count() == 0
    assert svc.get_stats()["callbacks"] == 0
    assert svc._state._seq == 0
    print("PASSED test_reset")


if __name__ == "__main__":
    test_register_hook()
    test_remove_hook()
    test_get_hooks()
    test_get_hooks_filtered()
    test_execute_hooks()
    test_execute_hooks_pre_post()
    test_get_hook_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("=== ALL 11 TESTS PASSED ===")
