"""Tests for AgentOutputFormatter."""

import json
import sys

sys.path.insert(0, ".")

from src.services.agent_output_formatter import AgentOutputFormatter


def test_configure_format():
    fmt = AgentOutputFormatter()
    cid = fmt.configure_format("agent-1", "json")
    assert cid.startswith("aof-"), f"Expected aof- prefix, got {cid}"
    assert len(cid) > 4
    # invalid format_type defaults to json
    cid2 = fmt.configure_format("agent-2", "xml")
    cfg = fmt.get_config("agent-2")
    assert cfg["format_type"] == "json"
    # empty agent_id returns ""
    assert fmt.configure_format("") == ""
    print("  PASSED test_configure_format")


def test_format_json():
    fmt = AgentOutputFormatter()
    fmt.configure_format("agent-1", "json")
    data = {"name": "Alice", "score": 42}
    result = fmt.format_output("agent-1", data)
    parsed = json.loads(result)
    assert parsed == data, f"JSON mismatch: {parsed}"
    print("  PASSED test_format_json")


def test_format_csv():
    fmt = AgentOutputFormatter()
    fmt.configure_format("agent-1", "csv")
    data = {"name": "Alice", "score": 42}
    result = fmt.format_output("agent-1", data)
    lines = result.split("\n")
    assert len(lines) == 2
    assert "name" in lines[0]
    assert "score" in lines[0]
    assert "Alice" in lines[1]
    assert "42" in lines[1]
    print("  PASSED test_format_csv")


def test_format_summary():
    fmt = AgentOutputFormatter()
    fmt.configure_format("agent-1", "summary")
    data = {"name": "Alice", "score": 42}
    result = fmt.format_output("agent-1", data)
    assert "name=Alice" in result
    assert "score=42" in result
    assert "; " in result
    print("  PASSED test_format_summary")


def test_format_no_config():
    fmt = AgentOutputFormatter()
    result = fmt.format_output("agent-unknown", {"key": "val"})
    assert result == "", f"Expected empty string, got {result!r}"
    print("  PASSED test_format_no_config")


def test_get_config():
    fmt = AgentOutputFormatter()
    assert fmt.get_config("no-agent") is None
    cid = fmt.configure_format("agent-1", "csv")
    cfg = fmt.get_config("agent-1")
    assert cfg is not None
    assert cfg["agent_id"] == "agent-1"
    assert cfg["format_type"] == "csv"
    assert cfg["config_id"] == cid
    print("  PASSED test_get_config")


def test_remove_config():
    fmt = AgentOutputFormatter()
    assert fmt.remove_config("nonexistent") is False
    cid = fmt.configure_format("agent-1", "json")
    assert fmt.remove_config(cid) is True
    assert fmt.get_config("agent-1") is None
    print("  PASSED test_remove_config")


def test_get_config_count():
    fmt = AgentOutputFormatter()
    assert fmt.get_config_count() == 0
    fmt.configure_format("agent-1", "json")
    fmt.configure_format("agent-1", "csv")
    fmt.configure_format("agent-2", "summary")
    assert fmt.get_config_count() == 3
    assert fmt.get_config_count("agent-1") == 2
    assert fmt.get_config_count("agent-2") == 1
    assert fmt.get_config_count("agent-3") == 0
    print("  PASSED test_get_config_count")


def test_list_agents():
    fmt = AgentOutputFormatter()
    assert fmt.list_agents() == []
    fmt.configure_format("beta", "json")
    fmt.configure_format("alpha", "csv")
    fmt.configure_format("beta", "summary")
    agents = fmt.list_agents()
    assert agents == ["alpha", "beta"], f"Got {agents}"
    print("  PASSED test_list_agents")


def test_callbacks():
    fmt = AgentOutputFormatter()
    events = []
    assert fmt.on_change("cb1", lambda a, d: events.append((a, d))) is True
    assert fmt.on_change("cb1", lambda a, d: None) is False  # duplicate
    fmt.configure_format("agent-1", "json")
    assert len(events) == 1
    assert events[0][0] == "format_configured"
    assert fmt.remove_callback("cb1") is True
    assert fmt.remove_callback("cb1") is False
    fmt.configure_format("agent-2", "csv")
    assert len(events) == 1  # no more events after removal
    print("  PASSED test_callbacks")


def test_stats():
    fmt = AgentOutputFormatter()
    fmt.configure_format("agent-1", "json")
    fmt.format_output("agent-1", {"x": 1})
    stats = fmt.get_stats()
    assert stats["total_configured"] == 1
    assert stats["total_formatted"] == 1
    assert stats["current_configs"] == 1
    assert stats["max_entries"] == 10000
    print("  PASSED test_stats")


def test_reset():
    fmt = AgentOutputFormatter()
    fmt.configure_format("agent-1", "json")
    fmt.on_change("cb1", lambda a, d: None)
    fmt.reset()
    assert fmt.get_config_count() == 0
    assert fmt.list_agents() == []
    stats = fmt.get_stats()
    assert stats["total_configured"] == 0
    assert stats["current_configs"] == 0
    print("  PASSED test_reset")


if __name__ == "__main__":
    tests = [
        test_configure_format,
        test_format_json,
        test_format_csv,
        test_format_summary,
        test_format_no_config,
        test_get_config,
        test_remove_config,
        test_get_config_count,
        test_list_agents,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAILED {t.__name__}: {e}")
    print(f"\n=== ALL {passed} TESTS PASSED ===" if passed == len(tests)
          else f"\n=== {passed}/{len(tests)} TESTS PASSED ===")
