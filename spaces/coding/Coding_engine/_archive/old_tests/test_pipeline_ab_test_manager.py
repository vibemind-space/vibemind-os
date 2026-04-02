"""Test pipeline AB test manager."""
import sys
sys.path.insert(0, ".")
from src.services.pipeline_ab_test_manager import PipelineAbTestManager

def test_create():
    am = PipelineAbTestManager()
    eid = am.create_experiment("btn_color", ["red", "blue"], tags=["ui"])
    assert eid.startswith("exp-")
    e = am.get_experiment("btn_color")
    assert e["status"] == "draft"
    assert "red" in e["variants"]
    print("OK: create")

def test_invalid():
    am = PipelineAbTestManager()
    assert am.create_experiment("", ["a", "b"]) == ""
    assert am.create_experiment("x", ["a"]) == ""  # need 2+ variants
    print("OK: invalid")

def test_duplicate():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    assert am.create_experiment("e1", ["a", "b"]) == ""
    print("OK: duplicate")

def test_start_stop():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    assert am.start_experiment("e1") is True
    assert am.get_experiment("e1")["status"] == "running"
    assert am.start_experiment("e1") is False  # already running
    assert am.stop_experiment("e1") is True
    assert am.get_experiment("e1")["status"] == "completed"
    print("OK: start stop")

def test_record_impression():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    am.start_experiment("e1")
    assert am.record_impression("e1", "a") is True
    assert am.record_impression("e1", "nonexistent") is False
    print("OK: record impression")

def test_record_conversion():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    am.start_experiment("e1")
    am.record_impression("e1", "a")
    assert am.record_conversion("e1", "a") is True
    print("OK: record conversion")

def test_get_results():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["control", "variant"])
    am.start_experiment("e1")
    for _ in range(100):
        am.record_impression("e1", "control")
        am.record_impression("e1", "variant")
    for _ in range(10):
        am.record_conversion("e1", "control")
    for _ in range(20):
        am.record_conversion("e1", "variant")
    results = am.get_results("e1")
    assert results["winner"] == "variant"
    assert results["variants"]["control"]["conversion_rate"] == 10.0
    assert results["variants"]["variant"]["conversion_rate"] == 20.0
    print("OK: get results")

def test_assign_variant():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    am.start_experiment("e1")
    v = am.assign_variant("e1", "user123")
    assert v in ["a", "b"]
    # Deterministic
    v2 = am.assign_variant("e1", "user123")
    assert v == v2
    print("OK: assign variant")

def test_remove():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    assert am.remove_experiment("e1") is True
    assert am.remove_experiment("e1") is False
    print("OK: remove")

def test_list():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"], tags=["ui"])
    am.create_experiment("e2", ["a", "b"])
    am.start_experiment("e1")
    assert len(am.list_experiments()) == 2
    assert len(am.list_experiments(status="running")) == 1
    assert len(am.list_experiments(tag="ui")) == 1
    print("OK: list")

def test_history():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    am.start_experiment("e1")
    hist = am.get_history()
    assert len(hist) == 2
    print("OK: history")

def test_callback():
    am = PipelineAbTestManager()
    fired = []
    am.on_change("mon", lambda a, d: fired.append(a))
    am.create_experiment("e1", ["a", "b"])
    assert "experiment_created" in fired
    print("OK: callback")

def test_callbacks():
    am = PipelineAbTestManager()
    assert am.on_change("m", lambda a, d: None) is True
    assert am.on_change("m", lambda a, d: None) is False
    assert am.remove_callback("m") is True
    assert am.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    am.start_experiment("e1")
    stats = am.get_stats()
    assert stats["current_experiments"] == 1
    assert stats["running"] == 1
    print("OK: stats")

def test_reset():
    am = PipelineAbTestManager()
    am.create_experiment("e1", ["a", "b"])
    am.reset()
    assert am.list_experiments() == []
    print("OK: reset")

def main():
    print("=== Pipeline AB Test Manager Tests ===\n")
    test_create()
    test_invalid()
    test_duplicate()
    test_start_stop()
    test_record_impression()
    test_record_conversion()
    test_get_results()
    test_assign_variant()
    test_remove()
    test_list()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 15 TESTS PASSED ===")

if __name__ == "__main__":
    main()
