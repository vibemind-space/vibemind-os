"""
Result Aggregator — Collects and delivers results from Minibook agents.

Two modes:
- sync_wait:  Single-space tasks — polls Minibook comments until the
              one agent responds (up to sync_timeout seconds).
- async_poll: Multi-space tasks — registers with DiscussionPollerWorker
              for background aggregation and async delivery.

Delivers results via:
1. inject_system_message() → Rachel speaks immediately
2. NotificationQueue → next-input delivery fallback
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[ResultAggregator] %s", msg)


class ResultAggregator:
    """
    Aggregates results from Minibook agent responses.

    Provides both synchronous waiting (for fast single-space tasks)
    and asynchronous polling (for multi-space collaboration).
    """

    def __init__(
        self,
        realtime_session_getter: Optional[Callable] = None,
        rachel_interface: Optional[Any] = None,
        sync_timeout: float = 10.0,
        async_timeout: float = 120.0,
        poll_interval: float = 0.5,
    ):
        """
        Args:
            realtime_session_getter: Returns the active voice session for inject_system_message
            rachel_interface: RachelInterface instance for status updates
            sync_timeout: Max seconds to wait for single-space response
            async_timeout: Max seconds for multi-space collaboration
            poll_interval: Seconds between comment polls in sync_wait mode
        """
        self._get_session = realtime_session_getter
        self._rachel = rachel_interface
        self._sync_timeout = sync_timeout
        self._async_timeout = async_timeout
        self._poll_interval = poll_interval

    # =========================================================================
    # Sync Wait (Single-Space, Fast Tasks)
    # =========================================================================

    async def wait_for_single(
        self,
        post_id: str,
        agent_name: str,
        task_id: str = "",
    ) -> Optional[str]:
        """
        Wait synchronously for a single agent's response.

        Polls Minibook comments on the post until the target agent
        responds or timeout is reached.

        Args:
            post_id: Minibook post ID to poll
            agent_name: Agent name to wait for (e.g., "vibemind_ideas")
            task_id: Task ID for Rachel status updates

        Returns:
            The agent's response text, or None on timeout
        """
        from spaces.minibook.tools.minibook_client import get_minibook_client

        client = get_minibook_client()
        start = time.time()
        result = None

        _debug_print(
            f"Sync-wait for {agent_name} on post {post_id} "
            f"(timeout={self._sync_timeout}s)"
        )

        while time.time() - start < self._sync_timeout:
            try:
                comments = client.get_comments(post_id)
                for comment in comments:
                    if comment.get("agent_name") == agent_name:
                        result = comment.get("content", "")
                        break

                if result is not None:
                    elapsed = time.time() - start
                    _debug_print(
                        f"Sync-wait: {agent_name} responded in {elapsed:.1f}s"
                    )

                    # Update Rachel Interface
                    if self._rachel:
                        self._rachel.mark_agent_responded(agent_name)
                        if task_id:
                            short_name = agent_name.replace("vibemind_", "")
                            self._rachel.complete_task(
                                task_id=task_id,
                                event_type=f"{short_name}.response",
                                result_summary=result[:100] if result else "",
                                success=True,
                            )

                    return result

            except Exception as e:
                _logger.warning(f"Sync-wait poll error: {e}")

            await asyncio.sleep(self._poll_interval)

        # Timeout
        elapsed = time.time() - start
        _debug_print(f"Sync-wait: TIMEOUT after {elapsed:.1f}s for {agent_name}")

        if self._rachel:
            self._rachel.mark_agent_failed(agent_name, "Timeout")
            if task_id:
                self._rachel.timeout_task(task_id)

        return None

    # =========================================================================
    # Async Poll (Multi-Space Tasks)
    # =========================================================================

    async def track_multi(
        self,
        post_id: str,
        mentioned_agents: List[str],
        original_request: str,
        task_id: str = "",
    ) -> None:
        """
        Register a multi-space task for async tracking.

        Delegates to the existing DiscussionPollerWorker for background
        polling and aggregation. Results are delivered async via
        inject_system_message or NotificationQueue.

        Args:
            post_id: Minibook post ID
            mentioned_agents: List of agent names that were @mentioned
            original_request: Original user request text
            task_id: Task ID for Rachel status updates
        """
        try:
            from spaces.minibook.workers.minibook_workers import get_discussion_poller

            poller = get_discussion_poller()
            if poller:
                poller.track_discussion(
                    post_id=post_id,
                    mentioned_agents=mentioned_agents,
                    original_request=original_request,
                )
                _debug_print(
                    f"Async-track: registered post {post_id} with "
                    f"{len(mentioned_agents)} agents"
                )
            else:
                _debug_print("Async-track: DiscussionPoller not available")

        except Exception as e:
            _logger.warning(f"Could not register multi-space tracking: {e}")

    # =========================================================================
    # Result Delivery
    # =========================================================================

    async def deliver_result(
        self,
        text: str,
        task_id: str = "",
        event_type: str = "",
    ) -> bool:
        """
        Deliver a result to the user via best available method.

        1. Try inject_system_message() for immediate voice output
        2. Fall back to NotificationQueue

        Args:
            text: Result text to deliver
            task_id: For Rachel tracking
            event_type: For Rachel tracking

        Returns:
            True if delivered via voice, False if queued
        """
        # Update Rachel
        if self._rachel and task_id:
            self._rachel.complete_task(
                task_id=task_id,
                event_type=event_type,
                result_summary=text[:100],
                success=True,
            )

        # Try direct voice injection
        if self._get_session:
            session = self._get_session()
            if session and hasattr(session, "inject_system_message"):
                try:
                    await session.inject_system_message(text)
                    _debug_print("Result delivered via voice session")
                    return True
                except Exception as e:
                    _logger.warning(f"Voice injection failed: {e}")

        # Fallback: NotificationQueue
        try:
            from swarm.orchestrator.notification_queue import get_notification_queue
            queue = get_notification_queue()
            queue.add_notification(
                job_id=f"hub-{task_id}" if task_id else f"hub-{time.time():.0f}",
                event_type=event_type or "minibook.hub_result",
                result=text,
                metadata={"source": "minibook_hub"},
            )
            _debug_print("Result queued in NotificationQueue (fallback)")
            return False
        except Exception as e:
            _logger.error(f"Could not deliver result: {e}")
            return False


# =============================================================================
# Singleton
# =============================================================================

_result_aggregator: Optional[ResultAggregator] = None


def get_result_aggregator(
    realtime_session_getter: Optional[Callable] = None,
    rachel_interface: Optional[Any] = None,
) -> ResultAggregator:
    """Get or create the global ResultAggregator singleton."""
    global _result_aggregator
    if _result_aggregator is None:
        _result_aggregator = ResultAggregator(
            realtime_session_getter=realtime_session_getter,
            rachel_interface=rachel_interface,
        )
    return _result_aggregator


__all__ = ["ResultAggregator", "get_result_aggregator"]
