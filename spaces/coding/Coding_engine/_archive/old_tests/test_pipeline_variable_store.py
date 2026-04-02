"""Test pipeline variable store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_variable_store import PipelineVariableStore


def test_set_and_get():
    vs = PipelineVariableStore()
    vid = vs.set_variable("deploy", "env", "production", scope="pipeline", tags=["config"])
    assert len(vid) > 0
    val = vs.get_variable("deploy", "env")
    assert val == "production"
    print("OK: set and get")


def test_delete_variable():
    vs = PipelineVariableStore()
    vs.set_variable("deploy", "env", "production")
    assert vs.delete_variable("deploy", "env") is True
    assert vs.delete_variable("deploy", "env") is False
    assert vs.get_variable("deploy", "env") is None
    print("OK: delete variable")


def test_list_variables():
    vs = PipelineVariableStore()
    vs.set_variable("deploy", "env", "prod")
    vs.set_variable("deploy", "region", "us-east")
    variables = vs.list_variables("deploy")
    assert len(variables) == 2
    print("OK: list variables")


def test_get_all_variables():
    vs = PipelineVariableStore()
    vs.set_variable("deploy", "env", "prod")
    vs.set_variable("deploy", "region", "us-east")
    all_vars = vs.get_all_variables("deploy")
    assert "env" in all_vars
    assert all_vars["env"] == "prod"
    print("OK: get all variables")


def test_secret_variable():
    vs = PipelineVariableStore()
    vid = vs.set_secret("deploy", "api_key", "sk-12345")
    assert len(vid) > 0
    # Secrets should be retrievable
    val = vs.get_variable("deploy", "api_key")
    assert val is not None
    print("OK: secret variable")


def test_has_variable():
    vs = PipelineVariableStore()
    vs.set_variable("deploy", "env", "prod")
    assert vs.has_variable("deploy", "env") is True
    assert vs.has_variable("deploy", "missing") is False
    print("OK: has variable")


def test_scoped_variables():
    vs = PipelineVariableStore()
    vs.set_variable("deploy", "env", "prod", scope="pipeline")
    vs.set_variable("deploy", "region", "us-east", scope="stage")
    val1 = vs.get_variable("deploy", "env")
    val2 = vs.get_variable("deploy", "region")
    assert val1 == "prod"
    assert val2 == "us-east"
    print("OK: scoped variables")


def test_callbacks():
    vs = PipelineVariableStore()
    fired = []
    vs.on_change("mon", lambda a, d: fired.append(a))
    vs.set_variable("deploy", "env", "prod")
    assert len(fired) >= 1
    assert vs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    vs = PipelineVariableStore()
    vs.set_variable("deploy", "env", "prod")
    stats = vs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    vs = PipelineVariableStore()
    vs.set_variable("deploy", "env", "prod")
    vs.reset()
    assert vs.get_variable("deploy", "env") is None
    print("OK: reset")


def main():
    print("=== Pipeline Variable Store Tests ===\n")
    test_set_and_get()
    test_delete_variable()
    test_list_variables()
    test_get_all_variables()
    test_secret_variable()
    test_has_variable()
    test_scoped_variables()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
