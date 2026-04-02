"""Test pipeline anomaly detector."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_anomaly_detector import PipelineAnomalyDetector


def test_register_metric():
    """Register and remove metric."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("cpu_usage", source="server-1",
                              detection_method="threshold",
                              threshold_high=90.0, threshold_low=0.0,
                              tags=["infra"])
    assert mid.startswith("metric-")

    m = ad.get_metric(mid)
    assert m is not None
    assert m["name"] == "cpu_usage"
    assert m["source"] == "server-1"
    assert m["threshold_high"] == 90.0
    assert "infra" in m["tags"]

    assert ad.remove_metric(mid) is True
    assert ad.remove_metric(mid) is False
    print("OK: register metric")


def test_invalid_metric():
    """Invalid metric rejected."""
    ad = PipelineAnomalyDetector()
    assert ad.register_metric("") == ""
    assert ad.register_metric("x", detection_method="invalid") == ""
    print("OK: invalid metric")


def test_max_metrics():
    """Max metrics enforced."""
    ad = PipelineAnomalyDetector(max_metrics=2)
    ad.register_metric("a")
    ad.register_metric("b")
    assert ad.register_metric("c") == ""
    print("OK: max metrics")


def test_threshold_detection():
    """Threshold anomaly detection."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_high=100.0, threshold_low=10.0)

    # Normal value
    result = ad.record_value(mid, 50.0)
    assert result is None

    # Anomaly: too high
    result = ad.record_value(mid, 120.0)
    assert result is not None
    assert result["severity"] == "warning"
    assert result["detection_method"] == "threshold"

    # Critical anomaly: way too high
    result = ad.record_value(mid, 200.0)
    assert result is not None
    assert result["severity"] == "critical"
    print("OK: threshold detection")


def test_threshold_low():
    """Low threshold anomaly."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_low=10.0)

    result = ad.record_value(mid, 5.0)
    assert result is not None
    assert result["severity"] == "warning"
    print("OK: threshold low")


def test_z_score_detection():
    """Z-score anomaly detection."""
    import random
    random.seed(42)

    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("latency", detection_method="z_score",
                              z_score_limit=2.0, window_size=20)

    # Build baseline with some variance (mean ~100, std ~5)
    for _ in range(20):
        ad.record_value(mid, 100 + random.gauss(0, 5))

    # Normal-ish value within 2 std
    result = ad.record_value(mid, 105.0)
    assert result is None

    # Extreme outlier (far beyond 2 std)
    result = ad.record_value(mid, 200.0)
    assert result is not None
    assert result["detection_method"] == "z_score"
    print("OK: z-score detection")


def test_moving_average_detection():
    """Moving average anomaly detection."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("requests", detection_method="moving_average",
                              window_size=10)

    # Build baseline
    for _ in range(15):
        ad.record_value(mid, 100.0)

    # Normal
    result = ad.record_value(mid, 110.0)
    assert result is None

    # Big deviation (>50%)
    result = ad.record_value(mid, 200.0)
    assert result is not None
    assert result["detection_method"] == "moving_average"
    print("OK: moving average detection")


def test_rate_of_change_detection():
    """Rate of change anomaly detection."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("errors", detection_method="rate_of_change")

    ad.record_value(mid, 100.0)

    # Small change
    result = ad.record_value(mid, 120.0)
    assert result is None

    # Big change (>50%)
    result = ad.record_value(mid, 250.0)
    assert result is not None
    assert result["detection_method"] == "rate_of_change"
    print("OK: rate of change detection")


def test_record_nonexistent():
    """Record to nonexistent metric."""
    ad = PipelineAnomalyDetector()
    assert ad.record_value("nonexistent", 50.0) is None
    print("OK: record nonexistent")


def test_get_anomalies():
    """Get anomalies with filters."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_high=100.0)

    ad.record_value(mid, 50.0)
    ad.record_value(mid, 120.0)  # Anomaly
    ad.record_value(mid, 200.0)  # Critical anomaly

    all_a = ad.get_anomalies()
    assert len(all_a) == 2

    by_metric = ad.get_anomalies(metric_id=mid)
    assert len(by_metric) == 2

    by_severity = ad.get_anomalies(severity="critical")
    assert len(by_severity) == 1

    unacked = ad.get_anomalies(acknowledged=False)
    assert len(unacked) == 2
    print("OK: get anomalies")


def test_acknowledge_anomaly():
    """Acknowledge an anomaly."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_high=100.0)

    ad.record_value(mid, 120.0)
    anomalies = ad.get_anomalies()
    aid = anomalies[0]["anomaly_id"]

    assert ad.acknowledge_anomaly(aid) is True
    assert ad.acknowledge_anomaly(aid) is False  # Already acked

    acked = ad.get_anomalies(acknowledged=True)
    assert len(acked) == 1
    print("OK: acknowledge anomaly")


def test_metric_health():
    """Get metric health summary."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("cpu", detection_method="threshold",
                              threshold_high=90.0)

    ad.record_value(mid, 50.0)
    ad.record_value(mid, 60.0)
    ad.record_value(mid, 95.0)  # Anomaly

    health = ad.get_metric_health(mid)
    assert health["name"] == "cpu"
    assert health["total_anomalies"] == 1
    assert health["statistics"]["min"] == 50.0
    assert health["statistics"]["max"] == 95.0
    assert health["statistics"]["count"] == 3

    assert ad.get_metric_health("nonexistent") == {}
    print("OK: metric health")


def test_severity_summary():
    """Get severity summary."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_high=100.0)

    ad.record_value(mid, 120.0)  # warning
    ad.record_value(mid, 200.0)  # critical

    summary = ad.get_severity_summary()
    assert summary["warning"] == 1
    assert summary["critical"] == 1
    print("OK: severity summary")


def test_list_metrics():
    """List metrics with filters."""
    ad = PipelineAnomalyDetector()
    ad.register_metric("cpu", source="server-1", tags=["infra"])
    ad.register_metric("mem", source="server-2")

    all_m = ad.list_metrics()
    assert len(all_m) == 2

    by_source = ad.list_metrics(source="server-1")
    assert len(by_source) == 1

    by_tag = ad.list_metrics(tag="infra")
    assert len(by_tag) == 1
    print("OK: list metrics")


def test_value_pruning():
    """Values pruned when max exceeded."""
    ad = PipelineAnomalyDetector(max_values_per_metric=5)
    mid = ad.register_metric("test")

    for i in range(10):
        ad.record_value(mid, float(i))

    m = ad.get_metric(mid)
    assert m["value_count"] == 5
    print("OK: value pruning")


def test_anomaly_pruning():
    """Anomalies pruned when max exceeded."""
    ad = PipelineAnomalyDetector(max_anomalies=4)
    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_high=10.0)

    for i in range(8):
        ad.record_value(mid, 100.0 + i)

    anomalies = ad.get_anomalies(limit=100)
    assert len(anomalies) <= 4
    print("OK: anomaly pruning")


def test_anomaly_callback():
    """Callback fires on anomaly detection."""
    ad = PipelineAnomalyDetector()
    fired = []
    ad.on_change("mon", lambda a, d: fired.append(a))

    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_high=100.0)
    ad.record_value(mid, 120.0)
    assert "anomaly_detected" in fired
    print("OK: anomaly callback")


def test_callbacks():
    """Callback registration."""
    ad = PipelineAnomalyDetector()
    assert ad.on_change("mon", lambda a, d: None) is True
    assert ad.on_change("mon", lambda a, d: None) is False
    assert ad.remove_callback("mon") is True
    assert ad.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("temp", detection_method="threshold",
                              threshold_high=100.0)

    ad.record_value(mid, 50.0)
    ad.record_value(mid, 120.0)

    stats = ad.get_stats()
    assert stats["total_metrics"] == 1
    assert stats["total_values_recorded"] == 2
    assert stats["total_anomalies_detected"] == 1
    assert stats["current_metrics"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ad = PipelineAnomalyDetector()
    mid = ad.register_metric("test")
    ad.record_value(mid, 50.0)

    ad.reset()
    assert ad.list_metrics() == []
    assert ad.get_anomalies() == []
    stats = ad.get_stats()
    assert stats["current_metrics"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Anomaly Detector Tests ===\n")
    test_register_metric()
    test_invalid_metric()
    test_max_metrics()
    test_threshold_detection()
    test_threshold_low()
    test_z_score_detection()
    test_moving_average_detection()
    test_rate_of_change_detection()
    test_record_nonexistent()
    test_get_anomalies()
    test_acknowledge_anomaly()
    test_metric_health()
    test_severity_summary()
    test_list_metrics()
    test_value_pruning()
    test_anomaly_pruning()
    test_anomaly_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
