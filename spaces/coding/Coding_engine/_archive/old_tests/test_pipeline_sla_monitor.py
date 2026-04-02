"""Test pipeline SLA monitor -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_sla_monitor import PipelineSlaMonitor


def test_define_sla():
    sm = PipelineSlaMonitor()
    sid = sm.define_sla("deploy", "latency_ms", 500.0)
    assert len(sid) > 0
    assert sid.startswith("psm-")
    # Duplicate returns ""
    assert sm.define_sla("deploy", "latency_ms", 500.0) == ""
    print("OK: define SLA")


def test_get_sla():
    sm = PipelineSlaMonitor()
    sid = sm.define_sla("deploy", "latency_ms", 500.0)
    sla = sm.get_sla(sid)
    assert sla is not None
    assert sla["pipeline_id"] == "deploy"
    assert sla["metric_name"] == "latency_ms"
    assert sla["threshold"] == 500.0
    assert sla["status"] == "compliant"
    assert sm.get_sla("nonexistent") is None
    print("OK: get SLA")


def test_get_sla_by_name():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0)
    sla = sm.get_sla_by_name("deploy", "latency_ms")
    assert sla is not None
    assert sla["metric_name"] == "latency_ms"
    assert sm.get_sla_by_name("deploy", "nonexistent") is None
    print("OK: get SLA by name")


def test_record_metric_compliant():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0, comparison="lte")
    result = sm.record_metric("deploy", "latency_ms", 300.0)
    assert result["compliant"] is True
    assert result["value"] == 300.0
    print("OK: record metric compliant")


def test_record_metric_violated():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0, comparison="lte")
    result = sm.record_metric("deploy", "latency_ms", 600.0)
    assert result["compliant"] is False
    sla = sm.get_sla_by_name("deploy", "latency_ms")
    assert sla["status"] == "violated"
    assert sla["violations"] >= 1
    print("OK: record metric violated")


def test_record_metric_gte():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "uptime_pct", 99.0, comparison="gte")
    result = sm.record_metric("deploy", "uptime_pct", 99.5)
    assert result["compliant"] is True
    result2 = sm.record_metric("deploy", "uptime_pct", 98.0)
    assert result2["compliant"] is False
    print("OK: record metric gte")


def test_get_violations():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0)
    sm.define_sla("deploy", "error_rate", 0.05)
    sm.record_metric("deploy", "latency_ms", 600.0)  # Violated
    violations = sm.get_violations()
    assert len(violations) == 1
    violations_deploy = sm.get_violations(pipeline_id="deploy")
    assert len(violations_deploy) == 1
    print("OK: get violations")


def test_get_compliance_rate():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0)
    sm.define_sla("deploy", "error_rate", 0.05)
    sm.record_metric("deploy", "latency_ms", 600.0)  # Violated
    rate = sm.get_compliance_rate("deploy")
    assert rate == 0.5
    print("OK: get compliance rate")


def test_delete_sla():
    sm = PipelineSlaMonitor()
    sid = sm.define_sla("deploy", "latency_ms", 500.0)
    assert sm.delete_sla(sid) is True
    assert sm.delete_sla(sid) is False
    print("OK: delete SLA")


def test_list_pipelines():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0)
    sm.define_sla("build", "duration_s", 300.0)
    pipes = sm.list_pipelines()
    assert "deploy" in pipes
    assert "build" in pipes
    print("OK: list pipelines")


def test_get_pipeline_slas():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0)
    sm.define_sla("deploy", "error_rate", 0.05)
    slas = sm.get_pipeline_slas("deploy")
    assert len(slas) == 2
    print("OK: get pipeline SLAs")


def test_callbacks():
    sm = PipelineSlaMonitor()
    fired = []
    sm.on_change("mon", lambda a, d: fired.append(a))
    sm.define_sla("deploy", "latency_ms", 500.0)
    assert len(fired) >= 1
    assert sm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0)
    stats = sm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sm = PipelineSlaMonitor()
    sm.define_sla("deploy", "latency_ms", 500.0)
    sm.reset()
    assert sm.get_sla_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline SLA Monitor Tests ===\n")
    test_define_sla()
    test_get_sla()
    test_get_sla_by_name()
    test_record_metric_compliant()
    test_record_metric_violated()
    test_record_metric_gte()
    test_get_violations()
    test_get_compliance_rate()
    test_delete_sla()
    test_list_pipelines()
    test_get_pipeline_slas()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()
