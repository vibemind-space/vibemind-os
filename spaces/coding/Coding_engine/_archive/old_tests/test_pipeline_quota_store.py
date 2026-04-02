"""Test pipeline quota store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_quota_store import PipelineQuotaStore


def test_set_quota():
    qs = PipelineQuotaStore()
    qid = qs.set_quota("deploy", "cpu", 100)
    assert len(qid) > 0
    assert qid.startswith("pqs-")
    print("OK: set quota")


def test_get_quota():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    q = qs.get_quota("deploy", "cpu")
    assert q is not None
    assert q["pipeline_id"] == "deploy"
    assert q["resource_type"] == "cpu"
    assert q["max_amount"] == 100
    assert qs.get_quota("nonexistent", "cpu") is None
    print("OK: get quota")


def test_consume():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    assert qs.consume("deploy", "cpu", 60) is True
    assert qs.consume("deploy", "cpu", 60) is False  # Would exceed
    assert qs.consume("deploy", "cpu", 40) is True  # Exactly at limit
    print("OK: consume")


def test_release():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    qs.consume("deploy", "cpu", 80)
    assert qs.release("deploy", "cpu", 30) is True
    assert qs.get_remaining("deploy", "cpu") == 50.0
    assert qs.release("nonexistent", "cpu", 10) is False
    print("OK: release")


def test_get_remaining():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    qs.consume("deploy", "cpu", 40)
    assert qs.get_remaining("deploy", "cpu") == 60.0
    assert qs.get_remaining("nonexistent", "cpu") == 0.0
    print("OK: get remaining")


def test_get_utilization():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    qs.consume("deploy", "cpu", 25)
    assert qs.get_utilization("deploy", "cpu") == 0.25
    assert qs.get_utilization("nonexistent", "cpu") == 0.0
    print("OK: get utilization")


def test_reset_quota():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    qs.consume("deploy", "cpu", 50)
    assert qs.reset_quota("deploy", "cpu") is True
    assert qs.get_remaining("deploy", "cpu") == 100.0
    assert qs.reset_quota("nonexistent", "cpu") is False
    print("OK: reset quota")


def test_remove_quota():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    assert qs.remove_quota("deploy", "cpu") is True
    assert qs.remove_quota("deploy", "cpu") is False
    print("OK: remove quota")


def test_list_pipelines():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    qs.set_quota("build", "memory", 200)
    pipes = qs.list_pipelines()
    assert "deploy" in pipes
    assert "build" in pipes
    print("OK: list pipelines")


def test_get_pipeline_quotas():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    qs.set_quota("deploy", "memory", 200)
    quotas = qs.get_pipeline_quotas("deploy")
    assert len(quotas) == 2
    print("OK: get pipeline quotas")


def test_callbacks():
    qs = PipelineQuotaStore()
    fired = []
    qs.on_change("mon", lambda a, d: fired.append(a))
    qs.set_quota("deploy", "cpu", 100)
    assert len(fired) >= 1
    assert qs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    stats = qs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    qs = PipelineQuotaStore()
    qs.set_quota("deploy", "cpu", 100)
    qs.reset()
    assert qs.get_quota_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Quota Store Tests ===\n")
    test_set_quota()
    test_get_quota()
    test_consume()
    test_release()
    test_get_remaining()
    test_get_utilization()
    test_reset_quota()
    test_remove_quota()
    test_list_pipelines()
    test_get_pipeline_quotas()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
