"""Capability Curator — Phase 5.

Closes the feedback loop on the capability router:

  1. Every routed intent (match or no-match) is logged via record_intent().
  2. Periodically — or on demand via /api/capabilities/curator/suggest —
     the curator inspects the no-match log, clusters semantically similar
     missed intents, and proposes a new capability spec for each cluster
     (regex pattern + description + suggested agents).
  3. Suggestions go to a queue. User reviews them via
     /api/capabilities/curator/suggestions and accepts/rejects.
     Accepted suggestions are appended to capabilities.yaml — Brain's
     reload endpoint picks them up live.

This is the "self-curating registry" promised in the plan: Brain
notices its own coverage gaps and proposes how to close them, but never
patches the registry without explicit approval.

Design decisions kept conservative:
  - Suggestions are *appended* to YAML, never replace existing entries.
  - No automatic acceptance — user must POST /accept/<id>.
  - DBSCAN clustering with low min_cluster_size=2 so even a pair of
    related missed intents is enough to surface a suggestion.
  - Telemetry persisted to a JSONL file under data/ so it survives
    Brain restarts. Bounded size (oldest-trimmed) to avoid runaway
    disk growth.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Configuration via env ─────────────────────────────────────────────

_TELEMETRY_PATH = Path(os.environ.get(
    "CAPABILITY_TELEMETRY_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "capability_telemetry.jsonl"),
))
_SUGGESTIONS_PATH = Path(os.environ.get(
    "CAPABILITY_SUGGESTIONS_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "capability_suggestions.json"),
))
_MAX_TELEMETRY_LINES = int(os.environ.get("CAPABILITY_TELEMETRY_MAX_LINES", "5000"))
_CLUSTER_EPS = float(os.environ.get("CAPABILITY_CURATOR_CLUSTER_EPS", "0.25"))
_MIN_CLUSTER_SIZE = int(os.environ.get("CAPABILITY_CURATOR_MIN_CLUSTER_SIZE", "2"))


# ── Data classes ───────────────────────────────────────────────────────


@dataclass
class TelemetryEntry:
    ts: float
    intent: str
    matched: bool
    capability: Optional[str] = None
    match_method: Optional[str] = None  # 'regex' | 'semantic' | None
    embedding: Optional[List[float]] = None  # only stored for no-match clustering

    def to_jsonl(self) -> str:
        d = {
            "ts": self.ts,
            "intent": self.intent[:500],
            "matched": self.matched,
            "capability": self.capability,
            "match_method": self.match_method,
        }
        if self.embedding:
            # Serialise embedding only for no-match entries; truncate
            # precision to 4 decimals for compactness.
            d["embedding"] = [round(float(x), 4) for x in self.embedding]
        return json.dumps(d, ensure_ascii=False)


@dataclass
class CapabilitySuggestion:
    id: str
    cluster_size: int
    sample_intents: List[str]
    suggested_capability: str
    suggested_description: str
    suggested_patterns: List[str]
    suggested_anchors: List[str]
    suggested_agents_primary: List[str] = field(default_factory=list)
    suggested_agents_supporting: List[str] = field(default_factory=list)
    suggested_execution_target: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | accepted | rejected
    decided_at: Optional[float] = None
    decided_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cluster_size": self.cluster_size,
            "sample_intents": list(self.sample_intents),
            "suggested_capability": self.suggested_capability,
            "suggested_description": self.suggested_description,
            "suggested_patterns": list(self.suggested_patterns),
            "suggested_anchors": list(self.suggested_anchors),
            "suggested_agents_primary": list(self.suggested_agents_primary),
            "suggested_agents_supporting": list(self.suggested_agents_supporting),
            "suggested_execution_target": self.suggested_execution_target,
            "created_at": self.created_at,
            "status": self.status,
            "decided_at": self.decided_at,
            "decided_reason": self.decided_reason,
        }


# ── Curator ────────────────────────────────────────────────────────────


class CapabilityCurator:
    """Telemetry recorder + clustering + suggestion generator + accept/reject."""

    def __init__(
        self,
        registry_path: Path,
        embedder=None,
        capability_router=None,
    ) -> None:
        self.registry_path = Path(registry_path)
        self._embedder = embedder
        self._cap_router = capability_router  # for reload after accept
        self._lock = threading.RLock()
        # Recent in-memory ring buffer for fast cluster runs
        self._recent: Deque[TelemetryEntry] = deque(maxlen=2000)
        self._suggestions: Dict[str, CapabilitySuggestion] = {}
        self._stats: Dict[str, Any] = {
            "intents_logged": 0,
            "no_match_logged": 0,
            "matches_logged": 0,
            "suggestions_generated": 0,
            "suggestions_accepted": 0,
            "suggestions_rejected": 0,
            "last_cluster_run_ts": None,
            "last_cluster_run_count": 0,
        }
        # Load persisted state — but never fail init on disk hiccups
        # (transient WinError 1450 during heavy startup is enough to abort
        # the whole curator otherwise). Subsequent record/suggest calls
        # work fine even with fresh in-memory state.
        try:
            self._load_persisted()
        except Exception as e:
            logger.warning(f"[curator] persisted-state reload skipped: {e}")

    # ── Wiring ──────────────────────────────────────────────────────────

    def set_embedder(self, embedder) -> None:
        self._embedder = embedder

    def set_capability_router(self, router) -> None:
        self._cap_router = router

    def attach_continuous_thinking(self, cte) -> None:
        """Phase 7.5 — wire CTE so cluster discoveries become thought-seeds."""
        self._continuous_thinking = cte

    # ── Telemetry ──────────────────────────────────────────────────────

    def record_intent(
        self,
        intent: str,
        matched: bool,
        *,
        capability: Optional[str] = None,
        match_method: Optional[str] = None,
    ) -> None:
        """Log a routing decision. No-match entries get embedded so they
        can be clustered later. Matched entries are stored without
        embedding to save space."""
        if not intent or not intent.strip():
            return
        intent = intent.strip()
        embedding: Optional[List[float]] = None
        if not matched and self._embedder is not None:
            try:
                v = self._embed(intent)
                if v:
                    embedding = list(v)
            except Exception as e:
                logger.debug(f"[curator] embed failed for no-match intent: {e}")
        entry = TelemetryEntry(
            ts=time.time(),
            intent=intent,
            matched=bool(matched),
            capability=capability,
            match_method=match_method,
            embedding=embedding,
        )
        with self._lock:
            self._recent.append(entry)
            self._stats["intents_logged"] += 1
            if matched:
                self._stats["matches_logged"] += 1
            else:
                self._stats["no_match_logged"] += 1
            try:
                self._append_jsonl(entry)
            except Exception as e:
                logger.debug(f"[curator] persist failed: {e}")

    # ── Cluster + suggest ──────────────────────────────────────────────

    def suggest(
        self,
        *,
        max_suggestions: int = 5,
        min_age_s: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Cluster recent no-match intents and produce up to N suggestions.

        Returns the list of suggestion dicts that are now `pending` in the
        queue. Idempotent — re-running with the same data returns the
        already-generated suggestions for the same cluster signatures.
        """
        with self._lock:
            self._stats["last_cluster_run_ts"] = time.time()
            now = time.time()
            no_match = [
                e for e in self._recent
                if (not e.matched)
                and e.embedding
                and (now - e.ts) >= min_age_s
            ]
            if len(no_match) < _MIN_CLUSTER_SIZE:
                self._stats["last_cluster_run_count"] = 0
                return []

            clusters = _dbscan_cosine(
                [e.embedding for e in no_match],
                eps=_CLUSTER_EPS,
                min_size=_MIN_CLUSTER_SIZE,
            )
            self._stats["last_cluster_run_count"] = len(clusters)

            generated: List[Dict[str, Any]] = []
            for indexes in clusters[:max_suggestions]:
                samples = [no_match[i].intent for i in indexes]
                signature = _cluster_signature(samples)
                # Skip clusters whose signature already maps to a pending
                # suggestion (so re-runs don't pile up duplicates).
                existing = self._find_pending_by_signature(signature)
                if existing:
                    generated.append(existing.to_dict())
                    continue
                suggestion = self._build_suggestion(samples, signature)
                self._suggestions[suggestion.id] = suggestion
                self._stats["suggestions_generated"] += 1
                generated.append(suggestion.to_dict())
                # Phase 7.5 — surface to ContinuousThinkingEngine
                cte = getattr(self, "_continuous_thinking", None)
                if cte is not None:
                    try:
                        cte.record_event("no_match_cluster", {
                            "signature": signature,
                            "sample_intents": samples[:5],
                            "capability": suggestion.suggested_capability,
                        })
                    except Exception:
                        pass
            self._persist_suggestions()
            return generated

    def _find_pending_by_signature(self, sig: str) -> Optional[CapabilitySuggestion]:
        for s in self._suggestions.values():
            if s.status == "pending" and s.id.endswith(sig):
                return s
        return None

    def _build_suggestion(self, samples: List[str], signature: str) -> CapabilitySuggestion:
        """Heuristic spec generation. Phase 5 keeps this rule-based so it
        works without an LLM call. The user can edit the YAML further
        after acceptance."""
        # Common token: pick the most-frequent meaningful word across samples
        common = _most_common_keyword(samples)
        cap_id = f"auto_{common}_{signature}"[:48].lower()
        cap_id = re.sub(r"[^a-z0-9_]+", "_", cap_id).strip("_")
        if not cap_id:
            cap_id = f"auto_capability_{signature}"

        description = (
            f"Auto-suggested by curator from {len(samples)} similar missed "
            f"intents. Common keyword: {common}. Sample: "
            f"{samples[0][:120]!r}"
        )
        patterns = _build_patterns(samples)
        anchors = list(samples[: min(5, len(samples))])
        # No agent assignment by default — user must pick
        return CapabilitySuggestion(
            id=cap_id,
            cluster_size=len(samples),
            sample_intents=list(samples[:10]),
            suggested_capability=cap_id,
            suggested_description=description,
            suggested_patterns=patterns,
            suggested_anchors=anchors,
            suggested_agents_primary=[],
            suggested_agents_supporting=[],
            suggested_execution_target=None,
        )

    # ── Accept / reject ────────────────────────────────────────────────

    def list_suggestions(
        self, *, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._suggestions.values())
            if status:
                items = [s for s in items if s.status == status]
            items.sort(key=lambda s: -s.created_at)
            return [s.to_dict() for s in items]

    def accept(
        self,
        suggestion_id: str,
        *,
        agents_primary: Optional[List[str]] = None,
        agents_supporting: Optional[List[str]] = None,
        execution_target: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append the suggestion to capabilities.yaml. Reload router so the
        capability becomes live without a Brain restart.

        Optional overrides let the user pin agents / execution target
        before the YAML write.
        """
        with self._lock:
            sug = self._suggestions.get(suggestion_id)
            if sug is None:
                return {"ok": False, "error": f"unknown suggestion '{suggestion_id}'"}
            if sug.status != "pending":
                return {"ok": False, "error": f"suggestion already {sug.status}"}

            if agents_primary is not None:
                sug.suggested_agents_primary = list(agents_primary)
            if agents_supporting is not None:
                sug.suggested_agents_supporting = list(agents_supporting)
            if execution_target is not None:
                sug.suggested_execution_target = execution_target

            try:
                self._append_to_yaml(sug)
            except Exception as e:
                return {"ok": False, "error": f"yaml write failed: {e}"}

            sug.status = "accepted"
            sug.decided_at = time.time()
            sug.decided_reason = reason or ""
            self._stats["suggestions_accepted"] += 1
            self._persist_suggestions()

        # Reload the router so the new capability is matchable immediately.
        if self._cap_router is not None:
            try:
                self._cap_router.reload()
            except Exception as e:
                logger.warning(f"[curator] router reload after accept failed: {e}")

        return {"ok": True, "id": suggestion_id, "status": "accepted"}

    def reject(self, suggestion_id: str, *, reason: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            sug = self._suggestions.get(suggestion_id)
            if sug is None:
                return {"ok": False, "error": f"unknown suggestion '{suggestion_id}'"}
            if sug.status != "pending":
                return {"ok": False, "error": f"suggestion already {sug.status}"}
            sug.status = "rejected"
            sug.decided_at = time.time()
            sug.decided_reason = reason or ""
            self._stats["suggestions_rejected"] += 1
            self._persist_suggestions()
        return {"ok": True, "id": suggestion_id, "status": "rejected"}

    def stats_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    # ── Persistence helpers ────────────────────────────────────────────

    def _append_jsonl(self, entry: TelemetryEntry) -> None:
        _TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TELEMETRY_PATH.open("a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")
        # Trim file if too large
        try:
            with _TELEMETRY_PATH.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > _MAX_TELEMETRY_LINES:
                keep = lines[-_MAX_TELEMETRY_LINES:]
                with _TELEMETRY_PATH.open("w", encoding="utf-8") as f:
                    f.writelines(keep)
        except Exception:
            pass

    def _load_persisted(self) -> None:
        """Re-load recent telemetry + previously generated suggestions."""
        try:
            if _TELEMETRY_PATH.exists():
                with _TELEMETRY_PATH.open("r", encoding="utf-8") as f:
                    lines = f.readlines()[-1500:]
                for line in lines:
                    try:
                        d = json.loads(line)
                        self._recent.append(TelemetryEntry(
                            ts=float(d.get("ts") or 0.0),
                            intent=str(d.get("intent") or ""),
                            matched=bool(d.get("matched")),
                            capability=d.get("capability"),
                            match_method=d.get("match_method"),
                            embedding=d.get("embedding"),
                        ))
                    except Exception:
                        continue
                self._stats["intents_logged"] = len(self._recent)
                self._stats["no_match_logged"] = sum(
                    1 for e in self._recent if not e.matched
                )
                self._stats["matches_logged"] = (
                    self._stats["intents_logged"] - self._stats["no_match_logged"]
                )
        except Exception as e:
            logger.debug(f"[curator] telemetry reload failed: {e}")

        try:
            if _SUGGESTIONS_PATH.exists():
                data = json.loads(_SUGGESTIONS_PATH.read_text(encoding="utf-8"))
                for d in data.get("suggestions", []) or []:
                    sug = CapabilitySuggestion(
                        id=d["id"],
                        cluster_size=int(d.get("cluster_size") or 0),
                        sample_intents=list(d.get("sample_intents") or []),
                        suggested_capability=d.get("suggested_capability") or d["id"],
                        suggested_description=d.get("suggested_description") or "",
                        suggested_patterns=list(d.get("suggested_patterns") or []),
                        suggested_anchors=list(d.get("suggested_anchors") or []),
                        suggested_agents_primary=list(d.get("suggested_agents_primary") or []),
                        suggested_agents_supporting=list(d.get("suggested_agents_supporting") or []),
                        suggested_execution_target=d.get("suggested_execution_target"),
                        created_at=float(d.get("created_at") or time.time()),
                        status=str(d.get("status") or "pending"),
                        decided_at=d.get("decided_at"),
                        decided_reason=d.get("decided_reason"),
                    )
                    self._suggestions[sug.id] = sug
        except Exception as e:
            logger.debug(f"[curator] suggestions reload failed: {e}")

    def _persist_suggestions(self) -> None:
        try:
            _SUGGESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {"suggestions": [s.to_dict() for s in self._suggestions.values()]}
            _SUGGESTIONS_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.debug(f"[curator] persist suggestions failed: {e}")

    def _append_to_yaml(self, sug: CapabilitySuggestion) -> None:
        """Append a YAML block for the accepted suggestion. Keeps existing
        capabilities untouched. Fails (raises) if the registry path doesn't
        exist."""
        if not self.registry_path.exists():
            raise FileNotFoundError(self.registry_path)

        block = _render_yaml_block(sug)
        # Atomic append — read full file, append, write back, so a partial
        # write can't corrupt the registry mid-stream.
        existing = self.registry_path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        new_content = existing + "\n" + block + "\n"
        tmp = self.registry_path.with_suffix(self.registry_path.suffix + ".tmp")
        tmp.write_text(new_content, encoding="utf-8")
        tmp.replace(self.registry_path)

    # ── Embedder adapter ───────────────────────────────────────────────

    def _embed(self, text: str) -> Optional[List[float]]:
        emb = self._embedder
        if emb is None:
            return None
        for attr in ("embed", "encode"):
            fn = getattr(emb, attr, None)
            if callable(fn):
                try:
                    v = fn(text)
                    if hasattr(v, "tolist"):
                        return list(v.tolist())
                    if v is not None:
                        return list(v)
                except Exception:
                    continue
        try:
            inner = getattr(emb, "_retriever", None)
            if inner is not None:
                model = getattr(inner, "embedding_model", None)
                if model is not None:
                    v = model.encode(text)
                    if hasattr(v, "tolist"):
                        return list(v.tolist())
                    return list(v)
        except Exception:
            pass
        return None


# ── Helpers — clustering + signature + pattern derivation ─────────────


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _dbscan_cosine(
    vectors: List[List[float]],
    *,
    eps: float,
    min_size: int,
) -> List[List[int]]:
    """Tiny pure-python DBSCAN over cosine distance (1 - cosine_sim).
    Linear in N^2 — fine for the few hundred no-match entries we expect.
    """
    n = len(vectors)
    if n == 0:
        return []
    visited = [False] * n
    labels = [-1] * n
    clusters: List[List[int]] = []

    def neighbors(i: int) -> List[int]:
        out = []
        for j in range(n):
            if i == j:
                continue
            d = 1.0 - _cosine(vectors[i], vectors[j])
            if d <= eps:
                out.append(j)
        return out

    cluster_id = 0
    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        nb = neighbors(i)
        if len(nb) + 1 < min_size:
            continue
        # Start a cluster
        labels[i] = cluster_id
        seeds = list(nb)
        idx = 0
        while idx < len(seeds):
            j = seeds[idx]
            if not visited[j]:
                visited[j] = True
                jn = neighbors(j)
                if len(jn) + 1 >= min_size:
                    for k in jn:
                        if k not in seeds:
                            seeds.append(k)
            if labels[j] == -1:
                labels[j] = cluster_id
            idx += 1
        cluster_id += 1

    for cid in range(cluster_id):
        members = [i for i, lab in enumerate(labels) if lab == cid]
        if len(members) >= min_size:
            clusters.append(members)
    return clusters


_STOP = {
    "the", "a", "an", "is", "are", "to", "of", "in", "on", "for", "and",
    "or", "i", "you", "we", "they", "it", "this", "that", "my", "your",
    "what", "how", "why", "when", "where", "do", "does", "did", "be",
    "have", "has", "had", "with", "will", "would", "should", "can",
    "could", "make", "let", "me", "us", "them", "der", "die", "das",
    "ein", "eine", "und", "oder", "bei", "wie", "was", "wer", "wo",
    "ist", "sind", "ich", "du", "wir", "ihr", "sie",
}


def _tokenise(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-zA-Z]{3,}", text.lower()) if w not in _STOP]


def _most_common_keyword(samples: List[str]) -> str:
    counts: Dict[str, int] = {}
    for s in samples:
        for tok in _tokenise(s):
            counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return "intent"
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _cluster_signature(samples: List[str]) -> str:
    """Stable short signature derived from the top-3 keywords."""
    counts: Dict[str, int] = {}
    for s in samples:
        for tok in _tokenise(s):
            counts[tok] = counts.get(tok, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return "_".join(t for t, _ in top) or "anon"


def _build_patterns(samples: List[str]) -> List[str]:
    """Derive 1-3 conservative regex patterns from the cluster.
    Strategy: take the top-1 keyword as a required word; build a couple
    of variations (verb + noun) when possible. Patterns are intentionally
    loose — user is expected to refine on accept."""
    kws = []
    counts: Dict[str, int] = {}
    for s in samples:
        for tok in _tokenise(s):
            counts[tok] = counts.get(tok, 0) + 1
    top = [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    if not top:
        return [r".+"]
    kws = [re.escape(t) for t in top]
    patterns: List[str] = []
    patterns.append(rf"\b({'|'.join(kws)})\b")
    if len(kws) >= 2:
        patterns.append(rf"\b{kws[0]}\b.*\b{kws[1]}\b")
    return patterns


def _render_yaml_block(sug: CapabilitySuggestion) -> str:
    """Render a YAML block compatible with capabilities.yaml schema."""
    lines: List[str] = []
    lines.append(f"- capability: {sug.suggested_capability}")
    lines.append(f"  description: {_yaml_str(sug.suggested_description)}")
    if sug.suggested_anchors:
        lines.append("  anchor_phrases:")
        for ap in sug.suggested_anchors:
            lines.append(f"    - {_yaml_str(ap)}")
    lines.append("  match_patterns:")
    for p in sug.suggested_patterns:
        lines.append(f"    - {_yaml_str(p)}")
    if sug.suggested_execution_target:
        lines.append(f"  execution_target: {_yaml_str(sug.suggested_execution_target)}")
    if sug.suggested_agents_primary or sug.suggested_agents_supporting:
        lines.append("  agents:")
        if sug.suggested_agents_primary:
            primary = ", ".join(sug.suggested_agents_primary)
            lines.append(f"    primary: [{primary}]")
        if sug.suggested_agents_supporting:
            supp = ", ".join(sug.suggested_agents_supporting)
            lines.append(f"    supporting: [{supp}]")
    lines.append(f"  # auto-curated by Phase 5 from {sug.cluster_size} missed intents")
    return "\n".join(lines)


def _yaml_str(s: str) -> str:
    """Quote a YAML string safely. Falls back to single-quote escape."""
    if not s:
        return '""'
    if any(c in s for c in [":", "#", "\n", "{", "}", "[", "]", "|", ">", "*", "&", "!", "%", "@", "`"]) or s.lstrip()[:1] in ("-", "?"):
        return "'" + s.replace("'", "''") + "'"
    return s
