"""Phase 8.B — Decision Graph (Neo4j-backed).

Persistent graph of Brain's decision history that the Cytoscape frontend
visualises in Mirofish-style. Reuses the existing Neo4j instance on
bolt://127.0.0.1:7688 (Mirofish's docker-compose).

Schema:

  (:Cluster {id, label, activation, fire_count, last_fired_ts, dominant_topic})
  (:Thought {id, content, category, ts})
  (:Plan {id, intent, ok, hop_count, reward_score, ts})
  (:Hop {id, plan_id, step_id, capability, target, ok, elapsed_s})
  (:Dispatch {id, ts, capability, target, ok, summary})

Relationships:
  (Cluster)-[:CO_ACTIVATED {weight, ts}]->(Cluster)
  (Cluster)-[:CONTAINS]->(Thought)
  (Cluster)-[:FIRED]->(Dispatch)
  (Plan)-[:HAS_HOP]->(Hop)
  (Plan)-[:GENERATED]->(Thought)
  (Hop)-[:HOP_OF_TARGET]->(Dispatch)            (when capability == OpenFang dispatch)
  (Dispatch)-[:PRODUCED]->(Thought)             (loop-back result thought)

Public API:
  upsert_cluster(state)
  upsert_thought(thought_id, content, category, cluster_id)
  upsert_plan(plan_id, intent, ok, hop_count, reward_score)
  upsert_hop(plan_id, step_id, capability, target, ok, elapsed_s)
  upsert_dispatch(dispatch_id, cluster_id, capability, target, ok, summary)
  upsert_co_activation(a_id, b_id, weight)
  query_subgraph(limit=200) -> {nodes, edges}    # for the UI
  prune(older_than_s=86400)
  stats() -> counts per label
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("DECISION_GRAPH_NEO4J_URI", "bolt://127.0.0.1:7688")
NEO4J_USER = os.environ.get("DECISION_GRAPH_NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("DECISION_GRAPH_NEO4J_PASS", "mirofish")
ENABLED = os.environ.get("DECISION_GRAPH_ENABLED", "1") not in ("0", "false", "False")
NODE_TTL_S = float(os.environ.get("DECISION_GRAPH_TTL_S", "604800"))  # 7 days


class DecisionGraph:
    """Neo4j-backed persistent decision history. Lazy-connect, fail-soft."""

    def __init__(self) -> None:
        self._driver = None
        self._connected = False
        self._connect_error: Optional[str] = None
        # In-memory mirror — used when Neo4j is offline so the UI still
        # sees decisions. Same shape as what query_subgraph would return.
        self._mem_clusters: Dict[str, Dict[str, Any]] = {}
        self._mem_plans: Dict[str, Dict[str, Any]] = {}
        self._mem_hops: Dict[str, Dict[str, Any]] = {}      # hop_id -> hop
        self._mem_dispatches: Dict[str, Dict[str, Any]] = {}
        self._mem_tool_calls: Dict[str, Dict[str, Any]] = {}
        self._mem_co_pairs: Dict[tuple, float] = {}          # (a,b) -> weight
        self._mem_fired: List[Dict[str, Any]] = []           # cluster→dispatch edges
        self._mem_used_tool: List[Dict[str, Any]] = []       # hop→toolcall edges
        self.stats_counters: Dict[str, int] = {
            "writes_clusters": 0,
            "writes_thoughts": 0,
            "writes_plans": 0,
            "writes_hops": 0,
            "writes_dispatches": 0,
            "writes_co_activations": 0,
            "writes_tool_calls": 0,
            "errors": 0,
        }
        self._connect()

    def _connect(self) -> None:
        if not ENABLED:
            return
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS),
            )
            with self._driver.session() as s:
                s.run("RETURN 1").single()
            self._connected = True
            logger.info(f"[decision-graph] connected to {NEO4J_URI}")
            self._ensure_constraints()
        except Exception as e:
            self._connect_error = f"{type(e).__name__}: {e}"
            self._connected = False
            logger.warning(f"[decision-graph] connect failed: {e}")

    def _ensure_constraints(self) -> None:
        """Create unique-constraints once on init. Idempotent."""
        if not self._connected:
            return
        try:
            with self._driver.session() as s:
                for label, key in [
                    ("Cluster", "id"),
                    ("Thought", "id"),
                    ("Plan", "id"),
                    ("Hop", "id"),
                    ("Dispatch", "id"),
                    ("ToolCall", "id"),
                ]:
                    s.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                    )
        except Exception as e:
            logger.debug(f"[decision-graph] constraint setup failed: {e}")

    def is_connected(self) -> bool:
        # ALWAYS report True — we use in-memory mirror when Neo4j is down,
        # so callers (engines, endpoints) keep writing/reading. Real Neo4j
        # state is observable via stats().neo4j_connected.
        return True

    def _neo4j_alive(self) -> bool:
        return self._connected

    # ── Upserts ────────────────────────────────────────────────────────

    def upsert_cluster(self, cluster: Dict[str, Any]) -> None:
        # In-memory mirror first (always)
        cid = cluster.get("cluster_id")
        if cid:
            self._mem_clusters[cid] = {
                "id": cid,
                "label": cluster.get("label") or cid,
                "activation": float(cluster.get("activation") or 0.0),
                "topic": cluster.get("dominant_topic") or "",
                "member_count": int(cluster.get("member_count") or 0),
                "fire_count": int(cluster.get("fire_count") or 0),
                "last_fired_ts": float(cluster.get("last_dispatch_ts") or 0.0),
            }
            self.stats_counters["writes_clusters"] += 1
        if not self._connected:
            return
        try:
            with self._driver.session() as s:
                s.run(
                    """
                    MERGE (c:Cluster {id: $id})
                    SET c.label = $label,
                        c.activation = $activation,
                        c.dominant_topic = $dominant_topic,
                        c.member_count = $member_count,
                        c.fire_count = $fire_count,
                        c.last_seen_ts = $last_seen_ts,
                        c.last_fired_ts = $last_fired_ts,
                        c.center_x = $cx,
                        c.center_y = $cy
                    """,
                    id=cluster.get("cluster_id"),
                    label=cluster.get("label") or cluster.get("cluster_id"),
                    activation=float(cluster.get("activation") or 0.0),
                    dominant_topic=cluster.get("dominant_topic") or "",
                    member_count=int(cluster.get("member_count") or 0),
                    fire_count=int(cluster.get("fire_count") or 0),
                    last_seen_ts=float(cluster.get("last_seen_ts") or 0.0),
                    last_fired_ts=float(cluster.get("last_dispatch_ts") or 0.0),
                    cx=float(cluster.get("center_x") or 0.0),
                    cy=float(cluster.get("center_y") or 0.0),
                )
        except Exception as e:
            self.stats_counters["errors"] += 1
            logger.debug(f"[decision-graph] upsert_cluster failed: {e}")

    def upsert_thought(
        self,
        thought_id: str,
        content: str,
        category: str = "",
        cluster_id: Optional[str] = None,
    ) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as s:
                s.run(
                    """
                    MERGE (t:Thought {id: $id})
                    SET t.content = $content,
                        t.category = $category,
                        t.ts = coalesce(t.ts, $ts)
                    """,
                    id=thought_id,
                    content=(content or "")[:300],
                    category=category,
                    ts=time.time(),
                )
                if cluster_id:
                    s.run(
                        """
                        MERGE (c:Cluster {id: $cid})
                        WITH c
                        MATCH (t:Thought {id: $tid})
                        MERGE (c)-[:CONTAINS]->(t)
                        """,
                        cid=cluster_id, tid=thought_id,
                    )
            self.stats_counters["writes_thoughts"] += 1
        except Exception as e:
            self.stats_counters["errors"] += 1
            logger.debug(f"[decision-graph] upsert_thought failed: {e}")

    def upsert_plan(
        self,
        plan_id: str,
        intent: str,
        ok: bool = True,
        hop_count: int = 0,
        reward_score: float = 0.0,
    ) -> None:
        # In-memory mirror
        if plan_id:
            self._mem_plans[plan_id] = {
                "id": plan_id,
                "intent": (intent or "")[:300],
                "ok": bool(ok),
                "hop_count": int(hop_count),
                "reward_score": float(reward_score),
                "ts": time.time(),
            }
            self.stats_counters["writes_plans"] += 1
        if not self._connected:
            return
        try:
            with self._driver.session() as s:
                s.run(
                    """
                    MERGE (p:Plan {id: $id})
                    SET p.intent = $intent,
                        p.ok = $ok,
                        p.hop_count = $hop_count,
                        p.reward_score = $reward,
                        p.ts = coalesce(p.ts, $ts)
                    """,
                    id=plan_id,
                    intent=(intent or "")[:300],
                    ok=bool(ok),
                    hop_count=int(hop_count),
                    reward=float(reward_score),
                    ts=time.time(),
                )
        except Exception as e:
            self.stats_counters["errors"] += 1
            logger.debug(f"[decision-graph] upsert_plan failed: {e}")

    def upsert_hop(
        self,
        plan_id: str,
        step_id: str,
        capability: str = "",
        target: str = "",
        ok: bool = True,
        elapsed_s: float = 0.0,
    ) -> None:
        hop_node_id = f"{plan_id}:{step_id}"
        # Mem mirror
        self._mem_hops[hop_node_id] = {
            "id": hop_node_id,
            "step_id": step_id,
            "plan_id": plan_id,
            "capability": capability or "",
            "target": target or "",
            "ok": bool(ok),
            "elapsed_s": float(elapsed_s),
        }
        self.stats_counters["writes_hops"] += 1
        if not self._connected:
            return
        try:
            with self._driver.session() as s:
                s.run(
                    """
                    MERGE (h:Hop {id: $id})
                    SET h.step_id = $step,
                        h.plan_id = $plan,
                        h.capability = $cap,
                        h.target = $target,
                        h.ok = $ok,
                        h.elapsed_s = $elapsed,
                        h.ts = coalesce(h.ts, $ts)
                    WITH h
                    MERGE (p:Plan {id: $plan})
                    MERGE (p)-[:HAS_HOP]->(h)
                    """,
                    id=hop_node_id, step=step_id, plan=plan_id,
                    cap=capability, target=target,
                    ok=bool(ok), elapsed=float(elapsed_s),
                    ts=time.time(),
                )
        except Exception as e:
            self.stats_counters["errors"] += 1
            logger.debug(f"[decision-graph] upsert_hop failed: {e}")

    def upsert_tool_calls(
        self,
        hop_node_id: str,
        tool_calls: List[Dict[str, Any]],
    ) -> int:
        """Phase 9.0.2 — link MCP-tool-call traces to a Hop. Each entry is a
        ToolCall node; (Hop)-[:USED_TOOL {seq}]->(ToolCall).

        Tool-call shape (from OpenFangExecutor._call_streaming):
            {seq, tool, input, result, ts_start, ts_end, elapsed_ms,
             approval_status?: 'none'|'requested'|'approved'|'denied'}
        """
        if not tool_calls:
            return 0
        import json as _json
        written = 0
        # In-memory mirror first (always, even if Neo4j down)
        for tc in tool_calls:
            if not tc.get("tool"):
                continue
            seq = int(tc.get("seq") or 0)
            tool = str(tc.get("tool") or "unknown")
            tc_id = f"{hop_node_id}::{seq}::{tool}"
            self._mem_tool_calls[tc_id] = {
                "id": tc_id,
                "tool": tool,
                "seq": seq,
                "elapsed_ms": float(tc.get("elapsed_ms") or 0.0),
                "tool_kind": self._classify_tool(tool),
                "mcp_server": self._guess_mcp_server(tool),
                "input_json": _json.dumps(tc.get("input"))[:2000] if tc.get("input") is not None else "",
                "result_json": _json.dumps(tc.get("result"))[:2000] if tc.get("result") is not None else "",
                "approval_status": str(tc.get("approval_status") or "none"),
                "risk_level": str(tc.get("risk_level") or "none"),
                "incomplete": bool(tc.get("incomplete") or False),
            }
            self._mem_used_tool.append({
                "source": hop_node_id, "target": tc_id, "seq": seq,
            })
            written += 1
        self.stats_counters["writes_tool_calls"] += written
        if not self._connected:
            return written
        try:
            with self._driver.session() as s:
                for tc in tool_calls:
                    if not tc.get("tool"):
                        continue
                    seq = int(tc.get("seq") or 0)
                    tool = str(tc.get("tool") or "unknown")
                    # Stable id so re-syncs don't duplicate
                    tc_id = f"{hop_node_id}::{seq}::{tool}"
                    s.run(
                        """
                        MERGE (tc:ToolCall {id: $id})
                        SET tc.tool = $tool,
                            tc.seq = $seq,
                            tc.input_json = $input_json,
                            tc.result_json = $result_json,
                            tc.ts_start = $ts_start,
                            tc.ts_end = $ts_end,
                            tc.elapsed_ms = $elapsed_ms,
                            tc.incomplete = $incomplete,
                            tc.approval_status = coalesce(tc.approval_status, $approval),
                            tc.risk_level = $risk_level,
                            tc.mcp_server = $mcp_server,
                            tc.tool_kind = $tool_kind
                        WITH tc
                        MATCH (h:Hop {id: $hop_id})
                        MERGE (h)-[r:USED_TOOL]->(tc)
                        SET r.seq = $seq
                        """,
                        id=tc_id,
                        tool=tool,
                        seq=seq,
                        input_json=_json.dumps(tc.get("input"))[:2000] if tc.get("input") is not None else "",
                        result_json=_json.dumps(tc.get("result"))[:2000] if tc.get("result") is not None else "",
                        ts_start=float(tc.get("ts_start") or 0.0),
                        ts_end=float(tc.get("ts_end") or 0.0),
                        elapsed_ms=float(tc.get("elapsed_ms") or 0.0),
                        incomplete=bool(tc.get("incomplete") or False),
                        approval=str(tc.get("approval_status") or "none"),
                        risk_level=str(tc.get("risk_level") or "none"),
                        mcp_server=self._guess_mcp_server(tool),
                        tool_kind=self._classify_tool(tool),
                        hop_id=hop_node_id,
                    )
        except Exception as e:
            self.stats_counters["errors"] += 1
            logger.debug(f"[decision-graph] upsert_tool_calls failed: {e}")
        return written

    @staticmethod
    def _guess_mcp_server(tool_name: str) -> str:
        """Heuristic: map tool name prefix → MCP server. Not authoritative
        (the actual MCP routing is OpenFang-side) but good enough for UI
        grouping."""
        t = (tool_name or "").lower()
        prefix_map = [
            ("handoff_", "desktop-automation"),
            ("clawdbot_", "desktop-automation"),
            ("vision_", "desktop-automation"),
            ("claude_cli_", "desktop-automation"),
            ("n8n_", "n8n"),
            ("vibemind_", "vibemind"),
            ("fungus_", "fungus-search"),
            ("brain_", "brain-core"),
        ]
        for p, srv in prefix_map:
            if t.startswith(p):
                return srv
        return "unknown"

    @staticmethod
    def _classify_tool(tool_name: str) -> str:
        """Tag tool by intent class for color-coding in the UI."""
        t = (tool_name or "").lower()
        if any(k in t for k in ("file_write", "doc_apply", "file_create", "edit", "write")):
            return "write"
        if any(k in t for k in ("shell", "exec", "process_kill", "execute")):
            return "shell"
        if any(k in t for k in ("browser", "fetch", "scrape", "navigate", "search")):
            return "web"
        if any(k in t for k in ("read", "scan", "inspect", "list", "view")):
            return "read"
        if any(k in t for k in ("email", "gmail", "send_message")):
            return "comms"
        if any(k in t for k in ("calendar", "event")):
            return "schedule"
        return "other"

    def upsert_dispatch(
        self,
        cluster_id: str,
        capability: str,
        target: str,
        ok: bool,
        summary: str = "",
    ) -> str:
        """Create a Dispatch node + FIRED edge from cluster. Returns the
        dispatch_id (the caller can use it to link a result thought)."""
        dispatch_id = f"disp_{uuid.uuid4().hex[:10]}"
        # Mem mirror first
        self._mem_dispatches[dispatch_id] = {
            "id": dispatch_id,
            "ts": time.time(),
            "capability": capability or "",
            "target": target or "",
            "ok": bool(ok),
            "summary": (summary or "")[:300],
        }
        if cluster_id:
            self._mem_fired.append({
                "source": cluster_id, "target": dispatch_id, "ts": time.time(),
            })
        self.stats_counters["writes_dispatches"] += 1
        if not self._connected:
            return dispatch_id
        try:
            with self._driver.session() as s:
                s.run(
                    """
                    MERGE (d:Dispatch {id: $id})
                    SET d.ts = $ts,
                        d.capability = $cap,
                        d.target = $target,
                        d.ok = $ok,
                        d.summary = $summary
                    WITH d
                    MERGE (c:Cluster {id: $cid})
                    MERGE (c)-[r:FIRED]->(d)
                    SET r.ts = $ts
                    """,
                    id=dispatch_id, ts=time.time(),
                    cap=capability, target=target,
                    ok=bool(ok), summary=(summary or "")[:300],
                    cid=cluster_id,
                )
            return dispatch_id
        except Exception as e:
            self.stats_counters["errors"] += 1
            logger.debug(f"[decision-graph] upsert_dispatch failed: {e}")
            return dispatch_id  # mem mirror still has it

    def upsert_co_activation(self, a_id: str, b_id: str, weight: float) -> None:
        # Mem mirror
        if a_id and b_id:
            key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            self._mem_co_pairs[key] = float(weight)
            self.stats_counters["writes_co_activations"] += 1
        if not self._connected:
            return
        try:
            with self._driver.session() as s:
                s.run(
                    """
                    MERGE (a:Cluster {id: $a})
                    MERGE (b:Cluster {id: $b})
                    MERGE (a)-[r:CO_ACTIVATED]->(b)
                    SET r.weight = $w, r.ts = $ts
                    """,
                    a=a_id, b=b_id, w=float(weight), ts=time.time(),
                )
        except Exception as e:
            self.stats_counters["errors"] += 1
            logger.debug(f"[decision-graph] upsert_co_activation failed: {e}")

    # ── Query ──────────────────────────────────────────────────────────

    def _query_subgraph_mem(self, limit: int, min_activation: float) -> Dict[str, Any]:
        """Phase 9 — in-memory subgraph for when Neo4j is offline.
        Same Cytoscape shape as query_subgraph()."""
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        # Active clusters
        active_clusters = [
            c for c in self._mem_clusters.values()
            if c.get("activation", 0) >= min_activation
        ]
        active_clusters.sort(key=lambda c: -c.get("activation", 0))
        for c in active_clusters[:limit]:
            nodes.append({
                "data": {
                    "id": c["id"],
                    "label": c.get("label") or c["id"],
                    "type": "cluster",
                    "activation": c.get("activation", 0.0),
                    "topic": c.get("topic", ""),
                    "size": int(c.get("member_count") or 0),
                    "fire_count": int(c.get("fire_count") or 0),
                }
            })
        for d in list(self._mem_dispatches.values())[-50:]:
            nodes.append({
                "data": {
                    "id": d["id"],
                    "label": (d.get("capability") or "?")[:24],
                    "type": "dispatch",
                    "ok": bool(d.get("ok")),
                    "capability": d.get("capability") or "",
                    "target": d.get("target") or "",
                    "summary": (d.get("summary") or "")[:120],
                    "ts": d.get("ts") or 0,
                }
            })
        for p in list(self._mem_plans.values())[-30:]:
            nodes.append({
                "data": {
                    "id": p["id"],
                    "label": (p.get("intent") or p["id"])[:36],
                    "type": "plan",
                    "ok": bool(p.get("ok")),
                    "hop_count": int(p.get("hop_count") or 0),
                    "reward_score": float(p.get("reward_score") or 0.0),
                    "ts": p.get("ts") or 0,
                }
            })
        for h in list(self._mem_hops.values())[-200:]:
            nodes.append({
                "data": {
                    "id": h["id"],
                    "label": (h.get("capability") or h.get("step_id") or "?")[:18],
                    "type": "hop",
                    "ok": bool(h.get("ok")),
                    "capability": h.get("capability") or "",
                    "target": h.get("target") or "",
                    "elapsed_s": float(h.get("elapsed_s") or 0.0),
                }
            })
        for tc in list(self._mem_tool_calls.values())[-300:]:
            nodes.append({
                "data": {
                    "id": tc["id"],
                    "label": (tc.get("tool") or "?")[:14],
                    "type": "toolcall",
                    "tool": tc.get("tool") or "",
                    "kind": tc.get("tool_kind") or "other",
                    "mcp_server": tc.get("mcp_server") or "",
                    "elapsed_ms": float(tc.get("elapsed_ms") or 0.0),
                    "input_preview": (tc.get("input_json") or "")[:160],
                    "result_preview": (tc.get("result_json") or "")[:160],
                    "approval_status": tc.get("approval_status") or "none",
                    "risk_level": tc.get("risk_level") or "none",
                    "incomplete": bool(tc.get("incomplete") or False),
                }
            })
        # Edges
        for f in self._mem_fired[-100:]:
            edges.append({
                "data": {
                    "id": f"fired_{f['source']}_{f['target']}",
                    "source": f["source"], "target": f["target"],
                    "type": "fired",
                }
            })
        for (a, b), w in list(self._mem_co_pairs.items())[:200]:
            if w < 0.1:
                continue
            edges.append({
                "data": {
                    "id": f"coact_{a}_{b}",
                    "source": a, "target": b,
                    "type": "co_activated",
                    "weight": float(w),
                }
            })
        for h in self._mem_hops.values():
            edges.append({
                "data": {
                    "id": f"hashop_{h['plan_id']}_{h['id']}",
                    "source": h["plan_id"], "target": h["id"],
                    "type": "has_hop",
                }
            })
        for ut in self._mem_used_tool[-300:]:
            edges.append({
                "data": {
                    "id": f"usedtool_{ut['source']}_{ut['target']}",
                    "source": ut["source"], "target": ut["target"],
                    "type": "used_tool",
                    "seq": int(ut.get("seq") or 0),
                }
            })
        return {
            "connected": True,
            "neo4j_connected": False,  # Hint that this is mem-only
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "clusters": len(active_clusters),
                "dispatches": len(self._mem_dispatches),
                "plans": len(self._mem_plans),
                "hops": len(self._mem_hops),
                "tool_calls": len(self._mem_tool_calls),
            },
        }

    def query_subgraph(
        self,
        limit: int = 200,
        min_activation: float = 0.05,
    ) -> Dict[str, Any]:
        """Return the active subgraph for visualisation. Filters out cold
        clusters + ancient nodes so the UI stays readable.

        Phase 9 fix — when Neo4j is offline, falls back to in-memory
        mirror so the UI still sees decisions that were made."""
        if not self._connected:
            return self._query_subgraph_mem(limit, min_activation)

        try:
            with self._driver.session() as s:
                # Active clusters
                clusters = s.run(
                    """
                    MATCH (c:Cluster)
                    WHERE c.activation >= $min_act
                    RETURN c.id AS id, c.label AS label,
                           c.activation AS activation,
                           c.dominant_topic AS topic,
                           c.member_count AS member_count,
                           c.fire_count AS fire_count,
                           c.last_fired_ts AS last_fired_ts
                    ORDER BY c.activation DESC LIMIT $limit
                    """,
                    min_act=float(min_activation), limit=int(limit),
                ).data()

                # Recent dispatches (last 24h)
                cutoff = time.time() - 86400
                dispatches = s.run(
                    """
                    MATCH (d:Dispatch)
                    WHERE d.ts >= $cutoff
                    RETURN d.id AS id, d.capability AS capability,
                           d.target AS target, d.ok AS ok,
                           d.summary AS summary, d.ts AS ts
                    ORDER BY d.ts DESC LIMIT 50
                    """,
                    cutoff=float(cutoff),
                ).data()

                # Recent plans (last 24h)
                plans = s.run(
                    """
                    MATCH (p:Plan)
                    WHERE p.ts >= $cutoff
                    RETURN p.id AS id, p.intent AS intent,
                           p.ok AS ok, p.hop_count AS hop_count,
                           p.reward_score AS reward_score, p.ts AS ts
                    ORDER BY p.ts DESC LIMIT 30
                    """,
                    cutoff=float(cutoff),
                ).data()

                # Recent hops belonging to those plans
                hops = s.run(
                    """
                    MATCH (p:Plan)-[:HAS_HOP]->(h:Hop)
                    WHERE p.ts >= $cutoff
                    RETURN h.id AS id, h.step_id AS step_id,
                           h.plan_id AS plan_id, h.capability AS capability,
                           h.target AS target, h.ok AS ok,
                           h.elapsed_s AS elapsed_s
                    LIMIT 200
                    """,
                    cutoff=float(cutoff),
                ).data()

                # Phase 9.0.2 — ToolCalls of recent hops
                tool_calls = s.run(
                    """
                    MATCH (p:Plan)-[:HAS_HOP]->(h:Hop)-[:USED_TOOL]->(tc:ToolCall)
                    WHERE p.ts >= $cutoff
                    RETURN tc.id AS id, tc.tool AS tool, tc.seq AS seq,
                           tc.elapsed_ms AS elapsed_ms,
                           tc.tool_kind AS kind,
                           tc.mcp_server AS mcp_server,
                           tc.input_json AS input_json,
                           tc.result_json AS result_json,
                           tc.approval_status AS approval_status,
                           tc.risk_level AS risk_level,
                           tc.incomplete AS incomplete
                    LIMIT 300
                    """,
                    cutoff=float(cutoff),
                ).data()

                # Edges
                fired = s.run(
                    """
                    MATCH (c:Cluster)-[r:FIRED]->(d:Dispatch)
                    WHERE r.ts >= $cutoff
                    RETURN c.id AS source, d.id AS target, r.ts AS ts
                    """, cutoff=float(cutoff),
                ).data()
                co_acts = s.run(
                    """
                    MATCH (a:Cluster)-[r:CO_ACTIVATED]->(b:Cluster)
                    WHERE r.weight >= 0.1
                    RETURN a.id AS source, b.id AS target,
                           r.weight AS weight
                    """,
                ).data()
                has_hop = s.run(
                    """
                    MATCH (p:Plan)-[:HAS_HOP]->(h:Hop)
                    WHERE p.ts >= $cutoff
                    RETURN p.id AS source, h.id AS target
                    LIMIT 200
                    """, cutoff=float(cutoff),
                ).data()
                used_tool = s.run(
                    """
                    MATCH (p:Plan)-[:HAS_HOP]->(h:Hop)-[r:USED_TOOL]->(tc:ToolCall)
                    WHERE p.ts >= $cutoff
                    RETURN h.id AS source, tc.id AS target, r.seq AS seq
                    LIMIT 300
                    """, cutoff=float(cutoff),
                ).data()

            # Cytoscape format
            nodes: List[Dict[str, Any]] = []
            for c in clusters:
                nodes.append({
                    "data": {
                        "id": c["id"],
                        "label": c.get("label") or c["id"],
                        "type": "cluster",
                        "activation": c.get("activation", 0.0),
                        "topic": c.get("topic") or "",
                        "size": int(c.get("member_count") or 0),
                        "fire_count": int(c.get("fire_count") or 0),
                    }
                })
            for d in dispatches:
                nodes.append({
                    "data": {
                        "id": d["id"],
                        "label": (d.get("capability") or "?")[:24],
                        "type": "dispatch",
                        "ok": bool(d.get("ok")),
                        "capability": d.get("capability") or "",
                        "target": d.get("target") or "",
                        "summary": (d.get("summary") or "")[:120],
                        "ts": d.get("ts") or 0,
                    }
                })
            for p in plans:
                nodes.append({
                    "data": {
                        "id": p["id"],
                        "label": (p.get("intent") or p["id"])[:36],
                        "type": "plan",
                        "ok": bool(p.get("ok")),
                        "hop_count": int(p.get("hop_count") or 0),
                        "reward_score": float(p.get("reward_score") or 0.0),
                        "ts": p.get("ts") or 0,
                    }
                })
            for h in hops:
                nodes.append({
                    "data": {
                        "id": h["id"],
                        "label": (h.get("capability") or h.get("step_id") or "?")[:18],
                        "type": "hop",
                        "ok": bool(h.get("ok")),
                        "capability": h.get("capability") or "",
                        "target": h.get("target") or "",
                        "elapsed_s": float(h.get("elapsed_s") or 0.0),
                    }
                })
            for tc in tool_calls:
                nodes.append({
                    "data": {
                        "id": tc["id"],
                        "label": (tc.get("tool") or "?")[:14],
                        "type": "toolcall",
                        "tool": tc.get("tool") or "",
                        "kind": tc.get("kind") or "other",
                        "mcp_server": tc.get("mcp_server") or "",
                        "elapsed_ms": float(tc.get("elapsed_ms") or 0.0),
                        "input_preview": (tc.get("input_json") or "")[:160],
                        "result_preview": (tc.get("result_json") or "")[:160],
                        "approval_status": tc.get("approval_status") or "none",
                        "risk_level": tc.get("risk_level") or "none",
                        "incomplete": bool(tc.get("incomplete") or False),
                    }
                })

            edges: List[Dict[str, Any]] = []
            for f in fired:
                edges.append({
                    "data": {
                        "id": f"fired_{f['source']}_{f['target']}",
                        "source": f["source"], "target": f["target"],
                        "type": "fired",
                    }
                })
            for ca in co_acts:
                edges.append({
                    "data": {
                        "id": f"coact_{ca['source']}_{ca['target']}",
                        "source": ca["source"], "target": ca["target"],
                        "type": "co_activated",
                        "weight": float(ca.get("weight") or 0.0),
                    }
                })
            for hh in has_hop:
                edges.append({
                    "data": {
                        "id": f"hashop_{hh['source']}_{hh['target']}",
                        "source": hh["source"], "target": hh["target"],
                        "type": "has_hop",
                    }
                })
            for ut in used_tool:
                edges.append({
                    "data": {
                        "id": f"usedtool_{ut['source']}_{ut['target']}",
                        "source": ut["source"], "target": ut["target"],
                        "type": "used_tool",
                        "seq": int(ut.get("seq") or 0),
                    }
                })

            return {
                "connected": True,
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "clusters": len(clusters),
                    "dispatches": len(dispatches),
                    "plans": len(plans),
                    "hops": len(hops),
                },
            }
        except Exception as e:
            logger.warning(f"[decision-graph] query_subgraph failed: {e}")
            return {"connected": True, "nodes": [], "edges": [], "error": str(e)}

    def stats(self) -> Dict[str, Any]:
        out = {
            "connected": self._connected,
            "uri": NEO4J_URI,
            "connect_error": self._connect_error,
            **self.stats_counters,
        }
        if not self._connected:
            return out
        try:
            with self._driver.session() as s:
                rec = s.run(
                    """
                    OPTIONAL MATCH (c:Cluster) WITH count(c) AS clusters
                    OPTIONAL MATCH (t:Thought) WITH clusters, count(t) AS thoughts
                    OPTIONAL MATCH (p:Plan) WITH clusters, thoughts, count(p) AS plans
                    OPTIONAL MATCH (h:Hop) WITH clusters, thoughts, plans, count(h) AS hops
                    OPTIONAL MATCH (d:Dispatch) WITH clusters, thoughts, plans, hops, count(d) AS dispatches
                    RETURN clusters, thoughts, plans, hops, dispatches
                    """
                ).single()
                if rec:
                    out["counts"] = {
                        "clusters": rec["clusters"],
                        "thoughts": rec["thoughts"],
                        "plans": rec["plans"],
                        "hops": rec["hops"],
                        "dispatches": rec["dispatches"],
                    }
        except Exception as e:
            out["count_error"] = str(e)
        return out

    def prune(self, older_than_s: float = NODE_TTL_S) -> Dict[str, int]:
        """Drop ancient nodes so the graph doesn't grow forever."""
        if not self._connected:
            return {"pruned": 0}
        cutoff = time.time() - older_than_s
        pruned = 0
        try:
            with self._driver.session() as s:
                for label in ("Dispatch", "Plan", "Hop", "Thought"):
                    rec = s.run(
                        f"MATCH (n:{label}) WHERE n.ts < $cutoff "
                        f"WITH n LIMIT 500 DETACH DELETE n RETURN count(n) AS n",
                        cutoff=float(cutoff),
                    ).single()
                    if rec:
                        pruned += int(rec["n"])
        except Exception as e:
            logger.debug(f"[decision-graph] prune failed: {e}")
        return {"pruned": pruned}

    def close(self) -> None:
        try:
            if self._driver:
                self._driver.close()
        except Exception:
            pass
