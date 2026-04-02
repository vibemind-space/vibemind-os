"""Test agent credential vault -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_credential_vault import AgentCredentialVault


def test_store_credential():
    cv = AgentCredentialVault()
    cid = cv.store_credential("agent-1", "api_key", "sk-12345")
    assert len(cid) > 0
    assert cid.startswith("acv-")
    print("OK: store credential")


def test_get_credential():
    cv = AgentCredentialVault()
    cv.store_credential("agent-1", "api_key", "sk-12345")
    val = cv.get_credential("agent-1", "api_key")
    assert val == "sk-12345"
    assert cv.get_credential("agent-1", "nonexistent") is None
    print("OK: get credential")


def test_has_credential():
    cv = AgentCredentialVault()
    cv.store_credential("agent-1", "token", "abc")
    assert cv.has_credential("agent-1", "token") is True
    assert cv.has_credential("agent-1", "missing") is False
    print("OK: has credential")


def test_revoke_credential():
    cv = AgentCredentialVault()
    cv.store_credential("agent-1", "secret", "xyz")
    assert cv.revoke_credential("agent-1", "secret") is True
    assert cv.has_credential("agent-1", "secret") is False
    assert cv.revoke_credential("agent-1", "nonexistent") is False
    print("OK: revoke credential")


def test_list_credentials():
    cv = AgentCredentialVault()
    cv.store_credential("agent-1", "key1", "v1")
    cv.store_credential("agent-1", "key2", "v2")
    creds = cv.list_credentials("agent-1")
    assert "key1" in creds
    assert "key2" in creds
    print("OK: list credentials")


def test_list_agents():
    cv = AgentCredentialVault()
    cv.store_credential("agent-1", "k", "v")
    cv.store_credential("agent-2", "k", "v")
    agents = cv.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    cv = AgentCredentialVault()
    fired = []
    cv.on_change("mon", lambda a, d: fired.append(a))
    cv.store_credential("agent-1", "k", "v")
    assert len(fired) >= 1
    assert cv.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cv = AgentCredentialVault()
    cv.store_credential("agent-1", "k", "v")
    stats = cv.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cv = AgentCredentialVault()
    cv.store_credential("agent-1", "k", "v")
    cv.reset()
    assert cv.get_credential_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Credential Vault Tests ===\n")
    test_store_credential()
    test_get_credential()
    test_has_credential()
    test_revoke_credential()
    test_list_credentials()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
