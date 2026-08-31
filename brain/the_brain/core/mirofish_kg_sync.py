"""
MirofishKGSync — Phase R.6.

Read-only mirror of Mirofish's Neo4j knowledge graph into Brain's Qdrant
``mirofish-kg`` collection. Brain can then query Mirofish entities with
the same semantic search machinery as its own thoughts/concepts/ideas,
and join them via cross-collection edges (``linked.mirofish``).

Connects to Neo4j on bolt://127.0.0.1:7688 (port 7688 to avoid clash
with other Neo4j instances). Default credentials are
neo4j/mirofish per docker-compose.mirofish.yml.

Sync runs every 5 minutes. Idempotent — re-syncing re-upserts the same
deterministic UUIDs so points are updated, not duplicated.

Environment:
  MIROFISH_NEO4J_URI         default bolt://127.0.0.1:7688
  MIROFISH_NEO4J_USER        default neo4j
  MIROFISH_NEO4J_PASSWORD    default mirofish
  MIROFISH_SYNC_INTERVAL_S   default 300       (5 min)
  MIROFISH_SYNC_INITIAL_DELAY default 120      (2 min after Brain boot)
  MIROFISH_SYNC_MAX_NODES    default 5000
  MIROFISH_SYNC_ENABLED      default 1
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


NEO4J_URI = os.environ.get("MIROFISH_NEO4J_URI", "bolt://127.0.0.1:7688")
NEO4J_USER = os.environ.get("MIROFISH_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("MIROFISH_NEO4J_PASSWORD", "mirofish")
TICK_INTERVAL_S = float(os.environ.get("MIROFISH_SYNC_INTERVAL_S", "300"))
INITIAL_DELAY_S = float(os.environ.get("MIROFISH_SYNC_INITIAL_DELAY", "120"))
MAX_NODES = int(os.environ.get("MIROFISH_SYNC_MAX_NODES", "5000"))
ENABLED = os.environ.get("MIROFISH_SYNC_ENABLED", "1").lower() in ("1", "true", "yes")


class MirofishKGSync:
    """Periodic Neo4j -> Brain Qdrant mirror."""

    def __init__(self, kg) -> None:
        """Args: kg = QdrantKG instance."""
        self.kg = kg
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._driver = None
        self.stats: Dict[str, Any] = {
            "ticks": 0,
            "nodes_synced": 0,
            "edges_synced": 0,
            "errors": 0,
            "last_error": None,
            "last_tick_ts": None,
            "last_node_count": 0,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not ENABLED:
            logger.info("[mirofish-sync] disabled")
            return
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._loop, daemon=True, name="MirofishKGSync",
        )
        self._worker.start()
        logger.info(
            f"[mirofish-sync] started (every {TICK_INTERVAL_S}s, "
            f"initial delay {INITIAL_DELAY_S}s)"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
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
                logger.warning(f"[mirofish-sync] tick failed: {e}")
            self._stop.wait(TICK_INTERVAL_S)

    # ── Driver ───────────────────────────────────────────────────────

    def _ensure_driver(self):
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import GraphDatabase
        except ImportError:
            raise RuntimeError(
                "neo4j python driver not installed. "
                "Run `pip install neo4j` to enable mirofish-kg sync."
            )
        self._driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
        )
        return self._driver

    # ── Single tick ──────────────────────────────────────────────────

    def tick_once(self) -> Dict[str, Any]:
        """One sync pass: pull all nodes + edges, upsert nodes into
        Brain Qdrant, attach edges as linked.mirofish_neighbours."""
        from core.qdrant_kg import NT_MIROFISH_ENTITY

        try:
            driver = self._ensure_driver()
        except Exception as e:
            self.stats["last_error"] = f"driver: {e}"
            return {"ok": False, "reason": str(e)}

        nodes_synced = 0
        edges_collected: Dict[str, List[str]] = {}

        try:
            with driver.session() as session:
                # 1) Nodes
                rows = session.run(
                    "MATCH (n) RETURN id(n) AS nid, labels(n) AS labels, "
                    "properties(n) AS props "
                    f"LIMIT {MAX_NODES}"
                )
                for r in rows:
                    nid = r["nid"]
                    labels = r["labels"] or []
                    props = dict(r["props"] or {})

                    text = self._compose_text(props)
                    if not text:
                        continue
                    ext_id = f"mirofish-{nid}"
                    try:
                        self.kg._upsert_point(
                            external_id=ext_id,
                            node_type=NT_MIROFISH_ENTITY,
                            text=text,
                            payload_extra={
                                "mirofish_id": nid,
                                "labels": labels,
                                "title": str(props.get("name") or props.get("title") or "")[:200],
                                "props": {
                                    k: v for k, v in props.items()
                                    if isinstance(v, (str, int, float, bool))
                                },
                                "source": "mirofish_neo4j",
                            },
                        )
                        nodes_synced += 1
                    except Exception as e:
                        logger.debug(f"[mirofish-sync] upsert {nid}: {e}")

                # 2) Edges — collected as linked.mirofish_neighbours arrays
                edge_rows = session.run(
                    "MATCH (a)-[r]->(b) RETURN id(a) AS a, id(b) AS b, "
                    "type(r) AS rtype LIMIT 50000"
                )
                for r in edge_rows:
                    a_ext = f"mirofish-{r['a']}"
                    b_ext = f"mirofish-{r['b']}"
                    edges_collected.setdefault(a_ext, []).append(b_ext)

            # Attach neighbour lists in second pass (set_payload only,
            # no re-embedding)
            edges_written = self._write_neighbours(edges_collected)

        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"sync: {type(e).__name__}: {e}"
            return {"ok": False, "reason": str(e)}

        self.stats["nodes_synced"] += nodes_synced
        self.stats["edges_synced"] += edges_written
        self.stats["last_node_count"] = nodes_synced
        return {"ok": True, "nodes": nodes_synced, "edges": edges_written}

    @staticmethod
    def _compose_text(props: Dict[str, Any]) -> str:
        """Build a single text blob from a node's properties for
        embedding. Prefer name/title/description fields."""
        parts: List[str] = []
        for key in ("name", "title", "description", "summary", "content", "text"):
            v = props.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
        if parts:
            return "\n".join(parts)[:1500]
        # fallback: stringify all string props
        for v in props.values():
            if isinstance(v, str) and len(v) > 5:
                parts.append(v)
        return "\n".join(parts)[:1500]

    def _write_neighbours(self, edges: Dict[str, List[str]]) -> int:
        """Update each point's payload.linked.mirofish_neighbours."""
        from core.qdrant_kg import COLLECTIONS, _point_id
        coll = COLLECTIONS["mirofish"]
        written = 0
        for src_ext_id, dsts in edges.items():
            try:
                pid = _point_id(src_ext_id)
                self.kg.client.set_payload(
                    collection_name=coll,
                    payload={
                        "linked": {"mirofish_neighbours": dsts[:50]},
                    },
                    points=[pid],
                )
                written += 1
            except Exception:
                continue
        return written

    # ── Stats ─────────────────────────────────────────────────────────

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "enabled": ENABLED,
            "interval_s": TICK_INTERVAL_S,
            "neo4j_uri": NEO4J_URI,
            "running": bool(self._worker and self._worker.is_alive()),
            **self.stats,
        }
