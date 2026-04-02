"""BrainRouter — wraps SpaceRouter with Brain-based fast routing via RadialNetwork."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger('minibook.brain_router')


class BrainRouter:
    """Routes intents through the Brain's RadialNetwork before falling back to SpaceRouter.

    4-tier fallback:
    1. Deterministic — event_type prefix match (0ms)
    2. Brain fast path — POST localhost:5000/api/cortex/route (<100ms)
    3. SpaceRouter LLM — existing LLM-based routing (<2s)
    4. Keywords — existing keyword fallback (0ms)
    """

    # Deterministic prefix → space mapping (same as SpaceRouter)
    _PREFIX_MAP = {
        'idea.': 'ideas',
        'bubble.': 'bubbles',
        'code.': 'coding',
        'desktop.': 'desktop',
        'messaging.': 'desktop',
        'web.': 'desktop',
        'research.': 'research',
        'n8n.': 'n8n',
        'agentfarm.': 'agentfarm',
        'schedule.': 'schedule',
        'roarboot.': 'research',
        'minibook.': 'ideas',
    }

    def __init__(self, brain_url: str = "http://localhost:5000",
                 fallback_router=None,
                 confidence_threshold: float = 0.6,
                 timeout: float = 0.3):
        self._brain_url = brain_url.rstrip('/')
        self._fallback = fallback_router  # SpaceRouter instance
        self._brain_available = True
        self._confidence_threshold = confidence_threshold
        self._timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self._total_brain_routes = 0
        self._total_fallback_routes = 0

    def _get_deterministic(self, event_type: str):
        """Tier 1: prefix-based deterministic routing."""
        for prefix, space in self._PREFIX_MAP.items():
            if event_type.startswith(prefix):
                return space
        return None

    async def _call_brain(self, user_text: str, event_type: str) -> Optional[Dict]:
        """Tier 2: call Brain routing endpoint."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        try:
            async with self._session.post(
                f"{self._brain_url}/api/cortex/route",
                json={"user_text": user_text, "event_type": event_type},
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.debug(f"Brain route call failed: {e}")
            return None

    def _re_enable_brain(self):
        """Re-enable brain routing after backoff."""
        self._brain_available = True
        logger.info("Brain routing re-enabled")

    async def route(self, event_type: str, user_text: str,
                    payload: Dict[str, Any], context_summary: str = ""):
        """Route an intent — Brain-first with SpaceRouter fallback.

        Returns a RoutingDecision (same interface as SpaceRouter).
        """
        # Import here to avoid circular imports
        from spaces.minibook.enrichment.space_router import RoutingDecision

        # Tier 1: Deterministic
        det_space = self._get_deterministic(event_type)
        if det_space:
            return RoutingDecision(
                primary_space=det_space,
                secondary_spaces=[],
                is_multi_space=False,
                reasoning=f"deterministic:{event_type}",
                confidence=0.95,
            )

        # Tier 2: Brain fast path
        if self._brain_available:
            try:
                resp = await self._call_brain(user_text, event_type)
                if resp and resp.get('confidence', 0) >= self._confidence_threshold:
                    self._total_brain_routes += 1
                    routing_id = resp.get('routing_id', '')
                    logger.info(f"Brain route: {resp['primary_space']} "
                               f"(conf={resp['confidence']:.2f}, id={routing_id})")
                    return RoutingDecision(
                        primary_space=resp['primary_space'],
                        secondary_spaces=resp.get('secondary_spaces', []),
                        is_multi_space=len(resp.get('secondary_spaces', [])) > 0,
                        reasoning=f"brain:{routing_id}",
                        confidence=resp['confidence'],
                    )
            except Exception as e:
                logger.warning(f"Brain routing failed, disabling for 30s: {e}")
                self._brain_available = False
                try:
                    loop = asyncio.get_event_loop()
                    loop.call_later(30, self._re_enable_brain)
                except Exception:
                    pass

        # Tier 3+4: SpaceRouter fallback (LLM + keywords)
        if self._fallback:
            self._total_fallback_routes += 1
            return await self._fallback.route(event_type, user_text, payload, context_summary)

        # Ultimate fallback
        return RoutingDecision(
            primary_space="ideas",
            secondary_spaces=[],
            is_multi_space=False,
            reasoning="fallback:default",
            confidence=0.3,
        )

    async def close(self):
        """Cleanup aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
