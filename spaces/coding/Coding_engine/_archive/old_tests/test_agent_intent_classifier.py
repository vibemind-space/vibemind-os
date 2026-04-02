"""Test agent intent classifier."""
import sys
sys.path.insert(0, ".")

from src.services.agent_intent_classifier import AgentIntentClassifier


def test_register_intent():
    """Register and retrieve intent."""
    ic = AgentIntentClassifier()
    iid = ic.register_intent("build_project", patterns=["build", "compile"],
                              category="command", action="run_build",
                              min_confidence=0.5, priority=8, tags=["ci"])
    assert iid.startswith("int-")

    i = ic.get_intent(iid)
    assert i is not None
    assert i["name"] == "build_project"
    assert i["category"] == "command"
    assert i["action"] == "run_build"
    assert i["patterns"] == ["build", "compile"]

    assert ic.remove_intent(iid) is True
    assert ic.remove_intent(iid) is False
    print("OK: register intent")


def test_invalid_intent():
    """Invalid intent rejected."""
    ic = AgentIntentClassifier()
    assert ic.register_intent("") == ""
    assert ic.register_intent("x", category="invalid") == ""
    assert ic.register_intent("x", patterns=[]) == ""
    assert ic.register_intent("x") == ""  # no patterns
    print("OK: invalid intent")


def test_duplicate_name():
    """Duplicate name rejected."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build"])
    assert ic.register_intent("build", patterns=["build"]) == ""
    print("OK: duplicate name")


def test_max_intents():
    """Max intents enforced."""
    ic = AgentIntentClassifier(max_intents=2)
    ic.register_intent("a", patterns=["a"])
    ic.register_intent("b", patterns=["b"])
    assert ic.register_intent("c", patterns=["c"]) == ""
    print("OK: max intents")


def test_classify_match():
    """Classify text with match."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build", "compile"],
                        category="command", action="run_build", min_confidence=0.5)

    result = ic.classify("please build the project", agent="agent_a")
    assert result is not None
    assert result["intent_name"] == "build"
    assert result["action"] == "run_build"
    assert result["confidence"] >= 0.5
    print("OK: classify match")


def test_classify_no_match():
    """Classify text with no match."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build", "compile"],
                        min_confidence=1.0)  # requires all patterns

    result = ic.classify("deploy the app")
    assert result is None
    print("OK: classify no match")


def test_classify_best_match():
    """Classify picks best matching intent."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build", "compile"], action="build",
                        min_confidence=0.5)
    ic.register_intent("build_test", patterns=["build", "test"], action="build_test",
                        min_confidence=0.5)

    # "build and test" matches build_test at 1.0 (2/2) vs build at 0.5 (1/2)
    result = ic.classify("build and test the project")
    assert result is not None
    assert result["action"] == "build_test"
    print("OK: classify best match")


def test_classify_multi():
    """Get multiple matches ranked."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build"], min_confidence=0.5)
    ic.register_intent("test", patterns=["test"], min_confidence=0.5)
    ic.register_intent("deploy", patterns=["deploy"], min_confidence=0.5)

    matches = ic.classify_multi("build and test everything")
    assert len(matches) == 2  # build + test match
    assert matches[0]["confidence"] >= matches[1]["confidence"] if len(matches) > 1 else True
    print("OK: classify multi")


def test_case_insensitive():
    """Classification is case insensitive."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["BUILD", "compile"])

    result = ic.classify("build the Project")
    assert result is not None
    print("OK: case insensitive")


def test_update_intent():
    """Update intent properties."""
    ic = AgentIntentClassifier()
    iid = ic.register_intent("build", patterns=["build"], action="old")

    assert ic.update_intent(iid, patterns=["build", "make"], action="new",
                             min_confidence=0.8, priority=10) is True
    i = ic.get_intent(iid)
    assert i["patterns"] == ["build", "make"]
    assert i["action"] == "new"
    assert i["min_confidence"] == 0.8
    assert i["priority"] == 10
    print("OK: update intent")


def test_get_by_name():
    """Get intent by name."""
    ic = AgentIntentClassifier()
    ic.register_intent("my_intent", patterns=["test"])

    i = ic.get_intent_by_name("my_intent")
    assert i is not None
    assert i["name"] == "my_intent"
    assert ic.get_intent_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_intents():
    """List intents with filters."""
    ic = AgentIntentClassifier()
    ic.register_intent("a", patterns=["a"], category="command", tags=["ci"])
    ic.register_intent("b", patterns=["b"], category="query")

    all_i = ic.list_intents()
    assert len(all_i) == 2

    by_cat = ic.list_intents(category="command")
    assert len(by_cat) == 1

    by_tag = ic.list_intents(tag="ci")
    assert len(by_tag) == 1
    print("OK: list intents")


def test_search_classifications():
    """Search classification history."""
    ic = AgentIntentClassifier()
    iid = ic.register_intent("build", patterns=["build"])
    ic.classify("build it", agent="agent_a")
    ic.classify("build again", agent="agent_b")

    all_c = ic.search_classifications()
    assert len(all_c) == 2

    by_intent = ic.search_classifications(intent_id=iid)
    assert len(by_intent) == 2

    by_agent = ic.search_classifications(agent="agent_a")
    assert len(by_agent) == 1
    print("OK: search classifications")


def test_get_classification():
    """Get specific classification."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build"])
    result = ic.classify("build it")
    assert result is not None

    c = ic.get_classification(result["classification_id"])
    assert c is not None
    assert c["input_text"] == "build it"
    print("OK: get classification")


def test_remove_cascades():
    """Remove intent cascades to classifications."""
    ic = AgentIntentClassifier()
    iid = ic.register_intent("build", patterns=["build"])
    ic.classify("build it")

    ic.remove_intent(iid)
    assert ic.search_classifications(intent_id=iid) == []
    print("OK: remove cascades")


def test_callback():
    """Callback fires on events."""
    ic = AgentIntentClassifier()
    fired = []
    ic.on_change("mon", lambda a, d: fired.append(a))

    iid = ic.register_intent("build", patterns=["build"])
    assert "intent_registered" in fired

    ic.classify("build it")
    assert "intent_classified" in fired

    ic.classify("deploy now")
    assert "intent_unmatched" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    ic = AgentIntentClassifier()
    assert ic.on_change("mon", lambda a, d: None) is True
    assert ic.on_change("mon", lambda a, d: None) is False
    assert ic.remove_callback("mon") is True
    assert ic.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build"])
    ic.classify("build it")  # match
    ic.classify("deploy now")  # no match

    stats = ic.get_stats()
    assert stats["total_intents"] == 1
    assert stats["total_classifications"] == 2
    assert stats["total_matched"] == 1
    assert stats["total_unmatched"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ic = AgentIntentClassifier()
    ic.register_intent("build", patterns=["build"])
    ic.classify("build it")

    ic.reset()
    assert ic.list_intents() == []
    assert ic.search_classifications() == []
    stats = ic.get_stats()
    assert stats["current_intents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Intent Classifier Tests ===\n")
    test_register_intent()
    test_invalid_intent()
    test_duplicate_name()
    test_max_intents()
    test_classify_match()
    test_classify_no_match()
    test_classify_best_match()
    test_classify_multi()
    test_case_insensitive()
    test_update_intent()
    test_get_by_name()
    test_list_intents()
    test_search_classifications()
    test_get_classification()
    test_remove_cascades()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
