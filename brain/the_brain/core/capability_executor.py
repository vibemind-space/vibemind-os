"""Capability Executor — Phase 1.5 (direct python-function execution).

Resolves and invokes a `direct:<module.path>:<function>` execution target
declared on a capability in capabilities.yaml. Used when an intent matches
a capability that should bypass the agent-broadcast discourse and instead
call an existing python function (e.g. evaluate_bubble_readiness).

Validates the target on registry-load so a typo or missing module fails
fast (capability marked inactive in router stats) instead of failing per
request at runtime.

See docs/plans/2026-05-01-capability-router-plan.md, "Phase 1.5" section.
"""

from __future__ import annotations

import importlib
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def _ensure_vibemind_paths() -> None:
    """Direct-execution targets often live outside Brain's own tree (e.g.
    spaces/mirofish/tools/mirofish_tools.py). Brain's start_server only
    adds the_brain/ to sys.path; for direct-execution to work we need the
    sibling tree roots too. Idempotent: each path is added at most once."""
    try:
        # capability_executor.py lives at <repo>/vibemind-os/brain/the_brain/core/
        # → repo root is 4 levels up.
        here = Path(__file__).resolve()
        repo_root = here.parent.parent.parent.parent.parent  # repo root
        # Common roots used by direct-execution targets
        roots = [
            repo_root / "vibemind-os",
            repo_root / "vibemind-os" / "spaces",
            repo_root / "vibemind-os" / "voice" / "python",
        ]
        for r in roots:
            r_str = str(r)
            if r.exists() and r_str not in sys.path:
                sys.path.insert(0, r_str)
    except Exception as e:
        logger.debug(f"[executor] _ensure_vibemind_paths failed: {e}")


_ensure_vibemind_paths()


class DirectExecutor:
    """Resolves and invokes a 'direct:module:function' execution target.

    Lazily imports the target module on first call. Re-import on every
    call would be wasteful; caching at instance level means a code change
    inside the target module needs a Brain restart (or watcher-driven
    reload, future Phase 2 followup) to take effect.
    """

    def __init__(self, target: str):
        # target = "direct:spaces.mirofish.tools.mirofish_tools:evaluate_bubble_readiness"
        if not target or ":" not in target:
            raise ValueError(f"invalid execution_target: {target!r}")
        parts = target.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"execution_target must be 'direct:module:function', got {target!r}")
        kind, module_path, func_name = parts
        if kind != "direct":
            raise ValueError(f"unsupported executor kind: {kind!r} (only 'direct' in Phase 1.5)")
        self.target = target
        self.module_path = module_path
        self.func_name = func_name
        self._fn: Optional[Callable] = None
        self._stats = {
            "calls": 0,
            "errors": 0,
            "last_error": None,
            "last_call_ts": None,
            "total_elapsed_s": 0.0,
        }

    def _resolve(self) -> Callable:
        if self._fn is None:
            mod = importlib.import_module(self.module_path)
            fn = getattr(mod, self.func_name, None)
            if fn is None or not callable(fn):
                raise AttributeError(
                    f"{self.module_path} has no callable '{self.func_name}'"
                )
            self._fn = fn
        return self._fn

    def is_resolvable(self) -> bool:
        """Cheap check used during capability registry load — does the
        module import and the named function exist? Returns False without
        raising so the router can mark the capability inactive."""
        try:
            self._resolve()
            return True
        except Exception as e:
            logger.warning(
                f"[executor] target {self.target!r} not resolvable: "
                f"{type(e).__name__}: {e}"
            )
            return False

    def call(self, *args, **kwargs) -> Dict[str, Any]:
        """Run the target function. Always returns a result envelope so
        callers don't need exception handling — `ok=False` on failure
        with `error` describing what broke."""
        t0 = time.time()
        self._stats["calls"] += 1
        self._stats["last_call_ts"] = t0
        try:
            fn = self._resolve()
            out = fn(*args, **kwargs)
            elapsed = time.time() - t0
            self._stats["total_elapsed_s"] += elapsed
            return {
                "ok": True,
                "result": out,
                "elapsed_s": elapsed,
                "target": self.target,
            }
        except Exception as e:
            elapsed = time.time() - t0
            self._stats["errors"] += 1
            self._stats["last_error"] = f"{type(e).__name__}: {e}"
            logger.warning(
                f"[executor] {self.target} failed: {type(e).__name__}: {e}"
            )
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "elapsed_s": elapsed,
                "target": self.target,
            }

    def call_with_arg(self, arg: Any, arg_kwarg: Optional[str] = None,
                      extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convenience: shape the extracted arg according to the YAML's
        `arg_kwarg` field. Two patterns covered:

        - arg_kwarg=None        → fn(arg)         positional
        - arg_kwarg='title'     → fn({"title": arg, **extra_params})   single-dict
                                                       for legacy voice-tool API

        Phase 11.P — `extra_params` lets the plan-executor pass auxiliary
        context (e.g. `_intent` so tools can re-extract args the planner
        couldn't fit into a single (arg_kwarg, arg_template) pair).
        """
        if arg_kwarg:
            payload = {arg_kwarg: arg}
            if extra_params:
                # Merge but don't overwrite the primary arg.
                for k, v in extra_params.items():
                    if k != arg_kwarg and v not in (None, ""):
                        payload[k] = v
            return self.call(payload)
        if extra_params:
            payload = {"value": arg, **extra_params}
            return self.call(payload)
        return self.call(arg)

    def stats_dict(self) -> Dict[str, Any]:
        avg_ms = 0.0
        if self._stats["calls"] > 0:
            avg_ms = (self._stats["total_elapsed_s"] / self._stats["calls"]) * 1000
        return {
            "target": self.target,
            "resolvable": self._fn is not None,
            "calls": self._stats["calls"],
            "errors": self._stats["errors"],
            "last_error": self._stats["last_error"],
            "avg_call_ms": round(avg_ms, 1),
        }


def extract_arg(intent_text: str, arg_extractor: Optional[str]) -> Optional[str]:
    """Pull a positional arg out of the user's intent using the extractor
    spec from capabilities.yaml. Returns None if no spec or no match.

    Spec format: 'regex:<pattern>' — the first capture group is the arg.
    Future extractors (e.g. 'jsonpath:$.bubble') can extend this without
    breaking existing capabilities.

    Example:
        intent_text = 'evaluate the "Brain Capability Router" bubble'
        arg_extractor = 'regex:["\\\']([^"\\\']+)["\\\']'
        → 'Brain Capability Router'
    """
    if not arg_extractor or not intent_text:
        return None
    if ":" not in arg_extractor:
        logger.warning(f"[executor] arg_extractor missing kind: {arg_extractor!r}")
        return None
    kind, spec = arg_extractor.split(":", 1)
    if kind == "regex":
        try:
            m = re.search(spec, intent_text, re.IGNORECASE)
            if m and m.groups():
                return m.group(1).strip()
            elif m:
                return m.group(0).strip()
        except re.error as e:
            logger.warning(f"[executor] bad arg_extractor regex {spec!r}: {e}")
        return None
    logger.warning(f"[executor] unsupported arg_extractor kind: {kind!r}")
    return None
