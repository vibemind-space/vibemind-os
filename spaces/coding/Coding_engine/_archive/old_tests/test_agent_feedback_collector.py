"""Test agent feedback collector."""
import sys
sys.path.insert(0, ".")

from src.services.agent_feedback_collector import AgentFeedbackCollector


def test_submit_feedback():
    """Submit and retrieve feedback."""
    fc = AgentFeedbackCollector()
    fid = fc.submit_feedback("agent-1", "build_module", 4,
                             category="code_quality", comment="Good work",
                             tags=["review"])
    assert fid.startswith("fb-")

    f = fc.get_feedback(fid)
    assert f is not None
    assert f["agent"] == "agent-1"
    assert f["target"] == "build_module"
    assert f["rating"] == 4
    assert f["category"] == "code_quality"
    assert f["comment"] == "Good work"

    assert fc.remove_feedback(fid) is True
    assert fc.remove_feedback(fid) is False
    print("OK: submit feedback")


def test_invalid_feedback():
    """Invalid feedback rejected."""
    fc = AgentFeedbackCollector()
    assert fc.submit_feedback("", "t", 3) == ""
    assert fc.submit_feedback("a", "", 3) == ""
    assert fc.submit_feedback("a", "t", 0) == ""
    assert fc.submit_feedback("a", "t", 6) == ""
    assert fc.submit_feedback("a", "t", 3, category="invalid") == ""
    print("OK: invalid feedback")


def test_create_survey():
    """Create and remove survey."""
    fc = AgentFeedbackCollector()
    sid = fc.create_survey("sprint_retro",
                           questions=["What went well?", "What to improve?"],
                           category="process", tags=["sprint"])
    assert sid.startswith("srv-")

    s = fc.get_survey(sid)
    assert s is not None
    assert s["name"] == "sprint_retro"
    assert len(s["questions"]) == 2
    assert s["category"] == "process"
    assert s["response_count"] == 0

    assert fc.remove_survey(sid) is True
    assert fc.remove_survey(sid) is False
    print("OK: create survey")


def test_invalid_survey():
    """Invalid survey rejected."""
    fc = AgentFeedbackCollector()
    assert fc.create_survey("") == ""
    assert fc.create_survey("x", category="invalid") == ""
    print("OK: invalid survey")


def test_max_surveys():
    """Max surveys enforced."""
    fc = AgentFeedbackCollector(max_surveys=2)
    fc.create_survey("a")
    fc.create_survey("b")
    assert fc.create_survey("c") == ""
    print("OK: max surveys")


def test_survey_response():
    """Respond to survey."""
    fc = AgentFeedbackCollector()
    sid = fc.create_survey("test", questions=["Q1?"])

    rid = fc.respond_to_survey(sid, "agent-1",
                               answers={"Q1?": "Great"}, rating=5)
    assert rid.startswith("sresp-")

    assert fc.get_survey(sid)["response_count"] == 1

    resps = fc.get_survey_responses(sid)
    assert len(resps) == 1
    assert resps[0]["agent"] == "agent-1"
    assert resps[0]["rating"] == 5
    print("OK: survey response")


def test_invalid_survey_response():
    """Invalid survey response rejected."""
    fc = AgentFeedbackCollector()
    sid = fc.create_survey("test")

    assert fc.respond_to_survey("nonexistent", "a") == ""
    assert fc.respond_to_survey(sid, "") == ""
    assert fc.respond_to_survey(sid, "a", rating=0) == ""
    print("OK: invalid survey response")


def test_search_feedback():
    """Search feedback with filters."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("agent-1", "mod_a", 4, category="code_quality", tags=["ci"])
    fc.submit_feedback("agent-2", "mod_b", 2, category="performance")
    fc.submit_feedback("agent-1", "mod_c", 5, category="code_quality")

    by_agent = fc.search_feedback(agent="agent-1")
    assert len(by_agent) == 2

    by_target = fc.search_feedback(target="mod_b")
    assert len(by_target) == 1

    by_cat = fc.search_feedback(category="code_quality")
    assert len(by_cat) == 2

    by_tag = fc.search_feedback(tag="ci")
    assert len(by_tag) == 1

    by_rating = fc.search_feedback(min_rating=4)
    assert len(by_rating) == 2
    print("OK: search feedback")


def test_search_limit():
    """Search respects limit."""
    fc = AgentFeedbackCollector()
    for i in range(20):
        fc.submit_feedback("a", f"t-{i}", 3)

    results = fc.search_feedback(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_average_rating():
    """Get average rating."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("a", "mod", 4)
    fc.submit_feedback("b", "mod", 2)

    avg = fc.get_average_rating(target="mod")
    assert avg == 3.0

    avg_all = fc.get_average_rating()
    assert avg_all == 3.0

    avg_none = fc.get_average_rating(target="nonexistent")
    assert avg_none == 0.0
    print("OK: average rating")


def test_rating_distribution():
    """Get rating distribution."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("a", "x", 5)
    fc.submit_feedback("b", "x", 5)
    fc.submit_feedback("c", "x", 3)
    fc.submit_feedback("d", "x", 1)

    dist = fc.get_rating_distribution(target="x")
    assert dist[5] == 2
    assert dist[3] == 1
    assert dist[1] == 1
    assert dist[2] == 0
    assert dist[4] == 0
    print("OK: rating distribution")


def test_top_targets():
    """Get top-rated targets."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("a", "good_mod", 5)
    fc.submit_feedback("b", "good_mod", 4)
    fc.submit_feedback("a", "bad_mod", 1)
    fc.submit_feedback("b", "bad_mod", 2)

    tops = fc.get_top_targets()
    assert len(tops) == 2
    assert tops[0]["target"] == "good_mod"
    assert tops[0]["avg_rating"] == 4.5
    print("OK: top targets")


def test_worst_targets():
    """Get worst-rated targets."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("a", "good_mod", 5)
    fc.submit_feedback("b", "bad_mod", 1)

    worsts = fc.get_worst_targets()
    assert len(worsts) == 2
    assert worsts[0]["target"] == "bad_mod"
    print("OK: worst targets")


def test_agent_feedback_summary():
    """Get agent feedback summary."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("alice", "bob", 4)
    fc.submit_feedback("alice", "charlie", 5)
    fc.submit_feedback("bob", "alice", 3)

    summary = fc.get_agent_feedback_summary("alice")
    assert summary["feedback_given"] == 2
    assert summary["avg_rating_given"] == 4.5
    assert summary["feedback_received"] == 1
    assert summary["avg_rating_received"] == 3.0
    print("OK: agent feedback summary")


def test_list_surveys():
    """List surveys with filters."""
    fc = AgentFeedbackCollector()
    fc.create_survey("a", category="process", tags=["sprint"])
    fc.create_survey("b", category="code_quality")

    all_s = fc.list_surveys()
    assert len(all_s) == 2

    by_cat = fc.list_surveys(category="process")
    assert len(by_cat) == 1

    by_tag = fc.list_surveys(tag="sprint")
    assert len(by_tag) == 1
    print("OK: list surveys")


def test_feedback_callback():
    """Callback fires on feedback submission."""
    fc = AgentFeedbackCollector()
    fired = []
    fc.on_change("mon", lambda a, d: fired.append(a))

    fc.submit_feedback("a", "t", 3)
    assert "feedback_submitted" in fired
    print("OK: feedback callback")


def test_callbacks():
    """Callback registration."""
    fc = AgentFeedbackCollector()
    assert fc.on_change("mon", lambda a, d: None) is True
    assert fc.on_change("mon", lambda a, d: None) is False
    assert fc.remove_callback("mon") is True
    assert fc.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("a", "t", 3)
    sid = fc.create_survey("s")
    fc.respond_to_survey(sid, "a", rating=4)

    stats = fc.get_stats()
    assert stats["total_feedback_submitted"] == 1
    assert stats["total_surveys_created"] == 1
    assert stats["total_responses_collected"] == 1
    assert stats["current_feedback"] == 1
    assert stats["current_surveys"] == 1
    assert stats["current_responses"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    fc = AgentFeedbackCollector()
    fc.submit_feedback("a", "t", 3)
    fc.create_survey("s")

    fc.reset()
    assert fc.search_feedback() == []
    assert fc.list_surveys() == []
    stats = fc.get_stats()
    assert stats["current_feedback"] == 0
    print("OK: reset")


def main():
    print("=== Agent Feedback Collector Tests ===\n")
    test_submit_feedback()
    test_invalid_feedback()
    test_create_survey()
    test_invalid_survey()
    test_max_surveys()
    test_survey_response()
    test_invalid_survey_response()
    test_search_feedback()
    test_search_limit()
    test_average_rating()
    test_rating_distribution()
    test_top_targets()
    test_worst_targets()
    test_agent_feedback_summary()
    test_list_surveys()
    test_feedback_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
