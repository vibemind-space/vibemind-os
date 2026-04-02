"""Test pipeline resource tracker."""
import sys
sys.path.insert(0, ".")
from src.services.pipeline_resource_tracker import PipelineResourceTracker

def test_register():
    rt = PipelineResourceTracker()
    rid = rt.register_resource("cpu_pool", resource_type="cpu", capacity=100.0, unit="cores", tags=["compute"])
    assert rid.startswith("res-")
    r = rt.get_resource("cpu_pool")
    assert r["capacity"] == 100.0
    assert rt.remove_resource("cpu_pool") is True
    assert rt.remove_resource("cpu_pool") is False
    print("OK: register")

def test_invalid():
    rt = PipelineResourceTracker()
    assert rt.register_resource("") == ""
    assert rt.register_resource("x", resource_type="invalid") == ""
    print("OK: invalid")

def test_duplicate():
    rt = PipelineResourceTracker()
    rt.register_resource("r1")
    assert rt.register_resource("r1") == ""
    print("OK: duplicate")

def test_max_resources():
    rt = PipelineResourceTracker(max_resources=2)
    rt.register_resource("a")
    rt.register_resource("b")
    assert rt.register_resource("c") == ""
    print("OK: max resources")

def test_allocate():
    rt = PipelineResourceTracker()
    rt.register_resource("r1", capacity=100.0)
    assert rt.allocate("r1", 30.0) is True
    r = rt.get_resource("r1")
    assert r["allocated"] == 30.0
    assert rt.allocate("r1", 80.0) is False  # over capacity
    print("OK: allocate")

def test_release():
    rt = PipelineResourceTracker()
    rt.register_resource("r1", capacity=100.0)
    rt.allocate("r1", 50.0)
    assert rt.release("r1", 20.0) is True
    assert rt.get_resource("r1")["allocated"] == 30.0
    print("OK: release")

def test_update_usage():
    rt = PipelineResourceTracker()
    rt.register_resource("r1", capacity=100.0)
    assert rt.update_usage("r1", 60.0) is True
    assert rt.get_resource("r1")["used"] == 60.0
    print("OK: update usage")

def test_utilization():
    rt = PipelineResourceTracker()
    rt.register_resource("r1", capacity=100.0)
    rt.update_usage("r1", 75.0)
    assert abs(rt.get_utilization("r1") - 75.0) < 0.01
    assert rt.get_utilization("nonexistent") == 0.0
    print("OK: utilization")

def test_threshold():
    rt = PipelineResourceTracker(threshold_pct=80.0)
    fired = []
    rt.on_change("mon", lambda a, d: fired.append(a))
    rt.register_resource("r1", capacity=100.0)
    rt.update_usage("r1", 85.0)
    assert "threshold_breached" in fired
    print("OK: threshold")

def test_over_threshold():
    rt = PipelineResourceTracker(threshold_pct=50.0)
    rt.register_resource("low", capacity=100.0)
    rt.register_resource("high", capacity=100.0)
    rt.update_usage("low", 30.0)
    rt.update_usage("high", 60.0)
    over = rt.get_over_threshold()
    assert len(over) == 1
    assert over[0]["name"] == "high"
    print("OK: over threshold")

def test_list_resources():
    rt = PipelineResourceTracker()
    rt.register_resource("r1", resource_type="cpu", tags=["compute"])
    rt.register_resource("r2", resource_type="memory")
    assert len(rt.list_resources()) == 2
    assert len(rt.list_resources(resource_type="cpu")) == 1
    assert len(rt.list_resources(tag="compute")) == 1
    print("OK: list resources")

def test_history():
    rt = PipelineResourceTracker()
    rt.register_resource("r1", capacity=100.0)
    rt.allocate("r1", 10.0)
    rt.release("r1", 5.0)
    hist = rt.get_history()
    assert len(hist) == 2
    limited = rt.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")

def test_callbacks():
    rt = PipelineResourceTracker()
    assert rt.on_change("m", lambda a, d: None) is True
    assert rt.on_change("m", lambda a, d: None) is False
    assert rt.remove_callback("m") is True
    assert rt.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    rt = PipelineResourceTracker()
    rt.register_resource("r1", capacity=100.0)
    rt.allocate("r1", 10.0)
    stats = rt.get_stats()
    assert stats["current_resources"] == 1
    assert stats["total_allocations"] == 1
    print("OK: stats")

def test_reset():
    rt = PipelineResourceTracker()
    rt.register_resource("r1")
    rt.reset()
    assert rt.list_resources() == []
    assert rt.get_stats()["current_resources"] == 0
    print("OK: reset")

def main():
    print("=== Pipeline Resource Tracker Tests ===\n")
    test_register()
    test_invalid()
    test_duplicate()
    test_max_resources()
    test_allocate()
    test_release()
    test_update_usage()
    test_utilization()
    test_threshold()
    test_over_threshold()
    test_list_resources()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")

if __name__ == "__main__":
    main()
