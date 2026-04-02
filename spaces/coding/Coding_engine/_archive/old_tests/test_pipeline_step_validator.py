"""Test pipeline step validator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_validator import PipelineStepValidator


def test_define_schema():
    sv = PipelineStepValidator()
    sid = sv.define_schema("pipeline-1", "extract",
                           input_fields={"url": "str", "timeout": "int"},
                           output_fields={"data": "list", "count": "int"})
    assert len(sid) > 0
    assert sid.startswith("psv-")
    print("OK: define schema")


def test_validate_input_valid():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract",
                     input_fields={"url": "str", "timeout": "int"})
    result = sv.validate_input("pipeline-1", "extract", {"url": "http://example.com", "timeout": 30})
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    print("OK: validate input valid")


def test_validate_input_invalid():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract",
                     input_fields={"url": "str", "timeout": "int"})
    result = sv.validate_input("pipeline-1", "extract", {"url": "http://example.com", "timeout": "not_int"})
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    print("OK: validate input invalid")


def test_validate_input_missing_field():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract",
                     input_fields={"url": "str", "timeout": "int"})
    result = sv.validate_input("pipeline-1", "extract", {"url": "http://example.com"})
    assert result["valid"] is False
    assert len(result["errors"]) > 0
    print("OK: validate input missing field")


def test_validate_output():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract",
                     output_fields={"data": "list", "count": "int"})
    result = sv.validate_output("pipeline-1", "extract", {"data": [1, 2], "count": 2})
    assert result["valid"] is True
    print("OK: validate output")


def test_get_schema():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract",
                     input_fields={"url": "str"})
    schema = sv.get_schema("pipeline-1", "extract")
    assert schema is not None
    assert sv.get_schema("pipeline-1", "nonexistent") is None
    print("OK: get schema")


def test_list_schemas():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract", input_fields={"url": "str"})
    sv.define_schema("pipeline-1", "transform", input_fields={"data": "list"})
    schemas = sv.list_schemas("pipeline-1")
    assert len(schemas) == 2
    print("OK: list schemas")


def test_list_pipelines():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract", input_fields={"url": "str"})
    sv.define_schema("pipeline-2", "load", input_fields={"target": "str"})
    pipelines = sv.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    sv = PipelineStepValidator()
    fired = []
    sv.on_change("mon", lambda a, d: fired.append(a))
    sv.define_schema("pipeline-1", "extract", input_fields={"url": "str"})
    assert len(fired) >= 1
    assert sv.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract", input_fields={"url": "str"})
    stats = sv.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sv = PipelineStepValidator()
    sv.define_schema("pipeline-1", "extract", input_fields={"url": "str"})
    sv.reset()
    assert sv.get_schema_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Step Validator Tests ===\n")
    test_define_schema()
    test_validate_input_valid()
    test_validate_input_invalid()
    test_validate_input_missing_field()
    test_validate_output()
    test_get_schema()
    test_list_schemas()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
