"""Test pipeline data enricher -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_enricher import PipelineDataEnricher


def test_register_enricher():
    de = PipelineDataEnricher()
    eid = de.register_enricher("pipeline-1", "status", default_value="pending")
    assert len(eid) > 0
    assert eid.startswith("pde-")
    print("OK: register enricher")


def test_enrich_add_default():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "status", default_value="pending")
    result = de.enrich("pipeline-1", {"name": "test"})
    assert result["status"] == "pending"
    assert result["name"] == "test"
    print("OK: enrich add default")


def test_enrich_no_overwrite():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "status", default_value="pending")
    result = de.enrich("pipeline-1", {"status": "active"})
    assert result["status"] == "active"  # existing value preserved
    print("OK: enrich no overwrite")


def test_enrich_transform_upper():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "region", default_value="us-east", transform="upper")
    result = de.enrich("pipeline-1", {})
    assert result["region"] == "US-EAST"
    print("OK: enrich transform upper")


def test_get_enricher():
    de = PipelineDataEnricher()
    eid = de.register_enricher("pipeline-1", "status", default_value="pending")
    enricher = de.get_enricher(eid)
    assert enricher is not None
    assert enricher["field_name"] == "status"
    assert de.get_enricher("nonexistent") is None
    print("OK: get enricher")


def test_get_enrichers():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "status")
    de.register_enricher("pipeline-1", "region")
    enrichers = de.get_enrichers("pipeline-1")
    assert len(enrichers) == 2
    print("OK: get enrichers")


def test_get_enricher_count():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "status")
    de.register_enricher("pipeline-2", "region")
    assert de.get_enricher_count() == 2
    assert de.get_enricher_count("pipeline-1") == 1
    print("OK: get enricher count")


def test_list_pipelines():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "status")
    de.register_enricher("pipeline-2", "region")
    pipelines = de.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    de = PipelineDataEnricher()
    fired = []
    de.on_change("mon", lambda a, d: fired.append(a))
    de.register_enricher("pipeline-1", "status")
    assert len(fired) >= 1
    assert de.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "status")
    stats = de.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    de = PipelineDataEnricher()
    de.register_enricher("pipeline-1", "status")
    de.reset()
    assert de.get_enricher_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Enricher Tests ===\n")
    test_register_enricher()
    test_enrich_add_default()
    test_enrich_no_overwrite()
    test_enrich_transform_upper()
    test_get_enricher()
    test_get_enrichers()
    test_get_enricher_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
