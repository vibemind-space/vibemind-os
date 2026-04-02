"""Test pipeline data aggregator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_aggregator import PipelineDataAggregator


def test_create_aggregation():
    da = PipelineDataAggregator()
    aid = da.create_aggregation("pipeline-1", "score", operation="sum")
    assert len(aid) > 0
    assert aid.startswith("pda-")
    print("OK: create aggregation")


def test_aggregate_sum():
    da = PipelineDataAggregator()
    aid = da.create_aggregation("pipeline-1", "score", operation="sum")
    result = da.aggregate(aid, [{"score": 10}, {"score": 20}, {"score": 30}])
    assert result["result"] == 60
    assert result["operation"] == "sum"
    print("OK: aggregate sum")


def test_aggregate_avg():
    da = PipelineDataAggregator()
    aid = da.create_aggregation("pipeline-1", "score", operation="avg")
    result = da.aggregate(aid, [{"score": 10}, {"score": 20}, {"score": 30}])
    assert abs(result["result"] - 20.0) < 0.01
    print("OK: aggregate avg")


def test_aggregate_count():
    da = PipelineDataAggregator()
    aid = da.create_aggregation("pipeline-1", "score", operation="count")
    result = da.aggregate(aid, [{"score": 10}, {"score": 20}, {"score": 30}])
    assert result["result"] == 3
    print("OK: aggregate count")


def test_aggregate_min_max():
    da = PipelineDataAggregator()
    aid_min = da.create_aggregation("pipeline-1", "score", operation="min")
    aid_max = da.create_aggregation("pipeline-1", "score", operation="max")
    records = [{"score": 10}, {"score": 5}, {"score": 30}]
    assert da.aggregate(aid_min, records)["result"] == 5
    assert da.aggregate(aid_max, records)["result"] == 30
    print("OK: aggregate min/max")


def test_get_aggregation():
    da = PipelineDataAggregator()
    aid = da.create_aggregation("pipeline-1", "score")
    agg = da.get_aggregation(aid)
    assert agg is not None
    assert agg["field"] == "score"
    assert da.get_aggregation("nonexistent") is None
    print("OK: get aggregation")


def test_get_aggregations():
    da = PipelineDataAggregator()
    da.create_aggregation("pipeline-1", "score")
    da.create_aggregation("pipeline-1", "count")
    aggs = da.get_aggregations("pipeline-1")
    assert len(aggs) == 2
    print("OK: get aggregations")


def test_get_aggregation_count():
    da = PipelineDataAggregator()
    da.create_aggregation("pipeline-1", "score")
    da.create_aggregation("pipeline-2", "count")
    assert da.get_aggregation_count() == 2
    assert da.get_aggregation_count("pipeline-1") == 1
    print("OK: get aggregation count")


def test_list_pipelines():
    da = PipelineDataAggregator()
    da.create_aggregation("pipeline-1", "score")
    da.create_aggregation("pipeline-2", "count")
    pipelines = da.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    da = PipelineDataAggregator()
    fired = []
    da.on_change("mon", lambda a, d: fired.append(a))
    da.create_aggregation("pipeline-1", "score")
    assert len(fired) >= 1
    assert da.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    da = PipelineDataAggregator()
    da.create_aggregation("pipeline-1", "score")
    stats = da.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    da = PipelineDataAggregator()
    da.create_aggregation("pipeline-1", "score")
    da.reset()
    assert da.get_aggregation_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Aggregator Tests ===\n")
    test_create_aggregation()
    test_aggregate_sum()
    test_aggregate_avg()
    test_aggregate_count()
    test_aggregate_min_max()
    test_get_aggregation()
    test_get_aggregations()
    test_get_aggregation_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
