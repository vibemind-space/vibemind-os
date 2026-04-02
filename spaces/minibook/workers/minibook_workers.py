"""
Minibook Workers - Background tasks for inter-space collaboration

DiscussionPollerWorker:
    Polls Minibook for new responses to active collaboration discussions.
    When all @mentioned spaces have responded, delivers aggregated results
    via inject_system_message() or NotificationQueue fallback.

SpaceMinibookResponder:
    Per-space worker that monitors Minibook notifications for @mentions
    and executes the appropriate tool, posting the result back as a comment.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Set, Optional, Callable

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[MinibookWorker] %s", msg)


# =============================================================================
# Active Discussion Tracking
# =============================================================================

@dataclass
class ActiveDiscussion:
    """Tracks a multi-space collaboration discussion."""
    post_id: str
    mentioned_agents: Set[str]
    responded_agents: Set[str] = field(default_factory=set)
    responses: Dict[str, str] = field(default_factory=dict)  # agent_name → content
    original_request: str = ""
    created_at: float = field(default_factory=time.time)


# =============================================================================
# Discussion Poller Worker
# =============================================================================

class DiscussionPollerWorker:
    """
    Polls Minibook for responses to active collaboration discussions.

    When all @mentioned agents have responded (or timeout), delivers
    aggregated results to the user.

    Delivery methods (in order of preference):
    1. inject_system_message() → Rachel speaks the result immediately
    2. NotificationQueue → Rachel picks up result on next user input
    """

    def __init__(
        self,
        realtime_session_getter: Optional[Callable] = None,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ):
        """
        Args:
            realtime_session_getter: Callable returning the active OpenAIRealtimeVoiceSession
            poll_interval: Seconds between polls
            timeout: Seconds before a discussion times out
        """
        self._get_session = realtime_session_getter
        self._active: Dict[str, ActiveDiscussion] = {}
        self._running = False
        self._poll_interval = poll_interval
        self._timeout = timeout

    @property
    def active_discussion_count(self) -> int:
        """Number of active (unresolved) discussions."""
        return len(self._active)

    def track_discussion(
        self,
        post_id: str,
        mentioned_agents: List[str],
        original_request: str,
    ) -> None:
        """
        Start tracking a collaboration discussion for completion.

        Args:
            post_id: Minibook post ID
            mentioned_agents: List of agent names that were @mentioned
            original_request: Original user request text
        """
        self._active[post_id] = ActiveDiscussion(
            post_id=post_id,
            mentioned_agents=set(mentioned_agents),
            original_request=original_request,
        )
        _debug_print(
            f"Tracking discussion {post_id}: "
            f"waiting for {mentioned_agents}"
        )

    async def poll_loop(self) -> None:
        """
        Main polling loop. Runs as asyncio.Task.

        Checks each active discussion for new comments from
        @mentioned agents. When all have responded (or timeout),
        delivers results.
        """
        from spaces.minibook.tools.minibook_client import get_minibook_client

        self._running = True
        _debug_print("Discussion poller started")

        while self._running:
            if not self._active:
                await asyncio.sleep(self._poll_interval)
                continue

            client = get_minibook_client()
            loop = asyncio.get_running_loop()

            for post_id, discussion in list(self._active.items()):
                try:
                    comments = await loop.run_in_executor(
                        None, client.get_comments, post_id
                    )

                    for comment in comments:
                        agent_name = comment.get("agent_name", "")
                        if agent_name in discussion.mentioned_agents:
                            if agent_name not in discussion.responded_agents:
                                discussion.responded_agents.add(agent_name)
                                discussion.responses[agent_name] = comment.get("content", "")
                                _debug_print(
                                    f"Discussion {post_id}: "
                                    f"{agent_name} responded "
                                    f"({len(discussion.responded_agents)}/{len(discussion.mentioned_agents)})"
                                )

                    # All agents responded
                    if discussion.responded_agents >= discussion.mentioned_agents:
                        await self._deliver_results(post_id, discussion)
                        del self._active[post_id]

                    # Timeout
                    elif time.time() - discussion.created_at > self._timeout:
                        _debug_print(f"Discussion {post_id} timed out")
                        await self._deliver_partial_results(post_id, discussion)
                        del self._active[post_id]

                except Exception as e:
                    _logger.warning(f"Poll error for discussion {post_id}: {e}")

            await asyncio.sleep(self._poll_interval)

        _debug_print("Discussion poller stopped")

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False

    async def _deliver_results(
        self, post_id: str, discussion: ActiveDiscussion
    ) -> None:
        """Deliver complete collaboration results to the user."""
        summary = self._aggregate_responses(discussion)
        _debug_print(f"Delivering results for {post_id}: {summary[:100]}...")
        await self._inject_or_queue(summary, discussion)

    async def _deliver_partial_results(
        self, post_id: str, discussion: ActiveDiscussion
    ) -> None:
        """Deliver partial results (timeout, not all agents responded)."""
        missing = discussion.mentioned_agents - discussion.responded_agents
        summary = self._aggregate_responses(discussion)
        summary += f"\n(Timeout: {', '.join(missing)} did not respond)"
        _debug_print(f"Delivering partial results for {post_id}")
        await self._inject_or_queue(summary, discussion)

    async def _inject_or_queue(
        self, text: str, discussion: ActiveDiscussion
    ) -> None:
        """
        Deliver result text via the best available method.

        1. Try inject_system_message() for immediate Rachel speech
        2. Fall back to NotificationQueue for next-input delivery
        """
        # Try direct injection into voice session
        if self._get_session:
            session = self._get_session()
            if session and hasattr(session, "inject_system_message"):
                try:
                    await session.inject_system_message(text)
                    _debug_print("Result injected via voice session")
                    return
                except Exception as e:
                    _logger.warning(f"Voice injection failed: {e}")

        # Fallback: NotificationQueue
        try:
            from swarm.orchestrator.notification_queue import get_notification_queue
            queue = get_notification_queue()
            queue.add_notification(
                job_id=f"minibook-{discussion.post_id}",
                event_type="minibook.collaboration_complete",
                result=text,
                metadata={"original_request": discussion.original_request},
            )
            _debug_print("Result queued in NotificationQueue (fallback)")
        except Exception as e:
            _logger.error(f"Could not deliver result: {e}")

    def _aggregate_responses(self, discussion: ActiveDiscussion) -> str:
        """Format all agent responses into a summary string."""
        parts = []
        for agent_name, content in discussion.responses.items():
            # Strip the "vibemind_" prefix for readability
            short_name = agent_name.replace("vibemind_", "")
            parts.append(f"{short_name}: {content}")

        if not parts:
            return "No results received."

        return "\n".join(parts)


# =============================================================================
# Space Minibook Responder
# =============================================================================

class SpaceMinibookResponder:
    """
    Per-space worker that monitors @mentions and responds.

    Each VibeMind space gets a responder that:
    1. Polls Minibook notifications for its agent
    2. Parses the mention content
    3. Executes the appropriate space tool
    4. Posts the result back as a comment
    """

    def __init__(
        self,
        agent_name: str,
        space_key: str,
        tool_executor: Optional[Callable] = None,
        space_agent: Optional[Any] = None,
        poll_interval: float = 2.0,
    ):
        """
        Args:
            agent_name: Minibook agent name (e.g., "vibemind_ideas")
            space_key: VibeMind space key (e.g., "ideas")
            tool_executor: Callable that executes a task and returns result string
            space_agent: Optional BaseSpaceAgent for agentic multi-tool execution
            poll_interval: Seconds between notification polls
        """
        self._agent_name = agent_name
        self._space_key = space_key
        self._executor = tool_executor
        self._space_agent = space_agent
        self._running = False
        self._poll_interval = poll_interval
        self._processed_posts: set = set()  # Dedup: post_ids already handled

    async def poll_and_respond(self) -> None:
        """
        Main loop: poll for @mentions and respond.
        Runs as asyncio.Task (or in its own thread).
        """
        from spaces.minibook.tools.minibook_client import get_minibook_client

        self._running = True
        _debug_print(f"SpaceResponder started for {self._agent_name}")

        # Flush stale notifications from previous sessions by adding their
        # post_ids to the dedup set. This prevents re-execution of old tasks
        # without needing HTTP calls to mark_notification_read (which may fail).
        try:
            client = get_minibook_client()
            loop = asyncio.get_running_loop()
            stale = await loop.run_in_executor(
                None, client.get_notifications, self._agent_name
            )
            if stale:
                stale_ids = set()
                for notif in stale:
                    pid = notif.get("payload", {}).get("post_id", "")
                    if pid:
                        stale_ids.add(pid)
                self._processed_posts.update(stale_ids)
                _debug_print(
                    f"SpaceResponder {self._agent_name}: "
                    f"flushed {len(stale_ids)} stale post_ids into dedup set"
                )
        except Exception as e:
            _debug_print(f"SpaceResponder {self._agent_name}: flush error: {e}")

        while self._running:
            try:
                client = get_minibook_client()
                # Use run_in_executor to avoid blocking the main event loop
                # with synchronous HTTP calls
                loop = asyncio.get_running_loop()
                all_notifs = await loop.run_in_executor(
                    None, client.get_notifications, self._agent_name
                )

                # Filter: only unread notifications with actionable types
                notifications = [
                    n for n in all_notifs
                    if not n.get("read", False)
                    and n.get("type", "") in ("mention", "new_comment", "thread_update")
                ]

                # Further filter: only posts we haven't processed yet
                new_notifications = []
                for notif in notifications:
                    notif_payload = notif.get("payload", {})
                    post_id = notif_payload.get("post_id", "")
                    if not post_id or post_id in self._processed_posts:
                        continue
                    new_notifications.append(notif)

                # Log only when there are genuinely new notifications
                if new_notifications:
                    _debug_print(
                        f"SpaceResponder {self._agent_name}: "
                        f"{len(new_notifications)} NEW notifications"
                    )

                for notif in new_notifications:
                    notif_payload = notif.get("payload", {})
                    post_id = notif_payload.get("post_id", "")
                    notif_id = notif.get("id", "")
                    self._processed_posts.add(post_id)

                    # Fetch the actual post content from Minibook
                    content = await self._fetch_post_content(
                        client, post_id, loop
                    )
                    if not content:
                        _debug_print(
                            f"SpaceResponder {self._agent_name}: "
                            f"could not fetch content for post {post_id}"
                        )
                        continue

                    _debug_print(
                        f"SpaceResponder {self._agent_name}: "
                        f"mentioned in post {post_id}, "
                        f"content={content[:80]}..."
                    )

                    # Execute the task
                    result = await self._handle_mention(content)

                    # Post response as comment (in executor to avoid blocking)
                    try:
                        await loop.run_in_executor(
                            None, client.create_comment, post_id, result, self._agent_name
                        )
                        _debug_print(
                            f"SpaceResponder {self._agent_name}: "
                            f"responded to {post_id}"
                        )
                    except Exception as e:
                        _logger.error(f"Failed to post comment: {e}")

                    # Mark notification as read
                    if notif_id:
                        try:
                            await loop.run_in_executor(
                                None, client.mark_notification_read, notif_id, self._agent_name
                            )
                        except Exception:
                            pass

            except Exception as e:
                # Connection errors are expected if Minibook is down
                if "Connection" not in str(type(e).__name__):
                    _logger.warning(f"SpaceResponder {self._agent_name} error: {e}")

            await asyncio.sleep(self._poll_interval)

        _debug_print(f"SpaceResponder stopped for {self._agent_name}")

    def stop(self) -> None:
        """Stop the responder loop."""
        self._running = False

    async def _fetch_post_content(
        self, client, post_id: str, loop
    ) -> Optional[str]:
        """
        Fetch post content from Minibook by listing project posts.

        Notifications only contain post_id (in payload), not the actual
        content. We need to fetch the post to get the enriched JSON.
        """
        try:
            project_id = client.project_id
            if not project_id:
                return None

            posts = await loop.run_in_executor(
                None, client.get_posts, project_id, self._agent_name
            )

            for post in posts:
                if post.get("id") == post_id:
                    return post.get("content", "")

            _debug_print(
                f"Post {post_id} not found in {len(posts)} project posts"
            )
            return None

        except Exception as e:
            _logger.warning(f"Failed to fetch post content: {e}")
            return None

    async def _handle_mention(self, content: str) -> str:
        """
        Handle an @mention by executing the appropriate tool.

        Supports two formats:
        1. Enriched (v2): JSON payload with event_type, payload, context
        2. Legacy (v1): Raw text — uses domain-constrained classification

        Args:
            content: The post/comment content that mentioned this agent

        Returns:
            Result string to post as a comment
        """
        # ─── Try enriched payload first (MinibookHub v2 format) ───
        enriched = self._try_parse_enriched(content)
        if enriched:
            return await self._execute_enriched(enriched)

        # ─── Legacy text-based execution (existing behavior) ───
        return await self._execute_legacy(content)

    def _try_parse_enriched(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Try to parse enriched JSON payload from post content.

        MinibookHub posts tasks in this format:
            ```enriched
            {"version": "2", "event_type": "...", "tasks": [...]}
            ```
            Aufgabe: <user text>

        Returns the enriched dict for this agent, or None if not enriched.
        """
        import json

        try:
            if "```enriched" not in content:
                return None

            # Extract JSON between ```enriched and ```
            start = content.index("```enriched") + len("```enriched")
            end = content.index("```", start)
            json_str = content[start:end].strip()
            data = json.loads(json_str)

            if data.get("version") != "2":
                return None

            # Find this agent's task in the tasks list
            tasks = data.get("tasks", [])
            for task in tasks:
                if task.get("space_key") == self._space_key:
                    return task

            # If no specific task for this space, use the global event_type
            return {
                "event_type": data.get("event_type", ""),
                "payload": {},
                "context": {},
                "space_key": self._space_key,
                "original_text": data.get("original_text", ""),
            }

        except (ValueError, json.JSONDecodeError, KeyError):
            return None

    async def _execute_enriched(self, enriched: Dict[str, Any]) -> str:
        """
        Execute an enriched task with pre-classified event_type and payload.

        Execution priority:
        1. SpaceAgent (agentic multi-tool loop) — no re-classification needed
        2. Orchestrator with domain_hint (flat single-tool fallback)

        Args:
            enriched: Dict with event_type, payload, context, space_key

        Returns:
            Result string to post as comment
        """
        event_type = enriched.get("event_type", "")
        payload = enriched.get("payload", {})
        user_text = payload.get("user_text", "") or enriched.get("original_text", "")
        context_data = enriched.get("context", {})

        _debug_print(
            f"SpaceResponder {self._agent_name}: "
            f"enriched execution: {event_type}"
        )

        # Anti-loop guard
        if event_type.startswith("minibook."):
            return (
                f"[{self._space_key}] Task received, "
                f"but outside my domain."
            )

        # --- Priority 1: SpaceAgent (agentic multi-tool loop) ---
        if self._space_agent and user_text:
            try:
                result = await self._execute_via_space_agent(user_text, context_data)
                if result:
                    return result
            except Exception as e:
                _logger.warning(
                    f"SpaceAgent {self._space_key} failed: {e}, "
                    f"falling back to orchestrator"
                )
                _debug_print(f"SpaceAgent {self._space_key} error: {e}")

        # --- Priority 2: Orchestrator with domain_hint (flat execution) ---
        if user_text:
            return await self._execute_via_orchestrator(user_text)

        return "No actionable task recognized."

    async def _execute_via_space_agent(
        self, user_text: str, context_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Execute via SpaceAgent's agentic loop (LLM with domain-specific tools).

        The SpaceAgent decides which tools to call and chains them intelligently.
        No re-classification needed — the agent handles everything.

        Args:
            user_text: Original user input text
            context_data: Context dict from EnrichmentPipeline (bubble state, history)

        Returns:
            Summary string from the agent, or None on failure
        """
        from swarm.space_agents.models import SpaceAgentContext

        agent_context = SpaceAgentContext(
            user_input=user_text,
            conversation_history=context_data.get("conversation_history", []),
            current_bubble=context_data.get("current_bubble"),
            current_bubble_id=context_data.get("current_bubble_id"),
            idea_count=context_data.get("idea_count", 0),
        )

        _debug_print(
            f"SpaceAgent {self._space_key}: executing '{user_text[:60]}...'"
        )

        result = await self._space_agent.execute(user_text, agent_context)

        if result and result.summary:
            _debug_print(
                f"SpaceAgent {self._space_key}: "
                f"{result.turns} turns, {len(result.tool_calls)} tools, "
                f"{result.total_latency_ms:.0f}ms"
            )
            return result.summary

        if result and result.error:
            _logger.warning(f"SpaceAgent {self._space_key} returned error: {result.error}")

        return None

    async def _execute_legacy(self, content: str) -> str:
        """
        Legacy text-based execution (existing behavior, unchanged).

        Strips @mentions and boilerplate, then executes via domain-constrained
        orchestrator or custom executor.

        Args:
            content: Raw post content text

        Returns:
            Result string to post as comment
        """
        # Strip @agent_name mentions from content for cleaner classification
        clean_content = content
        for prefix in ("@vibemind_", "@"):
            while prefix in clean_content:
                idx = clean_content.index(prefix)
                end = clean_content.find(" ", idx)
                if end == -1:
                    clean_content = clean_content[:idx].strip()
                else:
                    clean_content = (clean_content[:idx] + clean_content[end:]).strip()
        # Strip Minibook boilerplate
        clean_content = clean_content.replace("Aufgabe:", "").strip()
        clean_content = clean_content.replace("bitte bearbeitet euren Teil.", "").strip()
        clean_content = clean_content.replace("bitte bearbeitet euren teil.", "").strip()
        # Remove trailing newlines left after stripping
        clean_content = clean_content.strip()
        if not clean_content:
            return "No task recognized."

        if self._executor:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self._executor, clean_content)
                return str(result) if result else "Done."
            except Exception as e:
                _logger.error(f"SpaceResponder {self._agent_name} execution error: {e}")
                return f"Error: {e}"

        return await self._execute_via_orchestrator(clean_content)

    async def _execute_via_orchestrator(self, text: str) -> str:
        """
        Execute via IntentOrchestrator with domain_hint.

        Used by both enriched and legacy paths.

        Args:
            text: Text to classify and execute

        Returns:
            Result string
        """
        try:
            from swarm.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()
            result = orchestrator.process_intent_sync(
                text,
                domain_hint=self._space_key,
            )

            # Anti-loop guard: if the orchestrator classified back into
            # minibook.*, do NOT re-enter — return a safe fallback.
            event_type = getattr(result, "event_type", "") or ""
            if event_type.startswith("minibook."):
                _debug_print(
                    f"Anti-loop: {self._agent_name} got '{event_type}' "
                    f"— skipping to prevent recursion"
                )
                return (
                    f"[{self._space_key}] Aufgabe empfangen, "
                    f"aber liegt ausserhalb meiner Domain."
                )

            return result.response_hint
        except Exception as e:
            _logger.error(f"SpaceResponder fallback error: {e}")
            return f"Could not process request: {e}"


# =============================================================================
# Singleton + Factory
# =============================================================================

_discussion_poller: Optional[DiscussionPollerWorker] = None


def get_discussion_poller(
    realtime_session_getter: Optional[Callable] = None,
    poll_interval: float = 2.0,
    timeout: float = 120.0,
) -> DiscussionPollerWorker:
    """Get or create the global DiscussionPollerWorker."""
    global _discussion_poller
    if _discussion_poller is None:
        _discussion_poller = DiscussionPollerWorker(
            realtime_session_getter=realtime_session_getter,
            poll_interval=poll_interval,
            timeout=timeout,
        )
    return _discussion_poller


def _make_space_executor(space_key: str, domain_prefix: str) -> Callable:
    """
    Build a per-space tool executor that routes through the orchestrator
    constrained to this space's domain.

    The executor:
    1. Classifies the mention content with domain_hint → stays in-domain
    2. Anti-loop: if result is minibook.*, returns a safe fallback
    3. Returns the response_hint string for posting as a Minibook comment

    Args:
        space_key: VibeMind space key (e.g., "ideas", "coding")
        domain_prefix: Dot-separated event type prefixes (e.g., "bubble.,idea.")

    Returns:
        Callable(content: str) → str
    """
    def executor(content: str) -> str:
        try:
            from swarm.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()

            # Use domain_hint to constrain the classifier
            result = orchestrator.process_intent_sync(
                content,
                domain_hint=space_key,
            )

            # Anti-loop guard
            event_type = getattr(result, "event_type", "") or ""
            if event_type.startswith("minibook."):
                _debug_print(
                    f"Anti-loop: executor for '{space_key}' got "
                    f"'{event_type}' — blocking recursion"
                )
                return (
                    f"[{space_key}] Task outside "
                    f"my domain ({domain_prefix})."
                )

            return result.response_hint or "Done."

        except Exception as e:
            _logger.error(f"Space executor '{space_key}' error: {e}")
            return f"Error in {space_key}: {e}"

    return executor


def _load_space_agents() -> Dict[str, Any]:
    """
    Load all available SpaceAgents (where USE_SPACE_AGENTS=true).

    SpaceAgents provide agentic multi-tool execution (LLM decides which
    tools to call and chains them). Only spaces with implemented agents
    are returned; others fall back to orchestrator-based flat execution.

    Returns:
        Dict mapping space_key → BaseSpaceAgent instance
    """
    import os
    agents: Dict[str, Any] = {}

    if os.getenv("USE_SPACE_AGENTS", "false").lower() != "true":
        _debug_print("USE_SPACE_AGENTS=false — no SpaceAgents loaded")
        return agents

    # Ideas Space Agent (47 tools, agentic loop)
    try:
        from swarm.space_agents import get_ideas_space_agent
        agents["ideas"] = get_ideas_space_agent()
        _debug_print("Loaded IdeasSpaceAgent (47 tools)")
    except Exception as e:
        _logger.warning(f"Could not load IdeasSpaceAgent: {e}")

    # Future SpaceAgents:
    # try:
    #     from swarm.space_agents import get_desktop_space_agent
    #     agents["desktop"] = get_desktop_space_agent()
    # except Exception: pass

    if agents:
        _debug_print(f"Loaded {len(agents)} SpaceAgent(s): {list(agents.keys())}")

    return agents


def create_space_responders(
    poll_interval: float = 2.0,
) -> Dict[str, SpaceMinibookResponder]:
    """
    Create SpaceMinibookResponder instances for all registered spaces.

    Each responder gets:
    - A per-space tool executor (orchestrator with domain_hint, flat execution)
    - An optional SpaceAgent (agentic multi-tool loop, preferred when available)

    Returns:
        Dict mapping space_key → SpaceMinibookResponder
    """
    _logger.debug("create_space_responders called: poll_interval=%s", poll_interval)
    from spaces.minibook.tools.collaboration_tools import SPACE_AGENT_REGISTRY

    # Load SpaceAgents where available
    space_agents = _load_space_agents()

    responders = {}
    for space_key, agent_info in SPACE_AGENT_REGISTRY.items():
        domain_prefix = agent_info.get("domain_prefix", "")
        executor = _make_space_executor(space_key, domain_prefix)
        agent = space_agents.get(space_key)

        responders[space_key] = SpaceMinibookResponder(
            agent_name=agent_info["name"],
            space_key=space_key,
            tool_executor=executor,
            space_agent=agent,
            poll_interval=poll_interval,
        )

        agent_str = f", SpaceAgent=YES" if agent else ""
        _debug_print(
            f"Created responder for '{space_key}' "
            f"(agent={agent_info['name']}, prefix={domain_prefix}{agent_str})"
        )

    return responders


__all__ = [
    "DiscussionPollerWorker",
    "SpaceMinibookResponder",
    "ActiveDiscussion",
    "get_discussion_poller",
    "create_space_responders",
]
