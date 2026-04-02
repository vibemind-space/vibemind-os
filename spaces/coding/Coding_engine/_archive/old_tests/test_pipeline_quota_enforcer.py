"""Test pipeline quota enforcer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_quota_enforcer import PipelineQuotaEnforcer


def test_create_quota():
    qe = PipelineQuotaEnforcer()
    qid = qe.create_quota("pipeline-1", "executions", limit=100, period="hour")
    assert len(qid) > 0
    assert qid.startswith("pqe-")
    print("OK: create quota")


def test_get_quota():
    qe = PipelineQuotaEnforcer()
    qid = qe.create_quota("pipeline-1", "executions", limit=50)
    quota = qe.get_quota(qid)
    assert quota is not None
    assert quota["pipeline_id"] == "pipeline-1"
    assert quota["resource"] == "executions"
    assert quota["limit"] == 50
    assert qe.get_quota("nonexistent") is None
    print("OK: get quota")


def test_check_quota():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=5)
    assert qe.check_quota("pipeline-1", "executions") is True
    print("OK: check quota")


def test_consume_quota():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=3)
    assert qe.consume_quota("pipeline-1", "executions") is True
    assert qe.consume_quota("pipeline-1", "executions") is True
    assert qe.consume_quota("pipeline-1", "executions") is True
    assert qe.consume_quota("pipeline-1", "executions") is False
    print("OK: consume quota")


def test_get_usage():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=10)
    qe.consume_quota("pipeline-1", "executions", amount=3)
    assert qe.get_usage("pipeline-1", "executions") == 3
    print("OK: get usage")


def test_get_remaining():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=10)
    qe.consume_quota("pipeline-1", "executions", amount=4)
    assert qe.get_remaining("pipeline-1", "executions") == 6
    print("OK: get remaining")


def test_reset_quota():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=10)
    qe.consume_quota("pipeline-1", "executions", amount=5)
    assert qe.reset_quota("pipeline-1", "executions") is True
    assert qe.get_usage("pipeline-1", "executions") == 0
    print("OK: reset quota")


def test_list_pipelines():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=10)
    qe.create_quota("pipeline-2", "api_calls", limit=100)
    pipelines = qe.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    qe = PipelineQuotaEnforcer()
    fired = []
    qe.on_change("mon", lambda a, d: fired.append(a))
    qe.create_quota("pipeline-1", "executions", limit=10)
    assert len(fired) >= 1
    assert qe.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=10)
    stats = qe.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    qe = PipelineQuotaEnforcer()
    qe.create_quota("pipeline-1", "executions", limit=10)
    qe.reset()
    assert qe.get_quota_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Quota Enforcer Tests ===\n")
    test_create_quota()
    test_get_quota()
    test_check_quota()
    test_consume_quota()
    test_get_usage()
    test_get_remaining()
    test_reset_quota()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
