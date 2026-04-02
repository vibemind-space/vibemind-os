"""Test pipeline data flow tracker."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_flow_tracker import PipelineDataFlowTracker


def test_create_flow():
    """Create and retrieve flow."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("etl_flow", source="extractor", target="loader",
                         data_type="event", tags=["core"])
    assert fid.startswith("flow-")

    f = dt.get_flow(fid)
    assert f is not None
    assert f["name"] == "etl_flow"
    assert f["source"] == "extractor"
    assert f["target"] == "loader"
    assert f["data_type"] == "event"
    assert f["status"] == "active"

    assert dt.remove_flow(fid) is True
    assert dt.remove_flow(fid) is False
    print("OK: create flow")


def test_invalid_flow():
    """Invalid flow rejected."""
    dt = PipelineDataFlowTracker()
    assert dt.create_flow("") == ""
    assert dt.create_flow("x", data_type="invalid") == ""
    print("OK: invalid flow")


def test_max_flows():
    """Max flows enforced."""
    dt = PipelineDataFlowTracker(max_flows=2)
    dt.create_flow("a")
    dt.create_flow("b")
    assert dt.create_flow("c") == ""
    print("OK: max flows")


def test_pause_resume():
    """Pause and resume flow."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")

    assert dt.pause_flow(fid) is True
    assert dt.get_flow(fid)["status"] == "paused"
    assert dt.pause_flow(fid) is False

    assert dt.resume_flow(fid) is True
    assert dt.get_flow(fid)["status"] == "active"
    assert dt.resume_flow(fid) is False
    print("OK: pause resume")


def test_complete_flow():
    """Complete a flow."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")

    assert dt.complete_flow(fid) is True
    assert dt.get_flow(fid)["status"] == "completed"
    assert dt.complete_flow(fid) is False
    print("OK: complete flow")


def test_fail_flow():
    """Fail a flow."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")

    assert dt.fail_flow(fid) is True
    assert dt.get_flow(fid)["status"] == "failed"
    assert dt.fail_flow(fid) is False
    print("OK: fail flow")


def test_record_transfer():
    """Record a transfer."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")

    tid = dt.record_transfer(fid, bytes_count=1024, record_count=10,
                             duration_ms=50.0)
    assert tid.startswith("xfer-")

    t = dt.get_transfer(tid)
    assert t is not None
    assert t["flow_id"] == fid
    assert t["bytes_count"] == 1024
    assert t["record_count"] == 10
    assert t["duration_ms"] == 50.0

    f = dt.get_flow(fid)
    assert f["bytes_transferred"] == 1024
    assert f["record_count"] == 10
    print("OK: record transfer")


def test_failed_transfer():
    """Failed transfer increments error count."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")

    dt.record_transfer(fid, status="failed", error="timeout")
    assert dt.get_flow(fid)["error_count"] == 1
    print("OK: failed transfer")


def test_remove_flow_cascades():
    """Remove flow removes its transfers."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")
    dt.record_transfer(fid, bytes_count=100)

    dt.remove_flow(fid)
    assert dt.get_flow_transfers(fid) == []
    print("OK: remove flow cascades")


def test_search_flows():
    """Search flows with filters."""
    dt = PipelineDataFlowTracker()
    dt.create_flow("a", source="s1", data_type="event", tags=["core"])
    f2 = dt.create_flow("b", source="s2", data_type="message")
    dt.pause_flow(f2)

    all_f = dt.search_flows()
    assert len(all_f) == 2

    by_source = dt.search_flows(source="s1")
    assert len(by_source) == 1

    by_type = dt.search_flows(data_type="event")
    assert len(by_type) == 1

    by_status = dt.search_flows(status="paused")
    assert len(by_status) == 1

    by_tag = dt.search_flows(tag="core")
    assert len(by_tag) == 1
    print("OK: search flows")


def test_flow_transfers():
    """Get transfers for a flow."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")
    dt.record_transfer(fid, bytes_count=100)
    dt.record_transfer(fid, bytes_count=200)
    dt.record_transfer(fid, status="failed")

    all_t = dt.get_flow_transfers(fid)
    assert len(all_t) == 3

    completed = dt.get_flow_transfers(fid, status="completed")
    assert len(completed) == 2
    print("OK: flow transfers")


def test_flow_throughput():
    """Get flow throughput stats."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")
    dt.record_transfer(fid, bytes_count=1000, duration_ms=100.0)
    dt.record_transfer(fid, bytes_count=2000, duration_ms=200.0)

    tp = dt.get_flow_throughput(fid)
    assert tp["transfer_count"] == 2
    assert tp["total_bytes"] == 3000
    assert tp["avg_bytes_per_transfer"] == 1500.0
    assert tp["avg_duration_ms"] == 150.0
    assert tp["bytes_per_ms"] == 10.0
    print("OK: flow throughput")


def test_component_flows():
    """Get flows for a component."""
    dt = PipelineDataFlowTracker()
    dt.create_flow("out1", source="A", target="B")
    dt.create_flow("out2", source="A", target="C")
    dt.create_flow("in1", source="D", target="A")

    cf = dt.get_component_flows("A")
    assert cf["component"] == "A"
    assert len(cf["outgoing"]) == 2
    assert len(cf["incoming"]) == 1
    assert cf["total"] == 3
    print("OK: component flows")


def test_bottlenecks():
    """Identify bottleneck flows."""
    dt = PipelineDataFlowTracker()
    f1 = dt.create_flow("healthy")
    dt.record_transfer(f1, bytes_count=100, duration_ms=10.0)
    dt.record_transfer(f1, bytes_count=100, duration_ms=10.0)

    f2 = dt.create_flow("unhealthy")
    dt.record_transfer(f2, bytes_count=100, duration_ms=500.0)
    dt.record_transfer(f2, status="failed")
    dt.record_transfer(f2, status="failed")

    bottlenecks = dt.get_bottlenecks()
    assert len(bottlenecks) == 2
    assert bottlenecks[0]["name"] == "unhealthy"
    assert bottlenecks[0]["error_rate"] > 0
    print("OK: bottlenecks")


def test_callback():
    """Callback fires on flow create."""
    dt = PipelineDataFlowTracker()
    fired = []
    dt.on_change("mon", lambda a, d: fired.append(a))

    dt.create_flow("test")
    assert "flow_created" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    dt = PipelineDataFlowTracker()
    assert dt.on_change("mon", lambda a, d: None) is True
    assert dt.on_change("mon", lambda a, d: None) is False
    assert dt.remove_callback("mon") is True
    assert dt.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")
    dt.record_transfer(fid, bytes_count=500, record_count=5)
    dt.record_transfer(fid, status="failed")

    stats = dt.get_stats()
    assert stats["total_flows_created"] == 1
    assert stats["total_transfers"] == 2
    assert stats["total_bytes"] == 500
    assert stats["total_records"] == 5
    assert stats["total_errors"] == 1
    assert stats["current_flows"] == 1
    assert stats["active_flows"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    dt = PipelineDataFlowTracker()
    fid = dt.create_flow("test")
    dt.record_transfer(fid, bytes_count=100)

    dt.reset()
    assert dt.search_flows() == []
    stats = dt.get_stats()
    assert stats["current_flows"] == 0
    assert stats["current_transfers"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Flow Tracker Tests ===\n")
    test_create_flow()
    test_invalid_flow()
    test_max_flows()
    test_pause_resume()
    test_complete_flow()
    test_fail_flow()
    test_record_transfer()
    test_failed_transfer()
    test_remove_flow_cascades()
    test_search_flows()
    test_flow_transfers()
    test_flow_throughput()
    test_component_flows()
    test_bottlenecks()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
