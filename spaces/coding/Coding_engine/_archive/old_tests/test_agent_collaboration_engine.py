"""Test agent collaboration engine."""
import sys
sys.path.insert(0, ".")

from src.services.agent_collaboration_engine import AgentCollaborationEngine


def test_create_session():
    """Create and retrieve session."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("Design Review", topic="API design",
                            tags=["sprint1"])
    assert sid.startswith("collab-")

    s = ce.get_session(sid)
    assert s is not None
    assert s["name"] == "Design Review"
    assert s["topic"] == "API design"
    assert s["status"] == "active"
    assert s["participants"] == []

    assert ce.remove_session(sid) is True
    assert ce.remove_session(sid) is False
    print("OK: create session")


def test_invalid_session():
    """Invalid session rejected."""
    ce = AgentCollaborationEngine()
    assert ce.create_session("") == ""
    print("OK: invalid session")


def test_max_sessions():
    """Max sessions enforced."""
    ce = AgentCollaborationEngine(max_sessions=2)
    ce.create_session("a")
    ce.create_session("b")
    assert ce.create_session("c") == ""
    print("OK: max sessions")


def test_join_leave():
    """Join and leave session."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")

    assert ce.join_session(sid, "agent_a") is True
    assert ce.join_session(sid, "agent_a") is False  # duplicate
    assert ce.join_session(sid, "agent_b") is True

    s = ce.get_session(sid)
    assert len(s["participants"]) == 2

    assert ce.leave_session(sid, "agent_a") is True
    assert ce.leave_session(sid, "agent_a") is False
    print("OK: join leave")


def test_max_participants():
    """Max participants enforced."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test", max_participants=2)
    ce.join_session(sid, "a")
    ce.join_session(sid, "b")
    assert ce.join_session(sid, "c") is False
    print("OK: max participants")


def test_pause_resume():
    """Pause and resume session."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")

    assert ce.pause_session(sid) is True
    assert ce.get_session(sid)["status"] == "paused"
    assert ce.pause_session(sid) is False

    assert ce.resume_session(sid) is True
    assert ce.get_session(sid)["status"] == "active"
    assert ce.resume_session(sid) is False
    print("OK: pause resume")


def test_complete_session():
    """Complete session."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")

    assert ce.complete_session(sid) is True
    assert ce.get_session(sid)["status"] == "completed"
    assert ce.complete_session(sid) is False
    print("OK: complete session")


def test_cancel_session():
    """Cancel session."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")

    assert ce.cancel_session(sid) is True
    assert ce.get_session(sid)["status"] == "cancelled"
    assert ce.cancel_session(sid) is False
    print("OK: cancel session")


def test_search_sessions():
    """Search sessions."""
    ce = AgentCollaborationEngine()
    s1 = ce.create_session("a", tags=["t1"])
    ce.join_session(s1, "agent_a")
    s2 = ce.create_session("b")
    ce.complete_session(s2)

    all_s = ce.search_sessions()
    assert len(all_s) == 2

    by_status = ce.search_sessions(status="completed")
    assert len(by_status) == 1

    by_tag = ce.search_sessions(tag="t1")
    assert len(by_tag) == 1

    by_participant = ce.search_sessions(participant="agent_a")
    assert len(by_participant) == 1
    print("OK: search sessions")


def test_share_artifact():
    """Share artifact."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")

    aid = ce.share_artifact(sid, "design.md", "# Design\n...",
                             author="agent_a", artifact_type="doc")
    assert aid.startswith("art-")

    a = ce.get_artifact(aid)
    assert a is not None
    assert a["name"] == "design.md"
    assert a["artifact_type"] == "doc"
    print("OK: share artifact")


def test_invalid_artifact():
    """Invalid artifact rejected."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")
    assert ce.share_artifact(sid, "", "content") == ""
    assert ce.share_artifact(sid, "name", "content", artifact_type="invalid") == ""
    assert ce.share_artifact("nonexistent", "name", "content") == ""
    print("OK: invalid artifact")


def test_session_artifacts():
    """Get session artifacts."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")
    ce.share_artifact(sid, "a.py", "code", artifact_type="code")
    ce.share_artifact(sid, "notes.md", "text", artifact_type="note")

    all_a = ce.get_session_artifacts(sid)
    assert len(all_a) == 2

    code_only = ce.get_session_artifacts(sid, artifact_type="code")
    assert len(code_only) == 1
    print("OK: session artifacts")


def test_cast_vote():
    """Cast vote."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")

    vid = ce.cast_vote(sid, "Use REST API", "agent_a", choice="approve",
                        reason="simpler")
    assert vid.startswith("vote-")

    # Duplicate vote rejected
    assert ce.cast_vote(sid, "Use REST API", "agent_a", choice="reject") == ""
    print("OK: cast vote")


def test_invalid_vote():
    """Invalid vote rejected."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")
    assert ce.cast_vote(sid, "", "voter", "approve") == ""
    assert ce.cast_vote(sid, "prop", "", "approve") == ""
    assert ce.cast_vote(sid, "prop", "voter", "invalid") == ""
    print("OK: invalid vote")


def test_vote_results():
    """Get vote results."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")
    ce.cast_vote(sid, "Use REST", "a", "approve")
    ce.cast_vote(sid, "Use REST", "b", "approve")
    ce.cast_vote(sid, "Use REST", "c", "reject")

    results = ce.get_vote_results(sid, "Use REST")
    assert results["approve"] == 2
    assert results["reject"] == 1
    assert results["total_votes"] == 3
    assert results["approved"] is True
    print("OK: vote results")


def test_remove_cascades():
    """Remove session cascades to artifacts and votes."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")
    ce.share_artifact(sid, "a", "content")
    ce.cast_vote(sid, "prop", "voter", "approve")

    ce.remove_session(sid)
    assert ce.get_session_artifacts(sid) == []
    assert ce.get_session_votes(sid) == []
    print("OK: remove cascades")


def test_callback():
    """Callback fires on events."""
    ce = AgentCollaborationEngine()
    fired = []
    ce.on_change("mon", lambda a, d: fired.append(a))

    sid = ce.create_session("test")
    assert "session_created" in fired

    ce.join_session(sid, "agent_a")
    assert "agent_joined" in fired

    ce.share_artifact(sid, "a", "content")
    assert "artifact_shared" in fired

    ce.cast_vote(sid, "prop", "voter", "approve")
    assert "vote_cast" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    ce = AgentCollaborationEngine()
    assert ce.on_change("mon", lambda a, d: None) is True
    assert ce.on_change("mon", lambda a, d: None) is False
    assert ce.remove_callback("mon") is True
    assert ce.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")
    ce.share_artifact(sid, "a", "c")
    ce.cast_vote(sid, "p", "v", "approve")
    ce.complete_session(sid)

    stats = ce.get_stats()
    assert stats["total_sessions"] == 1
    assert stats["total_artifacts"] == 1
    assert stats["total_votes"] == 1
    assert stats["total_completed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ce = AgentCollaborationEngine()
    sid = ce.create_session("test")
    ce.share_artifact(sid, "a", "c")

    ce.reset()
    assert ce.search_sessions() == []
    stats = ce.get_stats()
    assert stats["current_sessions"] == 0
    print("OK: reset")


def main():
    print("=== Agent Collaboration Engine Tests ===\n")
    test_create_session()
    test_invalid_session()
    test_max_sessions()
    test_join_leave()
    test_max_participants()
    test_pause_resume()
    test_complete_session()
    test_cancel_session()
    test_search_sessions()
    test_share_artifact()
    test_invalid_artifact()
    test_session_artifacts()
    test_cast_vote()
    test_invalid_vote()
    test_vote_results()
    test_remove_cascades()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
