"""Test pipeline error classifier."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_error_classifier import PipelineErrorClassifier


def test_default_rules():
    """Default rules are installed."""
    c = PipelineErrorClassifier()
    rules = c.list_rules()
    assert len(rules) >= 10  # At least 10 default rules
    print("OK: default rules")


def test_classify_syntax():
    """Classify syntax errors."""
    c = PipelineErrorClassifier()
    result = c.classify("SyntaxError: unexpected token '}'", source="compiler")
    assert result["classified"] is True
    assert result["category"] == "syntax"
    assert result["severity"] == "high"
    assert result["error_id"].startswith("err-")
    print("OK: classify syntax")


def test_classify_timeout():
    """Classify timeout errors."""
    c = PipelineErrorClassifier()
    result = c.classify("Request timed out after 30s")
    assert result["classified"] is True
    assert result["category"] == "timeout"
    assert result["recovery_action"] == "increase_timeout"
    print("OK: classify timeout")


def test_classify_network():
    """Classify network errors."""
    c = PipelineErrorClassifier()
    result = c.classify("Connection refused on port 8080")
    assert result["classified"] is True
    assert result["category"] == "network"
    print("OK: classify network")


def test_classify_resource():
    """Classify resource errors."""
    c = PipelineErrorClassifier()
    result = c.classify("Out of memory error: heap space exceeded")
    assert result["classified"] is True
    assert result["category"] == "resource"
    assert result["severity"] == "critical"
    print("OK: classify resource")


def test_classify_permission():
    """Classify permission errors."""
    c = PipelineErrorClassifier()
    result = c.classify("Permission denied: /var/log/app.log")
    assert result["classified"] is True
    assert result["category"] == "permission"
    print("OK: classify permission")


def test_classify_import():
    """Classify import/dependency errors."""
    c = PipelineErrorClassifier()
    result = c.classify("ImportError: No module named 'flask'")
    assert result["classified"] is True
    assert result["category"] == "dependency"
    print("OK: classify import")


def test_classify_unknown():
    """Unknown errors are unclassified."""
    c = PipelineErrorClassifier()
    result = c.classify("Something weird happened in sector 7G")
    assert result["classified"] is False
    assert result["category"] == "unknown"
    assert result["recovery_action"] == "investigate"
    print("OK: classify unknown")


def test_classify_empty():
    """Empty message."""
    c = PipelineErrorClassifier()
    result = c.classify("")
    assert result["classified"] is False
    assert result["error_id"] == ""
    print("OK: classify empty")


def test_add_custom_rule():
    """Add custom classification rules."""
    c = PipelineErrorClassifier()
    rid = c.add_rule("CustomDB", r"(?i)database\s*locked", "runtime", "high",
                     recovery_action="retry_with_backoff", priority=90)
    assert rid.startswith("rule-")

    result = c.classify("Database locked during write")
    assert result["classified"] is True
    assert result["category"] == "runtime"
    assert result["matched_rule"] == rid
    print("OK: add custom rule")


def test_rule_priority():
    """Higher priority rules match first."""
    c = PipelineErrorClassifier()
    r1 = c.add_rule("LowPri", r"error", "unknown", "low", priority=10)
    r2 = c.add_rule("HighPri", r"error", "runtime", "high", priority=100)

    result = c.classify("some error occurred")
    assert result["matched_rule"] == r2
    assert result["category"] == "runtime"
    print("OK: rule priority")


def test_invalid_rule():
    """Invalid rules rejected."""
    c = PipelineErrorClassifier()
    assert c.add_rule("Bad", r"[invalid", "syntax", "high") == ""  # Bad regex
    assert c.add_rule("Bad", r"ok", "nonexistent_cat", "high") == ""
    assert c.add_rule("Bad", r"ok", "syntax", "nonexistent_sev") == ""
    print("OK: invalid rule")


def test_remove_rule():
    """Remove a rule."""
    c = PipelineErrorClassifier()
    rid = c.add_rule("Test", r"test", "runtime", "low")
    assert c.remove_rule(rid) is True
    assert c.remove_rule(rid) is False
    print("OK: remove rule")


def test_get_error():
    """Get classified error record."""
    c = PipelineErrorClassifier()
    result = c.classify("SyntaxError: bad token", source="parser")
    eid = result["error_id"]

    err = c.get_error(eid)
    assert err is not None
    assert err["source"] == "parser"
    assert err["category"] == "syntax"
    assert c.get_error("fake") is None
    print("OK: get error")


def test_list_errors():
    """List errors with filters."""
    c = PipelineErrorClassifier()
    c.classify("SyntaxError: bad", source="A")
    c.classify("Timeout occurred", source="B")
    c.classify("Connection refused", source="A")

    all_errs = c.list_errors()
    assert len(all_errs) == 3

    syntax = c.list_errors(category="syntax")
    assert len(syntax) == 1

    source_a = c.list_errors(source="A")
    assert len(source_a) == 2
    print("OK: list errors")


def test_search_errors():
    """Search errors by message."""
    c = PipelineErrorClassifier()
    c.classify("SyntaxError: unexpected '}'")
    c.classify("Timeout after 30s")

    results = c.search_errors("syntax")
    assert len(results) == 1
    print("OK: search errors")


def test_delete_error():
    """Delete error record."""
    c = PipelineErrorClassifier()
    result = c.classify("SyntaxError: bad")
    eid = result["error_id"]

    assert c.delete_error(eid) is True
    assert c.delete_error(eid) is False
    print("OK: delete error")


def test_classify_batch():
    """Batch classification."""
    c = PipelineErrorClassifier()
    results = c.classify_batch([
        "SyntaxError: bad token",
        "Timeout occurred",
        "unknown issue",
    ])
    assert len(results) == 3
    assert results[0]["category"] == "syntax"
    assert results[1]["category"] == "timeout"
    assert results[2]["classified"] is False
    print("OK: classify batch")


def test_category_counts():
    """Count by category."""
    c = PipelineErrorClassifier()
    c.classify("SyntaxError: bad")
    c.classify("SyntaxError: worse")
    c.classify("Timeout happened")

    counts = c.get_category_counts()
    assert counts["syntax"] == 2
    assert counts["timeout"] == 1
    print("OK: category counts")


def test_severity_counts():
    """Count by severity."""
    c = PipelineErrorClassifier()
    c.classify("Out of memory")  # critical
    c.classify("Timeout")        # medium

    counts = c.get_severity_counts()
    assert "critical" in counts
    assert "medium" in counts
    print("OK: severity counts")


def test_top_rules():
    """Get most matched rules."""
    c = PipelineErrorClassifier()
    c.classify("SyntaxError: a")
    c.classify("SyntaxError: b")
    c.classify("SyntaxError: c")
    c.classify("Timeout")

    top = c.get_top_rules(limit=3)
    assert len(top) >= 1
    assert top[0]["match_count"] >= 3
    print("OK: top rules")


def test_source_counts():
    """Count by source."""
    c = PipelineErrorClassifier()
    c.classify("SyntaxError", source="compiler")
    c.classify("Timeout", source="network")
    c.classify("Error", source="compiler")

    counts = c.get_source_counts()
    assert counts["compiler"] == 2
    assert counts["network"] == 1
    print("OK: source counts")


def test_callbacks():
    """Error callbacks fire."""
    c = PipelineErrorClassifier()
    fired = []
    assert c.on_error("mon", lambda eid, cat, sev: fired.append((cat, sev))) is True
    assert c.on_error("mon", lambda e, c, s: None) is False

    c.classify("SyntaxError: bad")
    assert len(fired) == 1
    assert fired[0] == ("syntax", "high")

    assert c.remove_callback("mon") is True
    assert c.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    c = PipelineErrorClassifier()
    c.classify("SyntaxError: bad")  # classified
    c.classify("random gibberish")  # unclassified

    stats = c.get_stats()
    assert stats["total_classified"] == 1
    assert stats["total_unclassified"] == 1
    assert stats["total_errors"] == 2
    assert stats["classification_rate"] == 50.0
    print("OK: stats")


def test_reset():
    """Reset reinstalls defaults."""
    c = PipelineErrorClassifier()
    c.classify("SyntaxError: bad")

    c.reset()
    assert c.list_errors() == []
    rules = c.list_rules()
    assert len(rules) >= 10  # Defaults reinstalled
    stats = c.get_stats()
    assert stats["total_errors"] == 0
    assert stats["total_classified"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Error Classifier Tests ===\n")
    test_default_rules()
    test_classify_syntax()
    test_classify_timeout()
    test_classify_network()
    test_classify_resource()
    test_classify_permission()
    test_classify_import()
    test_classify_unknown()
    test_classify_empty()
    test_add_custom_rule()
    test_rule_priority()
    test_invalid_rule()
    test_remove_rule()
    test_get_error()
    test_list_errors()
    test_search_errors()
    test_delete_error()
    test_classify_batch()
    test_category_counts()
    test_severity_counts()
    test_top_rules()
    test_source_counts()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 25 TESTS PASSED ===")


if __name__ == "__main__":
    main()
