"""Test pipeline branch router -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_branch_router import PipelineBranchRouter


def test_add_branch():
    br = PipelineBranchRouter()
    bid = br.add_branch("pipeline-1", "status", "error", "handle_error")
    assert len(bid) > 0
    assert bid.startswith("pbr-")
    print("OK: add branch")


def test_route_match():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    br.add_branch("pipeline-1", "status", "ok", "continue")
    target = br.route("pipeline-1", {"status": "error"})
    assert target == "handle_error"
    print("OK: route match")


def test_route_no_match():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    target = br.route("pipeline-1", {"status": "ok"})
    assert target == "" or target == "continue"  # depends on if second branch added
    # If no match, should return ""
    br2 = PipelineBranchRouter()
    br2.add_branch("pipeline-1", "status", "error", "handle_error")
    assert br2.route("pipeline-1", {"status": "ok"}) == ""
    print("OK: route no match")


def test_route_first_match():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "first_handler")
    br.add_branch("pipeline-1", "status", "error", "second_handler")
    target = br.route("pipeline-1", {"status": "error"})
    assert target == "first_handler"  # first match wins
    print("OK: route first match")


def test_get_branches():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    br.add_branch("pipeline-1", "type", "batch", "batch_handler")
    branches = br.get_branches("pipeline-1")
    assert len(branches) == 2
    print("OK: get branches")


def test_remove_branch():
    br = PipelineBranchRouter()
    bid = br.add_branch("pipeline-1", "status", "error", "handle_error")
    assert br.remove_branch(bid) is True
    assert br.remove_branch("nonexistent") is False
    assert br.get_branch_count("pipeline-1") == 0
    print("OK: remove branch")


def test_get_branch_count():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    br.add_branch("pipeline-2", "type", "batch", "batch_handler")
    assert br.get_branch_count() == 2
    assert br.get_branch_count("pipeline-1") == 1
    print("OK: get branch count")


def test_list_pipelines():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    br.add_branch("pipeline-2", "type", "batch", "batch_handler")
    pipelines = br.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    br = PipelineBranchRouter()
    fired = []
    br.on_change("mon", lambda a, d: fired.append(a))
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    assert len(fired) >= 1
    assert br.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    stats = br.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    br = PipelineBranchRouter()
    br.add_branch("pipeline-1", "status", "error", "handle_error")
    br.reset()
    assert br.get_branch_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Branch Router Tests ===\n")
    test_add_branch()
    test_route_match()
    test_route_no_match()
    test_route_first_match()
    test_get_branches()
    test_remove_branch()
    test_get_branch_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
