"""Test pipeline health probe -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_health_probe import PipelineHealthProbe


def test_register_probe():
    hp = PipelineHealthProbe()
    pid = hp.register_probe("pipeline-1", check_interval=60, timeout=10)
    assert len(pid) > 0
    assert pid.startswith("php-")
    print("OK: register probe")


def test_get_probe():
    hp = PipelineHealthProbe()
    pid = hp.register_probe("pipeline-1", check_interval=30)
    probe = hp.get_probe(pid)
    assert probe is not None
    assert probe["pipeline_id"] == "pipeline-1"
    assert probe["check_interval"] == 30
    assert hp.get_probe("nonexistent") is None
    print("OK: get probe")


def test_record_check():
    hp = PipelineHealthProbe()
    hp.register_probe("pipeline-1")
    result = hp.record_check("pipeline-1", healthy=True, latency=50.0)
    assert result is not None
    print("OK: record check")


def test_get_health_status():
    hp = PipelineHealthProbe()
    hp.register_probe("pipeline-1")
    assert hp.get_health_status("pipeline-1") == "unknown"
    hp.record_check("pipeline-1", healthy=True)
    assert hp.get_health_status("pipeline-1") == "healthy"
    hp.record_check("pipeline-1", healthy=False)
    assert hp.get_health_status("pipeline-1") == "unhealthy"
    print("OK: get health status")


def test_get_check_history():
    hp = PipelineHealthProbe()
    hp.register_probe("pipeline-1")
    hp.record_check("pipeline-1", healthy=True, latency=10.0)
    hp.record_check("pipeline-1", healthy=True, latency=15.0)
    history = hp.get_check_history("pipeline-1")
    assert len(history) == 2
    print("OK: get check history")


def test_get_uptime():
    hp = PipelineHealthProbe()
    hp.register_probe("pipeline-1")
    hp.record_check("pipeline-1", healthy=True)
    hp.record_check("pipeline-1", healthy=True)
    hp.record_check("pipeline-1", healthy=False)
    uptime = hp.get_uptime("pipeline-1")
    assert abs(uptime - 66.67) < 1.0  # ~66.67%
    print("OK: get uptime")


def test_remove_probe():
    hp = PipelineHealthProbe()
    pid = hp.register_probe("pipeline-1")
    assert hp.remove_probe(pid) is True
    assert hp.remove_probe(pid) is False
    print("OK: remove probe")


def test_list_pipelines():
    hp = PipelineHealthProbe()
    hp.register_probe("pipeline-1")
    hp.register_probe("pipeline-2")
    pipelines = hp.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    hp = PipelineHealthProbe()
    fired = []
    cb = lambda *args: fired.append("fired")
    hp.on_change(cb)
    hp.register_probe("pipeline-1")
    hp.record_check("pipeline-1", healthy=True)
    assert len(fired) >= 1
    hp.remove_callback(cb)
    print("OK: callbacks")


def test_stats():
    hp = PipelineHealthProbe()
    hp.register_probe("pipeline-1")
    stats = hp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    hp = PipelineHealthProbe()
    hp.register_probe("pipeline-1")
    hp.reset()
    assert hp.get_probe_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Health Probe Tests ===\n")
    test_register_probe()
    test_get_probe()
    test_record_check()
    test_get_health_status()
    test_get_check_history()
    test_get_uptime()
    test_remove_probe()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
