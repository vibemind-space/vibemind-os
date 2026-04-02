"""Test pipeline secret vault."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_secret_vault import PipelineSecretVault


def test_store_secret():
    """Store and retrieve secret."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("db_password", "s3cret!", secret_type="credential",
                          owner="admin", tags=["core"])
    assert sid.startswith("sec-")

    info = sv.get_secret_info(sid)
    assert info is not None
    assert info["name"] == "db_password"
    assert info["secret_type"] == "credential"
    assert info["owner"] == "admin"
    assert info["status"] == "active"
    assert info["version"] == 1

    assert sv.remove_secret(sid) is True
    assert sv.remove_secret(sid) is False
    print("OK: store secret")


def test_invalid_secret():
    """Invalid secret rejected."""
    sv = PipelineSecretVault()
    assert sv.store_secret("", "val") == ""
    assert sv.store_secret("name", "") == ""
    assert sv.store_secret("name", "val", secret_type="invalid") == ""
    print("OK: invalid secret")


def test_duplicate_name():
    """Duplicate name rejected."""
    sv = PipelineSecretVault()
    sv.store_secret("key", "val1")
    assert sv.store_secret("key", "val2") == ""
    print("OK: duplicate name")


def test_max_secrets():
    """Max secrets enforced."""
    sv = PipelineSecretVault(max_secrets=2)
    sv.store_secret("a", "v1")
    sv.store_secret("b", "v2")
    assert sv.store_secret("c", "v3") == ""
    print("OK: max secrets")


def test_read_secret():
    """Read secret value."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("api_key", "abc123")

    val = sv.read_secret(sid)
    assert val == "abc123"
    assert sv.get_secret_info(sid)["access_count"] == 1
    print("OK: read secret")


def test_read_by_name():
    """Read secret by name."""
    sv = PipelineSecretVault()
    sv.store_secret("my_token", "tok123")

    assert sv.read_secret_by_name("my_token") == "tok123"
    assert sv.read_secret_by_name("nonexistent") is None
    print("OK: read by name")


def test_access_control():
    """Access control restricts reads."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("restricted", "secret_val",
                          allowed_accessors=["agent_a"])

    # Allowed accessor
    val = sv.read_secret(sid, accessor="agent_a")
    assert val == "secret_val"

    # Denied accessor
    val = sv.read_secret(sid, accessor="agent_b")
    assert val is None
    print("OK: access control")


def test_grant_revoke_access():
    """Grant and revoke access."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("key", "val", allowed_accessors=["a"])

    assert sv.grant_access(sid, "b") is True
    assert sv.grant_access(sid, "b") is False  # already granted

    assert sv.read_secret(sid, accessor="b") == "val"

    assert sv.revoke_access(sid, "b") is True
    assert sv.revoke_access(sid, "b") is False

    assert sv.read_secret(sid, accessor="b") is None
    print("OK: grant revoke access")


def test_rotate_secret():
    """Rotate a secret."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("api_key", "old_value")

    assert sv.rotate_secret(sid, "new_value") is True
    assert sv.read_secret(sid) == "new_value"
    assert sv.get_secret_info(sid)["version"] == 2
    print("OK: rotate secret")


def test_revoke_secret():
    """Revoke a secret."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("token", "val123")

    assert sv.revoke_secret(sid) is True
    assert sv.get_secret_info(sid)["status"] == "revoked"
    assert sv.read_secret(sid) is None  # can't read revoked
    assert sv.revoke_secret(sid) is False  # already revoked
    print("OK: revoke secret")


def test_search_secrets():
    """Search secrets."""
    sv = PipelineSecretVault()
    sv.store_secret("a", "v1", secret_type="api_key", owner="admin",
                    tags=["core"])
    s2 = sv.store_secret("b", "v2", secret_type="token", owner="bot")
    sv.revoke_secret(s2)

    all_s = sv.search_secrets()
    assert len(all_s) == 2

    by_type = sv.search_secrets(secret_type="api_key")
    assert len(by_type) == 1

    by_owner = sv.search_secrets(owner="admin")
    assert len(by_owner) == 1

    by_status = sv.search_secrets(status="revoked")
    assert len(by_status) == 1

    by_tag = sv.search_secrets(tag="core")
    assert len(by_tag) == 1
    print("OK: search secrets")


def test_access_log():
    """Access log records reads."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("key", "val", allowed_accessors=["a"])

    sv.read_secret(sid, accessor="a")
    sv.read_secret(sid, accessor="b")  # denied

    log = sv.get_access_log(secret_id=sid)
    assert len(log) == 2

    denied = sv.get_access_log(granted=False)
    assert len(denied) == 1

    by_accessor = sv.get_access_log(accessor="a")
    assert len(by_accessor) == 1
    print("OK: access log")


def test_get_by_name():
    """Get secret info by name."""
    sv = PipelineSecretVault()
    sv.store_secret("my_secret", "val")

    info = sv.get_secret_by_name("my_secret")
    assert info is not None
    assert info["name"] == "my_secret"
    assert sv.get_secret_by_name("nonexistent") is None
    print("OK: get by name")


def test_remove_cascades():
    """Remove secret removes its logs."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("key", "val")
    sv.read_secret(sid, accessor="test")

    sv.remove_secret(sid)
    assert sv.get_access_log(secret_id=sid) == []
    print("OK: remove cascades")


def test_callback():
    """Callback fires on secret store."""
    sv = PipelineSecretVault()
    fired = []
    sv.on_change("mon", lambda a, d: fired.append(a))

    sv.store_secret("key", "val")
    assert "secret_stored" in fired
    print("OK: callback")


def test_rotation_callback():
    """Callback fires on rotation."""
    sv = PipelineSecretVault()
    fired = []
    sv.on_change("mon", lambda a, d: fired.append(a))

    sid = sv.store_secret("key", "val")
    sv.rotate_secret(sid, "new_val")
    assert "secret_rotated" in fired
    print("OK: rotation callback")


def test_callbacks():
    """Callback registration."""
    sv = PipelineSecretVault()
    assert sv.on_change("mon", lambda a, d: None) is True
    assert sv.on_change("mon", lambda a, d: None) is False
    assert sv.remove_callback("mon") is True
    assert sv.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sv = PipelineSecretVault()
    sid = sv.store_secret("key", "val", allowed_accessors=["a"])
    sv.read_secret(sid, accessor="a")
    sv.read_secret(sid, accessor="b")  # denied
    sv.rotate_secret(sid, "new")

    stats = sv.get_stats()
    assert stats["total_secrets_created"] == 1
    assert stats["total_accesses"] == 1
    assert stats["total_denied"] == 1
    assert stats["total_rotations"] == 1
    assert stats["current_secrets"] == 1
    assert stats["active_secrets"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sv = PipelineSecretVault()
    sv.store_secret("key", "val")

    sv.reset()
    assert sv.search_secrets() == []
    stats = sv.get_stats()
    assert stats["current_secrets"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Secret Vault Tests ===\n")
    test_store_secret()
    test_invalid_secret()
    test_duplicate_name()
    test_max_secrets()
    test_read_secret()
    test_read_by_name()
    test_access_control()
    test_grant_revoke_access()
    test_rotate_secret()
    test_revoke_secret()
    test_search_secrets()
    test_access_log()
    test_get_by_name()
    test_remove_cascades()
    test_callback()
    test_rotation_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
