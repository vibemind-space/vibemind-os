"""Test pipeline log aggregator."""
import sys
sys.path.insert(0, ".")
from src.services.pipeline_log_aggregator import PipelineLogAggregator

def test_log():
    la = PipelineLogAggregator()
    eid = la.log("auth", "info", "User logged in", tags=["security"])
    assert eid.startswith("log-")
    e = la.get_entry(eid)
    assert e["source"] == "auth"
    assert e["level"] == "info"
    print("OK: log")

def test_invalid_log():
    la = PipelineLogAggregator()
    assert la.log("", "info", "msg") == ""
    assert la.log("src", "info", "") == ""
    assert la.log("src", "invalid", "msg") == ""
    print("OK: invalid log")

def test_level_shortcuts():
    la = PipelineLogAggregator()
    assert la.debug("s", "d") != ""
    assert la.info("s", "i") != ""
    assert la.warn("s", "w") != ""
    assert la.error("s", "e") != ""
    assert la.critical("s", "c") != ""
    print("OK: level shortcuts")

def test_min_level():
    la = PipelineLogAggregator(min_level="warn")
    assert la.debug("s", "msg") == ""  # below min
    assert la.info("s", "msg") == ""  # below min
    assert la.warn("s", "msg") != ""
    assert la.error("s", "msg") != ""
    print("OK: min level")

def test_set_min_level():
    la = PipelineLogAggregator()
    assert la.set_min_level("error") is True
    assert la.info("s", "msg") == ""
    assert la.set_min_level("invalid") is False
    print("OK: set min level")

def test_max_entries():
    la = PipelineLogAggregator(max_entries=3)
    la.info("s", "1")
    la.info("s", "2")
    la.info("s", "3")
    la.info("s", "4")
    assert len(la.query()) == 3
    print("OK: max entries")

def test_query_source():
    la = PipelineLogAggregator()
    la.info("auth", "login")
    la.info("db", "query")
    results = la.query(source="auth")
    assert len(results) == 1
    print("OK: query source")

def test_query_level():
    la = PipelineLogAggregator()
    la.info("s", "info msg")
    la.error("s", "error msg")
    results = la.query(level="error")
    assert len(results) == 1
    print("OK: query level")

def test_query_min_level():
    la = PipelineLogAggregator()
    la.debug("s", "d")
    la.info("s", "i")
    la.error("s", "e")
    results = la.query(min_level="info")
    assert len(results) == 2
    print("OK: query min level")

def test_query_search():
    la = PipelineLogAggregator()
    la.info("s", "User logged in")
    la.info("s", "DB connected")
    results = la.query(search="logged")
    assert len(results) == 1
    print("OK: query search")

def test_query_tag():
    la = PipelineLogAggregator()
    la.info("s", "msg1", tags=["security"])
    la.info("s", "msg2")
    results = la.query(tag="security")
    assert len(results) == 1
    print("OK: query tag")

def test_query_limit():
    la = PipelineLogAggregator()
    for i in range(10):
        la.info("s", f"msg{i}")
    results = la.query(limit=3)
    assert len(results) == 3
    print("OK: query limit")

def test_get_sources():
    la = PipelineLogAggregator()
    la.info("auth", "m1")
    la.info("db", "m2")
    la.info("auth", "m3")
    sources = la.get_sources()
    assert sorted(sources) == ["auth", "db"]
    print("OK: get sources")

def test_level_counts():
    la = PipelineLogAggregator()
    la.info("s", "m1")
    la.info("s", "m2")
    la.error("s", "m3")
    counts = la.get_level_counts()
    assert counts["info"] == 2
    assert counts["error"] == 1
    print("OK: level counts")

def test_clear():
    la = PipelineLogAggregator()
    la.info("s", "m1")
    la.info("s", "m2")
    count = la.clear()
    assert count == 2
    assert len(la.query()) == 0
    print("OK: clear")

def test_callback():
    la = PipelineLogAggregator()
    fired = []
    la.on_change("mon", lambda a, d: fired.append(a))
    la.info("s", "msg")
    assert "log_entry" in fired
    print("OK: callback")

def test_callbacks():
    la = PipelineLogAggregator()
    assert la.on_change("m", lambda a, d: None) is True
    assert la.on_change("m", lambda a, d: None) is False
    assert la.remove_callback("m") is True
    assert la.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    la = PipelineLogAggregator()
    la.info("s", "m1")
    stats = la.get_stats()
    assert stats["current_entries"] == 1
    assert stats["total_logged"] == 1
    print("OK: stats")

def test_reset():
    la = PipelineLogAggregator()
    la.info("s", "m")
    la.reset()
    assert la.query() == []
    assert la.get_stats()["total_logged"] == 0
    print("OK: reset")

def main():
    print("=== Pipeline Log Aggregator Tests ===\n")
    test_log()
    test_invalid_log()
    test_level_shortcuts()
    test_min_level()
    test_set_min_level()
    test_max_entries()
    test_query_source()
    test_query_level()
    test_query_min_level()
    test_query_search()
    test_query_tag()
    test_query_limit()
    test_get_sources()
    test_level_counts()
    test_clear()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")

if __name__ == "__main__":
    main()
