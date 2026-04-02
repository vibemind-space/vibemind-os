"""Test pipeline output aggregator."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_output_aggregator import PipelineOutputAggregator


def test_add_output():
    """Add and retrieve output."""
    oa = PipelineOutputAggregator()
    oid = oa.add_output("codegen", "def hello(): pass",
                        output_type="code", source="agent-1",
                        quality_score=0.9, tags=["python"])
    assert oid.startswith("out-")

    o = oa.get_output(oid)
    assert o is not None
    assert o["stage"] == "codegen"
    assert o["content"] == "def hello(): pass"
    assert o["output_type"] == "code"
    assert o["status"] == "pending"
    assert o["quality_score"] == 0.9

    assert oa.remove_output(oid) is True
    assert oa.remove_output(oid) is False
    print("OK: add output")


def test_invalid_output():
    """Invalid output rejected."""
    oa = PipelineOutputAggregator()
    assert oa.add_output("", "content") == ""
    assert oa.add_output("stage", "") == ""
    assert oa.add_output("stage", "x", output_type="invalid") == ""
    print("OK: invalid output")


def test_accept_reject_merge():
    """Accept, reject, and merge outputs."""
    oa = PipelineOutputAggregator()
    o1 = oa.add_output("s", "good code")
    o2 = oa.add_output("s", "bad code")
    o3 = oa.add_output("s", "ok code")

    assert oa.accept_output(o1) is True
    assert oa.get_output(o1)["status"] == "accepted"
    assert oa.accept_output(o1) is False

    assert oa.reject_output(o2, reason="low quality") is True
    assert oa.get_output(o2)["status"] == "rejected"

    assert oa.merge_output(o3) is True
    assert oa.get_output(o3)["status"] == "merged"

    # Can merge accepted
    assert oa.merge_output(o1) is True
    assert oa.get_output(o1)["status"] == "merged"

    # Can't merge rejected
    assert oa.merge_output(o2) is False
    print("OK: accept reject merge")


def test_create_collection():
    """Create and manage collection."""
    oa = PipelineOutputAggregator()
    cid = oa.create_collection("sprint_1", tags=["v2"])
    assert cid.startswith("coll-")

    c = oa.get_collection(cid)
    assert c is not None
    assert c["name"] == "sprint_1"
    assert c["status"] == "open"
    assert c["output_count"] == 0

    assert oa.remove_collection(cid) is True
    assert oa.remove_collection(cid) is False
    print("OK: create collection")


def test_invalid_collection():
    """Invalid collection rejected."""
    oa = PipelineOutputAggregator()
    assert oa.create_collection("") == ""
    print("OK: invalid collection")


def test_max_collections():
    """Max collections enforced."""
    oa = PipelineOutputAggregator(max_collections=2)
    oa.create_collection("a")
    oa.create_collection("b")
    assert oa.create_collection("c") == ""
    print("OK: max collections")


def test_add_to_collection():
    """Add outputs to collection."""
    oa = PipelineOutputAggregator()
    cid = oa.create_collection("test")
    o1 = oa.add_output("s", "content1")
    o2 = oa.add_output("s", "content2")

    assert oa.add_to_collection(cid, o1) is True
    assert oa.add_to_collection(cid, o1) is False  # duplicate
    assert oa.add_to_collection(cid, "fake") is False  # nonexistent
    assert oa.add_to_collection(cid, o2) is True
    assert oa.get_collection(cid)["output_count"] == 2
    print("OK: add to collection")


def test_finalize_collection():
    """Finalize collection."""
    oa = PipelineOutputAggregator()
    cid = oa.create_collection("test")

    # Can't finalize empty
    assert oa.finalize_collection(cid) is False

    o1 = oa.add_output("s", "x")
    oa.add_to_collection(cid, o1)

    assert oa.finalize_collection(cid) is True
    assert oa.get_collection(cid)["status"] == "finalized"
    assert oa.finalize_collection(cid) is False

    # Can't add to finalized
    o2 = oa.add_output("s", "y")
    assert oa.add_to_collection(cid, o2) is False
    print("OK: finalize collection")


def test_archive_collection():
    """Archive collection."""
    oa = PipelineOutputAggregator()
    cid = oa.create_collection("test")

    assert oa.archive_collection(cid) is True
    assert oa.get_collection(cid)["status"] == "archived"
    assert oa.archive_collection(cid) is False
    print("OK: archive collection")


def test_collection_outputs():
    """Get outputs in collection in order."""
    oa = PipelineOutputAggregator()
    cid = oa.create_collection("test")
    o1 = oa.add_output("s1", "first")
    o2 = oa.add_output("s2", "second")
    oa.add_to_collection(cid, o1)
    oa.add_to_collection(cid, o2)

    outputs = oa.get_collection_outputs(cid)
    assert len(outputs) == 2
    assert outputs[0]["output_id"] == o1  # first added
    assert outputs[1]["output_id"] == o2
    print("OK: collection outputs")


def test_search_outputs():
    """Search outputs with filters."""
    oa = PipelineOutputAggregator()
    oa.add_output("codegen", "code1", output_type="code", source="a1",
                  quality_score=0.9, tags=["py"])
    oa.add_output("test", "result1", output_type="test_result", source="a2",
                  quality_score=0.5)
    o3 = oa.add_output("codegen", "code2", output_type="code", source="a1",
                       quality_score=0.3)
    oa.accept_output(o3)

    by_stage = oa.search_outputs(stage="codegen")
    assert len(by_stage) == 2

    by_type = oa.search_outputs(output_type="test_result")
    assert len(by_type) == 1

    by_status = oa.search_outputs(status="accepted")
    assert len(by_status) == 1

    by_source = oa.search_outputs(source="a1")
    assert len(by_source) == 2

    by_tag = oa.search_outputs(tag="py")
    assert len(by_tag) == 1

    by_quality = oa.search_outputs(min_quality=0.5)
    assert len(by_quality) == 2
    print("OK: search outputs")


def test_search_limit():
    """Search respects limit."""
    oa = PipelineOutputAggregator()
    for i in range(20):
        oa.add_output("s", f"c{i}")

    results = oa.search_outputs(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_stage_summary():
    """Get stage summary."""
    oa = PipelineOutputAggregator()
    o1 = oa.add_output("codegen", "x")
    o2 = oa.add_output("codegen", "y")
    oa.accept_output(o1)
    oa.reject_output(o2)
    oa.add_output("test", "z")

    summary = oa.get_stage_summary()
    assert "codegen" in summary
    assert summary["codegen"]["total"] == 2
    assert summary["codegen"]["accepted"] == 1
    assert summary["codegen"]["rejected"] == 1
    assert summary["test"]["total"] == 1
    print("OK: stage summary")


def test_quality_summary():
    """Get quality summary."""
    oa = PipelineOutputAggregator()
    oa.add_output("s", "a", quality_score=0.8)
    oa.add_output("s", "b", quality_score=0.4)
    oa.add_output("s", "c", quality_score=0.6)

    qs = oa.get_quality_summary()
    assert qs["count"] == 3
    assert qs["min"] == 0.4
    assert qs["max"] == 0.8
    assert qs["avg"] == 0.6
    print("OK: quality summary")


def test_list_collections():
    """List collections with filters."""
    oa = PipelineOutputAggregator()
    oa.create_collection("a", tags=["v1"])
    c2 = oa.create_collection("b")
    oa.archive_collection(c2)

    all_c = oa.list_collections()
    assert len(all_c) == 2

    by_status = oa.list_collections(status="open")
    assert len(by_status) == 1

    by_tag = oa.list_collections(tag="v1")
    assert len(by_tag) == 1
    print("OK: list collections")


def test_output_callback():
    """Callback fires on output add."""
    oa = PipelineOutputAggregator()
    fired = []
    oa.on_change("mon", lambda a, d: fired.append(a))

    oa.add_output("s", "x")
    assert "output_added" in fired
    print("OK: output callback")


def test_callbacks():
    """Callback registration."""
    oa = PipelineOutputAggregator()
    assert oa.on_change("mon", lambda a, d: None) is True
    assert oa.on_change("mon", lambda a, d: None) is False
    assert oa.remove_callback("mon") is True
    assert oa.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    oa = PipelineOutputAggregator()
    o1 = oa.add_output("s", "a")
    o2 = oa.add_output("s", "b")
    o3 = oa.add_output("s", "c")
    oa.accept_output(o1)
    oa.reject_output(o2)
    oa.merge_output(o3)
    oa.create_collection("coll")

    stats = oa.get_stats()
    assert stats["total_outputs_added"] == 3
    assert stats["total_accepted"] == 1
    assert stats["total_rejected"] == 1
    assert stats["total_merged"] == 1
    assert stats["total_collections_created"] == 1
    assert stats["current_outputs"] == 3
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    oa = PipelineOutputAggregator()
    oa.add_output("s", "x")
    oa.create_collection("c")

    oa.reset()
    assert oa.search_outputs() == []
    assert oa.list_collections() == []
    stats = oa.get_stats()
    assert stats["current_outputs"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Output Aggregator Tests ===\n")
    test_add_output()
    test_invalid_output()
    test_accept_reject_merge()
    test_create_collection()
    test_invalid_collection()
    test_max_collections()
    test_add_to_collection()
    test_finalize_collection()
    test_archive_collection()
    test_collection_outputs()
    test_search_outputs()
    test_search_limit()
    test_stage_summary()
    test_quality_summary()
    test_list_collections()
    test_output_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
