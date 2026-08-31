"""
Phase S.3 — Fungus client for Brain.

Direct-import wrapper around MCMPRetriever (vibemind-os/la-fungus-search).
Provides semantic code search to DiscourseEngine's QUERY-round resolver
and BrainChat's self-aware lookup path.

Loads the persistent index built by build_vibemind_index.py — does NOT
re-embed at startup. If the index is missing, returns empty hits with a
graceful "fungus offline" flag.

Device handling: defaults to CPU to avoid CUDA-OOM contention with Brain's
sentence-transformer + Qwen embedder. Override via FUNGUS_BRAIN_DEVICE.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Add fungus src/ to path so MCMPRetriever can be imported
_THIS = Path(__file__).resolve()
_REPO = _THIS.parent.parent.parent.parent.parent  # core/ → the_brain/ → brain/ → vibemind-os/ → REPO
_FUNGUS_SRC = _REPO / "vibemind-os" / "la-fungus-search" / "src"
if _FUNGUS_SRC.exists():
    sys.path.insert(0, str(_FUNGUS_SRC))


# Config
ENABLED = os.environ.get("FUNGUS_CLIENT_ENABLED", "1") == "1"
EMBED_MODEL = os.environ.get(
    "FUNGUS_BRAIN_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B"
)
DEVICE_MODE = os.environ.get("FUNGUS_BRAIN_DEVICE", "cpu")


class FungusClient:
    """Lazy-loaded MCMPRetriever wrapper. is_online=False if import or
    persistent-index load fails."""

    def __init__(self) -> None:
        self.is_online = False
        self.error: Optional[str] = None
        self._retriever = None
        self._stats = {
            "queries": 0,
            "hits_returned": 0,
            "errors": 0,
            "doc_count": 0,
            "embed_dim": None,
        }
        if not ENABLED:
            self.error = "disabled via FUNGUS_CLIENT_ENABLED=0"
            return
        self._lazy_load()

    def _lazy_load(self) -> None:
        try:
            from embeddinggemma.mcmp_rag import MCPMRetriever
        except Exception as e:
            self.error = f"import: {type(e).__name__}: {e}"
            logger.warning(f"[fungus] import failed: {self.error}")
            return

        try:
            r = MCPMRetriever(
                embedding_model_name=EMBED_MODEL,
                num_agents=20,             # smaller pool — Brain calls are infrequent
                max_iterations=5,
                device_mode=DEVICE_MODE,
                embed_batch_size=64,
            )
            loaded = r.load_persistent_index()
            if not loaded:
                self.error = (
                    "no persistent index — run "
                    "vibemind-os/la-fungus-search/build_vibemind_index.py"
                )
                logger.warning(f"[fungus] {self.error}")
                return
            self._retriever = r
            self.is_online = True
            self._stats["doc_count"] = len(r.documents)
            self._stats["embed_dim"] = r._embed_dim
            logger.info(
                f"[fungus] loaded persistent index: "
                f"{len(r.documents)} docs, dim={r._embed_dim}, device={DEVICE_MODE}"
            )
        except Exception as e:
            self.error = f"load: {type(e).__name__}: {e}"
            logger.warning(f"[fungus] load failed: {self.error}")

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Semantic code search. Returns list of {path, lines, score, content}.
        Returns [] if offline or on error."""
        if not self.is_online or self._retriever is None:
            return []
        if not query or not query.strip():
            return []

        try:
            self._stats["queries"] += 1
            # search_direct: no MCMP-walker iterations, just kNN over embeddings.
            # Fast enough for synchronous DiscourseEngine query-rounds.
            result = self._retriever.search_direct(query, top_k=int(top_k))
            hits_raw = result.get("results") or []
            hits: List[Dict[str, Any]] = []
            for h in hits_raw:
                content = h.get("content") or h.get("text") or ""
                # Fungus embeds path/lines as a leading comment header:
                #   "# file: <path> | lines: <range> | window: <size>\n<code>"
                path, lines, body = self._parse_chunk_header(content)
                # Fungus uses 'relevance_score' (cosine sim 0-1), not 'score'.
                score = float(h.get("relevance_score", h.get("score", 0.0)))
                hits.append({
                    "path": path,
                    "lines": lines,
                    "score": score,
                    "content": body[:1500],
                })
            self._stats["hits_returned"] += len(hits)
            return hits
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"[fungus] search failed: {e}")
            return []

    @staticmethod
    def _parse_chunk_header(content: str) -> tuple[str, str, str]:
        """Parse fungus's '# file: ... | lines: ...' header off a chunk."""
        if not content:
            return ("?", "?", "")
        first_nl = content.find("\n")
        header = content[:first_nl] if first_nl > 0 else content
        body = content[first_nl + 1:] if first_nl > 0 else content
        if not header.startswith("# file:"):
            return ("?", "?", content)
        parts = [p.strip() for p in header[2:].split("|")]
        path = "?"
        lines = "?"
        for p in parts:
            if p.startswith("file:"):
                path = p.split(":", 1)[1].strip().lstrip("..\\").lstrip("../")
            elif p.startswith("lines:"):
                lines = p.split(":", 1)[1].strip()
        return (path, lines, body)

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "online": self.is_online,
            "error": self.error,
            "device": DEVICE_MODE,
            "model": EMBED_MODEL,
            **self._stats,
        }
