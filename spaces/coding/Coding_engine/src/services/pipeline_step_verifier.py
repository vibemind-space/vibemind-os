"""Pipeline step verifier — verifies pipeline step outputs against expected schemas/values.

Compares actual pipeline step outputs against expected values or schemas,
recording verification results with pass/fail status and detailed diffs.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepVerifierState:
    """Internal state for the PipelineStepVerifier service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineStepVerifier:
    """Verifies pipeline step outputs against expected schemas/values.

    Records verification results including pass/fail status, mismatches,
    and metadata for auditing pipeline correctness.
    """

    PREFIX = "psvr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepVerifierState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks and on_change; exceptions are silenced."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest quarter of entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = len(self._state.entries) // 4
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # Verification logic
    # ------------------------------------------------------------------

    def _compare(self, expected: Any, actual: Any) -> Dict[str, Any]:
        """Compare expected vs actual and return result details."""
        mismatches: List[Dict[str, Any]] = []

        if isinstance(expected, dict) and isinstance(actual, dict):
            all_keys = set(expected.keys()) | set(actual.keys())
            for key in sorted(all_keys):
                if key not in actual:
                    mismatches.append({"field": key, "reason": "missing_in_actual", "expected": expected[key]})
                elif key not in expected:
                    mismatches.append({"field": key, "reason": "extra_in_actual", "actual": actual[key]})
                elif expected[key] != actual[key]:
                    mismatches.append({"field": key, "reason": "value_mismatch", "expected": expected[key], "actual": actual[key]})
        elif expected != actual:
            mismatches.append({"field": "_root", "reason": "value_mismatch", "expected": expected, "actual": actual})

        passed = len(mismatches) == 0
        return {"passed": passed, "mismatches": mismatches}

    # ------------------------------------------------------------------
    # verify
    # ------------------------------------------------------------------

    def verify(
        self,
        pipeline_id: str,
        step_name: str,
        expected: Any,
        actual: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Verify a pipeline step output against expected. Returns verification ID."""
        self._prune()
        verification_id = self._generate_id()
        now = time.time()
        comparison = self._compare(expected, actual)
        entry = {
            "verification_id": verification_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "expected": expected,
            "actual": actual,
            "passed": comparison["passed"],
            "mismatches": comparison["mismatches"],
            "metadata": metadata or {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[verification_id] = entry
        self._fire("verification_created", dict(entry))
        return verification_id

    # ------------------------------------------------------------------
    # get_verification
    # ------------------------------------------------------------------

    def get_verification(self, verification_id: str) -> Optional[dict]:
        """Get a single verification by ID. Returns None if not found."""
        entry = self._state.entries.get(verification_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # get_verifications
    # ------------------------------------------------------------------

    def get_verifications(
        self, pipeline_id: str = "", step_name: str = "", limit: int = 50
    ) -> List[dict]:
        """Get verifications, newest first. Optionally filter by pipeline_id and/or step_name."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        if step_name:
            entries = [e for e in entries if e.get("step_name") == step_name]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_verification_count
    # ------------------------------------------------------------------

    def get_verification_count(self, pipeline_id: str = "") -> int:
        """Count verifications, optionally filtering by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        entries = list(self._state.entries.values())
        total = len(entries)
        passed = sum(1 for e in entries if e.get("passed") is True)
        failed = sum(1 for e in entries if e.get("passed") is False)
        return {
            "total_verifications": total,
            "passed_count": passed,
            "failed_count": failed,
        }

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all entries, callbacks, on_change, and reset sequence."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
