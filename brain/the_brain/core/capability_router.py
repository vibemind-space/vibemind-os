"""Capability Router — Phase 1 (regex) + Phase 2 (semantic fallback).

Maps incoming intents to a curated subset of OpenFang agents based on
data/capabilities.yaml. Falls back to None on no-match — caller decides
whether to broadcast.

See docs/plans/2026-05-01-capability-router-design.md and
2026-05-01-capability-router-plan.md for the full design.

Phase 1 (regex) is deliberately additive:
    - On no-match, route() returns None and the existing broadcast path
      in DiscourseEngine.tick_intent stays in effect (zero regression).
    - On match, returns a CapabilityMatch with agent names; the
      DiscourseEngine resolves them against its loaded OpenFang agents
      and dispatches to a focused 3-5 agent set instead of all 25.

Phase 2 (semantic fallback, opt-in via set_embedder()):
    - On regex-miss, embed the intent and cosine-compare against cached
      capability description embeddings. First match >= threshold wins.
    - Threshold default 0.6, env-overridable via CAPABILITY_SEMANTIC_THRESHOLD.
    - Uses any embedder that exposes a `.embed(text) -> List[float]` method.
      In Brain we wire FungusClient's embedder (already loaded for S.3).
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


_DEFAULT_SEMANTIC_THRESHOLD = float(
    os.environ.get("CAPABILITY_SEMANTIC_THRESHOLD", "0.65")
)


class _CodingProviderIntent(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    BLOCKED = "blocked"


_PROVIDER_SELECTION = re.compile(
    r"\b(?:use|ask|have)\s+(?:the\s+)?(?:(?:only|both|either)\s+)?"
    r"(?:claude|anthropic|openai)"
    r"(?:\s+(?:model|agent))?\b|"
    r"\b(?:with|using|via|through)\s+(?:the\s+)?(?:claude|anthropic|openai)"
    r"(?:\s+(?:model|agent))?\b|"
    r"\b(?:without|avoid(?:ing)?|except(?:\s+for)?|neither|nor|not)\s+"
    r"(?:using\s+)?(?:claude|anthropic|openai)\b|"
    r"\bmit\s+(?:claude|anthropic|openai)\b|"
    r"\b(?:claude(?:\s+code)?|anthropic|openai)\s+verwenden\b|"
    r"\b(?:claude|anthropic|openai)\s*[,;:]|"
    r"\b(?:and|or|und|oder)\s+(?:claude|anthropic|openai)\b|"
    r"\bdefault\s+provider\b",
    re.IGNORECASE,
)
_PROVIDER_MENTION = re.compile(
    r"\b(?:claude(?:\s+code)?|anthropic|openai)\b",
    re.IGNORECASE,
)
_NEGATION_SUFFIX = re.compile(
    r"(?:\bdo\s+not(?:\s+ever)?|\bdon't(?:\s+ever)?|\bnever|\bnot|\bnicht|"
    r"\bkein(?:e|en|er|em|es)?)\s*$",
    re.IGNORECASE,
)

# Runbook §7.5 (2026-08-29): selecting an UNSUPPORTED provider must fail
# closed for the coding lanes — never silently fall back to the OpenAI
# default. These are distinct third-party provider names; bare "gpt" and
# "codex" stay out on purpose (they name the ChatGPT lane itself and appear
# in too many neutral contexts). Word-boundary matching keeps file/module
# names like `ollama_tool.py` or `gemini_client.py` out (underscore is \w,
# so no boundary forms inside them). Any selection-context hit — selecting,
# coordinating, or negating such a provider — blocks; the phrase is about a
# provider this system does not offer, so no route is the honest answer.
_FOREIGN_PROVIDER_TOKENS = (
    r"(?:gemini|google|grok|xai|copilot|mistral|deepseek|llama|ollama|"
    r"qwen|groq|openrouter|perplexity|kimi)"
)
_FOREIGN_PROVIDER_SELECTION = re.compile(
    r"\b(?:use|ask|have)\s+(?:the\s+)?(?:(?:only|both|either)\s+)?"
    + _FOREIGN_PROVIDER_TOKENS
    + r"(?:\s+(?:model|agent))?\b|"
    r"\b(?:with|using|via|through)\s+(?:the\s+)?"
    + _FOREIGN_PROVIDER_TOKENS
    + r"(?:\s+(?:model|agent))?\b|"
    r"\b(?:without|avoid(?:ing)?|except(?:\s+for)?|neither|nor|not)\s+"
    r"(?:using\s+)?" + _FOREIGN_PROVIDER_TOKENS + r"\b|"
    r"\bmit\s+" + _FOREIGN_PROVIDER_TOKENS + r"\b|"
    r"\b" + _FOREIGN_PROVIDER_TOKENS + r"\s+verwenden\b|"
    r"\b(?:and|or|und|oder)\s+" + _FOREIGN_PROVIDER_TOKENS + r"\b",
    re.IGNORECASE,
)


def _coding_provider_intent(intent: str) -> _CodingProviderIntent:
    """Resolve coding-provider selection once, including negation/conflicts."""
    if _FOREIGN_PROVIDER_SELECTION.search(intent):
        return _CodingProviderIntent.BLOCKED
    selected: set[_CodingProviderIntent] = set()
    rejected: set[_CodingProviderIntent] = set()
    previous_was_rejected = False
    for match in _PROVIDER_SELECTION.finditer(intent):
        token = match.group(0).casefold()
        provider = (
            _CodingProviderIntent.OPENAI
            if "openai" in token or "default provider" in token
            else _CodingProviderIntent.ANTHROPIC
        )
        prefix = intent[max(0, match.start() - 32) : match.start()]
        coordinated = re.match(r"(?:and|or|und|oder|nor)\b", token) is not None
        explicitly_rejected = re.match(
            r"(?:without|avoid(?:ing)?|except(?:\s+for)?|neither|nor|not)\b",
            token,
        ) is not None
        is_rejected = explicitly_rejected or (
            previous_was_rejected
            if coordinated
            else bool(_NEGATION_SUFFIX.search(prefix))
        )
        if is_rejected:
            rejected.add(provider)
        else:
            selected.add(provider)
        previous_was_rejected = is_rejected

    mentioned = {
        _CodingProviderIntent.OPENAI
        if "openai" in match.group(0).casefold()
        else _CodingProviderIntent.ANTHROPIC
        for match in _PROVIDER_MENTION.finditer(intent)
    }
    if not mentioned.issubset(selected | rejected):
        return _CodingProviderIntent.BLOCKED

    if not selected:
        return _CodingProviderIntent.BLOCKED if rejected else _CodingProviderIntent.OPENAI
    if len(selected) != 1:
        return _CodingProviderIntent.BLOCKED
    provider = next(iter(selected))
    return _CodingProviderIntent.BLOCKED if provider in rejected else provider


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity. Returns 0.0 on dim-mismatch / empty input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class CapabilityMatch:
    """Result of router.route() — routed agents + provenance."""

    capability: str
    description: str
    primary_names: List[str]
    supporting_names: List[str]
    matched_pattern: str
    match_method: str = "regex"          # "regex" | "semantic" (Phase 2) | "fallback"

    # Phase 1.5 fields — populated if YAML has execution_target / feedback_loop;
    # ignored by Phase 1 dispatch path (which only narrows agents).
    execution_target: Optional[str] = None
    arg_extractor: Optional[str] = None
    arg_kwarg: Optional[str] = None      # If set, wrap arg as {arg_kwarg: arg}
    feedback_loop: Optional[Dict[str, Any]] = None
    # Phase 3 — validator config dict, e.g. {"kind": "rule:non_empty_result", "on_fail": "report"}
    validator: Optional[Dict[str, Any]] = None

    @property
    def all_agent_names(self) -> List[str]:
        return list(self.primary_names) + list(self.supporting_names)

    @property
    def is_direct(self) -> bool:
        """True if Phase 1.5 should take over (direct execution path).
        Phase 1 ignores this and uses the agent-based path always."""
        return bool(self.execution_target and self.execution_target.startswith("direct:"))

    @property
    def has_execution_target(self) -> bool:
        """Phase 4 — True for any registered execution-target kind (direct,
        http, n8n, coding-engine, openfang, brain, mcp). Tells the
        DiscourseEngine to short-circuit out of broadcast mode and call the
        target executor instead."""
        if not self.execution_target or ":" not in self.execution_target:
            return False
        kind = self.execution_target.split(":", 1)[0].lower()
        return kind in {"direct", "http", "n8n", "coding-engine", "openfang", "brain", "mcp", "research"}


@dataclass
class _CompiledCapability:
    capability: str
    description: str
    primary_names: List[str]
    supporting_names: List[str]
    patterns: List[re.Pattern] = field(default_factory=list)
    execution_target: Optional[str] = None
    arg_extractor: Optional[str] = None
    arg_kwarg: Optional[str] = None
    feedback_loop: Optional[Dict[str, Any]] = None
    validator: Optional[Dict[str, Any]] = None  # Phase 3
    coding_provider: Optional[str] = None
    # Phase 2 — populated lazily by _build_embeddings() once an embedder
    # is wired via set_embedder(). Single description embedding plus a
    # list of anchor-phrase embeddings (Phase 2.5) — match takes max
    # cosine across all of them.
    description_embedding: Optional[List[float]] = None
    anchor_phrases: List[str] = field(default_factory=list)
    anchor_embeddings: List[List[float]] = field(default_factory=list)


class CapabilityRouter:
    """Regex + semantic-fallback router (Phase 1 + Phase 2)."""

    def __init__(self, registry_path: Path):
        self.registry_path = Path(registry_path)
        self._capabilities: List[_CompiledCapability] = []
        self._embedder = None  # Phase 2 — set via set_embedder()
        self._semantic_threshold = _DEFAULT_SEMANTIC_THRESHOLD
        self._stats = {
            "matches": 0,
            "regex_matches": 0,
            "semantic_matches": 0,
            "no_match": 0,
            "load_errors": 0,
            "bad_patterns": 0,
            "semantic_below_threshold": 0,
            "embedder_attached": False,
            "descriptions_embedded": 0,
        }
        self._load()

    # ── Phase 2 — semantic fallback wiring ────────────────────────────

    def set_embedder(self, embedder) -> None:
        """Wire any object with a `.embed(text) -> List[float]` method.
        In Brain we pass FungusClient's MCMPRetriever embedding model
        wrapper so we don't load a second sentence-transformer.

        Phase 11.R — embedding build runs in a daemon background thread
        so brain-server boot doesn't block on 100+ anchor embeddings.
        Regex-only routing works immediately; semantic-fallback comes
        online when the build finishes (typically 30-90s after boot).
        """
        self._embedder = embedder
        self._stats["embedder_attached"] = bool(embedder is not None)
        self._stats["embedding_build_state"] = "idle"
        if embedder is not None:
            self._start_embedding_build_async()

    def _start_embedding_build_async(self) -> None:
        """Kick off the (potentially long) _build_embeddings() in a daemon
        thread. The router stays usable for regex matches the whole time;
        only semantic-fallback waits for `_stats[embedding_build_state]`
        to flip to 'done'."""
        import threading
        if getattr(self, "_embedding_thread", None) and self._embedding_thread.is_alive():
            return  # already running
        self._stats["embedding_build_state"] = "running"
        def _worker():
            try:
                self._build_embeddings()
                self._stats["embedding_build_state"] = "done"
            except Exception as e:
                self._stats["embedding_build_state"] = f"error:{type(e).__name__}"
                logger.warning(f"[cap-router] async embedding build failed: {e}")
        t = threading.Thread(target=_worker, name="cap-router-embedder", daemon=True)
        self._embedding_thread = t
        t.start()
        logger.info("[cap-router] embedding build started (background thread)")

    def _build_embeddings(self) -> None:
        """Embed each capability description + any anchor_phrases listed in
        the YAML. Phase 2.5 — semantic match takes max cosine across the
        description vector AND all anchor vectors, which raises recall
        from ~70% to ~90%+ on paraphrase-style intents.

        Idempotent — safe to call after reload(). Errors per-capability so
        a single bad embed doesn't break the whole router."""
        if self._embedder is None:
            return
        embedded_descs = 0
        embedded_anchors = 0
        for cap in self._capabilities:
            # Description embedding
            if cap.description_embedding is None:
                text = (cap.description or cap.capability).strip()
                if text:
                    try:
                        vec = self._embed_text(text)
                        if vec:
                            cap.description_embedding = vec
                            embedded_descs += 1
                    except Exception as e:
                        logger.warning(
                            f"[cap-router] could not embed description for "
                            f"{cap.capability!r}: {e}"
                        )

            # Anchor-phrase embeddings (Phase 2.5)
            if cap.anchor_phrases and not cap.anchor_embeddings:
                for phrase in cap.anchor_phrases:
                    phrase = (phrase or "").strip()
                    if not phrase:
                        continue
                    try:
                        vec = self._embed_text(phrase)
                        if vec:
                            cap.anchor_embeddings.append(vec)
                            embedded_anchors += 1
                    except Exception as e:
                        logger.warning(
                            f"[cap-router] could not embed anchor for "
                            f"{cap.capability!r}: {e}"
                        )

        self._stats["descriptions_embedded"] = sum(
            1 for c in self._capabilities if c.description_embedding is not None
        )
        self._stats["anchors_embedded"] = sum(
            len(c.anchor_embeddings) for c in self._capabilities
        )
        logger.info(
            f"[cap-router] embedded {embedded_descs} new descriptions + "
            f"{embedded_anchors} new anchor phrases; total cached: "
            f"{self._stats['descriptions_embedded']} desc, "
            f"{self._stats['anchors_embedded']} anchors"
        )

    def _embed_text(self, text: str) -> Optional[List[float]]:
        """Adapter — different embedders expose different method names.
        Try the common ones in order so this works with FungusClient,
        sentence-transformers, and a thin custom wrapper."""
        emb = self._embedder
        if emb is None:
            return None
        # 1. Common '.embed(text)' shape
        if hasattr(emb, "embed"):
            try:
                v = emb.embed(text)
                if v is not None:
                    return list(v)
            except Exception:
                pass
        # 2. SentenceTransformer-style '.encode(text)'
        if hasattr(emb, "encode"):
            try:
                v = emb.encode(text)
                # numpy array → list
                if hasattr(v, "tolist"):
                    return list(v.tolist())
                return list(v)
            except Exception:
                pass
        # 3. FungusClient-style '._retriever.embedding_model.encode(text)'
        try:
            inner = getattr(emb, "_retriever", None)
            if inner is not None:
                model = getattr(inner, "embedding_model", None)
                if model is not None and hasattr(model, "encode"):
                    v = model.encode(text)
                    if hasattr(v, "tolist"):
                        return list(v.tolist())
                    return list(v)
        except Exception:
            pass
        return None

    # ── Load / reload ─────────────────────────────────────────────────

    def _load(self) -> None:
        if not self.registry_path.exists():
            logger.warning(f"[cap-router] registry not found: {self.registry_path}")
            return
        try:
            data = yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or []
        except Exception as e:
            logger.error(f"[cap-router] yaml parse failed: {e}")
            self._stats["load_errors"] += 1
            return

        if not isinstance(data, list):
            logger.error(f"[cap-router] registry must be a list, got {type(data).__name__}")
            self._stats["load_errors"] += 1
            return

        compiled: List[_CompiledCapability] = []
        for entry in data:
            if not isinstance(entry, dict):
                logger.warning(f"[cap-router] skipping non-dict entry: {entry!r}")
                self._stats["load_errors"] += 1
                continue
            if entry.get("enabled") is False:
                logger.info(
                    "[cap-router] skipping disabled capability %r",
                    entry.get("capability", "<unnamed>"),
                )
                continue
            try:
                cap_id = entry["capability"]
                pats_raw = entry.get("match_patterns") or []
                coding_provider = entry.get("coding_provider")
                if coding_provider not in {None, "openai", "anthropic"}:
                    raise ValueError(f"invalid coding_provider for {cap_id!r}")
                # Compile each regex; skip individual bad ones rather than
                # losing the whole capability.
                patterns: List[re.Pattern] = []
                for p in pats_raw:
                    try:
                        patterns.append(re.compile(p, re.IGNORECASE))
                    except re.error as re_err:
                        logger.warning(
                            f"[cap-router] bad regex in '{cap_id}': {p!r} ({re_err})"
                        )
                        self._stats["bad_patterns"] += 1
                if not patterns:
                    logger.warning(f"[cap-router] '{cap_id}' has no usable patterns, skipping")
                    self._stats["load_errors"] += 1
                    continue
                agents_block = entry.get("agents") or {}
                compiled.append(_CompiledCapability(
                    capability=cap_id,
                    description=entry.get("description", ""),
                    primary_names=list(agents_block.get("primary") or []),
                    supporting_names=list(agents_block.get("supporting") or []),
                    patterns=patterns,
                    execution_target=entry.get("execution_target"),
                    arg_extractor=entry.get("result_arg_extractor"),
                    arg_kwarg=entry.get("arg_kwarg"),
                    feedback_loop=entry.get("feedback_loop"),
                    validator=entry.get("validator"),
                    coding_provider=coding_provider,
                    anchor_phrases=list(entry.get("anchor_phrases") or []),
                ))
            except Exception as e:
                logger.warning(f"[cap-router] skipping bad entry: {e}")
                self._stats["load_errors"] += 1
        self._capabilities = compiled
        logger.info(
            f"[cap-router] loaded {len(compiled)} capabilities from {self.registry_path}"
        )

    def reload(self) -> None:
        """Force re-read of YAML — useful when watcher detects changes.
        Re-embeds descriptions in a background thread (Phase 11.R)."""
        self._capabilities = []
        # Reset structural counters but keep query counters so reloads don't
        # erase historical match stats.
        self._stats["load_errors"] = 0
        self._stats["bad_patterns"] = 0
        self._stats["descriptions_embedded"] = 0
        self._load()
        if self._embedder is not None:
            self._start_embedding_build_async()

    # ── Routing ───────────────────────────────────────────────────────

    def route(self, intent: str) -> Optional[CapabilityMatch]:
        """First regex hit wins. On regex-miss, tries semantic fallback if
        an embedder is wired. Returns None if neither matches."""
        if not intent or not intent.strip():
            self._stats["no_match"] += 1
            return None

        normalized_intent = re.sub(r"\s+", " ", intent).strip()
        coding_provider = _coding_provider_intent(normalized_intent)

        # Phase 1 — regex (fast, deterministic)
        for cap in self._capabilities:
            if not self._provider_allows(cap, coding_provider):
                continue
            for pat in cap.patterns:
                if pat.search(normalized_intent):
                    self._stats["matches"] += 1
                    self._stats["regex_matches"] += 1
                    return CapabilityMatch(
                        capability=cap.capability,
                        description=cap.description,
                        primary_names=cap.primary_names,
                        supporting_names=cap.supporting_names,
                        matched_pattern=pat.pattern,
                        match_method="regex",
                        execution_target=cap.execution_target,
                        arg_extractor=cap.arg_extractor,
                        arg_kwarg=cap.arg_kwarg,
                        feedback_loop=cap.feedback_loop,
                        validator=cap.validator,
                    )

        # Phase 2 — semantic fallback (only when an embedder is wired)
        sem_match = self._semantic_route(normalized_intent, coding_provider)
        if sem_match is not None:
            return sem_match

        self._stats["no_match"] += 1
        return None

    @staticmethod
    def _provider_allows(
        capability: _CompiledCapability,
        provider_intent: _CodingProviderIntent,
    ) -> bool:
        if capability.coding_provider is None:
            return True
        if provider_intent is _CodingProviderIntent.BLOCKED:
            return False
        return capability.coding_provider == provider_intent.value

    def _semantic_route(
        self,
        intent: str,
        coding_provider: _CodingProviderIntent,
    ) -> Optional[CapabilityMatch]:
        """Embed intent + cosine vs cached capability descriptions.
        First match >= threshold wins. Tracks below-threshold hits
        separately so coverage gaps can be diagnosed."""
        if self._embedder is None:
            return None

        # Lazy build if router was set_embedder'd before any capability
        # was loaded, or if reload() emptied the cache.
        if self._stats.get("descriptions_embedded", 0) == 0:
            self._build_embeddings()

        try:
            intent_vec = self._embed_text(intent)
        except Exception as e:
            logger.debug(f"[cap-router] intent embed failed: {e}")
            return None
        if not intent_vec:
            return None

        best_cap = None
        best_sim = 0.0
        best_source = "desc"
        for cap in self._capabilities:
            if not self._provider_allows(cap, coding_provider):
                continue
            # Track the highest cosine across description + all anchors.
            # Anchors typically score higher because they're shorter and
            # syntactically closer to user intents.
            cap_sims: List[Tuple[float, str]] = []
            if cap.description_embedding is not None:
                cap_sims.append((_cosine(intent_vec, cap.description_embedding), "desc"))
            for i, vec in enumerate(cap.anchor_embeddings):
                cap_sims.append((_cosine(intent_vec, vec), f"anchor[{i}]"))
            if not cap_sims:
                continue
            local_sim, local_src = max(cap_sims, key=lambda x: x[0])
            if local_sim > best_sim:
                best_sim = local_sim
                best_cap = cap
                best_source = local_src

        if best_cap is None:
            return None

        if best_sim < self._semantic_threshold:
            self._stats["semantic_below_threshold"] += 1
            logger.debug(
                f"[cap-router] best semantic match {best_cap.capability!r} "
                f"sim={best_sim:.3f} via {best_source} below threshold {self._semantic_threshold}"
            )
            return None

        self._stats["matches"] += 1
        self._stats["semantic_matches"] += 1
        return CapabilityMatch(
            capability=best_cap.capability,
            description=best_cap.description,
            primary_names=best_cap.primary_names,
            supporting_names=best_cap.supporting_names,
            matched_pattern=f"<semantic sim={best_sim:.3f} via {best_source}>",
            match_method="semantic",
            execution_target=best_cap.execution_target,
            arg_extractor=best_cap.arg_extractor,
            arg_kwarg=best_cap.arg_kwarg,
            feedback_loop=best_cap.feedback_loop,
            validator=best_cap.validator,
        )

    # ── Stats / introspection ─────────────────────────────────────────

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "registry_path": str(self.registry_path),
            "registry_size": len(self._capabilities),
            "capabilities": [c.capability for c in self._capabilities],
            "semantic_threshold": self._semantic_threshold,
            **self._stats,
        }

    def list_capabilities(self) -> List[Dict[str, Any]]:
        """Public listing for /api/capabilities/list — useful for the UI
        to render which agents handle which intent kind."""
        return [
            {
                "capability": c.capability,
                "description": c.description,
                "primary": c.primary_names,
                "supporting": c.supporting_names,
                "pattern_count": len(c.patterns),
                "anchor_count": len(c.anchor_phrases),
                "has_execution_target": bool(c.execution_target),
                "execution_target_kind": (
                    c.execution_target.split(":", 1)[0] if c.execution_target and ":" in c.execution_target else None
                ),
                "has_feedback_loop": bool(c.feedback_loop and c.feedback_loop.get("enabled")),
                "has_validator": bool(c.validator and c.validator.get("kind")),
                "validator_kind": (c.validator.get("kind") if c.validator else None),
                "embedded": bool(c.description_embedding),
                "anchors_embedded": len(c.anchor_embeddings),
            }
            for c in self._capabilities
        ]

    def get_capability(self, name: str) -> Optional[Dict[str, Any]]:
        """Detail for a single capability — patterns, anchors, embedding status.
        Used by /api/capabilities/{name}."""
        for c in self._capabilities:
            if c.capability == name:
                return {
                    "capability": c.capability,
                    "description": c.description,
                    "primary": c.primary_names,
                    "supporting": c.supporting_names,
                    "patterns": [p.pattern for p in c.patterns],
                    "anchor_phrases": list(c.anchor_phrases),
                    "execution_target": c.execution_target,
                    "arg_extractor": c.arg_extractor,
                    "arg_kwarg": c.arg_kwarg,
                    "feedback_loop": c.feedback_loop,
                    "validator": c.validator,
                    "embedded": bool(c.description_embedding),
                    "anchors_embedded": len(c.anchor_embeddings),
                }
        return None
