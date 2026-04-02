"""
Minibook Discussion Resolution — Structured agent-to-agent discussions with voting.

When agents disagree (e.g., TreeQuest finds an issue but ShinkaEvolve's fix is
debated), this module creates a structured discussion thread in Minibook and
resolves it through agent voting or moderator decision.

Architecture::

    DiscussionTrigger (Event) → DiscussionManager → Minibook Thread
                                                      ├─ Agent A: proposes fix
                                                      ├─ Agent B: objects / agrees
                                                      └─ Resolution: vote or moderator

Resolution strategies:
- VOTE: Agents vote, majority wins
- MODERATOR: A designated agent (e.g., Orchestrator) decides
- TIMEOUT: Auto-resolve after N seconds with default action
- CONSENSUS: All agents must agree

Usage::

    mgr = DiscussionManager(event_bus, minibook_connector)
    mgr.start()

    # Triggered automatically when TREEQUEST_FINDING_CRITICAL + EVOLUTION_FAILED
    # creates a discussion about what to do with the problematic code.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

from ..mind.event_bus import EventBus, Event, EventType

logger = structlog.get_logger(__name__)


class ResolutionStrategy(str, Enum):
    VOTE = "vote"
    MODERATOR = "moderator"
    TIMEOUT = "timeout"
    CONSENSUS = "consensus"


class DiscussionStatus(str, Enum):
    OPEN = "open"
    VOTING = "voting"
    RESOLVED = "resolved"
    TIMED_OUT = "timed_out"


@dataclass
class DiscussionVote:
    """A vote cast by an agent."""
    agent: str
    option: str  # The option voted for
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DiscussionOption:
    """An option proposed in a discussion."""
    option_id: str
    title: str
    description: str
    proposed_by: str
    votes: List[str] = field(default_factory=list)  # Agent names who voted for this


@dataclass
class Discussion:
    """A structured agent-to-agent discussion."""
    discussion_id: str
    title: str
    context: str
    trigger_event: str  # EventType that triggered this
    participants: List[str]
    options: List[DiscussionOption]
    strategy: ResolutionStrategy
    status: DiscussionStatus = DiscussionStatus.OPEN
    votes: List[DiscussionVote] = field(default_factory=list)
    resolution: Optional[str] = None  # Winning option_id
    resolution_reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None
    timeout_seconds: float = 120.0
    minibook_post_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "discussion_id": self.discussion_id,
            "title": self.title,
            "context": self.context,
            "trigger_event": self.trigger_event,
            "participants": self.participants,
            "options": [
                {"id": o.option_id, "title": o.title, "description": o.description,
                 "proposed_by": o.proposed_by, "votes": o.votes}
                for o in self.options
            ],
            "strategy": self.strategy.value,
            "status": self.status.value,
            "votes": [{"agent": v.agent, "option": v.option, "reason": v.reason}
                      for v in self.votes],
            "resolution": self.resolution,
            "resolution_reason": self.resolution_reason,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


class DiscussionManager:
    """
    Manages structured agent-to-agent discussions via Minibook.

    Automatically creates discussions when conflicting events occur,
    collects votes, and resolves based on the chosen strategy.
    """

    def __init__(
        self,
        event_bus: EventBus,
        minibook_connector: Optional[Any] = None,
        default_strategy: ResolutionStrategy = ResolutionStrategy.VOTE,
        default_timeout: float = 120.0,
    ):
        self.event_bus = event_bus
        self.minibook = minibook_connector
        self.default_strategy = default_strategy
        self.default_timeout = default_timeout

        self._discussions: Dict[str, Discussion] = {}
        self._discussion_counter = 0
        self._running = False

        # Resolution callbacks
        self._resolution_callbacks: Dict[str, Callable] = {}

    def start(self):
        """Start listening for discussion-triggering events."""
        self._running = True

        # Auto-trigger discussions on certain event patterns
        self.event_bus.subscribe(
            EventType.TREEQUEST_FINDING_CRITICAL, self._on_critical_finding
        )
        self.event_bus.subscribe(
            EventType.EVOLUTION_FAILED, self._on_evolution_failed
        )

        logger.info("discussion_manager_started")

    async def _on_critical_finding(self, event: Event):
        """Auto-create discussion when TreeQuest finds a critical issue."""
        file_path = event.data.get("file", "unknown")
        description = event.data.get("description", "Critical inconsistency found")
        suggested_fix = event.data.get("suggested_fix", "")

        discussion = await self.create_discussion(
            title=f"Critical Finding: {file_path}",
            context=f"TreeQuest found a critical inconsistency:\n\n{description}",
            trigger_event=event.type.value,
            participants=["TreeQuestVerification", "Fixer", "Builder", "ShinkaEvolveAgent"],
            options=[
                DiscussionOption(
                    option_id="fix_now",
                    title="Fix immediately",
                    description=f"Apply suggested fix: {suggested_fix}" if suggested_fix else "Generate a fix",
                    proposed_by="TreeQuestVerification",
                ),
                DiscussionOption(
                    option_id="evolve",
                    title="Evolve with ShinkaEvolve",
                    description="Use evolutionary algorithm to find an optimal fix",
                    proposed_by="ShinkaEvolveAgent",
                ),
                DiscussionOption(
                    option_id="defer",
                    title="Defer to next iteration",
                    description="Mark as known issue and continue pipeline",
                    proposed_by="Orchestrator",
                ),
            ],
        )

        # Auto-vote for proposing agents
        await self.cast_vote(
            discussion.discussion_id,
            "TreeQuestVerification",
            "fix_now",
            "Detected the issue, recommending immediate fix",
        )

    async def _on_evolution_failed(self, event: Event):
        """Create discussion when ShinkaEvolve can't find a fix."""
        file_path = event.data.get("file", "unknown")
        generations = event.data.get("generations", 0)

        discussion = await self.create_discussion(
            title=f"Evolution Failed: {file_path}",
            context=f"ShinkaEvolve could not find improvement after {generations} generations",
            trigger_event=event.type.value,
            participants=["ShinkaEvolveAgent", "Fixer", "Builder"],
            options=[
                DiscussionOption(
                    option_id="retry_more",
                    title="Retry with more generations",
                    description="Run evolution with 2x generations",
                    proposed_by="ShinkaEvolveAgent",
                ),
                DiscussionOption(
                    option_id="manual_fix",
                    title="Try standard fixer",
                    description="Fall back to standard code fixer agent",
                    proposed_by="Fixer",
                ),
                DiscussionOption(
                    option_id="skip",
                    title="Skip this file",
                    description="Mark as unresolvable and continue",
                    proposed_by="Orchestrator",
                ),
            ],
        )

    async def create_discussion(
        self,
        title: str,
        context: str,
        trigger_event: str,
        participants: List[str],
        options: List[DiscussionOption],
        strategy: Optional[ResolutionStrategy] = None,
        timeout: Optional[float] = None,
    ) -> Discussion:
        """Create a new discussion thread."""
        self._discussion_counter += 1
        discussion_id = f"disc-{self._discussion_counter:04d}"

        discussion = Discussion(
            discussion_id=discussion_id,
            title=title,
            context=context,
            trigger_event=trigger_event,
            participants=participants,
            options=options,
            strategy=strategy or self.default_strategy,
            timeout_seconds=timeout or self.default_timeout,
        )

        self._discussions[discussion_id] = discussion

        # Post to Minibook if available
        if self.minibook:
            try:
                options_text = "\n".join(
                    f"- **{o.title}** ({o.option_id}): {o.description}"
                    for o in options
                )
                post_content = (
                    f"## {title}\n\n"
                    f"{context}\n\n"
                    f"### Options:\n{options_text}\n\n"
                    f"**Strategy:** {discussion.strategy.value}\n"
                    f"**Timeout:** {discussion.timeout_seconds}s"
                )
                await self.minibook.post_summary(
                    post_content,
                    title=f"Discussion: {title}",
                )
            except Exception as e:
                logger.warning("minibook_discussion_post_failed", error=str(e))

        # Start timeout task
        asyncio.create_task(self._timeout_watcher(discussion_id))

        logger.info(
            "discussion_created",
            discussion_id=discussion_id,
            title=title,
            participants=participants,
            strategy=discussion.strategy.value,
        )

        return discussion

    async def cast_vote(
        self,
        discussion_id: str,
        agent: str,
        option_id: str,
        reason: str = "",
    ) -> bool:
        """Cast a vote in a discussion."""
        discussion = self._discussions.get(discussion_id)
        if not discussion:
            return False

        if discussion.status != DiscussionStatus.OPEN:
            return False

        # Check if agent already voted
        if any(v.agent == agent for v in discussion.votes):
            logger.debug("duplicate_vote", discussion_id=discussion_id, agent=agent)
            return False

        vote = DiscussionVote(agent=agent, option=option_id, reason=reason)
        discussion.votes.append(vote)

        # Add vote to option
        for opt in discussion.options:
            if opt.option_id == option_id:
                opt.votes.append(agent)
                break

        logger.info(
            "vote_cast",
            discussion_id=discussion_id,
            agent=agent,
            option=option_id,
        )

        # Check if all participants voted
        voted_agents = {v.agent for v in discussion.votes}
        if voted_agents >= set(discussion.participants):
            await self._resolve(discussion)

        return True

    async def _resolve(self, discussion: Discussion):
        """Resolve a discussion based on its strategy."""
        if discussion.status == DiscussionStatus.RESOLVED:
            return

        strategy = discussion.strategy

        if strategy == ResolutionStrategy.VOTE:
            # Count votes per option
            vote_counts = {}
            for opt in discussion.options:
                vote_counts[opt.option_id] = len(opt.votes)

            if vote_counts:
                winner = max(vote_counts, key=vote_counts.get)
                discussion.resolution = winner
                discussion.resolution_reason = (
                    f"Won by vote ({vote_counts[winner]} votes)"
                )
            else:
                discussion.resolution = discussion.options[0].option_id if discussion.options else None
                discussion.resolution_reason = "No votes, defaulting to first option"

        elif strategy == ResolutionStrategy.CONSENSUS:
            option_votes = {opt.option_id: set(opt.votes) for opt in discussion.options}
            for opt_id, voters in option_votes.items():
                if len(voters) == len(discussion.participants):
                    discussion.resolution = opt_id
                    discussion.resolution_reason = "Unanimous consensus"
                    break
            if not discussion.resolution:
                discussion.resolution_reason = "No consensus reached"

        elif strategy == ResolutionStrategy.MODERATOR:
            # Moderator vote takes precedence
            for vote in discussion.votes:
                if vote.agent == "Orchestrator":
                    discussion.resolution = vote.option
                    discussion.resolution_reason = f"Moderator decision by {vote.agent}"
                    break

        discussion.status = DiscussionStatus.RESOLVED
        discussion.resolved_at = datetime.now().isoformat()

        logger.info(
            "discussion_resolved",
            discussion_id=discussion.discussion_id,
            resolution=discussion.resolution,
            reason=discussion.resolution_reason,
        )

        # Emit resolution event
        await self.event_bus.publish(Event(
            type=EventType.MINIBOOK_DISCUSSION_RESOLVED,
            source="DiscussionManager",
            data={
                "discussion_id": discussion.discussion_id,
                "resolution": discussion.resolution,
                "reason": discussion.resolution_reason,
                "title": discussion.title,
            },
        ))

        # Call resolution callback if registered
        callback = self._resolution_callbacks.get(discussion.discussion_id)
        if callback:
            try:
                await callback(discussion)
            except Exception as e:
                logger.error("resolution_callback_failed", error=str(e))

    async def _timeout_watcher(self, discussion_id: str):
        """Watch for discussion timeout."""
        discussion = self._discussions.get(discussion_id)
        if not discussion:
            return

        await asyncio.sleep(discussion.timeout_seconds)

        if discussion.status == DiscussionStatus.OPEN:
            logger.info(
                "discussion_timeout",
                discussion_id=discussion_id,
                votes_received=len(discussion.votes),
            )

            # Try to resolve with available votes
            if discussion.votes:
                await self._resolve(discussion)
            else:
                # No votes at all — timeout with default
                discussion.status = DiscussionStatus.TIMED_OUT
                discussion.resolution = discussion.options[0].option_id if discussion.options else None
                discussion.resolution_reason = "Timed out with no votes, using default"
                discussion.resolved_at = datetime.now().isoformat()

    def on_resolution(self, discussion_id: str, callback: Callable):
        """Register a callback for when a discussion is resolved."""
        self._resolution_callbacks[discussion_id] = callback

    def get_discussion(self, discussion_id: str) -> Optional[Discussion]:
        """Get a specific discussion."""
        return self._discussions.get(discussion_id)

    def list_discussions(self, status: Optional[DiscussionStatus] = None) -> List[Dict]:
        """List discussions, optionally filtered by status."""
        result = []
        for d in self._discussions.values():
            if status and d.status != status:
                continue
            result.append(d.to_dict())
        return result

    def get_stats(self) -> Dict:
        """Get discussion statistics."""
        status_counts = {}
        for d in self._discussions.values():
            status_counts[d.status.value] = status_counts.get(d.status.value, 0) + 1

        return {
            "total_discussions": len(self._discussions),
            "by_status": status_counts,
            "total_votes": sum(len(d.votes) for d in self._discussions.values()),
        }
