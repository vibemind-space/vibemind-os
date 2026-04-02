"""Test pipeline data lineage -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_lineage import PipelineDataLineage


def test_register_dataset():
    dl = PipelineDataLineage()
    did = dl.register_dataset("raw_data", "s3://bucket/raw")
    assert len(did) > 0
    assert did.startswith("pdl-")
    # Duplicate returns ""
    assert dl.register_dataset("raw_data", "s3://bucket/raw") == ""
    print("OK: register dataset")


def test_get_dataset():
    dl = PipelineDataLineage()
    did = dl.register_dataset("raw_data", "s3://bucket/raw", metadata={"format": "csv"})
    ds = dl.get_dataset(did)
    assert ds is not None
    assert ds["name"] == "raw_data"
    assert ds["source"] == "s3://bucket/raw"
    assert dl.get_dataset("nonexistent") is None
    print("OK: get dataset")


def test_get_dataset_by_name():
    dl = PipelineDataLineage()
    dl.register_dataset("raw_data", "s3://bucket/raw")
    ds = dl.get_dataset_by_name("raw_data")
    assert ds is not None
    assert ds["name"] == "raw_data"
    assert dl.get_dataset_by_name("missing") is None
    print("OK: get dataset by name")


def test_add_transformation():
    dl = PipelineDataLineage()
    d1 = dl.register_dataset("raw", "source")
    d2 = dl.register_dataset("processed", "pipeline")
    tid = dl.add_transformation(d1, d2, "etl-pipeline", "transform")
    assert len(tid) > 0
    assert tid.startswith("pdl-")
    # Invalid dataset returns ""
    assert dl.add_transformation(d1, "nonexistent", "p", "s") == ""
    print("OK: add transformation")


def test_get_lineage():
    dl = PipelineDataLineage()
    d1 = dl.register_dataset("raw", "source")
    d2 = dl.register_dataset("clean", "pipeline")
    d3 = dl.register_dataset("final", "pipeline")
    dl.add_transformation(d1, d2, "etl", "clean")
    dl.add_transformation(d2, d3, "etl", "aggregate")
    lineage = dl.get_lineage(d3)
    assert len(lineage) >= 1
    print("OK: get lineage")


def test_get_downstream():
    dl = PipelineDataLineage()
    d1 = dl.register_dataset("raw", "source")
    d2 = dl.register_dataset("clean", "pipeline")
    dl.add_transformation(d1, d2, "etl", "clean")
    downstream = dl.get_downstream(d1)
    assert len(downstream) == 1
    print("OK: get downstream")


def test_get_pipeline_lineage():
    dl = PipelineDataLineage()
    d1 = dl.register_dataset("raw", "s")
    d2 = dl.register_dataset("clean", "p")
    dl.add_transformation(d1, d2, "etl", "clean")
    pl = dl.get_pipeline_lineage("etl")
    assert len(pl) == 1
    print("OK: get pipeline lineage")


def test_delete_dataset():
    dl = PipelineDataLineage()
    did = dl.register_dataset("temp", "s")
    assert dl.delete_dataset(did) is True
    assert dl.delete_dataset(did) is False
    print("OK: delete dataset")


def test_list_datasets():
    dl = PipelineDataLineage()
    dl.register_dataset("d1", "s1")
    dl.register_dataset("d2", "s2")
    datasets = dl.list_datasets()
    assert len(datasets) == 2
    print("OK: list datasets")


def test_get_counts():
    dl = PipelineDataLineage()
    d1 = dl.register_dataset("raw", "s")
    d2 = dl.register_dataset("clean", "p")
    dl.add_transformation(d1, d2, "etl", "clean")
    assert dl.get_dataset_count() == 2
    assert dl.get_transformation_count() == 1
    print("OK: get counts")


def test_callbacks():
    dl = PipelineDataLineage()
    fired = []
    dl.on_change("mon", lambda a, d: fired.append(a))
    dl.register_dataset("d1", "s1")
    assert len(fired) >= 1
    assert dl.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    dl = PipelineDataLineage()
    dl.register_dataset("d1", "s1")
    stats = dl.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dl = PipelineDataLineage()
    dl.register_dataset("d1", "s1")
    dl.reset()
    assert dl.get_dataset_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Lineage Tests ===\n")
    test_register_dataset()
    test_get_dataset()
    test_get_dataset_by_name()
    test_add_transformation()
    test_get_lineage()
    test_get_downstream()
    test_get_pipeline_lineage()
    test_delete_dataset()
    test_list_datasets()
    test_get_counts()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
