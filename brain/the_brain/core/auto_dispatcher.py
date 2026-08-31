"""
Phase F.4 — BrainChat auto-dispatch via Minibook.

When a user message contains explicit @mentions of known Minibook
agents (e.g. "@vibemind_ideas brainstorm marketing copy"), Brain
forwards the task to those agents in parallel to its own normal
response. Brain still answers locally — the dispatch is *additive*,
not a replacement.

Conservative by design: triggers only on explicit @mentions to avoid
surprise dispatches. Future versions can layer LLM-based intent
matching on top.

Environment:
  AUTODISPATCH_ENABLED        default 1
  AUTODISPATCH_PROJECT_ID     default '46daa2f8-...' (VibeMind Collaboration)
  AUTODISPATCH_KNOWN_AGENTS   csv, default 'vibemind_ideas,vibemind_coding,
                              vibemind_research'
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


ENABLED = os.environ.get("AUTODISPATCH_ENABLED", "1").lower() in ("1", "true", "yes")
DEFAULT_PROJECT = os.environ.get(
    "AUTODISPATCH_PROJECT_ID",
    "46daa2f8-6f39-4cde-87c3-c95235bfb557",  # VibeMind Collaboration
)
KNOWN_AGENTS = tuple(
    a.strip() for a in os.environ.get(
        "AUTODISPATCH_KNOWN_AGENTS",
        "vibemind_ideas,vibemind_coding,vibemind_research",
    ).split(",") if a.strip()
)

# @-mention regex: @word (word_chars only, 2+ chars)
_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{1,40})")


class AutoDispatcher:
    """Detects explicit dispatch intent in user messages and forwards to Minibook
    or, when @vibemind_ideas is the sole target, the local Ideas-Space (Phase O.1).
    """

    def __init__(
        self,
        minibook_client_provider,
        project_id: str = DEFAULT_PROJECT,
        ideas_client_provider=None,
    ) -> None:
        """
        Args:
            minibook_client_provider: callable () -> MinibookClient or None.
                Lazily evaluated so Brain start order doesn't matter.
            project_id: default Minibook project id for dispatched tasks.
            ideas_client_provider: callable () -> IdeasClient or None.
                If supplied AND the only mentioned agent is `vibemind_ideas`
                AND the client is online, the dispatch goes to the local
                Ideas HTTP wrapper instead of Minibook.
        """
        self._get_mb = minibook_client_provider
        self._get_ideas = ideas_client_provider
        self._project_id = project_id
        self._lock = threading.Lock()
        self.stats: Dict[str, Any] = {
            "messages_scanned": 0,
            "mentions_found": 0,
            "dispatches_sent": 0,
            "dispatches_failed": 0,
            "last_target": None,
            "last_post_id": None,
            "last_idea_id": None,
            "last_agents": None,
            "last_error": None,
        }

    # ── Public ───────────────────────────────────────────────────────

    def maybe_dispatch(
        self, message: str, intent_hint: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Scan message for @mentions; if any match KNOWN_AGENTS, dispatch.

        Returns None if no dispatch happened, otherwise a result dict:
          {ok, post_id, agents, project_id, intent}
        """
        if not ENABLED:
            return None
        with self._lock:
            self.stats["messages_scanned"] += 1

        agents = self._extract_targets(message)
        if not agents:
            return None

        with self._lock:
            self.stats["mentions_found"] += len(agents)

        intent = (intent_hint or message).strip()

        # ── Local-first: vibemind_ideas → Ideas-Space HTTP (O.1.F) ──
        if agents == ["vibemind_ideas"] and self._get_ideas is not None:
            ic = None
            try:
                ic = self._get_ideas()
            except Exception as e:
                logger.debug(f"[AutoDispatch] ideas provider failed: {e}")
            if ic is not None and getattr(ic, "is_online", False):
                local_result = self._dispatch_to_ideas(ic, message, intent)
                if local_result is not None:
                    return local_result
            # else: fall through to Minibook fallback

        mb = None
        try:
            mb = self._get_mb()
        except Exception as e:
            logger.debug(f"[AutoDispatch] minibook provider failed: {e}")
        if mb is None:
            with self._lock:
                self.stats["dispatches_failed"] += 1
                self.stats["last_error"] = "minibook_client unavailable"
            return None
        try:
            post_id = mb.dispatch_task(
                project_id=self._project_id,
                target_agents=agents,
                intent=intent,
                title=intent[:80],
            )
        except Exception as e:
            with self._lock:
                self.stats["dispatches_failed"] += 1
                self.stats["last_error"] = f"exc: {e}"
            logger.warning(f"[AutoDispatch] dispatch_task failed: {e}")
            return None

        if not post_id:
            with self._lock:
                self.stats["dispatches_failed"] += 1
                self.stats["last_error"] = (
                    f"no post_id (mb={type(mb).__name__}, "
                    f"online={getattr(mb, '_online', '?')}, "
                    f"key_set={bool(getattr(mb, '_api_key', ''))}, "
                    f"agents={agents}, project={self._project_id})"
                )
            return None

        with self._lock:
            self.stats["dispatches_sent"] += 1
            self.stats["last_post_id"] = post_id
            self.stats["last_agents"] = agents
            self.stats["last_target"] = "minibook"

        result = {
            "ok": True,
            "target": "minibook",
            "post_id": post_id,
            "agents": agents,
            "project_id": self._project_id,
            "intent": intent[:200],
            "ts": time.time(),
        }
        logger.info(f"[AutoDispatch] -> minibook agents={agents} post_id={post_id}")
        return result

    # ── Local Ideas-Space dispatch (Phase O.1.F) ─────────────────────

    def _dispatch_to_ideas(
        self, ic, message: str, intent: str,
    ) -> Optional[Dict[str, Any]]:
        """Route a single-target @vibemind_ideas mention to the local
        Ideas HTTP wrapper.

        Heuristic:
          - If the message is a question (contains '?' or starts with
            interrogatives), do a search and return matches.
          - Otherwise, treat the message as a new idea to capture.
        Mention text is stripped before content extraction.
        """
        cleaned = _MENTION_RE.sub("", message).strip(" \t,.:;!-")
        if not cleaned:
            cleaned = intent

        is_question = (
            "?" in cleaned
            or cleaned.lower().split(" ", 1)[0] in {
                "was", "wer", "wo", "wann", "wie", "warum", "welche",
                "what", "who", "where", "when", "how", "why", "which",
            }
        )

        # ── Notification layer (User-Decision E "always show") ──
        # Pre-dispatch KG lookup so the response can show what the agent
        # already knew, before the action was taken.
        prior_knowledge: Dict[str, Any] = {"hits_count": 0, "top": []}
        try:
            kg_resp = ic.kg_search(query=cleaned, limit=3, threshold=0.3)
            if isinstance(kg_resp, dict) and not kg_resp.get("error"):
                hits = kg_resp.get("hits") or []
                prior_knowledge = {
                    "hits_count": len(hits),
                    "top": [{
                        "id": (h.get("payload") or {}).get("idea_id"),
                        "title": (h.get("payload") or {}).get("title"),
                        "score": round(float(h.get("score") or 0.0), 3),
                    } for h in hits[:3]],
                }
        except Exception as e:
            prior_knowledge["error"] = str(e)

        try:
            if is_question:
                resp = ic.search_ideas(query=cleaned, limit=5)
                if isinstance(resp, dict) and resp.get("error"):
                    raise RuntimeError(resp.get("error"))
                with self._lock:
                    self.stats["dispatches_sent"] += 1
                    self.stats["last_target"] = "ideas_local:search"
                    self.stats["last_agents"] = ["vibemind_ideas"]
                logger.info(f"[AutoDispatch] -> ideas_local search '{cleaned[:60]}'")
                return {
                    "ok": True,
                    "target": "ideas_local",
                    "action": "search",
                    "query": cleaned,
                    "matches": resp.get("ideas", []),
                    "prior_knowledge": prior_knowledge,
                    "ts": time.time(),
                }
            # Capture as new idea — first line becomes title, rest is body
            parts = cleaned.split("\n", 1)
            title = parts[0][:80].strip() or "Untitled"
            content = parts[1].strip() if len(parts) > 1 else cleaned
            resp = ic.create_idea(
                title=title, content=content, source="brain_chat",
            )
            if isinstance(resp, dict) and resp.get("error"):
                raise RuntimeError(resp.get("error"))
            idea = (resp or {}).get("idea") or {}
            with self._lock:
                self.stats["dispatches_sent"] += 1
                self.stats["last_target"] = "ideas_local:create"
                self.stats["last_idea_id"] = idea.get("id")
                self.stats["last_agents"] = ["vibemind_ideas"]
            logger.info(f"[AutoDispatch] -> ideas_local create id={idea.get('id')}")
            return {
                "ok": True,
                "target": "ideas_local",
                "action": "create",
                "idea_id": idea.get("id"),
                "title": idea.get("title"),
                "prior_knowledge": prior_knowledge,
                "ts": time.time(),
            }
        except Exception as e:
            with self._lock:
                self.stats["dispatches_failed"] += 1
                self.stats["last_error"] = f"ideas_local: {e}"
            logger.warning(f"[AutoDispatch] ideas_local failed: {e}")
            return None

    # ── Helpers ───────────────────────────────────────────────────────

    def _extract_targets(self, message: str) -> List[str]:
        """Find @mentions in the message that match KNOWN_AGENTS.
        Case-insensitive match, returns canonical (lowercase) names."""
        if not message or "@" not in message:
            return []
        found = []
        seen = set()
        known_lc = {a.lower() for a in KNOWN_AGENTS}
        for m in _MENTION_RE.finditer(message):
            name = m.group(1).lower()
            if name in known_lc and name not in seen:
                found.append(name)
                seen.add(name)
        return found
