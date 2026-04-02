"""Test pipeline data transformer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_transformer import PipelineDataTransformer


def test_register_transform():
    dt = PipelineDataTransformer()
    tid = dt.register_transform("double", lambda x: x * 2, description="Double value")
    assert len(tid) > 0
    t = dt.get_transform("double")
    assert t is not None
    assert t["name"] == "double"
    assert dt.register_transform("double", lambda x: x) == ""  # dup
    print("OK: register transform")


def test_apply():
    dt = PipelineDataTransformer()
    dt.register_transform("upper", lambda x: x.upper())
    result = dt.apply("upper", "hello")
    assert result["success"] is True
    assert result["result"] == "HELLO"
    print("OK: apply")


def test_apply_error():
    dt = PipelineDataTransformer()
    dt.register_transform("bad", lambda x: 1/0)
    result = dt.apply("bad", "data")
    assert result["success"] is False
    print("OK: apply error")


def test_chain():
    dt = PipelineDataTransformer()
    dt.register_transform("add1", lambda x: x + 1)
    dt.register_transform("double", lambda x: x * 2)
    result = dt.chain(["add1", "double"], 5)
    assert result["success"] is True
    assert result["result"] == 12  # (5+1)*2
    print("OK: chain")


def test_map_transform():
    dt = PipelineDataTransformer()
    dt.register_transform("square", lambda x: x ** 2)
    result = dt.map_transform("square", [1, 2, 3, 4])
    assert result["success"] is True
    assert result["results"] == [1, 4, 9, 16]
    print("OK: map transform")


def test_filter_transform():
    dt = PipelineDataTransformer()
    dt.register_transform("is_even", lambda x: x % 2 == 0)
    result = dt.filter_transform("is_even", [1, 2, 3, 4, 5, 6])
    assert result["success"] is True
    assert result["results"] == [2, 4, 6]
    print("OK: filter transform")


def test_list_transforms():
    dt = PipelineDataTransformer()
    dt.register_transform("t1", lambda x: x, tags=["math"])
    dt.register_transform("t2", lambda x: x)
    assert len(dt.list_transforms()) == 2
    assert len(dt.list_transforms(tag="math")) == 1
    print("OK: list transforms")


def test_remove_transform():
    dt = PipelineDataTransformer()
    dt.register_transform("t1", lambda x: x)
    assert dt.remove_transform("t1") is True
    assert dt.remove_transform("t1") is False
    print("OK: remove transform")


def test_execution_stats():
    dt = PipelineDataTransformer()
    dt.register_transform("inc", lambda x: x + 1)
    dt.apply("inc", 1)
    dt.apply("inc", 2)
    stats = dt.get_execution_stats("inc")
    assert stats["call_count"] == 2
    print("OK: execution stats")


def test_callbacks():
    dt = PipelineDataTransformer()
    fired = []
    cb_id = dt.on_change(lambda a, d: fired.append(a))
    dt.register_transform("t1", lambda x: x)
    assert len(fired) >= 1
    assert dt.remove_callback(cb_id) is True
    print("OK: callbacks")


def test_stats():
    dt = PipelineDataTransformer()
    dt.register_transform("t1", lambda x: x)
    stats = dt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    dt = PipelineDataTransformer()
    dt.register_transform("t1", lambda x: x)
    dt.reset()
    assert dt.list_transforms() == []
    print("OK: reset")


def main():
    print("=== Pipeline Data Transformer Tests ===\n")
    test_register_transform()
    test_apply()
    test_apply_error()
    test_chain()
    test_map_transform()
    test_filter_transform()
    test_list_transforms()
    test_remove_transform()
    test_execution_stats()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
