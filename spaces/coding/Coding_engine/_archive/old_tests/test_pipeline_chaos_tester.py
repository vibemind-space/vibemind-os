"""Test pipeline chaos tester -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_chaos_tester import PipelineChaosTester


def test_register_target():
    ct = PipelineChaosTester()
    tid = ct.register_target("api_gateway", target_type="service")
    assert tid.startswith("ctg-")
    t = ct.list_targets()
    assert len(t) == 1
    assert t[0]["name"] == "api_gateway"
    assert ct.register_target("api_gateway") == ""  # dup
    print("OK: register target")


def test_create_experiment():
    ct = PipelineChaosTester()
    ct.register_target("api_gw")
    eid = ct.create_experiment("chaos1", target="api_gw", chaos_type="error", intensity=75.0)
    assert eid.startswith("cex-")
    e = ct.get_experiment("chaos1")
    assert e["name"] == "chaos1"
    assert e["chaos_type"] == "error"
    assert e["intensity"] == 75.0
    assert e["status"] == "created"
    assert ct.create_experiment("chaos1", target="api_gw") == ""  # dup
    print("OK: create experiment")


def test_start_stop():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc")
    assert ct.start_experiment("exp1") is True
    assert ct.get_experiment("exp1")["status"] == "running"
    assert ct.stop_experiment("exp1") is True
    assert ct.get_experiment("exp1")["status"] == "stopped"
    print("OK: start stop")


def test_inject_fault_error():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc", chaos_type="error")
    ct.start_experiment("exp1")
    result = ct.inject_fault("exp1")
    assert result["injected"] is True
    assert result["type"] == "error"
    print("OK: inject fault error")


def test_inject_fault_latency():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc", chaos_type="latency", intensity=200.0)
    ct.start_experiment("exp1")
    result = ct.inject_fault("exp1")
    assert result["injected"] is True
    assert result["type"] == "latency"
    assert "added_ms" in result
    print("OK: inject fault latency")


def test_record_observation():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc")
    ct.start_experiment("exp1")
    oid = ct.record_observation("exp1", "response_time", 150.0)
    assert oid.startswith("cob-")
    print("OK: record observation")


def test_experiment_report():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc", chaos_type="error")
    ct.start_experiment("exp1")
    ct.inject_fault("exp1")
    ct.inject_fault("exp1")
    ct.record_observation("exp1", "latency", 100.0)
    ct.record_observation("exp1", "latency", 200.0)
    report = ct.get_experiment_report("exp1")
    assert report["total_faults"] == 2
    assert report["total_observations"] == 2
    assert report["mean_observation_value"] == 150.0
    assert 0 <= report["resilience_score"] <= 100
    print("OK: experiment report")


def test_list_experiments():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc", chaos_type="error")
    ct.create_experiment("exp2", target="svc", chaos_type="latency")
    assert len(ct.list_experiments()) == 2
    assert len(ct.list_experiments(chaos_type="error")) == 1
    ct.start_experiment("exp1")
    assert len(ct.list_experiments(status="running")) == 1
    print("OK: list experiments")


def test_remove_experiment():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc")
    assert ct.remove_experiment("exp1") is True
    assert ct.remove_experiment("exp1") is False
    print("OK: remove experiment")


def test_list_targets():
    ct = PipelineChaosTester()
    ct.register_target("a", target_type="stage")
    ct.register_target("b", target_type="service")
    assert len(ct.list_targets()) == 2
    assert len(ct.list_targets(target_type="stage")) == 1
    print("OK: list targets")


def test_history():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc")
    hist = ct.get_history()
    assert len(hist) >= 2
    print("OK: history")


def test_callbacks():
    ct = PipelineChaosTester()
    fired = []
    ct.on_change("mon", lambda a, d: fired.append(a))
    ct.register_target("svc")
    assert "target_registered" in fired
    assert ct.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc")
    stats = ct.get_stats()
    assert stats["current_targets"] >= 1
    assert stats["total_experiments_created"] >= 1
    print("OK: stats")


def test_reset():
    ct = PipelineChaosTester()
    ct.register_target("svc")
    ct.create_experiment("exp1", target="svc")
    ct.reset()
    assert ct.list_experiments() == []
    assert ct.list_targets() == []
    print("OK: reset")


def main():
    print("=== Pipeline Chaos Tester Tests ===\n")
    test_register_target()
    test_create_experiment()
    test_start_stop()
    test_inject_fault_error()
    test_inject_fault_latency()
    test_record_observation()
    test_experiment_report()
    test_list_experiments()
    test_remove_experiment()
    test_list_targets()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()
