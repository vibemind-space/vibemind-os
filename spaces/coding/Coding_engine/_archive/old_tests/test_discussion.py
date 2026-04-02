"""Test minibook discussion resolution system."""
import asyncio
import sys
sys.path.insert(0, ".")

from src.mind.event_bus import EventBus, Event, EventType
from src.services.minibook_discussion import (
    DiscussionManager,
    DiscussionOption,
    DiscussionStatus,
    ResolutionStrategy,
)


def make_bus():
    return EventBus()


async def test_create_discussion():
    """Can create a discussion and it appears in listings."""
    bus = make_bus()
    mgr = DiscussionManager(bus)

    d = await mgr.create_discussion(
        title="Test Discussion",
        context="Something happened",
        trigger_event="test_event",
        participants=["AgentA", "AgentB"],
        options=[
            DiscussionOption("opt1", "Option 1", "First option", "AgentA"),
            DiscussionOption("opt2", "Option 2", "Second option", "AgentB"),
        ],
    )

    assert d.discussion_id == "disc-0001"
    assert d.status == DiscussionStatus.OPEN
    assert len(d.options) == 2

    listings = mgr.list_discussions()
    assert len(listings) == 1
    assert listings[0]["discussion_id"] == "disc-0001"
    print("OK: create discussion")


async def test_vote_majority():
    """VOTE strategy resolves by majority."""
    bus = make_bus()
    mgr = DiscussionManager(bus, default_strategy=ResolutionStrategy.VOTE)

    d = await mgr.create_discussion(
        title="Vote Test",
        context="ctx",
        trigger_event="test",
        participants=["A", "B", "C"],
        options=[
            DiscussionOption("fix", "Fix", "Fix it", "A"),
            DiscussionOption("skip", "Skip", "Skip it", "B"),
        ],
    )

    await mgr.cast_vote(d.discussion_id, "A", "fix", "I want fix")
    await mgr.cast_vote(d.discussion_id, "B", "skip", "I want skip")
    await mgr.cast_vote(d.discussion_id, "C", "fix", "I also want fix")

    # All voted -> auto-resolved
    assert d.status == DiscussionStatus.RESOLVED
    assert d.resolution == "fix"
    assert "2 votes" in d.resolution_reason
    print("OK: vote majority resolution")


async def test_duplicate_vote_rejected():
    """Same agent can't vote twice."""
    bus = make_bus()
    mgr = DiscussionManager(bus)

    d = await mgr.create_discussion(
        title="Dup Vote",
        context="ctx",
        trigger_event="test",
        participants=["A", "B"],
        options=[
            DiscussionOption("opt1", "O1", "d1", "A"),
            DiscussionOption("opt2", "O2", "d2", "B"),
        ],
    )

    ok1 = await mgr.cast_vote(d.discussion_id, "A", "opt1", "first")
    ok2 = await mgr.cast_vote(d.discussion_id, "A", "opt2", "second try")

    assert ok1 is True
    assert ok2 is False
    assert len(d.votes) == 1
    print("OK: duplicate vote rejected")


async def test_consensus_strategy():
    """CONSENSUS requires all agents to agree on same option."""
    bus = make_bus()
    mgr = DiscussionManager(bus, default_strategy=ResolutionStrategy.CONSENSUS)

    d = await mgr.create_discussion(
        title="Consensus Test",
        context="ctx",
        trigger_event="test",
        participants=["A", "B"],
        options=[
            DiscussionOption("opt1", "O1", "d1", "A"),
            DiscussionOption("opt2", "O2", "d2", "B"),
        ],
    )

    await mgr.cast_vote(d.discussion_id, "A", "opt1", "I pick opt1")
    await mgr.cast_vote(d.discussion_id, "B", "opt1", "I also pick opt1")

    assert d.status == DiscussionStatus.RESOLVED
    assert d.resolution == "opt1"
    assert "consensus" in d.resolution_reason.lower()
    print("OK: consensus resolution")


async def test_consensus_fails_on_disagreement():
    """CONSENSUS with disagreement -> no resolution."""
    bus = make_bus()
    mgr = DiscussionManager(bus, default_strategy=ResolutionStrategy.CONSENSUS)

    d = await mgr.create_discussion(
        title="No Consensus",
        context="ctx",
        trigger_event="test",
        participants=["A", "B"],
        options=[
            DiscussionOption("opt1", "O1", "d1", "A"),
            DiscussionOption("opt2", "O2", "d2", "B"),
        ],
    )

    await mgr.cast_vote(d.discussion_id, "A", "opt1", "pick1")
    await mgr.cast_vote(d.discussion_id, "B", "opt2", "pick2")

    assert d.status == DiscussionStatus.RESOLVED
    assert d.resolution is None or "no consensus" in d.resolution_reason.lower()
    print("OK: consensus fails on disagreement")


async def test_moderator_strategy():
    """MODERATOR strategy uses Orchestrator's vote."""
    bus = make_bus()
    mgr = DiscussionManager(bus, default_strategy=ResolutionStrategy.MODERATOR)

    d = await mgr.create_discussion(
        title="Moderator Test",
        context="ctx",
        trigger_event="test",
        participants=["AgentX", "Orchestrator"],
        options=[
            DiscussionOption("opt1", "O1", "d1", "AgentX"),
            DiscussionOption("opt2", "O2", "d2", "Orchestrator"),
        ],
    )

    await mgr.cast_vote(d.discussion_id, "AgentX", "opt1", "I vote opt1")
    await mgr.cast_vote(d.discussion_id, "Orchestrator", "opt2", "I decide opt2")

    assert d.status == DiscussionStatus.RESOLVED
    assert d.resolution == "opt2"
    assert "moderator" in d.resolution_reason.lower()
    print("OK: moderator resolution")


async def test_timeout_resolution():
    """Discussion times out and resolves with available votes."""
    bus = make_bus()
    mgr = DiscussionManager(bus, default_timeout=0.3)

    d = await mgr.create_discussion(
        title="Timeout Test",
        context="ctx",
        trigger_event="test",
        participants=["A", "B", "C"],
        options=[
            DiscussionOption("opt1", "O1", "d1", "A"),
            DiscussionOption("opt2", "O2", "d2", "B"),
        ],
    )

    # Only one agent votes
    await mgr.cast_vote(d.discussion_id, "A", "opt1", "my vote")

    # Wait for timeout
    await asyncio.sleep(0.5)

    assert d.status == DiscussionStatus.RESOLVED
    assert d.resolution == "opt1"
    print("OK: timeout resolution with partial votes")


async def test_timeout_no_votes():
    """Discussion times out with no votes -> default first option."""
    bus = make_bus()
    mgr = DiscussionManager(bus, default_timeout=0.2)

    d = await mgr.create_discussion(
        title="No Votes Timeout",
        context="ctx",
        trigger_event="test",
        participants=["A", "B"],
        options=[
            DiscussionOption("opt1", "O1", "d1", "A"),
            DiscussionOption("opt2", "O2", "d2", "B"),
        ],
    )

    await asyncio.sleep(0.4)

    assert d.status == DiscussionStatus.TIMED_OUT
    assert d.resolution == "opt1"
    assert "no votes" in d.resolution_reason.lower()
    print("OK: timeout with no votes defaults to first option")


async def test_resolution_callback():
    """Resolution callback fires when discussion resolves."""
    bus = make_bus()
    mgr = DiscussionManager(bus)

    callback_data = {}

    async def on_resolved(disc):
        callback_data["id"] = disc.discussion_id
        callback_data["resolution"] = disc.resolution

    d = await mgr.create_discussion(
        title="Callback Test",
        context="ctx",
        trigger_event="test",
        participants=["A"],
        options=[
            DiscussionOption("opt1", "O1", "d1", "A"),
        ],
    )

    mgr.on_resolution(d.discussion_id, on_resolved)
    await mgr.cast_vote(d.discussion_id, "A", "opt1", "only vote")

    assert callback_data.get("id") == d.discussion_id
    assert callback_data.get("resolution") == "opt1"
    print("OK: resolution callback fires")


async def test_stats():
    """Stats report correctly."""
    bus = make_bus()
    mgr = DiscussionManager(bus)

    d = await mgr.create_discussion(
        title="Stats Test",
        context="ctx",
        trigger_event="test",
        participants=["A"],
        options=[DiscussionOption("o1", "O1", "d1", "A")],
    )
    await mgr.cast_vote(d.discussion_id, "A", "o1", "vote")

    stats = mgr.get_stats()
    assert stats["total_discussions"] == 1
    assert stats["total_votes"] == 1
    assert stats["by_status"]["resolved"] == 1
    print("OK: stats reporting")


async def test_to_dict():
    """Discussion serializes to dict correctly."""
    bus = make_bus()
    mgr = DiscussionManager(bus)

    d = await mgr.create_discussion(
        title="Dict Test",
        context="ctx",
        trigger_event="test",
        participants=["A"],
        options=[DiscussionOption("o1", "O1", "d1", "A")],
    )

    data = d.to_dict()
    assert data["title"] == "Dict Test"
    assert data["strategy"] == "vote"
    assert data["status"] == "open"
    assert len(data["options"]) == 1
    assert data["options"][0]["id"] == "o1"
    print("OK: to_dict serialization")


async def main():
    print("=== Discussion Resolution Tests ===\n")
    await test_create_discussion()
    await test_vote_majority()
    await test_duplicate_vote_rejected()
    await test_consensus_strategy()
    await test_consensus_fails_on_disagreement()
    await test_moderator_strategy()
    await test_timeout_resolution()
    await test_timeout_no_votes()
    await test_resolution_callback()
    await test_stats()
    await test_to_dict()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
