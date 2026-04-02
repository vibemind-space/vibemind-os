"""Test pipeline state machine -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_state_machine import PipelineStateMachine


def test_create_machine():
    sm = PipelineStateMachine()
    mid = sm.create_machine("pipeline-1")
    assert len(mid) > 0
    assert mid.startswith("psm-")
    print("OK: create machine")


def test_get_state():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    assert sm.get_state("pipeline-1") == "idle"
    assert sm.get_state("nonexistent") == "unknown"
    print("OK: get state")


def test_transition_valid():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    assert sm.transition("pipeline-1", "running") is True
    assert sm.get_state("pipeline-1") == "running"
    print("OK: transition valid")


def test_transition_invalid():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    assert sm.transition("pipeline-1", "completed") is False
    assert sm.get_state("pipeline-1") == "idle"
    print("OK: transition invalid")


def test_transition_sequence():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    assert sm.transition("pipeline-1", "running") is True
    assert sm.transition("pipeline-1", "paused") is True
    assert sm.transition("pipeline-1", "running") is True
    assert sm.transition("pipeline-1", "completed") is True
    assert sm.get_state("pipeline-1") == "completed"
    print("OK: transition sequence")


def test_get_history():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    sm.transition("pipeline-1", "running")
    sm.transition("pipeline-1", "completed")
    history = sm.get_history("pipeline-1")
    assert len(history) == 2
    assert history[0]["to_state"] == "running"
    print("OK: get history")


def test_is_terminal():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    assert sm.is_terminal("pipeline-1") is False
    sm.transition("pipeline-1", "running")
    sm.transition("pipeline-1", "completed")
    assert sm.is_terminal("pipeline-1") is True
    print("OK: is terminal")


def test_reset_machine():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    sm.transition("pipeline-1", "running")
    assert sm.reset_machine("pipeline-1") is True
    assert sm.get_state("pipeline-1") == "idle"
    print("OK: reset machine")


def test_list_pipelines():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    sm.create_machine("pipeline-2")
    pipelines = sm.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    sm = PipelineStateMachine()
    fired = []
    sm.on_change("mon", lambda a, d: fired.append(a))
    sm.create_machine("pipeline-1")
    assert len(fired) >= 1
    assert sm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    stats = sm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sm = PipelineStateMachine()
    sm.create_machine("pipeline-1")
    sm.reset()
    assert sm.get_machine_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline State Machine Tests ===\n")
    test_create_machine()
    test_get_state()
    test_transition_valid()
    test_transition_invalid()
    test_transition_sequence()
    test_get_history()
    test_is_terminal()
    test_reset_machine()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
