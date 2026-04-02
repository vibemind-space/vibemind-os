"""Test pipeline data sampler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_sampler import PipelineDataSampler


def test_create_sampler():
    ds = PipelineDataSampler()
    sid = ds.create_sampler("pipeline-1", strategy="first_n", sample_size=5)
    assert len(sid) > 0
    assert sid.startswith("pdsa-")
    print("OK: create sampler")


def test_sample_first_n():
    ds = PipelineDataSampler()
    sid = ds.create_sampler("pipeline-1", strategy="first_n", sample_size=3)
    result = ds.sample(sid, [1, 2, 3, 4, 5])
    assert result == [1, 2, 3]
    print("OK: sample first_n")


def test_sample_last_n():
    ds = PipelineDataSampler()
    sid = ds.create_sampler("pipeline-1", strategy="last_n", sample_size=3)
    result = ds.sample(sid, [1, 2, 3, 4, 5])
    assert result == [3, 4, 5]
    print("OK: sample last_n")


def test_get_sampler():
    ds = PipelineDataSampler()
    sid = ds.create_sampler("pipeline-1")
    sampler = ds.get_sampler(sid)
    assert sampler is not None
    assert ds.get_sampler("nonexistent") is None
    print("OK: get sampler")


def test_get_samplers():
    ds = PipelineDataSampler()
    ds.create_sampler("pipeline-1", sample_size=3)
    ds.create_sampler("pipeline-1", sample_size=5)
    samplers = ds.get_samplers("pipeline-1")
    assert len(samplers) == 2
    print("OK: get samplers")


def test_get_sampler_count():
    ds = PipelineDataSampler()
    ds.create_sampler("pipeline-1")
    ds.create_sampler("pipeline-2")
    assert ds.get_sampler_count() == 2
    assert ds.get_sampler_count("pipeline-1") == 1
    print("OK: get sampler count")


def test_list_pipelines():
    ds = PipelineDataSampler()
    ds.create_sampler("pipeline-1")
    ds.create_sampler("pipeline-2")
    pipelines = ds.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    ds = PipelineDataSampler()
    fired = []
    ds.on_change("mon", lambda a, d: fired.append(a))
    ds.create_sampler("pipeline-1")
    assert len(fired) >= 1
    assert ds.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ds = PipelineDataSampler()
    ds.create_sampler("pipeline-1")
    stats = ds.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ds = PipelineDataSampler()
    ds.create_sampler("pipeline-1")
    ds.reset()
    assert ds.get_sampler_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Sampler Tests ===\n")
    test_create_sampler()
    test_sample_first_n()
    test_sample_last_n()
    test_get_sampler()
    test_get_samplers()
    test_get_sampler_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
