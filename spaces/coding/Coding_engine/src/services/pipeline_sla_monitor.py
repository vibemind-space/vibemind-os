"""Pipeline SLA monitor.

Tracks and enforces service-level agreements for pipeline metrics.
Supports defining SLAs per pipeline/metric pair, recording metric
values, detecting violations, and computing compliance rates.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

VALID_COMPARISONS = {"lte", "gte"}


@dataclass
class SlaRecord:
    """A single SLA definition."""

    sla_id: str = ""
    pipeline_id: str = ""
    metric_name: str = ""
    threshold: float = 0.0
    comparison: str = "lte"
    status: str = "compliant"
    last_value: float = 0.0
    violations: int = 0
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline SLA Monitor
# ---------------------------------------------------------------------------


class PipelineSlaMonitor:
    """Monitor and enforce SLAs for pipeline operations."""

    def __init__(self) -> None:
        self._slas: Dict[str, SlaRecord] = {}
        self._name_index: Dict[str, str] = {}  # "pipeline_id:metric_name" -> sla_id
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_defined": 0,
            "total_deleted": 0,
            "total_recordings": 0,
            "total_violations": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix ``psm-``."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"psm-{digest}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_dict(self, rec: SlaRecord) -> Dict:
        return {
            "sla_id": rec.sla_id,
            "pipeline_id": rec.pipeline_id,
            "metric_name": rec.metric_name,
            "threshold": rec.threshold,
            "comparison": rec.comparison,
            "status": rec.status,
            "last_value": rec.last_value,
            "violations": rec.violations,
            "created_at": rec.created_at,
        }

    def _fire(self, action: str, sla_id: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, sla_id)
            except Exception:
                logger.warning("callback_error", action=action, sla_id=sla_id)

    def _check_compliance(self, value: float, threshold: float, comparison: str) -> bool:
        if comparison == "lte":
            return value <= threshold
        if comparison == "gte":
            return value >= threshold
        return True

    # ------------------------------------------------------------------
    # SLA definition
    # ------------------------------------------------------------------

    def define_sla(
        self,
        pipeline_id: str,
        metric_name: str,
        threshold: float,
        comparison: str = "lte",
    ) -> str:
        """Define a new SLA.

        Returns sla_id (``psm-...``).  Returns ``""`` if a SLA for this
        *pipeline_id* + *metric_name* combination already exists.
        """
        key = f"{pipeline_id}:{metric_name}"
        if key in self._name_index:
            logger.warning(
                "sla_already_exists",
                pipeline_id=pipeline_id,
                metric_name=metric_name,
            )
            return ""

        if comparison not in VALID_COMPARISONS:
            comparison = "lte"

        sla_id = self._generate_id(key)
        now = time.time()

        rec = SlaRecord(
            sla_id=sla_id,
            pipeline_id=pipeline_id,
            metric_name=metric_name,
            threshold=threshold,
            comparison=comparison,
            status="compliant",
            last_value=0.0,
            violations=0,
            created_at=now,
        )

        self._slas[sla_id] = rec
        self._name_index[key] = sla_id
        self._stats["total_defined"] += 1

        logger.info(
            "sla_defined",
            sla_id=sla_id,
            pipeline_id=pipeline_id,
            metric_name=metric_name,
            threshold=threshold,
            comparison=comparison,
        )
        self._fire("define", sla_id)
        return sla_id

    # ------------------------------------------------------------------
    # SLA retrieval
    # ------------------------------------------------------------------

    def get_sla(self, sla_id: str) -> Optional[Dict]:
        """Return SLA dict or ``None``."""
        self._stats["total_lookups"] += 1
        rec = self._slas.get(sla_id)
        if rec is None:
            return None
        return self._to_dict(rec)

    def get_sla_by_name(self, pipeline_id: str, metric_name: str) -> Optional[Dict]:
        """Return SLA dict by pipeline_id + metric_name, or ``None``."""
        self._stats["total_lookups"] += 1
        key = f"{pipeline_id}:{metric_name}"
        sla_id = self._name_index.get(key)
        if sla_id is None:
            return None
        rec = self._slas.get(sla_id)
        if rec is None:
            return None
        return self._to_dict(rec)

    # ------------------------------------------------------------------
    # Metric recording
    # ------------------------------------------------------------------

    def record_metric(self, pipeline_id: str, metric_name: str, value: float) -> Dict:
        """Record a metric value and check compliance.

        Returns ``{"compliant": bool, "threshold": float, "value": float}``.
        If no SLA is found for the pair, returns compliant with threshold 0.
        """
        self._stats["total_recordings"] += 1
        key = f"{pipeline_id}:{metric_name}"
        sla_id = self._name_index.get(key)

        if sla_id is None or sla_id not in self._slas:
            logger.debug(
                "record_metric_no_sla",
                pipeline_id=pipeline_id,
                metric_name=metric_name,
            )
            return {"compliant": True, "threshold": 0, "value": value}

        rec = self._slas[sla_id]
        compliant = self._check_compliance(value, rec.threshold, rec.comparison)
        rec.last_value = value

        if compliant:
            rec.status = "compliant"
        else:
            rec.status = "violated"
            rec.violations += 1
            self._stats["total_violations"] += 1
            logger.info(
                "sla_violated",
                sla_id=sla_id,
                pipeline_id=pipeline_id,
                metric_name=metric_name,
                value=value,
                threshold=rec.threshold,
            )
            self._fire("violation", sla_id)

        return {"compliant": compliant, "threshold": rec.threshold, "value": value}

    # ------------------------------------------------------------------
    # Violations & compliance
    # ------------------------------------------------------------------

    def get_violations(self, pipeline_id: Optional[str] = None) -> List[Dict]:
        """Return list of SLA dicts currently in ``violated`` status.

        Optionally filter by *pipeline_id*.
        """
        result: List[Dict] = []
        for rec in self._slas.values():
            if rec.status != "violated":
                continue
            if pipeline_id is not None and rec.pipeline_id != pipeline_id:
                continue
            result.append(self._to_dict(rec))
        return result

    def get_compliance_rate(self, pipeline_id: str) -> float:
        """Return ratio of compliant SLAs to total SLAs for *pipeline_id*.

        Returns ``1.0`` if there are no SLAs for the pipeline.
        """
        total = 0
        compliant = 0
        for rec in self._slas.values():
            if rec.pipeline_id != pipeline_id:
                continue
            total += 1
            if rec.status == "compliant":
                compliant += 1
        if total == 0:
            return 1.0
        return compliant / total

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_sla(self, sla_id: str) -> bool:
        """Delete an SLA. Returns ``True`` if deleted, ``False`` if not found."""
        rec = self._slas.get(sla_id)
        if rec is None:
            return False

        key = f"{rec.pipeline_id}:{rec.metric_name}"
        self._name_index.pop(key, None)
        del self._slas[sla_id]
        self._stats["total_deleted"] += 1

        logger.info("sla_deleted", sla_id=sla_id)
        self._fire("delete", sla_id)
        return True

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return list of unique pipeline_ids."""
        seen: set = set()
        result: List[str] = []
        for rec in self._slas.values():
            if rec.pipeline_id not in seen:
                seen.add(rec.pipeline_id)
                result.append(rec.pipeline_id)
        return result

    def get_pipeline_slas(self, pipeline_id: str) -> List[Dict]:
        """Return list of SLA dicts for *pipeline_id*."""
        return [
            self._to_dict(rec)
            for rec in self._slas.values()
            if rec.pipeline_id == pipeline_id
        ]

    def get_sla_count(self) -> int:
        """Return total number of defined SLAs."""
        return len(self._slas)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns ``True`` if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "active_slas": len(self._slas),
            "active_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._slas.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_sla_monitor_reset")
