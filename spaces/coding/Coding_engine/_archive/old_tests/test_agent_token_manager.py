"""Test agent token manager."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_token_manager import AgentTokenManager


def test_issue():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1", scopes=["read", "write"], tags=["api"])
    assert tid.startswith("tok-")
    t = tm.get_token(tid)
    assert t["agent"] == "w1"
    assert "read" in t["scopes"]
    print("OK: issue")

def test_invalid_issue():
    tm = AgentTokenManager()
    assert tm.issue_token("") == ""
    print("OK: invalid issue")

def test_max_tokens():
    tm = AgentTokenManager(max_tokens=2)
    tm.issue_token("a")
    tm.issue_token("b")
    assert tm.issue_token("c") == ""
    print("OK: max tokens")

def test_validate():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1", scopes=["read"])
    r = tm.validate_token(tid)
    assert r["valid"] is True
    assert r["agent"] == "w1"
    print("OK: validate")

def test_validate_scope():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1", scopes=["read"])
    assert tm.validate_token(tid, "read")["valid"] is True
    assert tm.validate_token(tid, "admin")["valid"] is False
    print("OK: validate scope")

def test_validate_expired():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1", ttl=0.001)
    time.sleep(0.01)
    assert tm.validate_token(tid)["valid"] is False
    print("OK: validate expired")

def test_validate_revoked():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1")
    tm.revoke_token(tid)
    assert tm.validate_token(tid)["valid"] is False
    print("OK: validate revoked")

def test_validate_not_found():
    tm = AgentTokenManager()
    assert tm.validate_token("nonexistent")["valid"] is False
    print("OK: validate not found")

def test_refresh():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1", ttl=60.0)
    assert tm.refresh_token(tid) is True
    t = tm.get_token(tid)
    assert t["refresh_count"] == 1
    print("OK: refresh")

def test_refresh_max():
    tm = AgentTokenManager(max_refreshes=2)
    tid = tm.issue_token("w1", ttl=60.0)
    tm.refresh_token(tid)
    tm.refresh_token(tid)
    assert tm.refresh_token(tid) is False
    print("OK: refresh max")

def test_refresh_expired():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1", ttl=0.001)
    time.sleep(0.01)
    assert tm.refresh_token(tid) is False
    print("OK: refresh expired")

def test_revoke():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1")
    assert tm.revoke_token(tid) is True
    assert tm.revoke_token(tid) is False
    print("OK: revoke")

def test_revoke_agent():
    tm = AgentTokenManager()
    tm.issue_token("w1")
    tm.issue_token("w1")
    count = tm.revoke_agent_tokens("w1")
    assert count == 2
    print("OK: revoke agent")

def test_agent_tokens():
    tm = AgentTokenManager()
    tm.issue_token("w1")
    tm.issue_token("w1")
    tm.issue_token("w2")
    assert len(tm.get_agent_tokens("w1")) == 2
    print("OK: agent tokens")

def test_list_tokens():
    tm = AgentTokenManager()
    tm.issue_token("w1", ttl=60.0)
    tid2 = tm.issue_token("w2", ttl=60.0)
    tm.revoke_token(tid2)
    all_t = tm.list_tokens()
    assert len(all_t) == 2
    active = tm.list_tokens(active_only=True)
    assert len(active) == 1
    print("OK: list tokens")

def test_cleanup_expired():
    tm = AgentTokenManager()
    tm.issue_token("w1", ttl=0.001)
    tm.issue_token("w2", ttl=9999)
    time.sleep(0.01)
    count = tm.cleanup_expired()
    assert count == 1
    print("OK: cleanup expired")

def test_history():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1")
    tm.validate_token(tid)
    hist = tm.get_history()
    assert len(hist) == 2
    limited = tm.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")

def test_callback():
    tm = AgentTokenManager()
    fired = []
    tm.on_change("mon", lambda a, d: fired.append(a))
    tm.issue_token("w1")
    assert "token_issued" in fired
    print("OK: callback")

def test_callbacks():
    tm = AgentTokenManager()
    assert tm.on_change("m", lambda a, d: None) is True
    assert tm.on_change("m", lambda a, d: None) is False
    assert tm.remove_callback("m") is True
    assert tm.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    tm = AgentTokenManager()
    tid = tm.issue_token("w1", ttl=60.0)
    tm.validate_token(tid)
    stats = tm.get_stats()
    assert stats["total_issued"] == 1
    assert stats["total_validated"] == 1
    assert stats["active_tokens"] == 1
    print("OK: stats")

def test_reset():
    tm = AgentTokenManager()
    tm.issue_token("w1")
    tm.reset()
    assert tm.list_tokens() == []
    assert tm.get_stats()["total_issued"] == 0
    print("OK: reset")

def main():
    print("=== Agent Token Manager Tests ===\n")
    test_issue()
    test_invalid_issue()
    test_max_tokens()
    test_validate()
    test_validate_scope()
    test_validate_expired()
    test_validate_revoked()
    test_validate_not_found()
    test_refresh()
    test_refresh_max()
    test_refresh_expired()
    test_revoke()
    test_revoke_agent()
    test_agent_tokens()
    test_list_tokens()
    test_cleanup_expired()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")

if __name__ == "__main__":
    main()
