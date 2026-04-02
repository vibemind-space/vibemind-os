"""Test pipeline secret store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_secret_store import PipelineSecretStore


def test_set_get_secret():
    ss = PipelineSecretStore()
    sid = ss.set_secret("deploy", "api_key", "sk-12345")
    assert len(sid) > 0
    assert sid.startswith("pss2-")
    val = ss.get_secret("deploy", "api_key")
    assert val == "sk-12345"
    print("OK: set/get secret")


def test_update_secret():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "api_key", "old-key")
    ss.set_secret("deploy", "api_key", "new-key")
    assert ss.get_secret("deploy", "api_key") == "new-key"
    print("OK: update secret")


def test_delete_secret():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "token", "abc")
    assert ss.delete_secret("deploy", "token") is True
    assert ss.delete_secret("deploy", "token") is False
    print("OK: delete secret")


def test_has_secret():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "token", "abc")
    assert ss.has_secret("deploy", "token") is True
    assert ss.has_secret("deploy", "missing") is False
    print("OK: has secret")


def test_list_secrets():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "api_key", "k1")
    ss.set_secret("deploy", "db_pass", "k2")
    keys = ss.list_secrets("deploy")
    assert "api_key" in keys
    assert "db_pass" in keys
    print("OK: list secrets")


def test_clear_pipeline_secrets():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "k1", "v1")
    ss.set_secret("deploy", "k2", "v2")
    count = ss.clear_pipeline_secrets("deploy")
    assert count == 2
    assert ss.get_pipeline_secret_count("deploy") == 0
    print("OK: clear pipeline secrets")


def test_list_pipelines():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "k", "v")
    ss.set_secret("test", "k", "v")
    pipes = ss.list_pipelines()
    assert "deploy" in pipes
    assert "test" in pipes
    print("OK: list pipelines")


def test_rotate_secret():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "token", "old")
    assert ss.rotate_secret("deploy", "token", "new") is True
    assert ss.get_secret("deploy", "token") == "new"
    assert ss.rotate_secret("deploy", "nonexistent", "v") is False
    print("OK: rotate secret")


def test_callbacks():
    ss = PipelineSecretStore()
    fired = []
    ss.on_change("mon", lambda a, d: fired.append(a))
    ss.set_secret("deploy", "k", "v")
    assert len(fired) >= 1
    assert ss.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "k", "v")
    stats = ss.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ss = PipelineSecretStore()
    ss.set_secret("deploy", "k", "v")
    ss.reset()
    assert ss.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Secret Store Tests ===\n")
    test_set_get_secret()
    test_update_secret()
    test_delete_secret()
    test_has_secret()
    test_list_secrets()
    test_clear_pipeline_secrets()
    test_list_pipelines()
    test_rotate_secret()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
