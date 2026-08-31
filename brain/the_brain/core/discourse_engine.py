"""
DiscourseEngine — Phase R.3.

30-second tick driver. Each tick:

  1. Pick a KG-slice (rotating through Brain's cognitive collections)
  2. Pick 1-3 OpenFang-Phi3-clones whose tags match the slice's domain
  3. For each picked agent:
     a. Build a "discourse prompt" containing the slice + persona-hint
     b. POST the prompt to Mirofish's /api/simulation/{id}/interview —
        the agent answers in character. Mirofish persists the answer
        as a Tweet in its own SQLite + Neo4j memory.
     c. With 30% probability, pick a different agent and ask them to
        reply to the previous tweet (creates discourse).
  4. Increment stats.

The Mirofish simulation must already be running (set up via
``scripts/setup_mirofish_brain_sim.py``). The simulation_id is read
from ``data/discourse_sim.json``.

Environment:
  DISCOURSE_TICK_INTERVAL_S      default 30   (build mode; raise to 3600 in prod)
  DISCOURSE_AGENTS_PER_TICK      default 2
  DISCOURSE_REPLY_PROBABILITY    default 0.3
  DISCOURSE_INITIAL_DELAY_S      default 60   (let Brain settle before first tick)
  DISCOURSE_ENABLED              default 1
  MIROFISH_URL                   default http://127.0.0.1:5101
  OPENFANG_URL                   default http://127.0.0.1:4200
  BRAIN_URL                      default http://127.0.0.1:5000  (for KG slice fetch)
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


TICK_INTERVAL_S = float(os.environ.get("DISCOURSE_TICK_INTERVAL_S", "30"))
AGENTS_PER_TICK = int(os.environ.get("DISCOURSE_AGENTS_PER_TICK", "2"))
REPLY_PROBABILITY = float(os.environ.get("DISCOURSE_REPLY_PROBABILITY", "0.3"))
INITIAL_DELAY_S = float(os.environ.get("DISCOURSE_INITIAL_DELAY_S", "60"))
ENABLED = os.environ.get("DISCOURSE_ENABLED", "1").lower() in ("1", "true", "yes")

# Phase R+ — three-mode discourse
INTENT_AGENTS_ALL = os.environ.get("DISCOURSE_INTENT_AGENTS_ALL", "1").lower() in ("1", "true", "yes")
INTENT_TIMEOUT_S = float(os.environ.get("DISCOURSE_INTENT_TIMEOUT_S", "60"))
INTENT_QUERY_ROUNDS = int(os.environ.get("DISCOURSE_INTENT_QUERY_ROUNDS", "1"))
RESPONSE_AGENTS_PER_TICK = int(os.environ.get("DISCOURSE_RESPONSE_AGENTS_PER_TICK", "4"))
RESPONSE_TICK_INTERVAL_S = float(os.environ.get("DISCOURSE_RESPONSE_TICK_INTERVAL_S", "30"))
RESPONSE_QUEUE_MAX = int(os.environ.get("DISCOURSE_RESPONSE_QUEUE_MAX", "50"))
CONFIDENCE_DISPATCH_THRESHOLD = float(os.environ.get("DISCOURSE_CONFIDENCE_THRESHOLD", "0.8"))

MIROFISH_URL = os.environ.get("MIROFISH_URL", "http://127.0.0.1:5101").rstrip("/")
OPENFANG_URL = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200").rstrip("/")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:5000").rstrip("/")

# Where setup_mirofish_brain_sim.py persisted the running sim id
_BRAIN_DIR = Path(__file__).resolve().parent.parent
SIM_STATE_FILE = _BRAIN_DIR / "data" / "discourse_sim.json"

# Rotating KG slice sources. Each entry is
# (collection_logical_name, node_type_filter_or_None, payload_filter_or_None).
# payload_filter is a dict {key: value} that further narrows the scroll
# (e.g. {"self_awareness": True} to only sample architecture concepts
# seeded by Phase S.1).
SLICE_SOURCES: List[Tuple[str, Optional[str], Optional[Dict[str, Any]]]] = [
    ("episodic",   "thought",  None),
    ("episodic",   "response", None),
    # Phase S.2: prefer architecture concepts (self-awareness substrate)
    # before generic semantic concepts so Brain reflects on itself.
    ("semantic",   "concept",  {"self_awareness": True}),
    ("semantic",   "concept",  None),
    ("procedural", "space",    None),
    ("procedural", "event",    None),
    ("artifacts",  "idea",     None),
    ("artifacts",  "bubble",   None),
]

# Domain → agent-tag mapping for picking who tweets about what
DOMAIN_TAG_MAP: Dict[str, List[str]] = {
    "episodic":   ["knowledge", "memory", "vibemind"],
    "semantic":   ["knowledge", "ideas", "vibemind"],
    "procedural": ["coding", "devops", "orchestration"],
    "artifacts":  ["ideas", "knowledge", "rowboat"],
}

DISCOURSE_PROMPT_TEMPLATE = """\
You are {agent_name}, a {persona_role}. Look at this slice from the
{collection} knowledge graph (node_type={node_type}):

  Title:       {title}
  Snippet:     {snippet}
  Created:     {created_at}
  Tags:        {tags}

In 1-2 short sentences, write a single Tweet (≤ 240 chars) reflecting
on this from your perspective: is it fresh, stale, useful, missing
context, related to your work? Stay in character. Match the language
of the slice (German if German, else English). Output the tweet text
only — no quotes, no preamble.
"""

# Phase S.2 — Self-awareness prompt: when the slice is a Brain architecture
# concept (subsystem-tagged via seed_self_awareness.py), agents reflect on
# the *system* itself rather than treating it as opaque content.
SELF_AWARE_PROMPT_TEMPLATE = """\
You are {agent_name}, a {persona_role}.

Brain is reflecting on itself. Here's one of its own architectural
components:

  Module:      {title}
  Subsystem:   {subsystem}
  Source:      {source_path}
  Description: {snippet}

In 1-2 short sentences (≤ 240 chars), write a Tweet about your
relationship to this component: how would you interact with it? What
does it enable or limit for you? Stay in character. Match the language
of the description (German if German, else English). Output the tweet
text only — no quotes, no preamble.
"""

REPLY_PROMPT_TEMPLATE = """\
You are {agent_name}, a {persona_role}. Another agent ({prev_agent}) just
posted this in our internal discourse:

  > {prev_tweet}

Write a 1-2 sentence reply (≤ 240 chars) from your own perspective.
Agree, disagree, add context, or note something they missed. Stay in
character. Output the reply text only.
"""

# Phase R+ — Intent prompt with hybrid-search QUERY: pattern
INTENT_PROMPT_TEMPLATE = """\
You are {agent_name}, a {persona_role}.

A user just posted this intent / task:
  "{intent}"

Available context (from Brain's KGs):
{context}

Decide whether this falls in your area of responsibility. You may:

  1. Answer with a 1-2 sentence Tweet (≤ 240 chars). Format:
       "I CAN: <how you would handle this>"   if you'd take it
       "RELATED: <how you'd contribute>"      if you'd assist but not lead
       "NOT MINE: <why this is not your area>" if you'd skip
  2. OR reply with "QUERY: <topic>" to request more context from Brain's KGs
     before committing. You'll be re-prompted with the search hits.

Output the tweet text only — no quotes, no preamble.
"""

INTENT_QUERY_RETRY_TEMPLATE = """\
You are {agent_name}, a {persona_role}.

Earlier, given this intent:
  "{intent}"

You replied "QUERY: {query_topic}". Brain searched and found:

{hits}

Now answer the original intent in 1-2 sentences (≤ 240 chars).
Format: "I CAN: ..." or "RELATED: ..." or "NOT MINE: ...".
Output tweet text only.
"""

# Phase R+ — Response-ordnen prompt
RESPONSE_PROMPT_TEMPLATE = """\
You are {agent_name}, a {persona_role}.

Brain just produced this response to a user:

  > {response_text}

Was the answer good? In 1-2 sentences (≤ 240 chars), say what's strong,
what's missing, or what risk/follow-up you see — from your perspective.

Format: "STRONG: ..." or "MISSING: ..." or "RISK: ..." or "FINE."
Output tweet text only.
"""


class DiscourseEngine:
    """30s discourse driver. Brain → OpenFang phi3-clones → Mirofish."""

    def __init__(self, kg, dispatcher=None) -> None:
        """Args:
            kg: QdrantKG instance (used for slice fetching + hybrid-search).
            dispatcher: SubagentDispatcher (for Groq-based intent aggregation).
        """
        self.kg = kg
        self.dispatcher = dispatcher
        self._fungus_client = None  # S.3 — wired via set_fungus_client()
        self._cap_router = None     # Phase 1 capability routing — wired via set_capability_router()
        self._stop = threading.Event()
        self._stop_response = threading.Event()
        self._paused = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._response_worker: Optional[threading.Thread] = None
        self._slice_idx = 0
        self._last_tweet: Optional[Dict[str, Any]] = None
        self._sim_id: Optional[str] = None
        self._agents: List[Dict[str, Any]] = []
        # Phase R+ — response queue + intent decision history
        from collections import deque
        self._response_queue: "deque[Dict[str, Any]]" = deque(maxlen=RESPONSE_QUEUE_MAX)
        self._intent_decisions: "deque[Dict[str, Any]]" = deque(maxlen=50)
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "tweets_posted": 0,
            "replies_posted": 0,
            "tweet_failures": 0,
            "reply_failures": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
            "last_tweet_preview": None,
            "sim_id": None,
            "agents_loaded": 0,
            # Phase R+ stats
            "intent_ticks": 0,
            "intent_tweets": 0,
            "intent_decisions": 0,
            "intent_high_confidence": 0,
            "response_ticks": 0,
            "response_tweets": 0,
            "response_queue_depth": 0,
            "query_rounds_run": 0,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[discourse] disabled via DISCOURSE_ENABLED=0")
            return
        if not (self._worker and self._worker.is_alive()):
            self._stop.clear()
            self._worker = threading.Thread(
                target=self._loop, daemon=True, name="DiscourseEngineIdle",
            )
            self._worker.start()
            logger.info(
                f"[discourse] idle loop started (tick={TICK_INTERVAL_S}s)"
            )
        # Phase R+ — also start response-tick loop (reads from response queue)
        if not (self._response_worker and self._response_worker.is_alive()):
            self._stop_response.clear()
            self._response_worker = threading.Thread(
                target=self._response_loop, daemon=True,
                name="DiscourseEngineResponse",
            )
            self._response_worker.start()
            logger.info(
                f"[discourse] response loop started "
                f"(tick={RESPONSE_TICK_INTERVAL_S}s, agents={RESPONSE_AGENTS_PER_TICK})"
            )

    def stop(self) -> None:
        self._stop.set()
        self._stop_response.set()
        if self._worker:
            self._worker.join(timeout=5)
        if self._response_worker:
            self._response_worker.join(timeout=5)

    def pause(self) -> None:
        """Pause idle + response loops without killing threads. Intent-on-demand still works."""
        self._paused.set()
        logger.info("[discourse] paused (idle + response loops will skip ticks)")

    def resume(self) -> None:
        self._paused.clear()
        logger.info("[discourse] resumed")

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def set_fungus_client(self, client) -> None:
        """Phase S.3 — wire FungusClient so query-rounds can fetch real
        code-snippets in addition to KG architecture concepts."""
        self._fungus_client = client

    def set_capability_router(self, router) -> None:
        """Phase 1 capability routing — when set, tick_intent narrows the
        agent set to the matched capability's primary+supporting list
        instead of broadcasting to all 25. No-op if router is None or
        the intent doesn't match any capability."""
        self._cap_router = router
        # Phase 1.5 — DirectExecutor cache, lazily populated per
        # capability on first direct-execution call. Wiped on router
        # reload so YAML changes to execution_target propagate.
        self._executor_cache = {}

    def _get_executor(self, target: str):
        """Get or create an executor for the given target string. Cached
        per-target so we don't re-import or re-resolve on every call.

        Phase 4 — falls through to capability_targets.build_executor which
        handles direct:/http:/n8n:/coding-engine:/openfang:/brain:/mcp:
        kinds. The original DirectExecutor still owns the `direct:` path."""
        cache = getattr(self, "_executor_cache", None)
        if cache is None:
            cache = {}
            self._executor_cache = cache
        if target not in cache:
            try:
                from core.capability_targets import build_executor
                cache[target] = build_executor(target)
            except Exception as e:
                logger.warning(f"[discourse] cannot build executor for {target!r}: {e}")
                cache[target] = None
        return cache[target]

    def set_validator(self, validator) -> None:
        """Phase 3 — wire a CapabilityValidator that gets called after every
        direct-execution result. No-op if None; existing direct path stays
        identical."""
        self._validator = validator

    def record_user_topic(self, intent_text: str) -> None:
        """Phase 7.2 — accumulate domain-words from recent user intents
        so idle-discourse can bias slice picking towards what the user
        is currently working on."""
        if not hasattr(self, "_recent_user_topics"):
            from collections import deque as _deque
            self._recent_user_topics = _deque(maxlen=20)
        if not intent_text:
            return
        # Trivial keyword extraction: keep nouns ≥4 chars, drop common stop
        # words. Doesn't need to be perfect — semantic-search forgives.
        stop = {
            "create", "make", "add", "then", "evaluate", "have", "would",
            "with", "from", "this", "that", "about", "into", "onto",
            "what", "where", "when", "which", "what's", "could", "should",
            "really", "very", "much", "more", "less", "über", "the", "and",
            "for", "but", "not", "you", "your", "his", "her", "ihr", "its",
            "are", "were", "was", "wer", "wie", "the", "der", "die", "das",
            "ein", "eine", "einer", "und", "oder", "aber", "ist", "sind",
            "haben", "kann", "können", "müssen", "sollte", "would", "could",
        }
        for w in intent_text.lower().split():
            w = w.strip(".,!?;:'\"()[]{}").strip()
            if len(w) < 4 or w in stop or w.isdigit():
                continue
            self._recent_user_topics.append(w)

    def set_curator(self, curator) -> None:
        """Phase 5 — wire a CapabilityCurator. record_intent() will be
        called on every routing decision (match or no-match)."""
        self._curator = curator

    def _handle_direct_capability(
        self, cap_match, intent_text: str, ctx_block: str,
    ) -> Dict[str, Any]:
        """Phase 1.5 — execute a `direct:...` capability and optionally run
        a feedback-loop discourse round over the result.

        Returns the same record shape as tick_intent's normal path so
        callers don't need to special-case direct vs broadcast results.
        New fields: `result` (the raw direct-executor output) and
        `direct_elapsed_s`.
        """
        from core.capability_executor import extract_arg

        target = cap_match.execution_target
        executor = self._get_executor(target)
        if executor is None or not executor.is_resolvable():
            # Fall back to normal discourse if target unresolvable.
            logger.warning(
                f"[discourse] direct target {target!r} unresolvable, "
                f"falling back to broadcast for capability={cap_match.capability}"
            )
            return self._fallback_to_broadcast(cap_match, intent_text, ctx_block)

        # Extract the positional arg (e.g. bubble name) from the user's intent
        arg = extract_arg(intent_text, cap_match.arg_extractor)
        logger.info(
            f"[discourse] capability={cap_match.capability} direct-execute "
            f"target={target} arg={arg!r}"
        )

        # Call the python function directly. arg_kwarg (from YAML) shapes
        # the call: positional fn(arg) by default, or fn({arg_kwarg: arg})
        # for legacy voice-tools that take a params dict.
        arg_kwarg = getattr(cap_match, "arg_kwarg", None)
        if arg is not None:
            exec_result = executor.call_with_arg(arg, arg_kwarg=arg_kwarg)
        else:
            # No arg extractor configured or extraction failed — call with
            # the raw intent text as the only argument.
            exec_result = executor.call_with_arg(intent_text, arg_kwarg=arg_kwarg)

        self.stats["intent_ticks"] += 1
        self.stats.setdefault("direct_executions", 0)
        self.stats["direct_executions"] += 1

        if not exec_result.get("ok"):
            # Tool failed — return the error as the response, no feedback round
            return {
                "ok": False,
                "intent": intent_text[:300],
                "capability": cap_match.capability,
                "matched_pattern": cap_match.matched_pattern,
                "is_direct": True,
                "direct_error": exec_result.get("error"),
                "direct_elapsed_s": exec_result.get("elapsed_s"),
                "tweets": [],
                "tweet_count": 0,
                "decision": {},
                "high_confidence": False,
                "ts": time.time(),
            }

        raw_result = exec_result.get("result")

        # Phase 3 — Validator. Read the validator config off cap_match (set
        # by capability_router from YAML) and run it. The result is added to
        # the record under `validation`. on_fail='retry' triggers one
        # re-call; on_fail='block' converts the record to ok=False.
        validation = None
        validator_cfg = getattr(cap_match, "validator", None)
        if validator_cfg is None and isinstance(getattr(cap_match, "feedback_loop", None), dict):
            # Backwards compat — accept inline 'validator' under feedback_loop too
            validator_cfg = cap_match.feedback_loop.get("validator")
        validator = getattr(self, "_validator", None)
        if validator and validator_cfg:
            try:
                validation = validator.validate(
                    validator_cfg,
                    intent=intent_text,
                    arg=arg or "",
                    raw_result=raw_result,
                )
            except Exception as e:
                logger.warning(f"[discourse] validator threw: {e}")
                validation = {
                    "valid": False,
                    "reason": f"validator error: {e}",
                    "kind": validator_cfg.get("kind") if isinstance(validator_cfg, dict) else "?",
                    "on_fail": "report",
                    "elapsed_s": 0.0,
                    "error": f"{type(e).__name__}: {e}",
                }

            # Retry once if validator said invalid AND on_fail='retry'
            if validation and not validation.get("valid") and validation.get("on_fail") == "retry":
                logger.info(
                    f"[discourse] validator rejected, retrying once: "
                    f"{validation.get('reason')}"
                )
                self.stats.setdefault("validator_retries", 0)
                self.stats["validator_retries"] += 1
                if arg is not None:
                    exec_result = executor.call_with_arg(arg, arg_kwarg=arg_kwarg)
                else:
                    exec_result = executor.call_with_arg(intent_text, arg_kwarg=arg_kwarg)
                raw_result = exec_result.get("result")
                try:
                    validation = validator.validate(
                        validator_cfg,
                        intent=intent_text,
                        arg=arg or "",
                        raw_result=raw_result,
                    )
                except Exception as e:
                    logger.warning(f"[discourse] validator threw on retry: {e}")

            # Block if validator says invalid AND on_fail='block'
            if validation and not validation.get("valid") and validation.get("on_fail") == "block":
                self.stats.setdefault("validator_blocks", 0)
                self.stats["validator_blocks"] += 1
                return {
                    "ok": False,
                    "intent": intent_text[:300],
                    "capability": cap_match.capability,
                    "matched_pattern": cap_match.matched_pattern,
                    "is_direct": True,
                    "direct_target": target,
                    "direct_elapsed_s": round(exec_result.get("elapsed_s") or 0.0, 2),
                    "result": raw_result,
                    "validation": validation,
                    "blocked_by_validator": True,
                    "tweets": [],
                    "tweet_count": 0,
                    "decision": {},
                    "high_confidence": False,
                    "ts": time.time(),
                }

        # Feedback loop — run a small reflective discourse round over the
        # raw result so the user gets a coherent recommendation, not a
        # 64-item dump.
        feedback_cfg = cap_match.feedback_loop or {}
        run_feedback = bool(feedback_cfg.get("enabled"))
        feedback_decision = None
        feedback_tweets: List[Dict[str, Any]] = []

        if run_feedback:
            try:
                feedback_tweets, feedback_decision = self._run_feedback_round(
                    feedback_cfg=feedback_cfg,
                    intent_text=intent_text,
                    arg=arg or "",
                    raw_result=raw_result,
                    cap_match=cap_match,
                )
            except Exception as e:
                logger.warning(f"[discourse] feedback round failed: {e}")
                self.stats["last_error"] = f"feedback_round: {type(e).__name__}: {e}"

        record = {
            "ok": True,
            "intent": intent_text[:300],
            "capability": cap_match.capability,
            "matched_pattern": cap_match.matched_pattern,
            "is_direct": True,
            "direct_target": target,
            "direct_elapsed_s": round(exec_result.get("elapsed_s") or 0.0, 2),
            "result": raw_result,
            "validation": validation,
            "tweets": feedback_tweets[:30],
            "tweet_count": len(feedback_tweets),
            "decision": feedback_decision or {},
            "high_confidence": bool(
                feedback_decision
                and feedback_decision.get("confidence", 0.0)
                >= CONFIDENCE_DISPATCH_THRESHOLD
            ),
            "ts": time.time(),
        }
        self._intent_decisions.append(record)
        return record

    def _fallback_to_broadcast(
        self, cap_match, intent_text: str, ctx_block: str,
    ) -> Dict[str, Any]:
        """Helper used when a direct target fails to resolve — re-enters the
        normal flow with the matched capability cleared so we don't loop."""
        # Stash the original cap_match so router-rot is visible in stats,
        # but clear `is_direct` so we don't recurse into _handle_direct_*.
        logger.info(
            f"[discourse] direct fallback for capability={cap_match.capability}"
        )
        # Re-run tick_intent without the direct-flag by temporarily
        # disabling the router. Cheap — only used on rare unresolvable case.
        saved = self._cap_router
        self._cap_router = None
        try:
            return self.tick_intent(intent_text)
        finally:
            self._cap_router = saved

    def _run_feedback_round(
        self,
        feedback_cfg: Dict[str, Any],
        intent_text: str,
        arg: str,
        raw_result: Dict[str, Any],
        cap_match,
    ):
        """Phase 1.5 — fan out the structured exec result to a small focused
        agent set via OpenFang's direct agent-message endpoint, get reflective
        replies, aggregate as usual.

        Important: feedback agents are dispatched via OpenFang `/api/agents/<id>/message`
        directly rather than via Mirofish-interview, because the configured
        agents (e.g. brain-coder, fungus-search, poc-security-scanner) live in
        OpenFang's persistent agent pool, not as personas inside a per-sim
        Mirofish graph. This bypasses the "agents not in sim" failure mode.

        Returns (tweets, decision).
        """
        from concurrent.futures import (
            ThreadPoolExecutor,
            as_completed,
            TimeoutError as FuturesTimeoutError,
        )
        import os
        import requests

        # Resolve agent names against loaded OpenFang agents (these are the
        # ones DiscourseEngine has cached at startup via _ensure_agents).
        wanted_names = [n.lower() for n in (feedback_cfg.get("agents") or [])]
        wanted = set(wanted_names)
        targets = []
        for a in self._agents:
            aname = (a.get("name") or "").lower()
            base = aname[:-5] if aname.endswith("-phi3") else aname
            if base in wanted or aname in wanted:
                targets.append(a)
        if not targets:
            logger.warning(
                f"[discourse] feedback agents {wanted_names} not resolved against "
                f"OpenFang's loaded pool — skipping feedback round"
            )
            return [], None

        # Build the feedback prompt from the template
        template = feedback_cfg.get("prompt_template") or (
            "A tool returned this result: {raw_result_summary}\n\n"
            "Original intent: {original_intent}\n\nReply with a short take."
        )
        prompt = self._format_feedback_prompt(
            template=template,
            intent_text=intent_text,
            arg=arg,
            raw_result=raw_result,
        )

        of_url = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200").rstrip("/")

        def _dispatch_one(agent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            agent_id = agent.get("id")
            if not agent_id:
                return None
            try:
                r = requests.post(
                    f"{of_url}/api/agents/{agent_id}/message",
                    json={"message": prompt[:30000], "sender_name": "Brain"},
                    timeout=INTENT_TIMEOUT_S,
                )
                if not r.ok:
                    return None
                d = r.json() or {}
                return {
                    "agent_id":  agent_id,
                    "agent_name": agent.get("name"),
                    "response":  (d.get("response") or "").strip()[:800],
                    "ts": time.time(),
                }
            except Exception as e:
                logger.debug(f"[discourse] feedback dispatch to {agent.get('name')} failed: {e}")
                return None

        # Fan out — feedback agents respond in parallel
        tweets: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
            futs = {pool.submit(_dispatch_one, ag): ag for ag in targets}
            try:
                for f in as_completed(futs, timeout=INTENT_TIMEOUT_S + 5):
                    try:
                        res = f.result(timeout=1)
                    except Exception:
                        continue
                    if not res or not res.get("response"):
                        continue
                    tweets.append(res)
            except FuturesTimeoutError:
                done = sum(1 for f in futs if f.done())
                logger.warning(
                    f"[discourse] feedback round timeout: {done}/{len(futs)} replies"
                )
                for f in futs:
                    if not f.done():
                        f.cancel()

        # Aggregate
        decision = self._aggregate_intent_decision(intent_text, tweets) if tweets else None
        return tweets, decision

    @staticmethod
    def _format_feedback_prompt(
        template: str, intent_text: str, arg: str, raw_result: Dict[str, Any],
    ) -> str:
        """Substitute well-known placeholders in the feedback template.
        Tolerant of missing fields — returns a usable prompt even when the
        raw_result has unexpected shape."""
        # Pull common fields out of raw_result with sane defaults
        if not isinstance(raw_result, dict):
            raw_result = {"summary": str(raw_result)[:500]}

        # Different tools name this differently — check both common shapes.
        per_agent = (
            raw_result.get("per_agent")
            or raw_result.get("per_agent_scores")
            or {}
        )
        per_agent_summary = "\n".join(
            f"  - {name}: {data.get('score', '?')}/25"
            for name, data in list(per_agent.items())[:10]
        ) or "(no per-agent breakdown)"

        missing = raw_result.get("missing_items") or []
        missing_top10 = "\n".join(
            f"  {i+1}. {str(m)[:200]}"
            for i, m in enumerate(missing[:10])
        ) or "(none)"

        substitutions = {
            "bubble_name": str(arg or "(unknown)"),
            "original_intent": str(intent_text or "")[:300],
            "total_score": str(raw_result.get("total_score", "?")),
            "prediction": str(raw_result.get("prediction", "?")),
            "per_agent_summary": per_agent_summary,
            "missing_count": str(len(missing)),
            "missing_items_top10": missing_top10,
            # Generic catch-all for templates that prefer a single dump
            "raw_result_summary": str(raw_result)[:800],
        }
        try:
            return template.format(**substitutions)
        except KeyError as e:
            # Template uses a placeholder we don't know about — return
            # something informative rather than crashing.
            logger.warning(f"[discourse] feedback template missing key: {e}")
            return template + f"\n\n[result] {str(raw_result)[:500]}"

    def _loop(self) -> None:
        # Initial delay so Mirofish has fully booted + we re-load if sim got created late
        self._sleep_interruptible(INITIAL_DELAY_S)
        while not self._stop.is_set():
            if self._paused.is_set():
                # Phase 6.14.2 — short responsive sleep instead of full
                # tick interval so resume() takes effect within ~1s.
                self._sleep_interruptible(1.0)
                continue
            try:
                self.tick_idle()
                self.stats["ticks"] += 1
                self.stats["last_tick_ts"] = time.time()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"tick: {type(e).__name__}: {e}"
                logger.warning(f"[discourse] tick failed: {e}")
            self._sleep_interruptible(TICK_INTERVAL_S)

    def _response_loop(self) -> None:
        # Slight stagger after idle-loop boot
        self._sleep_interruptible(INITIAL_DELAY_S + 15, response=True)
        while not self._stop_response.is_set():
            if self._paused.is_set():
                self._sleep_interruptible(1.0, response=True)
                continue
            try:
                if self._response_queue:
                    self.tick_response()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"response_tick: {type(e).__name__}: {e}"
                logger.warning(f"[discourse] response tick failed: {e}")
            self._sleep_interruptible(RESPONSE_TICK_INTERVAL_S, response=True)

    def _sleep_interruptible(self, seconds: float, *, response: bool = False) -> None:
        """Phase 6.14.2 — sleep that wakes on stop OR pause-state-change.
        Response-loop variant uses its own stop event."""
        stop_evt = self._stop_response if response else self._stop
        # Wake every 0.5s to recheck pause flag — bounded latency for resume.
        # We don't add a separate wake-event because creating one per tick
        # interval is cheaper than another threading.Event refcount path.
        deadline = time.time() + seconds
        while time.time() < deadline:
            remaining = deadline - time.time()
            if stop_evt.wait(min(remaining, 0.5)):
                return
            # Fast resume: if we were paused but now aren't, exit early
            # so the loop body re-enters and runs immediately.
            if not self._paused.is_set() and seconds > 1.0:
                # Only short-circuit on long sleeps (the regular tick),
                # not on the 1.0s pause-poll which already covers itself.
                if seconds >= TICK_INTERVAL_S - 0.1:
                    return

    # ── Initialization helpers ───────────────────────────────────────

    def _ensure_sim(self) -> bool:
        """Load simulation_id from data/discourse_sim.json. Returns False
        if not yet ready (setup script hasn't completed)."""
        if self._sim_id:
            return True
        if not SIM_STATE_FILE.exists():
            self.stats["last_error"] = "discourse_sim.json missing — run setup script"
            return False
        try:
            d = json.loads(SIM_STATE_FILE.read_text(encoding="utf-8"))
            sid = d.get("simulation_id")
            if not sid:
                self.stats["last_error"] = "no simulation_id in state file"
                return False
            self._sim_id = sid
            self.stats["sim_id"] = sid
            return True
        except Exception as e:
            self.stats["last_error"] = f"sim state read: {e}"
            return False

    def _ensure_agents(self) -> bool:
        """Refresh OpenFang agent list (filtering to phi3 clones)."""
        if self._agents:
            return True
        try:
            r = requests.get(f"{OPENFANG_URL}/api/agents", timeout=5)
            r.raise_for_status()
            all_agents = r.json()
            phi3 = [a for a in all_agents if (a.get("name") or "").endswith("-phi3")]
            if not phi3:
                # fallback: all running agents (in case clones not registered yet)
                phi3 = [a for a in all_agents if a.get("state") == "Running"]
            self._agents = phi3
            self.stats["agents_loaded"] = len(phi3)
            return bool(phi3)
        except Exception as e:
            self.stats["last_error"] = f"agent list: {e}"
            return False

    # ── Single tick ──────────────────────────────────────────────────

    def tick_once(self) -> Dict[str, Any]:
        """Backward-compat alias for tick_idle()."""
        return self.tick_idle()

    def tick_idle(self) -> Dict[str, Any]:
        """One idle discourse round (Mode 1). Random KG-slice + 1-3 agents."""
        if not self._ensure_sim() or not self._ensure_agents():
            return {"ok": False, "reason": self.stats.get("last_error")}

        # 1) Pick KG slice (Phase S.2: 3-tuple now includes payload_filter)
        coll, node_type, payload_filter = SLICE_SOURCES[
            self._slice_idx % len(SLICE_SOURCES)
        ]
        self._slice_idx += 1
        slice_doc = self._sample_slice(coll, node_type, payload_filter)
        if not slice_doc:
            return {"ok": False, "reason": f"empty slice ({coll}/{node_type})"}

        # 2) Pick agents
        chosen = self._pick_agents(coll, n=AGENTS_PER_TICK)
        if not chosen:
            return {"ok": False, "reason": "no agents available"}

        # 3) Tweet
        tweet_results: List[Dict[str, Any]] = []
        for ag in chosen:
            tw = self._post_tweet_for(ag, slice_doc, coll, node_type)
            if tw:
                tweet_results.append(tw)
                self._last_tweet = tw
                self.stats["tweets_posted"] += 1
                self.stats["last_tweet_preview"] = (tw.get("response") or "")[:140]
            else:
                self.stats["tweet_failures"] += 1

        # 4) Maybe reply (if previous tweet exists in this or recent tick)
        if self._last_tweet and random.random() < REPLY_PROBABILITY:
            rep_agents = [a for a in self._agents
                          if a.get("id") != self._last_tweet.get("agent_id")]
            if rep_agents:
                reply_ag = random.choice(rep_agents)
                rep = self._post_reply_for(reply_ag, self._last_tweet)
                if rep:
                    self.stats["replies_posted"] += 1
                else:
                    self.stats["reply_failures"] += 1

        return {
            "ok": True,
            "slice": {"collection": coll, "node_type": node_type,
                      "id": slice_doc.get("id")},
            "tweets": len(tweet_results),
        }

    # ── Slice sampling ───────────────────────────────────────────────

    def _sample_slice(
        self,
        coll_logical: str,
        node_type: Optional[str],
        payload_filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Random one point from the given Brain collection, biased to recent.

        payload_filter: optional {key: value} that further narrows the scroll
        (Phase S.2: e.g. {"self_awareness": True} to only sample seeded
        architecture concepts).

        Phase 7.2 — biases slice towards recent user topics: if any user
        intent in the last hour mentioned domain words, 50% chance we
        run a semantic search for one of those words instead of random
        scrolling. Otherwise behaviour is unchanged.
        """
        try:
            from core.qdrant_kg import COLLECTIONS
        except Exception:
            return None
        coll_name = COLLECTIONS.get(coll_logical)
        if not coll_name:
            return None

        # Phase 7.2 — topic-biased slice
        if hasattr(self, "_recent_user_topics") and self._recent_user_topics:
            if random.random() < 0.5:
                topic = random.choice(list(self._recent_user_topics))
                try:
                    hits = self.kg.search(
                        topic, limit=5, score_threshold=0.4,
                        collection=coll_logical, node_type=node_type,
                    )
                except TypeError:
                    try:
                        hits = self.kg.search(topic, limit=5)
                    except Exception:
                        hits = []
                except Exception:
                    hits = []
                if hits:
                    h = random.choice(hits[:5])
                    return {
                        "id": str(h.get("id") or h.get("point_id") or ""),
                        "title": h.get("title")
                            or (h.get("content", "") or "")[:80],
                        "node_type": h.get("node_type") or node_type,
                        "content": h.get("content", "") or h.get("text", ""),
                        "subsystem": h.get("subsystem"),
                        "_topic_biased": True,
                        "_source_topic": topic,
                    }
        try:
            qm = self.kg._qm
            must_conds = []
            if node_type:
                must_conds.append(
                    qm.FieldCondition(
                        key="node_type",
                        match=qm.MatchValue(value=node_type),
                    )
                )
            if payload_filter:
                for k, v in payload_filter.items():
                    must_conds.append(
                        qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                    )
            qfilter = qm.Filter(must=must_conds) if must_conds else None
            # Scroll a small batch and pick random
            batch, _ = self.kg.client.scroll(
                collection_name=coll_name,
                scroll_filter=qfilter,
                limit=50,
                with_payload=True,
                with_vectors=False,
            )
            if not batch:
                return None
            rec = random.choice(batch)
            p = rec.payload or {}
            return {
                "id": str(rec.id),
                "title": p.get("title") or p.get("content", "")[:80],
                "snippet": (p.get("content") or p.get("description") or "")[:300],
                "created_at": p.get("created_at") or "",
                "tags": p.get("tags") or [],
                # Phase S.2: pass-through fields used by self-aware prompt
                "subsystem": p.get("subsystem"),
                "source_path": p.get("source_path"),
                "self_awareness": bool(p.get("self_awareness")),
            }
        except Exception as e:
            self.stats["last_error"] = f"slice fetch: {e}"
            return None

    # ── Agent selection ──────────────────────────────────────────────

    def _pick_agents(self, coll_logical: str, n: int) -> List[Dict[str, Any]]:
        if not self._agents:
            return []
        target_tags = set(DOMAIN_TAG_MAP.get(coll_logical, []))
        if target_tags:
            scored = []
            for a in self._agents:
                tags = set(a.get("tags") or [])
                score = len(target_tags & tags)
                scored.append((score, a))
            scored.sort(key=lambda x: -x[0])
            top = [a for s, a in scored if s > 0][:n * 2]
            if not top:
                top = [a for _, a in scored][:n * 2]
            return random.sample(top, min(n, len(top)))
        return random.sample(self._agents, min(n, len(self._agents)))

    # ── Tweet / Reply via Mirofish interview ─────────────────────────

    def _post_tweet_for(
        self,
        agent: Dict[str, Any],
        slice_doc: Dict[str, Any],
        coll: str,
        node_type: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Ask Mirofish to interview the agent with our discourse prompt;
        the response is captured as a tweet."""
        # Phase S.2: self-aware slices get a different prompt that frames
        # the content as Brain's own architecture rather than opaque data.
        if slice_doc.get("self_awareness"):
            prompt = SELF_AWARE_PROMPT_TEMPLATE.format(
                agent_name=agent.get("name") or "unnamed",
                persona_role=(agent.get("description") or "VibeMind agent")[:80],
                title=slice_doc.get("title", "")[:200],
                subsystem=slice_doc.get("subsystem") or "(unknown)",
                source_path=slice_doc.get("source_path") or "(synthetic)",
                snippet=slice_doc.get("snippet", "")[:500],
            )
        else:
            prompt = DISCOURSE_PROMPT_TEMPLATE.format(
                agent_name=agent.get("name") or "unnamed",
                persona_role=(agent.get("description") or "VibeMind agent")[:80],
                collection=coll,
                node_type=node_type or "any",
                title=slice_doc.get("title", "")[:200],
                snippet=slice_doc.get("snippet", "")[:300],
                created_at=slice_doc.get("created_at", ""),
                tags=", ".join(slice_doc.get("tags") or []) or "—",
            )
        try:
            r = requests.post(
                f"{MIROFISH_URL}/api/simulation/interview",
                json={
                    "simulation_id": self._sim_id,
                    "agent_id": self._mirofish_agent_id_for(agent),
                    "prompt": prompt,
                    "platform": "twitter",
                    "timeout": 60,
                },
                timeout=90,
            )
            if r.status_code >= 400:
                logger.debug(f"[discourse] interview HTTP {r.status_code}: {r.text[:300]}")
                return None
            d = r.json()
            if not d.get("success"):
                return None
            result = (d.get("data") or {}).get("result") or {}
            response = result.get("response") or ""
            if not response.strip():
                return None
            return {
                "agent_id": agent.get("id"),
                "agent_name": agent.get("name"),
                "response": response.strip()[:500],
                "slice": slice_doc.get("id"),
                "ts": time.time(),
            }
        except Exception as e:
            self.stats["last_error"] = f"interview: {type(e).__name__}: {e}"
            return None

    def _post_reply_for(
        self,
        agent: Dict[str, Any],
        prev: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        prompt = REPLY_PROMPT_TEMPLATE.format(
            agent_name=agent.get("name") or "unnamed",
            persona_role=(agent.get("description") or "VibeMind agent")[:80],
            prev_agent=prev.get("agent_name") or "another agent",
            prev_tweet=(prev.get("response") or "")[:240],
        )
        try:
            r = requests.post(
                f"{MIROFISH_URL}/api/simulation/interview",
                json={
                    "simulation_id": self._sim_id,
                    "agent_id": self._mirofish_agent_id_for(agent),
                    "prompt": prompt,
                    "platform": "twitter",
                    "timeout": 60,
                },
                timeout=90,
            )
            if r.status_code >= 400:
                return None
            d = r.json()
            if not d.get("success"):
                return None
            return (d.get("data") or {}).get("result") or {}
        except Exception:
            return None

    # ── Phase R+ — Intent-mode (Mode 2) ──────────────────────────────

    def tick_intent(self, intent_text: str, context: Optional[Dict[str, Any]] = None,
                    ) -> Dict[str, Any]:
        """All-26-Agents-parallel discourse round triggered by a User intent.

        Returns a decision dict::

          {
            "ok": True,
            "intent": "...",
            "tweets": [{agent_name, response, ...}],
            "decision": {primary, supporting, risks, confidence, reasoning},
            "high_confidence": True/False,
          }
        """
        from concurrent.futures import (
            ThreadPoolExecutor,
            as_completed,
            TimeoutError as FuturesTimeoutError,
        )

        if not self._ensure_sim() or not self._ensure_agents():
            return {"ok": False, "reason": self.stats.get("last_error")}

        ctx_block = self._format_context(context or {})

        # Phase 1 capability routing — narrow agent set if the intent
        # matches a capability in the registry. Falls back to broadcast
        # on no-match (existing behavior).
        cap_match = None
        if self._cap_router is not None:
            try:
                cap_match = self._cap_router.route(intent_text)
            except Exception as e:
                logger.warning(f"[discourse] capability router failed: {e}")
                cap_match = None

        # Phase 5 — telemetry. Record every routing decision so the
        # curator can later cluster missed intents and propose new
        # capabilities. Safe no-op if curator is unwired.
        curator = getattr(self, "_curator", None)
        if curator is not None:
            try:
                curator.record_intent(
                    intent_text,
                    matched=bool(cap_match),
                    capability=cap_match.capability if cap_match else None,
                    match_method=cap_match.match_method if cap_match else None,
                )
            except Exception as e:
                logger.debug(f"[discourse] curator log failed: {e}")

        # L4 GapSentinel — no capability matched this intent (route() -> None) = NO_TOOL.
        # Detect + autonomously dispatch to the capability-gap-filer agent (C1, live-green)
        # to file an issue. Flag-gated (CAPABILITY_GAP_ENABLED), fire-and-forget (daemon
        # thread) so it never blocks discourse; the gap-filer dedups (one issue per cap).
        if cap_match is None:
            try:
                from core import capability_gap as _gap
                if _gap.ENABLED:
                    _g = _gap.assess_no_tool(intent_text, None)
                    if _g:
                        import threading
                        threading.Thread(
                            target=_gap.handle, args=(_g,),
                            kwargs=dict(live=False, dispatcher=_gap.default_dispatcher),
                            daemon=True,
                        ).start()
            except Exception:
                pass  # never let gap detection break discourse

        # Phase 1.5 — direct execution short-circuit. If the matched
        # capability has an `execution_target: direct:...`, call the python
        # function directly instead of running discourse, then optionally
        # run a feedback-loop round to synthesise the structured result
        # into a coherent recommendation.
        # Phase 4 — same path now also handles http:/n8n:/coding-engine:/etc.
        if cap_match is not None and getattr(cap_match, "has_execution_target", False):
            return self._handle_direct_capability(cap_match, intent_text, ctx_block)

        if cap_match is not None and cap_match.all_agent_names:
            wanted = {n.lower() for n in cap_match.all_agent_names}
            # Match either the bare agent name or its '-phi3' variant — we
            # want both flavors when the YAML lists e.g. 'poc-keycloak' so
            # the discourse round uses the cheap local clone.
            narrowed = []
            for a in self._agents:
                aname = (a.get("name") or "").lower()
                base = aname[:-5] if aname.endswith("-phi3") else aname
                if base in wanted or aname in wanted:
                    narrowed.append(a)
            if narrowed:
                targets = narrowed
                logger.info(
                    f"[discourse] capability={cap_match.capability} "
                    f"matched {len(narrowed)}/{len(self._agents)} agents "
                    f"(pattern={cap_match.matched_pattern!r})"
                )
            else:
                # YAML referenced agent names not present in OpenFang —
                # fall back to broadcast and warn so registry-rot is visible.
                logger.warning(
                    f"[discourse] capability={cap_match.capability} matched but "
                    f"none of {sorted(wanted)} resolved against OpenFang's loaded "
                    f"agents — falling back to broadcast"
                )
                targets = self._agents if INTENT_AGENTS_ALL else self._agents[:8]
        else:
            # No capability registered for this intent OR capability has no agent
            # list (e.g. bubble_evaluate which is direct-execution only — Phase 1.5
            # will short-circuit before reaching here; Phase 1 broadcasts).
            targets = self._agents if INTENT_AGENTS_ALL else self._agents[:8]

        tweets: List[Dict[str, Any]] = []
        queries: List[Tuple[Dict[str, Any], str]] = []  # (agent, query_topic)

        # Round 1 — fan out to all agents. Collect partial results on timeout
        # rather than crashing — Mirofish serializes calls, so 25 agents may
        # not all finish within INTENT_TIMEOUT_S.
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
            futs = {
                pool.submit(self._intent_call_for, ag, intent_text, ctx_block): ag
                for ag in targets
            }
            try:
                for f in as_completed(futs, timeout=INTENT_TIMEOUT_S + 5):
                    try:
                        res = f.result(timeout=1)
                    except Exception:
                        continue
                    if not res:
                        continue
                    ag = futs[f]
                    resp_text = (res.get("response") or "").strip()
                    if resp_text.upper().startswith("QUERY:"):
                        queries.append((ag, resp_text[6:].strip()[:200]))
                    else:
                        tweets.append({
                            "agent_id": ag.get("id"),
                            "agent_name": ag.get("name"),
                            "response": resp_text[:500],
                            "ts": time.time(),
                        })
            except FuturesTimeoutError:
                # Deadline hit — proceed with whatever finished. Cancel pending.
                done = sum(1 for f in futs if f.done())
                pending = len(futs) - done
                logger.warning(
                    f"[discourse] intent fan-out: {done}/{len(futs)} agents "
                    f"answered within {INTENT_TIMEOUT_S}s, cancelling {pending} pending"
                )
                for f in futs:
                    if not f.done():
                        f.cancel()

        # Round 2 — resolve QUERY: replies via Brain KG (max INTENT_QUERY_ROUNDS)
        if queries and INTENT_QUERY_ROUNDS >= 1:
            self.stats["query_rounds_run"] += 1
            tweets.extend(self._run_query_round(queries, intent_text))

        self.stats["intent_tweets"] += len(tweets)
        self.stats["intent_ticks"] += 1

        # Aggregator decision
        decision = self._aggregate_intent_decision(intent_text, tweets)
        if decision:
            self.stats["intent_decisions"] += 1
            if decision.get("confidence", 0.0) >= CONFIDENCE_DISPATCH_THRESHOLD:
                self.stats["intent_high_confidence"] += 1

        record = {
            "ok": True,
            "intent": intent_text[:300],
            "tweet_count": len(tweets),
            "tweets": tweets[:30],
            "decision": decision or {},
            "high_confidence": bool(decision and decision.get("confidence", 0.0)
                                    >= CONFIDENCE_DISPATCH_THRESHOLD),
            "ts": time.time(),
            "capability": cap_match.capability if cap_match else None,
            "matched_pattern": cap_match.matched_pattern if cap_match else None,
            "agents_targeted": len(targets),
            "agents_total": len(self._agents),
        }
        self._intent_decisions.append(record)
        return record

    def _intent_call_for(
        self, agent: Dict[str, Any], intent_text: str, ctx_block: str,
    ) -> Optional[Dict[str, Any]]:
        prompt = INTENT_PROMPT_TEMPLATE.format(
            agent_name=agent.get("name") or "unnamed",
            persona_role=(agent.get("description") or "VibeMind agent")[:80],
            intent=intent_text[:600],
            context=ctx_block or "(no extra context provided)",
        )
        return self._mirofish_interview(agent, prompt, timeout=INTENT_TIMEOUT_S)

    def _run_query_round(
        self,
        queries: List[Tuple[Dict[str, Any], str]],
        intent_text: str,
    ) -> List[Dict[str, Any]]:
        """For each (agent, query_topic) pair, hit the KG once and re-prompt."""
        from concurrent.futures import (
            ThreadPoolExecutor,
            as_completed,
            TimeoutError as FuturesTimeoutError,
        )

        # Cache KG hits per topic (multiple agents may ask the same)
        hits_by_topic: Dict[str, str] = {}
        for _ag, topic in queries:
            if topic in hits_by_topic:
                continue
            hits_by_topic[topic] = self._kg_search_format(topic)

        out: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(8, len(queries))) as pool:
            futs = {}
            for ag, topic in queries:
                prompt = INTENT_QUERY_RETRY_TEMPLATE.format(
                    agent_name=ag.get("name") or "unnamed",
                    persona_role=(ag.get("description") or "VibeMind agent")[:80],
                    intent=intent_text[:600],
                    query_topic=topic[:200],
                    hits=hits_by_topic.get(topic) or "(no hits)",
                )
                futs[pool.submit(self._mirofish_interview, ag, prompt,
                                  INTENT_TIMEOUT_S)] = ag
            try:
                for f in as_completed(futs, timeout=INTENT_TIMEOUT_S + 5):
                    try:
                        res = f.result(timeout=1)
                    except Exception:
                        continue
                    if not res:
                        continue
                    ag = futs[f]
                    out.append({
                        "agent_id": ag.get("id"),
                        "agent_name": ag.get("name"),
                        "response": ((res.get("response") or "").strip())[:500],
                        "via_query": True,
                        "ts": time.time(),
                    })
            except FuturesTimeoutError:
                logger.warning(
                    f"[discourse] query-round timed out, "
                    f"got {len(out)}/{len(queries)} responses"
                )
                for f in futs:
                    if not f.done():
                        f.cancel()
        return out

    def _kg_search_format(self, topic: str) -> str:
        """Search Brain KG (+ optionally fungus code-search) for a topic
        and return a compact markdown block.

        Phase S.3: when topic looks code-related, also pull 2 hits from
        fungus (if available) so agents get real code-snippets in
        QUERY-rounds, not just architecture concepts.
        """
        try:
            hits = self.kg.search(topic, limit=3, score_threshold=0.3)
        except Exception as e:
            hits = []
            kg_err = str(e)
        else:
            kg_err = None

        out_lines = []
        if hits:
            out_lines.append("From Brain KG:")
            for h in hits[:3]:
                p = h.get("payload") or {}
                title = p.get("title") or p.get("content", "")[:80]
                score = h.get("score", 0)
                out_lines.append(f"  - {title} (score {score:.2f})")
        elif kg_err:
            out_lines.append(f"(KG search failed: {kg_err})")
        else:
            out_lines.append(f"(no KG hits for '{topic}')")

        # Fungus code-search for code-y queries
        fungus = getattr(self, "_fungus_client", None)
        if fungus is not None and fungus.is_online and self._looks_like_code_query(topic):
            try:
                code_hits = fungus.search(topic, top_k=2)
                if code_hits:
                    out_lines.append("")
                    out_lines.append("From code (fungus):")
                    for h in code_hits[:2]:
                        path = h.get("path", "?")
                        score = h.get("score", 0)
                        snippet = (h.get("content") or "")[:200].replace("\n", " ")
                        out_lines.append(
                            f"  - {path} (score {score:.2f}): {snippet}"
                        )
            except Exception as e:
                logger.debug(f"[discourse] fungus search failed: {e}")

        return "\n".join(out_lines) if out_lines else f"(no hits for '{topic}')"

    @staticmethod
    def _looks_like_code_query(topic: str) -> bool:
        """Heuristic: is this query about implementation rather than concepts?"""
        if not topic:
            return False
        t = topic.lower()
        signals = (
            "file", "function", "class", "method", "code", ".py", ".rs",
            "implementation", "how does", "how do you", "where is",
            "module", "import", "def ", "class ", "implementiert",
            "wie funktioniert", "wo ist", "implementierung",
        )
        return any(s in t for s in signals)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Render the basic-context block that goes into intent prompts."""
        if not context:
            return ""
        parts = []
        if "kg_summary" in context:
            parts.append(f"KG summary: {context['kg_summary']}")
        if "recent_thoughts" in context:
            parts.append("Recent thoughts:\n" + "\n".join(
                f"  - {t}" for t in context.get("recent_thoughts") or []
            ))
        if "active_bubbles" in context:
            parts.append(f"Active bubbles: {', '.join(context['active_bubbles'])}")
        return "\n".join(parts)

    def _aggregate_intent_decision(
        self, intent_text: str, tweets: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Hand all tweets to an IntentAggregator (Groq) and parse decision."""
        if not tweets:
            return {"primary": None, "supporting": [], "risks": [],
                    "confidence": 0.0, "reasoning": "no agents responded"}
        try:
            from core.discourse_intent_aggregator import IntentAggregator
        except Exception as e:
            self.stats["last_error"] = f"aggregator import: {e}"
            return None
        agg = IntentAggregator(self.dispatcher)
        return agg.decide(intent_text, tweets)

    # ── Phase R+ — Response-mode (Mode 3) ────────────────────────────

    def queue_response(self, response_text: str, ctx: Optional[Dict[str, Any]] = None,
                       ) -> None:
        """Public — BrainChat calls this after each Brain response. The
        response-tick loop will pick from this queue every 30s."""
        if not response_text or not response_text.strip():
            return
        self._response_queue.append({
            "text": response_text[:2000],
            "ctx": ctx or {},
            "ts": time.time(),
        })
        self.stats["response_queue_depth"] = len(self._response_queue)

    def tick_response(self) -> Dict[str, Any]:
        """One Mode-3 round: dequeue oldest response, ask N random agents
        to assess. Tweets land in Mirofish (via interview)."""
        from concurrent.futures import (
            ThreadPoolExecutor,
            as_completed,
            TimeoutError as FuturesTimeoutError,
        )

        if not self._ensure_sim() or not self._ensure_agents():
            return {"ok": False, "reason": self.stats.get("last_error")}
        if not self._response_queue:
            return {"ok": False, "reason": "queue empty"}

        item = self._response_queue.popleft()
        self.stats["response_queue_depth"] = len(self._response_queue)
        text = item.get("text", "")

        chosen = random.sample(
            self._agents, min(RESPONSE_AGENTS_PER_TICK, len(self._agents)),
        )
        tweets: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(4, len(chosen))) as pool:
            futs = {
                pool.submit(self._response_call_for, ag, text): ag
                for ag in chosen
            }
            try:
                for f in as_completed(futs, timeout=INTENT_TIMEOUT_S + 5):
                    try:
                        res = f.result(timeout=1)
                    except Exception:
                        continue
                    if not res:
                        continue
                    ag = futs[f]
                    tweets.append({
                        "agent_id": ag.get("id"),
                        "agent_name": ag.get("name"),
                        "response": ((res.get("response") or "").strip())[:500],
                        "ts": time.time(),
                    })
            except FuturesTimeoutError:
                logger.warning(
                    f"[discourse] response-tick timed out, "
                    f"got {len(tweets)}/{len(chosen)} responses"
                )
                for f in futs:
                    if not f.done():
                        f.cancel()

        self.stats["response_tweets"] += len(tweets)
        self.stats["response_ticks"] += 1
        return {
            "ok": True,
            "tweets_posted": len(tweets),
            "response_excerpt": text[:120],
        }

    def _response_call_for(
        self, agent: Dict[str, Any], response_text: str,
    ) -> Optional[Dict[str, Any]]:
        prompt = RESPONSE_PROMPT_TEMPLATE.format(
            agent_name=agent.get("name") or "unnamed",
            persona_role=(agent.get("description") or "VibeMind agent")[:80],
            response_text=response_text[:1200],
        )
        return self._mirofish_interview(agent, prompt, timeout=INTENT_TIMEOUT_S)

    # ── Shared Mirofish-interview wrapper ────────────────────────────

    def _mirofish_interview(
        self, agent: Dict[str, Any], prompt: str, timeout: float = 60.0,
    ) -> Optional[Dict[str, Any]]:
        """Single Mirofish /interview call. Used by intent + response paths.
        Returns dict with {response, agent_id, platform, ...} or None."""
        try:
            r = requests.post(
                f"{MIROFISH_URL}/api/simulation/interview",
                json={
                    "simulation_id": self._sim_id,
                    "agent_id": self._mirofish_agent_id_for(agent),
                    "prompt": prompt,
                    "platform": "twitter",
                    "timeout": int(timeout),
                },
                timeout=timeout + 30,
            )
            if r.status_code >= 400:
                return None
            d = r.json()
            if not d.get("success"):
                return None
            result = (d.get("data") or {}).get("result") or {}
            return result
        except Exception as e:
            self.stats["last_error"] = f"interview: {type(e).__name__}: {e}"
            return None

    def _mirofish_agent_id_for(self, agent: Dict[str, Any]) -> int:
        """OpenFang uses UUIDs; Mirofish expects integer agent_ids 0..N-1.
        Stable mapping via index in our cached agent list."""
        for i, a in enumerate(self._agents):
            if a.get("id") == agent.get("id"):
                return i
        return 0

    # ── Intent-decision history ──────────────────────────────────────

    def intent_decisions(self, limit: int = 10) -> List[Dict[str, Any]]:
        return list(self._intent_decisions)[-limit:]

    # ── Stats ─────────────────────────────────────────────────────────

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "enabled": ENABLED,
            "tick_interval_s": TICK_INTERVAL_S,
            "agents_per_tick": AGENTS_PER_TICK,
            "reply_probability": REPLY_PROBABILITY,
            "intent_agents_all": INTENT_AGENTS_ALL,
            "response_agents_per_tick": RESPONSE_AGENTS_PER_TICK,
            "confidence_threshold": CONFIDENCE_DISPATCH_THRESHOLD,
            "running": bool(self._worker and self._worker.is_alive()),
            "response_loop_running": bool(self._response_worker and self._response_worker.is_alive()),
            "paused": self._paused.is_set(),
            **self.stats,
        }
