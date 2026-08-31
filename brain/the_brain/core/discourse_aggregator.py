"""
DiscourseAggregator — Phase R.4.

Every 3 hours: pulls the last 3h of tweets from the running Mirofish
simulation, asks Groq Llama-3.3-70b to condense them into structured
findings, and persists the result in three places:

  1. aggregated-kg Qdrant collection — Topic / Finding / Decision nodes
     with cross-edges (linked.tweets, linked.topic, linked.findings)
  2. Brain ContinuousThinkingEngine — one condensed thought per cycle
     so the user sees discourse summaries in the normal thought stream
  3. Markdown file at
     ~/.rowboat/knowledge/vibemind-discourse/YYYY-MM-DD/HH-HH.md
     (lives inside the Rowboat knowledge vault so it shows in the UI tree)

The tweets themselves are NOT pushed into the Brain thought stream
(that would flood it). Only the 3h-condensed summaries make it through.

Environment:
  DISCOURSE_AGGREGATE_INTERVAL_S      default 10800   (3 hours)
  DISCOURSE_AGGREGATE_INITIAL_DELAY   default 600     (10 min after boot)
  DISCOURSE_AGGREGATE_LOOKBACK_S      default 10800
  DISCOURSE_AGGREGATE_MAX_TWEETS      default 500
  DISCOURSE_AGGREGATE_ENABLED         default 1
  MIROFISH_URL                        default http://127.0.0.1:5101
  ROWBOAT_DISCOURSE_DIR               default ~/.rowboat/knowledge/vibemind-discourse
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


TICK_INTERVAL_S = float(os.environ.get("DISCOURSE_AGGREGATE_INTERVAL_S", "10800"))
INITIAL_DELAY_S = float(os.environ.get("DISCOURSE_AGGREGATE_INITIAL_DELAY", "600"))
LOOKBACK_S = float(os.environ.get("DISCOURSE_AGGREGATE_LOOKBACK_S", "10800"))
MAX_TWEETS = int(os.environ.get("DISCOURSE_AGGREGATE_MAX_TWEETS", "500"))
ENABLED = os.environ.get("DISCOURSE_AGGREGATE_ENABLED", "1").lower() in ("1", "true", "yes")

MIROFISH_URL = os.environ.get("MIROFISH_URL", "http://127.0.0.1:5101").rstrip("/")
ROWBOAT_DISCOURSE_DIR = Path(os.environ.get(
    "ROWBOAT_DISCOURSE_DIR",
    str(Path.home() / ".rowboat" / "knowledge" / "vibemind-discourse"),
))

# Where setup_mirofish_brain_sim.py persisted the running sim id
_BRAIN_DIR = Path(__file__).resolve().parent.parent
SIM_STATE_FILE = _BRAIN_DIR / "data" / "discourse_sim.json"


SYNTH_PROMPT = """\
You are summarising a multi-agent self-reflective discourse from the
last {hours}h. The agents are 26 VibeMind components reflecting on
shared knowledge graphs.

Below are {n} tweets/replies. Condense them into structured JSON:

{{
  "topics":    [{{"id": "t1", "title": "…", "summary": "1-2 sentences"}}, …],
  "findings":  [{{"id": "f1", "topic_id": "t1", "text": "what was noticed",
                  "evidence_tweet_ids": [int, …]}}, …],
  "decisions": [{{"id": "d1", "topic_id": "t1", "text": "what was proposed",
                  "evidence_tweet_ids": [int, …]}}, …]
}}

Rules:
  - 1-5 topics max (cluster the tweets first)
  - 0-3 findings per topic
  - 0-2 decisions per topic
  - language: match the dominant language of the tweets (German if
    German, else English)
  - text fields: terse, factual; no marketing fluff
  - Output ONLY the JSON object. No preamble, no fences.

TWEETS:
{tweets}
"""


class DiscourseAggregator:
    """3-hour Groq-driven condenser for Mirofish discourse."""

    def __init__(self, kg, dispatcher, cte=None) -> None:
        """
        Args:
            kg: QdrantKG instance — used to upsert topic/finding/decision
            dispatcher: SubagentDispatcher — for the groq_subagent call
            cte: ContinuousThinkingEngine (optional) — to add summary thought
        """
        self.kg = kg
        self.dispatcher = dispatcher
        self.cte = cte
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._sim_id: Optional[str] = None
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "tweets_processed": 0,
            "topics_created": 0,
            "findings_created": 0,
            "decisions_created": 0,
            "markdown_files_written": 0,
            "thoughts_emitted": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
            "last_summary_path": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[discourse-agg] disabled")
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="DiscourseAggregator",
        )
        self._worker.start()
        logger.info(
            f"[discourse-agg] started (every {TICK_INTERVAL_S}s, "
            f"lookback {LOOKBACK_S}s)"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)

    def _loop(self) -> None:
        self._stop.wait(INITIAL_DELAY_S)
        while not self._stop.is_set():
            try:
                self.tick_once()
                self.stats["ticks"] += 1
                self.stats["last_tick_ts"] = time.time()
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = f"tick: {type(e).__name__}: {e}"
                logger.warning(f"[discourse-agg] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Sim id load ──────────────────────────────────────────────────

    def _ensure_sim(self) -> bool:
        if self._sim_id:
            return True
        if not SIM_STATE_FILE.exists():
            self.stats["last_error"] = "no discourse_sim.json"
            return False
        try:
            d = json.loads(SIM_STATE_FILE.read_text(encoding="utf-8"))
            sid = d.get("simulation_id")
            if not sid:
                return False
            self._sim_id = sid
            return True
        except Exception as e:
            self.stats["last_error"] = f"sim state: {e}"
            return False

    # ── Single aggregation pass ──────────────────────────────────────

    def tick_once(self) -> Dict[str, Any]:
        if not self._ensure_sim():
            return {"ok": False, "reason": self.stats.get("last_error")}

        period_end = time.time()
        period_start = period_end - LOOKBACK_S

        tweets = self._fetch_tweets(period_start, period_end)
        self.stats["tweets_processed"] += len(tweets)
        if not tweets:
            return {"ok": False, "reason": "no tweets in window",
                    "period_start": period_start, "period_end": period_end}

        synth = self._synthesise(tweets)
        if not synth:
            return {"ok": False, "reason": "synth failed"}

        # Persist 3 outputs
        kg_summary = self._persist_kg(synth, tweets, period_start, period_end)
        md_path = self._write_markdown(synth, tweets, period_start, period_end)
        thought_text = self._emit_thought(synth, period_start, period_end)

        self.stats["topics_created"] += kg_summary.get("topics", 0)
        self.stats["findings_created"] += kg_summary.get("findings", 0)
        self.stats["decisions_created"] += kg_summary.get("decisions", 0)
        if md_path:
            self.stats["markdown_files_written"] += 1
            self.stats["last_summary_path"] = str(md_path)
        if thought_text:
            self.stats["thoughts_emitted"] += 1

        return {
            "ok": True,
            "tweets": len(tweets),
            "topics": kg_summary.get("topics", 0),
            "findings": kg_summary.get("findings", 0),
            "decisions": kg_summary.get("decisions", 0),
            "markdown": str(md_path) if md_path else None,
        }

    # ── Tweet fetch ──────────────────────────────────────────────────

    def _fetch_tweets(self, since_ts: float, until_ts: float) -> List[Dict[str, Any]]:
        """Fetch posts from Mirofish for the running simulation."""
        try:
            r = requests.get(
                f"{MIROFISH_URL}/api/simulation/{self._sim_id}/posts",
                params={"limit": MAX_TWEETS, "offset": 0, "platform": "twitter"},
                timeout=30,
            )
            if r.status_code >= 400:
                self.stats["last_error"] = f"posts HTTP {r.status_code}"
                return []
            d = r.json()
            posts = (d.get("data") or {}).get("posts") or []
        except Exception as e:
            self.stats["last_error"] = f"posts fetch: {e}"
            return []

        # Filter by created_at if available
        out = []
        for p in posts:
            ca = p.get("created_at") or p.get("timestamp")
            ts = self._parse_ts(ca)
            if ts is not None and (ts < since_ts or ts > until_ts):
                continue
            out.append(p)
        return out

    @staticmethod
    def _parse_ts(s: Any) -> Optional[float]:
        if not s:
            return None
        if isinstance(s, (int, float)):
            return float(s)
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    # ── Groq synthesis ───────────────────────────────────────────────

    def _synthesise(self, tweets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not self.dispatcher:
            self.stats["last_error"] = "no dispatcher"
            return None

        lines = []
        for t in tweets[:200]:  # keep prompt manageable
            tid = t.get("id") or t.get("post_id") or "?"
            agent = t.get("agent_name") or t.get("agent_id") or "?"
            content = (t.get("content") or t.get("text") or "").replace("\n", " ")[:240]
            lines.append(f"  [{tid}] @{agent}: {content}")
        block = "\n".join(lines)

        prompt = SYNTH_PROMPT.format(
            hours=int(LOOKBACK_S // 3600),
            n=len(tweets),
            tweets=block,
        )

        try:
            result = self.dispatcher.dispatch(
                "groq_subagent",
                prompt=prompt,
                max_tokens=1500,
                temperature=0.2,
                model=os.environ.get(
                    "DISCOURSE_AGG_MODEL",
                    "groq::llama-3.1-8b-instant",
                ),
            )
            if not result.get("ok"):
                self.stats["last_error"] = f"synth: {result.get('error', 'unknown')}"
                return None
            text = (result.get("text") or "").strip()
            # tolerate ```json fences
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```\s*$", "", text)
            data = json.loads(text)
            return {
                "topics":    data.get("topics") or [],
                "findings":  data.get("findings") or [],
                "decisions": data.get("decisions") or [],
            }
        except json.JSONDecodeError as e:
            self.stats["last_error"] = f"synth JSON parse: {e}"
            logger.debug(f"[discourse-agg] synth output not JSON: {text[:300]}")
            return None
        except Exception as e:
            self.stats["last_error"] = f"synth: {type(e).__name__}: {e}"
            return None

    # ── Persist 1: aggregated-kg ─────────────────────────────────────

    def _persist_kg(
        self,
        synth: Dict[str, Any],
        tweets: List[Dict[str, Any]],
        period_start: float,
        period_end: float,
    ) -> Dict[str, int]:
        from core.qdrant_kg import (
            COLLECTIONS, NT_TOPIC, NT_FINDING, NT_DECISION,
            _point_id, _empty_linked,
        )
        from qdrant_client.http import models as qm

        coll = COLLECTIONS["aggregated"]
        period_id = f"{int(period_start)}-{int(period_end)}"
        out = {"topics": 0, "findings": 0, "decisions": 0}

        # Build a mapping from tweet evidence-id → tweet content for payloads
        tw_by_id: Dict[str, str] = {}
        for t in tweets:
            tid = str(t.get("id") or t.get("post_id") or "")
            if tid:
                tw_by_id[tid] = (t.get("content") or t.get("text") or "")[:200]

        for topic in synth.get("topics", []):
            tid = topic.get("id") or f"t-{uuid.uuid4().hex[:8]}"
            ext_id = f"agg-topic-{period_id}-{tid}"
            try:
                self.kg._upsert_point(
                    external_id=ext_id,
                    node_type=NT_TOPIC,
                    text=f"{topic.get('title', '')}\n{topic.get('summary', '')}",
                    payload_extra={
                        "topic_id": tid,
                        "title": (topic.get("title") or "")[:200],
                        "summary": (topic.get("summary") or "")[:1000],
                        "period_start": int(period_start),
                        "period_end": int(period_end),
                        "source": "discourse_aggregator",
                    },
                )
                out["topics"] += 1
            except Exception as e:
                logger.debug(f"[discourse-agg] topic upsert failed: {e}")

        for kind, nt in (("findings", NT_FINDING), ("decisions", NT_DECISION)):
            for item in synth.get(kind, []):
                iid = item.get("id") or f"{kind[:1]}-{uuid.uuid4().hex[:8]}"
                ext_id = f"agg-{kind[:1]}-{period_id}-{iid}"
                evi = item.get("evidence_tweet_ids") or []
                evi_text = [tw_by_id.get(str(e), "") for e in evi if str(e) in tw_by_id]
                try:
                    self.kg._upsert_point(
                        external_id=ext_id,
                        node_type=nt,
                        text=item.get("text", ""),
                        payload_extra={
                            kind[:-1] + "_id": iid,
                            "topic_id": item.get("topic_id"),
                            "text": (item.get("text") or "")[:1000],
                            "evidence_tweet_ids": [str(x) for x in evi[:20]],
                            "evidence_preview": evi_text[:5],
                            "period_start": int(period_start),
                            "period_end": int(period_end),
                            "source": "discourse_aggregator",
                        },
                    )
                    out[kind] += 1
                except Exception as e:
                    logger.debug(f"[discourse-agg] {kind} upsert failed: {e}")

        return out

    # ── Persist 2: Markdown ──────────────────────────────────────────

    def _write_markdown(
        self,
        synth: Dict[str, Any],
        tweets: List[Dict[str, Any]],
        period_start: float,
        period_end: float,
    ) -> Optional[Path]:
        try:
            d_start = datetime.fromtimestamp(period_start)
            d_end = datetime.fromtimestamp(period_end)
            day_dir = ROWBOAT_DISCOURSE_DIR / d_end.strftime("%Y-%m-%d")
            day_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{d_start.strftime('%H')}-{d_end.strftime('%H')}.md"
            path = day_dir / fname

            lines = [
                f"# VibeMind Self-Discourse — {d_start.strftime('%Y-%m-%d %H:%M')} → {d_end.strftime('%H:%M')}",
                "",
                f"**Tweets aggregated:** {len(tweets)}  ",
                f"**Topics:** {len(synth.get('topics') or [])}  ",
                f"**Findings:** {len(synth.get('findings') or [])}  ",
                f"**Decisions:** {len(synth.get('decisions') or [])}",
                "",
            ]
            for topic in synth.get("topics", []):
                lines.append(f"## Topic: {topic.get('title', '(untitled)')}")
                lines.append("")
                lines.append(topic.get("summary", "") or "_(no summary)_")
                lines.append("")
                tid = topic.get("id")
                related_findings = [f for f in (synth.get("findings") or []) if f.get("topic_id") == tid]
                if related_findings:
                    lines.append("### Findings")
                    for f in related_findings:
                        lines.append(f"- {f.get('text', '')}")
                    lines.append("")
                related_decisions = [d for d in (synth.get("decisions") or []) if d.get("topic_id") == tid]
                if related_decisions:
                    lines.append("### Decisions")
                    for d in related_decisions:
                        lines.append(f"> {d.get('text', '')}")
                    lines.append("")

            path.write_text("\n".join(lines), encoding="utf-8")
            return path
        except Exception as e:
            self.stats["last_error"] = f"markdown: {e}"
            return None

    # ── Persist 3: Brain ContinuousThinkingEngine thought ────────────

    def _emit_thought(
        self,
        synth: Dict[str, Any],
        period_start: float,
        period_end: float,
    ) -> Optional[str]:
        if self.cte is None:
            return None
        topics = synth.get("topics") or []
        if not topics:
            return None
        topic_titles = ", ".join(t.get("title", "?") for t in topics[:5])
        n_findings = len(synth.get("findings") or [])
        n_decisions = len(synth.get("decisions") or [])
        d_start = datetime.fromtimestamp(period_start).strftime("%H:%M")
        d_end = datetime.fromtimestamp(period_end).strftime("%H:%M")
        text = (
            f"[discourse {d_start}-{d_end}] {len(topics)} themes "
            f"({n_findings} findings, {n_decisions} decisions): "
            f"{topic_titles[:300]}"
        )
        try:
            # CTE expects different APIs depending on version; try common ones
            if hasattr(self.cte, "add_thought"):
                self.cte.add_thought(content=text, source="discourse_aggregator")
            elif hasattr(self.cte, "record_thought"):
                self.cte.record_thought(text, source="discourse_aggregator")
            elif hasattr(self.cte, "_thought_buffer") and hasattr(self.cte._thought_buffer, "add"):
                # Best-effort: synthesise minimal MicroThought-like dict
                self.cte._thought_buffer.add(text)
            else:
                logger.debug("[discourse-agg] CTE has no known add API")
                return None
            return text
        except Exception as e:
            self.stats["last_error"] = f"cte: {e}"
            return None

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "enabled": ENABLED,
            "interval_s": TICK_INTERVAL_S,
            "lookback_s": LOOKBACK_S,
            "running": bool(self._worker and self._worker.is_alive()),
            **self.stats,
        }
